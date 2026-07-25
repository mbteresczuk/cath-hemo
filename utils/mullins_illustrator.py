"""
Mullins illustrator — compose NEW congenital-heart diagrams from your REAL
hand-drawn art, using the Structure Painter's segmaps as the segmentation AND as
registration landmarks.

Why registration
----------------
Each diagram is an independent freehand drawing (line-art IoU between two
diagrams is ~0.03), so a structure cannot be pasted at raw pixel coordinates —
it lands where the *donor* drew it, not where it belongs on the base. But the
painter tells us where every structure sits and how it is oriented in each
drawing. We use the structures painted in BOTH diagrams as corresponding
landmarks, fit a similarity transform (Umeyama) donor->base (typically ~15-18
landmarks, ~6-7px residual), warp the donor into the base's frame, and only then
transfer the requested feature. The feature now aligns to the base's own septa
and chambers.

No model, no GPU, no SAM, no Vision tagging — just the painter's labels.

Public API
----------
    illustrate(text, base_id="Normal_PDA") -> {"image", "dx", "layers"}
    compose(base_id, feature_ids)          -> PIL.Image
"""
from __future__ import annotations

import json
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T = os.path.join(HERE, "training")
IMG = os.path.join(T, "dataset", "images")
SEG = os.path.join(T, "labels", "segmaps")
LBL = os.path.join(T, "labels")
CAT = os.path.join(T, "labeler", "catalog.json")
N = 512


# ── palette ──────────────────────────────────────────────────────────────────
def _hx(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


_catalog = None


def _catcol():
    global _catalog
    if _catalog is None:
        c = json.load(open(CAT))
        _catalog = {it["short"]: _hx(it["color"]) for g in c["groups"].values() for it in g}
    return _catalog


def _customs(did):
    p = os.path.join(LBL, did + ".json")
    if not os.path.exists(p):
        return {}
    d = json.load(open(p))
    return {c["name"]: _hx(c["color"]) for c in d.get("customs", []) if isinstance(c, dict)}


# ── loaders / segmentation ───────────────────────────────────────────────────
def _load_img(did):
    return Image.open(os.path.join(IMG, did + ".png")).convert("RGB").resize((N, N), Image.LANCZOS)


def _load_seg(did):
    return np.array(Image.open(os.path.join(SEG, did + ".png")).convert("RGB").resize((N, N), Image.NEAREST))


def _label_map(did):
    """Classify each painted pixel to the NEAREST palette color (so near-identical
    defect colors like ASD/VSD are still separated)."""
    seg = _load_seg(did).astype(int)
    names, cols = [], []
    for n, c in {**_catcol(), **_customs(did)}.items():
        names.append(n); cols.append(c)
    cols = np.array(cols)
    painted = seg.sum(2) > 60
    flat = seg[painted]
    idx = np.abs(flat[:, None, :] - cols[None, :, :]).sum(2).argmin(1)
    lm = np.full((N, N), -1, int)
    lm[painted] = idx
    return lm, names


def _regions(did, min_px=120):
    lm, names = _label_map(did)
    return {n: (lm == k) for k, n in enumerate(names) if (lm == k).sum() > min_px}


def _centroid(m):
    ys, xs = np.where(m)
    return np.array([xs.mean(), ys.mean()])


def _dilate(m, r):
    o = m.copy()
    for _ in range(r):
        g = o.copy()
        g[:-1] |= o[1:]; g[1:] |= o[:-1]; g[:, :-1] |= o[:, 1:]; g[:, 1:] |= o[:, :-1]
        o = g
    return o


# ── registration ─────────────────────────────────────────────────────────────
_DEFECTS = ("VSD", "ASD", "PDA", "LSVC_CS")


def _umeyama(s, d):
    ms, md = s.mean(0), d.mean(0)
    S, D = s - ms, d - md
    U, dd, Vt = np.linalg.svd((D.T @ S) / len(s))
    R = U @ Vt
    if np.linalg.det(R) < 0:
        U[:, -1] *= -1; R = U @ Vt
    sc = float(np.sum(dd) / ((S ** 2).sum() / len(s)))
    return sc, R, md - sc * R @ ms


_warp_cache = {}


def _warp_donor(base_id, donor_id):
    """Return (warped_donor_rgb, base->donor affine coeffs, nlandmarks)."""
    key = (base_id, donor_id)
    if key in _warp_cache:
        return _warp_cache[key]
    Rb, Rd = _regions(base_id), _regions(donor_id)
    shared = [n for n in Rd if n in Rb and n not in _DEFECTS]
    s = np.array([_centroid(Rd[n]) for n in shared])
    d = np.array([_centroid(Rb[n]) for n in shared])
    sc, R, t = _umeyama(s, d)
    Rinv = np.linalg.inv(R * sc)
    off = -Rinv @ t
    coeffs = (Rinv[0, 0], Rinv[0, 1], off[0], Rinv[1, 0], Rinv[1, 1], off[1])
    warped = np.array(_load_img(donor_id).transform(
        (N, N), Image.AFFINE, coeffs, resample=Image.BICUBIC, fillcolor=(255, 255, 255)))
    out = (warped, coeffs, len(shared))
    _warp_cache[key] = out
    return out


def _warp_mask(mask, coeffs):
    im = Image.fromarray((mask * 255).astype(np.uint8)).transform(
        (N, N), Image.AFFINE, coeffs, resample=Image.NEAREST)
    return np.array(im) > 128


# ── feature table ────────────────────────────────────────────────────────────
# host  : base structure whose zone we replace (for septal defects)
# feat  : donor structure to warp+add (for vessels)
# mode  : "replace" (swap the base's septum for the donor's defect septum)
#         "add"     (darker-wins overlay of the warped feature)
# Donor table for a NORMAL biventricular base. Each finding names a donor drawing
# that carries the structure, painted in your Structure Painter. Single-ventricle
# lesions (Glenn/Fontan/HLHS) register poorly onto a normal base and belong to a
# separate base family — not included here.
FINDINGS = {
    "ASD": {"label": "ASD", "donor": "ASD_VSD", "host": "IAS", "mode": "replace",
            "aliases": ["asd", "atrial septal defect", "secundum", "pfo"]},
    "VSD": {"label": "VSD", "donor": "ASD_VSD", "host": "IVS", "mode": "replace",
            "aliases": ["vsd", "ventricular septal defect", "perimembranous"]},
    "PDA": {"label": "PDA", "donor": "Normal_PDA", "feat": "PDA", "mode": "add",
            "aliases": ["pda", "patent ductus", "ductus arteriosus"]},
    "LSVC_CS": {"label": "LSVC → CS", "donor": "CoarctationAorta_LAA_Bil_SVCs",
                "feat": "LSVC_CS", "mode": "add",
                "aliases": ["lsvc", "l-svc", "left svc", "persistent left svc",
                            "lsvc to cs", "lsvc to coronary sinus"]},
    "COARC": {"label": "Coarctation", "donor": "CoarctationAorta_PDA",
              "feat": "coarctation", "mode": "add",
              "aliases": ["coarc", "coarctation", "coa", "aortic coarctation"]},
    "PS": {"label": "Pulmonary stenosis", "donor": "ToF__PS",
           "feat": "Pulmonary stenosis", "mode": "add",
           "aliases": ["ps", "pulmonary stenosis", "pulmonic stenosis", "valvar ps"]},
}


def parse(text):
    t = (" " + (text or "").lower() + " ").replace("/", " ")
    return [fid for fid, f in FINDINGS.items() if any(a in t for a in f["aliases"])]


def _heal(comp, base_id, region, donor_id):
    """Repair a base region by stamping the same area from a clean donor,
    registered into the base frame. Used to remove the ductus from Normal_PDA
    and rebuild a continuous aortic arch — cleaner than whitening, which would
    leave gaps or dashed remnants at the arch/aorta junction."""
    warped, coeffs, _ = _warp_donor(base_id, donor_id)
    zone = _dilate(region, 12)
    comp[zone] = warped[zone]
    return comp


# Structures to strip from a stand-in base, with the clean donor used to heal
# the area so it matches surrounding anatomy: {base: [(structure, heal_donor)]}
_BASE_STRIP = {"Normal_PDA": [("PDA", "VSD")]}


def compose(base_id, feature_ids):
    base = np.array(_load_img(base_id))
    Rb = _regions(base_id)
    comp = base.copy()
    for s, donor in _BASE_STRIP.get(base_id, []):
        if s in Rb:
            comp = _heal(comp, base_id, Rb[s], donor)
    for fid in feature_ids:
        f = FINDINGS[fid]
        warped, coeffs, _ = _warp_donor(base_id, f["donor"])
        if f["mode"] == "replace":
            if f["host"] not in Rb:
                continue
            zone = _dilate(Rb[f["host"]], 10)
            comp[zone] = warped[zone]
            ring = _dilate(zone, 4) & ~zone
            comp[ring] = np.minimum(comp[ring], warped[ring])
        else:  # add
            fm = _warp_mask(_regions(f["donor"])[f["feat"]], coeffs)
            zone = _dilate(fm, 6)
            comp[zone] = np.minimum(comp[zone], warped[zone])
    return Image.fromarray(comp.astype(np.uint8))


def illustrate(text, base_id="Normal_PDA"):
    hits = parse(text)
    img = compose(base_id, hits)
    labels = [FINDINGS[h]["label"] for h in hits]
    return {"image": img, "dx": " + ".join(labels) or "Normal", "layers": hits}


if __name__ == "__main__":
    out = illustrate("ASD, VSD, L-SVC to coronary sinus")
    out["image"].save("/tmp/mullins_new.png")
    print("dx:", out["dx"], "| layers:", out["layers"], "-> /tmp/mullins_new.png")

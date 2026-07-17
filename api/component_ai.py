"""
AI assists for the component-authoring tool:

  suggest_tags()   — Claude Vision looks at the source diagram with the masked
                     region highlighted and returns {segment, chamber, loop,
                     notes} so the author just confirms instead of typing.

  segment_click()  — Segment Anything (SAM / MobileSAM) turns a single click
                     into a clean mask, so masking is one click instead of a
                     hand-drawn polygon. Optional: needs a local model install
                     (see setup_sam.sh). Degrades gracefully when absent.
"""
import base64
import io
import json
import os

import anthropic
from PIL import Image

# ── LLM auto-tagging ───────────────────────────────────────────────────────

_TAG_SEGMENTS = ["atrium", "ventricle", "av_connection", "outflow", "arch",
                 "pulmonary_artery", "systemic_vein", "pulmonary_vein", "lesion"]

_TAG_PROMPT = """You are labeling ONE anatomical component cut from a congenital-heart
(Van Praagh / Mullins style) diagram. The whole diagram is: "{name}".

The region being labeled is outlined in RED on the image.

Return ONLY a JSON object with these keys (omit a key if not applicable):
  "segment":  one of {segments}
  "chamber":  e.g. "RV", "LV", "RA", "LA"  (only for atrium/ventricle)
  "loop":     "D" or "L"  (ventricular loop, only if the diagram implies it)
  "notes":    short free text, e.g. "DORV, both arteries from RV" or "PS"

Base "loop" and lesion "notes" on the diagram title's segmental notation
(e.g. {{S,L,L}} = L-loop) and abbreviations (DORV, TGA, PS, VSD, Fontan…).
Judge the segment/chamber from what is actually outlined in red.
Output the JSON and nothing else."""


def suggest_tags(image_b64_png: str, diagram_name: str) -> dict:
    """Return suggested tags for the highlighted component. image is a PNG
    (base64) of the source diagram with the mask region outlined in red."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=api_key)
    prompt = _TAG_PROMPT.format(name=diagram_name, segments=", ".join(_TAG_SEGMENTS))
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
             "media_type": "image/png", "data": image_b64_png}},
            {"type": "text", "text": prompt},
        ]}],
    )
    txt = msg.content[0].text.strip()
    # tolerate ```json fences
    if txt.startswith("```"):
        txt = txt.strip("`")
        txt = txt.split("\n", 1)[1] if "\n" in txt else txt
    try:
        start, end = txt.find("{"), txt.rfind("}")
        return json.loads(txt[start:end + 1])
    except Exception:
        return {"notes": txt[:120]}


# ── SAM click-to-segment (optional local model) ────────────────────────────

_sam_predictor = None
_sam_error = None


def _load_sam():
    """Lazy-load a SAM predictor. Tries MobileSAM (light) then segment-anything.
    Returns (predictor, None) or (None, reason)."""
    global _sam_predictor, _sam_error
    if _sam_predictor is not None or _sam_error is not None:
        return _sam_predictor, _sam_error
    ckpt = os.environ.get("SAM_CHECKPOINT", "")
    try:
        import numpy as np  # noqa
        try:
            from mobile_sam import sam_model_registry, SamPredictor
            mtype = "vit_t"
        except Exception:
            from segment_anything import sam_model_registry, SamPredictor
            mtype = os.environ.get("SAM_MODEL_TYPE", "vit_b")
        if not ckpt or not os.path.exists(ckpt):
            _sam_error = ("SAM model not found. Set SAM_CHECKPOINT to a downloaded "
                          "checkpoint (see setup_sam.sh).")
            return None, _sam_error
        sam = sam_model_registry[mtype](checkpoint=ckpt)
        sam.to("cpu")
        _sam_predictor = SamPredictor(sam)
        return _sam_predictor, None
    except Exception as e:
        _sam_error = f"SAM not installed ({e}). Run setup_sam.sh to enable one-click masking."
        return None, _sam_error


def sam_available() -> bool:
    pred, _ = _load_sam()
    return pred is not None


def segment_click(image_path: str, x: int, y: int) -> dict:
    """Run SAM at click (x,y) on the source image; return a mask polygon
    (list of [x,y] in source-image coordinates)."""
    pred, err = _load_sam()
    if err:
        return {"ok": False, "error": err}
    import numpy as np
    img = np.array(Image.open(image_path).convert("RGB"))
    pred.set_image(img)
    masks, scores, _ = pred.predict(
        point_coords=np.array([[x, y]]),
        point_labels=np.array([1]),
        multimask_output=True,
    )
    mask = masks[int(np.argmax(scores))]
    poly = _mask_to_polygon(mask)
    return {"ok": True, "polygon": poly}


def _mask_to_polygon(mask, step=6):
    """Trace the outer boundary of a boolean mask into a simplified polygon
    (no cv2 dependency — marching-square-ish border walk with subsampling)."""
    import numpy as np
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return []
    # boundary = mask pixels with a non-mask 4-neighbor
    m = mask.astype(np.uint8)
    up = np.zeros_like(m); up[1:] = m[:-1]
    dn = np.zeros_like(m); dn[:-1] = m[1:]
    lf = np.zeros_like(m); lf[:, 1:] = m[:, :-1]
    rt = np.zeros_like(m); rt[:, :-1] = m[:, 1:]
    border = (m == 1) & ((up == 0) | (dn == 0) | (lf == 0) | (rt == 0))
    by, bx = np.where(border)
    pts = np.c_[bx, by].astype(float)
    # order boundary points by angle around centroid (convex-ish structures)
    cx, cy = pts[:, 0].mean(), pts[:, 1].mean()
    ang = np.arctan2(pts[:, 1] - cy, pts[:, 0] - cx)
    order = np.argsort(ang)
    pts = pts[order][::step]
    return [[int(px), int(py)] for px, py in pts]

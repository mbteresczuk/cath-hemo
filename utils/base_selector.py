"""
Base selection for the Mullins generator.

Every diagram in the library is a candidate BASE (foundational substrate anatomy).
Given a free-text diagnosis, rank all bases by how well they match — using BOTH:
  * substrate / name  — the caption ("hypoplastic left heart ... Glenn"), scored
    with the same medical-abbreviation normalization as utils.matcher.
  * segmental anatomy — the structures actually painted in the diagram's segmap
    (catalog + custom structures from its label JSON, e.g. "Hypoplastic LV",
    "Glenn", "Fontan pathway"), so a base is matched on what it *contains*, not
    just what it's named.

The best base is used directly (if it already is the diagnosis) or as the base to
add residual features onto (place -> harmonize). "painted" bases (68 of 140) can
accept added features; all 140 can be used directly.

    select_base("HLHS with bidirectional Glenn")  ->  ranked [{id,name,score,...}]
"""
import glob
import json
import os
import re

from utils.matcher import STRONG_KEYWORDS, _normalize

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(HERE, "training", "dataset", "metadata.jsonl")
SEG_DIR = os.path.join(HERE, "training", "labels", "segmaps")
LBL_DIR = os.path.join(HERE, "training", "labels")

_index = None


def _diagram_name(caption: str) -> str:
    """Pull the human name off a training caption."""
    if "white background," in caption:
        return caption.split("white background,")[-1].strip()
    return caption.strip()


def _custom_tags(did: str) -> list:
    """Structure names painted in this diagram (from its label JSON customs)."""
    p = os.path.join(LBL_DIR, did + ".json")
    if not os.path.exists(p):
        return []
    try:
        d = json.load(open(p))
        return [c.get("name", "") for c in d.get("customs", []) if isinstance(c, dict)]
    except Exception:
        return []


def _build_index():
    global _index
    if _index is not None:
        return _index
    painted = set(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(SEG_DIR, "*.png")))
    idx = []
    for line in open(META):
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        did = os.path.splitext(os.path.basename(r["file_name"]))[0]
        name = _diagram_name(r.get("text", did))
        is_painted = did in painted
        tags = _custom_tags(did) if is_painted else []
        # searchable text = name + painted structure tags (substrate + segmental)
        text_norm = _normalize(name + " " + " ".join(tags))
        idx.append({
            "id": did,
            "name": name,
            "painted": is_painted,
            "tags": tags,
            "text_norm": text_norm,
            "text_tokens": set(text_norm.split()),
        })
    _index = idx
    return idx


# Surgical / palliation / device modifiers. When the query does NOT ask for one
# of these, a base that carries it is an over-specific (usually repaired) variant
# and should lose to the canonical native-anatomy diagram.
SURGICAL = {
    "status", "post", "sp", "repair", "repaired", "patch", "closure", "conduit",
    "band", "shunt", "stent", "device", "amplatzer", "warden", "ross", "konno",
    "rastelli", "switch", "aso", "mustard", "senning", "norwood", "sano", "glenn",
    "bdg", "bidirectional", "fontan", "ecff", "ltff", "ecf", "hemifontan", "dks",
    "bts", "rmbts", "stage", "starnes",
}


# Connective/filler words that must not contribute to matching ("ASD and VSD"
# should not match "Valvar AND subvalvar ... without VSD" on the word "and").
STOP = {"and", "with", "the", "of", "a", "to", "in", "on", "for", "s", "p", "without"}

# Severe anatomic variants — prefer the canonical (less severe) form when the
# query does not explicitly ask for them.
SEVERITY = {"atresia", "absent", "interrupted", "hypoplasia", "hypoplastic"}


def _score(diag_norm, raw_tokens, e) -> float:
    """Score one base against a normalized diagnosis (substrate + segmental)."""
    dwords = set(diag_norm.split()) - STOP
    twords = e["text_tokens"]
    raw_tokens = raw_tokens - STOP
    score = len(dwords & twords) * 3                      # word overlap
    for kw, bonus in STRONG_KEYWORDS.items():             # strong category cues
        if kw in diag_norm and kw in e["text_norm"]:
            score += bonus
    for tok in raw_tokens:                                # literal token match
        if len(tok) >= 2 and tok in twords:
            score += 5
    for w in dwords:                                      # mild miss penalty
        if len(w) > 3 and w not in twords:
            score -= 1
    # Penalize surgical/palliation modifiers the query didn't ask for, so the
    # canonical lesion beats its "s/p repair" cousins.
    score -= 4 * len((twords & SURGICAL) - dwords)
    # Bias away from SEVERE anatomic variants the query didn't ask for, so plain
    # "tetralogy of Fallot" defaults to ToF/PS, not ToF/pulmonary atresia.
    score -= 3 * len((twords & SEVERITY) - dwords)
    # Penalize extra specificity generally: base tokens beyond the query are
    # unrequested detail, so a simpler exact match wins.
    score -= 0.6 * len(twords - dwords - STOP)
    return score


def select_base(diagnosis: str, top_n: int = 5, painted_only: bool = False) -> list:
    """Rank candidate bases for a diagnosis. Returns list of dicts with 'score'."""
    if not diagnosis.strip():
        return []
    idx = _build_index()
    norm = _normalize(diagnosis)
    raw = set(re.findall(r"[a-z0-9]+", diagnosis.lower()))
    out = []
    for e in idx:
        if painted_only and not e["painted"]:
            continue
        s = _score(norm, raw, e)
        out.append({"id": e["id"], "name": e["name"], "painted": e["painted"],
                    "tags": e["tags"], "score": round(s, 1)})
    # rank by score, then prefer the simpler (shorter-named) diagram on ties
    out.sort(key=lambda x: (-x["score"], len(x["name"])))
    return out[:top_n]


if __name__ == "__main__":
    tests = [
        "ASD with PDA",
        "HLHS with bidirectional Glenn",
        "tetralogy of Fallot with pulmonary stenosis",
        "d-TGA intact ventricular septum",
        "tricuspid atresia s/p Fontan",
        "single ventricle",
        "DORV with subpulmonic VSD and pulmonary stenosis",
    ]
    for t in tests:
        print("\n=== " + t + " ===")
        for b in select_base(t, top_n=4):
            flag = "painted" if b["painted"] else "unpainted"
            print(f"  [{b['score']:3d}] {b['id']:34s} {flag}   \"{b['name']}\"")

"""
End-to-end draft generation: diagnosis text -> placed draft (base + features).

    generate(text) -> {"image": PIL, "base_id", "base_name", "findings", "added"}

Pipeline (the PLACE half of place->harmonize; CPU, instant):
  1. select_base(text)  — pick the best foundational base from ALL 140 diagrams
     (utils.base_selector, scored on substrate name + painted segmental structure).
  2. residual features  — findings named in the text (utils.mullins_illustrator.parse)
     that the chosen base does NOT already contain.
  3. place              — if there are residual features AND the base is painted,
     compose() warps them onto the base; otherwise the base drawing is used as-is
     (the base already IS the diagnosis, e.g. "HLHS with Glenn").

The returned image is the rough-but-correct draft; modal_harmonize.py renders it
into native Mullins line-art (the HARMONIZE half).
"""
from utils import mullins_illustrator as M
from utils.base_selector import select_base
from utils.diagram_library import _detect_anatomy_type


def _residual_findings(text: str, base_entry: dict):
    """(all findings named in text, findings NOT already in the base)."""
    fids = M.parse(text)
    base_text = (base_entry.get("name", "") + " " +
                 " ".join(base_entry.get("tags", []))).lower()
    residual = [fid for fid in fids
                if not any(a in base_text for a in M.FINDINGS[fid]["aliases"])]
    return fids, residual


def generate(text: str) -> dict:
    bases = select_base(text, top_n=1)
    if bases:
        base_entry = bases[0]
    else:  # nothing matched -> a normal biventricular heart is the safe default
        base_entry = {"id": "Normal", "name": "Normal", "painted": True, "tags": []}
    base_id = base_entry["id"]

    all_findings, residual = _residual_findings(text, base_entry)

    img = None
    if residual and base_entry.get("painted"):
        try:
            img = M.compose(base_id, residual)      # warp the missing features on
        except Exception:
            img = None                               # fall back to the base drawing
    if img is None:
        img = M._load_img(base_id)

    # anatomy_type + location_set drive where sats/pressures get placed later
    anatomy_type, location_set = _detect_anatomy_type(base_id)

    return {
        "image": img,
        "base_id": base_id,
        "base_name": base_entry["name"],
        "findings": [M.FINDINGS[f]["label"] for f in all_findings],
        "added": [M.FINDINGS[f]["label"] for f in residual],
        # donor diagrams whose structures were composed on — their coords for the
        # added structures should travel with the diagram to the report step.
        "added_donors": [M.FINDINGS[f]["donor"] for f in residual],
        "anatomy_type": anatomy_type,
        "location_set": location_set,
    }


if __name__ == "__main__":
    for t in ["ASD with PDA", "HLHS with bidirectional Glenn",
              "VSD and coarctation", "tetralogy of Fallot with pulmonary stenosis",
              "Normal"]:
        r = generate(t)
        print(f'{t:44s} -> base={r["base_id"]:26s} '
              f'findings={r["findings"]} added={r["added"]}')

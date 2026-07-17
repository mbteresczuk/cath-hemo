"""
Data-prep pipeline for the Mullins-style diffusion fine-tune.

Turns the ~140 existing diagrams into a training-ready dataset:

  dataset/images/<id>.png   — target: the real diagram, normalized to a
                              square white canvas at OUT_SIZE (for the LoRA
                              style fine-tune).
  dataset/images/<id>.txt   — caption (one per image, kohya/diffusers format).
  dataset/control/<id>.png  — structure map (clean line art) for the later
                              ControlNet phase.
  dataset/metadata.jsonl    — {"file_name","text"} per image (diffusers format).
  dataset/captions.jsonl    — human-readable review of every caption.

The style LoRA go/no-go test only needs images/ + captions. control/ is for
the structure-conditioning phase that follows.
"""
import json
import re
import sys
from pathlib import Path
from PIL import Image, ImageOps, ImageFilter

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))
from utils.diagram_library import load_library, get_all_diagrams  # noqa: E402

OUT = Path(__file__).parent / "dataset"
OUT_SIZE = 512
TRIGGER = "mullinsdiagram"   # LoRA style token you'll prompt with at inference

# ── caption building ────────────────────────────────────────────────────────

_ABBR = {
    "dorv": "double outlet right ventricle", "dilv": "double inlet left ventricle",
    "tof": "tetralogy of Fallot", "tga": "transposition of the great arteries",
    "l-tga": "L-transposition (congenitally corrected transposition)",
    "d-tga": "D-transposition of the great arteries",
    "hlhs": "hypoplastic left heart syndrome", "asd": "atrial septal defect",
    "vsd": "ventricular septal defect", "pda": "patent ductus arteriosus",
    "avsd": "atrioventricular septal defect", "cavc": "complete atrioventricular canal",
    "ccavc": "complete common atrioventricular canal", "uccavc": "unbalanced complete AV canal",
    "ps": "pulmonary stenosis", "pa": "pulmonary atresia", "as": "aortic stenosis",
    "ivs": "intact ventricular septum", "coa": "coarctation of the aorta",
    "coarc": "coarctation of the aorta", "iaa": "interrupted aortic arch",
    "tapvr": "total anomalous pulmonary venous return",
    "papvr": "partial anomalous pulmonary venous return",
    "raa": "right aortic arch", "laa": "left atrial appendage",
    "ltf": "lateral tunnel Fontan", "ltff": "fenestrated lateral tunnel Fontan",
    "ecf": "extracardiac Fontan", "ecff": "fenestrated extracardiac Fontan",
    "bdg": "bidirectional Glenn", "bbdg": "bilateral bidirectional Glenn",
    "glenn": "bidirectional Glenn", "fontan": "Fontan", "norwood": "Norwood",
    "bts": "Blalock-Taussig shunt", "rmbts": "right modified Blalock-Taussig shunt",
    "sano": "Sano shunt", "mustard": "Mustard atrial switch",
    "senning": "Senning atrial switch", "rastelli": "Rastelli repair",
    "ross": "Ross procedure", "pab": "pulmonary artery band", "lsvc": "left superior vena cava",
    "svc": "superior vena cava", "ivc": "inferior vena cava", "rv": "right ventricle",
    "lv": "left ventricle", "mpa": "main pulmonary artery", "sp": "status post",
    "s/p": "status post", "ebstein": "Ebstein anomaly", "truncus": "truncus arteriosus",
}

_SEGMENTAL = {
    "s,d,s": "situs solitus, D-loop ventricles, solitus great arteries",
    "s,d,d": "situs solitus, D-loop ventricles, D-malposed great arteries",
    "s,l,l": "situs solitus, L-loop ventricles, L-malposed great arteries",
    "s,l,r": "situs solitus, L-loop ventricles, R-malposed great arteries",
    "i,l,l": "situs inversus, L-loop ventricles, L-malposed great arteries",
    "i,d,d": "situs inversus, D-loop ventricles, D-malposed great arteries",
}

def caption_for(display_name: str) -> str:
    raw = display_name
    # segmental notation {S,D,S}
    segs = []
    for m in re.findall(r"\{([^}]*)\}", raw):
        key = m.lower().replace(" ", "")
        segs.append(_SEGMENTAL.get(key, m))
    body = re.sub(r"\{[^}]*\}", "", raw)
    # expand token-by-token
    words = re.split(r"[\s_]+", body)
    out = []
    for w in words:
        clean = w.strip().lower()
        out.append(_ABBR.get(clean, w))
    phrase = " ".join(x for x in out if x).strip(" -,")
    phrase = re.sub(r"\s+", " ", phrase)
    parts = [p for p in ([phrase] + segs) if p]
    desc = "; ".join(parts)
    return (f"{TRIGGER}, a hand-drawn Mullins-style line diagram of a congenital heart, "
            f"black ink on white background, {desc}")

# ── image normalization ─────────────────────────────────────────────────────

def normalize(img: Image.Image, size=OUT_SIZE) -> Image.Image:
    img = img.convert("L")
    img = ImageOps.autocontrast(img)
    # pad to square on white (never stretch — preserves anatomy proportions)
    w, h = img.size
    s = max(w, h)
    canvas = Image.new("L", (s, s), 255)
    canvas.paste(img, ((s - w) // 2, (s - h) // 2))
    return canvas.resize((size, size), Image.LANCZOS)

def control_map(gray_square: Image.Image) -> Image.Image:
    # clean line art as the ControlNet structure signal: crisp black/white
    bw = gray_square.point(lambda p: 0 if p < 150 else 255)
    return bw.convert("RGB")

# ── run ─────────────────────────────────────────────────────────────────────

def main():
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    (OUT / "control").mkdir(parents=True, exist_ok=True)
    lib = load_library()
    diagrams = get_all_diagrams(lib)
    meta, caps = [], []
    n = 0
    for d in diagrams:
        src = BASE / d["path"]
        if not src.exists():
            continue
        try:
            im = Image.open(src)
        except Exception:
            continue
        if d.get("image_width", 0) > 2500:   # skip the one giant scan
            continue
        cid = d["id"]
        gray = normalize(im)
        gray.convert("RGB").save(OUT / "images" / f"{cid}.png")
        control_map(gray).save(OUT / "control" / f"{cid}.png")
        cap = caption_for(d["display_name"])
        (OUT / "images" / f"{cid}.txt").write_text(cap)
        meta.append({"file_name": f"images/{cid}.png", "text": cap})
        caps.append({"id": cid, "display_name": d["display_name"], "caption": cap})
        n += 1

    with open(OUT / "metadata.jsonl", "w") as f:
        for m in meta:
            f.write(json.dumps(m) + "\n")
    with open(OUT / "captions.jsonl", "w") as f:
        for c in caps:
            f.write(json.dumps(c) + "\n")
    (OUT / "README.md").write_text(
        f"# Mullins style dataset\n\n{n} paired examples.\n\n"
        f"- `images/<id>.png` + `images/<id>.txt` — target + caption (LoRA style fine-tune)\n"
        f"- `control/<id>.png` — structure map (ControlNet phase)\n"
        f"- `metadata.jsonl` — diffusers format\n"
        f"- trigger token: `{TRIGGER}`\n\n"
        f"## Go/no-go test\nTrain a LoRA on images/ + captions, then prompt with "
        f"`{TRIGGER}, ...` to see if the Mullins style is learnable.\n"
    )
    print(f"prepared {n} examples -> {OUT}")
    print("sample caption:", caps[0]["caption"] if caps else "(none)")

if __name__ == "__main__":
    main()

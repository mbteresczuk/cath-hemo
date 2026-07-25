"""
FastAPI backend for the Cath Hemodynamics mobile app.

Exposes the existing Python utility modules (parser, hemodynamics, narrative,
annotator, diagram_library, matcher, coordinator, auto_coords) as a REST API
so the React PWA can consume them from a phone.

Start locally:
    uvicorn api.main:app --reload --port 8000
"""
import json
import os
import sys
from pathlib import Path
from typing import List, Optional

# Ensure the project root is on the path so utils.* imports resolve.
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR))

# Load .env file if present (so ANTHROPIC_API_KEY doesn't need to be exported manually)
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from utils.annotator import annotate_diagram, image_to_base64
from utils.auto_coords import auto_configure
from utils.coordinator import load_coords, save_coords
from utils.diagram_library import (
    build_library_from_source,
    get_all_diagrams,
    get_diagram_by_id,
    load_library,
    mark_coords_status,
    rename_diagram,
)
from utils.hemodynamics import calculate_all, detect_step_ups
from utils.matcher import match_diagrams
from utils.narrative import generate_hemodynamic_narrative
from utils.parser import parse_hemodynamics, parse_metadata

from api.ocr_service import extract_hemo_from_image

# ── App & CORS ────────────────────────────────────────────────────────────────

app = FastAPI(title="Cath Hemo API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # Tighten to your Vercel domain in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve diagram images at /diagrams/static/...
app.mount(
    "/diagrams/static",
    StaticFiles(directory=str(BASE_DIR / "diagrams")),
    name="diagrams",
)

# Component library (Route A: pieces extracted from existing diagrams,
# each registered to one shared template with anchors + tags).
COMPONENTS_DIR = BASE_DIR / "components"
COMPONENTS_DIR.mkdir(exist_ok=True)
app.mount(
    "/components/static",
    StaticFiles(directory=str(COMPONENTS_DIR)),
    name="components",
)


# ── Pydantic models ───────────────────────────────────────────────────────────

class ParseRequest(BaseModel):
    text: str
    extra_locations: Optional[List[str]] = None


class PatientData(BaseModel):
    hgb: Optional[float] = None   # None → Fick calculations skipped
    avo2: Optional[int] = None    # None → Fick calculations skipped
    anesthesia: str = "general anesthesia"
    anatomy_type: str = "biventricle"
    fio2: str = "21%"
    name: str = ""
    mrn: str = ""
    dob: str = ""


class ReportRequest(BaseModel):
    hemo_text: str
    diagram_id: str
    patient_data: PatientData = PatientData()
    extra_locations: Optional[List[str]] = None
    # Optional: base diagram with devices already composited (PNG base64).
    # When provided, annotations are drawn ON TOP of the devices.
    base_image_b64: Optional[str] = None
    # Optional: use these annotation coords for THIS render only (session
    # repositioning) — nothing is written to the diagram's coord file.
    coords_override: Optional[dict] = None


# ── Helper ────────────────────────────────────────────────────────────────────

def _thumbnail_url(diagram: dict) -> str:
    """Build a URL path that maps to the static file mount."""
    # diagram["path"] is e.g. "diagrams/TOF/some_diagram.bmp"
    # strip the leading "diagrams/" prefix since the mount is at /diagrams/static
    rel = diagram["path"]  # "diagrams/TOF/foo.bmp"
    without_prefix = rel[len("diagrams/"):]  # "TOF/foo.bmp"
    return f"/diagrams/static/{without_prefix}"


_library_cache: Optional[dict] = None


def _get_library() -> dict:
    global _library_cache
    if _library_cache is None:
        # Always rebuild from the actual files on disk so the library
        # stays consistent with whatever is deployed (never stale JSON).
        _library_cache = mark_coords_status(build_library_from_source())
    return _library_cache


@app.on_event("startup")
def _startup():
    """Pre-load the library at startup and log the diagram count."""
    lib = _get_library()
    all_diags = get_all_diagrams(lib)
    print(f"[startup] Library loaded: {len(all_diags)} diagrams across "
          f"{sum(1 for c in lib['categories'] if c['diagrams'])} categories")


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
def serve_mobile_app():
    """Serve the single-file mobile web app."""
    return FileResponse(
        str(BASE_DIR / "mobile_app.html"),
        media_type="text/html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.post("/api/ocr")
async def ocr_image(image: UploadFile = File(...)):
    """
    Accept a photo of a cath sheet and return extracted hemodynamic text.
    The text is in parser-compatible format (one location per line).
    """
    image_bytes = await image.read()
    media_type = image.content_type or "image/jpeg"

    try:
        text = extract_hemo_from_image(image_bytes, media_type)
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {e}")

    return {"text": text}


@app.post("/api/parse")
def parse_hemo(req: ParseRequest):
    """Parse free-text hemodynamic data into a structured dict."""
    parsed = parse_hemodynamics(req.text, extra_locations=req.extra_locations)
    return {"parsed": parsed}


@app.get("/api/diagrams")
def list_diagrams():
    """Return the full diagram library with thumbnail URLs."""
    library = _get_library()
    # Inject thumbnail_url into every diagram entry
    enriched_categories = []
    for cat in library.get("categories", []):
        diagrams = [
            {**d, "thumbnail_url": _thumbnail_url(d)}
            for d in cat["diagrams"]
        ]
        enriched_categories.append({**cat, "diagrams": diagrams})
    return {"categories": enriched_categories}


@app.get("/api/diagrams/match")
def match_diags(
    q: str = Query("", description="Diagnosis text"),
    top_n: int = Query(12, ge=1, le=50),
):
    """Return the top_n best-matching diagrams for a free-text diagnosis."""
    library = _get_library()
    if not q.strip():
        diagrams = get_all_diagrams(library)[:top_n]
    else:
        diagrams = match_diagrams(q, library, top_n=top_n)

    return {
        "results": [
            {**d, "thumbnail_url": _thumbnail_url(d)}
            for d in diagrams
        ]
    }


@app.post("/api/report")
def generate_report(req: ReportRequest):
    """
    Full pipeline: parse → calculate → narrative → annotate.

    Returns:
      - annotated_image_b64: base64-encoded PNG of the annotated diagram
      - narrative: 4-paragraph hemodynamics prose
      - calculations: Fick-derived flows, resistances, ratios
      - step_ups: detected saturation step-ups
      - parsed: structured hemodynamics dict
    """
    library = _get_library()
    diagram = get_diagram_by_id(library, req.diagram_id)
    if diagram is None:
        raise HTTPException(status_code=404, detail=f"Diagram '{req.diagram_id}' not found.")

    # --- Parse ---
    hemodynamics = parse_hemodynamics(
        req.hemo_text,
        extra_locations=req.extra_locations,
    )

    # --- Patient data dict (matches what app.py builds) ---
    # If hgb/avo2 were not supplied as patient defaults, try extracting them
    # from the hemodynamic text (user may type "HGB 12.5" or "AVO2 130").
    meta = parse_metadata(req.hemo_text)
    patient_data = {
        "name": req.patient_data.name,
        "mrn": req.patient_data.mrn,
        "dob": req.patient_data.dob,
        "hgb":  req.patient_data.hgb  if req.patient_data.hgb  is not None else meta.get("hgb"),
        "avo2": req.patient_data.avo2 if req.patient_data.avo2 is not None else meta.get("avo2"),
        "anesthesia": req.patient_data.anesthesia,
        "fio2": req.patient_data.fio2,
        "anatomy_type": req.patient_data.anatomy_type or diagram.get("anatomy_type", "biventricle"),
    }

    # --- Calculations & narrative ---
    calcs = calculate_all(hemodynamics, patient_data)
    step_ups = detect_step_ups(hemodynamics)
    narrative = generate_hemodynamic_narrative(hemodynamics, calcs, patient_data, step_ups)

    # --- Annotation coords (override > saved > auto-configure) ---
    img_path = BASE_DIR / diagram["path"]
    coords = req.coords_override or load_coords(diagram["id"])
    if coords is None:
        coords = auto_configure(
            diagram["id"],
            diagram["image_width"],
            diagram["image_height"],
            diagram["anatomy_type"],
            diagram["location_set"],
            image_path=str(img_path),
        )
        save_coords(diagram["id"], coords)
        # Bust library cache so has_coords is updated next call
        global _library_cache
        _library_cache = None

    # --- Annotate ---
    image_override = None
    if req.base_image_b64:
        import base64
        import io as _io
        try:
            from PIL import Image as _PILImage
            image_override = _PILImage.open(
                _io.BytesIO(base64.b64decode(req.base_image_b64))
            )
        except Exception:
            image_override = None

    try:
        annotated = annotate_diagram(
            str(img_path), coords, hemodynamics,
            anatomy_type=patient_data.get("anatomy_type", "biventricle"),
            image_override=image_override,
        )
        image_b64 = image_to_base64(annotated)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Annotation failed: {e}")

    # Serialize calculations (replace None with null-friendly values)
    calcs_out = {k: v for k, v in calcs.items()} if calcs else {}

    return {
        "annotated_image_b64": image_b64,
        "narrative": narrative,
        "calculations": calcs_out,
        "step_ups": step_ups,
        "parsed": hemodynamics,
    }


# ── Mullins diagram generator (text -> diagram) ───────────────────────────────

class MullinsRequest(BaseModel):
    text: str
    scale: float = 0.9
    res: int = 1024


@app.post("/api/mullins")
def generate_mullins(req: MullinsRequest):
    """
    Generate a Mullins diagram from a free-text diagnosis.

    Pipeline: select_base + place (CPU, here) -> harmonize (Modal GPU, remote).
    If MULLINS_HARMONIZE_URL is unset or the GPU call fails, the raw placed draft
    is returned (harmonized=false) so the feature still works for testing.
    """
    from utils.mullins_generate import generate

    result = generate(req.text)
    draft_b64 = image_to_base64(result["image"])

    image_b64 = draft_b64
    harmonized = False
    harmonize_url = os.environ.get("MULLINS_HARMONIZE_URL", "").strip()
    if harmonize_url:
        import json as _json
        import urllib.request
        try:
            payload = _json.dumps({
                "draft_b64": draft_b64, "scale": req.scale, "res": req.res,
            }).encode()
            rq = urllib.request.Request(
                harmonize_url, data=payload,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(rq, timeout=240) as resp:
                image_b64 = _json.loads(resp.read())["image_b64"]
                harmonized = True
        except Exception as e:  # noqa: BLE001 - degrade gracefully to the draft
            print(f"[mullins] harmonize call failed, returning draft: {e}")

    return {
        "image_b64": image_b64,
        "harmonized": harmonized,
        "base_id": result["base_id"],
        "base_name": result["base_name"],
        "findings": result["findings"],
        "added": result["added"],
        "added_donors": result["added_donors"],
        "base_id": result["base_id"],
        "anatomy_type": result["anatomy_type"],
        "location_set": result["location_set"],
    }


class GeneratedReportRequest(BaseModel):
    hemo_text: str
    image_b64: str                          # the generated diagram PNG (base64)
    base_id: str = ""                       # base diagram — its coords are reused
    added_donors: List[str] = []            # donors whose added-structure coords tag along
    anatomy_type: str = "biventricle"
    location_set: str = "standard_biventricle"
    patient_data: PatientData = PatientData()
    extra_locations: Optional[List[str]] = None


@app.post("/api/report_generated")
def generate_report_on_generated(req: GeneratedReportRequest):
    """
    Place sats/pressures on a GENERATED diagram (not a library diagram).

    Coords are auto-configured for the image itself (content detection keyed by
    location_set), so a freshly generated diagram flows into the same report
    pipeline as a picked one.
    """
    import base64
    import io as _io
    import tempfile

    from PIL import Image as _PILImage

    img = _PILImage.open(_io.BytesIO(base64.b64decode(req.image_b64))).convert("RGB")
    w, h = img.size
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        img.save(tf.name)
        tmp_path = tf.name

    hemodynamics = parse_hemodynamics(req.hemo_text, extra_locations=req.extra_locations)
    meta = parse_metadata(req.hemo_text)
    patient_data = {
        "name": req.patient_data.name, "mrn": req.patient_data.mrn, "dob": req.patient_data.dob,
        "hgb":  req.patient_data.hgb  if req.patient_data.hgb  is not None else meta.get("hgb"),
        "avo2": req.patient_data.avo2 if req.patient_data.avo2 is not None else meta.get("avo2"),
        "anesthesia": req.patient_data.anesthesia, "fio2": req.patient_data.fio2,
        "anatomy_type": req.anatomy_type,
    }
    calcs = calculate_all(hemodynamics, patient_data)
    step_ups = detect_step_ups(hemodynamics)
    narrative = generate_hemodynamic_narrative(hemodynamics, calcs, patient_data, step_ups)

    # Coordinates: reuse the BASE diagram's hand-tuned coords (the generated image
    # keeps the base's layout), then bring along coords for any added structures
    # from their donor diagrams. Only auto-configure if the base has none.
    coords = load_coords(req.base_id) if req.base_id else None
    if coords:
        base_locs = coords.setdefault("locations", {})
        for donor in req.added_donors:
            dc = load_coords(donor)
            if not dc:
                continue
            for loc, val in dc.get("locations", {}).items():
                base_locs.setdefault(loc, val)   # add donor's new sampling sites
    else:
        coords = auto_configure("generated", w, h, req.anatomy_type, req.location_set,
                                image_path=tmp_path)

    # The base coords are tuned for the base's own pixel size; the generated image
    # is a different size (e.g. 1024). Scale every x/y so markers land correctly.
    cw = coords.get("image_width") or w
    ch = coords.get("image_height") or h
    if (cw, ch) != (w, h):
        sx, sy = w / cw, h / ch
        for loc in coords.get("locations", {}).values():
            for k, val in list(loc.items()):
                if isinstance(val, (int, float)) and k.endswith("_x"):
                    loc[k] = val * sx
                elif isinstance(val, (int, float)) and k.endswith("_y"):
                    loc[k] = val * sy
        coords["image_width"], coords["image_height"] = w, h
    try:
        annotated = annotate_diagram(tmp_path, coords, hemodynamics,
                                     anatomy_type=req.anatomy_type)
        image_out = image_to_base64(annotated)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Annotation failed: {e}")
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    return {
        "annotated_image_b64": image_out,
        "narrative": narrative,
        "calculations": {k: v for k, v in calcs.items()} if calcs else {},
        "step_ups": step_ups,
        "parsed": hemodynamics,
    }


@app.get("/api/coords/{diagram_id}")
def get_coords(diagram_id: str):
    """Return annotation coords for a diagram (or empty locations if not configured)."""
    coords = load_coords(diagram_id)
    if coords is None:
        library = _get_library()
        diagram = get_diagram_by_id(library, diagram_id)
        if diagram is None:
            raise HTTPException(status_code=404, detail=f"Diagram '{diagram_id}' not found.")
        coords = {
            "diagram_id": diagram_id,
            "image_width": diagram["image_width"],
            "image_height": diagram["image_height"],
            "locations": {},
        }
    return coords


@app.put("/api/coords/{diagram_id}")
def put_coords(diagram_id: str, payload: dict = Body(...)):
    """Save annotation coords for a diagram."""
    library = _get_library()
    diagram = get_diagram_by_id(library, diagram_id)
    if diagram is None:
        raise HTTPException(status_code=404, detail=f"Diagram '{diagram_id}' not found.")
    save_coords(diagram_id, payload)
    global _library_cache
    _library_cache = None
    return {"ok": True}


@app.put("/api/diagrams/{diagram_id}/rename")
def rename_diag(diagram_id: str, payload: dict = Body(...)):
    """Rename a diagram. Body: {"name": "New Display Name"}"""
    library = _get_library()
    if get_diagram_by_id(library, diagram_id) is None:
        raise HTTPException(status_code=404, detail=f"Diagram '{diagram_id}' not found.")
    new_name = payload.get("name", "").strip()
    if not new_name:
        raise HTTPException(status_code=422, detail="name must not be empty.")
    rename_diagram(diagram_id, new_name)
    global _library_cache
    _library_cache = None
    return {"ok": True, "diagram_id": diagram_id, "name": new_name}


@app.get("/editor")
def serve_coord_editor():
    """Serve the standalone coordinate editor."""
    return FileResponse(
        str(BASE_DIR / "coord_editor.html"),
        media_type="text/html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


# ── Component authoring (Route A) ──────────────────────────────────────────

@app.get("/components")
def serve_component_editor():
    """Serve the standalone component-authoring tool."""
    return FileResponse(
        str(BASE_DIR / "component_editor.html"),
        media_type="text/html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache", "Expires": "0",
        },
    )


@app.get("/library")
def serve_component_library():
    """Serve the component library gallery viewer."""
    return FileResponse(
        str(BASE_DIR / "component_library.html"),
        media_type="text/html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate",
                 "Pragma": "no-cache", "Expires": "0"},
    )


@app.get("/api/components")
def list_components():
    """Return every saved component's metadata."""
    out = []
    for meta in sorted(COMPONENTS_DIR.glob("*.json")):
        try:
            d = json.loads(meta.read_text())
            d["image_url"] = f"/components/static/{d.get('image', meta.stem + '.png')}"
            out.append(d)
        except Exception:
            continue
    return {"components": out}


@app.post("/api/components/suggest_tags")
def suggest_component_tags(payload: dict = Body(...)):
    """LLM auto-tagging: given the source diagram with the masked region
    highlighted (PNG base64), return suggested {segment, chamber, loop, notes}."""
    from api.component_ai import suggest_tags
    b64 = payload.get("highlight_b64")
    if not b64:
        raise HTTPException(status_code=422, detail="highlight_b64 required")
    try:
        tags = suggest_tags(b64, payload.get("diagram_name", ""))
        return {"ok": True, "tags": tags}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auto-tag failed: {e}")


@app.get("/api/components/sam_status")
def sam_status():
    """Report whether one-click (SAM) masking is available on this host."""
    from api.component_ai import sam_available, _load_sam
    ok = sam_available()
    _, err = _load_sam()
    return {"available": ok, "detail": None if ok else err}


@app.post("/api/components/segment")
def segment_component(payload: dict = Body(...)):
    """One-click masking: SAM turns a click on a diagram into a mask polygon
    (returned in source-image coordinates)."""
    from api.component_ai import segment_click
    library = _get_library()
    diagram = get_diagram_by_id(library, payload.get("diagram_id", ""))
    if diagram is None:
        raise HTTPException(status_code=404, detail="Diagram not found")
    x, y = payload.get("x"), payload.get("y")
    if x is None or y is None:
        raise HTTPException(status_code=422, detail="x and y (source coords) required")
    res = segment_click(str(BASE_DIR / diagram["path"]), int(x), int(y))
    if not res.get("ok"):
        raise HTTPException(status_code=503, detail=res.get("error", "SAM unavailable"))
    return res


@app.post("/api/components")
def save_component(payload: dict = Body(...)):
    """Save one component: transparent PNG (base64) + metadata (tags, anchors).

    Everything is authored in the shared template frame, so components
    registered by different sessions still align.
    """
    import base64
    import io as _io
    import re as _re

    cid = (payload.get("id") or "").strip()
    if not cid:
        raise HTTPException(status_code=422, detail="Component id is required.")
    cid = _re.sub(r"[^A-Za-z0-9_-]", "_", cid)

    img_b64 = payload.get("image_b64")
    if not img_b64:
        raise HTTPException(status_code=422, detail="image_b64 (PNG) is required.")
    try:
        from PIL import Image as _PILImage
        img = _PILImage.open(_io.BytesIO(base64.b64decode(img_b64))).convert("RGBA")
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Bad image data: {e}")

    img.save(COMPONENTS_DIR / f"{cid}.png")
    meta = {
        "id": cid,
        "image": f"{cid}.png",
        "segment": payload.get("segment", ""),
        "tags": payload.get("tags", {}),
        "template_size": payload.get("template_size"),
        "anchors": payload.get("anchors", {}),
        "source_diagram": payload.get("source_diagram", ""),
    }
    (COMPONENTS_DIR / f"{cid}.json").write_text(json.dumps(meta, indent=2))
    return {"ok": True, "id": cid, "image_url": f"/components/static/{cid}.png"}


@app.post("/api/coords/{diagram_id}/auto")
def auto_configure_coords(diagram_id: str):
    """Auto-configure annotation coords for a diagram and return them."""
    library = _get_library()
    diagram = get_diagram_by_id(library, diagram_id)
    if diagram is None:
        raise HTTPException(status_code=404, detail=f"Diagram '{diagram_id}' not found.")
    img_path = BASE_DIR / diagram["path"]
    coords = auto_configure(
        diagram["id"],
        diagram["image_width"],
        diagram["image_height"],
        diagram["anatomy_type"],
        diagram["location_set"],
        image_path=str(img_path),
    )
    save_coords(diagram_id, coords)
    global _library_cache
    _library_cache = None
    return coords


@app.post("/api/push_coords")
def push_coords_to_git():
    """Commit and push changed coord files to GitHub so Render redeploys."""
    import subprocess
    script = BASE_DIR / "push_coords.sh"
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True, text=True, cwd=str(BASE_DIR)
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode == 0:
        return {"ok": True, "detail": output}
    from fastapi import HTTPException
    raise HTTPException(status_code=500, detail=output)


@app.get("/api/coords/export")
def export_all_coords():
    """
    Download all coord JSON files bundled into a single ZIP archive.
    Use this to export corrections made in the coord editor so they can
    be committed to GitHub and survive future redeploys.
    """
    import io
    import zipfile
    from fastapi.responses import StreamingResponse

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for coord_file in sorted(COORDS_DIR.glob("*.json")):
            zf.write(coord_file, coord_file.name)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=annotation_coords.zip"},
    )

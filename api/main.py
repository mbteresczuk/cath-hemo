"""
FastAPI backend for the Cath Hemodynamics mobile app.

Exposes the existing Python utility modules (parser, hemodynamics, narrative,
annotator, diagram_library, matcher, coordinator, auto_coords) as a REST API
so the React PWA can consume them from a phone.

Start locally:
    uvicorn api.main:app --reload --port 8000
"""
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
from utils.parser import parse_hemodynamics

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
    patient_data = {
        "name": req.patient_data.name,
        "mrn": req.patient_data.mrn,
        "dob": req.patient_data.dob,
        "hgb": req.patient_data.hgb,
        "avo2": req.patient_data.avo2,
        "anesthesia": req.patient_data.anesthesia,
        "fio2": req.patient_data.fio2,
        "anatomy_type": req.patient_data.anatomy_type or diagram.get("anatomy_type", "biventricle"),
    }

    # --- Calculations & narrative ---
    calcs = calculate_all(hemodynamics, patient_data)
    step_ups = detect_step_ups(hemodynamics)
    narrative = generate_hemodynamic_narrative(hemodynamics, calcs, patient_data, step_ups)

    # --- Annotation coords (load or auto-configure) ---
    img_path = BASE_DIR / diagram["path"]
    coords = load_coords(diagram["id"])
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
    try:
        annotated = annotate_diagram(str(img_path), coords, hemodynamics)
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

"""
Click-to-place coordinate management for annotation positions.

Supports two-step placement per location:
  - "sat"      → position of the saturation circle
  - "pressure" → position of the pressure text block

Old JSON files that only have "x"/"y" keys are fully backward-compatible:
annotator.py will use x/y for the saturation circle and auto-offset for pressure.
"""
import json
from pathlib import Path

from utils.diagram_library import (
    get_location_set,
    get_annotation_type,
    get_location_side,
)

BASE_DIR = Path(__file__).parent.parent
COORDS_DIR = BASE_DIR / "config" / "annotation_coords"


# ── helpers ──────────────────────────────────────────────────────────────────

def _needs_sat(location_name: str) -> bool:
    """True if this location requires a saturation circle position."""
    return get_annotation_type(location_name) in ("saturation", "saturation_and_pressure")


def _needs_pressure(location_name: str) -> bool:
    """True if this location requires a pressure text position."""
    return get_annotation_type(location_name) in (
        "saturation_and_pressure", "pressure_only", "pcwp"
    )


def _has_sat(loc_data: dict) -> bool:
    """Location data contains a saturation position (new or legacy format)."""
    return "sat_x" in loc_data or "x" in loc_data


def _has_pressure(loc_data: dict) -> bool:
    """Location data contains a pressure position (new or legacy format)."""
    return "pressure_x" in loc_data or "x" in loc_data


# ── I/O ──────────────────────────────────────────────────────────────────────

def load_coords(diagram_id: str):
    """Load coordinate config for diagram. Returns None if not yet configured."""
    path = COORDS_DIR / f"{diagram_id}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def save_coords(diagram_id: str, coords: dict):
    """Persist coordinate config as JSON."""
    COORDS_DIR.mkdir(parents=True, exist_ok=True)
    path = COORDS_DIR / f"{diagram_id}.json"
    with open(path, "w") as f:
        json.dump(coords, f, indent=2)


def new_coords(diagram_id: str, image_width: int, image_height: int) -> dict:
    """Create an empty coordinate config skeleton."""
    return {
        "diagram_id": diagram_id,
        "image_width": image_width,
        "image_height": image_height,
        "locations": {},
    }


# ── placement ────────────────────────────────────────────────────────────────

def add_location(coords: dict, location_name: str, x: int, y: int,
                 coord_type: str = "sat") -> dict:
    """
    Record a click coordinate for a named location.

    coord_type:
      "sat"      → saves as sat_x / sat_y  (saturation circle position)
      "pressure" → saves as pressure_x / pressure_y  (pressure text position)
    """
    if location_name not in coords["locations"]:
        coords["locations"][location_name] = {
            "side": get_location_side(location_name),
            "annotation_type": get_annotation_type(location_name),
        }
    entry = coords["locations"][location_name]

    if coord_type == "sat":
        entry["sat_x"] = int(x)
        entry["sat_y"] = int(y)
        # Remove legacy key if present so new format takes over
        entry.pop("x", None)
        entry.pop("y", None)
    else:  # "pressure"
        entry["pressure_x"] = int(x)
        entry["pressure_y"] = int(y)

    return coords


def remove_location(coords: dict, location_name: str) -> dict:
    """Remove a location entirely from the config."""
    coords["locations"].pop(location_name, None)
    return coords


def remove_location_step(coords: dict, location_name: str, coord_type: str) -> dict:
    """Remove just one step (sat or pressure) from a location."""
    entry = coords["locations"].get(location_name)
    if not entry:
        return coords
    if coord_type == "sat":
        entry.pop("sat_x", None)
        entry.pop("sat_y", None)
        entry.pop("x", None)
        entry.pop("y", None)
    else:
        entry.pop("pressure_x", None)
        entry.pop("pressure_y", None)
    # Clean up empty entry
    if not any(k in entry for k in ("sat_x", "pressure_x", "x")):
        coords["locations"].pop(location_name, None)
    return coords


# ── status queries ────────────────────────────────────────────────────────────

def is_location_complete(location_name: str, loc_data: dict) -> bool:
    """Check if a location has all required coordinate steps placed."""
    if loc_data.get("skipped"):
        return True
    sat_ok = (not _needs_sat(location_name)) or _has_sat(loc_data)
    pressure_ok = (not _needs_pressure(location_name)) or _has_pressure(loc_data)
    return sat_ok and pressure_ok


def get_placed_locations(coords: dict) -> list:
    """Return list of location names that are fully configured."""
    if not coords:
        return []
    return [
        name for name, data in coords.get("locations", {}).items()
        if is_location_complete(name, data)
    ]


def get_next_unplaced_step(location_set_name: str, coords: dict):
    """
    Return (location_name, step_type) for the next step to place.
    step_type is "sat" or "pressure".
    Returns None when everything is complete.
    """
    placed_locs = coords.get("locations", {}) if coords else {}

    for loc in get_location_set(location_set_name):
        loc_data = placed_locs.get(loc, {})
        if loc_data.get("skipped"):
            continue
        if _needs_sat(loc) and not _has_sat(loc_data):
            return (loc, "sat")
        if _needs_pressure(loc) and not _has_pressure(loc_data):
            return (loc, "pressure")
    return None


def get_next_unplaced(location_set_name: str, coords: dict):
    """Legacy helper — return just the location name of the next incomplete location."""
    step = get_next_unplaced_step(location_set_name, coords)
    return step[0] if step else None


def is_complete(location_set_name: str, coords: dict) -> bool:
    """Check if all locations in the set are fully placed."""
    if not coords:
        return False
    return get_next_unplaced_step(location_set_name, coords) is None


def get_progress(location_set_name: str, coords: dict) -> tuple:
    """Return (placed_count, total_count) counting fully-complete locations."""
    all_locs = get_location_set(location_set_name)
    placed = get_placed_locations(coords)
    count = sum(1 for loc in all_locs if loc in placed)
    return count, len(all_locs)

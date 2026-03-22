"""
Diagram library management: loads, searches, and builds the master diagram index.
"""
import json
import os
from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).parent.parent

CATEGORY_CONFIG = [
    {
        "id": "Normal",
        "display_name": "Normal Heart",
        "folder": "diagrams/Normal",
    },
    {
        "id": "ASD_VSD_CCAVC",
        "display_name": "ASD / VSD / CCAVC / AP Window",
        "folder": "diagrams/ASD_VSD_CCAVC",
    },
    {
        "id": "Coarctation_IAA",
        "display_name": "Coarctation / Interrupted Aortic Arch",
        "folder": "diagrams/Coarctation_IAA",
    },
    {
        "id": "Aortic_Stenosis",
        "display_name": "Aortic Stenosis / Aortic Valve",
        "folder": "diagrams/Aortic_Stenosis",
    },
    {
        "id": "TAPVR_PAPVR",
        "display_name": "TAPVR / PAPVR / Pulmonary Vein Stenosis",
        "folder": "diagrams/TAPVR_PAPVR",
    },
    {
        "id": "PA_IVS_TGA",
        "display_name": "PA-IVS / TGA + VSD",
        "folder": "diagrams/PA_IVS_TGA",
    },
    {
        "id": "TOF",
        "display_name": "Tetralogy of Fallot",
        "folder": "diagrams/TOF",
    },
    {
        "id": "DTGA",
        "display_name": "D-TGA Variants",
        "folder": "diagrams/DTGA",
    },
    {
        "id": "DORV",
        "display_name": "DORV (Double Outlet Right Ventricle)",
        "folder": "diagrams/DORV",
    },
    {
        "id": "Tricuspid_Atresia",
        "display_name": "Tricuspid Atresia",
        "folder": "diagrams/Tricuspid_Atresia",
    },
    {
        "id": "Ebsteins",
        "display_name": "Ebstein's Anomaly",
        "folder": "diagrams/Ebsteins",
    },
    {
        "id": "Truncus_Arteriosus",
        "display_name": "Truncus Arteriosus",
        "folder": "diagrams/Truncus_Arteriosus",
    },
    {
        "id": "HLHS_MA_AA",
        "display_name": "HLHS (Mitral Atresia / Aortic Atresia)",
        "folder": "diagrams/HLHS_MA_AA",
    },
    {
        "id": "HLHS_MS_AS",
        "display_name": "HLHS (Mitral Stenosis / Aortic Stenosis or Atresia)",
        "folder": "diagrams/HLHS_MS_AS",
    },
    {
        "id": "UCCAVC",
        "display_name": "Unbalanced CAVC / UCCAVC",
        "folder": "diagrams/UCCAVC",
    },
    {
        "id": "DILV_Single_Ventricle",
        "display_name": "DILV / Single Ventricle (Other)",
        "folder": "diagrams/DILV_Single_Ventricle",
    },
]

LOCATION_SETS = {
    "standard_biventricle": [
        "SVC", "IVC", "RA", "RV", "MPA", "RPA", "LPA",
        "RPCWP", "LPCWP", "LA", "LV", "Descending_Aorta",
        "RUPV", "LUPV", "RLPV", "LLPV",
    ],
    "single_ventricle_norwood": [
        "SVC", "IVC", "RA", "RV_systemic", "Neoaorta",
        "MPA", "RPA", "LPA", "RPCWP", "LPCWP", "Descending_Aorta",
        "RUPV", "LUPV", "RLPV", "LLPV",
    ],
    "post_glenn": [
        "SVC", "IVC", "RA", "Glenn_anastomosis",
        "RPA", "LPA", "RPCWP", "LPCWP", "LA", "LV_systemic", "Descending_Aorta",
        "RUPV", "LUPV", "RLPV", "LLPV",
    ],
    "post_fontan": [
        "Fontan_IVC_limb", "SVC", "RA", "RPA", "LPA",
        "RPCWP", "LPCWP", "LA", "LV_systemic", "Descending_Aorta",
        "RUPV", "LUPV", "RLPV", "LLPV",
    ],
    "post_mustard_senning": [
        "SVC", "IVC", "Venous_atrium", "RV_systemic",
        "Descending_Aorta", "MPA", "Arterial_atrium", "LV_pulmonary",
        "RUPV", "LUPV", "RLPV", "LLPV",
    ],
}

# Location annotation types
LOCATION_ANNOTATION_TYPES = {
    "SVC": "saturation",
    "IVC": "saturation",
    "RA": "saturation_and_pressure",
    "RV": "saturation_and_pressure",
    "RV_systemic": "saturation_and_pressure",
    "MPA": "saturation_and_pressure",
    "RPA": "saturation_and_pressure",
    "LPA": "saturation_and_pressure",
    "RPCWP": "pcwp",
    "LPCWP": "pcwp",
    "LA": "saturation_and_pressure",
    "LV": "saturation_and_pressure",
    "LV_systemic": "saturation_and_pressure",
    "LV_pulmonary": "saturation_and_pressure",
    "Descending_Aorta": "saturation_and_pressure",
    "Neoaorta": "saturation_and_pressure",
    "Glenn_anastomosis": "saturation_and_pressure",
    "Fontan_IVC_limb": "saturation_and_pressure",
    "Venous_atrium": "saturation_and_pressure",
    "Arterial_atrium": "saturation_and_pressure",
    # Extra locations available for per-diagram customization
    "Ascending_Aorta": "saturation_and_pressure",
    "BTS": "saturation",
    "Sano_conduit": "saturation_and_pressure",
    "Fontan_conduit": "saturation_and_pressure",
    "LSVC": "saturation",
    "Coronary_sinus": "saturation",
    "Innominate_vein": "saturation",
    "Hepatic_vein": "saturation",
    "Azygos_vein": "saturation",
    "RVOT": "saturation_and_pressure",
    "LVOT": "saturation_and_pressure",
    "Conduit": "saturation_and_pressure",
    "PV_confluence": "saturation_and_pressure",
    "Baffle": "saturation_and_pressure",
    "RV_body": "saturation_and_pressure",
    "RV_apex": "saturation_and_pressure",
    "RPV": "saturation_and_pressure",
    "LPV": "saturation_and_pressure",
    "RUPV": "saturation_and_pressure",
    "LUPV": "saturation_and_pressure",
    "RLPV": "saturation_and_pressure",
    "LLPV": "saturation_and_pressure",
}

# Location sides (right = blue circles/purple pressure, left = red circles/green pressure)
LOCATION_SIDES = {
    "SVC": "right",
    "IVC": "right",
    "RA": "right",
    "RV": "right",
    "RV_systemic": "left",  # Systemic RV is left-sided in terms of pressure
    "MPA": "right",
    "RPA": "right",
    "LPA": "right",
    "RPCWP": "left",
    "LPCWP": "left",
    "LA": "left",
    "LV": "left",
    "LV_systemic": "left",
    "LV_pulmonary": "right",
    "Descending_Aorta": "left",
    "Neoaorta": "left",
    "Glenn_anastomosis": "right",
    "Fontan_IVC_limb": "right",
    "Venous_atrium": "right",
    "Arterial_atrium": "left",
    # Extra locations
    "Ascending_Aorta": "left",
    "BTS": "right",
    "Sano_conduit": "right",
    "Fontan_conduit": "right",
    "LSVC": "right",
    "Coronary_sinus": "right",
    "Innominate_vein": "right",
    "Hepatic_vein": "right",
    "Azygos_vein": "right",
    "RVOT": "right",
    "LVOT": "left",
    "Conduit": "right",
    "PV_confluence": "left",
    "Baffle": "right",
    "RV_body": "right",
    "RV_apex": "right",
    "RPV": "left",
    "LPV": "left",
    "RUPV": "left",
    "LUPV": "left",
    "RLPV": "left",
    "LLPV": "left",
}


# Extra locations that can be added to any diagram on a per-diagram basis.
# These are NOT in any standard location set but can be selected in Setup Coordinates.
EXTRA_LOCATIONS = [
    "Ascending_Aorta", "BTS", "Sano_conduit",
    "Fontan_conduit", "LSVC", "Coronary_sinus", "Innominate_vein",
    "Hepatic_vein", "Azygos_vein", "RVOT", "LVOT", "Conduit",
    "PV_confluence", "Baffle", "RV_body", "RV_apex", "RPV", "LPV",
]


def _detect_anatomy_type(filename: str) -> tuple[str, str]:
    """Detect anatomy_type and location_set from filename."""
    name_upper = filename.upper()

    # Fontan variants (check before Glenn since HemiFontan contains neither word but is fontan-like)
    if any(k in name_upper for k in ["FONTAN", "ECFF", "LTFF", "HEMIFONT"]):
        return "post_fontan", "post_fontan"

    # Glenn
    if any(k in name_upper for k in ["GLENN", "BDG"]):
        return "post_glenn", "post_glenn"

    # Mustard/Senning atrial switch
    if any(k in name_upper for k in ["MUSTARD", "SENNING"]):
        return "post_mustard", "post_mustard_senning"

    # Single ventricle pre-Fontan (Norwood, BTS, shunt stages)
    if any(k in name_upper for k in [
        "NORWOOD", "_BTS", "SANO", "RMBTS", "PA_IVS",
        "PULM ATRESIA", "PULMATRESIA",
    ]):
        return "single_ventricle", "single_ventricle_norwood"

    return "biventricle", "standard_biventricle"


def _make_display_name(filename: str) -> str:
    """Create a human-readable display name from a filename."""
    name = Path(filename).stem
    # Some cleanup substitutions
    substitutions = [
        ("_sp_", " s/p "),
        ("_sp ", " s/p "),
        (" sp ", " s/p "),
        (" status post ", " s/p "),
        ("status post", "s/p"),
        ("_", " "),
        ("  ", " "),
    ]
    for old, new in substitutions:
        name = name.replace(old, new)
    return name.strip()


def _safe_id(filename: str) -> str:
    """Create a filesystem-safe ID from filename."""
    stem = Path(filename).stem
    # Replace characters that are problematic in filenames/JSON keys
    safe = ""
    for c in stem:
        if c.isalnum() or c in "-_":
            safe += c
        else:
            safe += "_"
    return safe


_NAME_OVERRIDES_PATH = BASE_DIR / "config" / "diagram_name_overrides.json"


def _load_name_overrides() -> dict:
    """Load the persistent diagram name overrides (id -> custom name)."""
    if _NAME_OVERRIDES_PATH.exists():
        with open(_NAME_OVERRIDES_PATH) as f:
            return json.load(f)
    return {}


def _save_name_overrides(overrides: dict) -> None:
    """Persist diagram name overrides to disk."""
    os.makedirs(str(_NAME_OVERRIDES_PATH.parent), exist_ok=True)
    with open(_NAME_OVERRIDES_PATH, "w") as f:
        json.dump(overrides, f, indent=2)


def build_library_from_source(output_path: str = None) -> dict:
    """
    Scan all category folders and build the diagram library JSON.
    Writes to config/diagram_library.json and returns the library dict.
    """
    if output_path is None:
        output_path = str(BASE_DIR / "config" / "diagram_library.json")

    name_overrides = _load_name_overrides()

    categories = []
    for cat in CATEGORY_CONFIG:
        folder_path = BASE_DIR / cat["folder"]
        if not folder_path.exists():
            continue

        diagrams = []
        for img_file in sorted(folder_path.iterdir()):
            if img_file.suffix.lower() not in (".bmp", ".png", ".jpg", ".jpeg"):
                continue

            anatomy_type, location_set = _detect_anatomy_type(img_file.name)
            diagram_id = _safe_id(img_file.name)
            coord_file = str(BASE_DIR / "config" / "annotation_coords" / f"{diagram_id}.json")
            has_coords = os.path.exists(coord_file)

            # Get image dimensions
            try:
                with Image.open(img_file) as img:
                    width, height = img.size
            except Exception:
                width, height = 0, 0

            # Use custom name override if present, otherwise derive from filename
            display_name = name_overrides.get(diagram_id, _make_display_name(img_file.name))

            diagrams.append({
                "id": diagram_id,
                "filename": img_file.name,
                "display_name": display_name,
                "path": str(img_file.relative_to(BASE_DIR)),
                "category_id": cat["id"],
                "anatomy_type": anatomy_type,
                "location_set": location_set,
                "has_coords": has_coords,
                "coord_file": str(Path("config/annotation_coords") / f"{diagram_id}.json"),
                "image_width": width,
                "image_height": height,
            })

        categories.append({
            "id": cat["id"],
            "display_name": cat["display_name"],
            "folder": cat["folder"],
            "diagrams": diagrams,
        })

    library = {"categories": categories}

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(library, f, indent=2)

    return library


def delete_diagram(diagram: dict) -> dict:
    """
    Permanently delete a diagram and its annotation coords, then rebuild
    and return the updated library dict.

    Removes:
      - The image file on disk
      - Its annotation coords JSON (config/annotation_coords/<id>.json)

    Returns the rebuilt library (the diagram is no longer present).
    """
    # Delete image file
    img_path = BASE_DIR / diagram["path"]
    if img_path.exists():
        img_path.unlink()

    # Delete coords file
    coords_path = BASE_DIR / "config" / "annotation_coords" / f"{diagram['id']}.json"
    if coords_path.exists():
        coords_path.unlink()

    # Rebuild library so the entry is removed
    return build_library_from_source()


def load_library(library_path: str = None) -> dict:
    """Load the diagram library JSON. Builds it if missing."""
    if library_path is None:
        library_path = str(BASE_DIR / "config" / "diagram_library.json")

    if not os.path.exists(library_path):
        return build_library_from_source(library_path)

    with open(library_path) as f:
        return json.load(f)


def get_all_categories(library: dict) -> list:
    return library.get("categories", [])


def get_diagrams_for_category(library: dict, category_id: str) -> list:
    for cat in library.get("categories", []):
        if cat["id"] == category_id:
            return cat["diagrams"]
    return []


def get_all_diagrams(library: dict) -> list:
    diagrams = []
    for cat in library.get("categories", []):
        diagrams.extend(cat["diagrams"])
    return diagrams


def get_diagram_by_id(library: dict, diagram_id: str):
    for diagram in get_all_diagrams(library):
        if diagram["id"] == diagram_id:
            return diagram
    return None


def search_diagrams(library: dict, query: str) -> list:
    """Full-text search across display_name, anatomy_type, category."""
    if not query:
        return get_all_diagrams(library)
    q = query.lower()
    results = []
    for diagram in get_all_diagrams(library):
        searchable = " ".join([
            diagram.get("display_name", ""),
            diagram.get("anatomy_type", ""),
            diagram.get("category_id", ""),
            diagram.get("filename", ""),
        ]).lower()
        if q in searchable:
            results.append(diagram)
    return results


def get_location_set(location_set_name: str) -> list:
    return LOCATION_SETS.get(location_set_name, LOCATION_SETS["standard_biventricle"])


def get_annotation_type(location_name: str) -> str:
    return LOCATION_ANNOTATION_TYPES.get(location_name, "saturation_and_pressure")


def get_location_side(location_name: str) -> str:
    return LOCATION_SIDES.get(location_name, "right")


def mark_coords_status(library: dict) -> dict:
    """Refresh has_coords status for all diagrams."""
    for cat in library.get("categories", []):
        for diagram in cat["diagrams"]:
            coord_path = BASE_DIR / diagram["coord_file"]
            diagram["has_coords"] = coord_path.exists()
    return library


# ── Anatomy type label → (anatomy_type, location_set) ───────────────────────
_ANATOMY_LABEL_MAP = {
    "Auto-detect from filename": None,
    "Standard Biventricle": ("biventricle", "standard_biventricle"),
    "Single Ventricle / Norwood": ("single_ventricle", "single_ventricle_norwood"),
    "Post-Glenn": ("post_glenn", "post_glenn"),
    "Post-Fontan": ("post_fontan", "post_fontan"),
    "Post-Mustard / Senning": ("post_mustard", "post_mustard_senning"),
}

ANATOMY_UPLOAD_OPTIONS = list(_ANATOMY_LABEL_MAP.keys())


def add_uploaded_diagram(
    file_bytes: bytes,
    filename: str,
    anatomy_override: str = "Auto-detect from filename",
) -> dict:
    """
    Save an uploaded image to diagrams/Uploaded/, rebuild the library, and
    return the updated library dict.  If the filename already exists, a
    numeric suffix is appended (_1, _2, …).

    anatomy_override must be one of ANATOMY_UPLOAD_OPTIONS.
    Returns the updated library dict (already mark_coords_status'd).
    """
    upload_dir = BASE_DIR / "diagrams" / "Uploaded"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Resolve any filename collision
    dest = upload_dir / filename
    if dest.exists():
        stem = Path(filename).stem
        ext  = Path(filename).suffix
        i = 1
        while dest.exists():
            dest = upload_dir / f"{stem}_{i}{ext}"
            i += 1

    dest.write_bytes(file_bytes)

    # Rebuild library from source files
    library = build_library_from_source()

    # Apply anatomy override if requested
    if anatomy_override and anatomy_override != "Auto-detect from filename":
        pair = _ANATOMY_LABEL_MAP.get(anatomy_override)
        if pair:
            anatomy_type, location_set = pair
            diag_id = _safe_id(dest.name)
            for cat in library.get("categories", []):
                for d in cat["diagrams"]:
                    if d["id"] == diag_id:
                        d["anatomy_type"]  = anatomy_type
                        d["location_set"]  = location_set

            # Persist the override
            lib_path = str(BASE_DIR / "config" / "diagram_library.json")
            with open(lib_path, "w") as f:
                json.dump(library, f, indent=2)

    return mark_coords_status(library)


def rename_diagram(diagram_id: str, new_name: str) -> None:
    """
    Persist a custom display name for any diagram.
    The name survives library rebuilds via config/diagram_name_overrides.json.
    Pass new_name="" to remove the override and revert to the filename-derived name.
    """
    overrides = _load_name_overrides()
    new_name = new_name.strip()
    if new_name:
        overrides[diagram_id] = new_name
    else:
        overrides.pop(diagram_id, None)
    _save_name_overrides(overrides)


def delete_uploaded_diagram(diagram_id: str, library: dict) -> dict:
    """
    Delete an uploaded diagram image file and rebuild/return the library.
    Only diagrams in the 'Uploaded' category can be deleted this way.
    """
    for cat in library.get("categories", []):
        if cat["id"] != "Uploaded":
            continue
        for d in cat["diagrams"]:
            if d["id"] == diagram_id:
                img_path = BASE_DIR / d["path"]
                if img_path.exists():
                    img_path.unlink()
                break

    return mark_coords_status(build_library_from_source())

"""
Automatic coordinate configuration for annotation positions.

Uses image-content analysis (dark-pixel centroid detection) to place
annotations at the actual anatomical structure positions in each diagram.
Falls back to calibrated fractional templates when detection yields
insufficient data.
"""
from utils.diagram_library import get_location_set, get_annotation_type, get_location_side


# ── Search regions for centroid detection ────────────────────────────────────
#
# For each anatomical location, defines the image region (as fractions of
# full image width/height) where that structure should appear, based on
# standard cardiac anatomy conventions:
#   - Right heart (RA, RV) → LEFT side of image
#   - Left heart (LA, LV)  → RIGHT side of image
#   - Great vessels         → TOP of image
#   - SVC/IVC               → upper/lower LEFT
#   - Aorta                 → lower CENTER/RIGHT
#
# Format: (x0_frac, y0_frac, x1_frac, y1_frac)

SEARCH_REGIONS = {
    "standard_biventricle": {
        # Tighter regions to minimize cross-structure contamination.
        # Right heart = left side of image; left heart = right side.
        "SVC":   (0.00, 0.00, 0.22, 0.22),  # narrow upper-left tube
        "IVC":   (0.00, 0.62, 0.24, 1.00),  # narrow lower-left tube
        "RA":    (0.04, 0.30, 0.38, 0.62),  # left-center chamber
        "RV":    (0.06, 0.50, 0.42, 0.88),  # left-lower chamber (avoid MPA)
        "MPA":   (0.18, 0.05, 0.55, 0.38),  # upper-center trunk (limited y)
        "RPA":   (0.02, 0.00, 0.40, 0.24),  # very upper-left branch
        "LPA":   (0.30, 0.00, 0.76, 0.24),  # very upper-right branch
        "LA":    (0.40, 0.22, 0.85, 0.62),  # right-center chamber
        "LV":    (0.42, 0.50, 0.85, 0.88),  # right-lower chamber
        "Descending_Aorta": (0.35, 0.65, 0.78, 1.00),  # lower-right area
    },
    "single_ventricle_norwood": {
        "SVC":         (0.02, 0.00, 0.26, 0.28),
        "IVC":         (0.00, 0.62, 0.22, 0.98),
        "RA":          (0.06, 0.28, 0.38, 0.62),
        "RV_systemic": (0.32, 0.42, 0.70, 0.88),
        "Neoaorta":    (0.28, 0.00, 0.70, 0.32),
        "MPA":         (0.18, 0.08, 0.55, 0.42),
        "RPA":         (0.02, 0.00, 0.38, 0.24),
        "LPA":         (0.30, 0.00, 0.74, 0.24),
        "Descending_Aorta":       (0.25, 0.68, 0.76, 1.00),
    },
    "post_glenn": {
        "SVC":               (0.02, 0.00, 0.34, 0.28),
        "IVC":               (0.00, 0.62, 0.22, 0.98),
        "RA":                (0.04, 0.30, 0.36, 0.62),
        "Glenn_anastomosis": (0.08, 0.02, 0.38, 0.26),
        "RPA":               (0.02, 0.00, 0.40, 0.22),
        "LPA":               (0.28, 0.00, 0.74, 0.22),
        "LA":                (0.40, 0.16, 0.84, 0.56),
        "LV_systemic":       (0.32, 0.50, 0.84, 0.88),
        "Descending_Aorta":             (0.22, 0.68, 0.76, 1.00),
    },
    "post_fontan": {
        "Fontan_IVC_limb": (0.00, 0.50, 0.24, 0.84),
        "SVC":             (0.02, 0.00, 0.24, 0.28),
        "RA":              (0.04, 0.30, 0.34, 0.62),
        "RPA":             (0.02, 0.00, 0.40, 0.22),
        "LPA":             (0.28, 0.00, 0.74, 0.22),
        "LA":              (0.40, 0.16, 0.84, 0.56),
        "LV_systemic":     (0.32, 0.50, 0.84, 0.88),
        "Descending_Aorta":           (0.22, 0.68, 0.76, 1.00),
    },
    "post_mustard_senning": {
        "SVC":             (0.00, 0.00, 0.26, 0.28),
        "IVC":             (0.00, 0.62, 0.24, 0.98),
        "Venous_atrium":   (0.04, 0.30, 0.46, 0.68),
        "RV_systemic":     (0.50, 0.42, 0.94, 0.88),
        "Descending_Aorta":           (0.24, 0.68, 0.78, 0.98),
        "MPA":             (0.18, 0.06, 0.56, 0.44),
        "Arterial_atrium": (0.46, 0.20, 0.88, 0.60),
        "LV_pulmonary":    (0.18, 0.46, 0.64, 0.88),
    },
}


# ── Fallback position templates (bbox-relative fractions) ────────────────────
#
# Used when centroid detection finds too few dark pixels in the search region.

POSITION_TABLES = {
    "standard_biventricle": {
        "SVC":               (0.087, 0.206),
        "IVC":               (0.083, 0.848),
        "RA":                (0.200, 0.468),
        "RV":                (0.376, 0.673),
        "MPA":               (0.431, 0.343),
        "RPA":               (0.252, 0.099),
        "LPA":               (0.628, 0.105),
        "LA":                (0.697, 0.415),
        "LV":               (0.773, 0.702),
        "Descending_Aorta": (0.510, 0.910),
        "RUPV":              (0.830, 0.300),
        "LUPV":              (0.910, 0.295),
        "RLPV":              (0.830, 0.490),
        "LLPV":              (0.910, 0.485),
    },
    "single_ventricle_norwood": {
        "SVC":              (0.096, 0.166),
        "IVC":              (0.070, 0.840),
        "RA":               (0.148, 0.431),
        "RV_systemic":      (0.513, 0.646),
        "Neoaorta":         (0.526, 0.074),
        "MPA":              (0.409, 0.278),
        "RPA":              (0.200, 0.063),
        "LPA":              (0.630, 0.074),
        "Descending_Aorta": (0.474, 0.922),
        "RUPV":             (0.820, 0.300),
        "LUPV":             (0.900, 0.295),
        "RLPV":             (0.820, 0.480),
        "LLPV":             (0.900, 0.475),
    },
    "post_glenn": {
        "SVC":               (0.145, 0.110),
        "IVC":               (0.040, 0.847),
        "RA":                (0.133, 0.458),
        "Glenn_anastomosis": (0.220, 0.131),
        "RPA":               (0.195, 0.080),
        "LPA":               (0.496, 0.080),
        "LA":                (0.596, 0.315),
        "LV_systemic":       (0.459, 0.642),
        "Descending_Aorta":  (0.446, 0.908),
        "RUPV":              (0.760, 0.200),
        "LUPV":              (0.840, 0.195),
        "RLPV":              (0.760, 0.375),
        "LLPV":              (0.840, 0.370),
    },
    "post_fontan": {
        "Fontan_IVC_limb":  (0.052, 0.683),
        "SVC":              (0.079, 0.110),
        "RA":               (0.107, 0.458),
        "RPA":              (0.203, 0.080),
        "LPA":              (0.518, 0.080),
        "LA":               (0.627, 0.315),
        "LV_systemic":      (0.477, 0.652),
        "Descending_Aorta": (0.449, 0.918),
        "RUPV":             (0.790, 0.205),
        "LUPV":             (0.870, 0.200),
        "RLPV":             (0.790, 0.380),
        "LLPV":             (0.870, 0.375),
    },
    "post_mustard_senning": {
        "SVC":              (0.067, 0.153),
        "IVC":              (0.067, 0.834),
        "Venous_atrium":    (0.174, 0.529),
        "RV_systemic":      (0.724, 0.651),
        "Descending_Aorta": (0.469, 0.886),
        "MPA":              (0.362, 0.336),
        "Arterial_atrium":  (0.670, 0.387),
        "LV_pulmonary":     (0.335, 0.651),
        "RUPV":             (0.830, 0.265),
        "LUPV":             (0.910, 0.260),
        "RLPV":             (0.830, 0.455),
        "LLPV":             (0.910, 0.450),
    },
}

POSITION_OVERRIDES = {
    "CCAVC": {
        "SVC":   (0.097, 0.081), "IVC":   (0.043, 0.835),
        "RA":    (0.137, 0.380), "RV":    (0.352, 0.608),
        "MPA":   (0.365, 0.298), "RPA":   (0.231, 0.081),
        "LPA":   (0.567, 0.081), "LA":    (0.473, 0.318),
        "LV":    (0.567, 0.691), "Descending_Aorta": (0.459, 0.918),
    },
    "CAVC": {
        "SVC":   (0.097, 0.081), "IVC":   (0.043, 0.835),
        "RA":    (0.137, 0.380), "RV":    (0.352, 0.608),
        "MPA":   (0.365, 0.298), "RPA":   (0.231, 0.081),
        "LPA":   (0.567, 0.081), "LA":    (0.473, 0.318),
        "LV":    (0.567, 0.691), "Descending_Aorta": (0.459, 0.918),
    },
    "DORV": {
        "SVC":   (0.079, 0.188), "IVC":   (0.079, 0.837),
        "RA":    (0.187, 0.427), "RV":    (0.336, 0.617),
        "MPA":   (0.404, 0.307), "RPA":   (0.228, 0.078),
        "LPA":   (0.594, 0.088), "LA":    (0.715, 0.367),
        "LV":    (0.783, 0.697), "Descending_Aorta": (0.499, 0.897),
    },
    "PA_IVS": {
        "SVC":         (0.118, 0.192), "IVC":         (0.092, 0.869),
        "RA":          (0.208, 0.455), "RV_systemic": (0.349, 0.616),
        "Neoaorta":    (0.374, 0.130), "MPA":         (0.374, 0.333),
        "RPA":         (0.233, 0.101), "LPA":         (0.541, 0.101),
        "Descending_Aorta":       (0.510, 0.910),
    },
    "InterruptedAorticArch": {
        "SVC":   (0.087, 0.200), "IVC":   (0.083, 0.848),
        "RA":    (0.200, 0.468), "RV":    (0.376, 0.673),
        "MPA":   (0.431, 0.343), "RPA":   (0.252, 0.099),
        "LPA":   (0.628, 0.105), "LA":    (0.697, 0.415),
        "LV":    (0.773, 0.702), "Descending_Aorta": (0.510, 0.910),
    },
}

# Pressure offset: (dx, dy) relative to the saturation circle center
_PRESSURE_OFFSET = {
    "right": (-10, -40),
    "left":  (-5,  -40),
}


def _compute_pressure_offset(sat_x, sat_y, image_width, image_height, side):
    """Adaptive pressure text offset based on sat circle position in the image.

    Structures in the upper 30% of the image get pressure text placed BELOW
    the circle to prevent clipping at the top edge (e.g. RPA, LPA, MPA).
    All others get pressure text placed ABOVE (standard behaviour).
    """
    dx = _PRESSURE_OFFSET.get(side, (-8, -40))[0]
    if sat_y < image_height * 0.30:
        dy = +32   # place below circle — avoids top-edge clipping
    else:
        dy = -40   # place above circle — normal case
    return dx, dy


# ── Anatomy position detection ─────────────────────────────────────────────────

def find_interior_point(image_path, x0_frac, y0_frac, x1_frac, y1_frac,
                        dark_threshold=200, white_threshold=220,
                        min_dark=50, min_white=20):
    """Find the center of the hollow white interior of an anatomy structure.

    1. Locates the bounding box of dark pixels (outline) in the search region.
    2. Within that bounding box, computes the centroid of white (interior) pixels.
    3. Falls back to bounding box midpoint if too few white pixels found.

    This places annotations inside the open hollow space of each chamber rather
    than on the dark outline border.

    Returns:
        (cx, cy) in image pixel coordinates, or None if structure not found.
    """
    from utils.annotator import safe_open_image
    try:
        img = safe_open_image(image_path).convert("L")
        w, h = img.size
        x0 = max(0, int(x0_frac * w))
        y0 = max(0, int(y0_frac * h))
        x1 = min(w, int(x1_frac * w))
        y1 = min(h, int(y1_frac * h))
        if x1 <= x0 or y1 <= y0:
            return None

        region = img.crop((x0, y0, x1, y1))
        rw, rh = region.width, region.height
        pixels = list(region.getdata())

        # Step 1: bounding box of dark (outline) pixels
        min_dx, max_dx = rw, 0
        min_dy, max_dy = rh, 0
        dark_count = 0
        for i, p in enumerate(pixels):
            if p < dark_threshold:
                rx, ry = i % rw, i // rw
                if rx < min_dx: min_dx = rx
                if rx > max_dx: max_dx = rx
                if ry < min_dy: min_dy = ry
                if ry > max_dy: max_dy = ry
                dark_count += 1

        if dark_count < min_dark:
            return None

        # Step 2: centroid of white pixels inside the dark bounding box
        # Small inset to avoid the outline edge itself
        pad = max(1, min(max_dx - min_dx, max_dy - min_dy) // 10)
        ibx0, iby0 = min_dx + pad, min_dy + pad
        ibx1, iby1 = max_dx - pad, max_dy - pad

        sum_x = sum_y = white_count = 0
        if ibx1 > ibx0 and iby1 > iby0:
            for iy in range(iby0, iby1 + 1):
                for ix in range(ibx0, ibx1 + 1):
                    idx = iy * rw + ix
                    if idx < len(pixels) and pixels[idx] >= white_threshold:
                        sum_x += ix
                        sum_y += iy
                        white_count += 1

        if white_count >= min_white:
            return x0 + sum_x // white_count, y0 + sum_y // white_count

        # Fallback: midpoint of the dark-pixel bounding box
        return x0 + (min_dx + max_dx) // 2, y0 + (min_dy + max_dy) // 2
    except Exception:
        return None


def find_dark_centroid(image_path, x0_frac, y0_frac, x1_frac, y1_frac,
                       threshold=200, min_pixels=50):
    """Find the centroid of dark pixels within a search region (secondary fallback).

    Returns:
        (cx, cy) in image pixel coordinates, or None if insufficient data.
    """
    from utils.annotator import safe_open_image
    try:
        img = safe_open_image(image_path).convert("L")
        w, h = img.size
        x0 = max(0, int(x0_frac * w))
        y0 = max(0, int(y0_frac * h))
        x1 = min(w, int(x1_frac * w))
        y1 = min(h, int(y1_frac * h))

        if x1 <= x0 or y1 <= y0:
            return None

        region = img.crop((x0, y0, x1, y1))
        rw = region.width
        pixels = list(region.getdata())

        sum_x = sum_y = count = 0
        for i, p in enumerate(pixels):
            if p < threshold:
                sum_x += i % rw
                sum_y += i // rw
                count += 1

        if count >= min_pixels:
            return x0 + sum_x // count, y0 + sum_y // count
        return None
    except Exception:
        return None


def detect_anatomy_bounds(image_path):
    """Detect the bounding box of the anatomy drawing (non-white pixels).

    Returns (left, top, right, bottom) or full image dimensions on failure.
    """
    from utils.annotator import safe_open_image
    try:
        img = safe_open_image(image_path).convert("L")
        binary = img.point(lambda p: 255 if p < 240 else 0)
        bbox = binary.getbbox()
        if bbox is not None:
            return bbox
        return (0, 0, img.width, img.height)
    except Exception:
        return None


def _get_fallback_positions(diagram_id, location_set_name):
    """Return the fallback template dict for a diagram (bbox-relative fractions)."""
    base = POSITION_TABLES.get(location_set_name) or POSITION_TABLES["standard_biventricle"]
    for prefix, overrides in POSITION_OVERRIDES.items():
        if diagram_id.startswith(prefix):
            merged = dict(base)
            merged.update(overrides)
            return merged
    return base


def _resolve_margin_position(margin_type, bbox, image_width, image_height, sat_entry):
    """Compute pixel position for margin-placed annotations (PCWP, PA pressures)."""
    bbox_left, bbox_top, bbox_right, bbox_bottom = bbox
    bbox_h = bbox_bottom - bbox_top

    if margin_type == "left_edge":
        x = max(5, bbox_left - 40)
        y = int(bbox_top + 0.30 * bbox_h)
        return x, y

    elif margin_type == "right_edge":
        x = min(image_width - 50, bbox_right + 10)
        y = int(bbox_top + 0.30 * bbox_h)
        return x, y

    elif margin_type == "left_margin":
        sat_x = sat_entry.get("sat_x", bbox_left + 50)
        sat_y = sat_entry.get("sat_y", bbox_top + 50)
        x = max(5, sat_x - 70)
        y = sat_y - 5
        return x, y

    elif margin_type == "right_margin":
        sat_x = sat_entry.get("sat_x", bbox_right - 50)
        sat_y = sat_entry.get("sat_y", bbox_top + 50)
        x = min(image_width - 50, sat_x + 25)
        y = sat_y - 5
        return x, y

    return None, None


def auto_configure(diagram_id: str, image_width: int, image_height: int,
                   anatomy_type: str, location_set_name: str,
                   image_path: str = None) -> dict:
    """Generate annotation coordinates using image-content centroid detection.

    For each anatomical location:
      1. Searches a known anatomical region of the image for dark pixels.
      2. Places the annotation at the centroid of those pixels.
      3. Falls back to calibrated fractional templates if detection fails.
    """
    # Bounding box (used for margin-based placements and fallback templates)
    bbox = None
    if image_path:
        bbox = detect_anatomy_bounds(image_path)
    if bbox:
        bbox_left, bbox_top, bbox_right, bbox_bottom = bbox
    else:
        bbox_left, bbox_top, bbox_right, bbox_bottom = 0, 0, image_width, image_height
    bbox_tuple = (bbox_left, bbox_top, bbox_right, bbox_bottom)
    bbox_w = bbox_right - bbox_left
    bbox_h = bbox_bottom - bbox_top

    search_regions = SEARCH_REGIONS.get(location_set_name, {})
    fallback_positions = _get_fallback_positions(diagram_id, location_set_name)
    locations = get_location_set(location_set_name)

    result = {
        "diagram_id": diagram_id,
        "image_width": image_width,
        "image_height": image_height,
        "auto_configured": True,
        "locations": {},
    }

    for loc in locations:
        ann_type = get_annotation_type(loc)
        side = get_location_side(loc)

        entry = {"side": side, "annotation_type": ann_type}
        sat_placed = False

        # ── Saturation position ──────────────────────────────────────────────
        if ann_type in ("saturation", "saturation_and_pressure"):
            # 1st: interior white-space detection (places circle inside chamber)
            centroid = None
            if image_path and loc in search_regions:
                sr = search_regions[loc]
                centroid = find_interior_point(image_path, *sr)
                if centroid is None:
                    centroid = find_dark_centroid(image_path, *sr)

            if centroid:
                entry["sat_x"], entry["sat_y"] = centroid
                sat_placed = True
            else:
                # Fall back to bbox-relative template
                pos = fallback_positions.get(loc)
                if pos is not None:
                    x_frac, y_frac = pos
                    entry["sat_x"] = int(bbox_left + x_frac * bbox_w)
                    entry["sat_y"] = int(bbox_top + y_frac * bbox_h)
                    sat_placed = True

        # ── Pressure position ────────────────────────────────────────────────
        if ann_type == "saturation_and_pressure" and sat_placed:
            dx, dy = _compute_pressure_offset(
                entry["sat_x"], entry["sat_y"], image_width, image_height, side
            )
            entry["pressure_x"] = entry["sat_x"] + dx
            entry["pressure_y"] = entry["sat_y"] + dy

        elif ann_type == "pressure_only":
            pos = fallback_positions.get(loc)
            if pos is not None:
                x_frac, y_frac = pos
                entry["pressure_x"] = int(bbox_left + x_frac * bbox_w)
                entry["pressure_y"] = int(bbox_top + y_frac * bbox_h)

        elif ann_type == "pcwp":
            margin_type = "left_edge" if loc == "RPCWP" else "right_edge"
            px, py = _resolve_margin_position(
                margin_type, bbox_tuple, image_width, image_height, entry
            )
            if px is not None:
                entry["pressure_x"] = px
                entry["pressure_y"] = py

        # ── PA branch pressures: margin-based ────────────────────────────────
        if loc == "RPA" and "pressure_x" not in entry and "sat_x" in entry:
            px, py = _resolve_margin_position(
                "left_margin", bbox_tuple, image_width, image_height, entry
            )
            if px is not None:
                entry["pressure_x"] = px
                entry["pressure_y"] = py

        elif loc == "LPA" and "pressure_x" not in entry and "sat_x" in entry:
            px, py = _resolve_margin_position(
                "right_margin", bbox_tuple, image_width, image_height, entry
            )
            if px is not None:
                entry["pressure_x"] = px
                entry["pressure_y"] = py

        # ── Clamp to image bounds ─────────────────────────────────────────────
        _CIRC_R = 16
        if "sat_x" in entry:
            entry["sat_x"] = max(_CIRC_R, min(image_width - _CIRC_R, entry["sat_x"]))
            entry["sat_y"] = max(_CIRC_R, min(image_height - _CIRC_R, entry["sat_y"]))
        if "pressure_x" in entry:
            entry["pressure_x"] = max(2, min(image_width - 60, entry["pressure_x"]))
            entry["pressure_y"] = max(2, min(image_height - 40, entry["pressure_y"]))

        result["locations"][loc] = entry

    return result

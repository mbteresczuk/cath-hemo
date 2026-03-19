"""
PIL-based annotation rendering for cardiac cath diagrams.
Draws saturation circles, pressure labels, and PCWP annotations.
"""
import io
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

# macOS TCC may block os.getcwd() for sandboxed Python processes.
# Many stdlib functions (os.path.abspath, pathlib) call os.getcwd() internally.
# Fix: chdir to a known-accessible directory if getcwd() is broken.
try:
    os.getcwd()
except (PermissionError, OSError):
    os.chdir("/tmp")


def pil_to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    """Convert a PIL Image to bytes for st.image() without temp file writes."""
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def safe_open_image(path) -> Image.Image:
    """Open an image by reading all bytes into memory first.

    macOS TCC may block PIL's lazy file reads. Reading bytes with
    Python's built-in open() bypasses this restriction.
    """
    with open(path, "rb") as f:
        data = f.read()
    return Image.open(io.BytesIO(data))

BASE_DIR = Path(__file__).parent.parent

# All annotations in black — no color coding
COLORS = {
    "right_circle":    "#000000",
    "right_pressure":  "#000000",
    "left_circle":     "#000000",
    "left_pressure":   "#000000",
    "pcwp":            "#000000",
    "dot_marker":      "#FF6600",   # Orange only for setup-mode placement dots
}

CIRCLE_RADIUS = 16
CIRCLE_OUTLINE_WIDTH = 2

# Ventricular chambers display sys/mean (e.g. 34/10) instead of the
# standard sys/dia block with mean below.
_VENTRICULAR_LOCS = {
    "RV", "LV", "RV_systemic", "LV_systemic", "LV_pulmonary",
}

# These locations show only the mean pressure value on the diagram.
# Systolic and diastolic values are suppressed for display purposes.
_MEAN_ONLY_LOCS = {
    "RPCWP", "LPCWP",
    "RPV", "LPV", "RUPV", "LUPV", "RLPV", "LLPV", "PV_confluence",
}


def _load_fonts():
    """Load Calibri regular 16pt; fall back to Arial then PIL default."""
    _here = Path(__file__).parent.parent / "assets" / "fonts"

    calibri_regular = [
        str(_here / "Calibri.ttf"),
        "/Applications/Microsoft Word.app/Contents/Resources/DFonts/Calibri.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]

    font = None
    for path in calibri_regular:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, 16)
                break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()

    # All keys point to the same regular font — no bold anywhere
    return {"bold_large": font, "regular": font, "bold_small": font}


_FONTS = None


def get_fonts():
    global _FONTS
    if _FONTS is None:
        _FONTS = _load_fonts()
    return _FONTS


def load_image_as_rgba(image_path: str) -> Image.Image:
    """Load image and convert to RGBA for drawing."""
    img = safe_open_image(image_path)
    if img.mode not in ("RGBA",):
        img = img.convert("RGBA")
    return img


def _text_size(draw, text, font):
    """Get (width, height) of rendered text."""
    try:
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except AttributeError:
        return draw.textsize(text, font=font)


def _text_top_offset(font, text):
    """Return the vertical offset from draw-y to the visual top of glyphs.

    Pillow's draw.text(xy) places text so the ascender starts at xy[1].
    font.getbbox returns (left, top, right, bottom) where top is often
    a negative number (e.g. -14 for a 16pt font), meaning the visual top
    of the glyph is at y + top_offset pixels above the draw point.
    We use this to compensate so text renders exactly at the intended y.
    """
    try:
        return font.getbbox(text)[1]
    except Exception:
        return 0


def _draw_text(draw, x, y, text, font, fill):
    """Draw text with its visual top-left corner exactly at (x, y)."""
    offset = _text_top_offset(font, text)
    draw.text((x, y - offset), text, fill=fill, font=font)


def draw_saturation_circle(draw, cx, cy, saturation, side, fonts, radius=CIRCLE_RADIUS):
    """
    Draw a circle with saturation value inside, centered on (cx, cy).
    """
    color = COLORS["right_circle"] if side == "right" else COLORS["left_circle"]
    font = fonts["regular"]

    # White fill so diagram lines don't show through
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill="white",
        outline=color,
        width=CIRCLE_OUTLINE_WIDTH,
    )

    if saturation is not None:
        text = str(int(saturation))
        tw, th = _text_size(draw, text, font)
        # Center text in circle, compensating for glyph top offset
        offset = _text_top_offset(font, text)
        draw.text((cx - tw // 2, cy - th // 2 - offset), text, fill=color, font=font)


def draw_pressure_annotation(draw, x, y, systolic, diastolic, mean, side, fonts,
                             anchor="left", ventricular=False):
    """
    Draw pressure annotation with its top-left corner exactly at (x, y).

    Standard format (atria, great vessels):
        systolic/diastolic
        ──────────────────
        mean

    Ventricular format (RV, LV, etc.) — sys/mean on one line:
        systolic/mean

    anchor: 'left' (x is left edge) or 'right' (x is right edge)
    White background ensures readability over anatomy lines.
    """
    color = COLORS["right_pressure"] if side == "right" else COLORS["left_pressure"]
    font = fonts["regular"]

    if systolic is None and diastolic is None:
        return

    if ventricular:
        if systolic is not None and mean is not None:
            line1 = f"{int(systolic)}/{int(mean)}"
        elif systolic is not None:
            line1 = str(int(systolic))
        else:
            line1 = str(int(mean))
        tw, th = _text_size(draw, line1, font)
        text_x = x - tw if anchor == "right" else x
        pad = 2
        draw.rectangle([text_x - pad, y - pad, text_x + tw + pad, y + th + pad], fill="white")
        _draw_text(draw, text_x, y, line1, font, color)
        return

    # Standard format: sys/dia on top, mean below overline
    if systolic is not None and diastolic is not None:
        line1 = f"{int(systolic)}/{int(diastolic)}"
    elif systolic is not None:
        line1 = str(int(systolic))
    else:
        line1 = str(int(diastolic))

    tw, th = _text_size(draw, line1, font)
    text_x = x - tw if anchor == "right" else x

    # Pre-calculate total block height for white background
    total_h = th
    max_w = tw
    mean_text = None
    mw = 0
    if mean is not None:
        mean_text = str(int(mean))
        mw, mh = _text_size(draw, mean_text, font)
        total_h += 3 + 1 + 3 + mh   # gap + overline + gap + mean text
        max_w = max(max_w, mw)

    pad = 2
    draw.rectangle(
        [text_x - pad, y - pad, text_x + max_w + pad, y + total_h + pad],
        fill="white"
    )

    _draw_text(draw, text_x, y, line1, font, color)

    if mean_text is not None:
        line_y = y + th + 3
        mean_x = (x - mw) if anchor == "right" else text_x
        draw.line([(mean_x, line_y), (mean_x + mw, line_y)], fill=color, width=1)
        _draw_text(draw, mean_x, line_y + 3, mean_text, font, color)


def draw_pcwp_annotation(draw, x, y, label, systolic, diastolic, mean, fonts):
    """
    Draw PCWP label + pressure with top-left corner exactly at (x, y):
        RPCW
        17/12
        ─────
        14
    White background ensures readability over anatomy lines.
    """
    color = COLORS["pcwp"]
    font = fonts["regular"]

    lw, lh = _text_size(draw, label, font)
    total_h = lh + 2
    max_w = lw

    if systolic is not None and diastolic is not None:
        pressure_str = f"{int(systolic)}/{int(diastolic)}"
        pw, ph = _text_size(draw, pressure_str, font)
        total_h += ph + 2
        max_w = max(max_w, pw)
        if mean is not None:
            mean_text = str(int(mean))
            mw, mh = _text_size(draw, mean_text, font)
            total_h += 3 + 1 + 3 + mh
            max_w = max(max_w, mw)
    elif mean is not None:
        mean_text = str(int(mean))
        mw, mh = _text_size(draw, mean_text, font)
        total_h += mh
        max_w = max(max_w, mw)
        pressure_str = None
    else:
        return

    pad = 2
    draw.rectangle([x - pad, y - pad, x + max_w + pad, y + total_h + pad], fill="white")

    _draw_text(draw, x, y, label, font, color)
    y_cur = y + lh + 2

    if systolic is not None and diastolic is not None:
        pressure_str = f"{int(systolic)}/{int(diastolic)}"
        pw, ph = _text_size(draw, pressure_str, font)
        _draw_text(draw, x, y_cur, pressure_str, font, color)
        y_cur += ph + 2
        if mean is not None:
            mean_text = str(int(mean))
            mw_mean, _ = _text_size(draw, mean_text, font)
            draw.line([(x, y_cur), (x + mw_mean, y_cur)], fill=color, width=1)
            y_cur += 3
            _draw_text(draw, x, y_cur, mean_text, font, color)
    elif mean is not None:
        _draw_text(draw, x, y_cur, str(int(mean)), font, color)


def draw_placement_dots(img: Image.Image, placed_coords: dict) -> Image.Image:
    """
    Overlay colored dots for placed annotation points.
    Used during coordinate setup mode.

    Orange dot  = saturation circle position
    Blue dot    = pressure text position
    (Legacy x/y entries show a single orange dot.)
    """
    img = img.copy()
    draw = ImageDraw.Draw(img)
    fonts = get_fonts()
    font = fonts["regular"]
    r = 5
    SAT_COLOR = "#FF6600"      # orange
    PRESSURE_COLOR = "#0066FF"  # blue

    for loc_name, coord in placed_coords.items():
        # Saturation circle dot
        sat_x = coord.get("sat_x", coord.get("x"))
        sat_y = coord.get("sat_y", coord.get("y"))
        if sat_x is not None and sat_x >= 0:
            draw.ellipse([sat_x - r, sat_y - r, sat_x + r, sat_y + r],
                         fill=SAT_COLOR, outline="black", width=1)
            draw.text((sat_x + r + 2, sat_y - r), loc_name, fill=SAT_COLOR, font=font)

        # Pressure text dot (only if using new format with separate positions)
        press_x = coord.get("pressure_x")
        press_y = coord.get("pressure_y")
        if press_x is not None and press_x >= 0:
            label = f"{loc_name}P"
            draw.ellipse([press_x - r, press_y - r, press_x + r, press_y + r],
                         fill=PRESSURE_COLOR, outline="black", width=1)
            draw.text((press_x + r + 2, press_y - r), label, fill=PRESSURE_COLOR, font=font)

    return img


def _resolve_coords(coord: dict) -> tuple:
    """
    Resolve (sat_cx, sat_cy, pressure_cx, pressure_cy) from a location coord entry.

    Supports two formats:
      New: sat_x/sat_y + pressure_x/pressure_y (separate, configurable positions)
      Old: x/y only (saturation position; pressure auto-offset to the right)
    """
    if "sat_x" in coord or "pressure_x" in coord:
        # New format — fully independent positions
        sat_cx = coord.get("sat_x")
        sat_cy = coord.get("sat_y")
        press_cx = coord.get("pressure_x")
        press_cy = coord.get("pressure_y")
    else:
        # Legacy format — single x/y; pressure auto-offset right of circle
        sat_cx = coord.get("x")
        sat_cy = coord.get("y")
        press_cx = (sat_cx + CIRCLE_RADIUS + 3) if sat_cx is not None else None
        press_cy = (sat_cy - 8) if sat_cy is not None else None

    return sat_cx, sat_cy, press_cx, press_cy


def annotate_diagram(image_path: str, coords: dict, hemodynamics: dict) -> Image.Image:
    """
    Main annotation entry point.

    Coord entries support two formats:
      New: separate sat_x/sat_y for the saturation circle and
           pressure_x/pressure_y for the pressure text block.
      Old: single x/y (pressure auto-offset to the right of the circle).
    """
    img = load_image_as_rgba(image_path)
    draw = ImageDraw.Draw(img)
    fonts = get_fonts()

    if not coords or "locations" not in coords:
        return img

    for loc_name, coord in coords["locations"].items():
        hemo = hemodynamics.get(loc_name, {})
        if not hemo:
            continue

        side = coord.get("side", "right")
        ann_type = coord.get("annotation_type", "saturation_and_pressure")

        sat = hemo.get("sat")
        systolic = hemo.get("systolic")
        diastolic = hemo.get("diastolic")
        mean = hemo.get("mean")

        # PV and wedge locations: display mean pressure only on diagram
        if loc_name in _MEAN_ONLY_LOCS:
            systolic = None
            diastolic = None

        sat_cx, sat_cy, press_cx, press_cy = _resolve_coords(coord)

        if ann_type == "saturation":
            if sat_cx is not None:
                draw_saturation_circle(draw, sat_cx, sat_cy, sat, side, fonts)

        elif ann_type == "saturation_and_pressure":
            is_ventricular = loc_name in _VENTRICULAR_LOCS
            if sat_cx is not None and sat is not None:
                draw_saturation_circle(draw, sat_cx, sat_cy, sat, side, fonts)
            if press_cx is not None and any(v is not None for v in [systolic, diastolic, mean]):
                draw_pressure_annotation(draw, press_cx, press_cy,
                                         systolic, diastolic, mean, side, fonts,
                                         ventricular=is_ventricular)

        elif ann_type == "pressure_only":
            is_ventricular = loc_name in _VENTRICULAR_LOCS
            if press_cx is not None and any(v is not None for v in [systolic, diastolic, mean]):
                draw_pressure_annotation(draw, press_cx, press_cy,
                                         systolic, diastolic, mean, side, fonts,
                                         ventricular=is_ventricular)

        elif ann_type == "pcwp":
            if press_cx is not None:
                # Use shorter display labels (RPCW/LPCW instead of RPCWP/LPCWP)
                display_label = loc_name.replace("PCWP", "PCW")
                draw_pcwp_annotation(draw, press_cx, press_cy,
                                     display_label, systolic, diastolic, mean, fonts)

    return img


def image_to_bytes(img: Image.Image, fmt: str = "PNG") -> bytes:
    """Convert PIL image to bytes for download or display."""
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


def image_to_base64(img: Image.Image) -> str:
    """Convert PIL image to base64-encoded PNG string."""
    import base64
    return base64.b64encode(image_to_bytes(img)).decode()


SIDEBAR_WIDTH = 200


def add_patient_sidebar(img: Image.Image, patient_data: dict) -> Image.Image:
    """Append a patient info + hemodynamics summary panel to the right of the diagram.

    patient_data keys used:
      name, mrn, dob, doc          — patient demographics
      avo2, abd, qp_manual,
      qs_manual, pvri_manual        — hemodynamic summary (user-entered)
    """
    sw = SIDEBAR_WIDTH
    canvas = Image.new("RGBA", (img.width + sw, img.height), "white")
    canvas.paste(img, (0, 0))
    draw = ImageDraw.Draw(canvas)
    fonts = get_fonts()
    bold = fonts["bold_small"]
    reg = fonts["regular"]

    bx = img.width  # x where sidebar begins
    # Vertical border separating diagram from sidebar
    draw.line([(bx, 0), (bx, img.height)], fill="black", width=2)

    sx = bx + 8          # text left edge
    rx = bx + sw - 8     # right edge for divider lines
    y = 10
    LH = 14              # line height

    def divider():
        nonlocal y
        draw.line([(sx, y), (rx, y)], fill="black", width=1)
        y += 5

    def section_hdr(text):
        nonlocal y
        draw.text((sx, y), text, fill="black", font=bold)
        y += LH
        divider()

    def field(label, value):
        nonlocal y
        draw.text((sx, y), label, fill="black", font=bold)
        y += LH - 2
        val = str(value) if value not in (None, "", "—") else "—"
        # Truncate text that would overflow the sidebar
        while len(val) > 1 and _text_size(draw, val, reg)[0] > sw - 16:
            val = val[:-1]
        draw.text((sx + 4, y), val, fill="black", font=reg)
        y += LH + 3

    # ── Patient section ──────────────────────────────────────────────────────
    section_hdr("PATIENT")
    field("Name:", patient_data.get("name", ""))
    field("MRN:", patient_data.get("mrn", ""))
    field("DOB:", patient_data.get("dob", ""))
    field("Cath Date:", patient_data.get("doc", ""))

    y += 4
    # ── Hemodynamics section ─────────────────────────────────────────────────
    section_hdr("HEMODYNAMICS")

    avo2 = patient_data.get("avo2", "")
    avo2_str = f"{avo2} mL/min/m\u00b2" if avo2 else "—"
    field("aVO\u2082:", avo2_str)
    field("ABD:", patient_data.get("abd", ""))
    field("Qp:", patient_data.get("qp_manual", ""))
    field("Qs:", patient_data.get("qs_manual", ""))
    field("PVRi:", patient_data.get("pvri_manual", ""))

    return canvas

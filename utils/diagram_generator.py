"""
Programmatic cardiac anatomy diagram generator.

Draws schematic cardiac schematics using matplotlib, returning both the PIL
image and a pixel-perfect coords dict suitable for annotate_diagram().

Because positions are recorded during drawing (not inferred from image
analysis), hemodynamic annotations land exactly on each structure.
"""
import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from PIL import Image

from utils.diagram_library import get_annotation_type, get_location_side

# ── Design tokens ────────────────────────────────────────────────────────────
_EC  = "#1B2B3A"   # edge / outline colour
_FC  = "#FFFFFF"   # chamber fill
_BG  = "#F8F6F3"   # page background
_LW  = 2.5         # chamber linewidth
_VLW = 2.0         # vessel linewidth
_DPI = 96
_W   = 480
_H   = 580


# ── Public API ───────────────────────────────────────────────────────────────

def generate_diagram(location_set_name: str, anatomy_type: str,
                     width: int = _W, height: int = _H):
    """Draw a cardiac schematic and return ``(PIL.Image, coords_dict)``.

    The returned ``coords_dict`` has pixel-perfect annotation positions —
    no image analysis needed.

    Parameters
    ----------
    location_set_name : str
        One of the keys in ``LOCATION_SETS`` (e.g. ``"standard_biventricle"``).
    anatomy_type : str
        Anatomy type string from the diagram library (e.g. ``"biventricle"``).
    width, height : int
        Canvas size in pixels (default 480 × 580).
    """
    _draw_fn = {
        "standard_biventricle":   _draw_standard_biventricle,
        "single_ventricle_norwood": _draw_single_ventricle_norwood,
        "post_glenn":             _draw_post_glenn,
        "post_fontan":            _draw_post_fontan,
        "post_mustard_senning":   _draw_post_mustard_senning,
    }.get(location_set_name, _draw_standard_biventricle)

    # Build figure at exact pixel resolution
    fig, ax = plt.subplots(
        figsize=(width / _DPI, height / _DPI),
        dpi=_DPI,
    )
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
    ax.set_position([0, 0, 1, 1])
    ax.set_xlim(0, width)
    ax.set_ylim(0, height)
    ax.invert_yaxis()
    ax.axis("off")
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)

    # Draw anatomy, get sat-annotation positions
    positions = _draw_fn(ax, width, height)

    # Render to PIL image
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=_DPI, facecolor=_BG,
                bbox_inches=None)
    plt.close(fig)
    buf.seek(0)
    pil_img = Image.open(buf).convert("RGB")

    # Build coords dict from recorded positions
    coords = _build_coords_from_positions(
        positions, pil_img.width, pil_img.height,
        location_set_name,
    )
    return pil_img, coords


# ── Coords builder ───────────────────────────────────────────────────────────

def _build_coords_from_positions(positions: dict, width: int, height: int,
                                 location_set_name: str) -> dict:
    """Convert ``{location: (sat_x, sat_y)}`` to the annotator coords dict."""
    locations = {}
    threshold_y = height * 0.30   # adaptive pressure offset boundary

    for loc, pos in positions.items():
        ann_type = get_annotation_type(loc)
        side     = get_location_side(loc)

        if ann_type == "pcwp":
            # PCWP entries: margin-placed only — no sat circle
            locations[loc] = {
                "side": side,
                "annotation_type": "pcwp",
                "pressure_x": pos[0],
                "pressure_y": pos[1],
            }
            continue

        sat_x, sat_y = pos
        dx = -10 if side == "right" else -5

        if ann_type == "saturation":
            locations[loc] = {
                "side": side,
                "annotation_type": "saturation",
                "sat_x": sat_x,
                "sat_y": sat_y,
            }
        else:
            # saturation_and_pressure
            dy = +32 if sat_y < threshold_y else -40
            locations[loc] = {
                "side": side,
                "annotation_type": "saturation_and_pressure",
                "sat_x": sat_x,
                "sat_y": sat_y,
                "pressure_x": sat_x + dx,
                "pressure_y": sat_y + dy,
            }

    return {
        "diagram_id": f"generated_{location_set_name}",
        "image_width": width,
        "image_height": height,
        "auto_configured": False,
        "locations": locations,
    }


# ── Drawing primitives ────────────────────────────────────────────────────────

def _chamber(ax, x0, y0, w, h, label="", lw=_LW):
    """Rounded rectangle chamber with optional label."""
    ax.add_patch(mpatches.FancyBboxPatch(
        (x0, y0), w, h,
        boxstyle="round,pad=5",
        ec=_EC, fc=_FC, lw=lw, zorder=2,
    ))
    if label:
        ax.text(x0 + w / 2, y0 + h * 0.35, label,
                ha="center", va="center", fontsize=8,
                fontfamily="DejaVu Serif", color=_EC,
                fontweight="bold", zorder=3)


def _tube_v(ax, x0, y0, w, h, label="", lw=_VLW):
    """Vertical vessel tube."""
    ax.add_patch(mpatches.FancyBboxPatch(
        (x0, y0), w, h,
        boxstyle="round,pad=3",
        ec=_EC, fc=_FC, lw=lw, zorder=2,
    ))
    if label:
        ax.text(x0 + w / 2, y0 + h / 2, label,
                ha="center", va="center", fontsize=6,
                fontfamily="DejaVu Serif", color=_EC, zorder=3)


def _tube_h(ax, x0, y0, w, h, label="", lw=_VLW):
    """Horizontal vessel tube."""
    ax.add_patch(mpatches.FancyBboxPatch(
        (x0, y0), w, h,
        boxstyle="round,pad=3",
        ec=_EC, fc=_FC, lw=lw, zorder=2,
    ))
    if label:
        ax.text(x0 + w / 2, y0 + h / 2, label,
                ha="center", va="center", fontsize=6,
                fontfamily="DejaVu Serif", color=_EC, zorder=3)


def _line(ax, x1, y1, x2, y2, lw=1.8):
    ax.plot([x1, x2], [y1, y2], "-", color=_EC, lw=lw, zorder=1)


def _aorta_arch(ax, apex_x, apex_y, span=70, arm_h=55, tube_w=26, lw=_VLW):
    """Draw an aortic arch: ascending arm | horizontal arch | descending arm.

    apex_y is the TOP of the arch; the base of each arm is apex_y + arm_h.
    Returns (asc_cx, desc_cx, base_y) — centres of ascending / descending arms.
    """
    # Ascending arm (left arm of arch, patient's right)
    asc_x0 = apex_x - span // 2 - tube_w // 2
    ax.add_patch(mpatches.FancyBboxPatch(
        (asc_x0, apex_y), tube_w, arm_h,
        boxstyle="round,pad=3", ec=_EC, fc=_FC, lw=lw, zorder=2,
    ))
    # Descending arm (right arm of arch, patient's left)
    desc_x0 = apex_x + span // 2 - tube_w // 2
    ax.add_patch(mpatches.FancyBboxPatch(
        (desc_x0, apex_y), tube_w, arm_h,
        boxstyle="round,pad=3", ec=_EC, fc=_FC, lw=lw, zorder=2,
    ))
    # Horizontal connector at top of arch
    bridge_x0 = asc_x0 + tube_w // 2
    bridge_x1 = desc_x0 + tube_w // 2
    ax.plot([bridge_x0, bridge_x1], [apex_y, apex_y],
            "-", color=_EC, lw=lw * 0.8, zorder=2)
    return (
        asc_x0 + tube_w // 2,
        desc_x0 + tube_w // 2,
        apex_y + arm_h,
    )


# ── Anatomy drawing functions ─────────────────────────────────────────────────

def _draw_standard_biventricle(ax, W=480, H=580):
    """Standard two-ventricle anatomy (ASD, VSD, TOF, etc.)."""

    # ── Right heart (left side of image) ──────────────────────────────
    # SVC — narrow vertical tube, upper-left
    _tube_v(ax, 52, 15, 27, 65, "SVC")
    _line(ax, 65, 80, 65, 220)          # SVC → RA connector

    # RA — medium chamber
    _chamber(ax, 38, 220, 128, 138, "RA")
    _line(ax, 102, 358, 120, 360)       # RA → RV connector

    # RV — large chamber
    _chamber(ax, 48, 360, 150, 120, "RV")

    # IVC — narrow vertical tube, lower-left
    _tube_v(ax, 52, 478, 27, 78, "IVC")
    _line(ax, 65, 478, 65, 358)         # RA → IVC connector

    # ── Pulmonary circuit (top-centre) ────────────────────────────────
    # MPA — vertical trunk rising from RV outflow
    _tube_v(ax, 205, 115, 28, 82, "MPA")
    _line(ax, 148, 360, 219, 197)       # RV outflow → MPA

    # RPA — horizontal left branch
    _tube_h(ax, 65, 80, 138, 24, "RPA")
    _line(ax, 205, 104, 135, 92)        # MPA top → RPA

    # LPA — horizontal right branch
    _tube_h(ax, 235, 80, 205, 24, "LPA")
    _line(ax, 233, 104, 280, 92)        # MPA top → LPA

    # ── Left heart (right side of image) ─────────────────────────────
    # LA — medium chamber
    _chamber(ax, 298, 195, 122, 108, "LA")
    _line(ax, 358, 303, 358, 358)       # LA → LV connector

    # LV — large chamber
    _chamber(ax, 302, 358, 130, 122, "LV")

    # Aorta — vertical tube below LV, represents aortic root/ascending aorta
    _tube_v(ax, 282, 482, 55, 68, "Ao")
    _line(ax, 332, 480, 309, 482)       # LV → Aorta connector

    # ── Annotation positions (sat circles go here) ────────────────────
    return {
        "SVC":   (65,  48),
        "IVC":   (65,  517),
        "RA":    (100, 285),
        "RV":    (123, 420),
        "MPA":   (219, 155),
        "RPA":   (134, 92),
        "LPA":   (337, 92),
        "LA":    (359, 248),
        "LV":    (367, 418),
        "Descending_Aorta": (309, 512),
        # PCWP — margin-placed (pressure_x, pressure_y)
        "RPCWP": (5,   240),
        "LPCWP": (415, 240),
    }


def _draw_single_ventricle_norwood(ax, W=480, H=580):
    """Single ventricle — Norwood/Blalock-Taussig stage."""

    # ── Systemic venous return (left side) ────────────────────────────
    _tube_v(ax, 52, 15, 27, 62, "SVC")
    _line(ax, 65, 77, 65, 218)

    _chamber(ax, 38, 218, 128, 130, "RA")
    _line(ax, 65, 478, 65, 348)

    _tube_v(ax, 52, 478, 27, 72, "IVC")

    # ── Single ventricle (RV_systemic) — large central chamber ────────
    _chamber(ax, 210, 325, 145, 135, "RV\nsystemic")
    # RA → RV_systemic connection
    _line(ax, 102, 348, 210, 390)

    # ── Neoaorta — arch above the single ventricle ────────────────────
    # Draw as aortic arch centred at x≈260
    _aorta_arch(ax, apex_x=258, apex_y=88, span=72, arm_h=58, tube_w=28)
    # Connect descending arm of arch to RV_systemic
    _line(ax, 282, 146, 282, 325)
    # Label the arch
    ax.text(258, 70, "Neoaorta", ha="center", va="center",
            fontsize=7, fontfamily="DejaVu Serif", color=_EC, zorder=3)

    # ── Pulmonary arteries (top) ───────────────────────────────────────
    # MPA — small tube (may be banded or reconstructed)
    _tube_v(ax, 175, 175, 26, 58, "MPA")
    # BTS/Sano-like shunt: connecting line from neoaorta region to MPA/PA
    _line(ax, 230, 115, 201, 175)

    # RPA
    _tube_h(ax, 65, 78, 125, 24, "RPA")
    _line(ax, 175, 100, 155, 90)

    # LPA
    _tube_h(ax, 200, 78, 215, 24, "LPA")
    _line(ax, 201, 175, 252, 90)

    # ── Descending aorta below single ventricle ────────────────────────
    _tube_v(ax, 285, 462, 45, 72, "Ao")
    _line(ax, 307, 460, 307, 462)

    return {
        "SVC":         (65,  48),
        "IVC":         (65,  506),
        "RA":          (100, 278),
        "RV_systemic": (282, 390),
        "Neoaorta":    (258, 130),
        "MPA":         (188, 210),
        "RPA":         (128, 90),
        "LPA":         (307, 90),
        "Descending_Aorta":       (307, 495),
        "RPCWP":       (5,   235),
        "LPCWP":       (415, 235),
    }


def _draw_post_glenn(ax, W=480, H=580):
    """Post-bidirectional Glenn (SVC directly connected to PA)."""

    # ── SVC — wider horizontal tube connecting to PA ───────────────────
    # SVC approaches from upper-left and anastomoses with PA
    _tube_v(ax, 148, 15, 30, 65, "SVC")
    _line(ax, 163, 80, 200, 92)         # SVC → Glenn anastomosis

    # Glenn anastomosis / PA confluence
    _tube_h(ax, 65, 80, 375, 24)
    ax.text(200, 80, "Glenn / PA", ha="center", va="bottom",
            fontsize=7, fontfamily="DejaVu Serif", color=_EC, zorder=3)

    # RPA (left branch)
    ax.text(92, 105, "RPA", ha="center", va="top",
            fontsize=6, fontfamily="DejaVu Serif", color=_EC, zorder=3)

    # LPA (right branch)
    ax.text(350, 105, "LPA", ha="center", va="top",
            fontsize=6, fontfamily="DejaVu Serif", color=_EC, zorder=3)

    # ── Right heart / RA (now just a passive venous chamber) ──────────
    _chamber(ax, 38, 215, 128, 135, "RA")
    # RA connects to SVC above
    _line(ax, 65, 215, 65, 118)
    _tube_v(ax, 52, 115, 27, 63, "")     # short SVC-to-RA stump
    # IVC enters RA from below
    _line(ax, 65, 350, 65, 478)
    _tube_v(ax, 52, 478, 27, 72, "IVC")

    # ── Left heart ────────────────────────────────────────────────────
    _chamber(ax, 298, 200, 122, 108, "LA")
    _line(ax, 358, 308, 358, 358)

    _chamber(ax, 302, 358, 132, 122, "LV\nsystemic")

    _tube_v(ax, 282, 482, 55, 68, "Ao")
    _line(ax, 335, 480, 309, 482)

    return {
        "SVC":               (163, 55),
        "IVC":               (65,  510),
        "RA":                (100, 278),
        "Glenn_anastomosis": (200, 92),
        "RPA":               (92,  92),
        "LPA":               (350, 92),
        "LA":                (359, 248),
        "LV_systemic":       (368, 418),
        "Descending_Aorta":             (309, 512),
        "RPCWP":             (5,   235),
        "LPCWP":             (415, 235),
    }


def _draw_post_fontan(ax, W=480, H=580):
    """Post-Fontan — IVC connected to PA via extracardiac conduit."""

    # ── PA confluence (horizontal bar at top) ─────────────────────────
    _tube_h(ax, 65, 80, 375, 24)
    ax.text(252, 70, "Fontan / PA", ha="center", va="bottom",
            fontsize=7, fontfamily="DejaVu Serif", color=_EC, zorder=3)
    ax.text(110, 106, "RPA", ha="center", va="top",
            fontsize=6, fontfamily="DejaVu Serif", color=_EC, zorder=3)
    ax.text(350, 106, "LPA", ha="center", va="top",
            fontsize=6, fontfamily="DejaVu Serif", color=_EC, zorder=3)

    # ── SVC — enters PA from above (Glenn component) ──────────────────
    _tube_v(ax, 148, 15, 30, 65, "SVC")
    _line(ax, 163, 80, 163, 92)

    # ── Fontan IVC limb — conduit from IVC to PA ──────────────────────
    _tube_v(ax, 58, 415, 30, 72, "IVC\nlimb")
    _line(ax, 73, 415, 73, 104)         # conduit runs up to PA

    # ── RA — excluded / decompressed chamber ──────────────────────────
    _chamber(ax, 35, 215, 118, 130, "RA")
    # RA is largely excluded; draw it with a dashed border to indicate bypassed
    ax.add_patch(mpatches.FancyBboxPatch(
        (36, 216), 116, 128,
        boxstyle="round,pad=5",
        ec=_EC, fc=_FC, lw=1.0, linestyle="--", zorder=2,
    ))

    # ── Left heart ────────────────────────────────────────────────────
    _chamber(ax, 298, 200, 122, 108, "LA")
    _line(ax, 358, 308, 358, 358)

    _chamber(ax, 302, 358, 132, 122, "LV\nsystemic")

    _tube_v(ax, 282, 482, 55, 68, "Ao")
    _line(ax, 335, 480, 309, 482)

    return {
        "Fontan_IVC_limb": (73,  450),
        "SVC":             (163, 50),
        "RA":              (93,  278),
        "RPA":             (110, 92),
        "LPA":             (350, 92),
        "LA":              (359, 248),
        "LV_systemic":     (368, 418),
        "Descending_Aorta":           (309, 512),
        "RPCWP":           (5,   235),
        "LPCWP":           (415, 235),
    }


def _draw_post_mustard_senning(ax, W=480, H=580):
    """Post-Mustard/Senning atrial switch for D-TGA."""

    # ── Systemic venous pathway (left side — goes to LV then MPA) ─────
    _tube_v(ax, 52, 15, 27, 62, "SVC")
    _line(ax, 65, 77, 65, 218)

    # Venous atrium (receives SVC + IVC blood via baffle)
    _chamber(ax, 35, 218, 135, 145, "Venous\natrium")
    _line(ax, 65, 478, 65, 363)
    _tube_v(ax, 52, 478, 27, 72, "IVC")

    # LV_pulmonary (receives systemic venous blood → pumps to MPA)
    _chamber(ax, 188, 355, 115, 120, "LV\npulm")

    # Connecting venous atrium → LV_pulmonary
    _line(ax, 170, 340, 188, 400)

    # MPA — from LV_pulmonary (pulmonary ventricle in TGA)
    _tube_v(ax, 218, 118, 28, 78, "MPA")
    _line(ax, 245, 355, 232, 196)       # LV_pulmonary → MPA

    # ── Arterial venous pathway (right side — goes to RV then Aorta) ──
    # Arterial atrium (receives pulmonary venous blood)
    _chamber(ax, 308, 195, 122, 110, "Arterial\natrium")

    # RV_systemic (receives arterial atrium blood → pumps to Aorta)
    _chamber(ax, 318, 355, 140, 120, "RV\nsystemic")
    _line(ax, 369, 305, 388, 355)

    # Aorta (from RV_systemic in D-TGA)
    _tube_v(ax, 360, 478, 55, 68, "Ao")
    _line(ax, 388, 475, 387, 478)

    return {
        "SVC":             (65,  48),
        "IVC":             (65,  510),
        "Venous_atrium":   (102, 285),
        "LV_pulmonary":    (245, 415),
        "MPA":             (232, 158),
        "Arterial_atrium": (369, 248),
        "RV_systemic":     (388, 415),
        "Descending_Aorta":           (387, 508),
    }

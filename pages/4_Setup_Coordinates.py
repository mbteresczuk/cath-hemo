"""
Page 4: Coordinate setup for diagram annotation positions.

Select a location from the right panel, then either:
  - Click "📍 Set on image" to click the diagram at the correct spot, OR
  - Type x/y values directly in the number inputs.
Use Auto-configure first for an initial layout, then adjust any that are off.
"""
import streamlit as st
import base64
import io
from pathlib import Path

from utils.diagram_library import (
    load_library, mark_coords_status, get_all_diagrams,
    get_location_set, get_annotation_type, get_location_side,
    EXTRA_LOCATIONS, LOCATION_ANNOTATION_TYPES,
)
from utils.coordinator import (
    load_coords, save_coords, new_coords,
    add_location, remove_location, remove_location_step,
    get_placed_locations, get_next_unplaced_step,
    get_progress, is_location_complete,
)
from utils.auto_coords import auto_configure
from utils.annotator import safe_open_image
from utils.styles import inject_styles
from utils.drag_component import draggable_dots as _drag_comp

BASE_DIR = Path(__file__).parent.parent

st.set_page_config(page_title="Setup Coordinates", page_icon="⚙️", layout="wide")
inject_styles()

if "library" not in st.session_state or st.session_state.library is None:
    st.session_state.library = mark_coords_status(load_library())

library = st.session_state.library

st.title("⚙️ Setup Annotation Coordinates")
st.info("💡 **Tip:** For faster drag-and-drop editing, use the **🖱️ Open Drag Editor** button in the sidebar — it opens a standalone editor with no lag.")

all_diagrams = get_all_diagrams(library)
default_diag_id = st.session_state.get("setup_target_diagram")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Select Diagram")
    diag_options = [
        f"{'✅' if d.get('has_coords') else '⚠️'} {d['display_name']}"
        for d in all_diagrams
    ]
    default_idx = 0
    if default_diag_id:
        ids = [d["id"] for d in all_diagrams]
        if default_diag_id in ids:
            default_idx = ids.index(default_diag_id)

    selected_label = st.selectbox("Diagram", diag_options, index=default_idx)
    selected_idx = diag_options.index(selected_label)
    selected_diag = all_diagrams[selected_idx]

    st.markdown("---")
    st.markdown(f"**Anatomy type:** {selected_diag['anatomy_type'].replace('_', ' ')}")
    st.markdown(f"**Location set:** {selected_diag['location_set']}")

    coords_now = load_coords(selected_diag["id"])
    placed, total = get_progress(selected_diag["location_set"], coords_now)
    st.markdown(f"**Progress:** {placed}/{total} locations fully placed")

    if st.button("← Back to Dashboard", use_container_width=True):
        st.switch_page("app.py")
    # Build the editor URL dynamically so it works both locally and on Render
    _host = st.context.headers.get("host", "localhost:8000")
    _scheme = "https" if "onrender.com" in _host or "render.com" in _host else "http"
    _editor_url = f"{_scheme}://{_host}/editor"
    st.link_button("🖱️ Open Drag Editor", url=_editor_url, use_container_width=True, help="Opens the fast standalone drag-and-drop editor in a new tab")

# ── Load / init coords ────────────────────────────────────────────────────────
diag_id           = selected_diag["id"]
location_set_name = selected_diag["location_set"]
standard_locations = get_location_set(location_set_name)
img_path          = BASE_DIR / selected_diag["path"]

coords = load_coords(diag_id)
if coords is None:
    try:
        img = safe_open_image(img_path)
        w, h = img.size
    except Exception:
        w, h = 800, 600
    coords = new_coords(diag_id, w, h)

custom_locs_in_config = [
    loc for loc in coords.get("locations", {})
    if loc not in standard_locations
]
locations = standard_locations + custom_locs_in_config

placed_locs = get_placed_locations(coords)

# Session state for armed click
active_loc_key  = f"active_loc_{diag_id}"
active_step_key = f"active_step_{diag_id}"
active_loc  = st.session_state.get(active_loc_key)
active_step = st.session_state.get(active_step_key)

# ── Top controls ──────────────────────────────────────────────────────────────
ctrl1, ctrl2, ctrl3, ctrl4, ctrl5 = st.columns([3, 1, 1, 1, 1])

with ctrl2:
    save_clicked = st.button("💾 Save", use_container_width=True, type="primary")

with ctrl5:
    if st.button("🚀 Push to Render", use_container_width=True,
                 help="Commit all saved coord changes and push to GitHub so Render picks them up."):
        import subprocess, os
        script = BASE_DIR / "push_coords.sh"
        result = subprocess.run(
            ["bash", str(script)],
            capture_output=True, text=True, cwd=str(BASE_DIR)
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode == 0:
            st.success("✅ Pushed to Render! Redeploy starts in ~1 minute.\n\n" + output)
        else:
            st.error("Push failed:\n\n" + output)

with ctrl3:
    if st.button("🤖 Auto-configure", use_container_width=True,
                 help="Place all coordinates from a built-in template scaled to this image."):
        try:
            img = safe_open_image(img_path)
            w, h = img.size
        except Exception:
            w = coords.get("image_width", 800)
            h = coords.get("image_height", 600)
        auto = auto_configure(
            diag_id, w, h,
            selected_diag["anatomy_type"],
            location_set_name,
            image_path=str(img_path),
        )
        save_coords(diag_id, auto)
        st.session_state.library = mark_coords_status(load_library())
        st.session_state.pop(active_loc_key, None)
        st.session_state.pop(active_step_key, None)
        st.rerun()

with ctrl4:
    if st.button("🗑️ Clear All", use_container_width=True):
        coords["locations"] = {}
        save_coords(diag_id, coords)
        st.session_state.pop(active_loc_key, None)
        st.session_state.pop(active_step_key, None)
        st.rerun()

# Status bar
with ctrl1:
    if active_loc and active_step:
        step_label = "SATURATION" if active_step == "sat" else "PRESSURE"
        st.info(
            f"**Click the diagram image** to set the **{step_label}** "
            f"position for **{active_loc.replace('_', ' ')}**  —  "
            f"or type x/y values on the right and click 💾 Save."
        )
    elif not placed_locs:
        st.info("Click **Auto-configure** to place all positions at once, or select a location on the right.")
    else:
        placed, total = get_progress(location_set_name, coords)
        if placed == total:
            st.success(f"✅ All {total} locations configured.")
        else:
            st.warning(f"{placed}/{total} locations configured — select a location on the right to place the rest.")

# ── Main two-column layout ────────────────────────────────────────────────────
left_col, right_col = st.columns([3, 2])

# ── LEFT: drag-and-drop diagram ───────────────────────────────────────────────
with left_col:
    try:
        base_img = safe_open_image(img_path).convert("RGB")
        img_w, img_h = base_img.size

        buf = io.BytesIO()
        base_img.save(buf, format="PNG")
        img_b64 = base64.b64encode(buf.getvalue()).decode()

        drag_result = _drag_comp(
            imageBase64     = img_b64,
            coords_locations= coords.get("locations", {}),
            image_width     = img_w,
            image_height    = img_h,
            armed_loc       = active_loc,
            armed_step      = active_step,
            armed_type      = get_annotation_type(active_loc) if active_loc else None,
            key             = f"drag_{diag_id}",
        )

        if drag_result is not None:
            new_locs = drag_result.get("locations", {})
            action   = drag_result.get("type", "drag")

            coords["locations"] = new_locs
            save_coords(diag_id, coords)
            st.session_state.library = mark_coords_status(load_library())

            # For drags: save silently — no rerun so the component keeps its
            # own dot positions without a disruptive round-trip to Python.
            # For clicks: rerun to advance the armed state to the next step.
            if action == "click":
                if active_loc and active_step:
                    ann_type = get_annotation_type(active_loc)
                    if active_step == "sat" and ann_type == "saturation_and_pressure":
                        st.session_state[active_step_key] = "pressure"
                    else:
                        st.session_state.pop(active_loc_key, None)
                        st.session_state.pop(active_step_key, None)
                st.rerun()

    except Exception as e:
        st.error(f"Drag component error: {e}")

# ── RIGHT: location editor ────────────────────────────────────────────────────
with right_col:
    st.markdown("**Edit location:**")

    loc_options = ["— select —"] + [loc.replace("_", " ") for loc in locations]
    # If already armed, keep that location selected
    default_sel = 0
    if active_loc and active_loc in locations:
        default_sel = locations.index(active_loc) + 1

    loc_label = st.selectbox(
        "Location",
        loc_options,
        index=default_sel,
        label_visibility="collapsed",
        key=f"loc_sel_{diag_id}",
    )

    # Clear armed state when user picks a different location
    selected_loc = loc_label.replace(" ", "_") if loc_label != "— select —" else None
    if selected_loc != active_loc:
        st.session_state.pop(active_loc_key, None)
        st.session_state.pop(active_step_key, None)
        active_loc  = None
        active_step = None

    if selected_loc:
        coord    = coords.get("locations", {}).get(selected_loc, {})
        ann_type = get_annotation_type(selected_loc)
        is_placed = selected_loc in placed_locs

        st.markdown("---")

        # ── Saturation position ───────────────────────────────────────────────
        if ann_type in ("saturation", "saturation_and_pressure"):
            sat_x_val = coord.get("sat_x", coord.get("x", 0)) or 0
            sat_y_val = coord.get("sat_y", coord.get("y", 0)) or 0

            st.markdown("🟠 **Saturation position**")
            sc1, sc2 = st.columns(2)
            with sc1:
                new_sat_x = st.number_input(
                    "x", value=int(sat_x_val), step=1,
                    min_value=0, max_value=coords.get("image_width", 9999),
                    key=f"sx_{selected_loc}_{diag_id}",
                )
            with sc2:
                new_sat_y = st.number_input(
                    "y", value=int(sat_y_val), step=1,
                    min_value=0, max_value=coords.get("image_height", 9999),
                    key=f"sy_{selected_loc}_{diag_id}",
                )

            arm_sat_label = (
                "📍 Armed — click diagram" if (active_loc == selected_loc and active_step == "sat")
                else "📍 Set on image"
            )
            if st.button(arm_sat_label, key=f"arm_sat_{selected_loc}_{diag_id}",
                         use_container_width=True,
                         type="primary" if (active_loc == selected_loc and active_step == "sat") else "secondary"):
                st.session_state[active_loc_key]  = selected_loc
                st.session_state[active_step_key] = "sat"
                st.rerun()

        # ── Pressure position ─────────────────────────────────────────────────
        if ann_type in ("pressure_only", "saturation_and_pressure", "pcwp"):
            press_x_val = coord.get("pressure_x", 0) or 0
            press_y_val = coord.get("pressure_y", 0) or 0

            st.markdown("🔵 **Pressure position**")
            pc1, pc2 = st.columns(2)
            with pc1:
                new_press_x = st.number_input(
                    "x", value=int(press_x_val), step=1,
                    min_value=0, max_value=coords.get("image_width", 9999),
                    key=f"px_{selected_loc}_{diag_id}",
                )
            with pc2:
                new_press_y = st.number_input(
                    "y", value=int(press_y_val), step=1,
                    min_value=0, max_value=coords.get("image_height", 9999),
                    key=f"py_{selected_loc}_{diag_id}",
                )

            arm_press_label = (
                "📍 Armed — click diagram" if (active_loc == selected_loc and active_step == "pressure")
                else "📍 Set on image"
            )
            if st.button(arm_press_label, key=f"arm_press_{selected_loc}_{diag_id}",
                         use_container_width=True,
                         type="primary" if (active_loc == selected_loc and active_step == "pressure") else "secondary"):
                st.session_state[active_loc_key]  = selected_loc
                st.session_state[active_step_key] = "pressure"
                st.rerun()

        st.markdown("---")

        # ── Remove button ─────────────────────────────────────────────────────
        if is_placed:
            rm1, rm2 = st.columns(2)
            with rm1:
                if st.button("Remove location", key=f"rm_{selected_loc}_{diag_id}",
                             use_container_width=True):
                    coords = remove_location(coords, selected_loc)
                    save_coords(diag_id, coords)
                    st.session_state.library = mark_coords_status(load_library())
                    st.session_state.pop(active_loc_key, None)
                    st.session_state.pop(active_step_key, None)
                    st.rerun()
            with rm2:
                if ann_type == "saturation_and_pressure" and coord.get("pressure_x") is not None:
                    if st.button("Redo pressure", key=f"rp_{selected_loc}_{diag_id}",
                                 use_container_width=True,
                                 help="Remove only the pressure position to re-set it"):
                        coords = remove_location_step(coords, selected_loc, "pressure")
                        save_coords(diag_id, coords)
                        st.session_state.pop(active_loc_key, None)
                        st.session_state.pop(active_step_key, None)
                        st.rerun()

# ── Handle Save (reads number inputs and persists) ────────────────────────────
if save_clicked and selected_loc:
    coord = coords.get("locations", {}).get(selected_loc, {})
    ann_type = get_annotation_type(selected_loc)

    if selected_loc not in coords["locations"]:
        coords["locations"][selected_loc] = {
            "side": get_location_side(selected_loc),
            "annotation_type": ann_type,
        }
    entry = coords["locations"][selected_loc]

    if ann_type in ("saturation", "saturation_and_pressure"):
        sx_key = f"sx_{selected_loc}_{diag_id}"
        sy_key = f"sy_{selected_loc}_{diag_id}"
        if sx_key in st.session_state:
            entry["sat_x"] = int(st.session_state[sx_key])
            entry["sat_y"] = int(st.session_state[sy_key])
            entry.pop("x", None)
            entry.pop("y", None)

    if ann_type in ("pressure_only", "saturation_and_pressure", "pcwp"):
        px_key = f"px_{selected_loc}_{diag_id}"
        py_key = f"py_{selected_loc}_{diag_id}"
        if px_key in st.session_state:
            entry["pressure_x"] = int(st.session_state[px_key])
            entry["pressure_y"] = int(st.session_state[py_key])

    save_coords(diag_id, coords)
    st.session_state.library = mark_coords_status(load_library())
    st.success(f"Saved {selected_loc.replace('_', ' ')}.")
    st.rerun()

# ── Progress summary ──────────────────────────────────────────────────────────
st.markdown("---")
placed_locs = get_placed_locations(coords)   # refresh after any saves above
remaining   = [loc for loc in locations if loc not in placed_locs]

if placed_locs:
    st.caption(f"✅ Configured ({len(placed_locs)}): " + ", ".join(
        loc.replace("_", " ") for loc in placed_locs
    ))
if remaining:
    st.caption(f"⚠️ Not placed ({len(remaining)}): " + ", ".join(
        loc.replace("_", " ") for loc in remaining
    ))

# ── Skip a remaining location ─────────────────────────────────────────────────
# Pulmonary veins must always be placed on the diagram — never skippable.
_ALWAYS_PLACE = {"RPV", "LPV", "RUPV", "LUPV", "RLPV", "LLPV"}
skippable = [loc for loc in remaining if loc not in _ALWAYS_PLACE]

if skippable:
    skip_loc = st.selectbox("Mark as absent (skip):", ["—"] + skippable, key="skip_sel")
    if skip_loc != "—":
        if st.button(f"Skip '{skip_loc}'"):
            if skip_loc not in coords["locations"]:
                coords["locations"][skip_loc] = {
                    "side": "right",
                    "annotation_type": get_annotation_type(skip_loc),
                }
            coords["locations"][skip_loc]["skipped"] = True
            save_coords(diag_id, coords)
            st.rerun()

# ── Partial placements ────────────────────────────────────────────────────────
partial = [
    loc for loc in locations
    if (
        loc in coords.get("locations", {})
        and not is_location_complete(loc, coords["locations"][loc])
        and not coords["locations"][loc].get("skipped")
        and ("sat_x" in coords["locations"][loc] or "x" in coords["locations"][loc])
    )
]
if partial:
    st.caption(
        "⏳ Saturation placed, pressure still needed: "
        + ", ".join(loc.replace("_", " ") for loc in partial)
    )

# ── Add Custom Location ───────────────────────────────────────────────────────
st.markdown("---")
with st.expander("➕ Add custom location"):
    st.caption(
        "Add extra locations specific to this diagram (e.g., Ascending Aorta, "
        "LSVC, Fontan conduit)."
    )
    already_used    = set(locations) | set(coords.get("locations", {}).keys())
    available_extras = [loc for loc in EXTRA_LOCATIONS if loc not in already_used]

    add_col1, add_col2 = st.columns([2, 1])
    with add_col1:
        extra_choice = st.selectbox(
            "Select a location to add:",
            ["—"] + [loc.replace("_", " ") for loc in available_extras],
            key="extra_loc_select",
        )
    with add_col2:
        custom_name = st.text_input(
            "Or type a custom name:",
            placeholder="e.g. Hepatic_vein",
            key="custom_loc_name",
        )

    loc_to_add = None
    if custom_name.strip():
        loc_to_add = custom_name.strip().replace(" ", "_")
    elif extra_choice != "—":
        loc_to_add = extra_choice.replace(" ", "_")

    if loc_to_add and loc_to_add not in already_used:
        ann_type = LOCATION_ANNOTATION_TYPES.get(loc_to_add, "saturation_and_pressure")
        side     = get_location_side(loc_to_add)
        st.caption(
            f"Will add **{loc_to_add.replace('_', ' ')}** — "
            f"type: {ann_type.replace('_', ' ')}, side: {side}"
        )
        if st.button(f"Add {loc_to_add.replace('_', ' ')}", type="primary"):
            # Place dot at image center by default so it's immediately draggable
            cx = coords.get("image_width",  800) // 2
            cy = coords.get("image_height", 600) // 2
            entry = {
                "side": side,
                "annotation_type": ann_type,
                "sat_x": cx,
                "sat_y": cy,
            }
            if ann_type in ("saturation_and_pressure", "pressure_only", "pcwp"):
                entry["pressure_x"] = cx + 25
                entry["pressure_y"] = cy - 30
            coords["locations"][loc_to_add] = entry
            save_coords(diag_id, coords)
            st.session_state.library = mark_coords_status(load_library())
            # Auto-select AND arm the new location so the orange banner
            # appears immediately and the user can click (or drag) to place it.
            st.session_state[f"loc_sel_{diag_id}"] = loc_to_add.replace("_", " ")
            st.session_state[active_loc_key]  = loc_to_add
            st.session_state[active_step_key] = "sat"
            st.rerun()
    elif loc_to_add and loc_to_add in already_used:
        st.warning(f"{loc_to_add.replace('_', ' ')} is already configured.")

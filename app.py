"""
Cardiac Catheterization Report Dashboard
Interactive form-based workflow: type diagnosis → select anatomy → enter hemodynamics → get annotated report.
"""
import streamlit as st
from pathlib import Path
from PIL import Image

from utils.diagram_library import load_library, mark_coords_status, get_location_set, delete_diagram
from utils.matcher import match_diagrams
from utils.parser import parse_hemodynamics, parse_hemodynamics_with_conflicts
from utils.coordinator import load_coords
from utils.annotator import (
    annotate_diagram,
    image_to_bytes, pil_to_bytes, safe_open_image,
)
from utils.hemodynamics import calculate_all, detect_step_ups
from utils.narrative import generate_hemodynamic_narrative
from utils.clipboard import copy_image_to_clipboard, get_clipboard_help
from utils.report_writer import populate_template
from utils.styles import inject_styles

BASE_DIR = Path(__file__).parent

st.set_page_config(
    page_title="Cath Report Dashboard",
    page_icon="🫀",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_styles()

# ── Session state defaults ───────────────────────────────────────────────────
_defaults = {
    "library": None,
    "selected_diagram": None,
    "matched_diagrams": [],
    "hemodynamics": {},
    "patient_data": {},
    "calculations": {},
    "step_ups": [],
    "narrative": "",
    "annotated_image": None,
    "docx_bytes": None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

if st.session_state.library is None:
    st.session_state.library = mark_coords_status(load_library())

library = st.session_state.library

# Sidebar nav
st.sidebar.button(
    "⚙️ Setup Annotation Positions",
    on_click=lambda: st.switch_page("pages/4_Setup_Coordinates.py"),
    use_container_width=True,
)

# ── Header ───────────────────────────────────────────────────────────────────
st.title("🫀 Cardiac Catheterization Report Dashboard")

st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# STEP 1: Diagnosis + Diagram  |  STEP 2: Hemodynamic Entry
# ═══════════════════════════════════════════════════════════════════════════
col_diag, col_hemo = st.columns([1, 1], gap="large")

with col_diag:
    st.subheader("1. Diagnosis & Anatomy")
    diagnosis_input = st.text_input(
        "Type the diagnosis:",
        placeholder="e.g.  TOF   |   HLHS s/p Norwood   |   ASD with LSVC",
        key="diagnosis_input",
    )

    if diagnosis_input:
        matches = match_diagrams(diagnosis_input, library, top_n=12)
        st.session_state.matched_diagrams = matches
    else:
        matches = st.session_state.matched_diagrams

    chosen_diag = None
    if matches:
        st.markdown("**Best matching diagrams:**")
        options = [m["display_name"] for m in matches]
        choice = st.radio(
            "Select anatomy:",
            options,
            index=0,
            key="diagram_choice",
            label_visibility="collapsed",
        )
        chosen_diag = next((m for m in matches if m["display_name"] == choice), matches[0])
        st.session_state.selected_diagram = chosen_diag

        img_path = BASE_DIR / chosen_diag["path"]
        try:
            thumb = safe_open_image(img_path)
            thumb.thumbnail((400, 340), Image.LANCZOS)
            st.image(pil_to_bytes(thumb), caption=chosen_diag["display_name"],
                     use_container_width=True)
        except Exception:
            st.warning("Could not load diagram image.")

        if not chosen_diag.get("has_coords"):
            st.warning(
                "⚠️ Annotation positions not set up for this diagram. "
                "The diagram will show without annotations."
            )
            if st.button("⚙️ Set up annotation positions", use_container_width=True):
                st.session_state["setup_target_diagram"] = chosen_diag["id"]
                st.switch_page("pages/4_Setup_Coordinates.py")

        # ── Delete diagram ────────────────────────────────────────────────────
        _del_key = f"_del_armed_{chosen_diag['id']}"
        if st.button("🗑️ Delete diagram", use_container_width=True, key="del_diag_btn"):
            st.session_state[_del_key] = True

        if st.session_state.get(_del_key):
            st.warning(
                f"⚠️ Permanently delete **{chosen_diag['display_name']}** "
                "and all its annotation positions? This cannot be undone."
            )
            _dc1, _dc2 = st.columns(2)
            with _dc1:
                if st.button("✅ Yes, delete", type="primary",
                             use_container_width=True, key="confirm_del_btn"):
                    delete_diagram(chosen_diag)
                    for _k in ["library", "selected_diagram", "annotated_image",
                               "matched_diagrams", "hemodynamics", "calculations",
                               "narrative", "step_ups", "docx_bytes"]:
                        st.session_state[_k] = None
                    st.session_state.matched_diagrams = []
                    st.session_state.pop(_del_key, None)
                    st.rerun()
            with _dc2:
                if st.button("Cancel", use_container_width=True, key="cancel_del_btn"):
                    st.session_state.pop(_del_key, None)
                    st.rerun()
    else:
        if diagnosis_input:
            st.info("No matching diagrams found. Try different keywords.")
        st.session_state.selected_diagram = None

# Collect custom location names (those added manually in Setup Coordinates
# and not built into the standard alias map).  These are passed to the parser
# so users can type them by name in the hemodynamics text area.
_diagram_custom_locs: list = []
if chosen_diag:
    _dc = load_coords(chosen_diag["id"])
    if _dc:
        from utils.parser import LOCATION_ALIASES as _LA
        _diagram_custom_locs = [
            k for k in _dc.get("locations", {})
            if k not in _LA
        ]

with col_hemo:
    st.subheader("2. Hemodynamic Measurements")
    st.caption("One location per line. Format: **Location  Sat  Sys/Dia  Mean** (omit any field not measured)")
    hemo_text = st.text_area(
        "Hemodynamic data",
        value=st.session_state.get("hemo_text_input", ""),
        height=340,
        placeholder=(
            "SVC  79\n"
            "IVC  81\n"
            "RA  75  10/5  7\n"
            "RV  75  50/5\n"
            "MPA  75  50/30  38\n"
            "RPA  75  50/30  38\n"
            "LPA  75  50/30  38\n"
            "RPCWP  12\n"
            "LPCWP  12\n"
            "LA  98  10/5  8\n"
            "LV  98  95/10\n"
            "Aorta  98  95/55  72"
        ),
        key="hemo_text_input",
        label_visibility="collapsed",
    )

    # Live parse preview + conflict detection
    if hemo_text.strip():
        parsed_preview, preview_conflicts = parse_hemodynamics_with_conflicts(
            hemo_text,
            extra_locations=_diagram_custom_locs or None,
        )
        if parsed_preview:
            with st.expander(f"✅ Recognized {len(parsed_preview)} location(s)", expanded=False):
                for loc, vals in parsed_preview.items():
                    parts = []
                    if "sat" in vals:
                        parts.append(f"Sat {int(vals['sat'])}%")
                    if "systolic" in vals and "diastolic" in vals:
                        parts.append(f"{int(vals['systolic'])}/{int(vals['diastolic'])}")
                        if "mean" in vals:
                            parts[-1] += f"  mean {int(vals['mean'])}"
                    elif "mean" in vals:
                        parts.append(f"mean {int(vals['mean'])}")
                    conflict_flag = " ⚠️" if loc in preview_conflicts else ""
                    st.caption(f"**{loc}**{conflict_flag}: {' | '.join(parts)}")
        else:
            st.caption("⚠️ No locations recognized yet.")

        # ── Conflict resolution UI ──────────────────────────────────────────
        if preview_conflicts:
            st.warning(
                f"⚠️ **Conflicting values found for {len(preview_conflicts)} location(s).** "
                "Please select which value to use for each conflict below before generating."
            )
            for loc, field_conflicts in preview_conflicts.items():
                st.markdown(f"**{loc.replace('_', ' ')}** — multiple values detected:")
                for field, values in field_conflicts.items():
                    unit = "%" if field == "sat" else " mmHg"
                    label = {"sat": "Saturation", "systolic": "Systolic",
                             "diastolic": "Diastolic", "mean": "Mean"}.get(field, field.title())
                    options = [f"{int(v)}{unit}" for v in values]
                    st.radio(
                        f"{label}",
                        options=options,
                        key=f"conflict_{loc}_{field}",
                        horizontal=True,
                    )
                st.markdown("---")

# ═══════════════════════════════════════════════════════════════════════════
# GENERATE BUTTON
# ═══════════════════════════════════════════════════════════════════════════
st.markdown("---")
can_generate = chosen_diag is not None

gen_col, hint_col = st.columns([2, 3])
with gen_col:
    generate_clicked = st.button(
        "⚡ Generate Report",
        type="primary",
        use_container_width=True,
        disabled=not can_generate,
    )
with hint_col:
    if not can_generate:
        st.caption("← Type a diagnosis and select an anatomy to generate the report.")

if generate_clicked and can_generate:
    # ── Collect hemodynamic data, applying any conflict resolutions ───────────
    new_hemo, gen_conflicts = parse_hemodynamics_with_conflicts(
        st.session_state.get("hemo_text_input", ""),
        extra_locations=_diagram_custom_locs or None,
    )
    # Apply user's conflict resolution choices from radio buttons
    for loc, field_conflicts in gen_conflicts.items():
        for field, values in field_conflicts.items():
            choice_key = f"conflict_{loc}_{field}"
            chosen_str = st.session_state.get(choice_key)
            if chosen_str is not None:
                try:
                    # Strip unit suffix (% or mmHg) and convert to float
                    chosen_val = float(chosen_str.replace("%", "").replace("mmHg", "").strip())
                    new_hemo.setdefault(loc, {})[field] = chosen_val
                except ValueError:
                    pass

    # ── Save patient data (including sidebar values) ─────────────────────────
    patient_data = {
        "name": st.session_state.get("pi_name", ""),
        "mrn": st.session_state.get("pi_mrn", ""),
        "dob": st.session_state.get("pi_dob", ""),
        "doc": st.session_state.get("pi_doc", ""),
        "hgb": st.session_state.get("pi_hgb", 12.0),
        "avo2": st.session_state.get("pi_avo2", 125),
        "anesthesia": st.session_state.get("pi_anes", "general anesthesia"),
        "case_type": st.session_state.get("pi_case", "standard"),
        "fio2": "21%",
        "anatomy_type": chosen_diag.get("anatomy_type", "biventricle"),
        "abd": st.session_state.get("pi_abd", ""),
        "qp_manual": st.session_state.get("pi_qp", ""),
        "qs_manual": st.session_state.get("pi_qs", ""),
        "pvri_manual": st.session_state.get("pi_pvri", ""),
    }

    st.session_state.patient_data = patient_data
    st.session_state.hemodynamics = new_hemo

    # ── Calculations and narrative ───────────────────────────────────────────
    calcs = calculate_all(new_hemo, patient_data)
    step_ups = detect_step_ups(new_hemo)
    narrative = generate_hemodynamic_narrative(new_hemo, calcs, patient_data, step_ups)

    st.session_state.calculations = calcs
    st.session_state.step_ups = step_ups
    st.session_state.narrative = narrative
    st.session_state.docx_bytes = None

    # ── Build annotated image ────────────────────────────────────────────────
    img_path = BASE_DIR / chosen_diag["path"]
    coords = load_coords(chosen_diag["id"])
    if coords is None:
        from utils.auto_coords import auto_configure
        from utils.coordinator import save_coords
        coords = auto_configure(
            chosen_diag["id"],
            chosen_diag["image_width"],
            chosen_diag["image_height"],
            chosen_diag["anatomy_type"],
            chosen_diag["location_set"],
            image_path=str(img_path),
        )
        save_coords(chosen_diag["id"], coords)
        st.session_state.library = mark_coords_status(load_library())
    annotated = annotate_diagram(str(img_path), coords, new_hemo)
    st.session_state.annotated_image = annotated


# ═══════════════════════════════════════════════════════════════════════════
# OUTPUT (shown after generation)
# ═══════════════════════════════════════════════════════════════════════════
if st.session_state.annotated_image is not None:
    st.markdown("---")
    st.subheader("3. Output")

    annotated_img = st.session_state.annotated_image
    calcs = st.session_state.calculations
    narrative = st.session_state.narrative
    step_ups = st.session_state.step_ups
    diag = st.session_state.selected_diagram or chosen_diag

    img_bytes = image_to_bytes(annotated_img, fmt="PNG")

    # ── Action buttons ───────────────────────────────────────────────────────
    ab1, ab2, ab3, ab4, ab5 = st.columns(5)
    with ab1:
        st.download_button(
            "⬇️ Download Diagram",
            data=img_bytes,
            file_name=f"cath_{diag['id']}.png",
            mime="image/png",
            use_container_width=True,
        )
    with ab2:
        if st.button("📋 Copy Diagram", use_container_width=True):
            ok, msg = copy_image_to_clipboard(annotated_img)
            st.success(msg) if ok else st.info(get_clipboard_help())

    with ab3:
        if st.button("📄 Generate Word Report", use_container_width=True):
            with st.spinner("Building document…"):
                try:
                    docx = populate_template(
                        template_name=st.session_state.patient_data.get("case_type", "standard"),
                        narrative=narrative,
                        patient_data=st.session_state.patient_data,
                        calculations=calcs,
                        annotated_image=annotated_img,
                    )
                    st.session_state.docx_bytes = docx
                except Exception as e:
                    st.error(f"Could not generate report: {e}")
        if st.session_state.docx_bytes:
            st.download_button(
                "⬇️ Download Word Report",
                data=st.session_state.docx_bytes,
                file_name=f"cath_report_{diag['id']}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )

    with ab4:
        if st.button("🔧 Fix Positions", use_container_width=True,
                     help="Annotation circles in wrong spots? Click to manually reposition them."):
            st.session_state["setup_target_diagram"] = diag["id"]
            st.switch_page("pages/4_Setup_Coordinates.py")

    with ab5:
        if st.button("🔄 New Report", use_container_width=True):
            for key in ["annotated_image", "hemodynamics", "calculations",
                        "narrative", "step_ups", "docx_bytes"]:
                st.session_state[key] = (
                    None if key == "annotated_image" else
                    {} if key in ("hemodynamics", "calculations") else
                    [] if key == "step_ups" else
                    "" if key == "narrative" else None
                )
            st.rerun()

    # ── Main output columns ──────────────────────────────────────────────────
    out_img_col, out_text_col = st.columns([3, 2], gap="large")

    with out_img_col:
        st.markdown(f"**Annotated Diagram — {diag['display_name']}**")
        st.image(pil_to_bytes(annotated_img), use_container_width=True)

    with out_text_col:
        # Narrative — shown first
        st.markdown("**Hemodynamic Narrative**")
        if narrative:
            st.text_area(
                "Copy and paste into your cath report:",
                value=narrative,
                height=220,
                key="narrative_out",
            )
            st.components.v1.html(
                """<button onclick="
                    var ta=document.querySelectorAll('textarea');
                    var t=Array.from(ta).find(x=>x.value && x.value.length>30);
                    if(t){t.select();document.execCommand('copy');
                    this.textContent='✓ Copied!';
                    setTimeout(()=>{this.textContent='📋 Copy Narrative'},2000)}"
                  style="background:#0068c9;color:white;border:none;padding:7px 14px;
                         border-radius:4px;cursor:pointer;font-size:13px;
                         width:100%;margin-top:2px">
                  📋 Copy Narrative
                </button>""",
                height=45,
            )
        else:
            st.info("No narrative generated — check that hemodynamic values were entered.")

        # Step-ups
        if step_ups:
            st.markdown("**Step-Up Detection**")
            for su in step_ups:
                st.warning(
                    f"⬆️ Step-up at **{su['level']}** level: "
                    f"{su['from']} {int(su['from_sat'])}% → "
                    f"{su['to']} {int(su['to_sat'])}% (Δ {su['delta']}%)"
                )

        # Calculated hemodynamics
        st.markdown("**Calculated Hemodynamics**")
        if calcs and not calcs.get("error"):
            import pandas as pd
            rows = [
                ("Cardiac Index (Qs)", calcs.get("qs"), "L/min/m²"),
                ("Pulmonary Flow (Qp)", calcs.get("qp"), "L/min/m²"),
                ("Qp:Qs", calcs.get("qp_qs"), ":1"),
                ("Mixed Venous Sat", calcs.get("mixed_venous_sat"), "%"),
                ("Mean PCWP", calcs.get("mean_pcwp"), "mmHg"),
                ("TPG", calcs.get("tpg"), "mmHg"),
                ("PVRi", calcs.get("pvri"), "iWU"),
                ("SVRi", calcs.get("svri"), "iWU"),
            ]
            table_rows = [{"Parameter": p, "Value": v, "Units": u}
                          for p, v, u in rows if v is not None]
            if table_rows:
                st.dataframe(pd.DataFrame(table_rows), use_container_width=True,
                             hide_index=True)
            for w in calcs.get("warnings", []):
                st.caption(f"ℹ️ {w}")
        else:
            st.info("Enter saturation and pressure values above to see calculations.")

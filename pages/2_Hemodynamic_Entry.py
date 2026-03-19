"""
Page 2: Enter hemodynamic measurements and patient info.
"""
import streamlit as st
from pathlib import Path
from PIL import Image

from utils.annotator import pil_to_bytes, safe_open_image
from utils.diagram_library import get_location_set, get_annotation_type, load_library, mark_coords_status
from utils.hemodynamics import calculate_all, detect_step_ups
from utils.narrative import generate_hemodynamic_narrative
from utils.styles import inject_styles

BASE_DIR = Path(__file__).parent.parent

st.set_page_config(page_title="Enter Hemodynamics", page_icon="🫀", layout="wide")
inject_styles()

if "library" not in st.session_state or st.session_state.library is None:
    st.session_state.library = mark_coords_status(load_library())

st.title("Step 2: Enter Hemodynamic Data")

if not st.session_state.get("selected_diagram"):
    st.warning("No diagram selected. Please go back to Step 1.")
    if st.button("← Back to Diagram Selector"):
        st.switch_page("pages/1_Diagram_Selector.py")
    st.stop()

diag = st.session_state.selected_diagram
location_set_name = diag.get("location_set", "standard_biventricle")
anatomy_type = diag.get("anatomy_type", "biventricle")
locations = get_location_set(location_set_name)

st.info(f"**Diagram:** {diag['display_name']} | **Anatomy:** {anatomy_type.replace('_', ' ')}")

# Location annotation types for disabling irrelevant fields
NO_SAT_LOCS = {"RPCWP", "LPCWP"}
NO_PRESSURE_LOCS = {"SVC", "IVC"}
MEAN_ONLY_LOCS = set()

left_col, right_col = st.columns([1, 2])

# --- Left: Diagram preview ---
with left_col:
    st.subheader("Anatomy")
    img_path = BASE_DIR / diag["path"]
    try:
        img = safe_open_image(img_path)
        st.image(img.convert("RGB"), use_container_width=True)
    except Exception as e:
        st.error(f"Could not load image: {e}")

    has_coords = diag.get("has_coords", False)
    if not has_coords:
        st.warning("⚠️ Annotation coordinates not set up for this diagram. Output diagram will not show annotations.")
        if st.button("Set up coordinates now"):
            st.session_state["setup_target_diagram"] = diag["id"]
            st.switch_page("pages/4_Setup_Coordinates.py")

# --- Right: Patient info + hemodynamic entry ---
with right_col:
    # Patient info
    st.subheader("Patient Information")
    pi_col1, pi_col2 = st.columns(2)
    with pi_col1:
        name = st.text_input("Patient Name", value=st.session_state.patient_data.get("name", ""))
        mrn = st.text_input("MRN", value=st.session_state.patient_data.get("mrn", ""))
        dob = st.text_input("DOB", value=st.session_state.patient_data.get("dob", ""))
    with pi_col2:
        doc_date = st.text_input("Date of Cath", value=st.session_state.patient_data.get("doc", ""))
        hgb = st.number_input("Hgb (g/dL)", min_value=1.0, max_value=25.0,
                               value=float(st.session_state.patient_data.get("hgb", 12.0)), step=0.1)


    avo2_col, anes_col = st.columns(2)
    with avo2_col:
        avo2 = st.number_input(
            "aVO₂ (mL/min/m²)", min_value=50, max_value=300,
            value=int(st.session_state.patient_data.get("avo2", 125)),
            help="Assumed O2 consumption index. Default 125 mL/min/m² at rest.",
        )
    with anes_col:
        anesthesia = st.selectbox(
            "Anesthesia",
            ["general anesthesia", "monitored anesthesia care (MAC)", "moderate sedation"],
            index=["general anesthesia", "monitored anesthesia care (MAC)", "moderate sedation"].index(
                st.session_state.patient_data.get("anesthesia", "general anesthesia")
            ),
        )

    case_type = st.selectbox(
        "Report Template",
        ["standard", "pHTN", "OHT"],
        index=["standard", "pHTN", "OHT"].index(
            st.session_state.patient_data.get("case_type", "standard")
        ),
    )

    st.markdown("---")
    st.subheader("Hemodynamic Measurements")
    st.caption("Leave blank if not measured. Pressures in mmHg, saturations in %.")

    # Column headers
    hdr = st.columns([1.5, 1, 1, 1, 1])
    hdr[0].markdown("**Location**")
    hdr[1].markdown("**Sat %**")
    hdr[2].markdown("**Systolic**")
    hdr[3].markdown("**Diastolic**")
    hdr[4].markdown("**Mean**")

    # Load existing hemodynamics from session state
    saved_hemo = st.session_state.hemodynamics

    new_hemo = {}
    for loc in locations:
        row = st.columns([1.5, 1, 1, 1, 1])
        ann_type = get_annotation_type(loc)

        row[0].markdown(f"**{loc.replace('_', ' ')}**")

        # Sat field
        sat_val = saved_hemo.get(loc, {}).get("sat", None)
        if loc not in NO_SAT_LOCS:
            sat_input = row[1].text_input(
                "sat", value="" if sat_val is None else str(int(sat_val)),
                key=f"sat_{loc}", label_visibility="collapsed",
            )
        else:
            row[1].markdown("—")
            sat_input = ""

        # Systolic
        sys_val = saved_hemo.get(loc, {}).get("systolic", None)
        if loc not in NO_PRESSURE_LOCS:
            sys_input = row[2].text_input(
                "sys", value="" if sys_val is None else str(int(sys_val)),
                key=f"sys_{loc}", label_visibility="collapsed",
            )
        else:
            row[2].markdown("—")
            sys_input = ""

        # Diastolic
        dia_val = saved_hemo.get(loc, {}).get("diastolic", None)
        if loc not in NO_PRESSURE_LOCS:
            dia_input = row[3].text_input(
                "dia", value="" if dia_val is None else str(int(dia_val)),
                key=f"dia_{loc}", label_visibility="collapsed",
            )
        else:
            row[3].markdown("—")
            dia_input = ""

        # Mean
        mean_val = saved_hemo.get(loc, {}).get("mean", None)
        if loc not in NO_PRESSURE_LOCS:
            mean_input = row[4].text_input(
                "mean", value="" if mean_val is None else str(int(mean_val)),
                key=f"mean_{loc}", label_visibility="collapsed",
            )
        else:
            row[4].markdown("—")
            mean_input = ""

        # Parse inputs
        def parse_float(s):
            try:
                return float(s.strip()) if s.strip() else None
            except Exception:
                return None

        loc_data = {}
        v = parse_float(sat_input)
        if v is not None:
            loc_data["sat"] = v
        v = parse_float(sys_input)
        if v is not None:
            loc_data["systolic"] = v
        v = parse_float(dia_input)
        if v is not None:
            loc_data["diastolic"] = v
        v = parse_float(mean_input)
        if v is not None:
            loc_data["mean"] = v

        if loc_data:
            new_hemo[loc] = loc_data

    st.markdown("---")

    if st.button("⚡ Calculate & Generate Report", type="primary", use_container_width=True):
        # Save patient data
        st.session_state.patient_data = {
            "name": name,
            "mrn": mrn,
            "dob": dob,
            "doc": doc_date,
            "hgb": hgb,
            "avo2": avo2,
            "anesthesia": anesthesia,
            "case_type": case_type,
            "fio2": "21%",
            "anatomy_type": anatomy_type,
        }
        st.session_state.hemodynamics = new_hemo

        # Run calculations
        calculations = calculate_all(new_hemo, st.session_state.patient_data)
        step_ups = detect_step_ups(new_hemo)
        narrative = generate_hemodynamic_narrative(
            new_hemo, calculations, st.session_state.patient_data, step_ups
        )

        st.session_state.calculations = calculations
        st.session_state.step_ups = step_ups
        st.session_state.narrative = narrative
        st.session_state.annotated_image = None  # Will be generated on output page

        st.switch_page("pages/3_Annotated_Output.py")

if st.button("← Back to Diagram Selector"):
    st.switch_page("pages/1_Diagram_Selector.py")

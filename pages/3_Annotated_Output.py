"""
Page 3: Display annotated diagram, narrative text, and calculated hemodynamics.
"""
import io
import streamlit as st
from pathlib import Path
from PIL import Image

from utils.annotator import annotate_diagram, image_to_bytes, pil_to_bytes, build_share_image
from utils.coordinator import load_coords
from utils.clipboard import copy_image_to_clipboard, get_clipboard_help
from utils.report_writer import populate_template
from utils.diagram_library import load_library, mark_coords_status
from utils.styles import inject_styles

BASE_DIR = Path(__file__).parent.parent

st.set_page_config(page_title="Cath Report Output", page_icon="🫀", layout="wide")
inject_styles()

if "library" not in st.session_state or st.session_state.library is None:
    st.session_state.library = mark_coords_status(load_library())

st.title("Step 3: Report Output")

if not st.session_state.get("selected_diagram"):
    st.warning("No diagram selected. Please start from Step 1.")
    if st.button("← Go to Step 1"):
        st.switch_page("pages/1_Diagram_Selector.py")
    st.stop()

if not st.session_state.get("hemodynamics") and not st.session_state.get("calculations"):
    st.warning("No hemodynamic data entered. Please go to Step 2.")
    if st.button("← Go to Step 2"):
        st.switch_page("pages/2_Hemodynamic_Entry.py")
    st.stop()

diag = st.session_state.selected_diagram
hemodynamics = st.session_state.hemodynamics
calculations = st.session_state.calculations
step_ups = st.session_state.step_ups
narrative = st.session_state.narrative
patient_data = st.session_state.patient_data

# Generate annotated image + Word report together on first load
if st.session_state.get("annotated_image") is None:
    img_path = BASE_DIR / diag["path"]
    coords = load_coords(diag["id"])
    annotated = annotate_diagram(str(img_path), coords, hemodynamics,
                                 anatomy_type=patient_data.get("anatomy_type", "biventricle"))
    st.session_state.annotated_image = annotated
    st.session_state.docx_bytes = None       # reset so report regenerates below
    st.session_state.share_img_bytes = None  # reset share image too

annotated_img = st.session_state.annotated_image
img_bytes = image_to_bytes(annotated_img, fmt="PNG")

# Build Word report (once per session / whenever annotated_image is fresh)
if st.session_state.get("docx_bytes") is None:
    try:
        st.session_state.docx_bytes = populate_template(
            template_name=patient_data.get("case_type", "standard"),
            narrative=narrative,
            patient_data=patient_data,
            calculations=calculations,
            annotated_image=annotated_img,
        )
    except Exception:
        st.session_state.docx_bytes = None

# Build combined share image (diagram + narrative side-by-side)
if st.session_state.get("share_img_bytes") is None:
    try:
        share_img = build_share_image(annotated_img, narrative, patient_data)
        st.session_state.share_img_bytes = image_to_bytes(share_img, fmt="PNG")
    except Exception:
        st.session_state.share_img_bytes = None

# ── Action buttons row ──────────────────────────────────────────────────────
st.subheader("Export")
btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)

with btn_col1:
    # Share: downloads the diagram image AND opens the email client
    # with the narrative pre-filled in the body — one click does both.
    share_bytes = st.session_state.get("share_img_bytes")
    if share_bytes:
        import base64, urllib.parse
        img_b64 = base64.b64encode(share_bytes).decode()
        subject = urllib.parse.quote(
            f"Cath Report – {patient_data.get('name', '')} {patient_data.get('doc', '')}".strip(" –")
        )
        body = urllib.parse.quote(narrative or "")
        filename = f"cath_report_{diag['id']}.png"
        st.components.v1.html(f"""
        <button onclick="
          /* 1. Download the diagram image */
          var a = document.createElement('a');
          a.href = 'data:image/png;base64,{img_b64}';
          a.download = '{filename}';
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          /* 2. Open email client with narrative pre-filled */
          setTimeout(function(){{
            window.location.href = 'mailto:?subject={subject}&body={body}';
          }}, 300);
        "
        style="background:#0068c9;color:white;border:none;padding:10px 16px;
               border-radius:6px;cursor:pointer;font-size:15px;width:100%;
               font-family:sans-serif;font-weight:600;">
          📤 Share (Diagram + Narrative)
        </button>
        <div style="font-size:11px;color:#666;margin-top:4px;">
          Downloads diagram · opens email with narrative
        </div>
        """, height=70)
    else:
        st.button("📤 Share (Diagram + Narrative)", disabled=True,
                  use_container_width=True, type="primary")

with btn_col2:
    # Word doc (also contains both diagram + narrative)
    if st.session_state.get("docx_bytes"):
        st.download_button(
            "📄 Download Word Report",
            data=st.session_state["docx_bytes"],
            file_name=f"cath_report_{diag['id']}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )
    else:
        if st.button("📄 Generate Word Report", use_container_width=True):
            with st.spinner("Building report..."):
                try:
                    st.session_state.docx_bytes = populate_template(
                        template_name=patient_data.get("case_type", "standard"),
                        narrative=narrative,
                        patient_data=patient_data,
                        calculations=calculations,
                        annotated_image=annotated_img,
                    )
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not generate report: {e}")

with btn_col3:
    st.download_button(
        "⬇️ Download Diagram (PNG)",
        data=img_bytes,
        file_name=f"cath_{diag['id']}.png",
        mime="image/png",
        use_container_width=True,
    )

with btn_col4:
    if st.button("← Edit Hemodynamics", use_container_width=True):
        st.switch_page("pages/2_Hemodynamic_Entry.py")

if st.button("🔧 Fix Annotation Positions",
             help="Circles or pressure values in wrong spots? Click to reposition them."):
    st.session_state["setup_target_diagram"] = diag["id"]
    st.switch_page("pages/4_Setup_Coordinates.py")

st.markdown("---")

# ── Main output columns ─────────────────────────────────────────────────────
diagram_col, text_col = st.columns([1, 1])

# Left: annotated diagram
with diagram_col:
    st.subheader(f"Annotated Diagram: {diag['display_name']}")
    if not diag.get("has_coords"):
        st.info(
            "ℹ️ Annotation positions not configured for this diagram. "
            "The base image is shown; go to **Setup Coordinates** to add annotation positions."
        )
    st.image(pil_to_bytes(annotated_img), use_container_width=True)

# Right: narrative + calculations
with text_col:
    # Narrative — shown first and prominently
    st.subheader("Hemodynamic Narrative")
    if narrative:
        st.text_area(
            "Copy and paste into your cath report:",
            value=narrative,
            height=250,
            key="narrative_text",
        )
        st.components.v1.html(
            """<button onclick="
                var ta=document.querySelectorAll('textarea');
                var t=Array.from(ta).find(x=>x.value&&x.value.length>20);
                if(t){t.select();document.execCommand('copy');
                this.textContent='✓ Copied!';
                setTimeout(()=>{this.textContent='📋 Copy Text'},2000)}"
              style="background:#0068c9;color:white;border:none;padding:8px 16px;
                     border-radius:4px;cursor:pointer;font-size:14px;margin-top:4px;width:100%">
              📋 Copy Text
            </button>""",
            height=50,
        )
    else:
        st.info("No narrative generated. Enter hemodynamic values on Step 2.")

    # Step-up alerts
    if step_ups:
        st.subheader("Step-Up Detection")
        for su in step_ups:
            st.warning(
                f"⬆️ Step-up at **{su['level']}** level: "
                f"{su['from']} {su['from_sat']}% → {su['to']} {su['to_sat']}% "
                f"(Δ {su['delta']}%)"
            )
    else:
        st.success("✅ No significant O₂ saturation step-ups detected.")

    # Calculated hemodynamics table
    st.subheader("Calculated Hemodynamics")
    if calculations and not calculations.get("error"):
        table_data = []
        entries = [
            ("Cardiac Index (Qs)", calculations.get("qs"), "L/min/m²"),
            ("Pulmonary Flow (Qp)", calculations.get("qp"), "L/min/m²"),
            ("Qp:Qs", calculations.get("qp_qs"), ":1"),
            ("Mixed Venous Sat", calculations.get("mixed_venous_sat"), "%"),
            ("Mean PCWP", calculations.get("mean_pcwp"), "mmHg"),
            ("TPG", calculations.get("tpg"), "mmHg"),
            ("PVRi", calculations.get("pvri"), "iWU"),
            ("SVRi", calculations.get("svri"), "iWU"),
            ("Rp/Rs", calculations.get("rp_rs"), ""),
        ]
        for param, val, units in entries:
            if val is not None:
                table_data.append({"Parameter": param, "Value": val, "Units": units})

        if table_data:
            import pandas as pd
            df = pd.DataFrame(table_data)
            st.dataframe(df, use_container_width=True, hide_index=True)

        # Warnings
        warnings = calculations.get("warnings", [])
        if warnings:
            with st.expander("⚠️ Calculation notes"):
                for w in warnings:
                    st.caption(f"• {w}")
    else:
        st.info("Enter hemodynamic data and run calculation to see results.")

    # Patient info summary
    if patient_data:
        with st.expander("Patient Info"):
            st.write(f"**Name:** {patient_data.get('name', '—')}")
            st.write(f"**MRN:** {patient_data.get('mrn', '—')}")
            st.write(f"**Date:** {patient_data.get('doc', '—')}")
            st.write(f"**Hgb:** {patient_data.get('hgb', '—')} g/dL")
            st.write(f"**BSA:** {patient_data.get('bsa', '—')} m²")
            st.write(f"**aVO₂:** {patient_data.get('avo2', '—')} mL/min/m²")
            st.write(f"**Anesthesia:** {patient_data.get('anesthesia', '—')}")

"""
Page 1: Browse and select the anatomy diagram for the current case.
"""
import streamlit as st
from pathlib import Path
from PIL import Image

from utils.annotator import pil_to_bytes, safe_open_image
from utils.diagram_library import (
    load_library,
    get_all_categories,
    get_diagrams_for_category,
    search_diagrams,
    mark_coords_status,
    add_uploaded_diagram,
    delete_uploaded_diagram,
    ANATOMY_UPLOAD_OPTIONS,
)
from utils.styles import inject_styles

BASE_DIR = Path(__file__).parent.parent

st.set_page_config(page_title="Select Diagram", page_icon="🫀", layout="wide")
inject_styles()

# Ensure library is loaded
if "library" not in st.session_state or st.session_state.library is None:
    st.session_state.library = mark_coords_status(load_library())

library = st.session_state.library
categories = get_all_categories(library)

st.title("Step 1: Select Anatomy Diagram")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("Search")
    search_query = st.text_input("", placeholder="e.g. ASD, Glenn, Norwood...",
                                  label_visibility="collapsed")
    st.markdown("---")
    if st.button("⚙️ Setup Coordinates", use_container_width=True):
        st.switch_page("pages/4_Setup_Coordinates.py")

    # ── Upload new diagram ────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📤 Upload New Diagram")
    st.caption("Add your own diagram image to the library.")

    uploaded_file = st.file_uploader(
        "Image file",
        type=["bmp", "png", "jpg", "jpeg"],
        key="diagram_upload",
        label_visibility="collapsed",
    )

    if uploaded_file is not None:
        anatomy_choice = st.selectbox(
            "Anatomy type",
            ANATOMY_UPLOAD_OPTIONS,
            key="upload_anatomy",
            help="Choose the anatomy type, or let the app detect it from the filename.",
        )

        if st.button("Add to library", type="primary", use_container_width=True):
            with st.spinner("Saving…"):
                try:
                    st.session_state.library = add_uploaded_diagram(
                        file_bytes=uploaded_file.getvalue(),
                        filename=uploaded_file.name,
                        anatomy_override=anatomy_choice,
                    )
                    st.success(f"✅ Added **{uploaded_file.name}**")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Upload failed: {exc}")

# Currently selected
current = st.session_state.get("selected_diagram")
if current:
    st.success(f"Currently selected: **{current.get('display_name', current['id'])}**")

# ── Helper: render a grid of diagram cards ────────────────────────────────────
THUMB_SIZE = (220, 180)
COLS_PER_ROW = 3


def _render_grid(diagrams: list):
    if not diagrams:
        st.caption("No diagrams in this category yet.")
        return
    for i in range(0, len(diagrams), COLS_PER_ROW):
        cols = st.columns(COLS_PER_ROW)
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(diagrams):
                break
            diag = diagrams[idx]
            img_path = BASE_DIR / diag["path"]

            with col:
                # Thumbnail
                try:
                    img = safe_open_image(img_path)
                    img.thumbnail(THUMB_SIZE, Image.LANCZOS)
                    st.image(pil_to_bytes(img), use_container_width=True)
                except Exception as e:
                    st.caption(f"⚠️ {e}")

                # Name and badges
                is_selected = current and current["id"] == diag["id"]
                badge = "✅ " if diag.get("has_coords") else "⚠️ "
                label = "Selected ✓" if is_selected else "Select"
                btn_type = "primary" if is_selected else "secondary"

                st.caption(f"{badge}{diag['display_name']}")
                st.caption(f"*{diag['anatomy_type'].replace('_', ' ')}*")

                if st.button(label, key=f"select_{diag['id']}",
                             use_container_width=True, type=btn_type):
                    st.session_state.selected_diagram = diag
                    # Reset downstream session state
                    st.session_state.hemodynamics = {}
                    st.session_state.calculations = {}
                    st.session_state.narrative = ""
                    st.session_state.annotated_image = None
                    st.rerun()

                # Delete button for uploaded diagrams
                if diag.get("category_id") == "Uploaded":
                    if st.button("🗑 Delete", key=f"del_{diag['id']}",
                                 use_container_width=True):
                        st.session_state.library = delete_uploaded_diagram(
                            diag["id"], library
                        )
                        if current and current["id"] == diag["id"]:
                            st.session_state.selected_diagram = None
                        st.rerun()


# ── Main content: search results (flat) or folder view ───────────────────────
if search_query:
    # ── Search mode: flat grid across all categories ──────────────────────────
    results = search_diagrams(library, search_query)
    st.markdown(f"**{len(results)} diagrams** matching \"{search_query}\"")
    _render_grid(results)

else:
    # ── Folder mode: one expander per category ────────────────────────────────
    total = sum(len(cat.get("diagrams", [])) for cat in categories)
    st.markdown(f"**{total} diagrams** in {sum(1 for c in categories if c.get('diagrams'))} categories")

    for cat in categories:
        cat_diagrams = get_diagrams_for_category(library, cat["id"])
        if not cat_diagrams:
            continue

        # Auto-expand the category that contains the currently selected diagram
        has_selected = current and any(d["id"] == current["id"] for d in cat_diagrams)
        with st.expander(
            f"📁 **{cat['display_name']}** — {len(cat_diagrams)} diagram{'s' if len(cat_diagrams) != 1 else ''}",
            expanded=bool(has_selected),
        ):
            _render_grid(cat_diagrams)

st.markdown("---")
st.caption("✅ = annotation coordinates configured | ⚠️ = coordinates not yet set up (use Setup Coordinates page)")

if st.button("Next: Enter Hemodynamics →", type="primary"):
    if st.session_state.selected_diagram:
        st.switch_page("pages/2_Hemodynamic_Entry.py")
    else:
        st.error("Please select a diagram first.")

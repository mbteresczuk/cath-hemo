"""
Draggable dots custom Streamlit component.
Declared here (in a proper Python module) so inspect.getmodule()
works correctly — it fails when called from Streamlit page files.
"""
from pathlib import Path
from streamlit.components.v1 import declare_component

_COMP_DIR = Path(__file__).parent / "draggable_dots_component"

# Declared at module level in a regular importable module
draggable_dots = declare_component("draggable_dots", path=str(_COMP_DIR))

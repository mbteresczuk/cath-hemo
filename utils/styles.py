"""
Clinical Editorial theme for the Cardiac Catheterization Report Dashboard.

Call inject_styles() once per page, immediately after st.set_page_config().
"""
import streamlit as st

_GOOGLE_FONTS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,400;0,600;1,400&family=Source+Sans+3:wght@300;400;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
"""

_CSS = """
<style>
/* ── Design tokens ────────────────────────────── */
:root {
  --cath-crimson:      #8C1A30;   /* deep medical red — primary accent   */
  --cath-navy:         #1B2B3A;   /* deep navy — text, dark surfaces     */
  --cath-bg:           #F8F6F3;   /* warm off-white — page background    */
  --cath-surface:      #FFFFFF;   /* pure white — cards, inputs          */
  --cath-border:       #D5CFCA;   /* warm gray — borders, dividers       */
  --cath-muted:        #6B6560;   /* muted warm gray — secondary text    */
  --cath-data:         #2A5C8A;   /* steel blue — numeric data, links    */
  --cath-accent-light: #F5EDED;   /* light crimson tint — hover states   */
}

/* ── Base typography ──────────────────────────── */
html, body, [class*="css"] {
  font-family: 'Source Sans 3', system-ui, sans-serif !important;
  color: var(--cath-navy) !important;
}

/* ── Page background ──────────────────────────── */
[data-testid="stAppViewContainer"],
[data-testid="stMain"] {
  background-color: var(--cath-bg) !important;
}
[data-testid="stHeader"] {
  background-color: var(--cath-bg) !important;
  border-bottom: 1px solid var(--cath-border) !important;
}

/* ── Page title (h1) ──────────────────────────── */
h1 {
  font-family: 'Spectral', Georgia, serif !important;
  font-weight: 600 !important;
  font-size: 1.65rem !important;
  color: var(--cath-navy) !important;
  letter-spacing: -0.02em !important;
  padding-bottom: 0.45rem !important;
  border-bottom: 2px solid var(--cath-crimson) !important;
  margin-bottom: 1.1rem !important;
}

/* ── Section headings (h2, h3) ────────────────── */
h2, h3 {
  font-family: 'Spectral', Georgia, serif !important;
  font-weight: 600 !important;
  color: var(--cath-navy) !important;
  letter-spacing: -0.01em !important;
}

/* Subheader left-border accent */
h3 {
  padding-left: 0.65rem !important;
  border-left: 3px solid var(--cath-crimson) !important;
  line-height: 1.3 !important;
}

/* ── Text inputs ──────────────────────────────── */
input[type="text"],
input[type="number"],
input[type="email"],
input[type="password"] {
  font-family: 'JetBrains Mono', 'Courier New', monospace !important;
  font-size: 0.84rem !important;
  border-radius: 3px !important;
  border-color: var(--cath-border) !important;
  background-color: var(--cath-surface) !important;
  color: var(--cath-navy) !important;
  transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}
input[type="text"]:focus,
input[type="number"]:focus {
  border-color: var(--cath-crimson) !important;
  box-shadow: 0 0 0 2px rgba(140, 26, 48, 0.10) !important;
  outline: none !important;
}

/* ── Text areas ───────────────────────────────── */
textarea {
  font-family: 'JetBrains Mono', 'Courier New', monospace !important;
  font-size: 0.82rem !important;
  border-radius: 3px !important;
  border-color: var(--cath-border) !important;
  background-color: var(--cath-surface) !important;
  color: var(--cath-navy) !important;
  line-height: 1.65 !important;
  transition: border-color 0.15s ease, box-shadow 0.15s ease !important;
}
textarea:focus {
  border-color: var(--cath-crimson) !important;
  box-shadow: 0 0 0 2px rgba(140, 26, 48, 0.10) !important;
  outline: none !important;
}

/* ── Select / dropdown ────────────────────────── */
[data-baseweb="select"] > div {
  border-radius: 3px !important;
  border-color: var(--cath-border) !important;
  background-color: var(--cath-surface) !important;
  font-family: 'Source Sans 3', sans-serif !important;
  font-size: 0.88rem !important;
  transition: border-color 0.15s ease !important;
}
[data-baseweb="select"] > div:focus-within {
  border-color: var(--cath-crimson) !important;
  box-shadow: 0 0 0 2px rgba(140, 26, 48, 0.10) !important;
}
[data-baseweb="menu"] {
  font-family: 'Source Sans 3', sans-serif !important;
  font-size: 0.88rem !important;
  border-radius: 3px !important;
}

/* ── Primary button ───────────────────────────── */
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primary"]:link,
[data-testid="stBaseButton-primary"]:visited {
  background-color: var(--cath-crimson) !important;
  color: #FFFFFF !important;
  border: none !important;
  border-radius: 3px !important;
  font-family: 'Source Sans 3', sans-serif !important;
  font-weight: 600 !important;
  font-size: 0.9rem !important;
  letter-spacing: 0.025em !important;
  transition: background-color 0.15s ease, box-shadow 0.15s ease !important;
}
[data-testid="stBaseButton-primary"]:hover {
  background-color: #701522 !important;
  box-shadow: 0 2px 8px rgba(140, 26, 48, 0.28) !important;
}
[data-testid="stBaseButton-primary"]:disabled,
[data-testid="stBaseButton-primary"][disabled] {
  background-color: var(--cath-border) !important;
  color: var(--cath-muted) !important;
}

/* ── Secondary / default buttons ─────────────── */
[data-testid="stBaseButton-secondary"] {
  background-color: var(--cath-surface) !important;
  color: var(--cath-navy) !important;
  border: 1.5px solid var(--cath-border) !important;
  border-radius: 3px !important;
  font-family: 'Source Sans 3', sans-serif !important;
  font-weight: 400 !important;
  font-size: 0.87rem !important;
  transition: border-color 0.15s ease, background-color 0.15s ease,
              color 0.15s ease !important;
}
[data-testid="stBaseButton-secondary"]:hover {
  border-color: var(--cath-crimson) !important;
  background-color: var(--cath-accent-light) !important;
  color: var(--cath-crimson) !important;
}

/* ── Download buttons ─────────────────────────── */
[data-testid="stBaseButton-downloadButton"] {
  background-color: var(--cath-surface) !important;
  color: var(--cath-data) !important;
  border: 1.5px solid var(--cath-data) !important;
  border-radius: 3px !important;
  font-family: 'Source Sans 3', sans-serif !important;
  font-size: 0.87rem !important;
  transition: background-color 0.15s ease !important;
}
[data-testid="stBaseButton-downloadButton"]:hover {
  background-color: #EEF3FA !important;
}

/* ── Alert/notification boxes ─────────────────── */
[data-testid="stAlert"] {
  border-radius: 3px !important;
  font-family: 'Source Sans 3', sans-serif !important;
  font-size: 0.875rem !important;
}

/* ── Expanders ────────────────────────────────── */
[data-testid="stExpander"] {
  border: 1px solid var(--cath-border) !important;
  border-radius: 3px !important;
  background-color: var(--cath-surface) !important;
}
[data-testid="stExpander"] summary {
  font-family: 'Source Sans 3', sans-serif !important;
  font-weight: 600 !important;
  font-size: 0.88rem !important;
  color: var(--cath-navy) !important;
}
[data-testid="stExpander"] summary:hover {
  color: var(--cath-crimson) !important;
}

/* ── Sidebar ──────────────────────────────────── */
[data-testid="stSidebar"] {
  background-color: var(--cath-navy) !important;
}
[data-testid="stSidebar"] * {
  color: #DDD8D2 !important;
}
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
  color: #FFFFFF !important;
  border-color: rgba(255,255,255,0.3) !important;
}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"] {
  background-color: rgba(255,255,255,0.08) !important;
  border-color: rgba(255,255,255,0.2) !important;
  color: #DDD8D2 !important;
}
[data-testid="stSidebar"] [data-testid="stBaseButton-secondary"]:hover {
  background-color: rgba(255,255,255,0.15) !important;
  border-color: rgba(255,255,255,0.4) !important;
  color: #FFFFFF !important;
}

/* ── Dataframe table ──────────────────────────── */
[data-testid="stDataFrame"] {
  font-family: 'JetBrains Mono', monospace !important;
  font-size: 0.81rem !important;
}
[data-testid="stDataFrame"] th {
  font-family: 'Source Sans 3', sans-serif !important;
  font-weight: 600 !important;
  font-size: 0.80rem !important;
  letter-spacing: 0.04em !important;
  text-transform: uppercase !important;
}

/* ── Caption / helper text ────────────────────── */
.stCaption p,
[data-testid="stCaptionContainer"] p {
  font-family: 'Source Sans 3', sans-serif !important;
  font-size: 0.80rem !important;
  color: var(--cath-muted) !important;
}

/* ── Horizontal dividers ──────────────────────── */
hr {
  border: none !important;
  border-top: 1px solid var(--cath-border) !important;
  margin: 1.1rem 0 !important;
}

/* ── Main content padding ─────────────────────── */
[data-testid="stMainBlockContainer"] {
  padding-top: 1.4rem !important;
  padding-bottom: 2rem !important;
}

/* ── Radio buttons ────────────────────────────── */
[data-testid="stRadio"] label {
  font-family: 'Source Sans 3', sans-serif !important;
  font-size: 0.88rem !important;
}

/* ── Number input spinners ────────────────────── */
[data-testid="stNumberInput"] input {
  font-family: 'JetBrains Mono', monospace !important;
  font-size: 0.84rem !important;
}

/* ── Markdown strong/bold ─────────────────────── */
p strong, li strong {
  color: var(--cath-navy) !important;
  font-weight: 600 !important;
}

/* ── Labels ───────────────────────────────────── */
label, .stTextInput label, .stSelectbox label,
.stNumberInput label, .stTextArea label {
  font-family: 'Source Sans 3', sans-serif !important;
  font-size: 0.82rem !important;
  font-weight: 600 !important;
  color: var(--cath-muted) !important;
  letter-spacing: 0.02em !important;
}
</style>
"""


def inject_styles() -> None:
    """Inject the Clinical Editorial theme into the current Streamlit page.

    Call once per page, immediately after st.set_page_config().
    """
    st.markdown(_GOOGLE_FONTS + _CSS, unsafe_allow_html=True)

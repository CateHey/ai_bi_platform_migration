import sys
from pathlib import Path

# Ensure the project root is on sys.path so `from src.main import ...` works
# regardless of how this file is launched (streamlit adds src/ to path, not
# the parent, so we add the parent explicitly here).
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

CLOUD_MODE = sys.platform != "win32"

import streamlit as st
import base64
import re
import json
from datetime import datetime
from collections import defaultdict
import streamlit.components.v1 as components
import pandas as pd
import altair as alt
import tempfile
from streamlit_option_menu import option_menu
import os
from src.utils.complexity import compute_complexity
from src.utils.evaluation import run_evaluation
from src.utils.io_helpers import read_csv_flexible_encoding

if not CLOUD_MODE:
    from src.main import (
        extract_qv_metadata, check_and_rerun_if_needed,
        parse_xml, map_fields,
        report_exports,
        generate_data_source, generate_expression_to_dax,
        load_settings, initialize_azure_openai_client, transform_output_from_csv,
        upload_restructured_metadata_to_sharepoint,
        setup_logger
    )

if not CLOUD_MODE:
    app_logger = setup_logger("app_logger", "output/logs/app_ui.log")
    metadata_logger = setup_logger("metadata_logger", "output/logs/qv_metadata_automation.log")
    datasource_logger = setup_logger("datasource_logger", "output/logs/datasource_creation.log")
    report_pages_logger = setup_logger("report_pages_logger", "output/logs/qv_report_pages_logger.log")
    xml_parser_logger = setup_logger("xml_parser_logger", "output/logs/xml_parser.log")
    field_mapping_logger = setup_logger("field_mapping_logger", "output/logs/field_mapping.log")
    expression_logger = setup_logger("expression_logger", "output/logs/expression_translation.log")
    output_logger = setup_logger("output_analysis_logger", "output/logs/output_analysis.log")
    upload_logger = setup_logger("upload_logger", "output/logs/upload_sharepoint.log")

# -- Settings --
REQUIRED_SETTINGS_KEYS = [
    "DOCUMENT_ANALYZER_PATH",
    "local_folder_path",
    "root_folder_path",
    "assets_folder_path",
    "output_qv_folder_path",
    "output_qv_restructured_folder_path",
    "api_key",
    "azure_endpoint",
    "field_mapping_file_path",
]

def load_settings(settings_file="settings.json"):
    config = {}
    if os.path.exists(settings_file):
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            st.error(f"`{settings_file}` no es JSON válido: {e}")
            st.stop()
    else:
        st.error(
            f"No se encontró `{settings_file}` en la raíz del proyecto. "
            "Copia `settings.json.example` a `settings.json` y complétalo antes de ejecutar la app."
        )
        st.stop()

    missing = [k for k in REQUIRED_SETTINGS_KEYS if not config.get(k)]
    if missing:
        st.error(
            "Faltan claves en `settings.json`:\n\n- " + "\n- ".join(missing)
        )
        st.stop()

    return config

# -- Background and logo --
def set_background(png_file=None):
    """Apply a modern purple gradient background. png_file is ignored (kept for signature compat)."""
    st.markdown(
        """
        <style>
        .stApp {
            background: radial-gradient(1200px 600px at 10% -10%, #7c3aed33 0%, transparent 60%),
                        radial-gradient(900px 500px at 100% 0%, #a855f733 0%, transparent 55%),
                        linear-gradient(135deg, #0f0725 0%, #1e1147 45%, #2a1065 100%);
            background-attachment: fixed;
            color: #f5f3ff;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def add_logo(png_file):
    try:
        with open(png_file, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        img_html = (
            f'<img src="data:image/png;base64,{data}" width="180" '
            'style="display:block;margin:0 auto;" />'
        )
    except FileNotFoundError:
        img_html = (
            '<div style="font-size:22px;font-weight:700;color:#2a1065;'
            'letter-spacing:1px;">One51 VizShifter</div>'
        )
    st.sidebar.markdown(
        f'''
        <div style="
            background:#ffffff;
            border-radius:16px;
            padding:18px 14px;
            margin:4px 6px 16px 6px;
            box-shadow:0 8px 24px rgba(124,58,237,0.35),
                       0 0 0 1px rgba(168,85,247,0.35);
            text-align:center;
        ">
            {img_html}
        </div>
        ''',
        unsafe_allow_html=True,
    )

# --- App Loading ---
st.set_page_config(layout="wide", page_title="One51 VizShifter")

if CLOUD_MODE:
    settings = {
        "output_qv_restructured_folder_path": "demo_output",
        "root_folder_path": "demo_output",
        "field_mapping_file_path": "assets/mapping/field_mapping.csv",
        "assets_folder_path": "assets",
    }
else:
    settings = load_settings(str(Path("settings.json")))

# -- Apply logo and background (safe fallback if assets are missing) --
def _safe(fn, path):
    try:
        fn(path)
    except FileNotFoundError:
        st.warning(f"Asset no encontrado: `{path}`")

_safe(add_logo, "assets/ui/One51Logo.png")
_safe(set_background, "assets/ui/background_test.png")

# -- Sidebar navigation (remains the same) --
st.sidebar.title("Navigation")

with st.sidebar:
    if CLOUD_MODE:
        _menu_items = ["Pipeline Info", "DAX, M Query, Pages", "Summary Report", "Complexity Analysis", "Translation Quality", "Execution History"]
        _menu_icons = ["book", "bar-chart", "clipboard-data", "graph-up", "check2-circle", "gear"]
    else:
        _menu_items = ["Main App", "Pipeline Info", "DAX, M Query, Pages", "Summary Report", "Complexity Analysis", "Translation Quality", "Execution History", "Logs"]
        _menu_icons = ["house", "book", "bar-chart", "clipboard-data", "graph-up", "check2-circle", "gear", "journal-text"]
    selected = option_menu(
        "",
        _menu_items,
        icons=_menu_icons,
        menu_icon="cast",
        default_index=0,
        styles={
            "container": {
                "padding": "10px 8px",
                "background-color": "#1e1147",
                "border-radius": "14px",
                "border": "1px solid rgba(168,85,247,0.35)",
            },
            "icon": {"color": "#ffffff", "font-size": "18px"},
            "nav-link": {
                "font-size": "15px",
                "font-weight": "600",
                "text-align": "left",
                "margin": "6px 0",
                "padding": "12px 16px",
                "border-radius": "10px",
                "color": "#ffffff",
                "background-color": "transparent",
                "--hover-color": "#3b1e73",
            },
            "nav-link-selected": {
                "background-color": "#7c3aed",
                "color": "#ffffff",
                "font-weight": "700",
                "box-shadow": "0 6px 18px rgba(124,58,237,0.55)",
            },
        },
    )

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/icon?family=Material+Icons');
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
    @import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200');
    /* ---------- Modern purple theme ---------- */
    :root {
        --violet-50:  #f5f3ff;
        --violet-200: #e9d5ff;
        --violet-300: #c4b5fd;
        --violet-400: #a855f7;
        --violet-500: #8b5cf6;
        --violet-600: #7c3aed;
        --violet-700: #6d28d9;
        --violet-900: #2a1065;
        --ink:        #0f0725;
        --card-bg:    rgba(255,255,255,0.06);
        --card-border:rgba(168,85,247,0.22);
    }

    html, body, [class*="css"], .stApp, .stApp p, .stApp span, .stApp div, .stApp li {
        font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
        color: #f5f3ff;
    }
    .stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown span {
        color: #f5f3ff !important;
    }

    /* Headers */
    h1, h2, h3, h4, h5, h6 {
        color: #ffffff !important;
        letter-spacing: 0.2px;
        font-weight: 700 !important;
    }
    h1 {
        background: linear-gradient(90deg,#ffffff 0%,#c4b5fd 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.4rem !important;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg,#160a36 0%,#0f0725 100%) !important;
        border-right: 1px solid rgba(168,85,247,0.18);
        min-width: 280px !important;
    }
    section[data-testid="stSidebar"] > div {
        padding: 18px 14px !important;
    }
    section[data-testid="stSidebar"] h1,
    section[data-testid="stSidebar"] h2,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] span {
        color: #ffffff !important;
    }
    /* Force option_menu items to stay visible (high specificity) */
    section[data-testid="stSidebar"] .nav-link,
    section[data-testid="stSidebar"] .nav-link span,
    section[data-testid="stSidebar"] .nav-link i {
        color: #ffffff !important;
        opacity: 1 !important;
    }
    section[data-testid="stSidebar"] .nav-link:hover {
        background-color: #3b1e73 !important;
        color: #ffffff !important;
    }

    /* GLOBAL: hide any un-rendered Material Symbols ligature text anywhere
       in the app (expanders, selectboxes, etc.). The specific header rules
       below re-enable and size their own labels via ::after. */
    [data-testid="stIconMaterial"],
    span.material-symbols-rounded,
    span.material-symbols-outlined,
    span.material-symbols-sharp,
    span.material-icons,
    span.material-icons-outlined,
    span.material-icons-round {
        font-size: 0 !important;
        line-height: 0 !important;
        color: transparent !important;
    }

    /* Make sure the top header + its button container are wide enough to
       fit the "Open Menu" / "Close Menu" label without clipping. */
    header[data-testid="stHeader"] {
        min-width: 160px !important;
    }
    header[data-testid="stHeader"] button,
    header[data-testid="stHeader"] [data-testid="stBaseButton-headerNoPadding"],
    header[data-testid="stHeader"] [data-testid="stBaseButton-header"] {
        width: auto !important;
        min-width: 120px !important;
        padding: 4px 10px !important;
        overflow: visible !important;
    }
    /* Also widen the sidebar header (where Streamlit puts the close button
       when the sidebar is OPEN) so the "Close Menu" label fits. */
    [data-testid="stSidebarHeader"] {
        min-height: 48px !important;
        padding: 8px 12px !important;
    }
    [data-testid="stSidebarHeader"] button {
        width: auto !important;
        min-width: 120px !important;
        padding: 4px 10px !important;
        overflow: visible !important;
    }
    /* Scoped fix: touch Material icons inside the TOP header bar AND the
       sidebar header (both places where the collapse/expand button lives
       depending on sidebar state). Hide the ligature text and draw a plain
       ASCII "Open Menu" / "Close Menu" label in its place. */
    header[data-testid="stHeader"] [data-testid="stIconMaterial"],
    header[data-testid="stHeader"] span.material-symbols-rounded,
    header[data-testid="stHeader"] span.material-symbols-outlined,
    header[data-testid="stHeader"] span.material-icons,
    [data-testid="stSidebarHeader"] [data-testid="stIconMaterial"],
    [data-testid="stSidebarHeader"] span.material-symbols-rounded,
    [data-testid="stSidebarHeader"] span.material-symbols-outlined,
    [data-testid="stSidebarHeader"] span.material-icons {
        text-indent: -9999px !important;
        overflow: visible !important;
        display: inline-block !important;
        width: 110px !important;
        height: 28px !important;
        position: relative !important;
        vertical-align: middle !important;
    }
    header[data-testid="stHeader"] [data-testid="stIconMaterial"]::after,
    header[data-testid="stHeader"] span.material-symbols-rounded::after,
    header[data-testid="stHeader"] span.material-symbols-outlined::after,
    header[data-testid="stHeader"] span.material-icons::after,
    [data-testid="stSidebarHeader"] [data-testid="stIconMaterial"]::after,
    [data-testid="stSidebarHeader"] span.material-symbols-rounded::after,
    [data-testid="stSidebarHeader"] span.material-symbols-outlined::after,
    [data-testid="stSidebarHeader"] span.material-icons::after {
        content: "Open Menu";
        text-indent: 0 !important;
        position: absolute !important;
        left: 0 !important;
        top: 0 !important;
        width: 110px !important;
        height: 28px !important;
        line-height: 28px !important;
        font-size: 12px !important;
        white-space: nowrap !important;
        font-weight: 600 !important;
        text-align: center !important;
        color: #ffffff !important;
        background: #7c3aed !important;
        border-radius: 6px !important;
        font-family: system-ui, -apple-system, sans-serif !important;
        letter-spacing: 0.3px !important;
    }
    /* Any icon inside the sidebar header is the "Close Menu" button
       (Streamlit only renders it there when the sidebar is OPEN). */
    [data-testid="stSidebarHeader"] [data-testid="stIconMaterial"]::after,
    [data-testid="stSidebarHeader"] span.material-symbols-rounded::after,
    [data-testid="stSidebarHeader"] span.material-symbols-outlined::after,
    [data-testid="stSidebarHeader"] span.material-icons::after,
    /* Fallback: any button with a Close/Collapse aria-label. */
    button[aria-label*="Close" i] [data-testid="stIconMaterial"]::after,
    button[aria-label*="Collapse" i] [data-testid="stIconMaterial"]::after,
    button[aria-label*="Close" i] span.material-symbols-rounded::after,
    button[aria-label*="Close" i] span.material-symbols-outlined::after {
        content: "Close Menu" !important;
    }

    /* Top bar / main content padding */
    .block-container {
        padding-top: 2.5rem !important;
        padding-left: 2.5rem !important;
        padding-right: 2.5rem !important;
        padding-bottom: 2rem !important;
        max-width: 1400px;
    }
    header[data-testid="stHeader"] {
        background: rgba(15,7,37,0.6) !important;
        backdrop-filter: blur(8px);
        border-bottom: 1px solid rgba(168,85,247,0.18);
        height: 3.2rem;
    }

    /* Cards / containers */
    div[data-testid="stVerticalBlockBorderWrapper"],
    div[data-testid="stExpander"] {
        background: var(--card-bg) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 16px !important;
        backdrop-filter: blur(10px);
        box-shadow: 0 8px 32px rgba(15,7,37,0.35);
    }

    /* Buttons */
    div.stButton > button, div.stDownloadButton > button {
        background: linear-gradient(135deg,#7c3aed 0%,#a855f7 100%);
        border: 1px solid rgba(233,213,255,0.25);
        border-radius: 12px;
        color: #fff;
        font-weight: 600;
        padding: 10px 20px;
        box-shadow: 0 6px 20px rgba(124,58,237,0.35);
        transition: transform .15s ease, box-shadow .15s ease, filter .15s ease;
    }
    div.stButton > button:hover, div.stDownloadButton > button:hover {
        filter: brightness(1.1);
        transform: translateY(-1px);
        box-shadow: 0 10px 26px rgba(168,85,247,0.5);
        color: #fff;
    }
    div.stButton > button:disabled {
        opacity: 0.55;
        filter: grayscale(0.2);
    }

    /* Inputs — closed selectbox */
    .stSelectbox div[data-baseweb="select"] > div,
    .stSelectbox div[data-baseweb="select"] > div > div,
    .stTextInput > div > div,
    .stTextArea textarea {
        background-color: #1e1147 !important;
        color: #ffffff !important;
    }
    .stSelectbox div[data-baseweb="select"] * {
        color: #ffffff !important;
    }

    /* Dropdown popover (opened selectbox) */
    ul[role="listbox"],
    div[data-baseweb="menu"],
    div[data-baseweb="popover"] {
        background-color: #1e1147 !important;
    }
    li[role="option"] {
        background-color: #1e1147 !important;
        color: #ffffff !important;
    }
    li[role="option"]:hover,
    li[aria-selected="true"] {
        background-color: #7c3aed !important;
        color: #ffffff !important;
    }

    /* Dropdown popover colors only */
    ul[role="listbox"],
    div[data-baseweb="menu"] {
        background-color: #1e1147 !important;
    }
    li[role="option"] {
        background-color: #1e1147 !important;
        color: #ffffff !important;
    }
    li[role="option"]:hover,
    li[aria-selected="true"] {
        background-color: #7c3aed !important;
        color: #ffffff !important;
    }
    .stSelectbox label, .stTextInput label, .stCheckbox label,
    .stRadio label, .stMultiSelect label {
        color: #ffffff !important;
        font-weight: 600 !important;
    }
    /* Caption (used below headers) */
    .stCaption, [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] * {
        color: #d8b4fe !important;
    }

    /* Checkbox */
    .stCheckbox [data-baseweb="checkbox"] > div:first-child {
        border-color: var(--violet-400) !important;
    }

    /* Tabs */
    [data-testid="stTabs"] button {
        font-size: 15px !important;
        font-weight: 600 !important;
        color: var(--violet-200) !important;
        padding: 8px 16px !important;
        border-radius: 10px !important;
    }
    [data-testid="stTabs"] button[aria-selected="true"] {
        background: linear-gradient(135deg,#7c3aed 0%,#a855f7 100%) !important;
        color: #fff !important;
    }

    /* Expander */
    div[data-testid="stExpander"] summary {
        font-size: 16px !important;
        font-weight: 600 !important;
        color: var(--violet-50) !important;
    }
    summary:focus { outline: none !important; }

    /* Code blocks */
    code, pre, .stCode {
        background-color: rgba(15,7,37,0.55) !important;
        color: #e9d5ff !important;
        border: 1px solid var(--card-border);
        border-radius: 8px;
    }

    /* Alerts keep readable */
    div[data-testid="stAlert"] {
        border-radius: 12px !important;
        border: 1px solid var(--card-border) !important;
        background: rgba(255,255,255,0.06) !important;
        color: var(--violet-50) !important;
    }

    /* Caption */
    .stCaption, [data-testid="stCaptionContainer"] {
        color: var(--violet-300) !important;
    }

    /* Divider */
    hr { border-color: rgba(168,85,247,0.25) !important; }

    /* Status box */
    div[data-testid="stStatusWidget"] {
        background: var(--card-bg) !important;
        border: 1px solid var(--card-border) !important;
        border-radius: 14px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# -- Executions History (remains the same) --

STEP_KEY_MAPPING = {
        "Metadata Extraction": "extract_qv_metadata",
        # "PDF Generation": "report_exports",  # disabled — requires local GUI
        "XML Parsing": "parse_xml",
        "Field Mapping": "map_fields",
        "Data Source Creation": "generate_data_source",
        "Expression to DAX": "generate_expression_to_dax",
        "Output analysis": "output_analysis",
        # "Comparison QlikView vs Power BI": "comparison_qlikview_powerbi"  # Step 8 disabled
    }

def get_last_run(ui_step_name, execution_log):
    step_key = STEP_KEY_MAPPING.get(ui_step_name)
    if not step_key:
        return "Not run yet", "unknown"

    step_data = execution_log.get(step_key, {})
    return step_data.get("last_run", "Not run yet"), step_data.get("status", "unknown")

def display_log_viewer():
    st.title("Log File Viewer")
    log_files = list(Path("output/logs").glob("*.log"))
    if not log_files:
        st.warning("No logs found in output/logs directory.")
        return

    selected_log = st.selectbox("Select a log file", log_files, format_func=lambda p: p.name)

    with open(selected_log, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    log_pattern = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\w+) - (.*)")
    parsed_logs = []
    for line in lines:
        match = log_pattern.match(line)
        if match:
            raw_ts, level, message = match.groups()
            timestamp = datetime.strptime(raw_ts, "%Y-%m-%d %H:%M:%S,%f")
            parsed_logs.append({
                "Timestamp": timestamp, "Level": level, "Message": message.strip()
            })
        elif parsed_logs:
            parsed_logs[-1]["Message"] += "\n" + line.strip()

    parsed_logs.sort(key=lambda x: x["Timestamp"], reverse=True)
    st.subheader("Parsed Log Entries (Newest First)")

    for log in parsed_logs:
        level_icon = {"INFO": "✅", "WARNING": "⚠️", "ERROR": "❌", "CRITICAL": "🚨", "DEBUG": "🐞"}.get(log["Level"].upper(), "🔹")
        with st.expander(f"{level_icon} {log['Timestamp'].strftime('%Y-%m-%d %H:%M:%S')} | {log['Level']}"):
            st.code(log["Message"], language="text")

def run_pipeline(full_pipeline, steps, settings, qv_metadata_settings, output_settings,split_tabs):
    """
    # CHANGE #1: Encapsulate all execution logic in a function and use st.status.
    # This cleans up the main UI and provides a better user experience.
    """
    client = None # Initialize client here

    print(f"\n{'='*60}")
    print(f"PIPELINE START -- full_pipeline={full_pipeline}")
    print(f"   Step selections: {steps}")
    print(f"{'='*60}\n")

    with st.status("Executing pipeline...", expanded=True) as status:
        try:
            Path("output/logs").mkdir(exist_ok=True)

            execution_log_path = Path(settings["output_qv_restructured_folder_path"]) / "execution_log.json"

            # Map UI step label → key used in execution_log.json by executor.py
            STEP_LOG_KEY = {
                "Metadata Extraction": "extract_qv_metadata",
                "XML Parsing": "parse_xml",
                "Field Mapping": "map_fields",
                "Data Source Creation": "generate_data_source",
                "Expression to DAX": "generate_expression_to_dax",
                # "PDF Generation": "report_exports",  # disabled
                "Output analysis": "transform_output_from_csv",
                # "Comparison QlikView vs Power BI": "compare_qlikview_powerbi_reports",  # Step 8 disabled
            }

            def report_step_outcome(step_name, success_msg):
                """Read execution_log.json and surface per-file failures/warnings."""
                log_key = STEP_LOG_KEY.get(step_name)
                if not log_key or not execution_log_path.exists():
                    st.write(f"✅ {success_msg}")
                    return
                try:
                    with open(execution_log_path, "r", encoding="utf-8") as f:
                        all_steps = json.load(f)
                except (json.JSONDecodeError, OSError) as e:
                    st.warning(f"⚠️ {step_name} completed but couldn't read execution log: {e}")
                    return

                entry = all_steps.get(log_key)
                if not entry:
                    st.write(f"✅ {success_msg}")
                    return

                files = entry.get("files", [])
                failed = [f for f in files if f.get("status") == "failed"]
                status_val = entry.get("status", "success")

                if failed:
                    st.error(
                        f"❌ {step_name} finished with **{len(failed)} failed file(s)**:\n\n"
                        + "\n".join(f"- `{f['file']}`" for f in failed)
                        + "\n\nCheck `output/logs/` for details."
                    )
                elif status_val == "failed":
                    st.error(f"❌ {step_name} reported failure. Check `output/logs/` for details.")
                else:
                    total = len(files)
                    if total:
                        st.write(f"✅ {success_msg} ({total} file(s) processed)")
                    else:
                        st.write(f"✅ {success_msg}")

            def execute_step(step_name, condition, func, success_msg, overwrite_func=None, overwrite_msg=None, **kwargs):
                """Helper function to run a step and log its progress."""
                try:
                    should_run = (
                        condition == "Run"
                        or (full_pipeline and condition != "Skip")
                    )
                    should_overwrite = condition == "Overwrite" and overwrite_func

                    if should_overwrite:
                        st.write(f"🏃 Running {step_name} with overwrite...")
                        print(f"[{step_name}] executing with overwrite=True")
                        overwrite_func(**kwargs, overwrite_existing=True)
                        report_step_outcome(step_name, overwrite_msg)
                    elif should_run:
                        st.write(f"🏃 Running {step_name}...")
                        print(f"[{step_name}] executing")
                        func(**kwargs)
                        report_step_outcome(step_name, success_msg)
                    else:
                        print(f"[{step_name}] skipped (condition={condition}, full_pipeline={full_pipeline})")
                except Exception as step_err:
                    st.error(
                        f"❌ {step_name} crashed: `{type(step_err).__name__}: {step_err}`\n\n"
                        f"Check `output/logs/` for the full traceback."
                    )
                    raise

            # --- Execution logic (unchanged, just adapted for the status box) ---
            # Metadata
            execute_step("Metadata Extraction", steps.get("Metadata Extraction"),
                         extract_qv_metadata, "Metadata extraction done.",
                         extract_qv_metadata, "Metadata extraction with overwrite done.",
                         settings=settings, logger=metadata_logger)
            
            # XML Parsing
            execute_step("XML Parsing", steps.get("XML Parsing"),
                         parse_xml, "XML parsing done.",
                         parse_xml, "XML parsing with overwrite done.",
                         settings=settings, logger=xml_parser_logger)
            
            # Field Mapping
            execute_step("Field Mapping", steps.get("Field Mapping"),
                         map_fields, "Field mapping done.",
                         map_fields, "Field mapping with overwrite done.",
                         settings=settings, logger=field_mapping_logger)
        
            # Initialize OpenAI only if needed for the selected steps
            ai_steps = ["Data Source Creation", "Expression to DAX"]  # "Comparison QlikView vs Power BI" Step 8 disabled
            if any(steps.get(s) in ["Run", "Overwrite"] for s in ai_steps) or full_pipeline:
                 if client is None:
                    st.write(" Initialising Azure OpenAI...")
                    client = initialize_azure_openai_client(settings["api_key"], settings["azure_endpoint"])
                    st.write("✅ Azure OpenAI ready.")

            # Data Source Creation
            if client:
                execute_step("Data Source Creation", steps.get("Data Source Creation"),
                             generate_data_source, "Data source generation done.",
                             generate_data_source, "Data source generation with overwrite done.",
                             model_name="gpt-4o", client=client, settings=settings, logger=datasource_logger, split=split_tabs)
            # Expression to DAX
            if client:
                execute_step("Expression to DAX", steps.get("Expression to DAX"),
                             generate_expression_to_dax, "DAX translation done.",
                             generate_expression_to_dax, "DAX translation with overwrite done.",
                             model_name="gpt-4o", client=client, settings=settings, logger=expression_logger)
            # PDF Generation (disabled — requires local GUI automation)
            # execute_step("PDF Generation", steps.get("PDF Generation"),
            #              report_exports, "PDF generation done.",
            #              report_exports, "PDF generation with overwrite done.",
            #              settings=settings, logger=report_pages_logger)
            # Output analysis
            execute_step("Output analysis", steps.get("Output analysis"),
                         transform_output_from_csv, "Output analysis done.",
                         transform_output_from_csv, "Output analysis with overwrite done.",
                         settings=settings , logger=output_logger,)

            # Comparison QlikView vs Power BI (disabled — not ready yet)
            # execute_step("Comparison QlikView vs Power BI", steps.get("Comparison QlikView vs Power BI"),
            #              compare_qlikview_powerbi_reports, "Comparison QlikView vs Power BI done.",
            #              compare_qlikview_powerbi_reports, "Output analysis with overwrite done.",
            #              settings=settings, client=client, logger=comparison_qlikview_powerbi_logger,)
                 
        except Exception as e:
            status.update(label="❌ Execution failed!", state="error", expanded=True)
            st.error(f"An error occurred: {str(e)}")
            app_logger.error(f"Execution failed: {str(e)}", exc_info=True)

STEP_DESCRIPTIONS = {
    "Metadata Extraction": "Extract QVW metadata via DocumentAnalyzer.",
    "XML Parsing": "Parse XML into structured data.",
    "Field Mapping": "Map QlikView fields to Power BI.",
    "Data Source Creation": "Generate M queries from QVS.",
    "Expression to DAX": "Translate expressions into DAX.",
    # "PDF Generation": "Export report pages as PDF.",  # disabled — requires local GUI
    "Output analysis": "Transform CSV outputs for review.",
    # "Comparison QlikView vs Power BI": "Compare source and target reports.",
}

def display_step_selector(full_pipeline, execution_log, key_prefix=""):
    steps = {}
    split_tabs = True  # Default

    st.write(
        "Full pipeline will run every step below."
        if full_pipeline
        else "Or select individual steps to run:"
    )
    num_cols = 3
    cols = st.columns(num_cols)

    step_names = list(STEP_DESCRIPTIONS.keys())

    for i, step_name in enumerate(step_names):
        col = cols[i % num_cols]
        with col:
            last_run, status = get_last_run(step_name, execution_log)

            steps[step_name] = st.selectbox(
                step_name,
                ["Skip", "Run", "Overwrite"],
                index=1 if full_pipeline else 0,
                disabled=full_pipeline,
                key=f"{key_prefix}_{step_name.lower().replace(' ', '_')}_{'full' if full_pipeline else 'manual'}"
            )

            st.markdown(
                f"""
                <p style='
                font-family:"Segoe UI", sans-serif;
                font-size:13px;
                font-style:italic;
                color:#c4b5fd;
                margin:2px 0 10px 0;
                '>{STEP_DESCRIPTIONS[step_name]}</p>
                """,
                unsafe_allow_html=True,
            )

            status_color = {
                "success": "#86efac",
                "failed":  "#fca5a5",
                "error":   "#fca5a5",
                "unknown": "#c4b5fd",
            }.get(str(status).lower(), "#c4b5fd")

            st.markdown(
                f"""
                <div style='
                    display:flex;flex-direction:column;gap:6px;
                    background:rgba(255,255,255,0.05);
                    border:1px solid rgba(168,85,247,0.25);
                    border-radius:10px;
                    padding:10px 12px;
                    margin-bottom:8px;
                    font-family:"Segoe UI",sans-serif;
                    font-size:13px;
                '>
                    <div style='color:#e9d5ff;'>
                        <span style='opacity:0.7;'>Last Run:</span>
                        <span style='font-weight:600;'> {last_run}</span>
                    </div>
                    <div style='color:{status_color};'>
                        <span style='opacity:0.7;color:#e9d5ff;'>Status:</span>
                        <span style='font-weight:700;text-transform:capitalize;'> {status}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # Show split option only if Data Source Creation is selected or running full pipeline
    if full_pipeline or steps.get("Data Source Creation") in ("Run", "Overwrite"):
        split_tabs = st.checkbox(
            "Split QVS script by tabs (recommended)",
            value=True,
            key=f"{key_prefix}_split_tabs"
        )

    return steps, split_tabs

def load_execution_log(settings):
    base = Path(settings["output_qv_restructured_folder_path"])
    for name in ("execution_log.json", "Execution_Log.json"):
        path = base / name
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return {}

def display_pipeline_info():
    st.title("Pipeline Overview")
    st.markdown(
        "This project implements an **end-to-end automated pipeline** that migrates "
        "QlikView business intelligence reports to **Microsoft Power BI / Fabric**. "
        "It combines GUI automation, XML parsing, and LLM-based code translation (RAG) "
        "to address a real-world enterprise migration challenge."
    )

    st.subheader("Architecture")
    st.code(
        ".qvw (QlikView file)\n"
        "  |\n"
        "  +---> [Step 1] Metadata Extraction      --> XML descriptors + CSV tables\n"
        "  |       (GUI automation via pyautogui)\n"
        "  |\n"
        "  +---> [Step 2] XML Parsing              --> Flattened CSVs (one per object)\n"
        "  |       (xmltodict + recursive flatten)\n"
        "  |\n"
        "  +---> [Step 3] Field Mapping            --> Filtered attribute/value CSVs\n"
        "  |       (lookup table from field_mapping.csv)\n"
        "  |\n"
        "  +---> [Step 4] Data Source Creation      --> M Query scripts (Power Query)\n"
        "  |       (RAG + GPT-4o)\n"
        "  |\n"
        "  +---> [Step 5] Expression to DAX        --> DAX measures\n"
        "  |       (semantic model context + GPT-4o)\n"
        "  |\n"
        "  +---> [Step 6] Output Analysis          --> Unified enriched JSON\n"
        "          (multi-source data integration)",
        language=None,
    )

    st.subheader("Step-by-Step Details")

    with st.expander("Step 1 — Metadata Extraction", expanded=False):
        st.markdown(
            "**Purpose:** Extract all internal metadata from QlikView documents by driving "
            "the proprietary DocumentAnalyzer tool through GUI automation.\n\n"
            "**Techniques:**\n"
            "- GUI automation using `pyautogui` and `pygetwindow`\n"
            "- Image recognition with template matching (confidence=0.8) for button detection\n"
            "- Incremental processing via SHA-256 file hashing (only changed files are re-processed)\n"
            "- Window reuse: QlikView window stays open between files to save ~10s per file\n\n"
            "**Input:** `.qvw` files from the source directory\n\n"
            "**Output per report:** `objects.csv`, `objectSheets.csv`, `sheets.csv`, "
            "`expressions.csv`, `fields.csv`, `script.qvs`, `Document/*.xml`"
        )

    with st.expander("Step 2 — XML Parsing", expanded=False):
        st.markdown(
            "**Purpose:** Parse QlikView's internal XML object descriptors into structured, "
            "flat CSV files suitable for analysis.\n\n"
            "**Techniques:**\n"
            "- XML deserialization using `xmltodict`\n"
            "- Recursive dictionary flattening via depth-first traversal\n"
            "- Encoding detection using `chardet` (handles UTF-16, Latin-1, UTF-8)\n"
            "- Field frequency analysis with `defaultdict(set)`\n\n"
            "**Input:** XML files in `Document/` subdirectories\n\n"
            "**Output:** Per-object flat CSV (e.g. `LB01.csv`), `objects_all_fields.csv`"
        )

    with st.expander("Step 3 — Field Mapping", expanded=False):
        st.markdown(
            "**Purpose:** Filter each flattened object CSV to retain only the attributes "
            "semantically relevant for Power BI migration, using a predefined mapping table.\n\n"
            "**Techniques:**\n"
            "- Lookup table (`field_mapping.csv`, 93 entries) maps QlikView 2-char prefixes to PBI types\n"
            "- Pivot transformation: wide-format CSVs pivoted into tall-format attribute/value pairs\n\n"
            "**Mapping examples:** CH (Chart) → Visualization, LB (ListBox) → Slicer, "
            "TB (Table Box) → Table, TX (Text Object) → Text Box\n\n"
            "**Input:** Flat CSVs from Step 2 + `field_mapping.csv`\n\n"
            "**Output:** `{object}_mapped_pivoted.csv` per object"
        )

    with st.expander("Step 4 — Data Source Creation (M Query)", expanded=False):
        st.markdown(
            "**Purpose:** Translate QlikView load scripts (`.qvs`) into Power BI M Query "
            "(Power Query) code using an LLM with Retrieval-Augmented Generation.\n\n"
            "**Techniques:**\n"
            "- Script segmentation: regex-based tab splitting for parallel translation\n"
            "- **RAG**: knowledge base of QVS→M examples embedded with `text-embedding-3-small`, "
            "top-k retrieval via cosine similarity, injected as few-shot demonstrations\n"
            "- LLM translation: Azure OpenAI `gpt-4o` (temperature 0.5)\n"
            "- Post-processing: regex extraction of table blocks into `(TableName, MQueryScript)` pairs\n\n"
            "**Input:** `script.qvs` files (UTF-16)\n\n"
            "**Output:** `m_query_output.csv` — one row per Power Query table\n\n"
            "**AI significance:** Practical RAG for code translation — embedding-based retrieval "
            "provides domain-specific context that improves LLM quality over zero-shot."
        )

    with st.expander("Step 5 — Expression to DAX Translation", expanded=False):
        st.markdown(
            "**Purpose:** Translate QlikView visual expressions into DAX measures for Power BI.\n\n"
            "**Techniques:**\n"
            "- Semantic model extraction: reads `fields.csv` to build contextual schema "
            "(groups by table, infers types from QlikView tags, identifies join keys)\n"
            "- LLM translation: Azure OpenAI `gpt-4o` (temperature 0.3)\n"
            "- Rate limiting: sliding-window RPM throttle (150 req/min) with automatic backoff\n"
            "- Low-confidence translations flagged for manual review\n\n"
            "**Input:** `expressions.csv` + `fields.csv` per report\n\n"
            "**Output:** `expressions_with_dax.csv`, `DAX_output.csv`\n\n"
            "**AI significance:** LLM-based semantic understanding bridges two expression languages. "
            "The semantic model context (field types, table relationships) prevents syntactically "
            "correct but semantically wrong DAX."
        )

    with st.expander("Step 6 — Output Analysis (Structured JSON Assembly)", expanded=False):
        st.markdown(
            "**Purpose:** Synthesize all intermediate outputs from Steps 1-5 into unified, "
            "enriched JSON files for validation and Power BI report construction.\n\n"
            "**Techniques:**\n"
            "- Multi-source data integration: loads up to 9 CSV sources with pandas `merge()`\n"
            "- Graceful degradation: processes everything available even when some sources are missing\n\n"
            "**Input:** All CSV outputs from prior steps\n\n"
            "**Output:** `enriched_dax.json`, `m_query_output.json`"
        )

    st.subheader("Technologies and Libraries")
    st.table(pd.DataFrame({
        "Category": [
            "Language", "Web UI", "AI / LLM", "GUI Automation",
            "Data Processing", "Embeddings / RAG",
        ],
        "Technologies": [
            "Python 3.11+",
            "Streamlit (interactive dashboard with step selection, monitoring, results viewer)",
            "Azure OpenAI GPT-4o (chat completions), text-embedding-3-small",
            "pyautogui, pygetwindow",
            "pandas, xmltodict, chardet, csv, json",
            "OpenAI embeddings + cosine similarity (numpy)",
        ],
    }))

    st.subheader("AI / Data Science Techniques by Step")
    st.table(pd.DataFrame({
        "Step": ["1", "2", "3", "4", "5", "6"],
        "Technique": [
            "Template matching", "Recursive flattening", "Lookup table",
            "RAG + LLM", "LLM + type inference",
            "Data integration",
        ],
        "Model / Algorithm": [
            "pyautogui (OpenCV)", "Custom DFS", "Pandas merge",
            "text-embedding-3-small + GPT-4o", "GPT-4o + heuristic mapping",
            "Pandas multi-join",
        ],
        "Purpose": [
            "Resolution-independent UI element detection",
            "XML hierarchy to tabular structure",
            "QlikView to Power BI type mapping",
            "QVS script to M Query translation",
            "Expression to DAX measure translation",
            "Multi-source synthesis to enriched JSON",
        ],
    }))


def display_main_app():
    settings_path = Path("settings.json")
    if not settings_path.is_file():
        st.error("❌ settings.json not found")
        st.stop()

    settings = load_settings(str(settings_path))
    
    if "execution_log" not in st.session_state:
        st.session_state["execution_log"] = load_execution_log(settings)

    execution_log = st.session_state["execution_log"]

    st.header("One51 VizShifter")
    st.caption("QlikView to Power BI Migration Tool: A comprehensive automation pipeline that extracts metadata from QlikView dashboards, parses XML definitions, maps fields intelligently, and translates expressions into optimized DAX code for seamless migration to Microsoft Fabric and Power BI.")

    # Settings loading
    settings_path = Path("settings.json")
    if not settings_path.is_file():
        st.error("❌ settings.json not found")
        st.stop()
    settings = load_settings(str(settings_path))

    qv_metadata_settings = {
        k: settings[k]
        for k in ["DOCUMENT_ANALYZER_PATH", "root_folder_path", "output_qv_folder_path", "output_qv_restructured_folder_path"]
    }

    output_settings = {
        k: settings[k]
        for k in ["output_qv_restructured_folder_path"]
    }

    # Initialize stop flag in session state
    if "stop_requested" not in st.session_state:
        st.session_state.stop_requested = False

    # Emergency stop button
    if st.button("🛑 Stop Pipeline", type="secondary"):
        st.session_state.stop_requested = True
        st.warning("🚨 Stop requested. The pipeline will halt at the next checkpoint.")

    with st.container(border=True):
        full_pipeline = st.checkbox("Run full pipeline", value=False, help="Select this to run all steps sequentially.")
        st.session_state["execution_log"] = load_execution_log(settings)
        steps, split_tabs  = display_step_selector(full_pipeline, execution_log, key_prefix="initial")

    st.session_state["pipeline_just_ran"] = False

    # Execute pipeline button
    if st.button("Execute", type="primary", use_container_width=True):
        if not full_pipeline and all(v == "Skip" for v in steps.values()):
            st.warning("No steps selected to run. Please select at least one step or choose 'Run full pipeline'.")
        else:
            run_pipeline(full_pipeline, steps, settings, qv_metadata_settings, output_settings,split_tabs)
            st.session_state["pipeline_just_ran"] = True
            st.session_state["execution_log"] = load_execution_log(settings)
             # 🔁 Reload execution log after pipeline runs
        
    # Optional reset button to clear stop flag
    if st.session_state.get("stop_requested"):
        st.markdown("---")
        if st.button("🔄 Reset Stop Flag"):
            st.session_state.stop_requested = False
            st.success("Stop flag cleared. You may now run the pipeline again.")
    
    # Display feedback after run
    if st.session_state.get("pipeline_just_ran") == True:
        if st.button("🔄 Refresh Status Panel"):
            st.session_state["execution_log"] = load_execution_log(settings)
            st.rerun()
    
    # ------------------------------
    # ✅ Completely independent SharePoint upload section
    # ------------------------------
    st.markdown("---")
    st.header("Upload Structured Output to SharePoint")
    st.caption("Open SharePoint in your browser, press F12 → Refresh the page → go to Network > Select one line > Cookies > copy values of FedAuth and rtFa.")
    st.markdown("[Open SharePoint Folder](https://one51comau.sharepoint.com/Shared%20Documents/Forms/AllItems.aspx?id=%2FShared%20Documents%2FMigrationQlikFabric&viewid=48196aad%2Db820%2D4d8e%2Dac62%2D1e40e7e4f731)", unsafe_allow_html=True)

    with st.expander("Enter SharePoint cookies (manual upload)"):
        fedauth_manual = st.text_input("FedAuth", type="password", key="fedauth_manual")
        rtfa_manual = st.text_input("rtFa", type="password", key="rtfa_manual")

    if st.button("Upload to SharePoint", type="primary"):
        if fedauth_manual and rtfa_manual:
            cookies = {
                "FedAuth": fedauth_manual.strip().replace(" ", ""),
                "rtFa": rtfa_manual.strip().replace(" ", "")
            }

            st.write("📤 Uploading restructured output to SharePoint...")
            success = upload_restructured_metadata_to_sharepoint(settings, cookies, upload_logger)

            if success:
                st.success("Files uploaded to SharePoint successfully.")
            else:
                st.error("Upload failed. Check logs.")
        else:
            st.warning("Please enter both FedAuth and rtFa cookies to proceed.")

def display_results():
    st.title("Analysis Results for QlikView to Power BI Migration")

    output_root = Path(settings.get("output_qv_restructured_folder_path", ""))

    if not output_root.exists():
        st.error("❌ Output path not found.")
        return

    if CLOUD_MODE:
        report_folders = sorted([
            d for d in output_root.iterdir()
            if d.is_dir() and (d / "Outputanalysis").exists()
        ])
    else:
        input_folder = Path(settings.get("root_folder_path", ""))
        if not input_folder.exists():
            st.error("❌ Input root path is invalid.")
            return
        qvw_files = sorted(input_folder.glob("*.qvw"))
        if not qvw_files:
            st.warning("⚠️ No QVW files found.")
            return
        report_folders = [output_root / qvw_file.stem for qvw_file in qvw_files]

    if not report_folders:
        st.warning("⚠️ No analysis results found.")
        return

    for folder in report_folders:
        qvw_name = folder.name
        analysis_folder = folder / "Outputanalysis"
        output_restructured_folder = folder

        if not analysis_folder.exists():
            st.warning(f"⚠️ No analysis found for `{qvw_name}`.")
            continue

        # Outer collapsible section per file
        with st.expander(f"📁 Analysis: {qvw_name}", expanded=False):
            dax_tab, m_tab = st.tabs(["DAX Expressions", "M Queries per Table"])

            with dax_tab:
                dax_path = output_restructured_folder / "DAX_output.csv"
                if dax_path.exists():
                    df = pd.read_csv(dax_path, header=None)
                    lines = df[0].dropna().tolist()
                    joined_text = "\n\n".join(lines)
                    st.code(joined_text, language="powerquery")
                else:
                    st.warning("DAX_output.csv not found. Run Step 5 first.")

            with m_tab:
                m_query_path = analysis_folder / "m_query_output.json"
                if m_query_path.exists():
                    with open(m_query_path, "r", encoding="utf-8") as f:
                        m_queries = json.load(f)

                    for entry in m_queries:
                        table = entry.get("TableName", "")
                        query = entry.get("MQueryScript", "")
                        with st.expander(f"{table}", expanded=False):
                            st.code(query, language="powerquery")
                else:
                    st.warning("m_query_output.json not found. Run Step 7 first.")

def display_report():
    st.title("Summary Report")

    output_root = Path(settings.get("output_qv_restructured_folder_path", ""))
    if not output_root.exists():
        st.error("Output path not found.")
        return

    if CLOUD_MODE:
        report_folders = sorted([
            d for d in output_root.iterdir()
            if d.is_dir() and (d / "fields.csv").exists()
        ])
    else:
        input_folder = Path(settings.get("root_folder_path", ""))
        if not input_folder.exists():
            st.error("Input root path is invalid.")
            return
        qvw_files = sorted(input_folder.glob("*.qvw"))
        report_folders = [output_root / qvw_file.stem for qvw_file in qvw_files]

    if not report_folders:
        st.warning("No report data found. Run the pipeline first.")
        return

    def _load(folder, filename):
        path = folder / filename
        if not path.exists():
            return None
        df = read_csv_flexible_encoding(path)
        df.columns = df.columns.str.strip()
        for col in df.select_dtypes(include="object").columns:
            df[col] = df[col].astype(str).str.strip()
        return df

    def _hbar(df, x, y, title, color="#7c3aed"):
        bars = alt.Chart(df).mark_bar(
            color=color, cornerRadiusEnd=4
        ).encode(
            x=alt.X(f"{x}:Q", title=None),
            y=alt.Y(f"{y}:N", sort="-x", title=None),
        )
        labels = bars.mark_text(
            align="left", dx=4, color="#c4b5fd", fontSize=13, fontWeight="bold"
        ).encode(text=f"{x}:Q")
        return (bars + labels).properties(
            title=alt.TitleParams(text=title, color="#e9d5ff", fontSize=16, anchor="start"),
            height=max(len(df) * 32, 120),
        ).configure_view(strokeWidth=0).configure(
            background="transparent",
        ).configure_axis(
            labelColor="#c4b5fd", titleColor="#c4b5fd", gridColor="#2a1065",
            labelFontSize=13,
        )

    OBJ_LABELS = {
        1: "Filter / Dropdown", 2: "Static Box", 3: "Multi-select Filter",
        4: "Data Table", 5: "Input Box", 6: "Active Selection",
        7: "Gauge", 10: "Chart", 11: "Pivot Table", 12: "Data Table",
        13: "Stacked Chart", 19: "Button", 20: "Text Label", 21: "Slider",
    }

    TAG_LABELS = {
        "key": "Key (joins tables)", "numeric": "Numeric",
        "integer": "Integer", "date": "Date", "text": "Text",
        "ascii": "ASCII Text", "timestamp": "Timestamp",
        "hidden": "Hidden", "system": "System",
    }

    INVENTORY = [
        ("Visual Components",    "objects.csv",        "Charts, tables, filters and buttons found in the report"),
        ("Data Fields",          "fields.csv",         "Columns and measures used across all data sources"),
        ("Calculated Formulas",  "expressions.csv",    "Business logic expressions that were translated to DAX"),
        ("Report Pages",         "sheets.csv",         "Individual pages/tabs within the original report"),
        ("Filter Dimensions",    "dimensions.csv",     "Fields used as interactive filters for the user"),
        ("Data Tables",          "m_query_output.csv",  "Source tables converted into Power Query (M) scripts"),
    ]

    all_metrics = []
    all_fields = {}
    all_tables = {}

    for folder in report_folders:
        if not folder.exists():
            continue

        qvw_name = folder.name
        dfs = {}
        counts = {}
        descs = {}
        for label, fname, desc in INVENTORY:
            df = _load(folder, fname)
            dfs[label] = df
            counts[label] = len(df) if df is not None else 0
            descs[label] = desc
            all_metrics.append({"Report": qvw_name, "Category": label, "Count": counts[label]})

        fdf = dfs.get("Data Fields")
        if fdf is not None and "FieldName" in fdf.columns:
            for fn in fdf["FieldName"].dropna().unique():
                all_fields.setdefault(fn, set()).add(qvw_name)
        tdf = dfs.get("Data Tables")
        if tdf is not None and "TableName" in tdf.columns:
            for tn in tdf["TableName"].dropna().unique():
                all_tables.setdefault(tn, set()).add(qvw_name)

        with st.expander(f"{qvw_name}", expanded=True):

            st.caption(
                "Overview of everything the pipeline extracted and translated from "
                "the original QlikView report into Power BI-ready artefacts."
            )

            # --- Key metrics as big numbers ---
            cols = st.columns(len(INVENTORY))
            for i, (label, _, desc) in enumerate(INVENTORY):
                cols[i].metric(label, counts[label], help=desc)

            st.markdown("---")

            # --- What was found: horizontal bar ---
            inv_df = pd.DataFrame([
                {"Category": k, "Count": v} for k, v in counts.items() if v > 0
            ])
            if not inv_df.empty:
                st.altair_chart(
                    _hbar(inv_df, "Count", "Category", "What the pipeline extracted"),
                    use_container_width=True,
                )

            col_left, col_right = st.columns(2)

            # --- Types of visual components ---
            objects_df = dfs.get("Visual Components")
            if objects_df is not None and "ObjectType" in objects_df.columns:
                with col_left:
                    type_col = pd.to_numeric(objects_df["ObjectType"], errors="coerce").dropna().astype(int)
                    type_named = type_col.map(lambda v: OBJ_LABELS.get(v, "Other"))
                    type_counts = type_named.value_counts().reset_index()
                    type_counts.columns = ["Component", "Count"]
                    st.altair_chart(
                        _hbar(type_counts, "Count", "Component", "Types of visual components", color="#a855f7"),
                        use_container_width=True,
                    )

            # --- Data field types ---
            fields_df = dfs.get("Data Fields")
            if fields_df is not None and "FieldTags" in fields_df.columns:
                with col_right:
                    tags = fields_df["FieldTags"].dropna()
                    all_tags = []
                    for t in tags:
                        all_tags.extend([x.strip("$ ") for x in t.split(";") if x.strip()])
                    if all_tags:
                        tag_series = pd.Series(all_tags).map(lambda v: TAG_LABELS.get(v, "Other")).value_counts().reset_index()
                        tag_series.columns = ["Field Type", "Count"]
                        st.altair_chart(
                            _hbar(tag_series, "Count", "Field Type", "Data field classification", color="#a855f7"),
                            use_container_width=True,
                        )

            # --- Formulas per component ---
            expr_df_raw = dfs.get("Calculated Formulas")
            if expr_df_raw is not None and "ObjectId" in expr_df_raw.columns:
                expr_counts = expr_df_raw["ObjectId"].value_counts().head(12).reset_index()
                expr_counts.columns = ["Component", "Formulas"]
                if objects_df is not None and "ObjectId" in objects_df.columns:
                    caption_map = objects_df.set_index("ObjectId")["Caption"].to_dict()
                    expr_counts["Component"] = expr_counts["Component"].map(
                        lambda x: caption_map.get(x, x) if caption_map.get(x, "nan") != "nan" else x
                    )
                st.altair_chart(
                    _hbar(expr_counts, "Formulas", "Component", "Formulas translated per component (top 12)"),
                    use_container_width=True,
                )

    # --- Cross-report comparison ---
    existing = [f for f in report_folders if f.exists()]
    if len(existing) > 1:
        st.markdown("---")
        st.subheader("Comparison across reports")
        st.caption("Side-by-side view of migration scope for each report processed by the pipeline.")
        cmp_df = pd.DataFrame(all_metrics)
        palette = ["#7c3aed", "#a855f7", "#c084fc", "#e9d5ff", "#6d28d9", "#8b5cf6"]
        chart = alt.Chart(cmp_df).mark_bar(cornerRadiusEnd=4).encode(
            x=alt.X("Count:Q", title=None),
            y=alt.Y("Category:N", sort="-x", title=None),
            color=alt.Color("Report:N", scale=alt.Scale(range=palette),
                            legend=alt.Legend(title="Report", labelColor="#c4b5fd", titleColor="#c4b5fd")),
            yOffset="Report:N",
        ).properties(height=350).configure_view(strokeWidth=0).configure(
            background="transparent",
        ).configure_axis(
            labelColor="#c4b5fd", titleColor="#c4b5fd", gridColor="#2a1065", labelFontSize=13,
        )
        st.altair_chart(chart, use_container_width=True)

    # --- Combined Data Landscape ---
    if all_tables or all_fields:
        st.markdown("---")
        st.subheader("Combined Data Landscape")
        st.caption(
            "All data tables and fields found across every report, "
            "showing which ones are shared between reports."
        )
        n_reports = len([f for f in report_folders if f.exists()])

        tab_tables, tab_fields = st.tabs(["Data Tables", "Data Fields"])

        with tab_tables:
            if all_tables:
                t_rows = []
                for name, reports in sorted(all_tables.items()):
                    t_rows.append({
                        "Table": name,
                        "Appears in": len(reports),
                        "Reports": ", ".join(sorted(reports)),
                        "Shared": "Yes" if len(reports) > 1 else "No",
                    })
                t_df = pd.DataFrame(t_rows)
                shared_t = t_df[t_df["Shared"] == "Yes"]
                c1, c2, c3 = st.columns(3)
                c1.metric("Total tables", len(t_df))
                c2.metric("Shared across reports", len(shared_t))
                c3.metric("Unique to one report", len(t_df) - len(shared_t))
                st.dataframe(
                    t_df.sort_values("Appears in", ascending=False),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.info("No table data available.")

        with tab_fields:
            if all_fields:
                f_rows = []
                for name, reports in sorted(all_fields.items()):
                    f_rows.append({
                        "Field": name,
                        "Appears in": len(reports),
                        "Reports": ", ".join(sorted(reports)),
                        "Shared": "Yes" if len(reports) > 1 else "No",
                    })
                f_df = pd.DataFrame(f_rows)
                shared_f = f_df[f_df["Shared"] == "Yes"]
                c1, c2, c3 = st.columns(3)
                c1.metric("Total fields", len(f_df))
                c2.metric("Shared across reports", len(shared_f))
                c3.metric("Unique to one report", len(f_df) - len(shared_f))
                if n_reports > 1 and not shared_f.empty:
                    st.altair_chart(
                        _hbar(
                            shared_f.sort_values("Appears in", ascending=False).head(20),
                            "Appears in", "Field",
                            "Most shared fields across reports",
                            color="#a855f7",
                        ),
                        use_container_width=True,
                    )
                st.dataframe(
                    f_df.sort_values("Appears in", ascending=False),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.info("No field data available.")

    # --- Pipeline Execution Summary ---
    log = load_execution_log(settings)
    if log:
        st.markdown("---")
        st.subheader("Pipeline Execution Summary")
        rows = []
        for step_key, step_data in log.items():
            rows.append({
                "Step": step_key,
                "Status": step_data.get("status", "unknown"),
                "Duration (s)": round(step_data.get("duration_sec", 0), 1),
                "Last Run": step_data.get("last_run", "N/A"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

def display_executions():
    st.title("Executions Summary")
    log = load_execution_log(settings)

    if not log:
        st.warning("⚠️ No execution log found.")
        return

    for step_key, step_data in log.items():
        with st.expander(f"**Step:** `{step_key}` **— Status:** `{step_data.get('status', 'unknown')}`", expanded=False):
            st.markdown(f"**Last Run:** `{step_data.get('last_run', 'N/A')}`  \n"
                        f"**Status:** `{step_data.get('status', 'N/A')}`  \n"
                        f"**Duration (s):** `{step_data.get('duration_sec', 0)}`")

            files = step_data.get("files", [])
            if files:
                df = pd.DataFrame(files)
                st.dataframe(df)
            else:
                st.info("No file-level data recorded for this step.")

def render_report_pages(report_pages_path, report_pages_dir=None):
    image_paths = []

    # Try JSON first, then fall back to reading PNGs directly from ReportPages/
    if report_pages_path.exists():
        with open(report_pages_path, "r", encoding="utf-8") as f:
            image_paths = json.load(f)
    elif report_pages_dir and report_pages_dir.exists():
        image_paths = sorted([str(p) for p in report_pages_dir.glob("*.png")])

    if not image_paths:
        st.warning("⚠️ No report page images found. Run PDF Generation (Step 6) and Output Analysis (Step 7).")
        return

    for img_path_str in image_paths:
        img_path = Path(img_path_str)
        if not img_path.exists():
            st.warning(f"⚠️ Image not found: {img_path}")
            continue

        filename = img_path.stem
        readable_name = filename.split("_", 1)[-1] if "_" in filename else filename
        readable_name = readable_name.replace("-", " ").replace("_", " ").title()

        st.markdown(f"### {readable_name}")
        st.image(str(img_path), use_container_width=True)
        st.markdown("---")

def render_upload_qvw_page():

    st.subheader("🔐 Provide SharePoint Cookies")
    fedauth = st.text_input("FedAuth", type="password")
    rtfa = st.text_input("rtFa", type="password")

    if not fedauth or not rtfa:
        st.warning("Please enter both FedAuth and rtFa cookies.")
        return

    uploaded_file = st.file_uploader("Choose a QVW file", type=["qvw"])

    if uploaded_file:
        st.success(f"📄 Selected file: {uploaded_file.name}")

        cookies = {"FedAuth": fedauth, "rtFa": rtfa}
        file_bytes = uploaded_file.read()
        filename = uploaded_file.name

        # NEW method that uploads from stream + preserves filename
        success = upload_qvw_stream_to_sharepoint(file_bytes, filename, cookies, upload_logger)

        if success:
            st.success("✅ File uploaded to SharePoint.")
        else:
            st.error("❌ Upload failed.")

# Comparison QlikView and Power BI

# ====================================
# Step 8 — Comparison/Validation (disabled temporarily)
# ====================================
# def load_comparison_results(base_path):
#     """Load all comparison results from the directory structure"""
#     base_dir = Path(base_path)
#     if not base_dir.exists():
#         return {}
#     results = {}
#     for report_folder in base_dir.iterdir():
#         if not report_folder.is_dir():
#             continue
#         report_name = report_folder.name
#         results[report_name] = {}
#         for json_file in report_folder.glob("*comparison.json"):
#             try:
#                 with open(json_file, 'r', encoding='utf-8') as f:
#                     data = json.load(f)
#                     page_key = data.get('page', json_file.stem)
#                     results[report_name][page_key] = data
#             except Exception as e:
#                 st.warning(f"Error loading {json_file}: {str(e)}")
#     return results
#
# def _wrap(s: str, width: int = 28) -> str:
#     return "<br>".join(textwrap.wrap(s, width=width)) if s else s
    
# def create_summary_chart(all_results):  # Step 8 disabled
# def display_page_details(page_data):    # Step 8 disabled
# def display_migration_comparison():     # Step 8 disabled
# (All comparison/validation display functions commented out — re-enable when Step 8 is ready)

def display_complexity_analysis():
    st.title("Migration Complexity Analysis")
    st.caption(
        "Quantitative complexity scoring based on feature extraction across four dimensions: "
        "Data Model, Expressions, Script structure, and Layout density. "
        "Features are normalised using predefined reference ranges and combined via weighted scoring."
    )

    output_root = Path(settings.get("output_qv_restructured_folder_path", ""))
    if not output_root.exists():
        st.error("Output path not found.")
        return

    if CLOUD_MODE:
        report_folders = sorted([
            d for d in output_root.iterdir()
            if d.is_dir() and (d / "fields.csv").exists()
        ])
    else:
        input_folder = Path(settings.get("root_folder_path", ""))
        if not input_folder.exists():
            st.error("Input root path is invalid.")
            return
        qvw_files = sorted(input_folder.glob("*.qvw"))
        report_folders = [output_root / qvw_file.stem for qvw_file in qvw_files]

    if not report_folders:
        st.warning("No report data found. Run the pipeline first.")
        return

    for folder in report_folders:
        if not folder.exists():
            continue

        qvw_name = folder.name
        with st.expander(f"Analysis: {qvw_name}", expanded=True):
            result = compute_complexity(folder)

            if result is None:
                st.warning(f"Insufficient data for complexity analysis in {qvw_name}.")
                continue

            score = result["overall_score"]
            classification = result["classification"]
            effort_min, effort_max = result["effort_days"]

            badge_colors = {
                "Low": "#22c55e", "Medium": "#eab308",
                "High": "#f97316", "Critical": "#ef4444",
            }
            badge_color = badge_colors.get(classification, "#8b5cf6")
            st.markdown(
                f'<div style="display:inline-block;padding:6px 18px;border-radius:8px;'
                f'background:{badge_color};color:#fff;font-weight:700;font-size:18px;'
                f'margin-bottom:12px;">{classification} Complexity</div>',
                unsafe_allow_html=True,
            )

            col1, col2, col3 = st.columns(3)
            col1.metric("Overall Score", f"{score:.1f} / 100")
            col2.metric("Classification", classification)
            col3.metric("Estimated Effort", f"{effort_min}–{effort_max} person-days")

            st.markdown("---")

            st.subheader("Dimension Scores")
            dim_cols = st.columns(4)
            cat_labels = ["Data Model", "Expressions", "Script", "Layout"]
            cat_weights = ["(30%)", "(25%)", "(25%)", "(20%)"]
            for i, label in enumerate(cat_labels):
                dim_cols[i].metric(
                    f"{label} {cat_weights[i]}",
                    f"{result['category_scores'][label]:.1f}",
                )

            st.subheader("Dimension Score Distribution")
            chart_df = pd.DataFrame({
                "Dimension": list(result["category_scores"].keys()),
                "Score": list(result["category_scores"].values()),
            }).set_index("Dimension")
            st.bar_chart(chart_df)

            st.subheader("Feature Breakdown")
            tab_dm, tab_expr, tab_scr, tab_lay = st.tabs(
                ["Data Model", "Expressions", "Script", "Layout"]
            )

            categories = [
                (tab_dm, "data_model", "Data Model"),
                (tab_expr, "expressions", "Expressions"),
                (tab_scr, "script", "Script"),
                (tab_lay, "layout", "Layout"),
            ]
            for tab, key, label in categories:
                with tab:
                    raw = result["raw_features"].get(key, {})
                    norm = result["normalized_features"].get(key, {})
                    rows = []
                    for feat_name in raw:
                        rows.append({
                            "Feature": feat_name.replace("_", " ").title(),
                            "Raw Value": raw[feat_name],
                            "Normalised (0-1)": round(norm.get(feat_name, 0), 3),
                        })
                    if rows:
                        st.dataframe(pd.DataFrame(rows), use_container_width=True)

                    if norm:
                        norm_df = pd.DataFrame({
                            "Feature": [k.replace("_", " ").title() for k in norm],
                            "Normalised Score": list(norm.values()),
                        }).set_index("Feature")
                        st.bar_chart(norm_df)

            st.subheader("Migration Recommendations")
            for rec in result["recommendations"]:
                st.markdown(f"- {rec}")

            with st.expander("Methodology", expanded=False):
                st.markdown(
                    "**Feature Engineering:** 27 features extracted from 7 data sources "
                    "across four analytical dimensions.\n\n"
                    "**Normalisation:** Min-max scaling with predefined reference ranges "
                    "(not data-dependent) to enable single-report scoring.\n\n"
                    "**Scoring:** Two-level weighted aggregation — features within each dimension "
                    "are combined using intra-category weights, then dimensions are combined "
                    "using inter-category weights (Data Model 30%, Expressions 25%, Script 25%, Layout 20%).\n\n"
                    "**Classification:** Score ranges — Low (0-25), Medium (25-50), High (50-75), Critical (75-100).\n\n"
                    "**Effort Estimation:** Based on industry benchmarks for QlikView-to-Power BI migration "
                    "projects, calibrated per complexity tier."
                )

def display_translation_quality():
    st.title("Translation Quality Evaluation")
    st.caption(
        "Quantitative evaluation of LLM-generated DAX and M Query translations "
        "against human-validated gold-standard references using BLEU, token-level "
        "precision/recall/F1, normalised edit similarity, and structural analysis."
    )

    output_root = Path(settings.get("output_qv_restructured_folder_path", ""))
    if not output_root.exists():
        st.error("Output path not found.")
        return

    if CLOUD_MODE:
        report_folders = sorted([
            d for d in output_root.iterdir()
            if d.is_dir() and (d / "expressions_with_dax.csv").exists()
        ])
    else:
        input_folder = Path(settings.get("root_folder_path", ""))
        if not input_folder.exists():
            st.error("Input root path is invalid.")
            return
        qvw_files = sorted(input_folder.glob("*.qvw"))
        report_folders = [output_root / qvw_file.stem for qvw_file in qvw_files]

    if not report_folders:
        st.warning("No report data found. Run the pipeline first (Steps 4-5).")
        return

    for folder in report_folders:
        if not folder.exists():
            continue

        result = run_evaluation(folder, _PROJECT_ROOT)
        if result is None:
            st.warning(f"No gold standard available for {folder.name}.")
            continue

        qvw_name = result["report_name"]
        s = result["summary"]

        with st.expander(f"Evaluation: {qvw_name}", expanded=True):

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("BLEU Score", f"{s['bleu']['mean']:.3f}")
            col2.metric("Token F1", f"{s['token_f1']['mean']:.3f}")
            col3.metric("Edit Similarity", f"{s['edit_similarity']['mean']:.3f}")
            col4.metric("Structural Match", f"{s['structural_similarity']['mean']:.3f}")

            st.markdown("---")

            mcol1, mcol2, mcol3 = st.columns(3)
            mcol1.metric("Total Evaluated", s["total_translations"])
            mcol2.metric("Exact Matches", f"{s['exact_matches']} ({s['exact_match_rate']*100:.0f}%)")
            mcol3.metric("DAX / M Query", f"{s['dax_count']} / {s['m_query_count']}")

            st.subheader("Quality Distribution")
            dist = s["quality_distribution"]
            dist_df = pd.DataFrame({
                "Quality Tier": list(dist.keys()),
                "Count": list(dist.values()),
            }).set_index("Quality Tier")
            st.bar_chart(dist_df)

            st.subheader("Metric Summary (mean +/- std)")
            stats_df = pd.DataFrame({
                "Metric": ["BLEU-4", "Token F1", "Edit Similarity", "Structural Similarity"],
                "Mean": [
                    s["bleu"]["mean"], s["token_f1"]["mean"],
                    s["edit_similarity"]["mean"], s["structural_similarity"]["mean"],
                ],
                "Std": [
                    s["bleu"]["std"], s["token_f1"]["std"],
                    s["edit_similarity"]["std"], s["structural_similarity"]["std"],
                ],
                "Min": [
                    s["bleu"]["min"], s["token_f1"]["min"],
                    s["edit_similarity"]["min"], s["structural_similarity"]["min"],
                ],
                "Max": [
                    s["bleu"]["max"], s["token_f1"]["max"],
                    s["edit_similarity"]["max"], s["structural_similarity"]["max"],
                ],
            })
            st.dataframe(stats_df, use_container_width=True)

            st.subheader("Per-Translation Results")
            tab_dax, tab_mq = st.tabs(["DAX Expressions", "M Query Tables"])

            with tab_dax:
                for r in result["dax_results"]:
                    m = r["metrics"]
                    badge_html = (
                        f'<span style="padding:3px 10px;border-radius:6px;'
                        f'background:{r["quality_color"]};color:#fff;'
                        f'font-weight:700;font-size:13px;">{r["quality"]}</span>'
                    )
                    with st.expander(f'{r["id"]} — {r["object_id"]} | BLEU {m["bleu"]["bleu"]:.3f}'):
                        st.markdown(badge_html, unsafe_allow_html=True)
                        st.markdown(f"**QlikView:** `{r['qlikview_expression']}`")
                        st.code(f"Reference:  {r['reference']}\nGenerated:  {r['generated']}", language="dax")
                        dcol1, dcol2, dcol3, dcol4 = st.columns(4)
                        dcol1.metric("BLEU-4", f"{m['bleu']['bleu']:.3f}")
                        dcol2.metric("Token F1", f"{m['token_metrics']['f1']:.3f}")
                        dcol3.metric("Edit Sim", f"{m['edit_similarity']:.3f}")
                        dcol4.metric("Struct Sim", f"{m['structural']['structural_similarity']:.3f}")
                        if "name_match" in m["structural"]:
                            scol1, scol2, scol3 = st.columns(3)
                            scol1.metric("Name Match", f"{m['structural']['name_match']:.0f}")
                            scol2.metric("Function Match", f"{m['structural']['function_match']:.2f}")
                            scol3.metric("Reference Match", f"{m['structural']['reference_match']:.2f}")

            with tab_mq:
                for r in result["m_query_results"]:
                    m = r["metrics"]
                    badge_html = (
                        f'<span style="padding:3px 10px;border-radius:6px;'
                        f'background:{r["quality_color"]};color:#fff;'
                        f'font-weight:700;font-size:13px;">{r["quality"]}</span>'
                    )
                    with st.expander(f'{r["id"]} — {r["table_name"]} | BLEU {m["bleu"]["bleu"]:.3f}'):
                        st.markdown(badge_html, unsafe_allow_html=True)
                        st.code(r["reference"], language="powerquery")
                        st.markdown("**Generated:**")
                        st.code(r["generated"], language="powerquery")
                        dcol1, dcol2, dcol3, dcol4 = st.columns(4)
                        dcol1.metric("BLEU-4", f"{m['bleu']['bleu']:.3f}")
                        dcol2.metric("Token F1", f"{m['token_metrics']['f1']:.3f}")
                        dcol3.metric("Edit Sim", f"{m['edit_similarity']:.3f}")
                        dcol4.metric("Struct Sim", f"{m['structural']['structural_similarity']:.3f}")
                        if "source_match" in m["structural"]:
                            scol1, scol2, scol3 = st.columns(3)
                            scol1.metric("Source Match", f"{m['structural']['source_match']:.2f}")
                            scol2.metric("Operation Match", f"{m['structural']['operation_match']:.2f}")
                            scol3.metric("Column Match", f"{m['structural']['column_match']:.2f}")

            with st.expander("Methodology", expanded=False):
                st.markdown(
                    "**BLEU-4:** Measures n-gram overlap (1-gram through 4-gram) between "
                    "reference and generated code, with brevity penalty for shorter outputs. "
                    "Standard machine translation metric adapted for code (Papineni et al., 2002).\n\n"
                    "**Token F1:** Precision, recall, and F1 computed on the multi-set of code tokens. "
                    "Captures whether the correct identifiers, functions, and operators are present.\n\n"
                    "**Edit Similarity:** 1 minus the normalised Levenshtein distance on tokenised code. "
                    "Measures character-level similarity after tokenisation.\n\n"
                    "**Structural Similarity:** Domain-specific analysis:\n"
                    "- *DAX:* Decomposes into measure name, DAX functions, and table[column] references. "
                    "Weighted combination (name 20%, functions 40%, references 40%).\n"
                    "- *M Query:* Decomposes into data sources, table operations, and column definitions. "
                    "Weighted Jaccard similarity (sources 30%, operations 30%, columns 40%).\n\n"
                    "**Quality Classification:** Composite score = 0.3*BLEU + 0.3*F1 + 0.4*Structural. "
                    "Thresholds: Exact Match (identical after normalisation), "
                    "High Quality (>= 0.85), Acceptable (>= 0.65), Needs Review (>= 0.40), Poor (< 0.40).\n\n"
                    "**Gold Standard:** 16 translations (8 DAX + 8 M Query) manually validated "
                    "by a Power BI expert. DAX references verified against fields.csv metadata. "
                    "M Query scripts validated for structural equivalence to QlikView LOAD statements."
                )


# Router logic
if selected == "Main App":
    display_main_app()
elif selected == "Pipeline Info":
    display_pipeline_info()
elif selected == "DAX, M Query, Pages":
    display_results()
elif selected == "Summary Report":
    display_report()
elif selected == "Complexity Analysis":
    display_complexity_analysis()
elif selected == "Translation Quality":
    display_translation_quality()
elif selected == "Execution History":
    display_executions()
elif selected == "Logs":
    display_log_viewer()

"""
app/main.py
-----------
ממשק Streamlit — נקודת הכניסה לאפליקציה.

פיצ'רים:
  1. העלאת קבצים (PDF / תמונות)
  2. עיבוד עם GPT-4o Vision
  3. תצוגת טופס לצד שדות — רואים את הטופס המקורי ליד הנתונים
  4. מצב "בדיקה מהירה" — מציג רק שורות עם בעיות
  5. משפט סיכום עם זמן עיבוד
  6. תיקון ידני + ייצוא לאקסל
"""

from __future__ import annotations

import sys
import os
import io
import time
from pathlib import Path
from typing import Any

import streamlit as st
import pandas as pd

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipeline import process_multiple_files
from app.exporter import export_to_excel
from app.confidence_handler import FieldStatus, count_issues
from config.fields import FIELDS
from utils.file_utils import save_temp_file, delete_temp_file, is_supported_file
from utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# הגדרות דף
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="מטפסי התחייבות → אקסל",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Assistant:wght@300;400;500;600;700&display=swap');

    /* ══ בסיס ══ */
    * { font-family: 'Assistant', -apple-system, sans-serif !important; }
    html, body, .main, .stApp { 
        direction: rtl; 
        background: linear-gradient(to bottom, #f0f4f8 0%, #ffffff 100%);
        color: #1a202c; 
    }
    .block-container { 
        max-width: 1200px !important; 
        padding: 2rem 2rem 3rem 2rem !important; 
    }

    /* ══ כותרת ראשית ══ */
    h1 { 
        font-size: 36px !important; 
        font-weight: 300 !important; 
        color: #1a202c !important; 
        margin: 0 !important;
        letter-spacing: -0.5px !important;
    }
    .stCaption { 
        color: #718096 !important; 
        font-size: 15px !important; 
        font-weight: 400 !important;
        margin-bottom: 2.5rem !important;
    }

    /* ══ סרגל צד ══ */
    [data-testid="stSidebar"] { 
        background: #ffffff !important; 
        border-left: 1px solid #e2e8f0 !important; 
        padding-top: 2rem !important; 
    }
    [data-testid="stSidebar"] h2 { 
        font-size: 15px !important; 
        font-weight: 600 !important; 
        color: #2d3748 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
        margin-bottom: 1.5rem !important;
    }
    [data-testid="stSidebar"] .stButton > button {
        background: #ffffff !important;
        border: 1px solid #cbd5e0 !important;
        color: #2d3748 !important;
        border-radius: 6px !important;
        font-size: 14px !important;
        font-weight: 500 !important;
        height: 40px !important;
        transition: all 0.15s !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background: #f7fafc !important;
        border-color: #4299e1 !important;
    }

    /* ══ כפתורים ראשיים ══ */
    .stButton > button {
        border-radius: 6px !important;
        font-size: 15px !important;
        font-weight: 500 !important;
        height: 48px !important;
        padding: 0 32px !important;
        border: none !important;
        transition: all 0.15s !important;
        letter-spacing: 0.2px !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #4299e1 0%, #3182ce 100%) !important;
        color: white !important;
        box-shadow: 0 2px 4px rgba(66, 153, 225, 0.3) !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #3182ce 0%, #2c5aa0 100%) !important;
        transform: translateY(-1px) !important;
        box-shadow: 0 4px 8px rgba(66, 153, 225, 0.4) !important;
    }
    .stButton > button[kind="secondary"] {
        background: white !important;
        color: #2d3748 !important;
        border: 1px solid #cbd5e0 !important;
    }
    .stButton > button[kind="secondary"]:hover {
        background: #f7fafc !important;
        border-color: #4299e1 !important;
    }

    /* ══ כפתור הורדה ══ */
    .stDownloadButton > button {
        background: linear-gradient(135deg, #48bb78 0%, #38a169 100%) !important;
        color: white !important;
        border-radius: 6px !important;
        font-size: 15px !important;
        font-weight: 500 !important;
        transition: all 0.15s !important;
        box-shadow: 0 2px 4px rgba(72, 187, 120, 0.3) !important;
    }
    .stDownloadButton > button:hover {
        background: linear-gradient(135deg, #38a169 0%, #2f855a 100%) !important;
        box-shadow: 0 4px 8px rgba(72, 187, 120, 0.4) !important;
    }

    /* ══ מטריקות ══ */
    [data-testid="stMetric"] {
        background: white !important;
        border-radius: 8px !important;
        padding: 24px !important;
        border: 1px solid #e2e8f0 !important;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05) !important;
    }
    [data-testid="stMetricValue"] { 
        font-size: 36px !important; 
        font-weight: 300 !important; 
        color: #4299e1 !important; 
    }
    [data-testid="stMetricLabel"] { 
        font-size: 13px !important; 
        color: #718096 !important; 
        text-transform: uppercase !important;
        letter-spacing: 0.5px !important;
        font-weight: 500 !important;
    }

    /* ══ באנר סיכום ══ */
    .summary-banner {
        background: linear-gradient(135deg, #e6f2ff 0%, #cfe5ff 100%);
        border: 1px solid #bee3f8;
        color: #2c5aa0;
        padding: 24px 32px;
        border-radius: 8px;
        font-size: 16px;
        font-weight: 400;
        text-align: center;
        margin: 32px 0;
    }

    /* ══ כרטיסי שדות ══ */
    .field-card {
        background: white;
        border-radius: 8px;
        padding: 20px;
        margin: 16px 0;
        border-left: 3px solid #e2e8f0;
        border: 1px solid #e2e8f0;
        transition: all 0.15s;
    }
    .field-card:hover { 
        border-color: #cbd5e0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }
    .field-ok      { border-left: 3px solid #48bb78 !important; }
    .field-low     { border-left: 3px solid #ed8936 !important; }
    .field-missing { border-left: 3px solid #f56565 !important; }

    /* ══ תגיות סטטוס ══ */
    .status-ok      { color: #48bb78; font-weight: 500; }
    .status-low     { color: #ed8936; font-weight: 500; }
    .status-missing { color: #f56565; font-weight: 500; }
    .status-error   { color: #718096; font-weight: 500; }

    /* ══ file uploader ══ */
    [data-testid="stFileUploader"] {
        background: white;
        border: 2px dashed #cbd5e0;
        border-radius: 8px;
        padding: 48px 24px;
    }
    [data-testid="stFileUploader"]:hover {
        border-color: #4299e1;
    }

    /* ══ expander ══ */
    [data-testid="stExpander"] {
        background: white !important;
        border: 1px solid #e2e8f0 !important;
        border-radius: 8px !important;
    }

    /* ══ divider ══ */
    hr { 
        border-color: #e2e8f0 !important; 
        margin: 32px 0 !important; 
        opacity: 1 !important; 
    }

    /* ══ הודעות ══ */
    .stSuccess {
        background: #f0fff4 !important;
        border: 1px solid #9ae6b4 !important;
        border-radius: 8px !important;
        color: #22543d !important;
    }
    .stWarning {
        background: #fffaf0 !important;
        border: 1px solid #fbd38d !important;
        border-radius: 8px !important;
        color: #7c2d12 !important;
    }
    .stError {
        background: #fff5f5 !important;
        border: 1px solid #fc8181 !important;
        border-radius: 8px !important;
        color: #742a2a !important;
    }
    .stInfo {
        background: #ebf8ff !important;
        border: 1px solid #90cdf4 !important;
        border-radius: 8px !important;
        color: #2c5aa0 !important;
    }

    /* ══ inputs - תיקון טקסט לבן ══ */
    .stTextInput > div > div, .stSelectbox > div > div {
        border-radius: 6px !important;
        border-color: #cbd5e0 !important;
        background: white !important;
    }
    .stTextInput input, .stSelectbox input {
        color: #1a202c !important;
        background: white !important;
    }
    .stTextInput > div > div:focus-within, .stSelectbox > div > div:focus-within {
        border-color: #4299e1 !important;
    }
    
    /* תיקון ספציפי לשדות עריכה */
    input[type="text"] {
        color: #1a202c !important;
        background-color: #ffffff !important;
    }
    
    /* label של input */
    .stTextInput label {
        color: #2d3748 !important;
        font-weight: 500 !important;
    }

    /* ══ selectbox ══ */
    .stSelectbox label {
        font-size: 13px !important;
        font-weight: 500 !important;
        color: #2d3748 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.3px !important;
    }

    /* ══ progress bar ══ */
    .stProgress > div > div > div { 
        background: linear-gradient(90deg, #4299e1, #3182ce) !important; 
        border-radius: 4px !important; 
    }

    /* ══ הסתרת אלמנטים מיותרים ══ */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Session State
# ─────────────────────────────────────────────────────────────────────────────

def _init_state() -> None:
    defaults = {
        "forms":            [],
        "form_images":      {},    # {index: base64_image_string} לתצוגה
        "processing":       False,
        "excel_bytes":      None,
        "excel_filename":   "",
        "error_msg":        "",
        "processing_time":  0.0,   # זמן עיבוד בשניות
        "quick_review":     False, # מצב בדיקה מהירה
        "selected_form":    0,     # טופס נבחר לתצוגה
        "ai_provider":      "gemini",  # ספק AI: openai, gemini, anthropic
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ─────────────────────────────────────────────────────────────────────────────
# ממשק ראשי
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    _init_state()

    # כותרת עם לוגו
    col_title, col_logo = st.columns([11, 1])
    
    with col_title:
        st.markdown("""
        <div style="display: flex; align-items: center; gap: 20px; margin-bottom: 0;">
            <h1 style="margin: 0; padding: 0;">מטפסי התחייבות → אקסל</h1>
        </div>
        """, unsafe_allow_html=True)
    
    with col_logo:
        logo_path = Path(__file__).parent.parent / "assets" / "logo.png"
        if logo_path.exists():
            st.image(str(logo_path), width=80)
    
    # תצוגת המודל הנוכחי
    provider_names = {
        "gemini": "Google Gemini 3.6 Flash",
        "openai": "OpenAI GPT-4o", 
        "anthropic": "Anthropic Claude 3 Opus",
    }
    current_model = provider_names.get(st.session_state.ai_provider, "Gemini")
    
    st.caption(f"חילוץ אוטומטי עם {current_model} • המעבדה המרכזית לנגיפים")
    st.divider()

    _render_sidebar()

    if not st.session_state.forms:
        _render_upload_section()
    else:
        _render_results_section()


# ─────────────────────────────────────────────────────────────────────────────
# סרגל צד
# ─────────────────────────────────────────────────────────────────────────────

def _render_sidebar() -> None:
    with st.sidebar:
        st.header("הגדרות")

        # ══════════════════════════════════════════════════════════════════
        # בחירת מודל AI
        # ══════════════════════════════════════════════════════════════════
        st.subheader("מודל AI")
        
        provider_options = {
            "gemini": "Google Gemini 3.6 Flash",
            "openai": "OpenAI GPT-4o",
            "anthropic": "Anthropic Claude 3 Opus",
        }
        
        selected_provider = st.selectbox(
            "בחרי ספק AI:",
            options=list(provider_options.keys()),
            format_func=lambda x: provider_options[x],
            index=list(provider_options.keys()).index(st.session_state.ai_provider),
            key="provider_selector",
        )
        
        if selected_provider != st.session_state.ai_provider:
            st.session_state.ai_provider = selected_provider
            st.rerun()

        # בדיקת API keys
        provider_key_map = {
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }
        
        current_key = provider_key_map[st.session_state.ai_provider]
        api_key = os.getenv(current_key, "")
        
        if api_key:
            st.success(f"{current_key} מוגדר")
        else:
            st.error(f"{current_key} חסר")
            st.info(f"הוסיפי ל-Secrets:\n```\n{current_key} = \"...\"\n```")

        st.divider()

        if st.session_state.forms:
            if st.button("טפסים חדשים", use_container_width=True):
                for key in ["forms", "form_images", "excel_bytes",
                            "excel_filename", "error_msg", "processing_time"]:
                    st.session_state[key] = {} if key == "form_images" else \
                                            [] if key == "forms" else \
                                            0.0 if key == "processing_time" else \
                                            None if key in ("excel_bytes",) else ""
                st.session_state.quick_review = False
                st.session_state.selected_form = 0
                st.rerun()

        st.divider()

        st.subheader("מקרא")
        st.markdown("""
        <span class="status-ok">תקין</span><br><br>
        <span class="status-low">לא בטוח</span><br><br>
        <span class="status-missing">חסר</span>
        """, unsafe_allow_html=True)

        st.divider()
        st.caption("משרד הבריאות • 2026")


# ─────────────────────────────────────────────────────────────────────────────
# העלאה ועיבוד
# ─────────────────────────────────────────────────────────────────────────────

def _render_upload_section() -> None:
    st.subheader("העלאת טפסים")
    uploaded_files = st.file_uploader(
        label="גרור טפסים לכאן או לחץ לבחירה",
        type=["pdf", "jpg", "jpeg", "png", "tiff", "bmp"],
        accept_multiple_files=True,
        help="PDF סרוק, צילום טלפון, תמונה",
    )

    if st.session_state.error_msg:
        st.error(st.session_state.error_msg)

    if uploaded_files:
        st.info(f"נבחרו {len(uploaded_files)} קבצים")
        if st.button("עבד טפסים", type="primary", use_container_width=True,
                     disabled=st.session_state.processing):
            _run_processing(uploaded_files)
    else:
        st.markdown("---")
        st.caption("ניתן לגרור מספר קבצים בבת אחת. כל דף PDF יעובד בנפרד.")


def _run_processing(uploaded_files) -> None:
    st.session_state.processing = True
    st.session_state.error_msg  = ""
    temp_paths: list[Path] = []

    provider_names = {
        "gemini": "Google Gemini 3.6 Flash",
        "openai": "OpenAI GPT-4o",
        "anthropic": "Anthropic Claude 3 Opus",
    }

    try:
        valid_paths: list[Path] = []
        original_names: dict[str, str] = {}  # temp_path → שם מקורי

        for uf in uploaded_files:
            if not is_supported_file(uf.name):
                st.warning(f"פורמט לא נתמך: {uf.name} — מדולג")
                continue
            suffix = Path(uf.name).suffix
            tmp = save_temp_file(uf.read(), suffix)
            tmp_named = tmp.rename(tmp.parent / f"{tmp.stem}_{uf.name}")
            temp_paths.append(tmp_named)
            valid_paths.append(tmp_named)

        if not valid_paths:
            st.error("לא נמצאו קבצים תקינים לעיבוד")
            return

        progress_bar = st.progress(0, text="מתחיל עיבוד...")
        status_text  = st.empty()

        def update_progress(current: int, total: int, message: str) -> None:
            if total > 0:
                progress_bar.progress(int((current / total) * 100), text=message)
            status_text.caption(message)

        # מדידת זמן עיבוד
        start_time = time.time()

        with st.spinner(f"מעבד טפסים עם {provider_names.get(st.session_state.ai_provider, 'AI')}..."):
            forms = process_multiple_files(
                valid_paths, 
                update_progress,
                ai_provider=st.session_state.ai_provider
            )

        elapsed = time.time() - start_time

        progress_bar.progress(100, text="✓ עיבוד הושלם")
        status_text.empty()

        if forms:
            # שמירת תמונות הטפסים לתצוגה לצד השדות
            form_images = _load_form_images(valid_paths, len(forms))

            st.session_state.forms           = forms
            st.session_state.form_images     = form_images
            st.session_state.processing_time = elapsed
            st.rerun()
        else:
            st.session_state.error_msg = "לא חולצו טפסים. בדקי שהקבצים תקינים."

    except EnvironmentError as e:
        st.session_state.error_msg = f"❌ {e}"
    except Exception as e:
        st.session_state.error_msg = f"❌ שגיאה בעיבוד: {e}"
        logger.error(f"שגיאת עיבוד: {e}", exc_info=True)
    finally:
        for p in temp_paths:
            delete_temp_file(p)
        st.session_state.processing = False


def _load_form_images(file_paths: list[Path], expected_count: int) -> dict[int, bytes]:
    """
    טוען את תמונות הטפסים לזיכרון לתצוגה בממשק.
    מחזיר dict: {form_index: image_bytes}
    """
    from app.pdf_handler import load_input_file
    from app.image_processor import resize_if_needed
    import io as _io

    images: dict[int, bytes] = {}
    form_idx = 0

    for file_path in file_paths:
        try:
            pages = load_input_file(file_path)
            for page in pages:
                if form_idx >= expected_count:
                    break
                # resize לתצוגה — לא צריך full resolution
                thumb = resize_if_needed(page, max_dim=800)
                buf = _io.BytesIO()
                thumb.save(buf, format="JPEG", quality=75)
                images[form_idx] = buf.getvalue()
                form_idx += 1
        except Exception as e:
            logger.debug(f"לא ניתן לטעון תמונה לתצוגה: {e}")
            form_idx += 1

    return images


# ─────────────────────────────────────────────────────────────────────────────
# תוצאות
# ─────────────────────────────────────────────────────────────────────────────

def _render_results_section() -> None:
    forms = st.session_state.forms

    # ── 1. משפט סיכום ────────────────────────────────────────────────────
    _render_processing_summary(forms)
    st.divider()

    # ── 2. מצב בדיקה מהירה / תצוגה מלאה ─────────────────────────────────
    col_mode1, col_mode2, col_mode3 = st.columns([1, 1, 2])
    with col_mode1:
        if st.button("בדיקה מהירה — רק בעיות",
                     type="primary" if st.session_state.quick_review else "secondary",
                     use_container_width=True):
            st.session_state.quick_review = True
            st.rerun()
    with col_mode2:
        if st.button("הצג הכל",
                     type="primary" if not st.session_state.quick_review else "secondary",
                     use_container_width=True):
            st.session_state.quick_review = False
            st.rerun()

    # סינון לפי מצב
    if st.session_state.quick_review:
        display_forms  = [(i, f) for i, f in enumerate(forms)
                          if _form_has_status(f, FieldStatus.LOW)
                          or _form_has_status(f, FieldStatus.MISSING)
                          or _form_has_status(f, FieldStatus.ERROR)]
        issues_count = len(display_forms)
        if issues_count == 0:
            st.success("✅ כל הטפסים תקינים! אין בעיות לבדיקה.")
            st.session_state.quick_review = False
        else:
            st.warning(f"מציג {issues_count} טפסים הדורשים בדיקה מתוך {len(forms)}")
    else:
        display_forms = list(enumerate(forms))

    st.divider()

    # ── 3. תצוגת טופס לצד שדות ───────────────────────────────────────────
    if display_forms:
        _render_form_with_preview(display_forms, forms)

    st.divider()

    # ── 4. טבלה מלאה לעריכה ──────────────────────────────────────────────
    with st.expander("טבלה מלאה לעריכה וייצוא", expanded=True):
        edited_forms = _render_editable_table(forms)
        st.session_state.forms = edited_forms

    st.divider()

    # ── 5. ייצוא ─────────────────────────────────────────────────────────
    _render_export_section(st.session_state.forms)


# ─────────────────────────────────────────────────────────────────────────────
# פיצ'ר 1: משפט סיכום עם זמן עיבוד
# ─────────────────────────────────────────────────────────────────────────────

def _render_processing_summary(forms: list[dict]) -> None:
    """
    מציג משפט סיכום אחד עם כל המידע החשוב:
    כמה טפסים, כמה תקינים, כמה דורשים בדיקה, זמן עיבוד.
    """
    total      = len(forms)
    ok_count   = sum(1 for f in forms if _form_all_ok(f))
    low_count  = sum(1 for f in forms if _form_has_status(f, FieldStatus.LOW))
    miss_count = sum(1 for f in forms if _form_has_status(f, FieldStatus.MISSING))
    elapsed    = st.session_state.processing_time

    # בניית משפט סיכום
    issues = low_count + miss_count
    if issues == 0:
        status_text = "כולם תקינים"
    else:
        parts = []
        if low_count > 0:
            parts.append(f"{low_count} דורשים בדיקה")
        if miss_count > 0:
            parts.append(f"{miss_count} עם שדות חסרים")
        status_text = ", ".join(parts)

    # פורמט זמן
    if elapsed < 60:
        time_str = f"{elapsed:.0f} שניות"
    else:
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        time_str = f"{mins} דקות {secs} שניות"

    summary = (
        f"עובדו {total} טפסים · "
        f"{ok_count} תקינים · "
        f"{status_text} · "
        f"זמן עיבוד: {time_str}"
    )

    st.markdown(f'<div class="summary-banner">{summary}</div>', unsafe_allow_html=True)

    # מטריקות מהירות
    cols = st.columns(4)
    cols[0].metric("סה\"כ טפסים",       total)
    cols[1].metric("תקינים לחלוטין",    ok_count)
    cols[2].metric("דורשים בדיקה",      low_count)
    cols[3].metric("שדות חסרים",        miss_count)


# ─────────────────────────────────────────────────────────────────────────────
# פיצ'ר 2: תצוגת טופס לצד שדות
# ─────────────────────────────────────────────────────────────────────────────

def _render_form_with_preview(
    display_forms: list[tuple[int, dict]],
    all_forms: list[dict],
) -> None:
    """
    מציג בורר טפסים + תמונת הטופס המקורי לצד השדות שחולצו.
    """
    st.subheader("צפייה בטופס לצד השדות")

    # בורר טופס
    form_labels = []
    for orig_idx, form in display_forms:
        src   = form.get("source_file", f"טופס {orig_idx+1}")
        page  = form.get("page", 1)
        issues = count_issues(form)
        has_issue = issues.get("low", 0) + issues.get("missing", 0) > 0
        icon  = "!" if has_issue else ""
        # קצר את שם הקובץ
        short_name = src[:30] + "..." if len(src) > 30 else src
        form_labels.append(f"{icon} דף {page} — {short_name}")

    selected_label = st.selectbox(
        "בחרי טופס לצפייה:",
        options=form_labels,
        index=min(st.session_state.selected_form, len(form_labels) - 1),
        key="form_selector",
    )
    selected_pos = form_labels.index(selected_label)
    st.session_state.selected_form = selected_pos

    orig_idx, selected_form = display_forms[selected_pos]

    # תצוגה דו-עמודית: תמונה | שדות
    col_img, col_fields = st.columns([1, 1])

    # עמודה שמאל — תמונת הטופס המקורי
    with col_img:
        st.markdown("**טופס מקורי**")
        img_bytes = st.session_state.form_images.get(orig_idx)
        if img_bytes:
            st.image(img_bytes, use_column_width=True, caption=f"דף {selected_form.get('page', 1)}")
        else:
            st.info("תמונה לא זמינה")

    # עמודה ימין — שדות מחולצים
    with col_fields:
        st.markdown("**שדות שחולצו**")
        _render_field_cards(selected_form, orig_idx, all_forms)


def _render_field_cards(form: dict, form_idx: int, all_forms: list[dict]) -> None:
    """
    מציג כרטיס לכל שדה עם צבע לפי סטטוס ואפשרות עריכה.
    """
    for field_key, field_def in FIELDS.items():
        field_data = form.get(field_key, {})
        if not isinstance(field_data, dict):
            field_data = {}

        value      = field_data.get("value")
        status     = field_data.get("status", FieldStatus.MISSING)
        confidence = field_data.get("confidence", 0.0)

        # ערך לתצוגה
        if isinstance(value, list):
            display_val = ", ".join(str(v) for v in value if v)
        else:
            display_val = str(value) if value is not None else ""

        # CSS class לפי סטטוס
        if status == FieldStatus.OK:
            css_class = "field-ok"
            icon = ""
        elif status == FieldStatus.LOW:
            css_class = "field-low"
            icon = ""
        elif status == FieldStatus.MISSING:
            css_class = "field-missing"
            icon = ""
        else:
            css_class = "field-missing"
            icon = ""

        col_name = field_def["excel_col"]

        # תצוגת הכרטיס
        st.markdown(
            f'<div class="field-card {css_class}">'
            f'<small><b>{col_name}</b> '
            f'<span style="color:#9ca3af;font-size:11px">({confidence:.0%})</span></small><br>'
            f'{display_val if display_val else "<i style=\'color:#9ca3af\'>לא נמצא</i>"}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # אם שדה לא תקין — מציגים תיבת עריכה
        if status in (FieldStatus.LOW, FieldStatus.MISSING, FieldStatus.ERROR):
            new_val = st.text_input(
                label     = f"תיקון: {col_name}",
                value     = display_val,
                key       = f"fix_{form_idx}_{field_key}",
                placeholder = f"הכניסי ערך לשדה {col_name}",
                help      = f"ערוך את השדה {col_name} ידנית",
            )
            # אם שונה — מעדכנים
            if new_val != display_val:
                field_def_data = FIELDS[field_key]
                if field_def_data["multi"]:
                    updated_val: Any = [v.strip() for v in new_val.split(",") if v.strip()]
                else:
                    updated_val = new_val.strip() if new_val.strip() else None

                all_forms[form_idx][field_key] = {
                    "value":      updated_val,
                    "confidence": 1.0,
                    "status":     FieldStatus.OK,
                }
                st.session_state.forms = all_forms


# ─────────────────────────────────────────────────────────────────────────────
# טבלה לעריכה
# ─────────────────────────────────────────────────────────────────────────────

def _render_editable_table(forms: list[dict]) -> list[dict]:
    df, field_col_map = _forms_to_dataframe(forms)
    column_config = _build_column_config(df.columns.tolist())

    edited_df = st.data_editor(
        df,
        column_config    = column_config,
        use_container_width = True,
        hide_index       = True,
        num_rows         = "fixed",
        key              = "forms_editor",
    )

    return _dataframe_to_forms(edited_df, forms, field_col_map)


def _forms_to_dataframe(forms: list[dict]) -> tuple[pd.DataFrame, dict]:
    rows: list[dict] = []
    field_col_map: dict[str, str] = {}

    for form in forms:
        row: dict[str, Any] = {
            "קובץ": form.get("source_file", ""),
            "דף":   form.get("page", 1),
        }
        for field_key, field_def in FIELDS.items():
            col_name = field_def["excel_col"]
            field_col_map[col_name] = field_key

            field_data = form.get(field_key, {})
            if not isinstance(field_data, dict):
                field_data = {}

            value  = field_data.get("value")
            status = field_data.get("status", FieldStatus.MISSING)

            if isinstance(value, list):
                display_val = ", ".join(str(v) for v in value if v)
            else:
                display_val = str(value) if value is not None else ""

            row[col_name] = display_val
            row[f"_status_{col_name}"] = status.value if isinstance(status, FieldStatus) else str(status)

        rows.append(row)

    return pd.DataFrame(rows), field_col_map


def _build_column_config(columns: list[str]) -> dict:
    config = {
        "קובץ": st.column_config.TextColumn("קובץ מקור", disabled=True, width="medium"),
        "דף":   st.column_config.NumberColumn("דף",       disabled=True, width="small"),
    }
    for field_key, field_def in FIELDS.items():
        col_name = field_def["excel_col"]
        config[col_name] = st.column_config.TextColumn(
            label=col_name, width="medium", help="ערוך ידנית אם נדרש תיקון"
        )
        config[f"_status_{col_name}"] = st.column_config.Column(
            label=f"סטטוס {col_name}", width="small"
        )
    return config


def _dataframe_to_forms(
    edited_df:      pd.DataFrame,
    original_forms: list[dict],
    field_col_map:  dict[str, str],
) -> list[dict]:
    updated: list[dict] = []

    for row_idx, row in edited_df.iterrows():
        if row_idx >= len(original_forms):
            break
        orig = original_forms[row_idx].copy()

        for col_name, field_key in field_col_map.items():
            if col_name not in row:
                continue
            new_val_str = str(row[col_name]).strip() if pd.notna(row[col_name]) else ""

            orig_data    = orig.get(field_key, {})
            orig_val_raw = orig_data.get("value") if isinstance(orig_data, dict) else None

            if isinstance(orig_val_raw, list):
                orig_display = ", ".join(str(v) for v in orig_val_raw if v)
            else:
                orig_display = str(orig_val_raw) if orig_val_raw is not None else ""

            if new_val_str != orig_display:
                field_def = FIELDS[field_key]
                if field_def["multi"]:
                    new_val: Any = [v.strip() for v in new_val_str.split(",") if v.strip()]
                else:
                    new_val = new_val_str if new_val_str else None

                orig[field_key] = {
                    "value":      new_val,
                    "confidence": 1.0,
                    "status":     FieldStatus.OK,
                }

        updated.append(orig)

    return updated


# ─────────────────────────────────────────────────────────────────────────────
# ייצוא
# ─────────────────────────────────────────────────────────────────────────────

def _render_export_section(forms: list[dict]) -> None:
    st.subheader("ייצוא לאקסל")
    col1, col2 = st.columns([1, 2])

    with col1:
        if st.button("צור קובץ אקסל", type="primary", use_container_width=True):
            try:
                with st.spinner("יוצר קובץ אקסל..."):
                    output_path = export_to_excel(forms)
                with open(output_path, "rb") as f:
                    st.session_state.excel_bytes    = f.read()
                    st.session_state.excel_filename = output_path.name
                st.rerun()
            except Exception as e:
                st.error(f"שגיאה ביצירת האקסל: {e}")

    with col2:
        if st.session_state.excel_bytes:
            st.download_button(
                label     = "הורד אקסל",
                data      = st.session_state.excel_bytes,
                file_name = st.session_state.excel_filename,
                mime      = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width = True,
            )
            st.success(f"קובץ מוכן: {st.session_state.excel_filename}")


# ─────────────────────────────────────────────────────────────────────────────
# עזר
# ─────────────────────────────────────────────────────────────────────────────

def _form_all_ok(form: dict) -> bool:
    for field_key in FIELDS:
        field_data = form.get(field_key)
        if not isinstance(field_data, dict):
            return False
        if field_data.get("status") != FieldStatus.OK:
            return False
    return True


def _form_has_status(form: dict, target: FieldStatus) -> bool:
    for field_key in FIELDS:
        field_data = form.get(field_key)
        if not isinstance(field_data, dict):
            continue
        if field_data.get("status") == target:
            return True
    return False


if __name__ == "__main__":
    main()

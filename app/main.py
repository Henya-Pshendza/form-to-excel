"""
app/main.py
-----------
ממשק Streamlit — נקודת הכניסה לאפליקציה.

הרצה:
    streamlit run app/main.py

זרימת המשתמש:
  1. העלאת קבצים (PDF / תמונות)
  2. לחיצה על "עבד טפסים"
  3. צפייה בטבלה עם השדות + סימון צבע
  4. תיקון שדות לא-בטוחים ישירות בטבלה
  5. לחיצה על "ייצא לאקסל" + הורדה
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import Any

import streamlit as st
import pandas as pd

# ── הוספת תיקיית הפרויקט ל-PYTHONPATH כדי שה-imports יעבדו ──────────────
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.pipeline import process_multiple_files
from app.exporter import export_to_excel
from app.confidence_handler import FieldStatus, STATUS_COLORS, STATUS_LABELS, count_issues
from config.fields import FIELDS
from utils.file_utils import save_temp_file, delete_temp_file, is_supported_file
from utils.logger import get_logger

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# הגדרות דף
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="מטפסי התחייבות לאקסל",
    page_icon="🧪",
    layout="wide",
    initial_sidebar_state="expanded",
)

# CSS מותאם — RTL, צבעי סטטוס, עיצוב כללי
st.markdown("""
<style>
    /* RTL לכל האפליקציה */
    .main, .stApp, .block-container {
        direction: rtl;
        text-align: right;
    }
    /* כותרות */
    h1, h2, h3, h4 { font-family: 'Segoe UI', Arial, sans-serif; }

    /* תאי טבלה לפי סטטוס */
    .status-ok      { background-color: #d4edda; padding: 4px 8px; border-radius: 4px; }
    .status-low     { background-color: #fff3cd; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .status-missing { background-color: #f8d7da; padding: 4px 8px; border-radius: 4px; font-weight: bold; }
    .status-error   { background-color: #e2e3e5; padding: 4px 8px; border-radius: 4px; }

    /* כרטיסי סיכום */
    .summary-card {
        background: #f8f9fa;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
        border: 1px solid #dee2e6;
    }
    /* כפתור ייצוא */
    .stDownloadButton > button {
        background-color: #28a745;
        color: white;
        font-size: 16px;
        padding: 10px 24px;
        border-radius: 8px;
        border: none;
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Session State — שמירת מצב בין interactions
# ─────────────────────────────────────────────────────────────────────────────

def _init_state() -> None:
    """מאתחל את session_state אם זו הפעלה ראשונה."""
    defaults = {
        "forms":          [],      # רשימת טפסים מעובדים
        "processing":     False,   # האם עיבוד פעיל כרגע
        "excel_bytes":    None,    # bytes של קובץ האקסל לייצוא
        "excel_filename": "",      # שם קובץ האקסל
        "error_msg":      "",      # הודעת שגיאה אחרונה
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ─────────────────────────────────────────────────────────────────────────────
# ממשק ראשי
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    _init_state()

    # ── כותרת ──────────────────────────────────────────────────────────────
    st.title("🧪 מטפסי התחייבות לאקסל")
    st.caption("מנוע חילוץ אוטומטי לטפסי התחייבות — המעבדה המרכזית לנגיפים")
    st.divider()

    # ── סרגל צד ──────────────────────────────────────────────────────────
    _render_sidebar()

    # ── גוף ראשי ─────────────────────────────────────────────────────────
    if not st.session_state.forms:
        _render_upload_section()
    else:
        _render_results_section()


# ─────────────────────────────────────────────────────────────────────────────
# סרגל צד
# ─────────────────────────────────────────────────────────────────────────────

def _render_sidebar() -> None:
    """מציג הגדרות ומידע בסרגל הצד."""
    with st.sidebar:
        st.header("⚙️ הגדרות")

        # בדיקת API Key
        api_key = os.getenv("OPENAI_API_KEY", "")
        if api_key and api_key.startswith("sk-"):
            st.success("✓ OpenAI API Key מוגדר")
        else:
            st.error("✗ OpenAI API Key חסר")
            st.info("צרי קובץ `.env` עם:\n```\nOPENAI_API_KEY=sk-...\n```")

        st.divider()

        # כפתור איפוס
        if st.session_state.forms:
            if st.button("🔄 טפסים חדשים", use_container_width=True):
                st.session_state.forms = []
                st.session_state.excel_bytes = None
                st.session_state.excel_filename = ""
                st.session_state.error_msg = ""
                st.rerun()

        st.divider()

        # מקרא צבעים
        st.subheader("מקרא")
        st.markdown("""
        <div class="status-ok">✓ תקין — ביטחון גבוה</div><br>
        <div class="status-low">⚠ לא בטוח — בדקי</div><br>
        <div class="status-missing">✗ חסר — לא נמצא</div><br>
        <div class="status-error">⚡ שגיאה טכנית</div>
        """, unsafe_allow_html=True)

        st.divider()
        st.caption("האקתון AI קוד פתוח 2026")


# ─────────────────────────────────────────────────────────────────────────────
# חלק העלאה
# ─────────────────────────────────────────────────────────────────────────────

def _render_upload_section() -> None:
    """מציג את אזור העלאת הקבצים ועיבודם."""

    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("📂 העלאת טפסים")
        uploaded_files = st.file_uploader(
            label="גרור טפסים לכאן או לחץ לבחירה",
            type=["pdf", "jpg", "jpeg", "png", "tiff", "bmp"],
            accept_multiple_files=True,
            help="PDF סרוק, צילום טלפון, תמונה — הכל נתמך",
        )

    with col2:
        st.subheader("ℹ️ מה נחלץ")
        for field_key, field_def in FIELDS.items():
            multi_mark = " (כמה)" if field_def["multi"] else ""
            req_mark   = " *" if field_def["required"] else ""
            st.markdown(f"• **{field_def['excel_col']}**{multi_mark}{req_mark}")
        st.caption("* = שדה חובה")

    # הודעת שגיאה אחרונה
    if st.session_state.error_msg:
        st.error(st.session_state.error_msg)

    # כפתור עיבוד
    if uploaded_files:
        st.info(f"נבחרו **{len(uploaded_files)}** קבצים")

        if st.button(
            "▶ עבד טפסים",
            type="primary",
            use_container_width=True,
            disabled=st.session_state.processing,
        ):
            _run_processing(uploaded_files)
    else:
        st.markdown("""
        ---
        **טיפ:** ניתן לגרור מספר קבצים בבת אחת.
        כל דף PDF יעובד בנפרד כטופס אחד.
        """)


def _run_processing(uploaded_files) -> None:
    """
    מריץ את ה-pipeline על הקבצים שהועלו.
    שומר קבצים זמניים, מעבד, ומנקה.
    """
    st.session_state.processing = True
    st.session_state.error_msg  = ""
    temp_paths: list[Path] = []

    try:
        # שמירת קבצים זמניים
        valid_paths: list[Path] = []
        for uf in uploaded_files:
            if not is_supported_file(uf.name):
                st.warning(f"פורמט לא נתמך: {uf.name} — מדולג")
                continue
            suffix = Path(uf.name).suffix
            tmp = save_temp_file(uf.read(), suffix)
            # שומרים את שם הקובץ המקורי ב-metadata
            tmp_with_name = tmp.rename(tmp.parent / f"{tmp.stem}_{uf.name}")
            temp_paths.append(tmp_with_name)
            valid_paths.append(tmp_with_name)

        if not valid_paths:
            st.error("לא נמצאו קבצים תקינים לעיבוד")
            return

        # progress bar
        progress_bar = st.progress(0, text="מתחיל עיבוד...")
        status_text  = st.empty()

        def update_progress(current: int, total: int, message: str) -> None:
            if total > 0:
                pct = int((current / total) * 100)
                progress_bar.progress(pct, text=message)
            status_text.caption(message)

        # הרצת pipeline
        with st.spinner("מעבד טפסים עם GPT-4o Vision..."):
            forms = process_multiple_files(valid_paths, update_progress)

        progress_bar.progress(100, text="✓ עיבוד הושלם")
        status_text.empty()

        if forms:
            st.session_state.forms = forms
            st.rerun()
        else:
            st.session_state.error_msg = "לא חולצו טפסים. בדקי שהקבצים תקינים."

    except EnvironmentError as e:
        # OPENAI_API_KEY חסר
        st.session_state.error_msg = f"❌ {e}"
        logger.error(f"EnvironmentError: {e}")

    except Exception as e:
        st.session_state.error_msg = f"❌ שגיאה בעיבוד: {e}"
        logger.error(f"שגיאת עיבוד: {e}", exc_info=True)

    finally:
        # מחיקת קבצים זמניים בכל מקרה
        for p in temp_paths:
            delete_temp_file(p)
        st.session_state.processing = False


# ─────────────────────────────────────────────────────────────────────────────
# חלק תוצאות
# ─────────────────────────────────────────────────────────────────────────────

def _render_results_section() -> None:
    """מציג את תוצאות החילוץ עם אפשרות תיקון וייצוא."""
    forms = st.session_state.forms

    # ── סיכום ────────────────────────────────────────────────────────────
    _render_summary(forms)
    st.divider()

    # ── טבלת תיקון ────────────────────────────────────────────────────────
    st.subheader("📋 תוצאות — ערוך לפני ייצוא")
    st.caption("שדות כתומים = לא בטוח, אדומים = חסר. ערוך ישירות בטבלה.")

    edited_forms = _render_editable_table(forms)
    st.session_state.forms = edited_forms

    st.divider()

    # ── ייצוא ────────────────────────────────────────────────────────────
    _render_export_section(edited_forms)


def _render_summary(forms: list[dict]) -> None:
    """מציג כרטיסי סיכום: סה"כ טפסים, תקינים, לא-בטוחים, חסרים."""
    total   = len(forms)
    ok_c    = sum(1 for f in forms if _form_all_ok(f))
    low_c   = sum(1 for f in forms if _form_has_status(f, FieldStatus.LOW))
    miss_c  = sum(1 for f in forms if _form_has_status(f, FieldStatus.MISSING))

    cols = st.columns(4)
    metrics = [
        ("📄 סה\"כ טפסים",    total,  None),
        ("✅ תקינים לחלוטין", ok_c,   "normal"),
        ("⚠️ דורשים בדיקה",  low_c,  "inverse" if low_c > 0 else "normal"),
        ("❌ שדות חסרים",     miss_c, "inverse" if miss_c > 0 else "normal"),
    ]
    for col, (label, value, delta_color) in zip(cols, metrics):
        with col:
            st.metric(label=label, value=value)


def _render_editable_table(forms: list[dict]) -> list[dict]:
    """
    מציג טבלה עם st.data_editor לעריכה ישירה.
    שדות לא-בטוחים מסומנים בצבע ברקע.

    Args:
        forms: רשימת טפסים מעובדים

    Returns:
        רשימת טפסים אחרי עריכה ידנית
    """
    # בניית DataFrame מהנתונים
    df, field_col_map = _forms_to_dataframe(forms)

    # הגדרת עמודות לעריכה
    column_config = _build_column_config(df.columns.tolist())

    # הצגת הטבלה הניתנת לעריכה
    edited_df = st.data_editor(
        df,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        key="forms_editor",
    )

    # הצגת סטטוסים בצד
    _render_status_legend_inline(forms)

    # המרה חזרה לפורמט forms
    return _dataframe_to_forms(edited_df, forms, field_col_map)


def _forms_to_dataframe(forms: list[dict]) -> tuple[pd.DataFrame, dict]:
    """
    ממיר רשימת forms ל-DataFrame לעריכה.

    Returns:
        (DataFrame, מיפוי שם_עמודה → field_key)
    """
    rows = []
    field_col_map: dict[str, str] = {}  # excel_col → field_key

    for form in forms:
        row: dict[str, Any] = {
            "קובץ": form.get("source_file", ""),
            "דף":   form.get("page", 1),
        }

        for field_key, field_def in FIELDS.items():
            col_name = field_def["excel_col"]
            field_col_map[col_name] = field_key

            field_data = form.get(field_key, {})
            # מגן מפני מקרה שהערך הוא string ולא dict (source_file, page וכד')
            if not isinstance(field_data, dict):
                field_data = {}
            value      = field_data.get("value")
            status     = field_data.get("status", FieldStatus.MISSING)

            # ערך לתצוגה
            if isinstance(value, list):
                display_val = ", ".join(str(v) for v in value if v)
            else:
                display_val = str(value) if value is not None else ""

            # עמודת ערך
            row[col_name] = display_val

            # עמודת סטטוס (נסתרת מהעריכה, מוצגת בנפרד)
            row[f"_status_{col_name}"] = status.value if isinstance(status, FieldStatus) else status

        rows.append(row)

    df = pd.DataFrame(rows)
    return df, field_col_map


def _build_column_config(columns: list[str]) -> dict:
    """בונה הגדרות עמודות לst.data_editor."""
    config = {
        "קובץ": st.column_config.TextColumn("קובץ מקור", disabled=True, width="medium"),
        "דף":   st.column_config.NumberColumn("דף", disabled=True, width="small"),
    }

    for field_key, field_def in FIELDS.items():
        col_name = field_def["excel_col"]
        config[col_name] = st.column_config.TextColumn(
            label    = col_name,
            width    = "medium",
            help     = f"ערוך ידנית אם נדרש תיקון",
        )
        # עמודות סטטוס — מוסתרות
        config[f"_status_{col_name}"] = st.column_config.Column(
            label  = f"סטטוס {col_name}",
            width  = "small",
        )

    return config


def _dataframe_to_forms(
    edited_df:    pd.DataFrame,
    original_forms: list[dict],
    field_col_map:  dict[str, str],
) -> list[dict]:
    """
    ממיר DataFrame ערוך חזרה לפורמט forms.
    שדה שנערך ידנית מקבל confidence=1.0 ו-status=OK.
    """
    updated_forms: list[dict] = []

    for row_idx, row in edited_df.iterrows():
        if row_idx >= len(original_forms):
            break

        orig = original_forms[row_idx].copy()

        for col_name, field_key in field_col_map.items():
            if col_name not in row:
                continue

            new_val_str = str(row[col_name]).strip() if pd.notna(row[col_name]) else ""

            field_def    = FIELDS[field_key]
            orig_data    = orig.get(field_key, {})
            orig_val_raw = orig_data.get("value")

            # ממיר ערך מקורי לתצוגה לשם השוואה
            if isinstance(orig_val_raw, list):
                orig_display = ", ".join(str(v) for v in orig_val_raw if v)
            else:
                orig_display = str(orig_val_raw) if orig_val_raw is not None else ""

            # אם המשתמש שינה — מעדכן confidence ל-1.0 ו-status ל-OK
            if new_val_str != orig_display:
                # ממיר חזרה לרשימה אם שדה multi
                if field_def["multi"]:
                    new_val: Any = [v.strip() for v in new_val_str.split(",") if v.strip()]
                else:
                    new_val = new_val_str if new_val_str else None

                orig[field_key] = {
                    "value":      new_val,
                    "confidence": 1.0,
                    "status":     FieldStatus.OK,
                }

        updated_forms.append(orig)

    return updated_forms


def _render_status_legend_inline(forms: list[dict]) -> None:
    """מציג מפת סטטוסים לכל טופס בצורה קומפקטית."""
    with st.expander("📊 סטטוס מפורט לכל טופס", expanded=False):
        for i, form in enumerate(forms):
            issues = count_issues(form)
            src    = form.get("source_file", f"טופס {i+1}")
            page   = form.get("page", 1)
            low    = issues.get("low", 0)
            miss   = issues.get("missing", 0)

            if low == 0 and miss == 0:
                st.markdown(f"✅ **{src}** דף {page} — תקין")
            else:
                parts = []
                if low > 0:
                    parts.append(f"⚠️ {low} לא-בטוחים")
                if miss > 0:
                    parts.append(f"❌ {miss} חסרים")
                st.markdown(f"**{src}** דף {page} — {', '.join(parts)}")


# ─────────────────────────────────────────────────────────────────────────────
# ייצוא
# ─────────────────────────────────────────────────────────────────────────────

def _render_export_section(forms: list[dict]) -> None:
    """מציג את כפתור הייצוא והורדת הקובץ."""
    st.subheader("📥 ייצוא לאקסל")

    col1, col2 = st.columns([1, 2])

    with col1:
        if st.button("📊 צור קובץ אקסל", type="primary", use_container_width=True):
            _generate_excel(forms)

    with col2:
        if st.session_state.excel_bytes:
            st.download_button(
                label     = "⬇️ הורד אקסל",
                data      = st.session_state.excel_bytes,
                file_name = st.session_state.excel_filename,
                mime      = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
            st.success(f"✓ קובץ מוכן: **{st.session_state.excel_filename}**")


def _generate_excel(forms: list[dict]) -> None:
    """
    מריץ את export_to_excel ושומר את התוצאה ב-session_state.
    """
    try:
        with st.spinner("יוצר קובץ אקסל..."):
            output_path = export_to_excel(forms)

        # קריאת הקובץ לזיכרון לכפתור הורדה
        with open(output_path, "rb") as f:
            st.session_state.excel_bytes    = f.read()
            st.session_state.excel_filename = output_path.name

        st.rerun()

    except Exception as e:
        st.error(f"❌ שגיאה ביצירת האקסל: {e}")
        logger.error(f"שגיאת ייצוא: {e}", exc_info=True)


# ─────────────────────────────────────────────────────────────────────────────
# פונקציות עזר לסטטוס
# ─────────────────────────────────────────────────────────────────────────────

def _form_all_ok(form: dict) -> bool:
    """מחזיר True אם כל השדות בטופס תקינים."""
    for field_key in FIELDS:
        field_data = form.get(field_key)
        if not isinstance(field_data, dict):
            return False
        status = field_data.get("status")
        if status != FieldStatus.OK:
            return False
    return True


def _form_has_status(form: dict, target: FieldStatus) -> bool:
    """מחזיר True אם לפחות שדה אחד בטופס הוא בסטטוס הנתון."""
    for field_key in FIELDS:
        field_data = form.get(field_key)
        if not isinstance(field_data, dict):
            continue
        status = field_data.get("status")
        if status == target:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# הרצה
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()

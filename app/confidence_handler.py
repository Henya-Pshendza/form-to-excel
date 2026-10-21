"""
app/confidence_handler.py
--------------------------
מחליט אילו שדות לסמן כ"לא בטוח — בדקי" ואילו כ"תקין".

כללי הסימון:
- confidence < THRESHOLD                  → LOW  (כתום — בדקי)
- שדה required שנשאר ריק                → MISSING (אדום — חסר)
- confidence >= THRESHOLD ויש ערך        → OK  (ירוק)

הסימון הזה עובר לממשק Streamlit ולאקסל.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from config.fields import FIELDS, CONFIDENCE_THRESHOLD
from utils.logger import get_logger

logger = get_logger(__name__)


class FieldStatus(str, Enum):
    """
    סטטוס של שדה בודד לאחר חילוץ ונרמול.
    """
    OK      = "ok"       # תקין, confidence גבוה
    LOW     = "low"      # ערך קיים אבל confidence נמוך — בדקי
    MISSING = "missing"  # שדה חובה שלא נמצא
    ERROR   = "error"    # שגיאה טכנית (כשל API וכד')


# צבעי הדגשה לממשק (Streamlit + Excel)
STATUS_COLORS = {
    FieldStatus.OK:      "#d4edda",   # ירוק בהיר
    FieldStatus.LOW:     "#fff3cd",   # כתום בהיר — "בדקי"
    FieldStatus.MISSING: "#f8d7da",   # אדום בהיר — "חסר"
    FieldStatus.ERROR:   "#e2e3e5",   # אפור — שגיאה
}

# תוויות בעברית לממשק
STATUS_LABELS = {
    FieldStatus.OK:      "✓ תקין",
    FieldStatus.LOW:     "⚠ לא בטוח — בדקי",
    FieldStatus.MISSING: "✗ חסר",
    FieldStatus.ERROR:   "⚡ שגיאה",
}


def apply_confidence_flags(
    extraction: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """
    מוסיף שדה "status" לכל שדה בתוצאת החילוץ.

    Args:
        extraction: תוצאת normalizer — { שדה: {value, confidence} }

    Returns:
        אותו מבנה עם "status" נוסף לכל שדה:
        { שדה: {value, confidence, status: FieldStatus} }
    """
    # בדיקה אם הייתה שגיאה כללית ב-API
    has_api_error = "_error" in extraction

    flagged: dict[str, dict[str, Any]] = {}

    for field_key, field_def in FIELDS.items():
        field_data = extraction.get(field_key, {})
        value      = field_data.get("value")
        confidence = field_data.get("confidence", 0.0)

        # קביעת סטטוס
        status = _determine_status(
            field_key  = field_key,
            field_def  = field_def,
            value      = value,
            confidence = confidence,
            has_error  = has_api_error,
        )

        flagged[field_key] = {
            "value":      value,
            "confidence": confidence,
            "status":     status,
        }

        if status != FieldStatus.OK:
            logger.debug(f"שדה {field_key}: {STATUS_LABELS[status]} (confidence={confidence:.2f})")

    # מעביר שדות פנימיים (כמו _error) ללא שינוי
    if has_api_error:
        flagged["_error"] = extraction["_error"]

    return flagged


def _determine_status(
    field_key:  str,
    field_def:  dict,
    value:      Any,
    confidence: float,
    has_error:  bool,
) -> FieldStatus:
    """
    קובע את הסטטוס של שדה בודד.

    Args:
        field_key:  שם השדה
        field_def:  הגדרת השדה מ-FIELDS
        value:      הערך שחולץ
        confidence: רמת הביטחון (0.0–1.0)
        has_error:  האם הייתה שגיאת API כללית

    Returns:
        FieldStatus המתאים
    """
    # שגיאה כללית — כל השדות מסומנים כשגיאה
    if has_error:
        return FieldStatus.ERROR

    # בדיקת שדה ריק
    is_empty = (
        value is None
        or value == ""
        or value == []
    )

    if is_empty:
        # שדה חובה שחסר
        if field_def.get("required", False):
            return FieldStatus.MISSING
        # שדה לא חובה שחסר — OK (לא מסמנים)
        return FieldStatus.OK

    # יש ערך — בודקים confidence
    if confidence < CONFIDENCE_THRESHOLD:
        return FieldStatus.LOW

    return FieldStatus.OK


def count_issues(flagged: dict[str, dict[str, Any]]) -> dict[str, int]:
    """
    סופר כמה שדות בכל סטטוס — לתצוגה בממשק.

    Args:
        flagged: תוצאת apply_confidence_flags

    Returns:
        { "ok": N, "low": N, "missing": N, "error": N }
    """
    counts = {s.value: 0 for s in FieldStatus}
    for field_key, field_data in flagged.items():
        # דולגים על מפתחות שאינם שדות FIELDS (כמו source_file, page, _error)
        if field_key not in FIELDS:
            continue
        # field_data חייב להיות dict — אחרת דולגים
        if not isinstance(field_data, dict):
            continue
        status = field_data.get("status", FieldStatus.ERROR)
        if isinstance(status, FieldStatus):
            counts[status.value] += 1
    return counts


def is_ready_to_export(flagged: dict[str, dict[str, Any]]) -> bool:
    """
    בודק אם הטופס מוכן לייצוא — אין שדות MISSING.
    שדות LOW מותרים לייצוא (הלבורנטית יכולה לבחור לייצא גם אם יש לא-בטוחים).

    Args:
        flagged: תוצאת apply_confidence_flags

    Returns:
        True אם אין שדות MISSING
    """
    counts = count_issues(flagged)
    return counts.get(FieldStatus.MISSING.value, 0) == 0

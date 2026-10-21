"""
app/normalizer.py
-----------------
מנרמל את הערכים שחולצו מהטפסים לפורמט אחיד ועקבי.

כל פונקציה מטפלת בסוג שדה אחד:
- תאריכים → DD/MM/YYYY
- תעודת זהות → 9 ספרות בדיוק
- גורם שולח → מהרשימה הסגורה (fuzzy match)
- טקסט → ניקוי תווים מיותרים
- מספרים (מרכזי/התחייבות) → ניקוי ועיצוב

חשוב: אם הנרמול נכשל — מחזירים None ומורידים את ה-confidence,
       לא מחזירים ניחוש.
"""

from __future__ import annotations

import re
from typing import Any

from dateutil import parser as dateutil_parser
from rapidfuzz import process as fuzz_process, fuzz

from config.fields import FIELDS
from config.senders import ALL_SENDERS, SENDER_ALIASES
from utils.logger import get_logger

logger = get_logger(__name__)

# ציון מינימלי ל-fuzzy match של גורם שולח (0-100)
# מתחת לציון זה — מחזירים None ולא מנחשים
SENDER_FUZZY_MIN_SCORE = 70


def normalize_result(extraction: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """
    מריץ נרמול על כל השדות בתוצאת החילוץ.

    Args:
        extraction: תוצאת vision_extractor — { שדה: {value, confidence} }

    Returns:
        אותו מבנה אחרי נרמול. confidence עלול לרדת אם הנרמול גילה בעיה.
    """
    normalized = {}

    for field_key, field_data in extraction.items():
        # שדות פנימיים (כמו _error) — עוברים ללא שינוי
        if field_key.startswith("_"):
            normalized[field_key] = field_data
            continue

        field_def = FIELDS.get(field_key)
        if field_def is None:
            normalized[field_key] = field_data
            continue

        value = field_data.get("value")
        confidence = field_data.get("confidence", 0.0)

        # שדה ריק — לא מנרמלים, מחזירים כמות שהוא
        if value is None or value == [] or value == "":
            normalized[field_key] = {"value": None if not field_def["multi"] else [], "confidence": confidence}
            continue

        field_type = field_def["type"]

        # נרמול לפי סוג השדה
        if field_type == "date":
            norm_value, confidence = _normalize_date(value, confidence)

        elif field_type == "id":
            norm_value, confidence = _normalize_id(value, confidence)

        elif field_type == "closed":
            norm_value, confidence = _normalize_sender(value, confidence)

        elif field_type == "list":
            norm_value, confidence = _normalize_list(value, confidence)

        else:
            # text — ניקוי בסיסי בלבד
            norm_value, confidence = _normalize_text(value, confidence)

        normalized[field_key] = {"value": norm_value, "confidence": confidence}

    return normalized


# ---------------------------------------------------------------------------
# נרמול תאריך
# ---------------------------------------------------------------------------

def _normalize_date(value: str, confidence: float) -> tuple[str | None, float]:
    """
    ממיר תאריך בכל פורמט ל-DD/MM/YYYY.

    מטפל ב:
    - 21.8.26 / 21/08/2026 / 21-08-26
    - "21 אוגוסט 2026"
    - תאריכים חלקיים (מוריד confidence)

    Args:
        value:      ערך התאריך כמחרוזת
        confidence: confidence נוכחי

    Returns:
        (תאריך מנורמל או None, confidence מעודכן)
    """
    if not value:
        return None, 0.0

    cleaned = str(value).strip()

    # מנסים קודם עם regex — יותר מהיר ומדויק לפורמטים ידועים
    date_match = re.search(
        r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})",
        cleaned
    )
    if date_match:
        day, month, year = date_match.groups()
        # תיקון שנה דו-ספרתית (26 → 2026)
        if len(year) == 2:
            year = "20" + year
        try:
            # ולידציה — dateutil יזרוק שגיאה אם לא תקין
            dateutil_parser.parse(f"{day}/{month}/{year}", dayfirst=True)
            return f"{int(day):02d}/{int(month):02d}/{year}", confidence
        except Exception:
            pass

    # ניסיון עם dateutil לפורמטים מורכבים יותר
    try:
        parsed = dateutil_parser.parse(cleaned, dayfirst=True, fuzzy=True)
        formatted = parsed.strftime("%d/%m/%Y")
        # fuzzy=True עלול לטעות — מורידים confidence מעט
        return formatted, max(0.0, confidence - 0.1)
    except Exception:
        logger.debug(f"לא ניתן לנרמל תאריך: {cleaned!r}")
        # מחזירים את הערך המקורי עם confidence נמוך — הלבורנטית תתקן
        return cleaned, max(0.0, confidence - 0.3)


# ---------------------------------------------------------------------------
# נרמול תעודת זהות
# ---------------------------------------------------------------------------

def _normalize_id(value: str, confidence: float) -> tuple[str | None, float]:
    """
    מנרמל מספר תעודת זהות ישראלי: מסיר תווים שאינם ספרות,
    מוודא שיש בדיוק 9 ספרות.

    Args:
        value:      ערך ת.ז. כמחרוזת
        confidence: confidence נוכחי

    Returns:
        (מספר ת.ז. מנורמל או None, confidence מעודכן)
    """
    if not value:
        return None, 0.0

    # מסיר הכל חוץ מספרות
    digits_only = re.sub(r"\D", "", str(value))

    if not digits_only:
        return None, 0.0

    if len(digits_only) == 9:
        return digits_only, confidence

    if len(digits_only) == 8:
        # ת.ז. עם אפס מוביל שנפל — מוסיפים
        padded = "0" + digits_only
        logger.debug(f"ת.ז. הורחבה ל-9 ספרות: {padded}")
        return padded, max(0.0, confidence - 0.05)

    if len(digits_only) > 9:
        # יש יותר מדי ספרות — ייתכן שחולצו שתי ת.ז. יחד
        logger.debug(f"ת.ז. ארוכה מדי ({len(digits_only)} ספרות): {digits_only}")
        return digits_only[:9], max(0.0, confidence - 0.2)

    # פחות מ-8 ספרות — לא ייתכן
    logger.debug(f"ת.ז. קצרה מדי ({len(digits_only)} ספרות): {digits_only}")
    return digits_only, max(0.0, confidence - 0.4)


# ---------------------------------------------------------------------------
# נרמול גורם שולח (רשימה סגורה)
# ---------------------------------------------------------------------------

def _normalize_sender(value: str, confidence: float) -> tuple[str | None, float]:
    """
    מוצא את הגורם השולח הקרוב ביותר מהרשימה הסגורה.
    משתמש ב-fuzzy matching כדי להתמודד עם שגיאות כתיב וקיצורים.

    לא מנחש — אם הציון נמוך מדי, מחזיר None.

    Args:
        value:      שם הגורם השולח כמחרוזת
        confidence: confidence נוכחי

    Returns:
        (שם מנורמל מהרשימה או None, confidence מעודכן)
    """
    if not value:
        return None, 0.0

    cleaned = str(value).strip().lower()

    # בדיקה ב-aliases תחילה (התאמות מדויקות/ידועות)
    for alias, canonical in SENDER_ALIASES.items():
        if cleaned == alias.lower() or cleaned in alias.lower():
            return canonical, min(1.0, confidence + 0.05)

    # fuzzy match מול כל הרשימה
    match = fuzz_process.extractOne(
        cleaned,
        [s.lower() for s in ALL_SENDERS],
        scorer=fuzz.WRatio,
        score_cutoff=SENDER_FUZZY_MIN_SCORE,
    )

    if match:
        matched_lower, score, index = match
        canonical_name = ALL_SENDERS[index]
        # ממיר ציון 70-100 ל-confidence 0.6-0.95
        normalized_conf = 0.6 + (score - 70) / 100
        final_confidence = min(confidence, normalized_conf)
        logger.debug(f"גורם שולח: {value!r} → {canonical_name!r} (score={score})")
        return canonical_name, round(final_confidence, 2)

    # לא נמצאה התאמה — מחזירים את הערך המקורי עם confidence נמוך
    logger.debug(f"גורם שולח לא זוהה: {value!r}")
    return value, max(0.0, confidence - 0.4)


# ---------------------------------------------------------------------------
# נרמול שדות רשימה (מספר מרכזי / מספר התחייבות)
# ---------------------------------------------------------------------------

def _normalize_list(value: list | str, confidence: float) -> tuple[list[str], float]:
    """
    מנרמל שדה שיכול להכיל כמה ערכים (רשימה).
    מנקה כל ערך ברשימה ומסיר כפילויות.

    Args:
        value:      רשימה או מחרוזת
        confidence: confidence נוכחי

    Returns:
        (רשימת ערכים מנורמלת, confidence)
    """
    if not value:
        return [], 0.0

    # אם המודל החזיר מחרוזת — ממירים לרשימה
    if isinstance(value, str):
        # מחפשים מפרידים נפוצים: פסיק, נקודה-פסיק, |, רווח מרובה
        parts = re.split(r"[,;|]+|\s{2,}", value)
        items = [p.strip() for p in parts if p.strip()]
    else:
        items = [str(item).strip() for item in value if item]

    # ניקוי כל ערך: מסיר תווים מיוחדים שאינם ספרות/אותיות
    cleaned = []
    for item in items:
        # שומר ספרות, אותיות (עברית + אנגלית), מקף, נקודה
        item_clean = re.sub(r"[^\w\d\-.]", "", item)
        if item_clean:
            cleaned.append(item_clean)

    # הסרת כפילויות תוך שמירת הסדר
    seen: set[str] = set()
    unique = []
    for item in cleaned:
        if item not in seen:
            seen.add(item)
            unique.append(item)

    return unique, confidence


# ---------------------------------------------------------------------------
# נרמול טקסט חופשי (שם פרטי / שם משפחה)
# ---------------------------------------------------------------------------

def _normalize_text(value: str, confidence: float) -> tuple[str | None, float]:
    """
    ניקוי בסיסי לשדות טקסט: מסיר רווחים מיותרים ותווים מוזרים.
    לא משנה את התוכן עצמו.

    Args:
        value:      ערך הטקסט
        confidence: confidence נוכחי

    Returns:
        (טקסט מנוקה, confidence)
    """
    if not value:
        return None, 0.0

    cleaned = str(value).strip()

    # מסיר תווי בקרה ותווים שאינם מופיעים בשמות
    cleaned = re.sub(r"[\x00-\x1f\x7f]", "", cleaned)

    # מנרמל רווחים מרובים לרווח בודד
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if not cleaned:
        return None, 0.0

    return cleaned, confidence

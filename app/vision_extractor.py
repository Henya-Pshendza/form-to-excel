"""
app/vision_extractor.py
-----------------------
שולח תמונת טופס ל-GPT-4o Vision ומחזיר JSON מובנה עם השדות.

עקרונות:
- מנסה עד MAX_RETRIES פעמים אם המודל מחזיר JSON פגום
- לא מלוגג תוכן תשובות (פרטיות)
- שדה לא נמצא → null, לא ניחוש
- confidence לכל שדה בנפרד
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError, APIError

from config.fields import FIELDS
from config.prompts import EXTRACTION_PROMPT, RETRY_PROMPT
from utils.logger import get_logger

# טוען .env מתיקיית שורש הפרויקט — עובד בכל מיקום הרצה
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = get_logger(__name__)

# מספר ניסיונות חוזרים במקרה של JSON פגום או שגיאת API
MAX_RETRIES = 3

# המתנה בשניות בין ניסיונות (גדל בכל ניסיון — exponential backoff)
RETRY_DELAY_SECONDS = 2

# מודל לשימוש — gpt-4o לדיוק מירבי על כתב יד ומדבקות
MODEL = "gpt-4o"

# טיפוס לתוצאת חילוץ בודדת
ExtractionResult = dict[str, dict[str, Any]]


def build_empty_result() -> ExtractionResult:
    """
    בונה תוצאת ברירת מחדל — כל השדות ריקים עם confidence=0.0.
    משמש במקרה של כישלון מוחלט.

    Returns:
        מילון עם כל השדות, value=null, confidence=0.0
    """
    result: ExtractionResult = {}
    for field_key, field_def in FIELDS.items():
        # שדות multi מקבלים רשימה ריקה, שאר מקבלים null
        empty_value: Any = [] if field_def["multi"] else None
        result[field_key] = {"value": empty_value, "confidence": 0.0}
    return result


def extract_from_image(base64_image: str) -> ExtractionResult:
    """
    שולח תמונה ב-base64 ל-GPT-4o Vision ומחזיר שדות מחולצים.

    Args:
        base64_image: תמונת הטופס מקודדת ב-base64 (JPEG)

    Returns:
        מילון: { שם_שדה: { "value": ..., "confidence": float } }
        confidence בין 0.0 ל-1.0 לכל שדה.
        שדה לא נמצא → value=null (או []), confidence=0.0
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY לא מוגדר. "
            "צרי קובץ .env עם OPENAI_API_KEY=sk-..."
        )

    client = OpenAI(api_key=api_key)

    # ניסיון ראשון עם הפרומפט המלא
    # ניסיונות חוזרים עם פרומפט קצר יותר אם JSON פגום
    prompts_to_try = [EXTRACTION_PROMPT, RETRY_PROMPT, RETRY_PROMPT]

    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        prompt = prompts_to_try[min(attempt, len(prompts_to_try) - 1)]

        try:
            logger.info(f"שולח תמונה ל-GPT-4o (ניסיון {attempt + 1}/{MAX_RETRIES})")

            response = client.chat.completions.create(
                model=MODEL,
                max_tokens=1000,
                temperature=0,        # 0 = דטרמיניסטי, פחות ניחושים
                messages=[
                    {
                        "role": "user",
                        "content": [
                            # הפרומפט עם הוראות החילוץ
                            {
                                "type": "text",
                                "text": prompt,
                            },
                            # התמונה עצמה
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}",
                                    "detail": "high",  # איכות גבוהה לקריאת כתב יד
                                },
                            },
                        ],
                    }
                ],
            )

            raw_text = response.choices[0].message.content or ""
            logger.debug("תשובה התקבלה מה-API")

            # ניסיון לפרסר JSON
            parsed = _parse_json_response(raw_text)
            if parsed is not None:
                # בדיקת תקינות ומילוי שדות חסרים
                validated = _validate_and_fill(parsed)
                logger.info("חילוץ הושלם בהצלחה")
                return validated

            logger.warning(f"ניסיון {attempt + 1}: JSON לא תקין — מנסה שוב")
            last_error = ValueError(f"JSON פגום בניסיון {attempt + 1}")

        except RateLimitError:
            # מגבלת קצב — ממתינים יותר
            wait = RETRY_DELAY_SECONDS * (attempt + 1) * 2
            logger.warning(f"Rate limit — ממתין {wait} שניות")
            time.sleep(wait)
            last_error = RateLimitError  # type: ignore

        except APIError as e:
            logger.error(f"שגיאת API בניסיון {attempt + 1}: {e}")
            last_error = e
            time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))

        except Exception as e:
            logger.error(f"שגיאה לא צפויה בניסיון {attempt + 1}: {e}")
            last_error = e
            time.sleep(RETRY_DELAY_SECONDS)

    # כל הניסיונות נכשלו — מחזירים תוצאה ריקה עם סימון שגיאה
    logger.error(f"כל {MAX_RETRIES} הניסיונות נכשלו: {last_error}")
    empty = build_empty_result()
    # מסמנים שהייתה שגיאה — ה-confidence_handler יסמן הכל בכתום
    empty["_error"] = {"value": str(last_error), "confidence": 0.0}  # type: ignore
    return empty


def _parse_json_response(text: str) -> dict | None:
    """
    מנסה לחלץ JSON מהתשובה.
    מטפל במקרים שבהם המודל מוסיף ```json ... ``` או טקסט נוסף.

    Args:
        text: טקסט גולמי מהמודל

    Returns:
        dict אם הצליח, None אחרת
    """
    if not text:
        return None

    # ניסיון 1: הטקסט הוא JSON טהור
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # ניסיון 2: המודל עטף ב-```json ... ```
    if "```" in text:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    # ניסיון 3: מחפשים { ... } ראשון בתשובה
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    return None


def _validate_and_fill(raw: dict) -> ExtractionResult:
    """
    בודק שכל השדות הנדרשים קיימים ותקינים.
    מוסיף ולידציה קפדנית לכל סוג שדה — מונע ערכים מומצאים.

    Args:
        raw: מילון גולמי מהמודל

    Returns:
        ExtractionResult תקין ומלא
    """
    result: ExtractionResult = {}

    for field_key, field_def in FIELDS.items():
        if field_key not in raw:
            empty_val: Any = [] if field_def["multi"] else None
            result[field_key] = {"value": empty_val, "confidence": 0.0}
            continue

        field_data = raw[field_key]

        if not isinstance(field_data, dict):
            empty_val = [] if field_def["multi"] else None
            result[field_key] = {"value": empty_val, "confidence": 0.0}
            continue

        value = field_data.get("value")
        confidence = field_data.get("confidence", 0.0)

        # ולידציה של confidence
        try:
            confidence = float(confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.0

        # תיקון פורמט לשדות multi
        if field_def["multi"]:
            if value is None:
                value = []
            elif isinstance(value, str):
                value = [value] if value.strip() else []
            elif not isinstance(value, list):
                value = [str(value)]
            value = [str(v).strip() for v in value if v and str(v).strip()]

        # תיקון לשדות לא-multi
        else:
            if isinstance(value, list):
                value = value[0] if value else None
            if value is not None:
                value = str(value).strip() or None

        # ─── ולידציה קפדנית לפי סוג שדה ────────────────────────────────────

        if field_key == "תעודת_זהות" and value is not None:
            # חייב להיות 8-9 ספרות בלבד — אחרת המודל בלבל עם שדה אחר
            digits = re.sub(r"\D", "", str(value))
            if len(digits) < 8 or len(digits) > 10:
                logger.warning(f"תעודת זהות לא תקינה ('{value}') — מאפס")
                value = None
                confidence = 0.0
            else:
                value = digits

        elif field_key == "תאריך_קבלה" and value is not None:
            # חייב להכיל תבנית תאריך — אחרת המודל שם מספר מרכזי במקום
            if not _looks_like_date(str(value)):
                logger.warning(f"תאריך לא תקין ('{value}') — מאפס")
                value = None
                confidence = 0.0

        elif field_key == "מספר_מרכזי" and isinstance(value, list):
            # מסנן ערכים שנראים כתאריכים (בלבול נפוץ)
            filtered = [v for v in value if not _looks_like_date(v)]
            if len(filtered) < len(value):
                logger.warning(f"סוננו תאריכים מרשימת מספרים מרכזיים: {value} → {filtered}")
            value = filtered
            if not value:
                confidence = 0.0

        elif field_key == "מספר_התחייבות" and isinstance(value, list):
            # מסנן ערכים שנראים כתאריכים
            filtered = [v for v in value if not _looks_like_date(v)]
            value = filtered
            if not value:
                confidence = 0.0

        # ─── סף confidence לפי סוג שדה ──────────────────────────────────────
        # שמות — סף גבוה יותר (0.85): עדיף ריק מניחוש שם שגוי
        # שאר השדות — סף רגיל (0.70)
        min_confidence = 0.85 if field_key in ("שם_פרטי", "שם_משפחה") else 0.70

        if confidence < min_confidence:
            if field_def["multi"]:
                value = []
            else:
                value = None
            confidence = 0.0
            logger.debug(f"שדה {field_key}: confidence {confidence:.2f} < {min_confidence} — מאופס")

        result[field_key] = {"value": value, "confidence": confidence}

    return result


def _looks_like_date(value: str) -> bool:
    """
    בודק אם מחרוזת נראית כתאריך.
    משמש למניעת בלבול בין תאריכים למספרים.

    Args:
        value: מחרוזת לבדיקה

    Returns:
        True אם נראה כתאריך
    """
    import re
    # תבנית תאריך: DD/MM/YYYY, DD.MM.YYYY, DD-MM-YY וכד'
    date_pattern = r"^\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}$"
    return bool(re.match(date_pattern, str(value).strip()))

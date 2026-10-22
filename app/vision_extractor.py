"""
app/vision_extractor.py
-----------------------
שולח תמונת טופס ל-Gemini Flash ומחזיר JSON מובנה עם השדות.

מודל: gemini-2.0-flash — חינמי עד 1,500 requests/day
מפתח: GOOGLE_API_KEY ב-.env או ב-Streamlit Secrets

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

from config.fields import FIELDS
from config.prompts import EXTRACTION_PROMPT, RETRY_PROMPT
from utils.logger import get_logger

# טוען .env מתיקיית שורש הפרויקט
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = get_logger(__name__)

MAX_RETRIES          = 3
RETRY_DELAY_SECONDS  = 2
MODEL                = "gemini-2.0-flash"

ExtractionResult = dict[str, dict[str, Any]]


def build_empty_result() -> ExtractionResult:
    """מחזיר תוצאה ריקה — כל השדות null עם confidence=0.0."""
    result: ExtractionResult = {}
    for field_key, field_def in FIELDS.items():
        empty_value: Any = [] if field_def["multi"] else None
        result[field_key] = {"value": empty_value, "confidence": 0.0}
    return result


def extract_from_image(base64_image: str) -> ExtractionResult:
    """
    שולח תמונה ב-base64 ל-Gemini Flash ומחזיר שדות מחולצים.

    Args:
        base64_image: תמונת הטופס מקודדת ב-base64 (JPEG)

    Returns:
        מילון: { שם_שדה: { "value": ..., "confidence": float } }
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GOOGLE_API_KEY לא מוגדר. "
            "הוסיפי GOOGLE_API_KEY=AI... לקובץ .env"
        )

    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError(
            "חבילת google-generativeai לא מותקנת. "
            "הריצי: pip install google-generativeai"
        )

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL)

    prompts_to_try = [EXTRACTION_PROMPT, RETRY_PROMPT, RETRY_PROMPT]
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        prompt = prompts_to_try[min(attempt, len(prompts_to_try) - 1)]

        try:
            logger.info(f"שולח תמונה ל-Gemini Flash (ניסיון {attempt + 1}/{MAX_RETRIES})")

            # בניית ה-parts: פרומפט + תמונה
            import base64 as _b64
            image_bytes = _b64.b64decode(base64_image)

            response = model.generate_content(
                contents=[
                    prompt,
                    {
                        "mime_type": "image/jpeg",
                        "data":      image_bytes,
                    },
                ],
                generation_config=genai.GenerationConfig(
                    temperature       = 0,      # דטרמיניסטי
                    max_output_tokens = 1024,
                ),
            )

            raw_text = response.text or ""
            logger.debug("תשובה התקבלה מ-Gemini")

            parsed = _parse_json_response(raw_text)
            if parsed is not None:
                validated = _validate_and_fill(parsed)
                logger.info("חילוץ הושלם בהצלחה")
                return validated

            logger.warning(f"ניסיון {attempt + 1}: JSON לא תקין — מנסה שוב")
            last_error = ValueError(f"JSON פגום בניסיון {attempt + 1}")

        except Exception as e:
            error_str = str(e).lower()
            # rate limit של Gemini
            if "quota" in error_str or "rate" in error_str or "429" in error_str:
                wait = RETRY_DELAY_SECONDS * (attempt + 1) * 3
                logger.warning(f"Rate limit — ממתין {wait} שניות")
                time.sleep(wait)
            else:
                logger.error(f"שגיאה בניסיון {attempt + 1}: {e}")
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
            last_error = e

    logger.error(f"כל {MAX_RETRIES} הניסיונות נכשלו: {last_error}")
    empty = build_empty_result()
    empty["_error"] = {"value": str(last_error), "confidence": 0.0}  # type: ignore
    return empty


def _parse_json_response(text: str) -> dict | None:
    """מחלץ JSON מתשובת המודל — מטפל ב-```json``` ובטקסט עטיפה."""
    if not text:
        return None

    # ניסיון 1: JSON טהור
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # ניסיון 2: עטוף ב-```json ... ```
    if "```" in text:
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end])
            except json.JSONDecodeError:
                pass

    # ניסיון 3: מחפש { ... } ראשון
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    return None


def _validate_and_fill(raw: dict) -> ExtractionResult:
    """
    מוודא שכל השדות קיימים ותקינים.
    מחיל ולידציה קפדנית לפי סוג שדה.
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

        value      = field_data.get("value")
        confidence = field_data.get("confidence", 0.0)

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
        else:
            if isinstance(value, list):
                value = value[0] if value else None
            if value is not None:
                value = str(value).strip() or None

        # ── ולידציה קפדנית לפי שדה ──────────────────────────────────────────

        if field_key == "תעודת_זהות" and value is not None:
            digits = re.sub(r"\D", "", str(value))
            if len(digits) < 8 or len(digits) > 10:
                logger.warning(f"ת.ז. לא תקינה ('{value}') — מאפס")
                value, confidence = None, 0.0
            else:
                value = digits

        elif field_key == "תאריך_קבלה" and value is not None:
            if not _looks_like_date(str(value)):
                logger.warning(f"תאריך לא תקין ('{value}') — מאפס")
                value, confidence = None, 0.0

        elif field_key == "מספר_מרכזי" and isinstance(value, list):
            filtered = [v for v in value if not _looks_like_date(v)]
            if len(filtered) < len(value):
                logger.warning(f"סוננו תאריכים ממספרים מרכזיים: {value} → {filtered}")
            value = filtered
            if not value:
                confidence = 0.0

        elif field_key == "מספר_התחייבות" and isinstance(value, list):
            value = [v for v in value if not _looks_like_date(v)]
            if not value:
                confidence = 0.0

        # ── סף confidence לפי שדה ────────────────────────────────────────────
        # שמות — סף גבוה יותר (0.85)
        # שאר — סף רגיל (0.70)
        min_conf = 0.85 if field_key in ("שם_פרטי", "שם_משפחה") else 0.70

        if confidence < min_conf:
            value      = [] if field_def["multi"] else None
            confidence = 0.0
            logger.debug(f"שדה {field_key}: confidence נמוך מדי — מאופס")

        result[field_key] = {"value": value, "confidence": confidence}

    return result


def _looks_like_date(value: str) -> bool:
    """בודק אם מחרוזת נראית כתאריך (DD/MM/YYYY וכד')."""
    return bool(re.match(r"^\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}$", str(value).strip()))

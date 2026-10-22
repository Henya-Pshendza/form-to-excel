"""
app/vision_extractor.py
-----------------------
שולח תמונת טופס ל-Claude claude-3-5-sonnet (Anthropic) ומחזיר JSON מובנה.

מפתח: ANTHROPIC_API_KEY ב-.env או ב-Streamlit Secrets

Two-step extraction:
  Step 1 — Claude קורא את כל הטקסט מהתמונה (OCR pass)
  Step 2 — Claude מחלץ שדות מובנים מהטקסט הגולמי
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from config.fields import FIELDS
from config.prompts import STEP1_READ_PROMPT, STEP2_EXTRACT_PROMPT, RETRY_PROMPT
from utils.logger import get_logger

_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = get_logger(__name__)

MAX_RETRIES         = 3
RETRY_DELAY_SECONDS = 2
MODEL               = "claude-3-5-sonnet-20241022"

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
    Two-step extraction עם Claude:
    Step 1 — קריאת כל הטקסט מהתמונה
    Step 2 — חילוץ שדות מובנים מהטקסט
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY לא מוגדר. "
            "הוסיפי ANTHROPIC_API_KEY=sk-ant-... לקובץ .env"
        )

    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "חבילת anthropic לא מותקנת. "
            "הריצי: pip install anthropic"
        )

    client = anthropic.Anthropic(api_key=api_key)

    # שלב 1: קריאת כל הטקסט
    raw_text = _step1_read_image(client, base64_image)
    if not raw_text:
        logger.warning("שלב 1 נכשל — עובר לחילוץ ישיר")
        return _step2_extract_direct(client, base64_image)

    # שלב 2: חילוץ שדות מהטקסט
    return _step2_extract_from_text(client, raw_text)


def _step1_read_image(client, base64_image: str) -> str | None:
    """שלב 1: Claude קורא את כל הטקסט הגלוי בתמונה."""
    try:
        logger.info("שלב 1 — קריאת טקסט מהתמונה (Claude)")

        message = client.messages.create(
            model      = MODEL,
            max_tokens = 2000,
            messages   = [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": "image/jpeg",
                            "data":       base64_image,
                        },
                    },
                    {
                        "type": "text",
                        "text": STEP1_READ_PROMPT,
                    },
                ],
            }],
        )

        text = message.content[0].text if message.content else ""
        logger.info(f"שלב 1 הושלם — {len(text)} תווים נקראו")
        return text

    except Exception as e:
        logger.error(f"שגיאה בשלב 1: {e}")
        return None


def _step2_extract_from_text(client, raw_text: str) -> ExtractionResult:
    """שלב 2: חילוץ שדות מובנים מהטקסט הגולמי."""
    prompts_to_try = [STEP2_EXTRACT_PROMPT, RETRY_PROMPT, RETRY_PROMPT]
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        prompt = prompts_to_try[min(attempt, len(prompts_to_try) - 1)]
        try:
            logger.info(f"שלב 2 — חילוץ שדות (ניסיון {attempt + 1}/{MAX_RETRIES})")

            full_prompt = f"{prompt}\n\nFORM TEXT TO ANALYZE:\n{raw_text}"

            message = client.messages.create(
                model      = MODEL,
                max_tokens = 1024,
                messages   = [{
                    "role":    "user",
                    "content": full_prompt,
                }],
            )

            raw_json = message.content[0].text if message.content else ""
            parsed   = _parse_json_response(raw_json)
            if parsed is not None:
                logger.info("שלב 2 הושלם בהצלחה")
                return _validate_and_fill(parsed)

            logger.warning(f"ניסיון {attempt + 1}: JSON לא תקין")
            last_error = ValueError("JSON פגום")

        except Exception as e:
            error_str = str(e).lower()
            if "rate" in error_str or "429" in error_str or "overloaded" in error_str:
                wait = RETRY_DELAY_SECONDS * (attempt + 1) * 2
                logger.warning(f"Rate limit — ממתין {wait} שניות")
                time.sleep(wait)
            else:
                logger.error(f"שגיאה בשלב 2: {e}")
                time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
            last_error = e

    empty = build_empty_result()
    empty["_error"] = {"value": str(last_error), "confidence": 0.0}  # type: ignore
    return empty


def _step2_extract_direct(client, base64_image: str) -> ExtractionResult:
    """Fallback: חילוץ ישיר מהתמונה ללא שלב 1."""
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        prompt = STEP2_EXTRACT_PROMPT if attempt == 0 else RETRY_PROMPT
        try:
            logger.info(f"חילוץ ישיר (ניסיון {attempt + 1}/{MAX_RETRIES})")

            message = client.messages.create(
                model      = MODEL,
                max_tokens = 1024,
                messages   = [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type":       "base64",
                                "media_type": "image/jpeg",
                                "data":       base64_image,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
            )

            raw_json = message.content[0].text if message.content else ""
            parsed   = _parse_json_response(raw_json)
            if parsed is not None:
                return _validate_and_fill(parsed)
            last_error = ValueError("JSON פגום")

        except Exception as e:
            error_str = str(e).lower()
            wait = RETRY_DELAY_SECONDS * (attempt + 1) * (
                2 if "rate" in error_str or "overloaded" in error_str else 1
            )
            time.sleep(wait)
            last_error = e

    empty = build_empty_result()
    empty["_error"] = {"value": str(last_error), "confidence": 0.0}  # type: ignore
    return empty


def _parse_json_response(text: str) -> dict | None:
    """מחלץ JSON מתשובת המודל."""
    if not text:
        return None
    # JSON טהור
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # עטוף ב-```
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return None


def _validate_and_fill(raw: dict) -> ExtractionResult:
    """ולידציה קפדנית — מונעת ערכים מומצאים."""
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
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.0

        # פורמט multi
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

        # ולידציה לפי שדה
        if field_key == "תעודת_זהות" and value is not None:
            digits = re.sub(r"\D", "", str(value))
            if len(digits) < 8 or len(digits) > 10:
                value, confidence = None, 0.0
            else:
                value = digits

        elif field_key == "תאריך_קבלה" and value is not None:
            if not re.match(r"^\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}$", str(value).strip()):
                value, confidence = None, 0.0

        elif field_key in ("מספר_מרכזי", "מספר_התחייבות") and isinstance(value, list):
            value = [v for v in value
                     if not re.match(r"^\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}$", str(v).strip())]
            if not value:
                confidence = 0.0

        # סף confidence
        min_conf = 0.85 if field_key in ("שם_פרטי", "שם_משפחה") else 0.70
        if confidence < min_conf:
            value      = [] if field_def["multi"] else None
            confidence = 0.0

        result[field_key] = {"value": value, "confidence": confidence}

    return result

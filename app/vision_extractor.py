"""
app/vision_extractor.py
-----------------------
Two-step extraction with Gemini Vision:
  Step 1 — reads all text from the image
  Step 2 — extracts structured fields from the raw text
"""

from __future__ import annotations

import json
import os
import re
import time
import base64
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import google.generativeai as genai

from config.fields import FIELDS
from config.prompts import STEP1_READ_PROMPT, STEP2_EXTRACT_PROMPT, RETRY_PROMPT
from utils.logger import get_logger

_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = get_logger(__name__)

MAX_RETRIES         = 3
RETRY_DELAY_SECONDS = 2
MODEL_NAME          = "gemini-3.6-flash"  # ✨ Gemini 3.6 Flash (2026)

ExtractionResult = dict[str, dict[str, Any]]


def build_empty_result() -> ExtractionResult:
    result: ExtractionResult = {}
    for field_key, field_def in FIELDS.items():
        result[field_key] = {
            "value":      [] if field_def["multi"] else None,
            "confidence": 0.0,
        }
    return result


def extract_from_image(base64_image: str) -> ExtractionResult:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("GEMINI_API_KEY לא מוגדר ב-.env")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(MODEL_NAME)

    # שלב 1: קריאת כל הטקסט
    raw_text = _step1_read(model, base64_image)
    if not raw_text:
        logger.warning("שלב 1 נכשל — עובר לחילוץ ישיר")
        return _extract_direct(model, base64_image)

    # שלב 2: חילוץ שדות מהטקסט
    return _step2_extract(model, raw_text)


def _step1_read(model: Any, base64_image: str) -> str | None:
    """שלב 1: קריאת כל הטקסט מהתמונה."""
    try:
        logger.info("שלב 1 — קריאת טקסט (Gemini)")
        
        # המרת base64 לבתים
        image_bytes = base64.b64decode(base64_image)
        
        # יצירת חלק תמונה
        image_part = {
            "mime_type": "image/jpeg",
            "data": image_bytes
        }
        
        response = model.generate_content(
            [STEP1_READ_PROMPT, image_part],
            generation_config=genai.types.GenerationConfig(
                max_output_tokens=2500,
            )
        )
        
        text = response.text if response else ""
        logger.info(f"שלב 1 הושלם — {len(text)} תווים")
        logger.info(f"טקסט מלא מהמודל:\n{text}")
        return text
    except Exception as e:
        logger.error(f"שגיאה בשלב 1: {e}")
        return None


def _step2_extract(model: Any, raw_text: str) -> ExtractionResult:
    """שלב 2: חילוץ שדות מהטקסט הגולמי."""
    prompts = [STEP2_EXTRACT_PROMPT, RETRY_PROMPT, RETRY_PROMPT]
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        prompt = prompts[min(attempt, len(prompts) - 1)]
        try:
            logger.info(f"שלב 2 — ניסיון {attempt + 1}/{MAX_RETRIES}")
            full_prompt = f"{prompt}\n\nFORM TEXT:\n{raw_text}"

            response = model.generate_content(
                full_prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=2048,  # ✨ הגדלה ל-2048
                    response_mime_type="application/json",
                )
            )
            
            raw_json = response.text if response else ""
            logger.info(f"תגובת המודל (ניסיון {attempt + 1}):\n{raw_json}")  # ✨ לוג מלא
            parsed   = _parse_json(raw_json)
            if parsed is not None:
                logger.info("חילוץ הושלם")
                return _validate(parsed)

            last_error = ValueError("JSON פגום")

        except Exception as e:
            logger.error(f"שגיאה: {e}")
            last_error = e
            time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))

    empty = build_empty_result()
    empty["_error"] = {"value": str(last_error), "confidence": 0.0}  # type: ignore
    return empty


def _extract_direct(model: Any, base64_image: str) -> ExtractionResult:
    """Fallback: חילוץ ישיר מהתמונה."""
    prompts = [STEP2_EXTRACT_PROMPT, RETRY_PROMPT, RETRY_PROMPT]
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        prompt = prompts[min(attempt, len(prompts) - 1)]
        try:
            image_bytes = base64.b64decode(base64_image)
            image_part = {
                "mime_type": "image/jpeg",
                "data": image_bytes
            }
            
            response = model.generate_content(
                [prompt, image_part],
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=2048,  # ✨ הגדלה ל-2048
                )
            )
            
            raw_json = response.text if response else ""
            parsed   = _parse_json(raw_json)
            if parsed is not None:
                return _validate(parsed)
            last_error = ValueError("JSON פגום")

        except Exception as e:
            last_error = e
            time.sleep(RETRY_DELAY_SECONDS)

    empty = build_empty_result()
    empty["_error"] = {"value": str(last_error), "confidence": 0.0}  # type: ignore
    return empty


def _parse_json(text: str) -> dict | None:
    if not text:
        return None
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass
    return None


def _validate(raw: dict) -> ExtractionResult:
    """ולידציה קפדנית — מונעת ערכים מומצאים."""
    result: ExtractionResult = {}

    for field_key, field_def in FIELDS.items():
        if field_key not in raw:
            result[field_key] = {
                "value":      [] if field_def["multi"] else None,
                "confidence": 0.0,
            }
            continue

        field_data = raw[field_key]
        if not isinstance(field_data, dict):
            result[field_key] = {
                "value":      [] if field_def["multi"] else None,
                "confidence": 0.0,
            }
            continue

        value      = field_data.get("value")
        confidence = field_data.get("confidence", 0.0)

        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.0

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
                confidence = max(0.0, confidence - 0.3)
            else:
                value = digits

        elif field_key == "תאריך_קבלה" and value is not None:
            if not re.match(r"^\d{1,2}[./\-]\d{1,2}[./\-]\d{2,4}$", str(value).strip()):
                confidence = max(0.0, confidence - 0.3)

        elif field_key in ("מספר_מרכזי", "מספר_התחייבות") and isinstance(value, list):
            filtered = []
            for v in value:
                v_str = str(v).strip()
                if v_str.count('/') >= 2 or v_str.count('.') >= 2 or v_str.count('-') >= 2:
                    continue
                digits = re.sub(r"\D", "", v_str)
                if len(digits) < 4:
                    continue
                filtered.append(v)
            value = filtered
            
            if len(value) > 3:
                logger.warning(f"{field_key}: {len(value)} ערכים נמצאו, שומר רק 3 ראשונים")
                value = value[:3]
            
            if not value:
                confidence = 0.0

        # סף confidence מאוזן
        if field_key in ("שם_פרטי", "שם_משפחה"):
            min_conf = 0.50
        elif field_key == "תעודת_זהות":
            min_conf = 0.45
        else:
            min_conf = 0.45
            
        if confidence < min_conf:
            value      = [] if field_def["multi"] else None
            confidence = 0.0

        result[field_key] = {"value": value, "confidence": confidence}

    return result

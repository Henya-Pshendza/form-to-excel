"""
app/vision_extractor_multi.py
------------------------------
Multi-provider vision extraction supporting OpenAI, Gemini, and Anthropic.
Two-step extraction:
  Step 1 — reads all text from the image
  Step 2 — extracts structured fields from the raw text + image
"""

from __future__ import annotations

import json
import os
import re
import time
import base64
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv

from config.fields import FIELDS
from config.prompts import STEP1_READ_PROMPT, STEP2_EXTRACT_PROMPT, RETRY_PROMPT
from utils.logger import get_logger

_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = get_logger(__name__)

MAX_RETRIES         = 3
RETRY_DELAY_SECONDS = 2

ExtractionResult = dict[str, dict[str, Any]]
Provider = Literal["openai", "gemini", "anthropic"]


# ═══════════════════════════════════════════════════════════════════════════
# Model Configurations
# ═══════════════════════════════════════════════════════════════════════════

MODELS = {
    "openai": {
        "name": "gpt-4o",
        "api_key_env": "OPENAI_API_KEY",
        "display_name": "OpenAI GPT-4o",
    },
    "gemini": {
        "name": "gemini-3.6-flash",
        "api_key_env": "GEMINI_API_KEY", 
        "display_name": "Google Gemini 3.6 Flash",
    },
    "anthropic": {
        "name": "claude-3-5-sonnet-20241022",
        "api_key_env": "ANTHROPIC_API_KEY",
        "display_name": "Anthropic Claude 3.5 Sonnet",
    }
}


def build_empty_result() -> ExtractionResult:
    result: ExtractionResult = {}
    for field_key, field_def in FIELDS.items():
        result[field_key] = {
            "value":      [] if field_def["multi"] else None,
            "confidence": 0.0,
        }
    return result


def extract_from_image(base64_image: str, provider: Provider = "gemini") -> ExtractionResult:
    """
    Main extraction function that routes to the appropriate provider.
    
    Args:
        base64_image: Base64-encoded image string
        provider: AI provider to use ("openai", "gemini", or "anthropic")
    
    Returns:
        ExtractionResult dictionary with all fields
    """
    if provider not in MODELS:
        raise ValueError(f"Provider '{provider}' not supported. Choose: {list(MODELS.keys())}")
    
    model_config = MODELS[provider]
    api_key = os.getenv(model_config["api_key_env"])
    
    if not api_key:
        raise EnvironmentError(
            f"{model_config['api_key_env']} לא מוגדר ב-Secrets. "
            f"נדרש עבור {model_config['display_name']}"
        )
    
    logger.info(f"משתמש במודל: {model_config['display_name']}")
    
    # Route to appropriate provider
    if provider == "openai":
        return _extract_openai(base64_image, api_key, model_config["name"])
    elif provider == "gemini":
        return _extract_gemini(base64_image, api_key, model_config["name"])
    elif provider == "anthropic":
        return _extract_anthropic(base64_image, api_key, model_config["name"])
    
    raise ValueError(f"Provider {provider} not implemented")


# ═══════════════════════════════════════════════════════════════════════════
# OpenAI Implementation
# ═══════════════════════════════════════════════════════════════════════════

def _extract_openai(base64_image: str, api_key: str, model_name: str) -> ExtractionResult:
    """OpenAI GPT-4o Vision extraction."""
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("חסר: pip install openai")
    
    client = OpenAI(api_key=api_key)
    
    # Step 1: Read all text
    raw_text = _openai_step1_read(client, model_name, base64_image)
    if not raw_text:
        logger.warning("OpenAI שלב 1 נכשל — עובר לחילוץ ישיר")
        return _openai_extract_direct(client, model_name, base64_image)
    
    # Step 2: Extract fields
    return _openai_step2_extract(client, model_name, base64_image, raw_text)


def _openai_step1_read(client: Any, model_name: str, base64_image: str) -> str | None:
    """OpenAI Step 1: Read all text from image."""
    try:
        logger.info("שלב 1 — קריאת טקסט (OpenAI)")
        
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": STEP1_READ_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                        }
                    ]
                }
            ],
            max_tokens=2500,
        )
        
        text = response.choices[0].message.content or ""
        logger.info(f"OpenAI שלב 1 הושלם — {len(text)} תווים")
        logger.info(f"טקסט מלא:\n{text}")
        return text
    except Exception as e:
        logger.error(f"שגיאה OpenAI שלב 1: {e}")
        return None


def _openai_step2_extract(
    client: Any, model_name: str, base64_image: str, raw_text: str
) -> ExtractionResult:
    """OpenAI Step 2: Extract structured fields."""
    prompts = [STEP2_EXTRACT_PROMPT, RETRY_PROMPT, RETRY_PROMPT]
    last_error: Exception | None = None
    
    for attempt in range(MAX_RETRIES):
        prompt = prompts[min(attempt, len(prompts) - 1)]
        try:
            logger.info(f"OpenAI שלב 2 — ניסיון {attempt + 1}/{MAX_RETRIES}")
            
            full_prompt = f"{prompt}\n\nכל הטקסט שקראתי מהטופס:\n{raw_text}\n\nעכשיו חלץ את השדות המבוקשים."
            
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": full_prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                            }
                        ]
                    }
                ],
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            
            raw_json = response.choices[0].message.content or ""
            logger.info(f"OpenAI תגובה (ניסיון {attempt + 1}):\n{raw_json}")
            
            parsed = _parse_json(raw_json)
            if parsed is not None:
                logger.info("OpenAI חילוץ הושלם")
                return _validate(parsed)
            
            last_error = ValueError("JSON פגום")
            
        except Exception as e:
            logger.error(f"שגיאה OpenAI: {e}")
            last_error = e
            time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
    
    empty = build_empty_result()
    empty["_error"] = {"value": str(last_error), "confidence": 0.0}
    return empty


def _openai_extract_direct(client: Any, model_name: str, base64_image: str) -> ExtractionResult:
    """OpenAI direct extraction fallback."""
    prompts = [STEP2_EXTRACT_PROMPT, RETRY_PROMPT, RETRY_PROMPT]
    last_error: Exception | None = None
    
    for attempt in range(MAX_RETRIES):
        prompt = prompts[min(attempt, len(prompts) - 1)]
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                            }
                        ]
                    }
                ],
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            
            raw_json = response.choices[0].message.content or ""
            parsed = _parse_json(raw_json)
            if parsed is not None:
                return _validate(parsed)
            
            last_error = ValueError("JSON פגום")
            
        except Exception as e:
            last_error = e
            time.sleep(RETRY_DELAY_SECONDS)
    
    empty = build_empty_result()
    empty["_error"] = {"value": str(last_error), "confidence": 0.0}
    return empty


# ═══════════════════════════════════════════════════════════════════════════
# Gemini Implementation
# ═══════════════════════════════════════════════════════════════════════════

def _extract_gemini(base64_image: str, api_key: str, model_name: str) -> ExtractionResult:
    """Google Gemini Vision extraction."""
    try:
        import google.generativeai as genai
    except ImportError:
        raise ImportError("חסר: pip install google-generativeai")
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    
    # Step 1: Read all text
    raw_text = _gemini_step1_read(model, base64_image)
    if not raw_text:
        logger.warning("Gemini שלב 1 נכשל — עובר לחילוץ ישיר")
        return _gemini_extract_direct(model, base64_image)
    
    # Step 2: Extract fields
    return _gemini_step2_extract(model, base64_image, raw_text)


def _gemini_step1_read(model: Any, base64_image: str) -> str | None:
    """Gemini Step 1: Read all text from image."""
    try:
        logger.info("שלב 1 — קריאת טקסט (Gemini)")
        
        image_bytes = base64.b64decode(base64_image)
        image_part = {
            "mime_type": "image/jpeg",
            "data": image_bytes
        }
        
        response = model.generate_content(
            [STEP1_READ_PROMPT, image_part],
            generation_config={"max_output_tokens": 2500}
        )
        
        text = response.text if response else ""
        logger.info(f"Gemini שלב 1 הושלם — {len(text)} תווים")
        logger.info(f"טקסט מלא:\n{text}")
        return text
    except Exception as e:
        logger.error(f"שגיאה Gemini שלב 1: {e}")
        return None


def _gemini_step2_extract(model: Any, base64_image: str, raw_text: str) -> ExtractionResult:
    """Gemini Step 2: Extract structured fields."""
    prompts = [STEP2_EXTRACT_PROMPT, RETRY_PROMPT, RETRY_PROMPT]
    last_error: Exception | None = None
    
    for attempt in range(MAX_RETRIES):
        prompt = prompts[min(attempt, len(prompts) - 1)]
        try:
            logger.info(f"Gemini שלב 2 — ניסיון {attempt + 1}/{MAX_RETRIES}")
            
            full_prompt = f"{prompt}\n\nכל הטקסט שקראתי מהטופס:\n{raw_text}\n\nעכשיו חלץ את השדות המבוקשים."
            
            image_bytes = base64.b64decode(base64_image)
            image_part = {
                "mime_type": "image/jpeg",
                "data": image_bytes
            }
            
            response = model.generate_content(
                [full_prompt, image_part],
                generation_config={
                    "max_output_tokens": 2048,
                    "response_mime_type": "application/json",
                }
            )
            
            raw_json = response.text if response else ""
            logger.info(f"Gemini תגובה (ניסיון {attempt + 1}):\n{raw_json}")
            
            parsed = _parse_json(raw_json)
            if parsed is not None:
                logger.info("Gemini חילוץ הושלם")
                return _validate(parsed)
            
            last_error = ValueError("JSON פגום")
            
        except Exception as e:
            logger.error(f"שגיאה Gemini: {e}")
            last_error = e
            time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
    
    empty = build_empty_result()
    empty["_error"] = {"value": str(last_error), "confidence": 0.0}
    return empty


def _gemini_extract_direct(model: Any, base64_image: str) -> ExtractionResult:
    """Gemini direct extraction fallback."""
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
                generation_config={"max_output_tokens": 2048}
            )
            
            raw_json = response.text if response else ""
            parsed = _parse_json(raw_json)
            if parsed is not None:
                return _validate(parsed)
            
            last_error = ValueError("JSON פגום")
            
        except Exception as e:
            last_error = e
            time.sleep(RETRY_DELAY_SECONDS)
    
    empty = build_empty_result()
    empty["_error"] = {"value": str(last_error), "confidence": 0.0}
    return empty


# ═══════════════════════════════════════════════════════════════════════════
# Anthropic Implementation
# ═══════════════════════════════════════════════════════════════════════════

def _extract_anthropic(base64_image: str, api_key: str, model_name: str) -> ExtractionResult:
    """Anthropic Claude Vision extraction."""
    try:
        from anthropic import Anthropic
    except ImportError:
        raise ImportError("חסר: pip install anthropic")
    
    client = Anthropic(api_key=api_key)
    
    # Step 1: Read all text
    raw_text = _anthropic_step1_read(client, model_name, base64_image)
    if not raw_text:
        logger.warning("Claude שלב 1 נכשל — עובר לחילוץ ישיר")
        return _anthropic_extract_direct(client, model_name, base64_image)
    
    # Step 2: Extract fields
    return _anthropic_step2_extract(client, model_name, base64_image, raw_text)


def _anthropic_step1_read(client: Any, model_name: str, base64_image: str) -> str | None:
    """Anthropic Step 1: Read all text from image."""
    try:
        logger.info("שלב 1 — קריאת טקסט (Claude)")
        
        response = client.messages.create(
            model=model_name,
            max_tokens=2500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": STEP1_READ_PROMPT
                        }
                    ],
                }
            ],
        )
        
        text = response.content[0].text if response.content else ""
        logger.info(f"Claude שלב 1 הושלם — {len(text)} תווים")
        logger.info(f"טקסט מלא:\n{text}")
        return text
    except Exception as e:
        logger.error(f"שגיאה Claude שלב 1: {e}")
        return None


def _anthropic_step2_extract(
    client: Any, model_name: str, base64_image: str, raw_text: str
) -> ExtractionResult:
    """Anthropic Step 2: Extract structured fields."""
    prompts = [STEP2_EXTRACT_PROMPT, RETRY_PROMPT, RETRY_PROMPT]
    last_error: Exception | None = None
    
    for attempt in range(MAX_RETRIES):
        prompt = prompts[min(attempt, len(prompts) - 1)]
        try:
            logger.info(f"Claude שלב 2 — ניסיון {attempt + 1}/{MAX_RETRIES}")
            
            full_prompt = f"{prompt}\n\nכל הטקסט שקראתי מהטופס:\n{raw_text}\n\nעכשיו חלץ את השדות המבוקשים. החזר JSON בלבד."
            
            response = client.messages.create(
                model=model_name,
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": base64_image,
                                },
                            },
                            {
                                "type": "text",
                                "text": full_prompt
                            }
                        ],
                    }
                ],
            )
            
            raw_json = response.content[0].text if response.content else ""
            logger.info(f"Claude תגובה (ניסיון {attempt + 1}):\n{raw_json}")
            
            parsed = _parse_json(raw_json)
            if parsed is not None:
                logger.info("Claude חילוץ הושלם")
                return _validate(parsed)
            
            last_error = ValueError("JSON פגום")
            
        except Exception as e:
            logger.error(f"שגיאה Claude: {e}")
            last_error = e
            time.sleep(RETRY_DELAY_SECONDS * (attempt + 1))
    
    empty = build_empty_result()
    empty["_error"] = {"value": str(last_error), "confidence": 0.0}
    return empty


def _anthropic_extract_direct(client: Any, model_name: str, base64_image: str) -> ExtractionResult:
    """Anthropic direct extraction fallback."""
    prompts = [STEP2_EXTRACT_PROMPT, RETRY_PROMPT, RETRY_PROMPT]
    last_error: Exception | None = None
    
    for attempt in range(MAX_RETRIES):
        prompt = prompts[min(attempt, len(prompts) - 1)]
        try:
            response = client.messages.create(
                model=model_name,
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": base64_image,
                                },
                            },
                            {
                                "type": "text",
                                "text": f"{prompt}\n\nהחזר JSON בלבד."
                            }
                        ],
                    }
                ],
            )
            
            raw_json = response.content[0].text if response.content else ""
            parsed = _parse_json(raw_json)
            if parsed is not None:
                return _validate(parsed)
            
            last_error = ValueError("JSON פגום")
            
        except Exception as e:
            last_error = e
            time.sleep(RETRY_DELAY_SECONDS)
    
    empty = build_empty_result()
    empty["_error"] = {"value": str(last_error), "confidence": 0.0}
    return empty


# ═══════════════════════════════════════════════════════════════════════════
# Shared Utilities
# ═══════════════════════════════════════════════════════════════════════════

def _parse_json(text: str) -> dict | None:
    """Parse JSON from text, with fallback extraction."""
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
    """Validation and filtering to prevent hallucinated values."""
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

        # Field-specific validation
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
                logger.warning(f"{field_key}: {len(value)} ערכים, שומר 3 ראשונים")
                value = value[:3]
            
            if not value:
                confidence = 0.0

        # Confidence thresholds
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

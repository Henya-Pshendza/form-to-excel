"""
app/name_extractor.py
---------------------
חילוץ ממוקד של שם פרטי ושם משפחה עם Claude.

האסטרטגיה:
1. שולחים את הטופס המלא ומבקשים קואורדינטות של אזור השם
2. חותכים ומגדילים את האזור
3. שולחים את האזור החתוך לקריאה מדויקת
"""

from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path
from typing import Any

from PIL import Image
from dotenv import load_dotenv

from utils.logger import get_logger

_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = get_logger(__name__)

MODEL = "claude-3-5-sonnet-20241022"


def extract_name_focused(image: Image.Image) -> dict[str, Any]:
    """
    מנסה לחלץ שם פרטי ושם משפחה עם crop ממוקד.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return _empty_names()

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        region = _find_name_region(client, image)
        if region is None:
            return _read_name_from_full_image(client, image)

        cropped = _crop_and_zoom(image, region)
        if cropped is None:
            return _empty_names()

        return _read_name_from_crop(client, cropped)

    except Exception as e:
        logger.debug(f"name_extractor נכשל: {e}")
        return _empty_names()


def _find_name_region(client, image: Image.Image) -> dict | None:
    """מוצא את הקואורדינטות של אזור השם בטופס."""
    b64 = _image_to_base64(image, quality=60)

    prompt = """Look at this Israeli medical form.
Find the area where the PATIENT NAME is written (handwritten or printed Hebrew name).
The name is usually next to a label like: שם, שם פרטי, שם החולה, מנוי, לכבוד

Return ONLY a JSON object with the bounding box as percentages of image size:
{"x1": 0, "y1": 10, "x2": 80, "y2": 20}

Where x1,y1 is top-left and x2,y2 is bottom-right, values 0-100.
If you cannot find a name area, return: {"x1": 0, "y1": 0, "x2": 0, "y2": 0}
Return ONLY the JSON, nothing else."""

    try:
        message = client.messages.create(
            model      = MODEL,
            max_tokens = 100,
            messages   = [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": "image/jpeg",
                            "data":       b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        text  = message.content[0].text if message.content else ""
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start == -1:
            return None
        data = json.loads(text[start:end])
        if data.get("x2", 0) == 0 and data.get("y2", 0) == 0:
            return None
        return data

    except Exception as e:
        logger.debug(f"_find_name_region נכשל: {e}")
        return None


def _crop_and_zoom(image: Image.Image, region: dict) -> Image.Image | None:
    """חותך את האזור ומגדיל אותו."""
    try:
        w, h = image.size
        pad  = 20
        x1   = max(0, int(region["x1"] / 100 * w) - pad)
        y1   = max(0, int(region["y1"] / 100 * h) - pad)
        x2   = min(w, int(region["x2"] / 100 * w) + pad)
        y2   = min(h, int(region["y2"] / 100 * h) + pad)

        if x2 <= x1 or y2 <= y1:
            return None

        cropped = image.crop((x1, y1, x2, y2))

        # הגדלה אם קטן מדי
        cw, ch = cropped.size
        if ch < 120:
            scale   = 120 / ch
            cropped = cropped.resize((int(cw * scale), 120), Image.LANCZOS)

        return cropped
    except Exception as e:
        logger.debug(f"_crop_and_zoom נכשל: {e}")
        return None


def _read_name_from_crop(client, cropped: Image.Image) -> dict[str, Any]:
    """קורא את השם מהאזור החתוך."""
    b64 = _image_to_base64(cropped, quality=90)

    prompt = """This is a zoomed crop from an Israeli medical form showing the patient name area.
Read the HANDWRITTEN or PRINTED Hebrew patient name you see.

Return ONLY JSON:
{"first_name": "ישראל", "last_name": "ישראלי", "confidence": 0.85}

If only one part visible: {"first_name": "ישראל", "last_name": null, "confidence": 0.8}
If completely unreadable: {"first_name": null, "last_name": null, "confidence": 0.0}

Rules:
- confidence = how clearly you can read it (0.0-1.0)
- If confidence < 0.7, set value to null
- Return ONLY the JSON, nothing else"""

    try:
        message = client.messages.create(
            model      = MODEL,
            max_tokens = 100,
            messages   = [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": "image/jpeg",
                            "data":       b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        text  = message.content[0].text if message.content else ""
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start == -1:
            return _empty_names()

        data       = json.loads(text[start:end])
        confidence = float(data.get("confidence", 0.0))
        first      = data.get("first_name")
        last       = data.get("last_name")

        logger.info(f"שם חולץ מ-crop: {first} {last} ({confidence:.0%})")
        return {
            "שם_פרטי":  {"value": first, "confidence": confidence},
            "שם_משפחה": {"value": last,  "confidence": confidence},
        }
    except Exception as e:
        logger.debug(f"_read_name_from_crop נכשל: {e}")
        return _empty_names()


def _read_name_from_full_image(client, image: Image.Image) -> dict[str, Any]:
    """Fallback: קריאת שם מהתמונה המלאה."""
    b64 = _image_to_base64(image, quality=75)

    prompt = """Look at this Israeli medical form.
Find and read the PATIENT NAME — it may be handwritten Hebrew next to שם/שם פרטי/מנוי.

Return ONLY JSON:
{"first_name": "ישראל", "last_name": "ישראלי", "confidence": 0.85}

If unreadable: {"first_name": null, "last_name": null, "confidence": 0.0}
Return ONLY the JSON."""

    try:
        message = client.messages.create(
            model      = MODEL,
            max_tokens = 100,
            messages   = [{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type":       "base64",
                            "media_type": "image/jpeg",
                            "data":       b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        text  = message.content[0].text if message.content else ""
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start == -1:
            return _empty_names()

        data       = json.loads(text[start:end])
        confidence = float(data.get("confidence", 0.0))
        return {
            "שם_פרטי":  {"value": data.get("first_name"), "confidence": confidence},
            "שם_משפחה": {"value": data.get("last_name"),  "confidence": confidence},
        }
    except Exception:
        return _empty_names()


def _image_to_base64(image: Image.Image, quality: int = 85) -> str:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def _empty_names() -> dict[str, Any]:
    return {
        "שם_פרטי":  {"value": None, "confidence": 0.0},
        "שם_משפחה": {"value": None, "confidence": 0.0},
    }

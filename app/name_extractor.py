"""
app/name_extractor.py
---------------------
חילוץ ממוקד של שם פרטי ושם משפחה.

האסטרטגיה:
1. שולחים את הטופס המלא ומבקשים את הקואורדינטות של אזור השם
2. חותכים את האזור ומגדילים אותו
3. שולחים את האזור החתוך בלבד לקריאה מדויקת

אם השלב הזה נכשל — מחזירים null ומשאירים לתיקון ידני.
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from typing import Any

from PIL import Image
from dotenv import load_dotenv

from utils.logger import get_logger

_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = get_logger(__name__)


def extract_name_focused(image: Image.Image) -> dict[str, Any]:
    """
    מנסה לחלץ שם פרטי ושם משפחה באמצעות crop ממוקד.

    Args:
        image: PIL.Image של הטופס המלא

    Returns:
        { "שם_פרטי": {"value": ..., "confidence": ...},
          "שם_משפחה": {"value": ..., "confidence": ...} }
        או None אם הניסיון נכשל
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _empty_names()

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        # שלב 1: מציאת אזור השם בטופס המלא
        region = _find_name_region(client, image)
        if region is None:
            logger.debug("לא מצאתי אזור שם — עובר לקריאה ישירה מהטופס המלא")
            return _read_name_from_full_image(client, image)

        # שלב 2: חיתוך והגדלה של האזור
        cropped = _crop_and_zoom(image, region)
        if cropped is None:
            return _empty_names()

        # שלב 3: קריאת השם מהאזור החתוך
        return _read_name_from_crop(client, cropped)

    except Exception as e:
        logger.debug(f"name_extractor נכשל: {e}")
        return _empty_names()


def _find_name_region(client, image: Image.Image) -> dict | None:
    """
    שולח את הטופס המלא ומבקש את מיקום שורת השם.
    מחזיר { "x1": %, "y1": %, "x2": %, "y2": % } — אחוזים מגודל התמונה.
    """
    b64 = _image_to_base64(image, quality=60)  # איכות נמוכה — מהיר יותר

    prompt = """Look at this Israeli medical form.
Find the area where the PATIENT NAME is written (handwritten or printed Hebrew name).
The name is usually next to a label like: שם, שם פרטי, שם החולה, מנוי, לכבוד

Return ONLY a JSON object with the bounding box as percentages of image size:
{"x1": 0, "y1": 10, "x2": 80, "y2": 20}

Where x1,y1 is top-left and x2,y2 is bottom-right, values 0-100.
If you cannot find a name area, return: {"x1": 0, "y1": 0, "x2": 0, "y2": 0}
Return ONLY the JSON, nothing else."""

    try:
        response = client.chat.completions.create(
            model      = "gpt-4o",
            max_tokens = 100,
            temperature= 0,
            messages   = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url":    f"data:image/jpeg;base64,{b64}",
                        "detail": "low",  # low — מהיר וזול
                    }},
                ],
            }],
        )
        import json
        text = response.choices[0].message.content or ""
        # מחפשים JSON בתשובה
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start == -1:
            return None
        data = json.loads(text[start:end])

        # בדיקה שהאזור לא אפס
        if data.get("x2", 0) == 0 and data.get("y2", 0) == 0:
            return None

        return data

    except Exception as e:
        logger.debug(f"_find_name_region נכשל: {e}")
        return None


def _crop_and_zoom(image: Image.Image, region: dict) -> Image.Image | None:
    """
    חותך את האזור הנתון ומגדיל אותו לגובה מינימלי של 200px.

    Args:
        image:  תמונה מלאה
        region: { x1%, y1%, x2%, y2% }

    Returns:
        PIL.Image חתוך ומוגדל, או None אם האזור לא תקין
    """
    try:
        w, h = image.size

        x1 = int(region["x1"] / 100 * w)
        y1 = int(region["y1"] / 100 * h)
        x2 = int(region["x2"] / 100 * w)
        y2 = int(region["y2"] / 100 * h)

        # הוספת padding
        pad = 20
        x1 = max(0, x1 - pad)
        y1 = max(0, y1 - pad)
        x2 = min(w, x2 + pad)
        y2 = min(h, y2 + pad)

        if x2 <= x1 or y2 <= y1:
            return None

        cropped = image.crop((x1, y1, x2, y2))

        # הגדלה אם קטן מדי
        crop_w, crop_h = cropped.size
        if crop_h < 120:
            scale  = 120 / crop_h
            new_w  = int(crop_w * scale)
            new_h  = 120
            cropped = cropped.resize((new_w, new_h), Image.LANCZOS)

        logger.debug(f"חתכתי אזור שם: {x1},{y1} → {x2},{y2}, גודל: {cropped.size}")
        return cropped

    except Exception as e:
        logger.debug(f"_crop_and_zoom נכשל: {e}")
        return None


def _read_name_from_crop(client, cropped: Image.Image) -> dict[str, Any]:
    """
    שולח את האזור החתוך ומבקש לקרוא את השם.
    """
    b64 = _image_to_base64(cropped, quality=90)  # איכות גבוהה לכתב יד

    prompt = """This is a zoomed crop from an Israeli medical form showing the patient name area.
Read the HANDWRITTEN or PRINTED Hebrew patient name you see.

Return ONLY JSON:
{"first_name": "ישראל", "last_name": "ישראלי", "confidence": 0.85}

If the name has only one part visible: {"first_name": "ישראל", "last_name": null, "confidence": 0.8}
If completely unreadable: {"first_name": null, "last_name": null, "confidence": 0.0}

Rules:
- confidence = how clearly you can read it (0.0-1.0)
- If confidence < 0.7, set the value to null
- Return ONLY the JSON, nothing else"""

    try:
        response = client.chat.completions.create(
            model      = "gpt-4o",
            max_tokens = 100,
            temperature= 0,
            messages   = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url":    f"data:image/jpeg;base64,{b64}",
                        "detail": "high",
                    }},
                ],
            }],
        )
        import json as _json
        text  = response.choices[0].message.content or ""
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start == -1:
            return _empty_names()

        data       = _json.loads(text[start:end])
        confidence = float(data.get("confidence", 0.0))
        first      = data.get("first_name")
        last       = data.get("last_name")

        logger.info(f"שם חולץ מ-crop: {first} {last} (confidence={confidence:.0%})")

        return {
            "שם_פרטי":  {"value": first, "confidence": confidence},
            "שם_משפחה": {"value": last,  "confidence": confidence},
        }

    except Exception as e:
        logger.debug(f"_read_name_from_crop נכשל: {e}")
        return _empty_names()


def _read_name_from_full_image(client, image: Image.Image) -> dict[str, Any]:
    """
    Fallback: מנסה לקרוא שם ישירות מהתמונה המלאה בלי crop.
    """
    b64 = _image_to_base64(image, quality=75)

    prompt = """Look at this Israeli medical form.
Find and read the PATIENT NAME — it may be handwritten Hebrew next to a label like שם/שם פרטי/מנוי.

Return ONLY JSON:
{"first_name": "ישראל", "last_name": "ישראלי", "confidence": 0.85}

If unreadable or not found: {"first_name": null, "last_name": null, "confidence": 0.0}
Return ONLY the JSON."""

    try:
        response = client.chat.completions.create(
            model      = "gpt-4o",
            max_tokens = 100,
            temperature= 0,
            messages   = [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {
                        "url":    f"data:image/jpeg;base64,{b64}",
                        "detail": "high",
                    }},
                ],
            }],
        )
        import json as _json
        text  = response.choices[0].message.content or ""
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start == -1:
            return _empty_names()

        data       = _json.loads(text[start:end])
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

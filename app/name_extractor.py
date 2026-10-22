"""
app/name_extractor.py
---------------------
חילוץ ממוקד של שם פרטי ושם משפחה עם GPT-4o.

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


def extract_name_focused(image: Image.Image) -> dict[str, Any]:
    """מנסה לחלץ שם פרטי ושם משפחה עם crop ממוקד."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _empty_names()
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        region = _find_name_region(client, image)
        if region is None:
            return _read_name_direct(client, image)
        cropped = _crop_and_zoom(image, region)
        if cropped is None:
            return _empty_names()
        return _read_name_from_crop(client, cropped)
    except Exception as e:
        logger.debug(f"name_extractor נכשל: {e}")
        return _empty_names()


def _find_name_region(client, image: Image.Image) -> dict | None:
    """מוצא קואורדינטות אזור השם."""
    b64    = _to_b64(image, quality=60)
    prompt = """Look at this Israeli medical form.
Find the area where the PATIENT NAME is written (handwritten or printed Hebrew).
It's usually next to a label: שם, שם פרטי, שם החולה, מנוי, לכבוד

Return ONLY JSON with bounding box as percentage of image size:
{"x1": 5, "y1": 12, "x2": 75, "y2": 22}
If not found: {"x1": 0, "y1": 0, "x2": 0, "y2": 0}
JSON only, nothing else."""

    try:
        resp  = client.chat.completions.create(
            model      = "gpt-4o",
            max_tokens = 80,
            temperature= 0,
            messages   = [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}},
            ]}],
        )
        text  = resp.choices[0].message.content or ""
        start = text.find("{"); end = text.rfind("}") + 1
        if start == -1: return None
        data  = json.loads(text[start:end])
        return None if (data.get("x2", 0) == 0 and data.get("y2", 0) == 0) else data
    except Exception as e:
        logger.debug(f"_find_name_region: {e}")
        return None


def _crop_and_zoom(image: Image.Image, region: dict) -> Image.Image | None:
    """חותך ומגדיל."""
    try:
        w, h  = image.size
        pad   = 20
        x1    = max(0, int(region["x1"] / 100 * w) - pad)
        y1    = max(0, int(region["y1"] / 100 * h) - pad)
        x2    = min(w, int(region["x2"] / 100 * w) + pad)
        y2    = min(h, int(region["y2"] / 100 * h) + pad)
        if x2 <= x1 or y2 <= y1: return None
        crop  = image.crop((x1, y1, x2, y2))
        cw, ch = crop.size
        if ch < 120:
            scale = 120 / ch
            crop  = crop.resize((int(cw * scale), 120), Image.LANCZOS)
        return crop
    except Exception as e:
        logger.debug(f"_crop_and_zoom: {e}")
        return None


def _read_name_from_crop(client, cropped: Image.Image) -> dict[str, Any]:
    """קורא שם מה-crop."""
    b64    = _to_b64(cropped, quality=90)
    prompt = """This is a zoomed crop from an Israeli medical form showing the patient name area.
Read the HANDWRITTEN or PRINTED Hebrew patient name.

Return ONLY JSON:
{"first_name": "ישראל", "last_name": "ישראלי", "confidence": 0.85}

If unreadable: {"first_name": null, "last_name": null, "confidence": 0.0}
If confidence < 0.7 set value to null. JSON only."""

    try:
        resp  = client.chat.completions.create(
            model="gpt-4o", max_tokens=80, temperature=0,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
            ]}],
        )
        text  = resp.choices[0].message.content or ""
        start = text.find("{"); end = text.rfind("}") + 1
        if start == -1: return _empty_names()
        data  = json.loads(text[start:end])
        conf  = float(data.get("confidence", 0.0))
        logger.info(f"שם מ-crop: {data.get('first_name')} {data.get('last_name')} ({conf:.0%})")
        return {
            "שם_פרטי":  {"value": data.get("first_name"), "confidence": conf},
            "שם_משפחה": {"value": data.get("last_name"),  "confidence": conf},
        }
    except Exception as e:
        logger.debug(f"_read_name_from_crop: {e}")
        return _empty_names()


def _read_name_direct(client, image: Image.Image) -> dict[str, Any]:
    """Fallback: קריאה ישירה מהתמונה המלאה."""
    b64    = _to_b64(image, quality=75)
    prompt = """Look at this Israeli medical form.
Find and read the PATIENT NAME — handwritten Hebrew next to שם/שם פרטי/מנוי/לכבוד.

Return ONLY JSON:
{"first_name": "ישראל", "last_name": "ישראלי", "confidence": 0.85}
If unreadable: {"first_name": null, "last_name": null, "confidence": 0.0}
JSON only."""

    try:
        resp  = client.chat.completions.create(
            model="gpt-4o", max_tokens=80, temperature=0,
            messages=[{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "high"}},
            ]}],
        )
        text  = resp.choices[0].message.content or ""
        start = text.find("{"); end = text.rfind("}") + 1
        if start == -1: return _empty_names()
        data  = json.loads(text[start:end])
        conf  = float(data.get("confidence", 0.0))
        return {
            "שם_פרטי":  {"value": data.get("first_name"), "confidence": conf},
            "שם_משפחה": {"value": data.get("last_name"),  "confidence": conf},
        }
    except Exception:
        return _empty_names()


def _to_b64(image: Image.Image, quality: int = 85) -> str:
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")


def _empty_names() -> dict[str, Any]:
    return {
        "שם_פרטי":  {"value": None, "confidence": 0.0},
        "שם_משפחה": {"value": None, "confidence": 0.0},
    }

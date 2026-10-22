"""
app/pipeline.py
---------------
מתאם הראשי — מריץ את כל שלבי העיבוד על קובץ אחד.

הזרימה לכל קובץ:
  1. load   — PDF/תמונה → רשימת תמונות PIL
  2. process — עיבוד מקדים (deskew, contrast, resize)
  3. encode  — PIL → base64
  4. extract — GPT-4o Vision → JSON גולמי
  5. normalize — JSON → ערכים תקינים
  6. flag    — הוספת status לכל שדה

הפונקציה הראשית מחזירה רשימת טפסים מעובדים,
מוכנים לתצוגה ולייצוא.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.pdf_handler import load_input_file
from app.image_processor import preprocess_image, image_to_base64
from app.vision_extractor_multi import extract_from_image
from app.normalizer import normalize_result
from app.confidence_handler import apply_confidence_flags
from utils.logger import get_logger

# ✨ טעינת משתני סביבה מ-.env
_PROJECT_ROOT = Path(__file__).parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

logger = get_logger(__name__)


def process_file(
    file_path: str | Path,
    progress_callback=None,
    ai_provider: str = "gemini",
) -> list[dict[str, Any]]:
    """
    מעבד קובץ PDF או תמונה אחד ומחזיר רשימת טפסים מחולצים.

    PDF עם N דפים → רשימה של עד N טפסים.
    תמונה בודדת → רשימה עם טופס אחד.

    Args:
        file_path:         נתיב לקובץ (PDF / JPG / PNG / ...)
        progress_callback: פונקציה אופציונלית לדיווח התקדמות.
                           חתימה: callback(current: int, total: int, message: str)
        ai_provider:       ספק AI ("openai", "gemini", "anthropic")

    Returns:
        רשימת מילונות, אחד לכל טופס:
        {
          "source_file": שם הקובץ,
          "page":        מספר הדף,
          "שם_פרטי":     {"value": ..., "confidence": ..., "status": FieldStatus},
          ...
        }
    """
    file_path = Path(file_path)
    logger.info(f"=== מתחיל עיבוד: {file_path.name} עם {ai_provider} ===")

    results: list[dict[str, Any]] = []

    # ── שלב 1: טעינה ─────────────────────────────────────────────────────────
    _report(progress_callback, 0, 1, f"טוען קובץ: {file_path.name}")
    try:
        pages = load_input_file(file_path)
    except Exception as e:
        logger.error(f"שגיאה בטעינת קובץ {file_path.name}: {e}")
        raise

    total_pages = len(pages)
    logger.info(f"{total_pages} דפים נטענו")

    # ── עיבוד דף אחר דף ─────────────────────────────────────────────────────
    for page_idx, page_image in enumerate(pages):
        page_num = page_idx + 1
        msg = f"מעבד דף {page_num}/{total_pages} ({file_path.name})"
        _report(progress_callback, page_idx, total_pages, msg)
        logger.info(f"--- דף {page_num}/{total_pages} ---")

        try:
            form_data = _process_single_page(
                page_image  = page_image,
                source_file = file_path.name,
                page_num    = page_num,
                ai_provider = ai_provider,
            )
            results.append(form_data)

            # המתנה קצרה בין דפים — מונעת rate limit
            if page_idx < total_pages - 1:
                time.sleep(1.5)

        except Exception as e:
            # שגיאה בדף אחד לא עוצרת את כל הסריקה
            logger.error(f"שגיאה בדף {page_num}: {e}")
            results.append(_error_form(file_path.name, page_num, str(e)))

    _report(progress_callback, total_pages, total_pages, "עיבוד הושלם")
    logger.info(f"=== הסתיים: {len(results)} טפסים חולצו ===")
    return results


def process_multiple_files(
    file_paths: list[str | Path],
    progress_callback=None,
    ai_provider: str = "gemini",
) -> list[dict[str, Any]]:
    """
    מעבד מספר קבצים ומחזיר רשימה מאוחדת של כל הטפסים.

    Args:
        file_paths:        רשימת נתיבים לקבצים
        progress_callback: פונקציה אופציונלית לדיווח התקדמות.
                           חתימה: callback(current: int, total: int, message: str)
        ai_provider:       ספק AI ("openai", "gemini", "anthropic")

    Returns:
        רשימה מאוחדת של כל הטפסים מכל הקבצים
    """
    all_results: list[dict[str, Any]] = []
    total_files = len(file_paths)

    for file_idx, file_path in enumerate(file_paths):
        file_name = Path(file_path).name
        _report(
            progress_callback,
            file_idx,
            total_files,
            f"מעבד קובץ {file_idx + 1}/{total_files}: {file_name}",
        )

        try:
            file_results = process_file(file_path, progress_callback, ai_provider)
            all_results.extend(file_results)
        except Exception as e:
            logger.error(f"כישלון בקובץ {file_name}: {e}")
            all_results.append(_error_form(file_name, 1, str(e)))

    _report(
        progress_callback,
        total_files,
        total_files,
        f"סיום — {len(all_results)} טפסים עובדו",
    )
    return all_results


# ─────────────────────────────────────────────────────────────────────────────
# פונקציות פנימיות
# ─────────────────────────────────────────────────────────────────────────────

def _process_single_page(
    page_image: Any,   # PIL.Image
    source_file: str,
    page_num: int,
    ai_provider: str = "gemini",
) -> dict[str, Any]:
    """
    מעבד דף בודד דרך כל שלבי ה-pipeline.

    Args:
        page_image:  PIL.Image של הדף
        source_file: שם קובץ המקור (לתיעוד בלבד)
        page_num:    מספר הדף
        ai_provider: ספק AI ("openai", "gemini", "anthropic")

    Returns:
        מילון עם כל שדות הטופס + metadata
    """
    # שלב 2: עיבוד מקדים
    logger.debug("מעבד תמונה (deskew, contrast, resize)")
    processed = preprocess_image(page_image)

    # שלב 3: קידוד base64 לשליחה ל-API
    logger.debug("מקודד תמונה ל-base64")
    b64_image = image_to_base64(processed)

    # שלב 4: חילוץ עם AI Vision
    logger.debug(f"שולח ל-{ai_provider} Vision")
    raw_extraction = extract_from_image(b64_image, provider=ai_provider)

    # שלב 5: נרמול
    logger.debug("מנרמל ערכים")
    normalized = normalize_result(raw_extraction)

    # שלב 6: סימון confidence
    logger.debug("מחיל סימוני ביטחון")
    flagged = apply_confidence_flags(normalized)

    # שלב 7: אם שם חסר — ניסיון ממוקד עם crop
    name_missing = (
        not flagged.get("שם_פרטי", {}).get("value") or
        not flagged.get("שם_משפחה", {}).get("value")
    )
    if name_missing:
        logger.debug("שם חסר — מנסה חילוץ ממוקד")
        try:
            from app.name_extractor import extract_name_focused
            name_result = extract_name_focused(page_image)
            for field in ("שם_פרטי", "שם_משפחה"):
                extracted = name_result.get(field, {})
                if extracted.get("value") and not flagged.get(field, {}).get("value"):
                    # מחיל סטטוס על התוצאה החדשה
                    from app.confidence_handler import _determine_status
                    from config.fields import FIELDS
                    status = _determine_status(
                        field_key  = field,
                        field_def  = FIELDS[field],
                        value      = extracted["value"],
                        confidence = extracted["confidence"],
                        has_error  = False,
                    )
                    flagged[field] = {
                        "value":      extracted["value"],
                        "confidence": extracted["confidence"],
                        "status":     status,
                    }
                    logger.info(f"שם חולץ מ-crop: {field} = {extracted['value']}")
        except Exception as e:
            logger.debug(f"חילוץ שם ממוקד נכשל: {e}")

    # הוספת metadata
    flagged["source_file"] = source_file
    flagged["page"]        = page_num

    return flagged


def _error_form(source_file: str, page_num: int, error_msg: str) -> dict[str, Any]:
    """
    יוצר רשומת טופס עם שגיאה — לכל דף שנכשל לחלוטין.
    כך הלבורנטית רואה שהיה דף ויכולה לבדוק ידנית.

    Args:
        source_file: שם הקובץ
        page_num:    מספר הדף
        error_msg:   תיאור השגיאה

    Returns:
        מילון טופס ריק עם סטטוס שגיאה
    """
    from config.fields import FIELDS
    from app.confidence_handler import FieldStatus

    form: dict[str, Any] = {
        "source_file": source_file,
        "page":        page_num,
        "_error":      {"value": error_msg, "confidence": 0.0},
    }

    for field_key, field_def in FIELDS.items():
        empty_val: Any = [] if field_def["multi"] else None
        form[field_key] = {
            "value":      empty_val,
            "confidence": 0.0,
            "status":     FieldStatus.ERROR,
        }

    return form


def _report(callback, current: int, total: int, message: str) -> None:
    """
    קורא ל-progress_callback אם הוגדר, אחרת לוגים.

    Args:
        callback: פונקציה או None
        current:  ערך נוכחי
        total:    ערך מקסימלי
        message:  הודעה לתצוגה
    """
    logger.debug(f"התקדמות {current}/{total}: {message}")
    if callable(callback):
        try:
            callback(current, total, message)
        except Exception:
            pass   # לא עוצרים אם ה-callback נכשל

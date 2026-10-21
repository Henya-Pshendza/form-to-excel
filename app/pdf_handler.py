"""
app/pdf_handler.py
------------------
ממיר PDF לרשימת תמונות PIL — דף אחד = תמונה אחת.

תומך בשני מצבים:
1. pdf2image  — איכות גבוהה, דורש Poppler
2. pdfplumber — fallback אם Poppler לא מותקן, מרנדר דף כתמונה

כל תמונה מוחזרת כ-PIL.Image בפורמט RGB.
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator

from PIL import Image

from utils.logger import get_logger

logger = get_logger(__name__)

# DPI לרנדור PDF — 200 מספיק לרוב הטפסים, 300 לסריקות עמומות
DEFAULT_DPI = 200


def pdf_to_images(pdf_path: str | Path, dpi: int = DEFAULT_DPI) -> list[Image.Image]:
    """
    ממיר PDF לרשימת תמונות PIL, דף לכל תמונה.

    מנסה pdf2image תחילה (איכות מיטבית).
    אם Poppler לא זמין — עובר ל-pdfplumber כ-fallback.

    Args:
        pdf_path: נתיב לקובץ PDF
        dpi:      רזולוציה לרנדור (ברירת מחדל 200)

    Returns:
        רשימת תמונות PIL.Image (RGB), אחת לכל דף

    Raises:
        FileNotFoundError: אם הקובץ לא קיים
        ValueError:        אם הקובץ ריק או לא ניתן לפרסר
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF לא נמצא: {pdf_path}")

    logger.info(f"ממיר PDF לתמונות: {pdf_path.name}")

    # ניסיון ראשון: pdf2image (דורש Poppler)
    try:
        images = _convert_with_pdf2image(pdf_path, dpi)
        logger.info(f"pdf2image: {len(images)} דפים חולצו")
        return images
    except ImportError:
        logger.warning("pdf2image לא זמין — עובר ל-pdfplumber fallback")
    except Exception as e:
        logger.warning(f"pdf2image נכשל ({e}) — עובר ל-pdfplumber fallback")

    # fallback: pdfplumber
    images = _convert_with_pdfplumber(pdf_path)
    logger.info(f"pdfplumber: {len(images)} דפים חולצו")
    return images


def _convert_with_pdf2image(pdf_path: Path, dpi: int) -> list[Image.Image]:
    """
    ממיר PDF לתמונות באמצעות pdf2image + Poppler.
    איכות מיטבית לסריקות.
    """
    from pdf2image import convert_from_path  # type: ignore

    pages = convert_from_path(
        str(pdf_path),
        dpi=dpi,
        fmt="RGB",
        thread_count=2,  # לא יותר מ-2 כדי לא לחסום את ה-UI
    )
    # מוודאים שכל הדפים ב-RGB
    return [p.convert("RGB") for p in pages]


def _convert_with_pdfplumber(pdf_path: Path) -> list[Image.Image]:
    """
    ממיר PDF לתמונות באמצעות pdfplumber.
    fallback כשאין Poppler — איכות מעט נמוכה יותר.
    """
    import pdfplumber  # type: ignore

    images: list[Image.Image] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        if len(pdf.pages) == 0:
            raise ValueError(f"קובץ PDF ריק: {pdf_path.name}")

        for page_num, page in enumerate(pdf.pages, start=1):
            try:
                # pdfplumber מרנדר דף לתמונה PIL
                img = page.to_image(resolution=200).original
                images.append(img.convert("RGB"))
                logger.debug(f"דף {page_num} הומר בהצלחה")
            except Exception as e:
                logger.error(f"שגיאה בהמרת דף {page_num}: {e}")
                # ממשיכים לדפים הבאים — לא עוצרים את כל הסריקה
                continue

    if not images:
        raise ValueError(f"לא ניתן היה לחלץ אף דף מ-{pdf_path.name}")

    return images


def image_file_to_pil(image_path: str | Path) -> Image.Image:
    """
    פותח קובץ תמונה ומחזיר PIL.Image ב-RGB.

    Args:
        image_path: נתיב לקובץ תמונה (JPG/PNG/TIFF/...)

    Returns:
        PIL.Image בפורמט RGB

    Raises:
        FileNotFoundError: אם הקובץ לא קיים
        IOError:           אם הפורמט לא נתמך
    """
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"תמונה לא נמצאה: {image_path}")

    logger.debug(f"פותח תמונה: {image_path.name}")
    img = Image.open(image_path)
    return img.convert("RGB")


def load_input_file(file_path: str | Path) -> list[Image.Image]:
    """
    נקודת כניסה אחידה — מקבל PDF או תמונה, מחזיר רשימת תמונות.

    Args:
        file_path: נתיב לקובץ (PDF / JPG / PNG / ...)

    Returns:
        רשימת PIL.Image (תמיד רשימה, גם לתמונה בודדת)
    """
    from utils.file_utils import get_file_type

    file_type = get_file_type(file_path)

    if file_type == "pdf":
        return pdf_to_images(file_path)
    elif file_type == "image":
        return [image_file_to_pil(file_path)]
    else:
        suffix = Path(file_path).suffix
        raise ValueError(
            f"פורמט קובץ לא נתמך: {suffix}. "
            "השתמשי ב-PDF, JPG, PNG, TIFF, או BMP."
        )

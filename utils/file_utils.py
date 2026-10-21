"""
utils/file_utils.py
-------------------
פונקציות עזר לטיפול בקבצים:
- זיהוי סוג קובץ (PDF / תמונה)
- קריאת קובץ לבייטים
- שמירת קובץ זמני ומחיקתו
"""

import tempfile
import shutil
from pathlib import Path
from typing import Literal

from utils.logger import get_logger

logger = get_logger(__name__)

# סיומות קבצים נתמכות
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp", ".webp"}
PDF_EXTENSIONS   = {".pdf"}
SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | PDF_EXTENSIONS


def get_file_type(path: str | Path) -> Literal["pdf", "image", "unsupported"]:
    """
    מזהה אם הקובץ הוא PDF, תמונה, או לא נתמך.

    Args:
        path: נתיב הקובץ

    Returns:
        "pdf" / "image" / "unsupported"
    """
    suffix = Path(path).suffix.lower()
    if suffix in PDF_EXTENSIONS:
        return "pdf"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    return "unsupported"


def read_file_bytes(path: str | Path) -> bytes:
    """
    קורא קובץ ומחזיר את תוכנו כ-bytes.

    Args:
        path: נתיב הקובץ

    Returns:
        תוכן הקובץ כ-bytes

    Raises:
        FileNotFoundError: אם הקובץ לא קיים
        IOError: אם לא ניתן לקרוא את הקובץ
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"קובץ לא נמצא: {path}")
    if not file_path.is_file():
        raise IOError(f"הנתיב אינו קובץ: {path}")

    logger.debug(f"קורא קובץ: {file_path.name} ({file_path.stat().st_size:,} bytes)")
    return file_path.read_bytes()


def save_temp_file(data: bytes, suffix: str) -> Path:
    """
    שומר bytes לקובץ זמני ומחזיר את הנתיב.
    חשוב: למחוק אחרי השימוש עם delete_temp_file().

    Args:
        data:   תוכן הקובץ
        suffix: סיומת הקובץ (למשל ".pdf" או ".jpg")

    Returns:
        נתיב לקובץ הזמני
    """
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(data)
    tmp.close()
    logger.debug(f"נוצר קובץ זמני: {tmp.name}")
    return Path(tmp.name)


def delete_temp_file(path: str | Path) -> None:
    """
    מוחק קובץ זמני. לא מרים שגיאה אם הקובץ כבר נמחק.

    Args:
        path: נתיב הקובץ למחיקה
    """
    try:
        Path(path).unlink(missing_ok=True)
        logger.debug(f"קובץ זמני נמחק: {path}")
    except Exception as e:
        logger.warning(f"לא ניתן למחוק קובץ זמני {path}: {e}")


def ensure_output_dir() -> Path:
    """
    מוודא שתיקיית outputs/ קיימת ומחזיר את הנתיב אליה.

    Returns:
        נתיב לתיקיית הפלט
    """
    output_dir = Path(__file__).parent.parent / "outputs"
    output_dir.mkdir(exist_ok=True)
    return output_dir


def is_supported_file(filename: str) -> bool:
    """
    בודק אם שם הקובץ הוא בפורמט נתמך.

    Args:
        filename: שם הקובץ (עם סיומת)

    Returns:
        True אם נתמך
    """
    return Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS

"""
app/image_processor.py
-----------------------
עיבוד מקדים של תמונות לפני שליחה ל-GPT-4o.

המטרה: לשפר את איכות הקלט כך שהמודל יצליח לקרוא גם:
- סריקות עקומות
- תמונות עמומות או בהירות מדי
- סריקות בצבע שמקשות על קריאת טקסט

כל פונקציה עצמאית — ניתן לשנות פרמטרים ללא השפעה על שאר הקוד.
"""

from __future__ import annotations

import io
import base64

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

from utils.logger import get_logger

logger = get_logger(__name__)

# גבול מקסימלי לרוחב/גובה תמונה לפני שליחה ל-API
# GPT-4o מטפל היטב עד ~2000px, מעל זה אין תועלת ורק עלות גבוהה יותר
MAX_DIMENSION = 2000

# גודל מקסימלי לקובץ שנשלח ל-API (בבייטים) — 20MB
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024


def preprocess_image(image: Image.Image) -> Image.Image:
    """
    מריץ את כל שלבי העיבוד המקדים על תמונה.
    זו הפונקציה הראשית — קוראת לכל השאר לפי הסדר.

    Args:
        image: PIL.Image (RGB)

    Returns:
        PIL.Image מעובד ומוכן לשליחה
    """
    logger.debug(f"עיבוד תמונה: {image.size[0]}x{image.size[1]}")

    # שלב 1: ודא RGB
    img = image.convert("RGB")

    # שלב 2: תיקון זווית (deskew) — חשוב לסריקות עקומות
    img = deskew(img)

    # שלב 3: resize אם גדול מדי
    img = resize_if_needed(img, max_dim=MAX_DIMENSION)

    # שלב 4: שיפור ניגודיות — עוזר לטקסט דהוי ומדבקות
    img = enhance_contrast(img, factor=1.3)

    # שלב 5: חידוד קל — עוזר לכתב יד
    img = sharpen(img, factor=1.2)

    logger.debug(f"עיבוד הסתיים: {img.size[0]}x{img.size[1]}")
    return img


def deskew(image: Image.Image) -> Image.Image:
    """
    מתקן זווית טיה של סריקה עקומה.
    משתמש ב-OpenCV למציאת הזווית ו-PIL לסיבוב.

    אם OpenCV לא זמין — מחזיר את התמונה ללא שינוי.

    Args:
        image: PIL.Image (RGB)

    Returns:
        PIL.Image מיושר
    """
    try:
        import cv2

        # המרה ל-numpy array
        img_array = np.array(image)

        # המרה לגווני אפור לצורך זיהוי זווית
        gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

        # סף (threshold) להפרדת טקסט מרקע
        _, thresh = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
        )

        # מציאת קואורדינטות הפיקסלים הכהים (הטקסט)
        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) < 100:
            # אין מספיק נקודות לחישוב זווית — מחזיר כמות שהוא
            return image

        # חישוב minAreaRect — נותן את הזווית
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]

        # נרמול הזווית לטווח [-45, 45]
        if angle < -45:
            angle = 90 + angle
        elif angle > 45:
            angle = angle - 90

        # לא מסובבים אם הזווית קטנה מ-0.5 מעלות
        if abs(angle) < 0.5:
            return image

        logger.debug(f"מתקן זווית: {angle:.1f}°")

        # סיבוב עם PIL (שומר על גודל מקורי, ממלא שוליים בלבן)
        rotated = image.rotate(
            angle,
            expand=False,
            fillcolor=(255, 255, 255),
            resample=Image.BICUBIC,
        )
        return rotated

    except ImportError:
        logger.debug("OpenCV לא זמין — מדלג על תיקון זווית")
        return image
    except Exception as e:
        logger.debug(f"תיקון זווית נכשל ({e}) — ממשיך ללא תיקון")
        return image


def resize_if_needed(image: Image.Image, max_dim: int = MAX_DIMENSION) -> Image.Image:
    """
    מקטין תמונה אם הצד הארוך שלה גדול מ-max_dim.
    שומר על יחס גובה-רוחב.

    Args:
        image:   PIL.Image
        max_dim: הממד המקסימלי המותר (ב-pixels)

    Returns:
        PIL.Image — מוקטן אם נדרש, אחרת ללא שינוי
    """
    w, h = image.size
    max_current = max(w, h)

    if max_current <= max_dim:
        return image

    scale = max_dim / max_current
    new_w = int(w * scale)
    new_h = int(h * scale)

    logger.debug(f"resize: {w}x{h} → {new_w}x{new_h}")
    return image.resize((new_w, new_h), Image.LANCZOS)


def enhance_contrast(image: Image.Image, factor: float = 1.3) -> Image.Image:
    """
    משפר ניגודיות התמונה.

    factor=1.0 = ללא שינוי
    factor=1.5 = ניגודיות גבוהה יותר
    factor=0.5 = ניגודיות נמוכה יותר

    Args:
        image:  PIL.Image
        factor: מקדם ניגודיות

    Returns:
        PIL.Image עם ניגודיות משופרת
    """
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(factor)


def sharpen(image: Image.Image, factor: float = 1.2) -> Image.Image:
    """
    מחדד את התמונה — עוזר לכתב יד ולטקסט מטושטש.

    factor=1.0 = ללא שינוי
    factor=2.0 = חידוד חזק

    Args:
        image:  PIL.Image
        factor: מקדם חידוד

    Returns:
        PIL.Image מחודד
    """
    enhancer = ImageEnhance.Sharpness(image)
    return enhancer.enhance(factor)


def image_to_base64(image: Image.Image, quality: int = 85) -> str:
    """
    ממיר PIL.Image ל-base64 string לשליחה ל-OpenAI API.

    שומר כ-JPEG (קטן יותר מ-PNG) באיכות מספיקה לקריאת טקסט.

    Args:
        image:   PIL.Image (RGB)
        quality: איכות JPEG (1-95), ברירת מחדל 85

    Returns:
        מחרוזת base64

    Raises:
        ValueError: אם התמונה גדולה מדי לשליחה
    """
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    size = buffer.tell()

    # אם גדול מדי — מקטינים איכות
    if size > MAX_FILE_SIZE_BYTES:
        logger.warning(f"תמונה גדולה ({size:,} bytes) — מצמצם איכות")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=60, optimize=True)
        size = buffer.tell()

        if size > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"התמונה גדולה מדי ({size:,} bytes). "
                "נסי להקטין את ה-DPI של הסריקה."
            )

    buffer.seek(0)
    encoded = base64.b64encode(buffer.read()).decode("utf-8")
    logger.debug(f"תמונה הומרה ל-base64: {size:,} bytes")
    return encoded

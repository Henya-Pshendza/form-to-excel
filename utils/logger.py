"""
utils/logger.py
---------------
לוגר מרכזי לכל הפרויקט.

חשוב: הלוגר לא מתעד תוכן טפסים (נתוני חולים) — רק פעולות ומצבים.
"""

import logging
import sys
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    """
    מחזיר logger עם הגדרות אחידות.
    
    שימוש:
        from utils.logger import get_logger
        logger = get_logger(__name__)
        logger.info("עיבוד טופס מתחיל")
    """
    logger = logging.getLogger(name)

    # אם כבר הוגדר — מחזירים אותו כמות שהוא (מונע כפילויות)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # פורמט: זמן | שם המודול | רמה | הודעה
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(name)-20s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # handler לקונסול — מציג INFO ומעלה
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # handler לקובץ — מציג DEBUG ומעלה (לאבחון בעיות)
    log_dir = Path(__file__).parent.parent / "outputs"
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

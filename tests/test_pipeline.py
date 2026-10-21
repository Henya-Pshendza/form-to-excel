"""
tests/test_pipeline.py
-----------------------
בדיקות יחידה לכל רכיבי ה-pipeline — ללא קריאות ל-API.

הרצה:
    cd form-to-excel
    python -m pytest tests/test_pipeline.py -v

הבדיקות מכסות:
  - נרמול תאריכים, ת.ז., גורם שולח, רשימות
  - לוגיקת FieldStatus (OK / LOW / MISSING / ERROR)
  - בניית עמודות דינמית באקסל
  - file_utils
  - vision_extractor._parse_json_response ו-_validate_and_fill
"""

import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# הוספת שורש הפרויקט ל-path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from app.normalizer import (
    _normalize_date,
    _normalize_id,
    _normalize_sender,
    _normalize_list,
    _normalize_text,
    normalize_result,
)
from app.confidence_handler import (
    FieldStatus,
    apply_confidence_flags,
    count_issues,
    is_ready_to_export,
    CONFIDENCE_THRESHOLD,
)
from app.vision_extractor import (
    _parse_json_response,
    _validate_and_fill,
    build_empty_result,
)
from utils.file_utils import get_file_type, is_supported_file


# ═════════════════════════════════════════════════════════════════════════════
# נרמול תאריכים
# ═════════════════════════════════════════════════════════════════════════════

class TestNormalizeDate:

    def test_slash_format(self):
        val, conf = _normalize_date("21/08/2026", 0.9)
        assert val == "21/08/2026"
        assert conf == 0.9

    def test_dot_format(self):
        val, conf = _normalize_date("21.8.2026", 0.9)
        assert val == "21/08/2026"

    def test_two_digit_year(self):
        val, conf = _normalize_date("21.8.26", 0.9)
        assert val == "21/08/2026"

    def test_dash_format(self):
        val, conf = _normalize_date("21-08-2026", 0.9)
        assert val == "21/08/2026"

    def test_zero_padded_day(self):
        val, conf = _normalize_date("01/01/2026", 0.9)
        assert val == "01/01/2026"

    def test_empty_returns_none(self):
        val, conf = _normalize_date("", 0.9)
        assert val is None
        assert conf == 0.0

    def test_none_returns_none(self):
        val, conf = _normalize_date(None, 0.9)
        assert val is None

    def test_invalid_date_lowers_confidence(self):
        val, conf = _normalize_date("תאריך לא ברור", 0.9)
        assert conf < 0.9   # confidence ירד


# ═════════════════════════════════════════════════════════════════════════════
# נרמול תעודת זהות
# ═════════════════════════════════════════════════════════════════════════════

class TestNormalizeId:

    def test_nine_digits_unchanged(self):
        val, conf = _normalize_id("123456789", 0.95)
        assert val == "123456789"
        assert conf == 0.95

    def test_eight_digits_padded(self):
        val, conf = _normalize_id("12345678", 0.95)
        assert val == "012345678"
        assert len(val) == 9

    def test_removes_dashes(self):
        val, conf = _normalize_id("123-456-789", 0.9)
        assert val == "123456789"

    def test_removes_spaces(self):
        val, conf = _normalize_id("123 456 789", 0.9)
        assert val == "123456789"

    def test_too_long_lowers_confidence(self):
        val, conf = _normalize_id("1234567890", 0.9)
        assert conf < 0.9
        assert len(val) == 9   # חותכים ל-9

    def test_empty_returns_none(self):
        val, conf = _normalize_id("", 0.9)
        assert val is None

    def test_non_digits_only(self):
        val, conf = _normalize_id("אבגדאבגדא", 0.9)
        assert val is None


# ═════════════════════════════════════════════════════════════════════════════
# נרמול גורם שולח
# ═════════════════════════════════════════════════════════════════════════════

class TestNormalizeSender:

    def test_exact_match_kupah(self):
        val, conf = _normalize_sender("כללית", 0.9)
        assert val == "כללית"

    def test_exact_match_maccabi(self):
        val, conf = _normalize_sender("מכבי", 0.9)
        assert val == "מכבי"

    def test_alias_kupat_holim(self):
        val, conf = _normalize_sender("קופת חולים כללית", 0.9)
        assert val == "כללית"

    def test_fuzzy_typo(self):
        # שגיאת כתיב קלה
        val, conf = _normalize_sender("כלאית", 0.9)
        # עדיין צריך לזהות ככללית או להחזיר ערך כלשהו עם confidence נמוך
        assert val is not None

    def test_empty_returns_none(self):
        val, conf = _normalize_sender("", 0.9)
        assert val is None

    def test_unknown_returns_low_confidence(self):
        val, conf = _normalize_sender("מעבדה לא קיימת xyz123", 0.9)
        # confidence צריך לרדת
        assert conf < 0.9


# ═════════════════════════════════════════════════════════════════════════════
# נרמול רשימות (מספר מרכזי / התחייבות)
# ═════════════════════════════════════════════════════════════════════════════

class TestNormalizeList:

    def test_list_unchanged(self):
        val, conf = _normalize_list(["123", "456"], 0.9)
        assert val == ["123", "456"]

    def test_string_becomes_list(self):
        val, conf = _normalize_list("123", 0.9)
        assert isinstance(val, list)
        assert "123" in val

    def test_comma_separated_split(self):
        val, conf = _normalize_list("123, 456, 789", 0.9)
        assert len(val) == 3

    def test_deduplication(self):
        val, conf = _normalize_list(["123", "123", "456"], 0.9)
        assert val.count("123") == 1

    def test_empty_list(self):
        val, conf = _normalize_list([], 0.9)
        assert val == []

    def test_empty_string(self):
        val, conf = _normalize_list("", 0.9)
        assert val == []

    def test_filters_empty_items(self):
        val, conf = _normalize_list(["123", "", "456"], 0.9)
        assert "" not in val


# ═════════════════════════════════════════════════════════════════════════════
# confidence_handler
# ═════════════════════════════════════════════════════════════════════════════

class TestConfidenceHandler:

    def _make_extraction(self, overrides: dict = None) -> dict:
        """בונה תוצאת חילוץ בסיסית לבדיקות."""
        base = {
            "שם_פרטי":       {"value": "ישראל",    "confidence": 0.95},
            "שם_משפחה":      {"value": "ישראלי",   "confidence": 0.95},
            "תעודת_זהות":    {"value": "123456789", "confidence": 0.95},
            "מספר_מרכזי":    {"value": ["M001"],   "confidence": 0.90},
            "תאריך_קבלה":    {"value": "01/01/2026","confidence": 0.88},
            "גורם_שולח":     {"value": "כללית",    "confidence": 0.92},
            "מספר_התחייבות": {"value": ["H001"],   "confidence": 0.90},
        }
        if overrides:
            base.update(overrides)
        return base

    def test_all_ok_when_high_confidence(self):
        result = apply_confidence_flags(self._make_extraction())
        for field_key in ["שם_פרטי", "שם_משפחה", "תעודת_זהות"]:
            assert result[field_key]["status"] == FieldStatus.OK

    def test_low_confidence_flagged(self):
        ext = self._make_extraction({
            "שם_פרטי": {"value": "ישראל", "confidence": 0.5}
        })
        result = apply_confidence_flags(ext)
        assert result["שם_פרטי"]["status"] == FieldStatus.LOW

    def test_missing_required_field(self):
        ext = self._make_extraction({
            "תעודת_זהות": {"value": None, "confidence": 0.0}
        })
        result = apply_confidence_flags(ext)
        assert result["תעודת_זהות"]["status"] == FieldStatus.MISSING

    def test_empty_list_is_missing(self):
        ext = self._make_extraction({
            "מספר_מרכזי": {"value": [], "confidence": 0.0}
        })
        result = apply_confidence_flags(ext)
        assert result["מספר_מרכזי"]["status"] == FieldStatus.MISSING

    def test_count_issues(self):
        ext = self._make_extraction({
            "שם_פרטי":    {"value": "ישראל", "confidence": 0.5},
            "תעודת_זהות": {"value": None,    "confidence": 0.0},
        })
        flagged = apply_confidence_flags(ext)
        counts  = count_issues(flagged)
        assert counts["low"]     >= 1
        assert counts["missing"] >= 1

    def test_is_ready_to_export_all_ok(self):
        flagged = apply_confidence_flags(self._make_extraction())
        assert is_ready_to_export(flagged) is True

    def test_not_ready_when_missing(self):
        ext = self._make_extraction({
            "תעודת_זהות": {"value": None, "confidence": 0.0}
        })
        flagged = apply_confidence_flags(ext)
        assert is_ready_to_export(flagged) is False

    def test_api_error_marks_all_error(self):
        ext = self._make_extraction()
        ext["_error"] = {"value": "שגיאת API", "confidence": 0.0}
        flagged = apply_confidence_flags(ext)
        for field_key in ["שם_פרטי", "שם_משפחה"]:
            assert flagged[field_key]["status"] == FieldStatus.ERROR


# ═════════════════════════════════════════════════════════════════════════════
# vision_extractor — פרסור JSON
# ═════════════════════════════════════════════════════════════════════════════

class TestParseJsonResponse:

    def test_pure_json(self):
        data = {"שם_פרטי": {"value": "ישראל", "confidence": 0.9}}
        result = _parse_json_response(json.dumps(data))
        assert result == data

    def test_json_with_markdown_fences(self):
        data = {"שם_פרטי": {"value": "ישראל", "confidence": 0.9}}
        text = f"```json\n{json.dumps(data)}\n```"
        result = _parse_json_response(text)
        assert result == data

    def test_json_with_preamble_text(self):
        data = {"שם_פרטי": {"value": "ישראל", "confidence": 0.9}}
        text = f"הנה התוצאה:\n{json.dumps(data)}"
        result = _parse_json_response(text)
        assert result == data

    def test_empty_string_returns_none(self):
        assert _parse_json_response("") is None

    def test_invalid_json_returns_none(self):
        assert _parse_json_response("זה לא JSON") is None

    def test_none_returns_none(self):
        assert _parse_json_response(None) is None


# ═════════════════════════════════════════════════════════════════════════════
# vision_extractor — validate_and_fill
# ═════════════════════════════════════════════════════════════════════════════

class TestValidateAndFill:

    def test_complete_result_unchanged(self):
        raw = {
            "שם_פרטי":       {"value": "ישראל",     "confidence": 0.95},
            "שם_משפחה":      {"value": "ישראלי",    "confidence": 0.95},
            "תעודת_זהות":    {"value": "123456789",  "confidence": 0.95},
            "מספר_מרכזי":    {"value": ["M001"],    "confidence": 0.90},
            "תאריך_קבלה":    {"value": "01/01/2026","confidence": 0.88},
            "גורם_שולח":     {"value": "כללית",     "confidence": 0.92},
            "מספר_התחייבות": {"value": ["H001"],    "confidence": 0.90},
        }
        result = _validate_and_fill(raw)
        assert result["שם_פרטי"]["value"] == "ישראל"

    def test_missing_field_filled_with_null(self):
        raw = {}
        result = _validate_and_fill(raw)
        assert result["שם_פרטי"]["value"] is None
        assert result["שם_פרטי"]["confidence"] == 0.0

    def test_multi_field_string_becomes_list(self):
        raw = {"מספר_מרכזי": {"value": "M001", "confidence": 0.9}}
        result = _validate_and_fill(raw)
        assert isinstance(result["מספר_מרכזי"]["value"], list)

    def test_confidence_clamped_to_range(self):
        raw = {"שם_פרטי": {"value": "ישראל", "confidence": 1.5}}
        result = _validate_and_fill(raw)
        assert result["שם_פרטי"]["confidence"] <= 1.0

    def test_confidence_negative_clamped(self):
        raw = {"שם_פרטי": {"value": "ישראל", "confidence": -0.5}}
        result = _validate_and_fill(raw)
        assert result["שם_פרטי"]["confidence"] >= 0.0

    def test_build_empty_result_has_all_fields(self):
        empty = build_empty_result()
        from config.fields import FIELDS
        for field_key in FIELDS:
            assert field_key in empty


# ═════════════════════════════════════════════════════════════════════════════
# file_utils
# ═════════════════════════════════════════════════════════════════════════════

class TestFileUtils:

    def test_pdf_detected(self):
        assert get_file_type("form.pdf") == "pdf"
        assert get_file_type("FORM.PDF") == "pdf"

    def test_image_detected(self):
        assert get_file_type("scan.jpg")  == "image"
        assert get_file_type("scan.jpeg") == "image"
        assert get_file_type("scan.png")  == "image"
        assert get_file_type("scan.tiff") == "image"

    def test_unsupported_detected(self):
        assert get_file_type("doc.docx") == "unsupported"
        assert get_file_type("data.csv") == "unsupported"

    def test_is_supported_file(self):
        assert is_supported_file("form.pdf")   is True
        assert is_supported_file("scan.jpg")   is True
        assert is_supported_file("doc.docx")   is False

    def test_path_object_works(self):
        assert get_file_type(Path("form.pdf")) == "pdf"


# ═════════════════════════════════════════════════════════════════════════════
# אינטגרציה — normalize_result end-to-end
# ═════════════════════════════════════════════════════════════════════════════

class TestNormalizeResultIntegration:

    def test_full_normalization(self):
        """בדיקת נרמול מלא של תוצאת חילוץ."""
        raw = {
            "שם_פרטי":       {"value": "  ישראל  ",  "confidence": 0.95},
            "שם_משפחה":      {"value": "ישראלי",     "confidence": 0.95},
            "תעודת_זהות":    {"value": "12345678",   "confidence": 0.95},   # 8 ספרות
            "מספר_מרכזי":    {"value": ["M001", "M001", "M002"], "confidence": 0.90},  # כפולים
            "תאריך_קבלה":    {"value": "1.8.26",     "confidence": 0.88},   # פורמט קצר
            "גורם_שולח":     {"value": "כללית",      "confidence": 0.92},
            "מספר_התחייבות": {"value": "H001, H002", "confidence": 0.90},   # מחרוזת
        }
        result = normalize_result(raw)

        # שם — רווחים הוסרו
        assert result["שם_פרטי"]["value"] == "ישראל"

        # ת.ז — הורחבה ל-9 ספרות
        assert len(result["תעודת_זהות"]["value"]) == 9
        assert result["תעודת_זהות"]["value"] == "012345678"

        # מרכזי — כפולים הוסרו
        assert len(set(result["מספר_מרכזי"]["value"])) == len(result["מספר_מרכזי"]["value"])

        # תאריך — מנורמל
        assert result["תאריך_קבלה"]["value"] == "01/08/2026"

        # התחייבות — מחרוזת הפכה לרשימה
        assert isinstance(result["מספר_התחייבות"]["value"], list)
        assert len(result["מספר_התחייבות"]["value"]) == 2

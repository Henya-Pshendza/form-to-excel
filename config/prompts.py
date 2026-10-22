"""
config/prompts.py
-----------------
Two-step extraction prompts for GPT-4o Vision.

Step 1: Read all text from the form (OCR pass)
Step 2: Extract structured fields from the raw text
"""

from config.senders import ALL_SENDERS

_SENDERS_LIST = ", ".join(ALL_SENDERS)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Read everything visible in the image
# ─────────────────────────────────────────────────────────────────────────────

STEP1_READ_PROMPT = """You are an OCR engine. Your only job right now is to READ and TRANSCRIBE.

Look at this Israeli medical form image carefully.
Read EVERY piece of text you can see — printed, handwritten, stamped, on stickers.

Organize what you see into sections:
- TOP SECTION (header, organization name, form title)
- PATIENT INFO (any names, ID numbers, dates of birth)
- FORM FIELDS (labels and their values)
- STICKERS (barcode stickers and what's written on/near them)
- STAMPS (rubber stamps, especially any that say התקבל/received)
- HANDWRITING (any handwritten additions)
- BOTTOM SECTION (signatures, notes)

Be thorough. Include Hebrew text exactly as written.
Do not interpret yet — just transcribe everything you see.
"""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Extract structured fields from the transcribed text
# ─────────────────────────────────────────────────────────────────────────────

STEP2_EXTRACT_PROMPT = f"""You are a data extraction engine for Israeli medical commitment forms.

You will receive a text transcription of a medical form.
Extract the following 7 fields and return ONLY valid JSON.

═══════════════════════════════════════════════
CRITICAL: NEVER invent data. If not found → null.
A blank field is better than a wrong value.
═══════════════════════════════════════════════

FIELDS:

1. שם_פרטי (patient first name)
   - The PATIENT's first name
   - May appear next to labels: "שם פרטי", "שם", "מנוי", "מעבדה/מנוי", "לכבוד", "שם החולה"
   - In Wolfson/hospital forms: handwritten in Hebrew next to the word "שם" near the top
   - Look carefully for handwritten Hebrew text — it may be unclear
   - Hebrew name, 1-3 words
   - null if confidence < 0.85

2. שם_משפחה (patient family name)
   - The PATIENT's family/last name
   - Usually appears next to the first name
   - In Wolfson hospital forms: handwritten next to "שם" label at top of form
   - null if confidence < 0.85

3. תעודת_זהות (Israeli ID number)
   - 8-9 digits only
   - Labeled: "ת.ז.", "מספר זהות", "ת.ז"
   - NOT a date, NOT a phone number
   - null if not clearly an ID number

4. מספר_מרכזי (central lab number — return as list)
   - Number on a sticker labeled "מרכזי" nearby
   - Or handwritten next to word "מרכזי"
   - Multiple values possible — return ALL as list
   - [] if not found

5. תאריך_קבלה (received date)
   - Date INSIDE a stamp that says "התקבל" / "נתקבל"
   - OR a handwritten date added later (not pre-printed)
   - Format: DD/MM/YYYY
   - NOT the form date, NOT birth date, NOT test date
   - null if no received stamp found

6. גורם_שולח (sending organization)
   - Organization name at the TOP of the form (header/logo area)
   - Must match one of: {_SENDERS_LIST}
   - null if unclear

7. מספר_התחייבות (commitment number — return as list)
   - Number next to label: "מספר התחייבות", "התחייבות", "דרישה", "דגימה", "מס'"
   - OR number on barcode sticker labeled "התחייבות"/"דרישה"
   - Multiple values possible — return ALL as list
   - [] if not found

Return ONLY this JSON (no markdown, no explanation):
{{
  "שם_פרטי":          {{"value": "ישראל",        "confidence": 0.95}},
  "שם_משפחה":         {{"value": "ישראלי",       "confidence": 0.95}},
  "תעודת_זהות":       {{"value": "123456789",    "confidence": 0.90}},
  "מספר_מרכזי":       {{"value": ["2344936"],    "confidence": 0.85}},
  "תאריך_קבלה":       {{"value": "21/08/2026",   "confidence": 0.90}},
  "גורם_שולח":        {{"value": "כללית",        "confidence": 0.95}},
  "מספר_התחייבות":    {{"value": ["4034345113"], "confidence": 0.85}}
}}
"""

# ─────────────────────────────────────────────────────────────────────────────
# Legacy single-step prompts (fallback)
# ─────────────────────────────────────────────────────────────────────────────

EXTRACTION_PROMPT = STEP2_EXTRACT_PROMPT  # backward compat

RETRY_PROMPT = """Return ONLY valid JSON. null for missing, [] for missing lists:

{
  "שם_פרטי":          {"value": null, "confidence": 0.0},
  "שם_משפחה":         {"value": null, "confidence": 0.0},
  "תעודת_זהות":       {"value": null, "confidence": 0.0},
  "מספר_מרכזי":       {"value": [], "confidence": 0.0},
  "תאריך_קבלה":       {"value": null, "confidence": 0.0},
  "גורם_שולח":        {"value": null, "confidence": 0.0},
  "מספר_התחייבות":    {"value": [], "confidence": 0.0}
}
"""

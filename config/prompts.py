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

STEP2_EXTRACT_PROMPT = f"""Extract 7 fields from this Israeli medical commitment form text.

IMPORTANT RULES:
• ONLY extract data that clearly exists in the text
• If unsure, set lower confidence (0.50-0.70) rather than null
• Handwritten text may be unclear - try your best and mark lower confidence
• Multiple values for מרכזי/התחייבות → return all in a list

FIELDS TO EXTRACT:

1. שם_פרטי — Patient's FIRST name
   Labels: "שם פרטי", "שם", "מנוי", "לכבוד", "שם החולה"
   Often handwritten in Hebrew near top of form
   
2. שם_משפחה — Patient's FAMILY name
   Usually next to first name
   Often handwritten
   
3. תעודת_זהות — Israeli ID (8-9 digits)
   Labels: "ת.ז.", "מספר זהות", "ת.ז"
   Must be digits only, NOT a date
   
4. מספר_מרכזי — Lab central number(s) [list]
   On sticker or handwritten near word "מרכזי"
   Return ALL numbers found as list
   
5. תאריך_קבלה — Received date
   Inside "התקבל"/"נתקבל" stamp, format: DD/MM/YYYY
   NOT form date, NOT birth date
   
6. גורם_שולח — Sending organization
   Organization name in header/logo area
   Options: {_SENDERS_LIST}
   
7. מספר_התחייבות — Commitment number(s) [list]
   Labels: "מספר התחייבות", "התחייבות", "דרישה", "דגימה", "מס'"
   Return ALL numbers found as list

CONFIDENCE GUIDE:
• 0.90-1.00 = Crystal clear, printed text
• 0.70-0.89 = Clear but handwritten or slightly unclear
• 0.50-0.69 = Visible but hard to read, best guess
• Below 0.50 = Too unclear, use null

OUTPUT FORMAT (valid JSON only, no markdown):
{{
  "שם_פרטי":          {{"value": "דוד",          "confidence": 0.75}},
  "שם_משפחה":         {{"value": "כהן",          "confidence": 0.75}},
  "תעודת_זהות":       {{"value": "123456789",    "confidence": 0.85}},
  "מספר_מרכזי":       {{"value": ["2344936"],    "confidence": 0.80}},
  "תאריך_קבלה":       {{"value": "21/08/2026",   "confidence": 0.90}},
  "גורם_שולח":        {{"value": "כללית",        "confidence": 0.95}},
  "מספר_התחייבות":    {{"value": ["4034345113"], "confidence": 0.80}}
}}

If field not found: use null (not list fields use [])
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

"""
config/prompts.py
-----------------
Two-step extraction prompts for Gemini Vision.

Step 1: Read all text from the form (OCR pass)
Step 2: Extract structured fields from the raw text
"""

from config.senders import ALL_SENDERS

_SENDERS_LIST = ", ".join(ALL_SENDERS)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Read everything visible in the image
# ─────────────────────────────────────────────────────────────────────────────

STEP1_READ_PROMPT = """Read ALL visible text from this Israeli medical form. Transcribe everything you see.

CRITICAL: Read Hebrew handwritten names letter-by-letter, even if unclear!

Organize the text into these sections:

1. PATIENT NAMES (handwritten Hebrew, usually near top):
   - First name (שם פרטי): ____
   - Family name (שם משפחה): ____
   Note: "שם: כהן" means family name is כהן, but first name is MISSING - write "empty" for first name!

2. ID NUMBER (ת.ז., usually handwritten):
   ____

3. BARCODE STICKERS:
   List ALL barcode stickers you see. For each, write if it has the word "מרכזי" on/near it:
   - Sticker 1: [number] (has "מרכזי"? yes/no)
   - Sticker 2: [number] (has "מרכזי"? yes/no)

4. "התקבל" STAMP/DATE (received date - look for stamp or handwriting with "התקבל"):
   ____

5. ORGANIZATION (header/logo - כללית, מכבי, מאוחדת, לאומית, or hospital name):
   ____

6. OTHER TEXT (everything else you see):
   ____

FORMAT:
```
שם פרטי: [write first name OR "empty"]
שם משפחה: [write family name OR "empty"]
ת.ז.: [ID number OR "empty"]
Stickers: [list all with yes/no for "מרכזי"]
התקבל date: [date OR "empty"]
Organization: [name OR "empty"]
Other text: [everything else]
```

Read everything, including unclear handwriting - just do your best!"""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Extract structured fields from the transcribed text
# ─────────────────────────────────────────────────────────────────────────────

STEP2_EXTRACT_PROMPT = f"""Extract these 7 fields from the transcribed text:

RULES:

1. שם_פרטי (first name):
   - Hebrew FIRST name only
   - If text says "empty" or only shows family name: use null
   - Confidence 0.50-0.90

2. שם_משפחה (family name):
   - Hebrew FAMILY name only
   - If text says "empty": use null
   - Confidence 0.50-0.90

3. תעודת_זהות (ID):
   - 8-9 digits
   - If missing: use null

4. מספר_מרכזי (list):
   - ONLY stickers where "מרכזי"=yes
   - Return as list: ["123456"]
   - If no stickers with "מרכזי": use []

5. מספר_התחייבות (list):
   - ONLY stickers where "מרכזי"=no (barcode without "מרכזי" label)
   - Return as list: ["123456"]
   - If no such stickers: use []

6. תאריך_קבלה (date):
   - From "התקבל date" field ONLY
   - Format: DD/MM/YYYY or DD.MM.YYYY
   - If missing: use null

7. גורם_שולח (organization):
   - From "Organization" field
   - Must match one of: {_SENDERS_LIST}
   - If you see a close match (e.g., "וולפסון"), find the full name from the list
   - If missing: use null

CONFIDENCE:
- Clear: 0.75-0.95
- Handwritten (readable): 0.55-0.75
- Unclear: 0.45-0.60

OUTPUT (JSON only):
{{
  "שם_פרטי":          {{"value": null, "confidence": 0.0}},
  "שם_משפחה":         {{"value": "כהן", "confidence": 0.70}},
  "תעודת_זהות":       {{"value": "123456789", "confidence": 0.80}},
  "מספר_מרכזי":       {{"value": ["2344936"], "confidence": 0.90}},
  "תאריך_קבלה":       {{"value": "24/08/2023", "confidence": 0.90}},
  "גורם_שולח":        {{"value": "מכבי", "confidence": 0.95}},
  "מספר_התחייבות":    {{"value": ["947828"], "confidence": 0.85}}
}}"""

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

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

STEP1_READ_PROMPT = """Read this Israeli medical form carefully. Extract ALL visible text.

Focus on these areas in order:

1. HANDWRITTEN HEBREW NAMES (usually at top of the form):
   - שם פרטי (first name)
   - שם משפחה (family name)
   Read the handwriting carefully, even if unclear.

2. BARCODE STICKERS on the page:
   - Sticker with word "מרכזי" on/near it → this is a מרכזי number
   - Sticker with ONLY barcode + number (NO text label) → this is a התחייבות number
   Read ALL sticker numbers.

3. HANDWRITTEN ID NUMBER:
   - ת.ז. (8-9 digits, usually handwritten near the names)

4. FORM FIELD "מספר התחייבות":
   - Look for a printed form field labeled exactly "מספר התחייבות"
   - The number written in this field is a התחייבות number

5. STAMP OR HANDWRITTEN DATE (OUTSIDE the form):
   - Look for "התקבל" stamp with date inside OR handwritten date near "התקבל"
   - This date is when the form was received (NOT a date printed on the form itself)
   - Usually appears as a rubber stamp or handwritten addition on the page

6. ORGANIZATION NAME:
   - כללית, מכבי, מאוחדת, or לאומית (in header/logo)

Please organize your output:
```
Names (handwritten):
שם פרטי: [name or empty if missing]
שם משפחה: [name or empty if missing]

ID (handwritten): [8-9 digits or empty]

Sticker - מרכזי (has "מרכזי" label):
Number: [digits or empty]

Sticker - התחייבות (barcode only, NO label):
Number: [digits or empty]

Form field - התחייבות (printed field labeled "מספר התחייבות"):
Number: [digits or empty]

Received date (stamp or handwritten OUTSIDE form, near "התקבל"):
Date: [DD/MM/YYYY or empty]

Organization: [כללית/מכבי/מאוחדת/לאומית or empty]
```

CRITICAL: 
- תאריך קבלה = ONLY from stamp/handwriting OUTSIDE the form (not dates printed on form)
- מספר התחייבות = ONLY from barcode sticker OR form field labeled "מספר התחייבות"
- מספר מרכזי = ONLY from sticker with "מרכזי" label"""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Extract structured fields from the transcribed text
# ─────────────────────────────────────────────────────────────────────────────

STEP2_EXTRACT_PROMPT = f"""Extract 7 fields from the transcribed Israeli medical form text.

🎯 EXTRACTION RULES:

1️⃣ NAMES (שם_פרטי, שם_משפחה):
   • From "Names (handwritten)" section
   • Hebrew patient names only
   • If missing/empty → null
   • Confidence 0.55-0.90 depending on clarity

2️⃣ תעודת_זהות:
   • From "ID (handwritten)" section
   • 8-9 digits only
   • If missing → null

3️⃣ מספר_מרכזי [list]:
   • From "Sticker - מרכזי" section ONLY
   • These are stickers that have the word "מרכזי" on them
   • Return as list: ["number"]
   • If missing → []

4️⃣ מספר_התחייבות [list]:
   • From TWO possible sources:
     A) "Sticker - התחייבות" section (barcode sticker without label)
     B) "Form field - התחייבות" section (field labeled "מספר התחייבות")
   • Combine numbers from BOTH sources into one list
   • Return as list: ["number1", "number2"]
   • If missing from both → []

5️⃣ תאריך_קבלה:
   • From "Received date" section ONLY
   • This is a stamp or handwritten date OUTSIDE the form
   • Format: DD/MM/YYYY
   • NOT dates printed on the form itself
   • If missing → null

6️⃣ גורם_שולח:
   • From "Organization" section
   • Must be one of: {_SENDERS_LIST}
   • If missing → null

7️⃣ CONFIDENCE:
   • Clear text: 0.80-0.95
   • Handwritten (clear): 0.65-0.80
   • Handwritten (unclear): 0.50-0.65
   • Missing: 0.0

✨ OUTPUT (valid JSON only):
{{
  "שם_פרטי":          {{"value": "דוד",          "confidence": 0.70}},
  "שם_משפחה":         {{"value": "כהן",          "confidence": 0.65}},
  "תעודת_זהות":       {{"value": "123456789",    "confidence": 0.75}},
  "מספר_מרכזי":       {{"value": ["2344936"],    "confidence": 0.90}},
  "תאריך_קבלה":       {{"value": "21/08/2026",   "confidence": 0.85}},
  "גורם_שולח":        {{"value": "כללית",        "confidence": 0.95}},
  "מספר_התחייבות":    {{"value": ["4034345113"], "confidence": 0.85}}
}}

Missing → null (lists → [])"""

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

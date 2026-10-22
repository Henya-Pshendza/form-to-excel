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

1. HANDWRITTEN HEBREW NAMES (usually at top):
   - שם פרטי (first name)
   - שם משפחה (family name)
   Read the handwriting carefully, even if unclear.

2. BARCODE STICKERS:
   - Stickers with "מרכזי" label → note the number
   - Stickers WITHOUT label (just barcode + number) → note the number
   Read ALL stickers you see.

3. HANDWRITTEN ID NUMBER:
   - ת.ז. (8-9 digits, usually handwritten)

4. STAMPS:
   - "התקבל" stamp with date inside

5. OTHER TEXT:
   - Organization name (כללית, מכבי, מאוחדת, לאומית)
   - Any field labeled "מספר התחייבות"
   - Any other visible text

Please organize your output like this:
```
Names (handwritten):
שם פרטי: [write what you see]
שם משפחה: [write what you see]

ID: [digits]

Stickers:
- Sticker with "מרכזי": [number]
- Sticker without label: [number]

Stamp:
התקבל: [date]

Organization: [name]

Other: [any other visible text]
```

Read everything you can see, even if handwriting is unclear."""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Extract structured fields from the transcribed text
# ─────────────────────────────────────────────────────────────────────────────

STEP2_EXTRACT_PROMPT = f"""Extract 7 fields from the transcribed Israeli medical form text.

🎯 CRITICAL RULES:

1️⃣ NAMES (שם_פרטי, שם_משפחה):
   • Extract from "HANDWRITTEN NAMES" section
   • If marked "(illegible)" → still try to extract with lower confidence (0.50-0.60)
   • If completely missing from text → null
   • Hebrew patient names only (not organization names)
   • Clear names: confidence 0.70-0.90
   • Unclear/partial names: confidence 0.50-0.65

2️⃣ תעודת_זהות:
   • Usually HANDWRITTEN (not printed)
   • Extract from "HANDWRITTEN ID" section
   • 8-9 digits only

3️⃣ מספר_מרכזי vs מספר_התחייבות — CRITICAL DISTINCTION:
   
   ✅ מספר_מרכזי:
      - From "STICKERS - מרכזי" section ONLY
      - Sticker must have word "מרכזי" on/near it
      - Usually 6-8 digits
   
   ✅ מספר_התחייבות:
      - From "STICKERS - התחייבות (no label)" section (barcode stickers WITHOUT "מרכזי")
      - OR from "FORM FIELDS - התחייבות" section (printed form field)
      - Usually 8-12 digits
   
   ⚠️ NEVER put same number in both fields!
   ⚠️ If sticker has "מרכזי" → goes to מספר_מרכזי ONLY
   ⚠️ If sticker has NO label (just barcode+number) → goes to מספר_התחייבות ONLY

3️⃣ VALIDATION:
   • מספר_מרכזי: Usually 6-8 digits, often on physical sticker
   • מספר_התחייבות: Usually 8-12 digits, printed on form
   • If ONE number appears twice in text → include ONCE in the correct field
   • If truly 2+ different numbers → include ALL in list

4️⃣ CONFIDENCE LEVELS:
   • Crystal clear printed: 0.90-0.95
   • Clear handwritten: 0.70-0.85
   • Readable but unclear handwriting: 0.50-0.65
   • Very hard to read (best guess): 0.45-0.55
   • Completely missing/illegible: 0.0 + null
   
   ⚠️ Use 0.50-0.65 for unclear Hebrew handwriting (don't give up too easily!)

📋 FIELDS:

1. שם_פרטי — First name (Hebrew, often handwritten)
2. שם_משפחה — Family name (Hebrew, often handwritten)  
3. תעודת_זהות — ID number (8-9 digits, NOT a date)
4. מספר_מרכזי — Lab central number(s) from STICKERS [list]
5. תאריך_קבלה — Date from "התקבל" STAMP (DD/MM/YYYY)
6. גורם_שולח — Organization ({_SENDERS_LIST})
7. מספר_התחייבות — Commitment number(s) from FORM FIELD [list]

✨ EXAMPLE OUTPUT (valid JSON only):
{{
  "שם_פרטי":          {{"value": "דוד",          "confidence": 0.70}},
  "שם_משפחה":         {{"value": "כהן",          "confidence": 0.65}},
  "תעודת_זהות":       {{"value": "123456789",    "confidence": 0.85}},
  "מספר_מרכזי":       {{"value": ["2344936"],    "confidence": 0.90}},
  "תאריך_קבלה":       {{"value": "21/08/2026",   "confidence": 0.90}},
  "גורם_שולח":        {{"value": "כללית",        "confidence": 0.95}},
  "מספר_התחייבות":    {{"value": ["4034345113"], "confidence": 0.85}}
}}

Missing field → null (lists → [])"""

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

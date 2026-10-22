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

STEP1_READ_PROMPT = """You are an expert OCR engine specializing in Hebrew handwriting and medical forms.

🎯 YOUR MISSION: Read EVERY character, especially HANDWRITTEN HEBREW names.

CRITICAL FOCUS AREAS:
1. HANDWRITTEN HEBREW TEXT (names, dates) — read letter by letter, even if unclear
2. STICKERS with numbers and labels
3. STAMPS (especially "התקבל" with dates)
4. Printed form fields and their values

READ EVERYTHING IN THIS ORDER:

📍 PATIENT NAMES (TOP PRIORITY - usually handwritten in Hebrew):
   - Look for "שם פרטי" / "שם" / "מנוי" labels
   - Look for "שם משפחה" / "משפחה" labels  
   - Names are often handwritten in cursive Hebrew near the top
   - ⚠️ ONLY transcribe if clearly visible — if unclear/illegible, mark as "(illegible)"

📍 STICKERS (2 types - READ CAREFULLY):
   
   TYPE 1 - מרכזי sticker:
   - White/yellow barcode sticker WITH the word "מרכזי" written on/next to it
   - Usually 6-8 digits
   
   TYPE 2 - התחייבות sticker:
   - Barcode sticker WITHOUT any label (just barcode + number)
   - OR sticker with numbers but NO "מרכזי" label
   - Usually 8-12 digits
   
   ⚠️ CRITICAL: Distinguish between these two types!

📍 FORM FIELDS (printed text):
   - מספר התחייבות field — may appear as printed form field labeled "מספר התחייבות"/"התחייבות"/"דרישה"/"דגימה"
   - ת.ז. field — often handwritten, 8-9 digits (NOT printed field, usually filled in by hand)

📍 STAMPS:
   - "התקבל" stamp — read the date inside it (DD/MM/YYYY format)
   - Any other stamps with dates or numbers

📍 OTHER:
   - Organization name (header/logo: כללית, מכבי, מאוחדת, לאומית)

OUTPUT FORMAT — organize clearly:
```
=== HANDWRITTEN NAMES ===
שם פרטי: [transcribe exactly OR "(illegible)" if unreadable]
שם משפחה: [transcribe exactly OR "(illegible)" if unreadable]

=== HANDWRITTEN ID ===
ת.ז.: [8-9 digits, usually handwritten]

=== STICKERS - מרכזי ===
[List stickers that have "מרכזי" label]
Number: [digits]

=== STICKERS - התחייבות (no label) ===
[List barcode stickers WITHOUT "מרכזי" label]
Number: [digits]

=== FORM FIELDS - התחייבות ===
[If there's a printed field labeled "מספר התחייבות"]
Number: [digits]

=== STAMPS ===
התקבל: [date if exists]

=== ORGANIZATION ===
[כללית/מכבי/מאוחדת/לאומית]
```

⚠️ CRITICAL: Names only if clearly readable — empty if illegible is better than wrong!"""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Extract structured fields from the transcribed text
# ─────────────────────────────────────────────────────────────────────────────

STEP2_EXTRACT_PROMPT = f"""Extract 7 fields from the transcribed Israeli medical form text.

🎯 CRITICAL RULES:

1️⃣ NAMES (שם_פרטי, שם_משפחה):
   • Extract from "HANDWRITTEN NAMES" section
   • ⚠️ CRITICAL: If marked "(illegible)" or missing → USE NULL (do NOT guess!)
   • Empty/null is BETTER than wrong name
   • Only extract if clearly visible in the text
   • Confidence 0.65-0.85 for clear names

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

4️⃣ CONFIDENCE:
   • Clear handwritten names: 0.70-0.85
   • Slightly unclear names: 0.55-0.70
   • Illegible names: 0.0 + null (DO NOT GUESS!)
   • Sticker numbers (clear): 0.85-0.95
   • Handwritten ID: 0.65-0.85
   • Printed text: 0.85-0.95
   • Missing completely: 0.0 + null

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

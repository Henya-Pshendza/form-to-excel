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
   - If unclear, write your best attempt + add "(unclear handwriting)"

📍 STICKERS (usually white/yellow barcode stickers):
   - Look for sticker labeled "מרכזי" or near the word מרכזי
   - Read the number on/near the sticker
   - Look for multiple stickers — read ALL numbers

📍 COMMITMENT NUMBERS:
   - Look for labels: "מספר התחייבות", "התחייבות", "דרישה", "דגימה"
   - Usually printed or stamped, NOT on stickers
   - Different from מרכזי numbers!

📍 STAMPS:
   - "התקבל" stamp — read the date inside it (DD/MM/YYYY format)
   - Any other stamps with dates or numbers

📍 OTHER FIELDS:
   - ת.ז. (ID number) — 8-9 digits
   - Organization name (header/logo: כללית, מכבי, מאוחדת, לאומית)

OUTPUT FORMAT — organize clearly:
```
=== HANDWRITTEN NAMES ===
שם פרטי: [transcribe exactly]
שם משפחה: [transcribe exactly]

=== STICKERS (מרכזי) ===
Sticker 1: [number + location description]
Sticker 2: [number + location description]

=== COMMITMENT NUMBERS (התחייבות) ===
[list all numbers found with their labels]

=== STAMPS ===
[list all stamps and dates]

=== PRINTED FIELDS ===
[other fields]
```

⚠️ CRITICAL: Do NOT skip handwritten Hebrew names even if hard to read!"""

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Extract structured fields from the transcribed text
# ─────────────────────────────────────────────────────────────────────────────

STEP2_EXTRACT_PROMPT = f"""Extract 7 fields from the transcribed Israeli medical form text.

🎯 CRITICAL RULES:

1️⃣ NAMES (שם_פרטי, שם_משפחה):
   • Extract from "HANDWRITTEN NAMES" section FIRST
   • Even if marked "(unclear)" — extract it anyway with confidence 0.60-0.75
   • Hebrew names only (not organization names)
   • If completely missing → null

2️⃣ מספר_מרכזי vs מספר_התחייבות — DO NOT CONFUSE:
   ✅ מספר_מרכזי = Numbers from "STICKERS (מרכזי)" section OR near word "מרכזי"
   ✅ מספר_התחייבות = Numbers from "COMMITMENT NUMBERS" section OR near labels: "התחייבות"/"דרישה"/"דגימה"
   
   ⚠️ If unclear which is which:
      - Sticker numbers → מרכזי
      - Stamped/printed form field numbers → התחייבות
      - When in doubt: put in BOTH (better duplicate than miss)

3️⃣ VALIDATION:
   • מספר_מרכזי: Usually 6-8 digits, often on physical sticker
   • מספר_התחייבות: Usually 8-12 digits, printed on form
   • If ONE number appears twice in text → include ONCE in the correct field
   • If truly 2+ different numbers → include ALL in list

4️⃣ CONFIDENCE:
   • Handwritten Hebrew names: 0.60-0.80 (don't reject!)
   • Sticker numbers (clear): 0.80-0.95
   • Printed text: 0.85-0.95
   • Unclear but visible: 0.50-0.70
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

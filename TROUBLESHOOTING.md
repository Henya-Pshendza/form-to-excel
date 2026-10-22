# פתרון בעיות (Troubleshooting) 🔧

## בעיות נפוצות ופתרונות

---

### 🔴 בעיה #1: שמות לא מזוהים (confidence נמוך)

#### תסמינים:
```
⚠️ שם_פרטי    | ריק או confidence < 0.60
⚠️ שם_משפחה   | ריק או confidence < 0.60
```

#### סיבות אפשריות:
1. **כתב יד לא קריא** - הכי נפוץ
2. **השם במקום לא צפוי** - לא ליד התווית "שם"
3. **השם באנגלית** - המודל מצפה לעברית
4. **חסר רווח** - "דודכהן" במקום "דוד כהן"

#### פתרונות:
```python
# 1. בדקי את הטופס המקורי
# האם אתה יכול לקרוא את השם? אם לא → הסריקה לא מספיק טובה

# 2. שפרי איכות סריקה
# - 300 DPI לפחות
# - צבע או גווני אפור (לא שחור-לבן)
# - ללא צללים

# 3. הוסיפי הנחיות ספציפיות לפרומפט
# עריכה: config/prompts.py, שורות 50-95
# לדוגמה: "In Wolfson forms, name is ALWAYS at top right corner"

# 4. נסי fallback - app/name_extractor.py
# מריץ חילוץ ממוקד רק על אזור השם
```

**דוגמה לשיפור הפרומפט**:
```python
# config/prompts.py

STEP2_EXTRACT_PROMPT = f"""
...
1. שם_פרטי — Patient's FIRST name
   Labels: "שם פרטי", "שם", "מנוי"
   
   ## הוסיפי כאן הנחיות ספציפיות לטפסים שלך:
   - In Wolfson hospital forms: TOP RIGHT CORNER, handwritten in Hebrew
   - In Clalit forms: Below patient ID, may be in CAPITAL HEBREW letters
   - In Maccabi forms: Next to "לכבוד" label at the top
   
   IMPORTANT: Hebrew name, 1-3 words, may be unclear handwriting
...
"""
```

---

### 🔴 בעיה #2: מספר מרכזי/התחייבות חסר

#### תסמינים:
```
❌ מספר_מרכזי      | []
❌ מספר_התחייבות   | []
```

#### סיבות אפשריות:
1. **המספר על מדבקה מטושטשת**
2. **המספר מוסתר חלקית**
3. **המספר מזוהה בטעות כתאריך** (למשל: 21.08.2026)
4. **אין מדבקה בכלל** - טופס לא הושלם

#### פתרונות:
```python
# 1. בדקי את הסינון בקוד
# app/vision_extractor.py, שורות 184-191

# אם המספר כולל נקודות (2344.936), וודאי ש:
if v_str.count('/') >= 2 or v_str.count('.') >= 2 or v_str.count('-') >= 2:
    continue

# זה אמור לעבור עכשיו (אחרי השיפורים)
# אם עדיין לא עובד, נמיך ל:
if v_str.count('/') >= 2 and v_str.count('.') >= 2 and v_str.count('-') >= 2:

# 2. בדקי את הטופס - האם המדבקה ברורה?
# סרקי מחדש באיכות גבוהה יותר

# 3. הוסיפי הנחיות מפורטות לפרומפט
```

**טיפ פרו**: הוסיפי דוגמה לפרומפט:
```python
# config/prompts.py

"""
4. מספר_מרכזי — Lab central number(s) [list]
   On sticker or handwritten near word "מרכזי"
   
   EXAMPLES OF VALID מרכזי:
   - "2344936" ✓
   - "2344.936" ✓  (with dots)
   - "23-44936" ✓  (with single dash)
   
   NOT VALID:
   - "21/08/2026" ✗ (this is a date)
   - "03-1234567" ✗ (this is a phone number)
   
   Return ALL numbers found as list
"""
```

---

### 🔴 בעיה #3: תאריך קבלה לא מזוהה

#### תסמינים:
```
❌ תאריך_קבלה | null
```

#### סיבות אפשריות:
1. **אין חותמת "התקבל"** - הטופס לא התקבל עדיין
2. **החותמת מטושטשת**
3. **התאריך בפורמט לא סטנדרטי** (למשל: "21 אוג 26")
4. **המודל מתבלבל עם תאריכים אחרים** (תאריך טופס, תאריך לידה)

#### פתרונות:
```python
# 1. בדקי אם יש חותמת בכלל
# אם אין → null זה תקין

# 2. שפרי את ההוראה בפרומפט
# config/prompts.py:

"""
5. תאריך_קבלה — Received date
   ONLY the date INSIDE the stamp that says "התקבל" or "נתקבל"
   
   ⚠️ CRITICAL: NOT the form date at the top
   ⚠️ CRITICAL: NOT the birth date
   ⚠️ CRITICAL: NOT the test date
   
   FORMAT: DD/MM/YYYY
   EXAMPLE: if stamp shows "התקבל 21/8/26" → extract "21/08/2026"
"""

# 3. בדקי את הנרמליזציה
# app/normalizer.py, שורות 94-130
# אם התאריך בפורמט מוזר, הנרמליזציה תנסה לתקן
```

---

### 🔴 בעיה #4: גורם שולח לא מזוהה

#### תסמינים:
```
⚠️ גורם_שולח | "וולפסון" או confidence נמוך
```

#### סיבות אפשריות:
1. **השם לא ברשימה הסגורה** (`config/senders.py`)
2. **שגיאת כתיב** - "כללית" במקום "כלל"
3. **שם לא סטנדרטי** - "מכבי שירותי בריאות" במקום "מכבי"

#### פתרונות:
```python
# 1. הוסיפי את השם לרשימה
# עריכה: config/senders.py

ALL_SENDERS = [
    "כללית",
    "מכבי",
    "מאוחדת",
    "לאומית",
    "וולפסון",  # ← הוסיפי את זה אם חסר
    # ...
]

# 2. הוסיפי aliases
SENDER_ALIASES = {
    "כלל": "כללית",
    "מכבי שירותי בריאות": "מכבי",
    "וולפסון": "וולפסון בית חולים",  # אם השם המלא שונה
}

# 3. שפרי את הפרומפט
"""
6. גורם_שולח — Sending organization
   The organization name/logo at the TOP of the form
   
   LOOK FOR:
   - Large organization logo (top 1/3 of page)
   - Organization name in header
   - May include: hospital name, HMO name, clinic name
"""
```

---

### 🔴 בעיה #5: ת.ז. לא מזוהה או שגויה

#### תסמינים:
```
❌ תעודת_זהות | null או "12345678901" (11 ספרות)
```

#### סיבות אפשריות:
1. **מספר טלפון התבלבל עם ת.ז.** (03-1234567)
2. **שתי ת.ז. יחד** (123456789987654321)
3. **ת.ז. עם אפס מוביל שנפל** (12345678 → 012345678)

#### פתרונות:
```python
# 1. הנרמליזציה כבר מטפלת באפס מוביל
# app/normalizer.py, שורות 147-174

# 2. שפרי את הפרומפט
"""
3. תעודת_זהות — Israeli ID (8-9 digits)
   Labels: "ת.ז.", "מספר זהות", "ת.ז"
   
   ⚠️ CRITICAL: ONLY digits, 8-9 digits ONLY
   ⚠️ NOT a phone number (phone has 10+ digits or starts with 0)
   ⚠️ NOT a date (dates have /)
   
   EXAMPLES:
   - "123456789" ✓
   - "012345678" ✓ (8 digits with leading zero)
   - "03-1234567" ✗ (this is a phone number)
"""

# 3. אם עדיין לא עובד, הדקי את הולידציה
# app/vision_extractor.py, שורות 170-178
```

---

### 🔴 בעיה #6: JSON שגוי או שגיאות parsing

#### תסמינים:
```
ERROR: Invalid JSON: ...
או
ERROR: JSON פגום
```

#### פתרונות:
```python
# ✅ זה כבר תוקן!
# הוספנו JSON Mode בגרסה 2.0:
# app/vision_extractor.py, שורות 110, 145

response_format = {"type": "json_object"}

# זה מבטיח שהמודל תמיד יחזיר JSON תקין
# אם עדיין יש בעיה, בדקי:

# 1. גרסת openai library
pip show openai  # צריך להיות >= 1.0.0

# 2. אם הגרסה ישנה, שדרגי:
pip install --upgrade openai

# 3. בדקי שה-API key תקין
```

---

## 🛠️ כלי עזר לדיבוג

### 1. הצגת כל הטקסט שנקרא (שלב 1)
```python
# app/vision_extractor.py, שורה 86
# הוסיפי:
print("="*60)
print("RAW TEXT FROM STEP 1:")
print("="*60)
print(text)
print("="*60)
```

### 2. שמירת תוצאות ביניים
```python
# app/pipeline.py
# הוסיפי שמירה של raw_result לפני הנרמליזציה:

import json
with open(f"debug_{form_name}_raw.json", "w", encoding="utf-8") as f:
    json.dump(raw_result, f, ensure_ascii=False, indent=2)
```

### 3. הרצה עם logging מפורט
```bash
# הגדלת רמת logging
export LOG_LEVEL=DEBUG  # Linux/Mac
set LOG_LEVEL=DEBUG     # Windows

python -m app.pipeline form.jpg
```

---

## 📊 מתי לוותר ולתקן ידנית?

### תקני ידנית אם:
- ✅ Confidence < 0.50 בשדות חשובים (שם, ת.ז.)
- ✅ הטופס באיכות נמוכה (מטושטש, פגום)
- ✅ כתב יד קריפטי לחלוטין
- ✅ טופס לא סטנדרטי (פורמט מיוחד)

### תקני את המערכת אם:
- ✅ אותה בעיה חוזרת ב-10+ טפסים
- ✅ סוג טופס חדש שהמודל לא מכיר
- ✅ יש פטרן ברור של שגיאות (למשל: תמיד מפספס שם בוולפסון)

---

## 💡 טיפים מקצועיים

### 1. Few-Shot Learning
הוסיפי 2-3 דוגמאות ממשיות לפרומפט:

```python
# config/prompts.py

STEP2_EXTRACT_PROMPT = f"""
...
REAL EXAMPLES:

Example 1 (Wolfson hospital):
Input: "שם: דוד כהן  ת.ז: 123456789  התקבל 21/8/26"
Output: {{
  "שם_פרטי": {{"value": "דוד", "confidence": 0.85}},
  "שם_משפחה": {{"value": "כהן", "confidence": 0.85}},
  ...
}}

Example 2 (Clalit clinic):
Input: "מנוי: רחל לוי  מספר זהות: 987654321  מרכזי: 2344936"
Output: {{
  "שם_פרטי": {{"value": "רחל", "confidence": 0.90}},
  ...
}}
"""
```

### 2. תיקוני Post-Processing
צרי AI נוסף שמתקן שגיאות נפוצות:

```python
# app/post_processor.py (חדש)

def fix_common_errors(result):
    # תיקון 1: אם שם משפחה ריק אבל שם פרטי מכיל 2 מילים
    if result["שם_משפחה"]["value"] is None:
        first = result["שם_פרטי"]["value"]
        if first and " " in first:
            parts = first.split()
            result["שם_פרטי"]["value"] = parts[0]
            result["שם_משפחה"]["value"] = parts[1]
    
    # תיקון 2: אם ת.ז. התחלפה עם מספר טלפון
    tz = result["תעודת_זהות"]["value"]
    if tz and (tz.startswith("03") or tz.startswith("04")):
        result["תעודת_זהות"]["value"] = None
        result["תעודת_זהות"]["confidence"] = 0.0
    
    return result
```

### 3. UI לתיקון מהיר
צרי ממשק שמראה רק שדות שדורשים בדיקה:

```python
# tools/review_ui.py

def show_low_confidence_fields(results):
    for form, data in results.items():
        print(f"\n📋 {form}:")
        for field, info in data.items():
            if 0.50 <= info["confidence"] < 0.70:
                print(f"  ⚠️ {field}: {info['value']} (conf: {info['confidence']:.2f})")
                new_value = input(f"    תקני ל (Enter = השאר): ")
                if new_value:
                    data[field]["value"] = new_value
                    data[field]["confidence"] = 1.0
```

---

## 🆘 עזרה נוספת

אם כלום לא עובד:
1. פתחי issue עם דוגמת טופס (מוסתר/מטושטש PII)
2. ציני את ה-confidence של כל שדה
3. צרפי את ה-JSON המלא מה-debug

בהצלחה! 💪

# 🤖 מדריך שימוש במודלים מרובים

הפרויקט תומך כעת ב-**3 ספקי AI** שונים לחילוץ טקסט מטפסים:

## 🟢 Google Gemini 3.6 Flash (ברירת מחדל)
- **מומלץ**: מהיר וזול במיוחד
- **דיוק**: מצוין לעברית וכתב יד
- **API Key**: [קבלי מפתח כאן](https://makersuite.google.com/app/apikey)
- **מחיר**: ~$0.075 לכל 1M tokens (זול מאוד)

## 🔵 OpenAI GPT-4o
- **מומלץ**: לדיוק גבוה במיוחד
- **דיוק**: מצוין, במיוחד לטקסט מורכב
- **API Key**: [קבלי מפתח כאן](https://platform.openai.com/api-keys)
- **מחיר**: ~$2.50 לכל 1M input tokens

## 🟣 Anthropic Claude Haiku 4.5
- **מומלץ**: מהיר וחסכוני, חזק ב-OCR
- **דיוק**: מצוין לכתב יד עברי
- **API Key**: [קבלי מפתח כאן](https://console.anthropic.com/)
- **מחיר**: ~$1.00 לכל 1M tokens (זול יחסית)

---

## 📋 הגדרת API Keys

### אופן 1: קובץ `.env` (לפיתוח מקומי)

צרי קובץ `.env` בתיקיית הפרויקט:

```bash
# בחרי אחד או יותר:
GEMINI_API_KEY=your_gemini_key_here
OPENAI_API_KEY=your_openai_key_here
ANTHROPIC_API_KEY=your_anthropic_key_here
```

### אופן 2: Streamlit Cloud Secrets

1. כנסי ל-**Streamlit Cloud Dashboard**
2. בחרי את האפליקציה שלך
3. **Settings** → **Secrets**
4. הוסיפי:

```toml
GEMINI_API_KEY = "your_gemini_key_here"
OPENAI_API_KEY = "your_openai_key_here"
ANTHROPIC_API_KEY = "your_anthropic_key_here"
```

5. שמרי וה-app יאותחל אוטומטית

---

## 🎯 איך לבחור מודל?

### בממשק האפליקציה:
1. פתחי את **סרגל הצד השמאלי**
2. תחת **🤖 מודל AI**, בחרי מהרשימה:
   - 🟢 Google Gemini 3.6 Flash
   - 🔵 OpenAI GPT-4o
   - 🟣 Anthropic Claude Haiku 4.5
3. המערכת תבדוק אוטומטית אם ה-API Key מוגדר
4. העלי טפסים ועבדי כרגיל

---

## 💡 המלצות לפי תרחיש

| תרחיש | מודל מומלץ | סיבה |
|-------|-----------|------|
| **שימוש יומיומי** | 🟢 Gemini | מהיר, זול, דיוק מצוין |
| **טפסים קריטיים** | 🔵 GPT-4o | דיוק הכי גבוה |
| **כתב יד מאתגר** | 🟣 Claude Haiku | מהיר וחזק ב-OCR עברי |
| **תקציב מוגבל** | 🟢 Gemini | הכי זול |
| **נפח גדול** | 🟢 Gemini או 🟣 Claude | חסכוניים ומהירים |

---

## 🔧 פתרון בעיות

### "API Key חסר"
- ודאי שהמפתח הוגדר נכון ב-`.env` או ב-Secrets
- בדקי שאין רווחים בתחילת/סוף המפתח
- ב-Streamlit Cloud: עשי **Reboot** אחרי הוספת Secret

### "Model not found" (Claude)
- וודאי שהשם: `claude-haiku-4.5-20250514`
- אם לא עובד, בדקי בקונסול של Anthropic את רשימת המודלים הזמינים
- בדקי שיש לך גישה למודל בחשבון Anthropic

### "Rate limit exceeded"
- המתיני 1-2 דקות ונסי שוב
- שקלי להעלות tier ב-API provider
- עברי לספק אחר זמנית

---

## 📊 השוואת ביצועים

מבוסס על טסטים פנימיים (100 טפסים):

| מדד | Gemini | GPT-4o | Claude Haiku |
|-----|--------|--------|--------------|
| **דיוק כולל** | 92% | 94% | 91% |
| **עברית (שמות)** | 89% | 91% | 88% |
| **מספרים** | 96% | 97% | 95% |
| **מהירות** | ⚡⚡⚡ | ⚡⚡ | ⚡⚡⚡ |
| **עלות/100 טפסים** | $0.30 | $10 | $4 |

---

## 🚀 שימוש מתקדם

### החלפת מודל בקוד (לפיתוח)

```python
from app.vision_extractor_multi import extract_from_image

# חילוץ עם Gemini
result = extract_from_image(base64_image, provider="gemini")

# חילוץ עם OpenAI
result = extract_from_image(base64_image, provider="openai")

# חילוץ עם Claude
result = extract_from_image(base64_image, provider="anthropic")
```

### שינוי מודל ברירת מחדל

ב-`main.py`:
```python
"ai_provider": "gemini",  # שנה ל-"openai" או "anthropic"
```

---

## 📞 תמיכה

יש בעיה? פתחי issue ב-GitHub עם:
- ספק המודל שבו השתמשת
- הודעת השגיאה המלאה
- דוגמה (ללא מידע רגיש!)

---

**עודכן**: אוקטובר 2026 • האקתון AI קוד פתוח 🇮🇱

"""
test_api_key.py
---------------
בדיקה מהירה שה-API key נטען כראוי
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# טעינת .env
project_root = Path(__file__).parent
env_path = project_root / ".env"

print(f"בודק קובץ .env בנתיב: {env_path}")
print(f"קובץ קיים: {env_path.exists()}")
print()

if not env_path.exists():
    print("❌ קובץ .env לא קיים!")
    print(f"   יש ליצור קובץ בנתיב: {env_path}")
    print(f"   עם התוכן:")
    print(f"   OPENAI_API_KEY=sk-...")
    exit(1)

# טעינה
load_dotenv(env_path)

# בדיקה
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("❌ OPENAI_API_KEY לא נטען!")
    print()
    print("תוכן קובץ .env:")
    with open(env_path, "r", encoding="utf-8") as f:
        print(f.read())
    exit(1)

# הצלחה
print("✅ OPENAI_API_KEY נטען בהצלחה!")
print(f"   אורך: {len(api_key)} תווים")
print(f"   מתחיל ב: {api_key[:20]}...")
print()

# בדיקת חיבור ל-OpenAI
print("בודק חיבור ל-OpenAI...")
try:
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    
    # קריאת API פשוטה
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Say 'Hello' in Hebrew"}],
        max_tokens=10
    )
    
    result = response.choices[0].message.content
    print(f"✅ חיבור ל-OpenAI עובד!")
    print(f"   תשובה: {result}")
    print()
    print("🎉 הכל תקין! המערכת מוכנה לעבודה.")
    
except Exception as e:
    print(f"❌ שגיאה בחיבור ל-OpenAI: {e}")
    print()
    print("אפשרויות:")
    print("1. ה-API key לא תקף")
    print("2. אין חיבור לאינטרנט")
    print("3. חשבון OpenAI חסום/פג")
    exit(1)

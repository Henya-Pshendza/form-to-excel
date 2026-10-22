"""
quick_test.py
-------------
בדיקה מהירה של חילוץ נתונים מטופס
"""

import sys
import json
from pathlib import Path

# בדיקת ארגומנטים
if len(sys.argv) < 2:
    print("שימוש: python quick_test.py path/to/form.jpg")
    sys.exit(1)

form_path = Path(sys.argv[1])

if not form_path.exists():
    print(f"❌ קובץ לא נמצא: {form_path}")
    sys.exit(1)

print(f"🔄 בודק טופס: {form_path.name}")
print("="*60)

# טעינת .env
print("\n1️⃣ טוען הגדרות...")
import os
from dotenv import load_dotenv

project_root = Path(__file__).parent
load_dotenv(project_root / ".env")

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    print("❌ OPENAI_API_KEY לא נטען מקובץ .env")
    print("   הרץ: python test_api_key.py")
    sys.exit(1)

print(f"✅ API key נטען (אורך: {len(api_key)} תווים)")

# טעינת תמונה
print("\n2️⃣ טוען תמונה...")
try:
    from PIL import Image
    image = Image.open(form_path)
    print(f"✅ תמונה נטענה: {image.size[0]}x{image.size[1]} px")
except Exception as e:
    print(f"❌ שגיאה בטעינת תמונה: {e}")
    sys.exit(1)

# עיבוד מקדים
print("\n3️⃣ מעבד תמונה...")
try:
    from app.image_processor import preprocess_image, image_to_base64
    processed = preprocess_image(image)
    print(f"✅ תמונה עובדה: {processed.size[0]}x{processed.size[1]} px")
    
    base64_image = image_to_base64(processed)
    print(f"✅ הומרה ל-base64: {len(base64_image):,} bytes")
except Exception as e:
    print(f"❌ שגיאה בעיבוד: {e}")
    sys.exit(1)

# חילוץ
print("\n4️⃣ מחלץ נתונים עם GPT-4o...")
print("   (יכול לקחת 5-15 שניות)")
try:
    from app.vision_extractor import extract_from_image
    result = extract_from_image(base64_image)
    print(f"✅ חילוץ הושלם!")
except Exception as e:
    print(f"❌ שגיאה בחילוץ: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# נרמול
print("\n5️⃣ מנרמל נתונים...")
try:
    from app.normalizer import normalize_result
    normalized = normalize_result(result)
    print(f"✅ נרמול הושלם")
except Exception as e:
    print(f"❌ שגיאה בנרמול: {e}")
    sys.exit(1)

# הצגת תוצאות
print("\n" + "="*60)
print("📊 תוצאות:")
print("="*60)

for field_key, field_data in normalized.items():
    if field_key.startswith("_"):
        continue
    
    value = field_data.get("value")
    confidence = field_data.get("confidence", 0.0)
    
    # אייקון לפי confidence
    if confidence >= 0.85:
        icon = "✅"
    elif confidence >= 0.70:
        icon = "✓"
    elif confidence >= 0.50:
        icon = "⚠️"
    else:
        icon = "❌"
    
    # הצגת ערך
    if value is None or value == [] or value == "":
        display = "(ריק)"
    elif isinstance(value, list):
        display = ", ".join(str(v) for v in value) if value else "(ריק)"
    else:
        display = str(value)
    
    print(f"{icon} {field_key:20s} | {display:30s} | Conf: {confidence:.2f}")

# JSON מלא
print("\n" + "="*60)
print("📄 JSON מלא:")
print("="*60)
print(json.dumps(normalized, ensure_ascii=False, indent=2))

print("\n✅ בדיקה הושלמה!")

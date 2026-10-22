"""
test_improvements.py
--------------------
סקריפט לבדיקת השיפורים שנעשו במערכת.
מריץ חילוץ על טופס בודד ומציג דו"ח מפורט.
"""

import sys
from pathlib import Path

# הוספת הנתיב לפייתון
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from app.vision_extractor import extract_from_image
from app.normalizer import normalize_result
import base64
import json


def test_single_form(image_path: str):
    """
    בודק טופס בודד ומציג דו"ח מפורט.
    
    Args:
        image_path: נתיב לקובץ התמונה
    """
    print(f"\n{'='*60}")
    print(f"בודק טופס: {image_path}")
    print(f"{'='*60}\n")
    
    # קריאת התמונה
    try:
        with open(image_path, 'rb') as f:
            image_data = f.read()
        base64_image = base64.b64encode(image_data).decode('utf-8')
    except Exception as e:
        print(f"❌ שגיאה בקריאת הקובץ: {e}")
        return
    
    # חילוץ
    print("🔄 מריץ חילוץ...")
    try:
        raw_result = extract_from_image(base64_image)
        normalized_result = normalize_result(raw_result)
    except Exception as e:
        print(f"❌ שגיאה בחילוץ: {e}")
        return
    
    # הצגת תוצאות
    print("\n" + "="*60)
    print("תוצאות חילוץ:")
    print("="*60 + "\n")
    
    for field_key, field_data in normalized_result.items():
        if field_key.startswith("_"):
            continue
            
        value = field_data.get("value")
        confidence = field_data.get("confidence", 0.0)
        
        # אייקון לפי confidence
        if confidence >= 0.85:
            icon = "✅"
            status = "מצוין"
        elif confidence >= 0.70:
            icon = "✓"
            status = "טוב"
        elif confidence >= 0.50:
            icon = "⚠️"
            status = "בדקי"
        else:
            icon = "❌"
            status = "חסר/נמוך"
        
        # הצגת הערך
        if value is None or value == [] or value == "":
            display = "(ריק)"
        elif isinstance(value, list):
            display = ", ".join(str(v) for v in value) if value else "(ריק)"
        else:
            display = str(value)
        
        print(f"{icon} {field_key:20s} | {display:30s} | Conf: {confidence:.2f} ({status})")
    
    # סיכום
    print("\n" + "="*60)
    print("סיכום:")
    print("="*60)
    
    total = len([k for k in normalized_result.keys() if not k.startswith("_")])
    filled = len([v for k, v in normalized_result.items() 
                  if not k.startswith("_") and v.get("value") not in (None, [], "")])
    high_conf = len([v for k, v in normalized_result.items() 
                     if not k.startswith("_") and v.get("confidence", 0) >= 0.70])
    needs_check = len([v for k, v in normalized_result.items() 
                       if not k.startswith("_") and 0.50 <= v.get("confidence", 0) < 0.70])
    
    print(f"שדות מלאים:     {filled}/{total} ({filled/total*100:.0f}%)")
    print(f"Confidence גבוה: {high_conf}/{total} ({high_conf/total*100:.0f}%)")
    print(f"דורש בדיקה:     {needs_check}/{total}")
    
    print("\n" + "="*60)
    print("JSON מלא (לדיבוג):")
    print("="*60)
    print(json.dumps(normalized_result, ensure_ascii=False, indent=2))


def compare_results(before_json: str, after_json: str):
    """
    משווה תוצאות לפני/אחרי השיפורים.
    
    Args:
        before_json: נתיב לקובץ JSON עם תוצאות לפני
        after_json: נתיב לקובץ JSON עם תוצאות אחרי
    """
    print(f"\n{'='*60}")
    print("השוואת תוצאות לפני/אחרי")
    print(f"{'='*60}\n")
    
    try:
        with open(before_json, 'r', encoding='utf-8') as f:
            before = json.load(f)
        with open(after_json, 'r', encoding='utf-8') as f:
            after = json.load(f)
    except Exception as e:
        print(f"❌ שגיאה בקריאת הקבצים: {e}")
        return
    
    # מציאת הבדלים
    improvements = []
    degradations = []
    
    for field_key in before.keys():
        if field_key.startswith("_"):
            continue
            
        before_val = before[field_key].get("value")
        before_conf = before[field_key].get("confidence", 0)
        
        after_val = after.get(field_key, {}).get("value")
        after_conf = after.get(field_key, {}).get("confidence", 0)
        
        # בדיקת שיפורים
        if before_val in (None, [], "") and after_val not in (None, [], ""):
            improvements.append(f"✅ {field_key}: ריק → {after_val} (conf: {after_conf:.2f})")
        elif before_conf < after_conf:
            improvements.append(f"📈 {field_key}: confidence {before_conf:.2f} → {after_conf:.2f}")
        
        # בדיקת החמרות
        if before_val not in (None, [], "") and after_val in (None, [], ""):
            degradations.append(f"❌ {field_key}: {before_val} → ריק")
        elif after_conf < before_conf - 0.1:  # ירידה משמעותית
            degradations.append(f"📉 {field_key}: confidence {before_conf:.2f} → {after_conf:.2f}")
    
    # הצגת תוצאות
    print("\nשיפורים:")
    print("-" * 60)
    if improvements:
        for imp in improvements:
            print(imp)
    else:
        print("אין שיפורים")
    
    print("\n\nהחמרות:")
    print("-" * 60)
    if degradations:
        for deg in degradations:
            print(deg)
    else:
        print("✅ אין החמרות!")
    
    print(f"\n{'='*60}")
    print(f"סיכום: {len(improvements)} שיפורים, {len(degradations)} החמרות")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="בדיקת שיפורים במערכת החילוץ")
    subparsers = parser.add_subparsers(dest='command', help='פעולה')
    
    # פקודה: test
    test_parser = subparsers.add_parser('test', help='בדיקת טופס בודד')
    test_parser.add_argument('image', help='נתיב לתמונת הטופס')
    
    # פקודה: compare
    compare_parser = subparsers.add_parser('compare', help='השוואת תוצאות לפני/אחרי')
    compare_parser.add_argument('before', help='JSON לפני השיפורים')
    compare_parser.add_argument('after', help='JSON אחרי השיפורים')
    
    args = parser.parse_args()
    
    if args.command == 'test':
        test_single_form(args.image)
    elif args.command == 'compare':
        compare_results(args.before, args.after)
    else:
        parser.print_help()
        print("\n\nדוגמאות שימוש:")
        print("-" * 60)
        print("בדיקת טופס בודד:")
        print("  python test_improvements.py test path/to/form.jpg")
        print("\nהשוואת תוצאות:")
        print("  python test_improvements.py compare before.json after.json")

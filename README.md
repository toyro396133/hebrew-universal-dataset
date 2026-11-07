# Hebrew Universal Dataset — מאגר עברי אוניברסלי

תשתית פתוחה למחקר, אימון והערכה של מודלי שפה בעברית, ללא תלות בטוקנייזר או בארכיטקטורה.

**סטטוס:** מאגר התחלה ניסיוני. הדוגמאות הסינתטיות מצומצמות ואינן מאגר אימון בהיקף מספק.

## שש רמות
1. משפטים ותיאורים פשוטים
2. יחסים, מאפיינים ופעולות
3. הבנת הקשר, שאלות ושאלות המשך
4. הסקה לוגית במספר שלבים
5. הפשטה והכללה
6. מעקב אחר ישויות לאורך מסמכים

טקסטים מקוריים נמצאים ב־`corpus/samples/`; משימות ותשובות ייחוס ב־`evaluation/samples/`. חלוקות `train`, `validation`, `test` מופרדות ברמת `group_id` כדי לצמצם זליגה.

## הפעלה

נדרשת Python 3.10 ומעלה, ללא תלות בספריות צד שלישי:

```bash
python scripts/validate.py
python -m unittest discover -s tests -v
python scripts/export.py --format text --split train --output exports/train-text.jsonl
python scripts/export.py --format chars --split train --output exports/train-chars.jsonl
python scripts/export.py --format bytes --split train --output exports/train-bytes.jsonl
python scripts/export.py --format messages --split train --output exports/train-messages.jsonl
```

אין לאמן על תשובות ההערכה של validation/test. רישוי הקוד: MIT; הדוגמאות הסינתטיות: CC0-1.0. ייבוא נתונים חיצוניים מחייב בדיקת מקור, רישיון, פרטיות ואיכות.

המבנה הראשוני נועד להתרחב בהדרגה ולאפשר השוואת טוקנים, בייטים, תווים ורשתות מושגיות על אותם מקורות.

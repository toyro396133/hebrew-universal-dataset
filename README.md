# Hebrew Universal Dataset — מאגר עברי אוניברסלי

תשתית פתוחה למחקר, אימון והערכה של מודלי שפה בעברית, ללא תלות בטוקנייזר או בארכיטקטורה.

**סטטוס:** מאגר התחלה ניסיוני. הדוגמאות הסינתטיות מצומצמות ואינן מאגר אימון בהיקף מספק.

## 14 רמות יכולת + סיווג 0 לטקסט שטרם דורג
משפה בסיסית עד בקרה עצמית על הסקה, כולל סיבתיות, העברת ידע, חריגים, תכנון והפשטה היררכית. תיאור מלא ב־`taxonomy/levels.json` וב־`docs/taxonomy.md`.

12 צירי סיווג ו־16 תחומי תוכן מוגדרים ב־`taxonomy/axes.json` וב־`taxonomy/topics.json`. המידע הזה הוא מטא־נתונים למחקר, לא מבנה מושגי הכפוי על המודל.

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


## מחולל ניסויים פרמטרי
המחולל (ללא ספריות חיצוניות) יוצר עולמות נפרדים עם שרשראות העברת קופסה, ועוקב אחר מיקום עצם שנשאר בתוכה:

```bash
python scripts/generate_worlds.py --seed 17 --count-per-split 4 --entities 50 --steps 8 --documents 6 --generalization world --output-dir generated/experiment-17
python scripts/validate.py --root generated/experiment-17
```

הפרמטרים `--entities`, `--steps` ו־`--documents` בלתי תלויים. ערכי `--generalization` הם תוויות לתצורות; כרגע המחולל אינו מממש שוני מוכח בין חוקי האימון לחוקי המבחן. הנתונים נוצרים בתיקייה נפרדת ולא נכנסים אוטומטית למאגר המקורי. מומלץ לפרסם תוצאות מדויקות רק אחרי בדיקה והערכה עצמאית.

ניתן לייצא את הקורפוס בשיטות `text`, `chars`, `bytes`, ואת משימות ה־train כ־`messages`. תשובות ההערכה של test ו־validation אינן נכללות בייצוא שיחות כברירת מחדל.

## קליטה מבוקרת של קורפוסים קיימים

נוסף `scripts/ingest_corpus.py` לקליטת מדגם מקורפוס טבעי אל `staging/` בלבד, בלי מיזוג אוטומטי לנתוני המאגר או תיוג קושי מומצא. לרשימה המאושרת ולמדיניות הרישוי: `sources/registry.json` ו־`docs/natural-corpus-ingestion.md`. `scripts/audit_staging.py` מאמת מקור, זכויות, כפילויות והיעדר זליגת מבחנים; תוצאות פיילוט חי מ־GitHub Actions הן דוח סטטיסטי, לא פרסום הנתונים עצמם.

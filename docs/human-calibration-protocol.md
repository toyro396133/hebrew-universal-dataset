# כיול איכות — פרוטוקול סקירה בלתי תלויה

גרסה 1 היא **תהליך עבודה ולא מודל איכות מכויל**. ידוע שהדירוג האוטומטי הקיים רווי: במדגם של 2,000 קטעים ציון פני־שטח ממוצע היה 99.39, ו־175 משפטים סומנו ללא סימן סיום ברור.

## יצירת חבילת ביקורת מקומית
נדרשת תיקיית `staging` שנוצרה באמצעות `scripts/ingest_corpus.py`. אין להעלות את הקורפוס החיצוני או את חבילת הטקסט ל־GitHub לפני ביקורת זכויות ופרטיות.

```bash
python scripts/ingest_corpus.py --fixture tests/fixtures/wiki-rows.jsonl --limit 50 --output-dir staging/local-example
python scripts/review_calibration.py prepare --stage-dir staging/local-example --output-dir staging/review-example --count 5 --seed 17
```

הפקודה מפיקה `blind-review-packet.jsonl` (מזהה וטקסט בלבד), `internal-manifest.json` (כולל ציוני המודל, מוצפן? **לא** — לכן אסור להציג לבודקים), וקובץ הוראות. שני בודקים קוראים בנפרד את אותו packet, בלי לראות את ציון האלגוריתם או אחד את דירוגי השני.

**אין להקליד ציוני דוגמה בדיווח על נתונים אמיתיים.** שני בודקים אמיתיים חייבים להעריך עצמאית כל קטע ב־4 תחומים (1–5): תקינות לשונית, בהירות, מובנות ללא הקשר, ושימושיות ללמידת עברית. בדיקת נכונות עובדתית אינה כלולה.

הפורמט (דוגמת מבנה בלבד, לא דירוג של משפט אמיתי):
```json
{"id":"id-from-packet","reviewer_id":"A","ratings":{"language_quality":3,"clarity":3,"context_independence":3,"training_usefulness":3}}
```

לאחר מכן:
```bash
python scripts/review_calibration.py evaluate --manifest staging/review-example/internal-manifest.json --ratings-a staging/ratings-A.jsonl --ratings-b staging/ratings-B.jsonl --output staging/calibration-report.json
```

## מה מחושב
- שיעור הסכמה מדויקת, מחלוקות של 2 דרגות ומעלה, Cohen weighted kappa לכל ממד.
- מתאם Pearson **תיאורי בלבד** בין ציון פני־השטח לבין ממוצע שני בודקים (כשיש שונות).
- גודל מדגם, טווח הציונים האוטומטיים, מספר ציונים שונים, מספר דוגמאות holdout.
- אין אימון משקולות אוטומטי, אין הפקת אמת עובדתית ואין אישור פרסום.

הכנסת שני קובצי דירוג של אותו בודק אינה מאומתת טכנית כביקורת עצמאית. יש לקיים זאת כנהלי מחקר מתועדים.

## המשך
אחרי תוצאות אנושיות אמיתיות: להכריע במחלוקות, לבנות סולם אנושי מוסכם, לבצע כיול על חלק מהדוגמאות ולהעריך על holdout לפי קבוצות מקור. אם אין שונות בציון (כמו במדגם הראשון), אין לנסות לפרש מתאם כמדד הצלחה — יש לשפר את תכונות הדירוג לפני כיול.

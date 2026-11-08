# AI Reviewer A — גישת נתונים וביקורת שחזור (8.11.2026)

**סטטוס: BLOCKED — no sentence-level review performed.** מסמך זה אינו תחליף לתוצאות הביקורת המבוקשות. אין לפרש אותו ככיול או כהערכת איכות עברית.

## זיהוי המשימה והמקור
- Repository: `toyro396133/hebrew-universal-dataset`
- Base: PR #4 / `598ce74760b93d9c7a149d00d4e8ceedc16df991`
- Reviewer: `AI_A`; model: `GPT-6` (build/version ID unavailable); type: AI, not human
- Dataset: `tomron87/hebrew-wikipedia-sentences-corpus`, configuration `default`, split `train`
- Expected source revision: `76fe89e00b5cfac26b85af6b0a289590993c1753`
- Pilot commands: `ingest_corpus.py --fetch --strategy spread --seed 17 --limit 2000 --scan-limit 5000 --expected-revision 76fe89e00b5cfac26b85af6b0a289590993c1753`, followed by `audit_staging.py` and `review_calibration.py prepare --seed 17 --count 120`.
- Previous run: https://github.com/toyro396133/hebrew-universal-dataset/actions/runs/42427723758 (according to PR #4).
- Previous sample composition (from PR #4): `code_mixed: 17`, `no_terminal: 52`, `routine: 51` (120 total). These are *metadata only*, not qualitative judgements.

## ביצוע ובדיקות
1. PR #4, source registry, ingestion, audit, blind-review generation, and workflow inspected in GitHub.
2. Attempt to retrieve the external source text through direct local HTTPS failed due to DNS/network access unavailable in reviewer execution environment.
3. Web dataset viewer/API retrieval did not return the required records. No private review packet or raw corpus was exposed through the repository or existing Actions artifact.
4. The workflow explicitly does not upload raw text or review packets; previous 120 samples existed only in ephemeral runner storage.
5. **Actual sentences read from the required 120-row sample: 0. Actual sentences rated: 0. Rating JSONL: not produced.**
6. No externally sourced text, fabricated ratings, identifiable private information, or misleading distribution report has been committed.

## ממצאים מוכחים מתוך הקוד
- `review_calibration.py` selects the sample deterministically from the staged records using ID hashes and seed 17, with priority to defined strata. It does not independently perform AI semantic review.
- `ingest_corpus.py` checks the Hugging Face dataset HEAD SHA before and after retrieval. The viewer `/rows` request itself does not pass a revision parameter; matching the old sample depends on the same upstream rows/order being served under the expected SHA.
- The current evaluator requires **two** completed independent label files for four fields; one AI reviewer with six scored dimensions and conceptual/complexity metadata cannot be represented by the existing `evaluate` function without an additional independent format. No existing scores were consulted as a basis for subjective ratings.
- The previously recorded automatic score mean of 99.39 is a surface heuristic; it does not verify linguistic, semantic, conceptual or factual quality.
- `factuality` is unassessed. No calibration, score distribution, inter-annotator reliability, or comparisons to automatic ratings can be computed from missing reviews.

## חסם להשלמת הביקורת בפועל
The AI reviewer must receive the **actual text** of each blinded row in a secure session, without the automatic scores or the other reviewer’s scores. An ephemeral Actions run alone cannot transmit the text to this AI session: its workflow currently emits metadata only and the runner is not an interactive model session. An encrypted private transfer or user-supplied secure attachment of `blind-review-packet.jsonl` (subject to applicable source rights/privacy review) would permit actual independent human-readable review. A raw public repository commit or plain workflow log is **not** an acceptable substitute.

Upon receiving real sample text: review each accessible row, assign independent 1–5 ratings and conceptual/complexity annotations, save a separate `AI_A` JSONL without original text, validate IDs/score bounds, summarize results and optionally compare surface scores **only after scoring is frozen**. The project should keep the generated source manifest private and preserve its sample IDs, seed, snapshot, and run ID.

**No merge requested or authorized.** The task’s original acceptance condition is **not met**.

# Safe handoff from public GitHub Actions to AI Reviewer A

The external Hebrew sample is licensed CC BY-SA 3.0 and may contain content requiring privacy review. A public GitHub repository MUST NOT upload the plaintext review packet or print it in logs. This workflow uploads an **AES-256-GCM encrypted archive only**, encrypted with a private passphrase held as an Actions secret.

## Owner-only setup

1. On your own machine choose a **random passphrase of at least 20 characters**, preferably 32+. Keep it private. Do not share it with ChatGPT, issue comments, code, or logs.
2. In `toyro396133/hebrew-universal-dataset` open **Settings → Secrets and variables → Actions → New repository secret**, create `REVIEW_PACKET_PASSPHRASE` with the private passphrase.
3. After the secret is configured, rerun the failed job from the **Encrypted AI review handoff** workflow (GitHub Actions → relevant run → Re-run failed jobs). If no run exists, a maintainer can make a new push to the feature branch or trigger its workflow by GitHub CLI when supported.
4. Download the **`ai-review-a-encrypted-packet`** artifact ZIP from that Actions run. The ZIP includes a single file `ai-review-a-120.hureview` which contains authenticated encrypted bytes, **not plaintext**. Downloaded ciphertext alone cannot be read without the passphrase.
5. On your Windows machine, install Python 3.11+ and the `cryptography` package if needed:
   ```powershell
   py -m pip install "cryptography>=42,<48"
   ```
6. Unzip the Actions artifact into a local folder, then run from the checked-out source repository:
   ```powershell
   $env:REVIEW_PACKET_PASSPHRASE = Read-Host "Review packet secret"
   py scripts/encrypted_review_handoff.py decrypt --input ".\ai-review-a-120.hureview" --output-dir ".\private-review"
   Remove-Item Env:REVIEW_PACKET_PASSPHRASE
   ```
   The resulting `private-review/blind-review-packet.jsonl` is the **ONLY** file to attach to the AI Reviewer A session. The `internal-manifest.json` contains machine scores and MUST remain withheld until the AI ratings are finished.
7. Ask AI Reviewer A to score actual sentences and publish **only IDs, numeric scores, non-quoting reasons and distributions** to its own PR #5. Do not publish the plaintext or manifest in the public repo. The reviewer should pause on suspicious personal information.

## Technical details

- Source: `tomron87/hebrew-wikipedia-sentences-corpus`, snapshot pinned to `76fe89e00b5cfac26b85af6b0a289590993c1753`.
- Sampling: `ingest_corpus.py --seed 17 --strategy spread --limit 2000 --scan-limit 5000`; `review_calibration.py prepare --seed 17 --count 120`.
- The workflow validates the staging source and review packet before encrypting. The encrypted bundle includes only the blind packet, manifest and instructions; raw source staging remains in temporary runner storage.
- Encryption: AES-256-GCM with random 96-bit nonce and salt, scrypt-derived 256-bit key and authenticated header. Bad passphrases or altered ciphertext fail before writing plaintext.
- The public action **must fail closed** when the secret is unset; never substitute a default passphrase.
- The user's private passphrase should not be shared with any AI chat. This mechanism is confidential transport, **not** a copyright clearance, malware review, privacy guarantee, or independent source-quality audit.
- Public GitHub workflows/artifacts might expose their ciphertext to other people. Protect confidentiality using the secret and do not publish it.

## Alternative
For maximum privacy, run the ingest/prepare workflow wholly on your own machine with lawful source access and hand the resulting packet to the AI reviewer directly.

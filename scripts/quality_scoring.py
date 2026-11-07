#!/usr/bin/env python3
"""Deterministic *surface* triage, not semantic truth, grammar or model understanding.

No learned model is used. Scores have NOT been calibrated to human judgments.
A short, meaningful sentence can score highly. Uncertainty is routed to human
review rather than thrown away. Only hard safety/integrity gates may reject text.
"""
import re
import unicodedata
from collections import Counter

HEBREW = re.compile(r"[\u05d0-\u05ea]")
LATIN = re.compile(r"[A-Za-z]")
EMAIL = re.compile(r"(?<!\S)[^\s@]+@[^\s@]+\.[A-Za-z]{2,}")
URL = re.compile(r"https?://|www\.", re.I)
PHONE = re.compile(r"(?<!\d)(?:\+972|0[2-9])[-\s]?(?:\d[-\s]?){7,9}(?!\d)")
WORDS = re.compile(r"\S+")
TECH = re.compile(r"\b(?:API|JSON|Python|CPU|GPU|SQL|HTML|GitHub|RAM|HTTP)\b|[{};=]", re.I)
LOGICAL = re.compile(r"\b(?:אם|אז|לכן|אולם|אבל|אלא|מפני|בגלל|כאשר|אף)\b")
TERMINATOR = re.compile(r'[.!?׃:;…。؟]$')

SCORER_VERSION = "surface-proxy-1.0"

def hard_rejection(text):
    """Hard reject only untrainable or obvious contact/unsafe content."""
    if not isinstance(text, str) or not text.strip():
        return "empty"
    if len(text) > 15000:
        return "oversize"
    if EMAIL.search(text) or PHONE.search(text):
        return "contact_data"
    if any(unicodedata.category(ch) == "Cc" and ch not in "\t\n\r" for ch in text):
        return "control_character"
    if re.search(r"(.)\1{8,}", text):
        return "noise"
    if not HEBREW.search(text):
        return "no_hebrew"
    return None

def score_text(text):
    """Explainable, uncalibrated surface indicators. Never infers factuality."""
    text = unicodedata.normalize("NFC", text).strip()
    tokens = WORDS.findall(text)
    chars = len(text)
    hebrew = len(HEBREW.findall(text))
    latin = len(LATIN.findall(text))
    ratio = round(hebrew / max(1, hebrew + latin), 4)
    has_punctuation = bool(TERMINATOR.search(text))
    unique = len(set(t.casefold() for t in tokens)) / max(1, len(tokens))
    noisy = sum(unicodedata.category(c).startswith("C") and c not in "\n\r\t" for c in text)
    repeat = max(Counter(text).values(), default=0) / max(1, chars)

    # A majority of Hebrew is good, but code-mixed Hebrew can still be valid.
    script_score = round(100 * min(1.0, ratio / 0.50))
    # Do NOT penalize short messages or long but legal sentences.
    form_score = 100 if has_punctuation else 72
    if len(tokens) == 1 and not has_punctuation:
        form_score = 55
    if noisy:
        form_score = min(form_score, 25)
    diversity_score = round(100 * min(1.0, unique / 0.65))
    signal_score = 100 if repeat < 0.35 else 70 if repeat < 0.55 else 35
    score = round(0.30 * script_score + 0.25 * form_score +
                  0.20 * diversity_score + 0.25 * signal_score)

    flags = []
    if ratio < 0.50:
        flags.append("mixed_script_review")
    if URL.search(text):
        flags.append("url_review")
    if len(tokens) < 5:
        flags.append("short_text")
    if len(tokens) > 70:
        flags.append("long_text")
    if not has_punctuation:
        flags.append("fragment_or_no_terminal_punctuation")
    if score < 60:
        flags.append("low_surface_score")
    if "�" in text:
        flags.append("replacement_character")
    hints = []
    if "?" in text or "؟" in text:
        hints.append("question_form")
    if LOGICAL.search(text):
        hints.append("possible_logical_connector")
    if TECH.search(text):
        hints.append("technical_lexicon_or_symbols")
    if len(tokens) >= 15 or any(ch in text for ch in ",;:"):
        hints.append("possible_multiclause")
    return {
        "version": SCORER_VERSION,
        "surface_score": score,
        "dimensions": {"script_proxy": script_score, "form_proxy": form_score,
                       "lexical_variety_proxy": diversity_score, "signal_proxy": signal_score},
        "signals": {"characters": chars, "words": len(tokens),
                    "hebrew_letter_ratio": ratio, "has_terminal_punctuation": has_punctuation},
        "review_flags": sorted(set(flags)),
        "complexity_hints": sorted(set(hints)),
        "triage": "priority_review" if any(x in flags for x in
                 ("mixed_script_review","url_review","low_surface_score",
                  "replacement_character","fragment_or_no_terminal_punctuation","long_text")) else "routine_review",
        "semantic_quality": None, "factuality": None,
        "human_verified": False
    }

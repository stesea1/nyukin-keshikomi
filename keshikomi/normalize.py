"""Payer name normalization (振込依頼人名の正規化).

Bank statements print the payer as half-width katakana in the limited
Zengin character set, e.g. ``ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ``.  Customer masters usually hold
``株式会社サンプル商事`` / ``カブシキガイシャサンプルショウジ``.  To compare them we:

1. NFKC-normalize (half-width kana -> full-width, full-width ASCII -> ASCII)
2. upper-case latin letters
3. map small kana to large kana (the Zengin set has no small kana: ショウジ -> シヨウジ)
4. unify long-vowel marks / hyphens
5. drop legal-entity markers (カ) / (カ / カブシキガイシャ / 株式会社 / ユ) / ド) ...)
6. drop spaces, punctuation and a leading "振込" style prefix
"""
from __future__ import annotations

import re
import unicodedata

SMALL_TO_LARGE = str.maketrans({
    "ァ": "ア", "ィ": "イ", "ゥ": "ウ", "ェ": "エ", "ォ": "オ",
    "ッ": "ツ", "ャ": "ヤ", "ュ": "ユ", "ョ": "ヨ", "ヮ": "ワ", "ヵ": "カ", "ヶ": "ケ",
    "ぁ": "あ", "ぃ": "い", "ぅ": "う", "ぇ": "え", "ぉ": "お",
    "っ": "つ", "ゃ": "や", "ゅ": "ゆ", "ょ": "よ", "ゎ": "わ",
})

# Long-vowel marks and dash look-alikes all become "ー".
DASHES = re.compile(r"[‐‑‒–—―−ｰ\-－﹣]")

# Legal entity words in full (kanji and katakana spellings).
ENTITY_WORDS = [
    "株式会社", "有限会社", "合同会社", "合資会社", "合名会社",
    "一般社団法人", "一般財団法人", "公益社団法人", "公益財団法人",
    "社団法人", "財団法人", "医療法人", "学校法人", "社会福祉法人",
    "特定非営利活動法人", "NPO法人",
    "カブシキガイシヤ", "カブシキカイシヤ", "ユウゲンガイシヤ", "ユウゲンカイシヤ",
    "ゴウドウガイシヤ", "ゴウドウカイシヤ", "ゴウシガイシヤ", "ゴウメイガイシヤ",
    "イツパンシヤダンホウジン", "イツパンザイダンホウジン",
    "シヤダンホウジン", "ザイダンホウジン", "イリヨウホウジン", "ガツコウホウジン",
    "(株)", "(有)", "(合)", "(同)",
]

# Bank abbreviations: "カ)" prefix, "(カ" suffix, "(カ)" anywhere.
ENTITY_ABBR = ["カ", "ユ", "ド", "メ", "シ", "ザイ", "シヤ", "イ", "ガク", "フク", "トクヒ", "ソ"]
_abbr = "|".join(sorted(ENTITY_ABBR, key=len, reverse=True))
ABBR_RE = re.compile(rf"\(({_abbr})\)|^({_abbr})\)|\(({_abbr})$")

# Typical prefixes some net-banking exports put in the description column.
PREFIX_RE = re.compile(r"^(振込|フリコミ|振込入金|ﾌﾘｺﾐ|カ\)フリコミ)\s*")

PUNCT_RE = re.compile(r"[\s・,，.．。、'\"「」/／]+")


def basic(text: str) -> str:
    """Width/case/kana normalization without removing entity words."""
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", text)
    s = s.upper()
    s = s.translate(SMALL_TO_LARGE)
    s = DASHES.sub("ー", s)
    s = s.replace("（", "(").replace("）", ")")
    return s.strip()


def normalize_name(text: str) -> str:
    """Return a comparison key for a company / payer name."""
    s = basic(text)
    s = PREFIX_RE.sub("", s)
    s = re.sub(r"\s+", "", s)
    for w in ENTITY_WORDS:
        s = s.replace(basic(w), "")
    # abbreviations may appear more than once, e.g. "(カ)" after a prefix was removed
    prev = None
    while prev != s:
        prev = s
        s = ABBR_RE.sub("", s)
    s = PUNCT_RE.sub("", s)
    s = s.replace("(", "").replace(")", "")
    return s


def digits_in(text: str) -> str:
    return re.sub(r"\D", "", basic(text))


def names_match(payer_key: str, candidate_key: str, min_prefix: int = 4) -> bool:
    """Exact key match, or prefix match (bank truncates long names)."""
    if not payer_key or not candidate_key:
        return False
    if payer_key == candidate_key:
        return True
    shorter, longer = sorted((payer_key, candidate_key), key=len)
    return len(shorter) >= min_prefix and longer.startswith(shorter)

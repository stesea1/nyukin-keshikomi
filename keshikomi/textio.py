"""Encoding detection and small parsing helpers shared by the readers."""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path

OUTPUT_ENCODINGS = {"utf8": "utf-8-sig", "sjis": "cp932"}


def decode_bytes(data: bytes, encoding: str = "auto") -> str:
    """Decode UTF-8 (with or without BOM) or Shift_JIS (cp932).

    ``auto`` tries UTF-8 first: valid Shift_JIS text with kana is almost never
    valid UTF-8, so the order is safe.
    """
    if encoding != "auto":
        return data.decode(encoding)
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp932")


def read_text(path: str | Path, encoding: str = "auto") -> str:
    return decode_bytes(Path(path).read_bytes(), encoding)


def parse_amount(s: str | None) -> int:
    """'1,234' / '¥1,234' / '1234円' / '' -> int. Negative with '-' or '△'."""
    if s is None:
        return 0
    t = unicodedata.normalize("NFKC", str(s)).strip()
    t = t.replace(",", "").replace("¥", "").replace("\\", "").replace("円", "").strip()
    if t in ("", "-", "ー"):
        return 0
    neg = t.startswith(("-", "△", "▲"))
    t = t.lstrip("-△▲").strip()
    if "." in t:  # "1234.0" from spreadsheets
        t = t.split(".")[0]
    v = int(t)
    return -v if neg else v


ERA_OFFSETS = {"R": 2018, "令和": 2018, "H": 1988, "平成": 1988}
_era_re = re.compile(r"^(令和|平成|R|H)\s*(\d{1,2}|元)[./年-](\d{1,2})[./月-](\d{1,2})日?$")


def parse_date(s: str) -> date:
    """Accept 2026/10/31, 2026-10-31, 2026年10月31日, 20261031, R8.10.31, 令和8年10月31日."""
    t = unicodedata.normalize("NFKC", s).strip().upper()
    m = _era_re.match(t)
    if m:
        era, y, mo, d = m.groups()
        year = ERA_OFFSETS[era] + (1 if y == "元" else int(y))
        return date(year, int(mo), int(d))
    if re.fullmatch(r"\d{8}", t):
        return date(int(t[:4]), int(t[4:6]), int(t[6:]))
    m = re.match(r"^(\d{4})[./年-](\d{1,2})[./月-](\d{1,2})", t)
    if m:
        return date(*map(int, m.groups()))
    raise ValueError(f"日付を解釈できません: {s!r}")

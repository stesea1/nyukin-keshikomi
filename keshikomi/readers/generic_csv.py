"""Generic net-banking CSV reader (ネットバンキングの入出金明細CSV).

Every bank exports a slightly different CSV.  Columns are found by header
aliases (see ``DEFAULT_ALIASES``); anything unusual can be configured with a
JSON mapping file::

    {"date": "お取引日", "deposit": "お預入金額", "withdrawal": "お引出金額",
     "payer": "お取引内容", "description": "メモ", "skip_rows": 0}

Two amount layouts are supported:

* separate deposit / withdrawal columns (most common), or
* one ``amount`` column plus a ``direction`` column (入金/出金), or a signed amount.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

from ..models import BankTransaction
from ..textio import parse_amount, parse_date, read_text

DEFAULT_ALIASES: dict[str, list[str]] = {
    "date": ["取引日", "勘定日", "日付", "お取引日", "年月日", "入出金日", "date"],
    "deposit": ["入金", "入金額", "入金金額", "お預入れ", "お預入金額", "預入金額", "お預り金額", "deposit"],
    "withdrawal": ["出金", "出金額", "出金金額", "お引出し", "お引出金額", "支払金額", "お支払金額", "withdrawal"],
    "amount": ["金額", "取引金額", "amount"],
    "direction": ["入出金区分", "入払区分", "区分", "direction"],
    "payer": ["振込依頼人名", "依頼人名", "振込依頼人", "お取引内容", "取引内容", "内容", "payer"],
    "description": ["摘要", "摘要内容", "メモ", "備考", "EDI情報", "description", "memo"],
    "row_id": ["照会番号", "取引番号", "明細番号", "row_id"],
}


@dataclass
class ColumnMapping:
    columns: dict[str, str] = field(default_factory=dict)  # logical name -> header text
    skip_rows: int = 0                                     # lines before the header row

    @classmethod
    def from_json(cls, path: str | Path) -> "ColumnMapping":
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        skip = int(raw.pop("skip_rows", 0))
        return cls(columns={k: v for k, v in raw.items() if isinstance(v, str)}, skip_rows=skip)


def _resolve(headers: list[str], mapping: ColumnMapping) -> dict[str, str]:
    stripped = {h.strip(): h for h in headers}
    found: dict[str, str] = {}
    for key, aliases in DEFAULT_ALIASES.items():
        if key in mapping.columns:
            name = mapping.columns[key]
            if name not in stripped:
                raise ValueError(f"マッピングで指定された列「{name}」がCSVにありません: {list(stripped)}")
            found[key] = stripped[name]
            continue
        for a in aliases:
            if a in stripped:
                found[key] = stripped[a]
                break
    if "date" not in found:
        raise ValueError(f"日付列が見つかりません。--mapping で指定してください: {list(stripped)}")
    if not ({"deposit"} <= found.keys() or "amount" in found):
        raise ValueError(f"入金額の列が見つかりません。--mapping で指定してください: {list(stripped)}")
    return found


def read_generic_csv(path: str | Path, mapping: ColumnMapping | None = None,
                     encoding: str = "auto") -> list[BankTransaction]:
    mapping = mapping or ColumnMapping()
    text = read_text(path, encoding)
    lines = text.splitlines()[mapping.skip_rows:]
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    cols = _resolve(reader.fieldnames or [], mapping)
    name = Path(path).name
    out: list[BankTransaction] = []
    for i, row in enumerate(reader, start=mapping.skip_rows + 2):
        raw_date = (row.get(cols["date"]) or "").strip()
        if not raw_date:
            continue  # blank / total lines
        try:
            d = parse_date(raw_date)
        except ValueError:
            continue  # footer such as "合計"
        if "deposit" in cols:
            dep = parse_amount(row.get(cols["deposit"]))
            wd = parse_amount(row.get(cols["withdrawal"])) if "withdrawal" in cols else 0
            direction, amount = ("in", dep) if dep else ("out", wd)
        else:
            amount = parse_amount(row.get(cols["amount"]))
            flag = (row.get(cols["direction"]) or "").strip() if "direction" in cols else ""
            if flag in ("出金", "2", "支払", "out"):
                direction = "out"
            elif flag in ("入金", "1", "預入", "in"):
                direction = "in"
            else:
                direction = "in" if amount >= 0 else "out"
            amount = abs(amount)
        if amount == 0:
            continue
        out.append(BankTransaction(
            row_id=(row.get(cols["row_id"]) or "").strip() if "row_id" in cols else f"{i}",
            value_date=d,
            direction=direction,
            amount=amount,
            payer_name=(row.get(cols["payer"]) or "").strip() if "payer" in cols else "",
            description=(row.get(cols["description"]) or "").strip() if "description" in cols else "",
            source=f"{name}:{i}",
        ))
    return out

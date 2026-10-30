"""Invoice (請求書 / 売掛金残高) and customer master readers.

Column names accept Japanese and English aliases so that exports from
ERP / 販売管理 systems can be used with little or no editing.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from ..models import Customer, Invoice
from ..textio import parse_amount, parse_date, read_text

INVOICE_ALIASES: dict[str, list[str]] = {
    "invoice_no": ["invoice_no", "請求書番号", "請求番号", "伝票番号"],
    "customer_id": ["customer_id", "取引先コード", "得意先コード", "顧客コード"],
    "customer_name": ["customer_name", "取引先名", "得意先名", "顧客名"],
    "customer_kana": ["customer_kana", "取引先カナ", "振込名義", "得意先カナ", "フリガナ"],
    "issue_date": ["issue_date", "請求日", "発行日"],
    "due_date": ["due_date", "支払期日", "入金予定日", "期日"],
    "amount": ["amount", "請求金額", "税込金額", "金額"],
    "paid": ["paid", "入金済額", "消込済額"],
}

CUSTOMER_ALIASES: dict[str, list[str]] = {
    "customer_id": ["customer_id", "取引先コード", "得意先コード"],
    "name": ["name", "取引先名", "得意先名"],
    "kana": ["kana", "振込名義", "取引先カナ", "振込名義カナ"],
    "payer_code": ["payer_code", "振込依頼人コード"],
}


def _pick(row: dict, aliases: list[str], default: str = "") -> str:
    for a in aliases:
        v = row.get(a)
        if v not in (None, ""):
            return v.strip()
    return default


def _rows(path: str | Path, encoding: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(read_text(path, encoding)))
    reader.fieldnames = [h.strip() for h in (reader.fieldnames or [])]
    return list(reader)


def read_invoices(path: str | Path, encoding: str = "auto") -> list[Invoice]:
    out = []
    for n, r in enumerate(_rows(path, encoding), start=2):
        no = _pick(r, INVOICE_ALIASES["invoice_no"])
        if not no:
            continue
        try:
            issue = _pick(r, INVOICE_ALIASES["issue_date"])
            due = _pick(r, INVOICE_ALIASES["due_date"]) or issue
            out.append(Invoice(
                invoice_no=no,
                customer_id=_pick(r, INVOICE_ALIASES["customer_id"]),
                customer_name=_pick(r, INVOICE_ALIASES["customer_name"]),
                customer_kana=_pick(r, INVOICE_ALIASES["customer_kana"]),
                issue_date=parse_date(issue or due),
                due_date=parse_date(due),
                amount=parse_amount(_pick(r, INVOICE_ALIASES["amount"])),
                paid=parse_amount(_pick(r, INVOICE_ALIASES["paid"], "0")),
            ))
        except (ValueError, KeyError) as e:
            raise ValueError(f"{Path(path).name} {n} 行目: {e}") from None
    seen = set()
    for inv in out:
        if inv.invoice_no in seen:
            raise ValueError(f"請求書番号が重複しています: {inv.invoice_no}")
        seen.add(inv.invoice_no)
    return out


def read_customers(path: str | Path, encoding: str = "auto") -> list[Customer]:
    """取引先マスタ. One customer may have several 振込名義 (separated by '|')
    or appear on several rows (e.g. parent company paying on behalf)."""
    by_id: dict[str, Customer] = {}
    for r in _rows(path, encoding):
        cid = _pick(r, CUSTOMER_ALIASES["customer_id"])
        if not cid:
            continue
        c = by_id.setdefault(cid, Customer(cid, _pick(r, CUSTOMER_ALIASES["name"])))
        for k in _pick(r, CUSTOMER_ALIASES["kana"]).split("|"):
            if k.strip() and k.strip() not in c.kana_names:
                c.kana_names.append(k.strip())
        code = _pick(r, CUSTOMER_ALIASES["payer_code"]).lstrip("0")
        if code and code not in c.payer_codes:
            c.payer_codes.append(code)
    return list(by_id.values())

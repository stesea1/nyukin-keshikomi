"""Journal entries (仕訳) for the 消込 result.

One row per debit or credit line; lines of a compound entry share the same
伝票番号.  Typical patterns::

    exact          普通預金 110,000 / 売掛金 110,000
    fee deducted   普通預金 219,560 / 売掛金 220,000
                   支払手数料   440 /
    combined       普通預金  99,000 / 売掛金  66,000 (INV-A)
                                    / 売掛金  33,000 (INV-B)
    overpayment    普通預金  80,000 / 売掛金  77,000
                                    / 仮受金   3,000
    partial        普通預金 300,000 / 売掛金 300,000   (balance stays open)
    unmatched      普通預金  12,345 / 仮受金  12,345   (only with --suspense)
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .models import DiffKind, MatchResult, Status
from .textio import OUTPUT_ENCODINGS


@dataclass
class Accounts:
    bank: str = "普通預金"
    bank_sub: str = ""            # 補助科目 for the bank account, e.g. "サンプル銀行"
    receivable: str = "売掛金"
    fee: str = "支払手数料"
    overpay: str = "仮受金"
    suspense: str = "仮受金"


@dataclass
class JournalLine:
    no: int
    line: int
    date: str
    dr_account: str = ""
    dr_sub: str = ""
    dr_amount: int | None = None
    cr_account: str = ""
    cr_sub: str = ""
    cr_amount: int | None = None
    memo: str = ""
    partner: str = ""
    invoice_no: str = ""
    bank_ref: str = ""


JOURNAL_HEADER = ["伝票番号", "行", "取引日", "借方勘定科目", "借方補助科目", "借方金額",
                  "貸方勘定科目", "貸方補助科目", "貸方金額", "摘要", "取引先", "請求書番号", "明細参照"]


def build_journal(results: list[MatchResult], acc: Accounts | None = None, start_no: int = 1,
                  suspense: bool = False) -> list[JournalLine]:
    acc = acc or Accounts()
    lines: list[JournalLine] = []
    no = start_no
    for r in results:
        t = r.txn
        posted = r.status in (Status.MATCHED, Status.PARTIAL)
        if not posted and not (suspense and t.is_deposit and r.status != Status.SKIPPED):
            continue
        d = t.value_date.strftime("%Y/%m/%d")
        payer = t.payer_name or t.description
        if posted:
            nos = "・".join(i.invoice_no for i in r.invoices)
            memo = f"入金消込 {payer} 請求書 {nos}"
            if r.status == Status.PARTIAL:
                memo += "（一部入金）"
        else:
            memo = f"未確認入金 {payer}"
        n = 1

        def add(**kw):
            nonlocal n
            lines.append(JournalLine(no=no, line=n, date=d, memo=memo, partner=r.customer_name,
                                     bank_ref=t.source, **kw))
            n += 1

        add(dr_account=acc.bank, dr_sub=acc.bank_sub, dr_amount=t.amount)
        if posted:
            for inv in r.invoices:
                add(cr_account=acc.receivable, cr_amount=r.cleared[inv.invoice_no], invoice_no=inv.invoice_no)
            if r.diff_kind == DiffKind.FEE:
                add(dr_account=acc.fee, dr_amount=-r.diff)
            elif r.diff_kind == DiffKind.OVERPAY:
                add(cr_account=acc.overpay, cr_amount=r.diff)
        else:
            add(cr_account=acc.suspense, cr_amount=t.amount)
        no += 1
    _check_balanced(lines)
    return lines


def _check_balanced(lines: list[JournalLine]) -> None:
    totals: dict[int, int] = {}
    for ln in lines:
        totals[ln.no] = totals.get(ln.no, 0) + (ln.dr_amount or 0) - (ln.cr_amount or 0)
    bad = [k for k, v in totals.items() if v != 0]
    if bad:
        raise AssertionError(f"貸借不一致の伝票があります: {bad}")


def _fmt(v: int | None) -> str:
    return "" if v is None else str(v)


def write_journal_csv(lines: list[JournalLine], path: str | Path, encoding: str = "utf8") -> None:
    with open(path, "w", encoding=OUTPUT_ENCODINGS[encoding], newline="") as f:
        w = csv.writer(f)
        w.writerow(JOURNAL_HEADER)
        for ln in lines:
            w.writerow([ln.no, ln.line, ln.date, ln.dr_account, ln.dr_sub, _fmt(ln.dr_amount),
                        ln.cr_account, ln.cr_sub, _fmt(ln.cr_amount), ln.memo, ln.partner,
                        ln.invoice_no, ln.bank_ref])

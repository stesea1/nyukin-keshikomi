"""消込結果 CSV, 未消込請求書 CSV and a Markdown summary report."""
from __future__ import annotations

import csv
from collections import Counter
from datetime import date
from pathlib import Path

from .models import Invoice, MatchResult, Status

STATUS_JA = {
    Status.MATCHED: "消込済",
    Status.PARTIAL: "一部消込",
    Status.NEEDS_REVIEW: "要確認",
    Status.UNMATCHED: "未消込",
    Status.SKIPPED: "対象外",
}

RESULT_HEADER = ["明細参照", "勘定日", "入出金", "金額", "振込依頼人名", "摘要", "ステータス", "ルール",
                 "確度", "取引先コード", "取引先名", "消込請求書", "消込額", "差額", "差額区分", "候補請求書", "理由"]


def result_row(r: MatchResult) -> list[str]:
    t = r.txn
    return [
        t.source, t.value_date.isoformat(), "入金" if t.is_deposit else "出金", str(t.amount),
        t.payer_name, t.description, STATUS_JA[r.status], r.rule, r.confidence,
        r.customer_id, r.customer_name,
        " / ".join(i.invoice_no for i in r.invoices),
        " / ".join(str(r.cleared[i.invoice_no]) for i in r.invoices),
        str(r.diff) if r.diff else "", r.diff_kind.value,
        " / ".join(i.invoice_no for i in r.candidates), r.reason,
    ]


def write_result_csv(results: list[MatchResult], path: str | Path) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(RESULT_HEADER)
        w.writerows(result_row(r) for r in results)


def write_open_invoices(invoices: list[Invoice], path: str | Path, as_of: date) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["請求書番号", "取引先コード", "取引先名", "支払期日", "請求金額", "入金済額", "残額", "期日経過日数"])
        for i in sorted(invoices, key=lambda x: (x.due_date, x.invoice_no)):
            if i.open_amount > 0:
                w.writerow([i.invoice_no, i.customer_id, i.customer_name, i.due_date.isoformat(), i.amount,
                            i.paid, i.open_amount, max(0, (as_of - i.due_date).days)])


def _yen(v: int) -> str:
    return f"{v:,}円"


def summary_markdown(results: list[MatchResult], invoices: list[Invoice], as_of: date) -> str:
    deposits = [r for r in results if r.txn.is_deposit]
    by = Counter(r.status for r in deposits)
    amt = Counter()
    for r in deposits:
        amt[r.status] += r.txn.amount
    fee = sum(-r.diff for r in deposits if r.diff_kind.value == "fee")
    over = sum(r.diff for r in deposits if r.diff_kind.value == "overpay")
    open_invs = [i for i in invoices if i.open_amount > 0]
    overdue = [i for i in open_invs if i.due_date < as_of]
    auto = by[Status.MATCHED] + by[Status.PARTIAL]
    rate = auto / len(deposits) * 100 if deposits else 0.0

    out = [
        "# 入金消込サマリー", "",
        f"- 基準日: {as_of.isoformat()}",
        f"- 入金明細: {len(deposits)} 件 / {_yen(sum(r.txn.amount for r in deposits))}"
        f"（出金 {sum(1 for r in results if not r.txn.is_deposit)} 件は対象外）",
        f"- 自動消込率: {rate:.0f}%（{auto}/{len(deposits)} 件）", "",
        "| ステータス | 件数 | 金額 |", "|---|---:|---:|",
    ]
    for s in (Status.MATCHED, Status.PARTIAL, Status.NEEDS_REVIEW, Status.UNMATCHED):
        out.append(f"| {STATUS_JA[s]} | {by[s]} | {_yen(amt[s])} |")
    out += ["", f"- 振込手数料として処理した差額: {_yen(fee)}",
            f"- 過入金（仮受金）: {_yen(over)}", ""]

    medium = [r for r in deposits if r.status == Status.MATCHED and r.confidence == "medium"]
    todo = [r for r in deposits if r.status in (Status.NEEDS_REVIEW, Status.UNMATCHED)] + medium
    out += ["## 確認が必要な入金", ""]
    if todo:
        out += ["| 勘定日 | 金額 | 振込依頼人名 | 状態 | 候補 | 理由 |", "|---|---:|---|---|---|---|"]
        for r in todo:
            state = "確度 medium" if r in medium else STATUS_JA[r.status]
            cands = " / ".join(i.invoice_no for i in (r.candidates or r.invoices))
            out.append(f"| {r.txn.value_date} | {_yen(r.txn.amount)} | {r.txn.payer_name or r.txn.description} "
                       f"| {state} | {cands} | {r.reason} |")
    else:
        out.append("なし")
    out += ["", "## 未消込の請求書", "",
            f"- 残 {len(open_invs)} 件 / {_yen(sum(i.open_amount for i in open_invs))}"
            f"（うち期日経過 {len(overdue)} 件 / {_yen(sum(i.open_amount for i in overdue))}）", ""]
    if open_invs:
        out += ["| 請求書番号 | 取引先 | 支払期日 | 残額 | 経過日数 |", "|---|---|---|---:|---:|"]
        for i in sorted(open_invs, key=lambda x: x.due_date):
            out.append(f"| {i.invoice_no} | {i.customer_name} | {i.due_date} | {_yen(i.open_amount)} "
                       f"| {max(0, (as_of - i.due_date).days)} |")
    return "\n".join(out) + "\n"

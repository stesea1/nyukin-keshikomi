"""Command line interface.

    python -m keshikomi match --bank sample/bank_generic.csv \
        --invoices sample/invoices.csv --customers sample/customers.csv --out out/
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from .export_mf import write_mf_csv
from .journal import Accounts, build_journal, write_journal_csv
from .matcher import MatchConfig, Matcher
from .readers import ColumnMapping, read_bank, read_customers, read_invoices
from .report import STATUS_JA, summary_markdown, write_open_invoices, write_result_csv
from .textio import parse_date


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="keshikomi", description="銀行入金明細と請求書の自動消込")
    sub = p.add_subparsers(dest="command", required=True)
    m = sub.add_parser("match", help="入金明細と請求書を照合し、消込結果・仕訳を出力する")
    m.add_argument("--bank", required=True, nargs="+", help="入出金明細ファイル（複数可）")
    m.add_argument("--bank-format", choices=["auto", "generic", "zengin"], default="auto")
    m.add_argument("--bank-encoding", default="auto", help="auto / utf-8 / cp932")
    m.add_argument("--mapping", help="汎用CSVの列マッピング JSON")
    m.add_argument("--zengin-era", choices=["auto", "reiwa", "western"], default="auto",
                   help="全銀フォーマットの年（YY）の解釈")
    m.add_argument("--invoices", required=True, help="請求書（売掛金残高）CSV")
    m.add_argument("--customers", help="取引先マスタ CSV（振込名義・振込依頼人コード）")
    m.add_argument("--out", required=True, help="出力フォルダ")
    m.add_argument("--fee-tolerance", type=int, default=880, help="振込手数料として許容する不足額（円）")
    m.add_argument("--overpay-max", type=int, default=None, help="これを超える過入金は要確認にする（円）")
    m.add_argument("--max-combo", type=int, default=4, help="まとめ入金で組み合わせる請求書の最大件数")
    m.add_argument("--accept-unique-amount", action="store_true",
                   help="振込名義が不明でも、金額が未入金請求書の中で一意なら消込済にする（確度 medium）。既定は要確認")
    m.add_argument("--bank-account", default="", help="普通預金の補助科目（例: サンプル銀行）")
    m.add_argument("--suspense", action="store_true", help="未消込の入金を仮受金で仕訳する")
    m.add_argument("--start-no", type=int, default=1, help="仕訳の伝票番号の開始値")
    m.add_argument("--mf-encoding", choices=["sjis", "utf8"], default="sjis",
                   help="マネーフォワード取込CSVの文字コード")
    m.add_argument("--as-of", help="基準日（期日経過の計算用）YYYY-MM-DD。省略時は明細の最終日")
    return p


def run_match(a: argparse.Namespace) -> int:
    mapping = ColumnMapping.from_json(a.mapping) if a.mapping else None
    txns = []
    for f in a.bank:
        txns += read_bank(f, a.bank_format, a.bank_encoding, mapping, a.zengin_era)
    invoices = read_invoices(a.invoices)
    customers = read_customers(a.customers) if a.customers else []
    cfg = MatchConfig(fee_tolerance=a.fee_tolerance, overpay_max=a.overpay_max, max_combo=a.max_combo,
                      accept_unique_amount=a.accept_unique_amount)
    results = Matcher(invoices, customers, cfg).run(txns)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    acc = Accounts(bank_sub=a.bank_account)
    lines = build_journal(results, acc, start_no=a.start_no, suspense=a.suspense)
    as_of = parse_date(a.as_of) if a.as_of else max((t.value_date for t in txns), default=date.today())

    write_result_csv(results, out / "keshikomi_result.csv")
    write_journal_csv(lines, out / "journal.csv")
    write_mf_csv(lines, out / "mf_journal_import.csv", a.mf_encoding, acc.fee)
    write_open_invoices(invoices, out / "open_invoices.csv", as_of)
    (out / "summary.md").write_text(summary_markdown(results, invoices, as_of), encoding="utf-8")

    counts: dict[str, int] = {}
    for r in results:
        counts[STATUS_JA[r.status]] = counts.get(STATUS_JA[r.status], 0) + 1
    print(f"明細 {len(txns)} 件: " + "、".join(f"{k} {v}" for k, v in counts.items()))
    print(f"仕訳 {len(lines)} 行 → {out}/journal.csv, {out}/mf_journal_import.csv")
    print(f"サマリー → {out}/summary.md")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "match":
            return run_match(args)
    except (ValueError, FileNotFoundError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    return 0

"""マネーフォワード クラウド会計「仕訳帳」インポート形式 (columns A-AA, 27 columns).

Column order follows the public help page 「「仕訳帳」をインポートする」
(https://biz.moneyforward.com/support/account/guide/import-books/ib01.html,
checked 2026-10).  Key points from that page:

* 取引日 is ``yyyy/MM/dd``; 取引No is up to 9 digits.
* Rows with the same 取引No and 取引日 whose debit/credit totals agree are
  imported as one compound entry (複合仕訳).
* 借方税額 / 貸方税額 must be 0 or blank.
* 税区分 must be the official or short name shown in the 税区分 screen; when
  left blank the account's default tax category is used.
* 作成日時 / 作成者 / 最終更新日時 / 最終更新者 are ignored on import.

The official template is downloaded from inside the product; this module
reproduces its header row.  If MoneyForward changes the template, adjust
``MF_HEADER``.
"""
from __future__ import annotations

import csv
from pathlib import Path

from .journal import JournalLine
from .textio import OUTPUT_ENCODINGS

MF_HEADER = [
    "取引No", "取引日",
    "借方勘定科目", "借方補助科目", "借方部門", "借方取引先", "借方税区分", "借方インボイス",
    "借方金額(円)", "借方税額",
    "貸方勘定科目", "貸方補助科目", "貸方部門", "貸方取引先", "貸方税区分", "貸方インボイス",
    "貸方金額(円)", "貸方税額",
    "摘要", "仕訳メモ", "タグ", "MF仕訳タイプ", "決算整理仕訳",
    "作成日時", "作成者", "最終更新日時", "最終更新者",
]

# 預金・売掛金・仮受金 are outside the scope of consumption tax -> 対象外.
# 支払手数料 (bank transfer fee) is normally a taxable purchase; it is left
# blank so that MoneyForward applies the account's default tax category.
DEFAULT_TAX = "対象外"


def _tax(account: str, fee_account: str) -> str:
    if not account or account == fee_account:
        return ""
    return DEFAULT_TAX


def build_mf_rows(lines: list[JournalLine], fee_account: str = "支払手数料",
                  tag: str = "入金消込") -> list[list[str]]:
    rows = []
    for ln in lines:
        dr = ln.dr_account
        cr = ln.cr_account
        rows.append([
            str(ln.no), ln.date,
            dr, ln.dr_sub if dr else "", "", ln.partner if dr and dr != fee_account else "",
            _tax(dr, fee_account), "", "" if ln.dr_amount is None else str(ln.dr_amount), "0" if dr else "",
            cr, ln.cr_sub if cr else "", "", ln.partner if cr else "",
            _tax(cr, fee_account), "", "" if ln.cr_amount is None else str(ln.cr_amount), "0" if cr else "",
            ln.memo[:200], f"明細 {ln.bank_ref}"[:200], tag, "", "",
            "", "", "", "",
        ])
    return rows


def write_mf_csv(lines: list[JournalLine], path: str | Path, encoding: str = "sjis",
                 fee_account: str = "支払手数料") -> int:
    rows = build_mf_rows(lines, fee_account)
    enc = OUTPUT_ENCODINGS[encoding]
    for row in rows:  # validate before writing so we never leave half a file
        try:
            ",".join(row).encode(enc)
        except UnicodeEncodeError as e:
            raise ValueError(f"取引No {row[0]} に {encoding} で表せない文字「{e.object[e.start:e.end]}」が"
                             f"あります。--encoding utf8 を使ってください") from None
    with open(path, "w", encoding=enc, newline="") as f:
        w = csv.writer(f)
        w.writerow(MF_HEADER)
        w.writerows(rows)
    return len(rows)

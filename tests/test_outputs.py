import csv
from datetime import date
from pathlib import Path

from keshikomi.cli import main
from keshikomi.export_mf import MF_HEADER, build_mf_rows
from keshikomi.journal import build_journal
from keshikomi.matcher import Matcher
from keshikomi.readers import read_bank, read_customers, read_invoices

SAMPLE = Path(__file__).resolve().parent.parent / "sample"


def _run(bank="bank_zengin.txt"):
    invs = read_invoices(SAMPLE / "invoices.csv")
    res = Matcher(invs, read_customers(SAMPLE / "customers.csv")).run(read_bank(SAMPLE / bank))
    return invs, res


def test_journal_balances_per_entry():
    _, res = _run()
    lines = build_journal(res)
    totals = {}
    for ln in lines:
        totals[ln.no] = totals.get(ln.no, 0) + (ln.dr_amount or 0) - (ln.cr_amount or 0)
    assert totals and all(v == 0 for v in totals.values())
    fee = [ln for ln in lines if ln.dr_account == "支払手数料"]
    assert len(fee) == 1 and fee[0].dr_amount == 440
    assert any(ln.cr_account == "仮受金" and ln.cr_amount == 3000 for ln in lines)


def test_suspense_option_books_unmatched_deposits():
    _, res = _run()
    plain = build_journal(res)
    with_suspense = build_journal(res, suspense=True)
    extra = {ln.no for ln in with_suspense} - {ln.no for ln in plain}
    assert len(extra) == 2  # the ambiguous 55,000 and the unknown 12,345


def test_mf_rows_have_27_columns():
    _, res = _run()
    rows = build_mf_rows(build_journal(res))
    assert len(MF_HEADER) == 27
    assert all(len(r) == 27 for r in rows)
    assert rows[0][1] == "2026/10/30"
    fee_row = [r for r in rows if r[2] == "支払手数料"][0]
    assert fee_row[6] == ""  # tax category left to MoneyForward default


def test_generic_and_zengin_give_same_core_results():
    _, a = _run("bank_generic.csv")
    _, b = _run("bank_zengin.txt")
    rules_a = [r.rule for r in a]
    rules_b = [r.rule for r in b]
    # only difference: the payer code in the Zengin file identifies ミホン製作所 (R1 vs R7)
    assert [x for x, y in zip(rules_a, rules_b) if x != y] == ["R7"]


def test_cli_end_to_end(tmp_path, capsys):
    out = tmp_path / "out"
    rc = main(["match", "--bank", str(SAMPLE / "bank_zengin.txt"), "--invoices", str(SAMPLE / "invoices.csv"),
               "--customers", str(SAMPLE / "customers.csv"), "--out", str(out), "--bank-account", "サンプル銀行"])
    assert rc == 0
    for f in ["keshikomi_result.csv", "journal.csv", "mf_journal_import.csv", "open_invoices.csv", "summary.md"]:
        assert (out / f).exists(), f
    with open(out / "mf_journal_import.csv", encoding="cp932") as f:
        header = next(csv.reader(f))
    assert header == MF_HEADER
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "自動消込率: 80%" in summary
    with open(out / "open_invoices.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert {r["請求書番号"]: int(r["残額"]) for r in rows}["INV-2026-1009"] == 250000


def test_cli_reports_errors(tmp_path, capsys):
    rc = main(["match", "--bank", str(tmp_path / "missing.csv"), "--invoices", str(SAMPLE / "invoices.csv"),
               "--out", str(tmp_path)])
    assert rc == 1 and "エラー" in capsys.readouterr().err

from datetime import date

from keshikomi.matcher import MatchConfig, Matcher
from keshikomi.models import BankTransaction, Customer, DiffKind, Invoice, Status


def inv(no, cid, amount, due=date(2026, 10, 31), name=None):
    return Invoice(no, cid, name or f"株式会社{cid}", date(2026, 9, 30), due, amount)


def dep(amount, payer, d=date(2026, 10, 31), desc="", code="", n=[0]):
    n[0] += 1
    return BankTransaction(str(n[0]), d, "in", amount, payer, desc, code, f"t:{n[0]}")


CUSTS = [
    Customer("C1", "株式会社サンプル商事", ["ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ"]),
    Customer("C2", "合同会社テスト物産", ["ﾃｽﾄﾌﾞﾂｻﾝ(ﾄﾞ"], ["555"]),
]


def run(invoices, txns, **cfg):
    return Matcher(invoices, CUSTS, MatchConfig(**cfg)).run(txns)


def test_r1_exact():
    invs = [inv("A-1001", "C1", 110000), inv("A-1002", "C1", 50000)]
    [r] = run(invs, [dep(110000, "ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ")])
    assert (r.status, r.rule, r.diff) == (Status.MATCHED, "R1", 0)
    assert invs[0].open_amount == 0 and invs[1].open_amount == 50000


def test_r2_fee_shortfall():
    invs = [inv("A-1", "C2", 220000)]
    [r] = run(invs, [dep(219340, "ﾃｽﾄﾌﾞﾂｻﾝ(ﾄﾞ")])
    assert r.rule == "R2" and r.diff == -660 and r.diff_kind == DiffKind.FEE
    assert invs[0].open_amount == 0


def test_fee_tolerance_is_configurable():
    invs = [inv("A-1", "C2", 220000), inv("A-2", "C2", 10000)]
    [r] = run(invs, [dep(219340, "ﾃｽﾄﾌﾞﾂｻﾝ(ﾄﾞ")], fee_tolerance=500)
    assert r.status == Status.NEEDS_REVIEW


def test_r3_combined_payment():
    invs = [inv("A-1", "C1", 66000), inv("A-2", "C1", 33000), inv("A-3", "C1", 44000)]
    [r] = run(invs, [dep(99000, "ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ")])
    assert r.rule == "R3" and [i.invoice_no for i in r.invoices] == ["A-1", "A-2"]
    assert invs[2].open_amount == 44000


def test_r3_combined_payment_with_fee():
    invs = [inv("A-1", "C1", 66000), inv("A-2", "C1", 33000), inv("A-3", "C1", 44000)]
    [r] = run(invs, [dep(98560, "ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ")])
    assert r.rule == "R3" and r.diff == -440 and r.diff_kind == DiffKind.FEE


def test_r4_overpayment_and_cap():
    invs = [inv("A-1", "C1", 77000)]
    [r] = run(invs, [dep(80000, "ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ")])
    assert r.rule == "R4" and r.diff == 3000 and r.diff_kind == DiffKind.OVERPAY
    invs = [inv("A-1", "C1", 77000)]
    [r] = run(invs, [dep(80000, "ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ")], overpay_max=1000)
    assert r.status == Status.NEEDS_REVIEW and invs[0].open_amount == 77000


def test_r5_partial_then_balance():
    invs = [inv("A-1", "C1", 550000)]
    r1, r2 = run(invs, [dep(300000, "ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ", date(2026, 10, 31)),
                        dep(250000, "ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ", date(2026, 11, 5))])
    assert r1.status == Status.PARTIAL and r1.cleared == {"A-1": 300000}
    assert r2.status == Status.MATCHED and r2.rule == "R1" and invs[0].open_amount == 0


def test_r6_ambiguous_is_not_guessed():
    invs = [inv("A-1", "C1", 55000), inv("A-2", "C1", 55000)]
    [r] = run(invs, [dep(55000, "ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ")])
    assert r.status == Status.NEEDS_REVIEW and len(r.candidates) == 2
    assert all(i.open_amount == 55000 for i in invs)


def test_r0_invoice_reference_resolves_ambiguity():
    invs = [inv("INV-2026-1002", "C1", 55000), inv("INV-2026-1003", "C1", 55000)]
    [r] = run(invs, [dep(55000, "ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ", desc="EDI 20261003")])
    assert r.rule == "R0" and r.invoices[0].invoice_no == "INV-2026-1003"


def test_payer_code_identifies_customer():
    invs = [inv("A-1", "C2", 12000), inv("A-2", "C1", 12000)]
    [r] = run(invs, [dep(12000, "ﾍﾞﾂﾒｲｷﾞ", code="555")])
    assert r.rule == "R1" and r.customer_id == "C2"


def test_r7_unknown_payer_unique_amount_needs_review_by_default():
    invs = [inv("A-1", "C1", 132000), inv("A-2", "C2", 10000)]
    [r] = run(invs, [dep(132000, "振込 ｶ)ｵﾔｶﾞｲｼﾔ")])
    assert (r.status, r.rule, r.customer_id) == (Status.NEEDS_REVIEW, "R7", "C1")
    assert [i.invoice_no for i in r.candidates] == ["A-1"] and not r.invoices
    assert invs[0].open_amount == 132000                      # nothing cleared
    assert "「ｶ)ｵﾔｶﾞｲｼﾔ」を追加" in r.reason                    # suggestion without the bank's 振込 prefix


def test_r7_opt_in_clears_with_medium_confidence():
    invs = [inv("A-1", "C1", 132000), inv("A-2", "C2", 10000)]
    [r] = Matcher(invs, [], MatchConfig(accept_unique_amount=True)).run([dep(132000, "ｶ)ｵﾔｶﾞｲｼﾔ")])
    assert (r.status, r.rule, r.confidence, r.customer_id) == (Status.MATCHED, "R7", "medium", "C1")
    assert "要確認" not in r.reason and invs[0].open_amount == 0


def test_r8_r9_unknown_payer():
    invs = [inv("A-1", "C1", 5000), inv("A-2", "C2", 5000)]
    r8, r9 = run(invs, [dep(5000, "ﾌﾒｲ"), dep(12345, "ｽｽﾞｷ ｲﾁﾛｳ")])
    assert r8.status == Status.NEEDS_REVIEW and r8.rule == "R8"
    assert r9.status == Status.UNMATCHED and r9.rule == "R9"


def test_known_customer_without_open_invoice():
    invs = [inv("A-1", "C1", 5000)]
    invs[0].paid = 5000
    [r] = run(invs, [dep(5000, "ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ")])
    assert r.status == Status.UNMATCHED and "未入金の請求書がありません" in r.reason


def test_withdrawals_are_skipped():
    t = BankTransaction("x", date(2026, 10, 31), "out", 440, "", "手数料")
    [r] = run([inv("A-1", "C1", 440)], [t])
    assert r.status == Status.SKIPPED


def test_kana_from_invoice_file_is_used():
    i = inv("A-1", "C9", 7000, name="株式会社ホゲ")
    i.customer_kana = "ｶ)ﾎｹﾞ"
    [r] = Matcher([i]).run([dep(7000, "ﾎｹﾞ(ｶ")])
    assert r.rule == "R1" and r.customer_id == "C9"

"""Matching engine (入金消込ロジック).

Each deposit is processed in value-date order and the matched invoices are
updated immediately, so an invoice is never cleared twice and a partial
payment's remaining balance can be cleared by a later deposit.

Rules, in priority order (rule ids appear in the output):

R0  Invoice reference  - the payer name / memo / EDI field contains the
                         invoice number -> that invoice is evaluated alone
                         (exact, fee shortfall, overpayment, partial).
Payer identified (取引先マスタ / 振込名義 / 振込依頼人コード):
R1  exact amount       - exactly one open invoice of that customer equals the deposit.
R2  fee shortfall      - exactly one open invoice is short by <= fee tolerance
                         (振込手数料を差し引いて入金) -> difference to 支払手数料.
R3  combined payment   - the deposit equals the sum of 2..N open invoices of the
                         customer (まとめ入金); fee tolerance also applies.
R4  overpayment        - customer has one open invoice and paid more -> 仮受金.
R5  partial payment    - customer has one open invoice and paid less (beyond the
                         fee tolerance) -> partial clear, balance stays open.
R6  ambiguous          - several candidates -> needs_review (never guessed).
Payer unknown:
R7  unique amount      - exactly one open invoice in the whole ledger has the
                         same amount -> matched with confidence "medium".
R8  ambiguous amount   - several invoices with that amount -> needs_review.
R9  no match           - unmatched, listed for manual handling.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from .models import BankTransaction, Customer, DiffKind, Invoice, MatchResult, Status
from .normalize import digits_in, names_match, normalize_name


@dataclass
class MatchConfig:
    fee_tolerance: int = 880          # max 振込手数料 a payer may deduct (yen)
    overpay_max: int | None = None    # overpayment above this -> needs_review; None = no cap
    max_combo: int = 4                # まとめ入金: max invoices in one deposit
    combo_pool: int = 12              # only the oldest N open invoices are combined
    min_ref_digits: int = 6           # invoice number digits needed for R0


class Matcher:
    def __init__(self, invoices: list[Invoice], customers: list[Customer] | None = None,
                 config: MatchConfig | None = None):
        self.invoices = invoices
        self.cfg = config or MatchConfig()
        self.customers: dict[str, Customer] = {c.customer_id: c for c in (customers or [])}
        # customers that only appear in the invoice file
        for inv in invoices:
            c = self.customers.setdefault(inv.customer_id, Customer(inv.customer_id, inv.customer_name))
            if inv.customer_kana and inv.customer_kana not in c.kana_names:
                c.kana_names.append(inv.customer_kana)
        self._keys: list[tuple[str, str]] = []   # (normalized key, customer_id)
        for c in self.customers.values():
            for n in [c.name, *c.kana_names]:
                k = normalize_name(n)
                if k:
                    self._keys.append((k, c.customer_id))

    # ---- identification -------------------------------------------------
    def identify(self, txn: BankTransaction) -> tuple[str, str]:
        """Return (customer_id, how) or ("", reason)."""
        if txn.payer_code:
            hits = {c.customer_id for c in self.customers.values() if txn.payer_code in c.payer_codes}
            if len(hits) == 1:
                return hits.pop(), "振込依頼人コード一致"
        key = normalize_name(txn.payer_name or txn.description)
        hits = {cid for k, cid in self._keys if names_match(key, k)}
        if len(hits) == 1:
            return hits.pop(), "振込名義一致"
        if len(hits) > 1:
            return "", f"振込名義が複数の取引先に該当（{', '.join(sorted(hits))}）"
        return "", "振込名義が取引先マスタに未登録"

    def _open(self, customer_id: str | None = None) -> list[Invoice]:
        invs = [i for i in self.invoices if i.open_amount > 0
                and (customer_id is None or i.customer_id == customer_id)]
        return sorted(invs, key=lambda i: (i.due_date, i.invoice_no))

    def _referenced(self, txn: BankTransaction) -> Invoice | None:
        text = digits_in(f"{txn.payer_name} {txn.description}")
        hits = []
        for inv in self._open():
            d = digits_in(inv.invoice_no)
            if len(d) >= self.cfg.min_ref_digits and d in text:
                hits.append(inv)
        return hits[0] if len(hits) == 1 else None

    # ---- main loop ------------------------------------------------------
    def run(self, transactions: list[BankTransaction]) -> list[MatchResult]:
        results = []
        for txn in sorted(transactions, key=lambda t: t.value_date):
            results.append(self.match_one(txn))
        return results

    def match_one(self, txn: BankTransaction) -> MatchResult:
        if not txn.is_deposit:
            return MatchResult(txn, Status.SKIPPED, rule="-", reason="出金のため対象外")
        res = MatchResult(txn, Status.UNMATCHED)
        cid, how = self.identify(txn)
        if cid:
            res.customer_id, res.customer_name = cid, self.customers[cid].name

        ref = self._referenced(txn)
        if ref and (not cid or ref.customer_id == cid):
            res.customer_id, res.customer_name = ref.customer_id, ref.customer_name
            self._single(res, ref, "R0", f"請求書番号 {ref.invoice_no} の記載あり",
                         "high" if cid else "medium")
            return res

        if cid:
            self._known(res, self._open(cid), how)
        else:
            self._unknown(res, how)
        return res

    # ---- rule helpers -----------------------------------------------------
    def _single(self, res: MatchResult, inv: Invoice, rule: str, why: str, conf: str) -> None:
        amt, open_ = res.txn.amount, inv.open_amount
        short = open_ - amt
        if short == 0:
            self._settle(res, [inv], rule, f"{why}・金額一致", conf)
        elif 0 < short <= self.cfg.fee_tolerance:
            self._settle(res, [inv], rule, f"{why}・{short:,}円不足（振込手数料として処理）", conf)
        elif short < 0:
            over = -short
            if self.cfg.overpay_max is not None and over > self.cfg.overpay_max:
                res.status, res.rule, res.candidates = Status.NEEDS_REVIEW, rule, [inv]
                res.reason = f"{why}・過入金 {over:,}円 が上限を超えるため要確認"
                return
            self._settle(res, [inv], rule, f"{why}・過入金 {over:,}円（仮受金）", conf)
        else:
            res.status, res.rule, res.confidence = Status.PARTIAL, rule, conf
            res.invoices = [inv]
            res.cleared[inv.invoice_no] = amt
            inv.paid += amt
            res.diff_kind = DiffKind.PARTIAL
            res.reason = f"{why}・一部入金、残額 {inv.open_amount:,}円 は売掛金に残す"

    def _fits(self, amount: int, target: int) -> bool:
        return 0 <= target - amount <= self.cfg.fee_tolerance

    def _known(self, res: MatchResult, own: list[Invoice], how: str) -> None:
        amt = res.txn.amount
        if not own:
            res.rule, res.reason = "R9", f"{how}。ただし未入金の請求書がありません（前受・二重入金の可能性）"
            return
        exact = [i for i in own if i.open_amount == amt]
        if len(exact) == 1:
            self._settle(res, exact, "R1", f"{how}・金額一致", "high")
            return
        if len(exact) > 1:
            self._review(res, exact, "R6", f"{how}・同額の請求書が {len(exact)} 件あり特定不可")
            return
        fee = [i for i in own if 0 < i.open_amount - amt <= self.cfg.fee_tolerance]
        if len(fee) == 1:
            short = fee[0].open_amount - amt
            self._settle(res, fee, "R2", f"{how}・{short:,}円不足（振込手数料として処理）", "high")
            return
        if len(fee) > 1:
            self._review(res, fee, "R6", f"{how}・手数料差額の範囲に請求書が {len(fee)} 件あり特定不可")
            return
        combo = self._combo(amt, own)
        if combo:
            nos = "・".join(i.invoice_no for i in combo)
            self._settle(res, combo, "R3", f"{how}・{len(combo)} 件の合計と一致（まとめ入金: {nos}）", "high")
            return
        if len(own) == 1:
            self._single(res, own[0], "R4" if amt > own[0].open_amount else "R5", how, "high")
            return
        self._review(res, own, "R6", f"{how}・未入金 {len(own)} 件のいずれとも金額が合わない")

    def _unknown(self, res: MatchResult, how: str) -> None:
        amt = res.txn.amount
        exact = [i for i in self._open() if i.open_amount == amt]
        if len(exact) == 1:
            inv = exact[0]
            res.customer_id, res.customer_name = inv.customer_id, inv.customer_name
            self._settle(res, exact, "R7", f"{how}・金額が未入金請求書の中で一意（要確認）", "medium")
            return
        if len(exact) > 1:
            self._review(res, exact, "R8", f"{how}・同額の請求書が {len(exact)} 件")
            return
        res.rule, res.reason = "R9", f"{how}・金額の一致する請求書なし"

    def _combo(self, amount: int, invs: list[Invoice]) -> list[Invoice] | None:
        pool = invs[: self.cfg.combo_pool]
        best = None
        for k in range(2, min(self.cfg.max_combo, len(pool)) + 1):
            for combo in combinations(pool, k):
                total = sum(i.open_amount for i in combo)
                if total == amount:
                    return list(combo)          # exact sum wins immediately
                if best is None and self._fits(amount, total):
                    best = list(combo)
            if best:
                return best
        return None

    def _review(self, res: MatchResult, cands: list[Invoice], rule: str, why: str) -> None:
        res.status, res.rule, res.reason, res.candidates = Status.NEEDS_REVIEW, rule, why, cands

    def _settle(self, res: MatchResult, invs: list[Invoice], rule: str, why: str, conf: str) -> None:
        res.status, res.rule, res.reason, res.confidence = Status.MATCHED, rule, why, conf
        res.invoices = invs
        res.diff = res.txn.amount - sum(i.open_amount for i in invs)
        if res.diff < 0:
            res.diff_kind = DiffKind.FEE
        elif res.diff > 0:
            res.diff_kind = DiffKind.OVERPAY
        for i in invs:
            res.cleared[i.invoice_no] = i.open_amount
            i.paid += i.open_amount
        if not res.customer_id and invs:
            res.customer_id, res.customer_name = invs[0].customer_id, invs[0].customer_name


def match(transactions: list[BankTransaction], invoices: list[Invoice],
          customers: list[Customer] | None = None, config: MatchConfig | None = None) -> list[MatchResult]:
    return Matcher(invoices, customers, config).run(transactions)

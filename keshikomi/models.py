"""Core data structures. All amounts are integer yen."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


@dataclass(frozen=True)
class BankTransaction:
    """One line of a bank statement (入出金明細)."""

    row_id: str               # 照会番号 or a generated sequence number
    value_date: date          # 勘定日
    direction: str            # "in" (入金) or "out" (出金)
    amount: int               # always positive
    payer_name: str = ""      # 振込依頼人名 (as printed by the bank, usually half-width kana)
    description: str = ""     # 摘要 / EDI情報 / memo
    payer_code: str = ""      # 振込依頼人コード (if any)
    source: str = ""          # file name + line, for audit trail

    @property
    def is_deposit(self) -> bool:
        return self.direction == "in"


@dataclass
class Invoice:
    """A receivable (売掛金) issued to a customer."""

    invoice_no: str
    customer_id: str
    customer_name: str
    issue_date: date
    due_date: date
    amount: int                    # 税込請求額
    customer_kana: str = ""        # 振込名義 (optional)
    paid: int = 0                  # amount already cleared

    @property
    def open_amount(self) -> int:
        return self.amount - self.paid


@dataclass
class Customer:
    customer_id: str
    name: str
    kana_names: list[str] = field(default_factory=list)   # registered 振込名義 / aliases
    payer_codes: list[str] = field(default_factory=list)  # 振込依頼人コード


class Status(str, Enum):
    MATCHED = "matched"            # cleared automatically
    PARTIAL = "partial"            # partial payment; remaining balance stays open
    NEEDS_REVIEW = "needs_review"  # a rule fired but a human should confirm
    UNMATCHED = "unmatched"        # no safe match; candidates may be listed
    SKIPPED = "skipped"            # withdrawal (出金) etc.; not a target of 消込


class DiffKind(str, Enum):
    NONE = ""
    FEE = "fee"            # 振込手数料 deducted by the payer -> 支払手数料
    OVERPAY = "overpay"    # 過入金 -> 仮受金
    PARTIAL = "partial"    # 一部入金; no diff entry, balance remains in 売掛金


@dataclass
class MatchResult:
    txn: BankTransaction
    status: Status
    customer_id: str = ""
    customer_name: str = ""
    invoices: list[Invoice] = field(default_factory=list)
    candidates: list[Invoice] = field(default_factory=list)
    cleared: dict[str, int] = field(default_factory=dict)   # invoice_no -> amount cleared now
    diff: int = 0                    # received - total open amount of matched invoices
    diff_kind: DiffKind = DiffKind.NONE
    rule: str = ""                   # short rule id, e.g. "R1-exact"
    reason: str = ""                 # human readable explanation (Japanese)
    confidence: str = ""             # "high" / "medium" / ""

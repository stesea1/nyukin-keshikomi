"""Input readers: bank statements (generic CSV / Zengin format) and invoices."""
from __future__ import annotations

from pathlib import Path

from ..models import BankTransaction
from .generic_csv import ColumnMapping, read_generic_csv
from .invoices import read_customers, read_invoices
from .zengin import looks_like_zengin, read_zengin

__all__ = [
    "ColumnMapping", "read_generic_csv", "read_zengin", "read_invoices",
    "read_customers", "read_bank", "looks_like_zengin",
]


def read_bank(path: str | Path, fmt: str = "auto", encoding: str = "auto",
              mapping: ColumnMapping | None = None, era: str = "auto") -> list[BankTransaction]:
    """Read a bank statement. ``fmt`` is ``auto`` / ``generic`` / ``zengin``."""
    if fmt == "auto":
        fmt = "zengin" if looks_like_zengin(Path(path).read_bytes()) else "generic"
    if fmt == "zengin":
        return read_zengin(path, encoding=encoding, era=era)
    if fmt == "generic":
        return read_generic_csv(path, mapping=mapping, encoding=encoding)
    raise ValueError(f"unknown bank format: {fmt}")

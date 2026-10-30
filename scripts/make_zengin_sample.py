"""Generate sample/bank_zengin.txt (全銀協 入出金取引明細, 200-byte fixed length, Shift_JIS).

All names and amounts are fictional.  Run:  python scripts/make_zengin_sample.py
"""
from __future__ import annotations

from pathlib import Path


def n(v, width: int) -> bytes:
    return str(v).rjust(width, "0").encode("ascii")


def c(s: str, width: int) -> bytes:
    b = s.encode("cp932")
    if len(b) > width:
        raise ValueError(f"too long: {s}")
    return b + b" " * (width - len(b))


def header(created: str, frm: str, to: str) -> bytes:
    rec = (b"1" + b"03" + b"0" + created.encode() + frm.encode() + to.encode()
           + n(9999, 4) + c("ｻﾝﾌﾟﾙｷﾞﾝｺｳ", 15) + n(123, 3) + c("ﾎﾝﾃﾝ", 15) + b"000"
           + b"1" + n(1234567, 10) + c("ｶ)ﾎﾟｰﾄﾌｵﾘｵ", 40) + b"1" + b"1" + n(1000000, 14) + b" " * 71)
    assert len(rec) == 200, len(rec)
    return rec


def data(ref: int, d: str, io: str, kind: str, amount: int, payer: str = "", code: str = "",
         summary: str = "", edi: str = "") -> bytes:
    rec = (b"2" + n(ref, 8) + d.encode() + d.encode() + io.encode() + kind.encode()
           + n(amount, 12) + n(0, 12) + b" " * 6 + b" " * 6 + b" " + b" " * 7 + b"   "
           + (n(code, 10) if code else b" " * 10) + c(payer, 48)
           + c("ﾃｽﾄｷﾞﾝｺｳ" if io == "1" else "", 15) + c("ﾎﾝﾃﾝ" if io == "1" else "", 15)
           + c(summary, 20) + c(edi, 20) + b" ")
    assert len(rec) == 200, (len(rec), payer)
    return rec


# 令和8年 = 2026 -> YY = "08"
ROWS = [
    (1, "081030", "1", "11", 110000, "ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ", "", "", ""),
    (2, "081030", "1", "11", 219560, "ﾃｽﾄﾌﾞﾂｻﾝ(ﾄﾞ", "", "", ""),
    (3, "081030", "1", "11", 99000, "ﾀﾞﾐｰｺｳｷﾞﾖｳ(ｶ", "", "", ""),
    (4, "081030", "2", "11", 33000, "", "", "ﾌﾘｺﾐ", ""),
    (5, "081030", "2", "18", 440, "", "", "ﾃｽｳﾘﾖｳ", ""),
    (6, "081031", "1", "11", 80000, "ﾕ)ﾓﾃﾞﾙｳﾝﾕ", "", "", ""),
    (7, "081031", "1", "11", 300000, "ｶ)ﾚｲﾃﾞﾝｷ", "", "", ""),
    (8, "081031", "1", "11", 132000, "ｶ)ｴｸﾞｻﾞﾝﾌﾟﾙHD", "", "", ""),
    (9, "081031", "1", "11", 55000, "ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ", "", "", ""),
    (10, "081031", "1", "11", 55000, "ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ", "", "", "INV-2026-1003"),
    (11, "081031", "1", "11", 330000, "ﾐﾎﾝ(ｶ ｹｲﾘﾌﾞ", "1234567890", "", ""),
    (12, "081031", "1", "11", 12345, "ｽｽﾞｷ ｲﾁﾛｳ", "", "", ""),
]


def build() -> bytes:
    recs = [header("081031", "081030", "081031")]
    recs += [data(*r) for r in ROWS]
    ins = [r for r in ROWS if r[2] == "1"]
    outs = [r for r in ROWS if r[2] == "2"]
    balance = 1000000 + sum(r[4] for r in ins) - sum(r[4] for r in outs)
    trailer = (b"8" + n(len(ins), 6) + n(sum(r[4] for r in ins), 13) + n(len(outs), 6)
               + n(sum(r[4] for r in outs), 13) + b"1" + n(balance, 14) + n(len(ROWS), 7) + b" " * 139)
    end = b"9" + n(len(ROWS) + 3, 10) + n(1, 5) + b" " * 184
    assert len(trailer) == 200 and len(end) == 200
    recs += [trailer, end]
    return b"\r\n".join(recs) + b"\r\n"


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "sample" / "bank_zengin.txt"
    out.write_bytes(build())
    print(f"wrote {out}")

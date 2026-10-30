"""全銀協規定形式「入出金取引明細」(種別コード 03) reader.

Record layout (200 bytes per record,普通・当座・貯蓄預金), taken from the
public format sheets that Japanese banks publish for their corporate
net-banking services.  Positions are 1-based byte offsets.

Header record (データ区分 = 1)
    1     データ区分 N(1)       "1"
    2-3   種別コード N(2)       "03"
    4     コード区分 N(1)       0 = JIS (SJIS half-width kana), 1 = EBCDIC (not supported)
    5-10  作成日 N(6)           YYMMDD (和暦)
    11-16 勘定日(自) N(6)
    17-22 勘定日(至) N(6)
    23-26 銀行コード N(4)
    27-41 銀行名 C(15)
    42-44 支店コード N(3)
    45-59 支店名 C(15)
    60-62 ダミー N(3)
    63    預金種目 N(1)         1 普通 / 2 当座 / 4 貯蓄
    64-73 口座番号 N(10)
    74-113 口座名 C(40)
    114   貸越区分, 115 通帳・証書区分, 116-129 取引前残高 N(14), 130-200 ダミー

Data record (データ区分 = 2)
    1      データ区分 N(1)      "2"
    2-9    照会番号 N(8)
    10-15  勘定日 N(6)          YYMMDD (和暦)
    16-21  預入・払出日 N(6)
    22     入払区分 N(1)        1 = 入金, 2 = 出金
    23-24  取引区分 N(2)        10 現金 / 11 振込 / 12 他店券入金 / 13 交換 / 14 振替 / 18 その他 / 19 訂正
    25-36  取引金額 N(12)
    37-48  うち他店券金額 N(12)
    49-54  交換呈示日, 55-60 不渡返還日, 61 手形・小切手区分, 62-68 手形・小切手番号
    69-71  僚店番号 N(3)
    72-81  振込依頼人コード N(10)
    82-129 振込依頼人名または契約者番号 C(48)
    130-144 仕向銀行名 C(15)
    145-159 仕向店名 C(15)
    160-179 摘要内容 C(20)
    180-199 EDI情報 C(20)
    200    ダミー

Trailer (データ区分 = 8) and end (データ区分 = 9) records are read only for a
count check.

Assumptions (see README):
* Text is Shift_JIS (cp932); half-width katakana are 1 byte each, so byte
  offsets are used, not character offsets.
* Records may be separated by CR/LF or concatenated without line breaks.
* Dates are 和暦 YYMMDD (令和).  Some banks emit 西暦 YYMMDD instead; ``era="auto"``
  treats YY as 令和 when it is a plausible 令和 year (<= current 令和 year + 1)
  and as 西暦 20YY otherwise.  Use ``era="reiwa"`` / ``era="western"`` to force.
* A CSV variant (same fields, comma separated, one record per line) is also
  accepted; field order is the same as the fixed-length layout.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from ..models import BankTransaction
from ..textio import decode_bytes

RECORD_LEN = 200

# (name, start, length) with 1-based start, for the data record
DATA_FIELDS = [
    ("kind", 1, 1), ("ref_no", 2, 8), ("value_date", 10, 6), ("start_date", 16, 6),
    ("direction", 22, 1), ("txn_type", 23, 2), ("amount", 25, 12), ("other_bank_amount", 37, 12),
    ("presented", 49, 6), ("dishonored", 55, 6), ("bill_type", 61, 1), ("bill_no", 62, 7),
    ("branch", 69, 3), ("payer_code", 72, 10), ("payer_name", 82, 48),
    ("from_bank", 130, 15), ("from_branch", 145, 15), ("summary", 160, 20), ("edi", 180, 20),
]
HEADER_FIELDS = [
    ("kind", 1, 1), ("type_code", 2, 2), ("code_kind", 4, 1), ("created", 5, 6),
    ("from_date", 11, 6), ("to_date", 17, 6), ("bank_code", 23, 4), ("bank_name", 27, 15),
    ("branch_code", 42, 3), ("branch_name", 45, 15), ("dummy", 60, 3), ("account_type", 63, 1),
    ("account_no", 64, 10), ("account_name", 74, 40),
]
TRAILER_FIELDS = [
    ("kind", 1, 1), ("in_count", 2, 6), ("in_total", 8, 13), ("out_count", 21, 6), ("out_total", 27, 13),
]

TXN_TYPES = {"10": "現金", "11": "振込", "12": "他店券入金", "13": "交換", "14": "振替",
             "18": "その他", "19": "訂正"}


def _split_fixed(rec: bytes, fields) -> dict[str, str]:
    return {name: rec[s - 1:s - 1 + n].decode("cp932", errors="replace").strip()
            for name, s, n in fields}


def to_date(yymmdd: str, era: str = "auto", today: date | None = None) -> date:
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    today = today or date.today()
    reiwa_now = today.year - 2018
    if era == "reiwa" or (era == "auto" and 1 <= yy <= reiwa_now + 1):
        return date(2018 + yy, mm, dd)
    return date(2000 + yy, mm, dd)


def looks_like_zengin(data: bytes) -> bool:
    head = data.lstrip(b"\xef\xbb\xbf")[:4]
    if head.startswith(b"103"):            # fixed length header "1" + "03"
        return True
    return head.replace(b'"', b"").startswith(b"1,03")   # CSV variant


def _records(data: bytes) -> list[bytes]:
    data = data.lstrip(b"\xef\xbb\xbf")
    if b"\n" in data or b"\r" in data:
        recs = [r for r in data.replace(b"\r\n", b"\n").replace(b"\r", b"\n").split(b"\n") if r.strip()]
    else:
        recs = [data[i:i + RECORD_LEN] for i in range(0, len(data), RECORD_LEN)]
    return [r.rstrip(b"\x1a") for r in recs if r.rstrip(b"\x1a")]


def _csv_to_fixed_dict(rec: bytes, fields) -> dict[str, str]:
    import csv
    import io
    text = decode_bytes(rec)
    values = next(csv.reader(io.StringIO(text)))
    return {name: (values[i].strip() if i < len(values) else "") for i, (name, _, _) in enumerate(fields)}


def read_zengin(path: str | Path, encoding: str = "auto", era: str = "auto",
                today: date | None = None) -> list[BankTransaction]:
    data = Path(path).read_bytes()
    is_csv = data.lstrip(b"\xef\xbb\xbf")[:4].replace(b'"', b"").startswith(b"1,03")
    name = Path(path).name
    out: list[BankTransaction] = []
    trailer: dict[str, str] | None = None
    for n, rec in enumerate(_records(data), start=1):
        kind = rec[:1].decode("ascii", errors="replace")
        if kind == "1":
            h = _csv_to_fixed_dict(rec, HEADER_FIELDS) if is_csv else _split_fixed(rec, HEADER_FIELDS)
            if h["type_code"] != "03":
                raise ValueError(f"{name}: 種別コード {h['type_code']} は入出金取引明細(03)ではありません")
            if h["code_kind"] == "1":
                raise ValueError(f"{name}: EBCDIC (コード区分=1) には対応していません")
        elif kind == "2":
            if not is_csv and len(rec) != RECORD_LEN:
                raise ValueError(f"{name}: レコード {n} の長さが {len(rec)} バイトです（200 バイト固定）")
            r = _csv_to_fixed_dict(rec, DATA_FIELDS) if is_csv else _split_fixed(rec, DATA_FIELDS)
            desc = " ".join(x for x in (TXN_TYPES.get(r["txn_type"], ""), r["summary"], r["edi"]) if x)
            out.append(BankTransaction(
                row_id=r["ref_no"].lstrip("0") or str(n),
                value_date=to_date(r["value_date"], era, today),
                direction="in" if r["direction"] == "1" else "out",
                amount=int(r["amount"] or 0),
                payer_name=r["payer_name"] if r["direction"] == "1" else "",
                description=desc,
                payer_code=r["payer_code"].lstrip("0"),
                source=f"{name}:{n}",
            ))
        elif kind == "8":
            trailer = _csv_to_fixed_dict(rec, TRAILER_FIELDS) if is_csv else _split_fixed(rec, TRAILER_FIELDS)
    if trailer and trailer.get("in_count", "").isdigit():
        ins = [t for t in out if t.is_deposit]
        if int(trailer["in_count"]) != len(ins) or int(trailer["in_total"] or 0) != sum(t.amount for t in ins):
            raise ValueError(f"{name}: トレーラ・レコードの入金件数/合計とデータ・レコードが一致しません")
    return out

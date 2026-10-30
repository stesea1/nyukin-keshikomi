from datetime import date
from pathlib import Path

import pytest

import make_zengin_sample as mz
from keshikomi.readers import ColumnMapping, read_bank, read_customers, read_generic_csv, read_invoices, read_zengin
from keshikomi.readers.zengin import looks_like_zengin, to_date
from keshikomi.textio import parse_amount, parse_date

SAMPLE = Path(__file__).resolve().parent.parent / "sample"


def test_parse_helpers():
    assert parse_amount("¥1,234") == 1234
    assert parse_amount("△500") == -500
    assert parse_amount("") == 0
    assert parse_date("2026年10月31日") == date(2026, 10, 31)
    assert parse_date("R8.10.31") == date(2026, 10, 31)
    assert parse_date("令和8年10月31日") == date(2026, 10, 31)
    assert parse_date("20261031") == date(2026, 10, 31)


def test_generic_utf8_sample():
    txns = read_generic_csv(SAMPLE / "bank_generic.csv")
    assert len(txns) == 12
    assert sum(t.is_deposit for t in txns) == 10
    assert txns[0].payer_name == "振込 ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ" and txns[0].amount == 110000


def test_generic_shift_jis_autodetect(tmp_path):
    p = tmp_path / "sjis.csv"
    p.write_bytes((SAMPLE / "bank_generic.csv").read_text(encoding="utf-8").encode("cp932"))
    assert read_bank(p)[1].payer_name == "振込 ﾃｽﾄﾌﾞﾂｻﾝ(ﾄﾞ"


def test_generic_signed_amount_and_mapping(tmp_path):
    p = tmp_path / "b.csv"
    p.write_text("口座番号 1234567\n\nDate,Amt,Who,Note\n2026/11/02,\"5,500\",ｶ)ﾃｽﾄ,x\n"
                 "2026/11/02,-300,ﾃｽｳﾘﾖｳ,\n合計,5200,,\n", encoding="utf-8")
    m = ColumnMapping(columns={"date": "Date", "amount": "Amt", "payer": "Who", "description": "Note"},
                      skip_rows=2)
    txns = read_generic_csv(p, m)
    assert [(t.direction, t.amount) for t in txns] == [("in", 5500), ("out", 300)]


def test_generic_mapping_file(tmp_path):
    m = ColumnMapping.from_json(SAMPLE / "mapping_example.json")
    assert m.columns["deposit"] == "お預入れ"
    assert len(read_generic_csv(SAMPLE / "bank_generic.csv", m)) == 12


def test_generic_missing_columns(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("foo,bar\n1,2\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_generic_csv(p)


def test_zengin_fixed_sample():
    data = (SAMPLE / "bank_zengin.txt").read_bytes()
    assert looks_like_zengin(data)
    assert all(len(r) == 200 for r in data.split(b"\r\n") if r)
    txns = read_zengin(SAMPLE / "bank_zengin.txt", today=date(2026, 10, 31))
    assert len(txns) == 12
    first = txns[0]
    assert first.value_date == date(2026, 10, 31).replace(day=30)
    assert first.payer_name == "ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ" and first.amount == 110000 and first.direction == "in"
    mihon = [t for t in txns if t.amount == 330000][0]
    assert mihon.payer_code == "1234567890"
    assert "INV-2026-1003" in txns[9].description


def test_zengin_without_line_breaks(tmp_path):
    p = tmp_path / "z.dat"
    p.write_bytes(mz.build().replace(b"\r\n", b""))
    assert len(read_bank(p)) == 12


def test_zengin_csv_variant(tmp_path):
    p = tmp_path / "z.csv"
    lines = ["1,03,0,081031,081030,081031,9999,ｻﾝﾌﾟﾙｷﾞﾝｺｳ,123,ﾎﾝﾃﾝ,000,1,0001234567,ｶ)ﾎﾟｰﾄﾌｵﾘｵ",
             "2,00000001,081030,081030,1,11,000000110000,000000000000,,,,,,,ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ,ﾃｽﾄｷﾞﾝｺｳ,ﾎﾝﾃﾝ,,",
             "8,000001,0000000110000,000000,0000000000000,1,00000001110000,0000001",
             "9,0000000004,00001"]
    p.write_bytes("\r\n".join(lines).encode("cp932"))
    txns = read_bank(p)
    assert len(txns) == 1 and txns[0].amount == 110000 and txns[0].payer_name == "ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ"


def test_zengin_trailer_mismatch(tmp_path):
    data = mz.build().replace(b"8000010", b"8000011", 1)
    p = tmp_path / "bad.txt"
    p.write_bytes(data)
    with pytest.raises(ValueError, match="トレーラ"):
        read_zengin(p)


def test_zengin_era():
    today = date(2026, 10, 31)
    assert to_date("081031", "auto", today) == date(2026, 10, 31)   # 令和8年
    assert to_date("261031", "auto", today) == date(2026, 10, 31)   # 西暦 26
    assert to_date("081031", "western", today) == date(2008, 10, 31)


def test_invoices_and_customers():
    invs = read_invoices(SAMPLE / "invoices.csv")
    assert len(invs) == 12 and invs[0].amount == 110000
    custs = read_customers(SAMPLE / "customers.csv")
    assert {c.customer_id for c in custs} >= {"C001", "C007"}
    assert [c for c in custs if c.customer_id == "C007"][0].payer_codes == ["1234567890"]


def test_duplicate_invoice_rejected(tmp_path):
    p = tmp_path / "i.csv"
    p.write_text("請求書番号,取引先コード,取引先名,支払期日,請求金額\nA-1,C1,X,2026/10/31,100\n"
                 "A-1,C1,X,2026/10/31,100\n", encoding="utf-8")
    with pytest.raises(ValueError, match="重複"):
        read_invoices(p)

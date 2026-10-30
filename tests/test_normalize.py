import pytest

from keshikomi.normalize import names_match, normalize_name


@pytest.mark.parametrize("a,b", [
    ("ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ", "カブシキガイシャサンプルショウジ"),
    ("ｻﾝﾌﾟﾙｼﾖｳｼﾞ(ｶ", "株式会社サンプルショウジ"),
    ("(ｶ)ｻﾝﾌﾟﾙ ｼﾖｳｼﾞ", "サンプル　ショウジ"),
    ("振込 ﾃｽﾄﾌﾞﾂｻﾝ(ﾄﾞ", "合同会社テストブッサン"),
    ("ﾕ)ﾓﾃﾞﾙｳﾝﾕ", "ﾓﾃﾞﾙｳﾝﾕ ﾕｳｹﾞﾝｶﾞｲｼﾔ"),
    ("ﾀﾞﾐｰｺｳｷﾞﾖｳ", "ダミ-コウギョウ"),
])
def test_same_key(a, b):
    assert normalize_name(a) == normalize_name(b)


def test_small_kana_and_width():
    assert normalize_name("ｼﾖｳｼﾞ") == normalize_name("ショウジ") == "シヨウジ"


def test_prefix_match_for_truncated_names():
    assert names_match(normalize_name("ｶ)ｴｸﾞｻﾞﾝﾌﾟﾙｼﾖｸﾋﾝ"), normalize_name("エグザンプルショクヒンホンシャ"))
    assert not names_match(normalize_name("ｶ)ｴｸﾞｻﾞﾝﾌﾟﾙHD"), normalize_name("エグザンプルショクヒン"))
    assert not names_match("サン", "サンプルシヨウジ")  # too short for a prefix match

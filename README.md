# nyukin-keshikomi — 入金消込ツール

銀行の入出金明細と請求書（売掛金）データを突き合わせて **入金消込** を自動化し、
消込結果・仕訳・マネーフォワード クラウド会計の仕訳帳インポート CSV を出力する Python 製 CLI ツールです。

中小企業の経理で毎月発生する「通帳を見ながら請求書に消し込む」作業を、
**判断の根拠つきで機械的に処理し、迷うものだけ人に回す** ことを目的にしています。

- 依存ライブラリなし（Python 3.9 以上の標準ライブラリのみ。テストに pytest）
- 汎用ネットバンキング CSV（列マッピング設定可、Shift_JIS / UTF-8 自動判定）
- 全銀協フォーマット「入出金取引明細」（固定長 200 バイト / CSV 版）
- 振込名義の正規化（半角/全角、`ｶ)` / `(ｶ` / `カブシキガイシャ` 等の法人略語、空白、小書き文字）
- 完全一致・振込手数料差引・過入金・一部入金・まとめ入金（複数請求書）に対応
- 自動で決められないものは「要確認」「未消込」として理由と候補を出力

> サンプルデータに出てくる会社名・金額・口座はすべて架空のものです。

---

## ブラウザ版（インストール不要）

**https://stesea1.github.io/nyukin-keshikomi/**

コマンドラインに慣れていない経理担当者向けに、同じ処理をブラウザで使えるようにしたページです。
明細・請求書・取引先マスタの CSV を選んで「消込を実行」を押すと、結果を表で確認でき、各ファイルをダウンロードできます。

- **ファイルは外部に送信されません。** この Python パッケージを [Pyodide](https://pyodide.org/)（WebAssembly 版 Python）で
  ブラウザ内で実行しています。ページの通信先は Content-Security-Policy でこのサイト自身と Pyodide の配信元だけに制限しています。
- 処理はコマンドライン版と同じコードです。出力ファイルがコマンドライン版とバイト単位で一致することを
  `scripts/web_selftest.mjs` で確認しています。
- 「サンプルデータで試す」で架空のデータを使って動きを確認できます。

---

## インストール

```bash
git clone https://github.com/stesea1/nyukin-keshikomi.git
cd nyukin-keshikomi
python -m keshikomi --help          # そのまま実行できます
# または
pip install -e ".[dev]"             # `keshikomi` コマンドと pytest が入ります
```

## 使い方

```bash
python -m keshikomi match \
  --bank sample/bank_generic.csv \
  --invoices sample/invoices.csv \
  --customers sample/customers.csv \
  --bank-account サンプル銀行 \
  --out out/
```

全銀フォーマットのファイルも自動判定されます。

```bash
python -m keshikomi match --bank sample/bank_zengin.txt \
  --invoices sample/invoices.csv --customers sample/customers.csv --out out/
```

主なオプション:

| オプション | 説明 | 既定値 |
|---|---|---|
| `--bank FILE [FILE ...]` | 入出金明細（複数ファイル可） | 必須 |
| `--bank-format` | `auto` / `generic` / `zengin` | `auto` |
| `--bank-encoding` | `auto` / `utf-8` / `cp932` | `auto` |
| `--mapping FILE` | 汎用 CSV の列マッピング JSON | 列名から自動推定 |
| `--zengin-era` | 全銀の年 2 桁の解釈 `auto` / `reiwa` / `western` | `auto` |
| `--invoices FILE` | 請求書 CSV | 必須 |
| `--customers FILE` | 取引先マスタ CSV（振込名義・振込依頼人コード） | なし |
| `--fee-tolerance YEN` | 振込手数料として許容する不足額 | `880` |
| `--overpay-max YEN` | これを超える過入金は要確認にする | 上限なし |
| `--max-combo N` | まとめ入金で組み合わせる請求書の最大件数 | `4` |
| `--bank-account NAME` | 普通預金の補助科目 | 空 |
| `--suspense` | 未消込・要確認の入金も仮受金で仕訳する | オフ |
| `--start-no N` | 伝票番号（取引No）の開始値 | `1` |
| `--mf-encoding` | MF 取込 CSV の文字コード `sjis` / `utf8` | `sjis` |
| `--as-of YYYY-MM-DD` | 期日経過日数の基準日 | 明細の最終日 |

### 出力ファイル（`--out` フォルダ）

| ファイル | 内容 |
|---|---|
| `keshikomi_result.csv` | 明細 1 行ごとの消込結果（ステータス・適用ルール・確度・消込請求書・差額・候補・理由） |
| `journal.csv` | 消込済み入金の仕訳（伝票番号・借方/貸方・摘要・請求書番号・明細参照） |
| `mf_journal_import.csv` | マネーフォワード クラウド会計「仕訳帳インポート」形式（27 列、既定は Shift_JIS） |
| `open_invoices.csv` | 消込後に残った未入金請求書と期日経過日数 |
| `summary.md` | 件数・金額・自動消込率、要確認一覧、未入金一覧のサマリー |

UTF-8 の CSV は Excel で文字化けしないよう BOM 付きで出力します。

### 入力ファイル

**請求書 CSV**（`sample/invoices.csv`）

```csv
請求書番号,取引先コード,取引先名,請求日,支払期日,請求金額,入金済額
INV-2026-1001,C001,株式会社サンプル商事,2026/09/30,2026/10/31,110000,0
```

必須は `請求書番号` `取引先名` `請求金額`。`入金済額` があれば残額だけを消込対象にします。
`振込名義`（カナ）列があれば取引先マスタなしでも名義照合に使います。英語の列名（`invoice_no`, `amount`, `due_date` など）も可。

**取引先マスタ CSV**（任意、`sample/customers.csv`）

```csv
取引先コード,取引先名,振込名義,振込依頼人コード
C001,株式会社サンプル商事,ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ,
C007,株式会社ミホン製作所,ﾐﾎﾝ(ｶ|ﾐﾎﾝｾｲｻｸｼﾖ,1234567890
```

1 社に複数の振込名義がある場合は `|` で区切ります（親会社・経理代行からの振込など）。

**汎用ネットバンキング CSV**

`日付` `お取引内容` `お預入れ` `お引出し` `摘要` `入金額` `金額` などのよくある列名を自動で認識します。
銀行ごとに列名が違う場合は JSON で指定します（`sample/mapping_example.json`）。

```json
{
  "date": "日付",
  "payer": "お取引内容",
  "withdrawal": "お引出し",
  "deposit": "お預入れ",
  "description": "メモ",
  "skip_rows": 0
}
```

- 入金・出金が別列の形式と、`amount`（符号付き）＋任意の `direction`（入金/出金）列の形式に対応
- `skip_rows` で口座情報などの前置き行を読み飛ばし
- 日付は `2026/10/31` `2026-10-31` `20261031` `2026年10月31日` `R8.10.31` `令和8年10月31日` を解釈
- 合計行など日付が読めない行はスキップ

## サンプル出力

`sample/bank_zengin.txt` を処理した `summary.md`（抜粋）:

```markdown
- 入金明細: 10 件 / 1,392,905円（出金 2 件は対象外）
- 自動消込率: 80%（8/10 件）

| ステータス | 件数 | 金額 |
|---|---:|---:|
| 消込済 | 7 | 1,025,560円 |
| 一部消込 | 1 | 300,000円 |
| 要確認 | 1 | 55,000円 |
| 未消込 | 1 | 12,345円 |

- 振込手数料として処理した差額: 440円
- 過入金（仮受金）: 3,000円

## 確認が必要な入金
| 勘定日 | 金額 | 振込依頼人名 | 状態 | 候補 | 理由 |
| 2026-10-31 | 55,000円 | ｶ)ｻﾝﾌﾟﾙｼﾖｳｼﾞ | 要確認 | INV-2026-1002 / INV-2026-1003 | 振込名義一致・同額の請求書が 2 件あり特定不可 |
| 2026-10-31 | 12,345円 | ｽｽﾞｷ ｲﾁﾛｳ | 未消込 |  | 振込名義が取引先マスタに未登録・金額の一致する請求書なし |
| 2026-10-31 | 132,000円 | ｶ)ｴｸﾞｻﾞﾝﾌﾟﾙHD | 確度 medium | INV-2026-1010 | 振込名義が取引先マスタに未登録・金額が未入金請求書の中で一意（要確認） |
```

`journal.csv`（振込手数料差引の例）:

```csv
伝票番号,行,取引日,借方勘定科目,借方補助科目,借方金額,貸方勘定科目,貸方補助科目,貸方金額,摘要,...
2,1,2026/10/30,普通預金,サンプル銀行,219560,,,,入金消込 ﾃｽﾄﾌﾞﾂｻﾝ(ﾄﾞ 請求書 INV-2026-1004,...
2,2,2026/10/30,,,,売掛金,,220000,入金消込 ﾃｽﾄﾌﾞﾂｻﾝ(ﾄﾞ 請求書 INV-2026-1004,...
2,3,2026/10/30,支払手数料,,440,,,,入金消込 ﾃｽﾄﾌﾞﾂｻﾝ(ﾄﾞ 請求書 INV-2026-1004,...
```

## 消込ロジック

入金 1 件ごとに、まず **取引先を特定** し、次に **その取引先の未入金請求書** と金額を照合します。
ルールは上から順に評価し、最初に当てはまったものを採用します。

**取引先の特定**

1. 全銀フォーマットの振込依頼人コードが取引先マスタに登録されていれば、それを最優先
2. 振込名義を正規化して、取引先マスタ／請求書の振込名義と比較（完全一致、または 4 文字以上の前方一致 ※銀行側で名義が切れる場合の対策）

**名義の正規化**: NFKC 変換（半角カナ→全角、全角英数→半角）→ 大文字化 → 小書き文字を大きい文字に（`ショウジ` と `ｼﾖｳｼﾞ` を同一視）→ 長音・ハイフン統一 →
`ｶ)` `(ｶ` `(ﾕ)` `ﾄﾞ)` などの略語と `株式会社` `カブシキガイシャ` `合同会社` `有限会社` などの法人格を除去 → 先頭の `振込` を除去 → 空白・記号を除去

| ルール | 条件 | 結果 |
|---|---|---|
| R0 | 摘要・EDI 情報に未入金請求書の番号（数字 6 桁以上）が含まれ、金額が一致（手数料差引含む） | 消込済 |
| R1 | 取引先特定済み、未入金請求書 1 件と金額が完全一致 | 消込済 |
| R2 | 取引先特定済み、不足額が `--fee-tolerance` 以内の請求書が 1 件 | 消込済（差額は支払手数料） |
| R3 | 取引先特定済み、2〜`--max-combo` 件の請求書の合計と一致（手数料差引含む） | 消込済（まとめ入金） |
| R4 | 取引先特定済み、未入金請求書が 1 件のみで入金額がそれを上回る | 消込済（超過分は仮受金） |
| R5 | 取引先特定済み、未入金請求書が 1 件のみで入金額が不足（手数料範囲外） | 一部消込（残額は次回以降） |
| R6 | 取引先特定済みだが候補が複数・一意に決まらない | 要確認（候補を列挙） |
| R7 | 取引先不明、金額が全未入金請求書の中で一意に一致 | 消込済（確度 medium、サマリーで要確認表示） |
| R8 | 取引先不明、同額の請求書が複数 | 要確認 |
| R9 | 上記いずれにも該当しない | 未消込 |

設計上のポイント:

- **推測で消さない**: 同額の請求書が複数ある場合は支払期日の近い方を選ぶようなことはせず、要確認に回します（誤消込は後で見つけにくいため）
- **すべて整数（円）で計算** し、浮動小数点の誤差を出しません
- 入金は日付順に処理し、一部入金の残額は後続の入金で消し込めます
- まとめ入金の探索は、支払期日の古い順に最大 12 件の請求書から組み合わせを探すため、件数が多くても爆発しません
- 各仕訳は貸借一致をコードで検証してから出力します

**仕訳の形**

| ケース | 借方 | 貸方 |
|---|---|---|
| 完全一致 | 普通預金 | 売掛金 |
| 手数料差引 | 普通預金 ＋ 支払手数料 | 売掛金 |
| 過入金 | 普通預金 | 売掛金 ＋ 仮受金 |
| 一部入金 | 普通預金 | 売掛金（入金額分） |
| `--suspense` 指定時の未消込 | 普通預金 | 仮受金 |

## 前提・仮定（必ずご確認ください）

### 全銀協フォーマット（入出金取引明細）

- 全銀協標準通信プロトコルのデータフォーマット「入出金取引明細」（種別コード `03`）の **1 レコード 200 バイト** 固定長、JIS（Shift_JIS / cp932）を前提としています。EBCDIC は非対応です
- レコードの区切りは CR+LF（改行あり）と改行なしの 200 バイト連続の両方に対応
- 使用する主なバイト位置（1 始まり）: データレコードの照会番号 2–9、勘定日 10–15、入払区分 22（1=入金 / 2=出金）、取引区分 23–24、取引金額 25–36、振込依頼人コード 72–81、振込依頼人名 82–129、仕向銀行名 130–144、仕向店名 145–159、摘要内容 160–179、EDI 情報 180–199
- トレーラレコードの入金件数・入金額合計・出金件数・出金額合計とデータレコードを照合し、不一致ならエラーにします
- 日付の年 2 桁は銀行により **和暦（令和）** と **西暦下 2 桁** があります。`auto` では「現在の令和年＋1 以下なら令和、それより大きければ西暦」と判定します。銀行の仕様が分かっている場合は `--zengin-era reiwa` / `western` を指定してください
- CSV 版は、固定長と同じ項目順をカンマ区切りにしたもの（先頭列がデータ区分 1/2/8/9）を想定しています。銀行独自の CSV はレイアウトが異なることが多いので、その場合は汎用 CSV として `--mapping` で読み込んでください
- 実在の銀行が出力するファイルで細部（予備領域の扱いなど）が異なる場合があります。初回は必ず結果を通帳と照合してください

### マネーフォワード クラウド会計 仕訳帳インポート

- マネーフォワード クラウド会計のサポートページ「仕訳帳のインポート」（2026 年 7 月時点）に記載の **27 列（A〜AA 列）** に合わせています:
  `取引No, 取引日, 借方勘定科目, 借方補助科目, 借方部門, 借方取引先, 借方税区分, 借方インボイス, 借方金額(円), 借方税額, 貸方勘定科目, 貸方補助科目, 貸方部門, 貸方取引先, 貸方税区分, 貸方インボイス, 貸方金額(円), 貸方税額, 摘要, 仕訳メモ, タグ, MF仕訳タイプ, 決算整理仕訳, 作成日時, 作成者, 最終更新日時, 最終更新者`
- 取引日は `yyyy/MM/dd`。手数料差引・まとめ入金などの複合仕訳は、同じ取引No・同じ取引日の複数行で出力します
- 税区分: 普通預金・売掛金・仮受金は `対象外`、支払手数料は **空欄（勘定科目の既定の税区分を使用）** にしています。振込手数料を課税仕入として扱うかは事業者ごとの判断のため、必要に応じて取込後に修正してください。税額列は 0 / 空欄です
- 勘定科目名・補助科目名は事業者側の設定と一致している必要があります（`--bank-account` で普通預金の補助科目を指定）
- 文字コードは既定で Shift_JIS（cp932）。cp932 で表せない文字が含まれる場合はエラーにします（`--mf-encoding utf8` で回避可）
- 仕訳メモに明細参照、タグに `入金消込` を入れています

### その他

- 振込手数料の許容額は既定 880 円（一般的な他行宛振込手数料の上限付近）。取引先ごとの差は考慮していません
- 外貨・小数点以下の金額は扱いません
- 請求書番号の参照（R0）は、番号から数字だけを取り出して 6 桁以上のものを摘要・EDI 情報から探します

## テスト

```bash
pip install pytest   # または pip install -e ".[dev]"
python -m pytest -q
```

正規化、各リーダー（UTF-8 / Shift_JIS、全銀固定長・改行なし・CSV 版・トレーラ不一致・年の解釈）、消込ルール R0〜R9、仕訳の貸借一致、MF 27 列、CLI の一連の動作をテストしています。

サンプルの全銀ファイルは `python scripts/make_zengin_sample.py` で再生成できます。

## ライセンス

MIT License © 2026 Hao Yue

---

## English

**nyukin-keshikomi** is a small, dependency-free Python CLI that reconciles Japanese bank deposit statements against open invoices (accounts receivable). This process is called *nyukin keshikomi* (入金消込). The tool writes:

- a reconciliation result CSV with the rule applied, confidence, difference and reason for every bank line
- a double-entry journal CSV
- a journal import CSV for MoneyForward Cloud Accounting (the 27-column 仕訳帳インポート format)
- the invoices still open, with days overdue
- a Markdown summary listing everything that needs a human decision

### Features

- **Bank input:** generic internet-banking CSV with configurable column mapping, UTF-8/Shift_JIS auto-detection and Japanese/era date formats.
- **Zengin input:** the Zenginkyo 入出金取引明細 format, both 200-byte fixed-length and a CSV variant, with trailer total validation.
- **Payer-name normalization:** half/full-width, small kana, corporate abbreviations such as `ｶ)`, `(ｶ`, `カブシキガイシャ` and `株式会社`, plus spaces and punctuation. Prefix matching handles names the bank has truncated.
- **Matching cases:** exact match, bank-fee shortfall within a tolerance, overpayment (booked to 仮受金 / suspense received), partial payment, and one payment covering several invoices.
- **No guessing:** ambiguous deposits are flagged for review with their candidate invoices, never silently assigned.
- **Integer-yen arithmetic only.** Every journal entry is checked to balance.

### Usage

```bash
python -m keshikomi match --bank bank.csv --invoices invoices.csv \
    --customers customers.csv --out out/
```

See the option table above. Key options include `--fee-tolerance` (default 880 yen), `--mapping` for custom CSV columns, `--zengin-era` and `--suspense`.

### Matching rules

For each deposit the tool first identifies the customer, using the Zengin payer code or else the normalized payer name. It then compares the deposit with that customer's open invoices: invoice-number reference (R0), exact amount (R1), fee shortfall (R2), combination of 2–4 invoices (R3), overpayment against the only open invoice (R4), and partial payment (R5). Anything ambiguous goes to review (R6). For an unknown payer, a deposit is matched only if its amount is unique among all open invoices, with medium confidence (R7). Otherwise it goes to review (R8) or stays unmatched (R9).

### Assumptions

- **Zengin layout:** type code 03, 200-byte records, cp932, byte positions as listed above. Two-digit years are read as Reiwa or Gregorian; see `--zengin-era`.
- **MoneyForward import:** columns follow MoneyForward's published 27-column journal import layout. Tax category is `対象外` for bank, receivable and suspense lines, and left blank on bank-fee lines so the account default applies.

All sample data is fictional. MIT License © 2026 Hao Yue.

## ブラウザ版の開発

`keshikomi/` や `sample/` を変更したら `docs/` を作り直します（作り直し忘れは `pytest` が検出します）。

```bash
python scripts/build_web.py                       # docs/keshikomi.zip と docs/sample/ を更新
npm install pyodide@0.27.7 && node scripts/web_selftest.mjs   # ブラウザ版の出力が CLI と一致するか確認
```

GitHub Pages は「Settings → Pages → Deploy from a branch → main / docs」で公開します。

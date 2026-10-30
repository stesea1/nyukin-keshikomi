"""The browser version in docs/ must stay in sync with the package (run scripts/build_web.py)."""
import importlib.util
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def test_zip_matches_package_source():
    with zipfile.ZipFile(DOCS / "keshikomi.zip") as z:
        in_zip = {n: z.read(n) for n in z.namelist()}
    src = {p.relative_to(ROOT).as_posix(): p.read_bytes()
           for p in (ROOT / "keshikomi").rglob("*.py") if "__pycache__" not in p.parts}
    assert in_zip == src, "docs/keshikomi.zip is stale: run python scripts/build_web.py"


def test_samples_match():
    for p in (DOCS / "sample").iterdir():
        assert p.read_bytes() == (ROOT / "sample" / p.name).read_bytes(), f"docs/sample/{p.name} is stale"


def test_pyodide_version_pinned_consistently():
    html = (DOCS / "index.html").read_text(encoding="utf-8")
    js = (DOCS / "app.js").read_text(encoding="utf-8")
    v_html = re.search(r"pyodide/v([\d.]+)/full/pyodide\.js", html).group(1)
    v_js = re.search(r"pyodide/v([\d.]+)/full/", js).group(1)
    assert v_html == v_js


def test_csp_limits_network_to_self_and_cdn():
    html = (DOCS / "index.html").read_text(encoding="utf-8")
    csp = re.search(r'Content-Security-Policy" content="([^"]+)"', html).group(1)
    rules = dict((d.split()[0], d.split()[1:]) for d in (x.strip() for x in csp.split(";")) if d)
    assert rules["default-src"] == ["'none'"]
    assert rules["connect-src"] == ["'self'", "https://cdn.jsdelivr.net"]
    assert rules["form-action"] == ["'none'"]


def test_page_never_posts_data():
    js = (DOCS / "app.js").read_text(encoding="utf-8")
    assert "XMLHttpRequest" not in js and "sendBeacon" not in js and "method:" not in js
    targets = [u.strip() for u in re.findall(r'fetch\(([^)]+)\)', js)]
    assert targets and all(u in ('"keshikomi.zip"', '"runner.py"') or u.startswith('"sample/"') for u in targets), targets


def test_runner_matches_cli(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("web_runner", DOCS / "runner.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    monkeypatch.setattr(runner, "OUT", str(tmp_path / "out"))
    args = ["match", "--bank", str(ROOT / "sample/bank_generic.csv"), "--invoices", str(ROOT / "sample/invoices.csv"),
            "--customers", str(ROOT / "sample/customers.csv")]
    res = json.loads(runner.run(json.dumps(args)))
    assert res["rc"] == 0 and res["stdout"].startswith("明細 12 件")
    assert res["files"] == ["journal.csv", "keshikomi_result.csv", "mf_journal_import.csv", "open_invoices.csv", "summary.md"]
    bad = json.loads(runner.run(json.dumps(["match", "--bank", "nope.csv", "--invoices", "nope.csv"])))
    assert bad["rc"] != 0 and "エラー" in bad["stderr"]

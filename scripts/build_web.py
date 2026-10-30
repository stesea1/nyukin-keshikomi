"""Build the browser version's assets in docs/ (served by GitHub Pages).

    python scripts/build_web.py

- docs/keshikomi.zip : the keshikomi package, unpacked inside Pyodide in the browser.
  Deterministic (sorted, fixed timestamps), so rebuilding without changes gives the same bytes.
- docs/sample/       : copies of sample/ for the "サンプルで試す" button.
- docs/index.html    : app.js / style.css references get ?v=<content hash> (cache busting).

tests/test_web_bundle.py fails if docs/ is out of date with the source, so run this after
changing anything under keshikomi/, sample/, docs/app.js or docs/style.css.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SAMPLES = ["bank_generic.csv", "bank_zengin.txt", "invoices.csv", "customers.csv"]


def package_files() -> list[Path]:
    return sorted(p for p in (ROOT / "keshikomi").rglob("*.py") if "__pycache__" not in p.parts)


def build_zip(dest: Path) -> None:
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for p in package_files():
            info = zipfile.ZipInfo(p.relative_to(ROOT).as_posix(), date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, p.read_bytes())


def asset_version(name: str) -> str:
    return hashlib.sha256((DOCS / name).read_bytes()).hexdigest()[:10]


def stamp_index() -> None:
    """Reference app.js / style.css as name?v=<content hash> so browsers cannot keep a stale copy
    after an update (a cached old app.js with a new index.html breaks the page)."""
    path = DOCS / "index.html"
    html = path.read_text(encoding="utf-8")
    for name in ("app.js", "style.css"):
        html, n = re.subn(rf'(["\']){re.escape(name)}(\?v=[0-9a-f]+)?(["\'])', rf"\g<1>{name}?v={asset_version(name)}\g<3>", html)
        assert n == 1, f"index.html must reference {name} exactly once"
    path.write_text(html, encoding="utf-8")


def main() -> None:
    DOCS.mkdir(exist_ok=True)
    build_zip(DOCS / "keshikomi.zip")
    (DOCS / "sample").mkdir(exist_ok=True)
    for name in SAMPLES:
        shutil.copyfile(ROOT / "sample" / name, DOCS / "sample" / name)
    stamp_index()
    print(f"docs/keshikomi.zip ({len(package_files())} files), docs/sample/ ({len(SAMPLES)} files)")


if __name__ == "__main__":
    main()

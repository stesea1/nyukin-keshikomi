"""Glue between the web page and keshikomi.cli, run inside Pyodide.

The page writes the user's files into Pyodide's in-memory file system (/work/in),
calls run() with the same arguments as the command line, and reads /work/out back.
Nothing here touches the network. scripts/web_selftest.mjs runs this same file in
Node to check that the browser version's output is byte-for-byte the CLI's.
"""
import contextlib
import io
import json
import os
import shutil

from keshikomi.cli import main

OUT = "/work/out"


def run(args_json: str) -> str:
    args = json.loads(args_json)
    shutil.rmtree(OUT, ignore_errors=True)
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = main(args + ["--out", OUT])
        except SystemExit as e:                     # argparse errors
            rc = e.code if isinstance(e.code, int) else 2
        except Exception as e:                      # unexpected: show it instead of a blank page
            print(f"エラー: {type(e).__name__}: {e}", file=err)
            rc = 1
    files = sorted(os.listdir(OUT)) if os.path.isdir(OUT) else []
    return json.dumps({"rc": rc, "stdout": out.getvalue(), "stderr": err.getvalue(), "files": files},
                      ensure_ascii=False)

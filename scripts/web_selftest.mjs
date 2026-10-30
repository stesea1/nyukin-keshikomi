// End-to-end check of the browser version without a browser.
//
//   npm install pyodide@0.27.7        (same version as docs/app.js)
//   node scripts/web_selftest.mjs
//
// Runs docs/keshikomi.zip + docs/runner.py inside Pyodide exactly as docs/app.js does,
// then runs the normal CLI with the same arguments and requires every output file to be
// byte-for-byte identical.
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname, basename } from "node:path";
import { fileURLToPath } from "node:url";
import { loadPyodide } from "pyodide";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const docs = (p) => join(ROOT, "docs", p);
const appVersion = readFileSync(docs("app.js"), "utf8").match(/pyodide\/v([\d.]+)\//)[1];
const pkgVersion = JSON.parse(readFileSync(join(dirname(fileURLToPath(import.meta.resolve("pyodide"))), "package.json"), "utf8")).version;
if (appVersion !== pkgVersion) throw new Error(`app.js uses Pyodide ${appVersion} but ${pkgVersion} is installed`);

const py = await loadPyodide();
const u8 = (b) => new Uint8Array(b.buffer, b.byteOffset, b.byteLength);
py.unpackArchive(u8(readFileSync(docs("keshikomi.zip"))), "zip", { extractDir: "/lib/app" });
py.FS.writeFile("/lib/app/web_runner.py", readFileSync(docs("runner.py"), "utf8"));
py.runPython("import sys; sys.path.insert(0, '/lib/app'); import web_runner");

const CASES = [
  { bank: ["bank_generic.csv"], customers: true, opts: ["--bank-account", "サンプル銀行"] },
  { bank: ["bank_zengin.txt"], customers: true, opts: ["--mf-encoding", "utf8", "--suspense"] },
  { bank: ["bank_generic.csv", "bank_zengin.txt"], customers: false, opts: ["--fee-tolerance", "440", "--max-combo", "2"] },
  { bank: ["bank_generic.csv"], customers: true, opts: ["--accept-unique-amount"] },
];

let failed = 0;
for (const c of CASES) {
  // browser path (mirrors app.js: files written to /work/in, invoices and customers in their own folders)
  for (const d of ["/work/in/inv", "/work/in/cus"]) py.FS.mkdirTree(d);
  const args = ["match", "--bank"];
  for (const b of c.bank) { py.FS.writeFile(`/work/in/${b}`, u8(readFileSync(docs("sample/" + b)))); args.push(`/work/in/${b}`); }
  py.FS.writeFile("/work/in/inv/invoices.csv", u8(readFileSync(docs("sample/invoices.csv"))));
  args.push("--invoices", "/work/in/inv/invoices.csv");
  if (c.customers) {
    py.FS.writeFile("/work/in/cus/customers.csv", u8(readFileSync(docs("sample/customers.csv"))));
    args.push("--customers", "/work/in/cus/customers.csv");
  }
  args.push(...c.opts);
  py.globals.set("ARGS", JSON.stringify(args));
  const res = JSON.parse(py.runPython("web_runner.run(ARGS)"));
  if (res.rc !== 0) throw new Error("browser run failed: " + res.stderr);

  // CLI path with the same inputs and options
  const out = mkdtempSync(join(tmpdir(), "kes-"));
  const cliArgs = ["-m", "keshikomi", "match", "--bank", ...c.bank.map((b) => docs("sample/" + b)),
                   "--invoices", docs("sample/invoices.csv"), ...(c.customers ? ["--customers", docs("sample/customers.csv")] : []),
                   ...c.opts, "--out", out];
  const cliStdout = execFileSync("python3", cliArgs, { cwd: ROOT, encoding: "utf8" });

  const cliFiles = readdirSync(out).sort();
  if (JSON.stringify(cliFiles) !== JSON.stringify(res.files)) { failed++; console.log("FILE LIST DIFFERS", cliFiles, res.files); }
  for (const f of cliFiles) {
    const a = Buffer.from(py.FS.readFile(`/work/out/${f}`)), b = readFileSync(join(out, f));
    if (!a.equals(b)) { failed++; console.log(`DIFF ${c.bank.join("+")} ${f}`); }
  }
  const first = (s) => s.split("\n")[0];
  if (first(res.stdout) !== first(cliStdout)) { failed++; console.log("STDOUT DIFFERS", first(res.stdout), first(cliStdout)); }
  console.log(`ok  ${c.bank.join(" + ")}: ${first(res.stdout)} (${res.files.length} files identical)`);
}

// results table: default filter is すべて, rows needing a person come first (display only)
{
  const js = readFileSync(docs("app.js"), "utf8");
  const src = js.match(/const DISPLAY_ORDER = [^\n]+\nfunction displayOrder[\s\S]*?\n}\n/)[0];
  const displayOrder = new Function(src + "return displayOrder;")();
  const rows = [["a", "消込済"], ["b", "対象外"], ["c", "未消込"], ["d", "要確認"], ["e", "消込済"], ["f", "一部消込"], ["g", "要確認"]];
  const got = displayOrder(rows, 1).map((r) => r[0]).join("");
  if (got !== "dgcfaeb") { failed++; console.log("display order wrong", got); }
  else if (!/\n  filter\("すべて"\);\n/.test(js)) { failed++; console.log("default filter is not すべて"); }
  else console.log("ok  results table: default すべて, order 要確認 > 未消込 > 一部消込 > 消込済 > 対象外 (stable)");
}

// a broken input must come back as an error message, not a crash
py.FS.writeFile("/work/in/broken.csv", new TextEncoder().encode("foo,bar\n1,2\n"));
py.globals.set("ARGS", JSON.stringify(["match", "--bank", "/work/in/broken.csv", "--invoices", "/work/in/inv/invoices.csv"]));
const bad = JSON.parse(py.runPython("web_runner.run(ARGS)"));
if (bad.rc === 0 || !bad.stderr.includes("エラー")) { failed++; console.log("broken input not reported", bad); }
else console.log(`ok  broken input -> ${bad.stderr.trim().split("\n")[0]}`);

console.log(`Python in Pyodide: ${py.runPython("import sys; sys.version.split()[0]")}`);
if (failed) { console.log(`WEB SELFTEST FAILED (${failed})`); process.exit(1); }
console.log("WEB SELFTEST PASSED");

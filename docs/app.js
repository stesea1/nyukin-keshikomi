// Browser version of nyukin-keshikomi: runs the Python package with Pyodide, entirely in the page.
"use strict";

const INDEX_URL = "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/";
const IN = "/work/in";
const OUT = "/work/out";
const STATUSES = ["消込済", "一部消込", "要確認", "未消込", "対象外"];
const FILE_LABELS = {
  "keshikomi_result.csv": "消込結果",
  "journal.csv": "仕訳",
  "mf_journal_import.csv": "MF 取込用仕訳",
  "open_invoices.csv": "未入金請求書",
  "summary.md": "サマリー",
};

// Display order of the results table: rows that need a person first. Display only; the
// downloaded files keep the CLI's order. Stable, so rows keep their original order within a status.
const DISPLAY_ORDER = ["要確認", "未消込", "一部消込", "消込済", "対象外"];
function displayOrder(rows, si) {
  const rank = (s) => { const k = DISPLAY_ORDER.indexOf(s); return k < 0 ? DISPLAY_ORDER.length : k; };
  return rows.map((r, i) => [r, i]).sort((a, b) => rank(a[0][si]) - rank(b[0][si]) || a[1] - b[1]).map((x) => x[0]);
}

const $ = (id) => document.getElementById(id);
let py = null;
let sampleFiles = null;   // set by the sample button, cleared when the user picks files
// The run button is clickable only when Python is ready and nothing else is in progress.
const state = { ready: false, loadingSample: false, running: false };

function updateRun() {
  const b = $("run");
  b.disabled = !state.ready || state.loadingSample || state.running;
  b.textContent = !state.ready ? "Python を準備しています…"
    : state.loadingSample ? "サンプルを読み込んでいます…"
    : state.running ? "処理しています…" : "消込を実行";
}

function setStatus(text) { $("status").textContent = text; }
function sampleStatus(text, kind = "") { const e = $("sampleStatus"); e.textContent = text; e.className = "samplestatus " + kind; }
function showError(text) { const e = $("error"); e.textContent = text; e.hidden = !text; }

async function boot() {
  try {
    py = await loadPyodide({ indexURL: INDEX_URL });
    const zip = await (await fetch("keshikomi.zip")).arrayBuffer();
    py.unpackArchive(zip, "zip", { extractDir: "/lib/app" });
    py.FS.writeFile("/lib/app/web_runner.py", await (await fetch("runner.py")).text());
    py.runPython("import sys; sys.path.insert(0, '/lib/app'); import web_runner");
    state.ready = true;
    updateRun();
  } catch (e) {
    $("run").disabled = true;
    $("run").textContent = "準備に失敗しました";
    showError("Python 実行環境を読み込めませんでした。ネットワーク接続を確認して再読み込みしてください。\n" + e);
  }
}

function safeName(name) { return name.replace(/[\\/:*?"<>|]/g, "_"); }

function chosenFiles() {
  if (sampleFiles) return sampleFiles;
  return { bank: [...$("bank").files], invoices: $("invoices").files[0], customers: $("customers").files[0] };
}

function describeChoice() {
  const f = chosenFiles();
  const parts = [];
  if (f.bank.length) parts.push("明細：" + f.bank.map((x) => x.name).join("、"));
  if (f.invoices) parts.push("請求書：" + f.invoices.name);
  if (f.customers) parts.push("取引先マスタ：" + f.customers.name);
  $("chosen").textContent = (sampleFiles ? "（サンプル）" : "") + parts.join(" ／ ");
}

async function writeInput(file, dir) {
  const path = `${dir}/${safeName(file.name)}`;
  py.FS.writeFile(path, new Uint8Array(await file.arrayBuffer()));
  return path;
}

function resetFS() {
  for (const d of [IN, OUT]) {
    try { for (const n of py.FS.readdir(d)) if (n !== "." && n !== "..") py.FS.unlink(`${d}/${n}`); } catch (_) { /* absent */ }
  }
  py.FS.mkdirTree(IN);
}

async function run() {
  showError("");
  const f = chosenFiles();
  if (!f.bank.length || !f.invoices) { showError("入出金明細と請求書 CSV を選んでください。"); return; }
  state.running = true; updateRun();
  setStatus("処理しています…");
  try {
    resetFS();
    const args = ["match", "--bank"];
    const seen = new Set();
    for (const b of f.bank) {
      if (seen.has(b.name)) throw new Error(`同じ名前の明細ファイルが 2 つあります：${b.name}`);
      seen.add(b.name);
      args.push(await writeInput(b, IN));
    }
    py.FS.mkdirTree(IN + "/inv");
    args.push("--invoices", await writeInput(f.invoices, IN + "/inv"));
    if (f.customers) { py.FS.mkdirTree(IN + "/cus"); args.push("--customers", await writeInput(f.customers, IN + "/cus")); }
    args.push("--bank-format", $("bankFormat").value, "--zengin-era", $("zenginEra").value,
              "--fee-tolerance", String(Math.max(0, parseInt($("feeTolerance").value || "0", 10))),
              "--max-combo", String(Math.min(8, Math.max(1, parseInt($("maxCombo").value || "4", 10)))),
              "--bank-account", $("bankAccount").value.trim(), "--mf-encoding", $("mfEncoding").value);
    if ($("suspense").checked) args.push("--suspense");
    if ($("acceptUnique").checked) args.push("--accept-unique-amount");

    py.globals.set("ARGS", JSON.stringify(args));
    const res = JSON.parse(py.runPython("web_runner.run(ARGS)"));
    if (res.rc !== 0) {
      showError(res.stderr || res.stdout || "処理に失敗しました。");
      setStatus("");
      $("results").hidden = true;
      return;
    }
    render(res);
    setStatus("完了しました。");
  } catch (e) {
    showError(String(e.message || e));
    setStatus("");
  } finally {
    state.running = false; updateRun();
  }
}

function parseCSV(text) {
  const rows = []; let row = []; let cell = ""; let q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; }
      else if (c === '"') q = false;
      else cell += c;
    } else if (c === '"') q = true;
    else if (c === ",") { row.push(cell); cell = ""; }
    else if (c === "\n") { row.push(cell.replace(/\r$/, "")); rows.push(row); row = []; cell = ""; }
    else cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  return rows;
}

function download(name) {
  const bytes = py.FS.readFile(`${OUT}/${name}`);
  const type = name.endsWith(".md") ? "text/markdown" : "text/csv";
  const url = URL.createObjectURL(new Blob([bytes], { type }));
  const a = document.createElement("a");
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function render(res) {
  $("results").hidden = false;
  $("headline").textContent = res.stdout.split("\n")[0] || "";

  const dl = $("downloads"); dl.textContent = "";
  for (const name of res.files) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = `⬇ ${FILE_LABELS[name] || name}（${name}）`;
    b.addEventListener("click", () => download(name));
    dl.appendChild(b);
  }

  const text = new TextDecoder("utf-8").decode(py.FS.readFile(`${OUT}/keshikomi_result.csv`)).replace(/^﻿/, "");
  const [header, ...rows] = parseCSV(text).filter((r) => r.length > 1);
  const si = header.indexOf("ステータス");
  const show = ["明細参照", "勘定日", "金額", "振込依頼人名", "ステータス", "取引先名", "消込請求書", "差額", "理由"]
    .map((h) => header.indexOf(h)).filter((i) => i >= 0);

  const table = $("table"); table.textContent = "";
  const thead = table.createTHead().insertRow();
  for (const i of show) { const th = document.createElement("th"); th.textContent = header[i]; thead.appendChild(th); }
  const body = table.createTBody();
  for (const r of displayOrder(rows, si)) {
    const tr = body.insertRow(); tr.dataset.status = r[si];
    for (const i of show) {
      const td = tr.insertCell(); td.textContent = r[i];
      if (i === si) td.className = "st st-" + STATUSES.indexOf(r[i]);
      if (header[i] === "金額" || header[i] === "差額") td.className = "num";
    }
  }

  const counts = Object.fromEntries(STATUSES.map((s) => [s, rows.filter((r) => r[si] === s).length]));
  const fl = $("filters"); fl.textContent = "";
  const filter = (s) => {
    for (const tr of body.rows) tr.hidden = s !== "すべて" && tr.dataset.status !== s;
    for (const b of fl.children) b.setAttribute("aria-pressed", String(b.dataset.s === s));
  };
  for (const s of ["すべて", ...STATUSES]) {
    const n = s === "すべて" ? rows.length : counts[s];
    if (s !== "すべて" && !n) continue;
    const b = document.createElement("button");
    b.type = "button"; b.dataset.s = s; b.textContent = `${s} ${n}`;
    b.addEventListener("click", () => filter(s));
    fl.appendChild(b);
  }
  filter("すべて");
}

async function loadSample() {
  const get = async (name) => {
    const r = await fetch("sample/" + name);
    if (!r.ok) throw new Error(`サンプル ${name} を読み込めませんでした（${r.status}）`);
    return new File([await r.blob()], name);
  };
  state.loadingSample = true; updateRun();
  sampleStatus("サンプルを読み込んでいます…");
  try {
    const [bank, invoices, customers] = await Promise.all(["bank_generic.csv", "invoices.csv", "customers.csv"].map(get));
    sampleFiles = { bank: [bank], invoices, customers };
    if (!$("bankAccount").value) $("bankAccount").value = "サンプル銀行";
    describeChoice();
    sampleStatus(state.ready
      ? "✓ サンプルを読み込みました。下の「消込を実行」を押してください。"
      : "✓ サンプルを読み込みました。Python の準備ができると「消込を実行」が押せるようになります（初回は 30 秒ほど）。", "done");
    $("run").scrollIntoView?.({ behavior: "smooth", block: "center" });
  } catch (e) {
    sampleStatus("サンプルを読み込めませんでした：" + (e.message || e), "fail");
    throw e;
  } finally {
    state.loadingSample = false; updateRun();
  }
}

for (const id of ["bank", "invoices", "customers"]) {
  $(id).addEventListener("change", () => {
    if (sampleFiles) sampleStatus("自分のファイルを使います（サンプルは解除しました）。");
    sampleFiles = null; describeChoice();
  });
}
$("sample").addEventListener("click", () => loadSample().catch((e) => showError(String(e))));
$("run").addEventListener("click", run);
boot();

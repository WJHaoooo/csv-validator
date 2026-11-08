import {defaultRule, activeNames, serializeSchema, firstJsonRecords} from "/static/rules.js?v=w2";

const $ = (id) => document.getElementById(id);
const LIMIT = 5 * 1024 * 1024;
const SCHEMA_LIMIT = 128 * 1024;
let state;
let generation = 0;
let revision = 0;
let controller = null;
let conversionController = null;
let schemaController = null;
let loading = false;
let converting = false;
let importing = false;
let schemaRequest = 0;
let step = "explore";

function names() {
  return activeNames(state.ruleOrder, state.columns, state.selected);
}
function ensureRule(name) {
  if (!state.rules.has(name)) state.rules.set(name, defaultRule());
  if (!state.ruleOrder.includes(name)) state.ruleOrder.push(name);
}
export function getExplorerState() {
  return {
    file: state.file, columns: [...state.columns],
    selectedColumns: state.columns.filter((name) => state.selected.has(name)),
    preview: state.preview.map((row) => [...row]),
  };
}

function invalidateResult() {
  revision++;
  conversionController?.abort();
  conversionController = null;
  converting = false;
  if (state.result) {
    URL.revokeObjectURL(state.result.url);
    $("upload-status").textContent = "CSV 已保留；先前轉換結果已失效，請重新驗證。";
  }
  state.result = null;
  $("download-json").removeAttribute("href");
  $("json-preview").textContent = "";
  $("result-status").textContent = "";
  $("results").hidden = true;
  if (step === "results") showStep("rules");
}

function showStep(value) {
  step = value;
  $("workspace").hidden = value !== "explore" || !state.columns.length;
  $("rules-editor").hidden = value !== "rules";
  $("results").hidden = value !== "results" || !state.result;
  $("empty-state").hidden = Boolean(state.columns.length);
  for (const item of ["explore", "rules", "results"]) {
    if (item === value) $("step-" + item).setAttribute("aria-current", "step");
    else $("step-" + item).removeAttribute("aria-current");
  }
  const text = {
    explore: ["CSV EXPLORER", "先看清資料，再選擇欄位。", "上傳 CSV、檢視前 5 筆原始資料，選擇要保留的欄位。此階段尚未完成資料驗證。"],
    rules: ["CONFIGURE RULES", "為每個欄位，設定清楚規則。", "選擇型別與必填規則，再執行完整驗證。使用本專案自訂 Schema 格式。"],
    results: ["VALIDATION RESULTS", "驗證完成，準備好匯出。", "全部資料已通過本次 Schema。畫面只預覽前 5 筆，下載包含完整結果。"],
  }[value];
  $("intro-eyebrow").textContent = text[0];
  $("intro-title").textContent = text[1];
  $("intro-description").textContent = text[2];
}

function updateSelection() {
  const missing = names().filter((name) => !state.columns.includes(name)).length;
  $("selected-count").textContent = `已選擇 ${state.selected.size} / ${state.columns.length} 個 CSV 欄位`;
  $("selection-hint").textContent = missing
    ? `另保留 ${missing} 個匯入 Schema 的缺失欄位；不會自動刪除。`
    : names().length ? "規則會依 Schema 順序保留；可返回修改。" : "至少保留一個欄位才能繼續。";
  $("next-step").disabled = loading || names().length === 0;
  $("convert-button").disabled = loading || importing || converting || !names().length;
  $("convert-button").textContent = converting ? "正在驗證與轉換…" : "驗證並轉換";
  $("download-schema").disabled = importing || converting || !names().length;
  $("schema-file").disabled = converting || loading;
}

function renderColumns() {
  const term = $("column-search").value.toLocaleLowerCase();
  const list = $("column-list");
  list.replaceChildren();
  let visible = 0;
  state.columns.forEach((name, index) => {
    if (!name.toLocaleLowerCase().includes(term)) return;
    visible++;
    const label = document.createElement("label");
    label.className = "column-item";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.selected.has(name);
    checkbox.addEventListener("change", () => {
      invalidateResult();
      if (checkbox.checked) { state.selected.add(name); ensureRule(name); }
      else state.selected.delete(name);
      updateSelection();
    });
    const text = document.createElement("span");
    text.className = "column-name";
    text.textContent = name;
    const number = document.createElement("span");
    number.className = "column-index";
    number.setAttribute("aria-hidden", "true");
    number.textContent = String(index + 1).padStart(2, "0");
    label.append(checkbox, text, number);
    list.append(label);
  });
  $("visible-count").textContent = `${visible} / ${state.columns.length}`;
  $("no-results").hidden = visible !== 0;
}

function renderPreview() {
  const table = $("preview-table");
  table.tHead.replaceChildren();
  table.tBodies[0].replaceChildren();
  const row = table.tHead.insertRow();
  const marker = document.createElement("th");
  marker.textContent = "#";
  marker.scope = "col";
  marker.className = "row-number";
  row.append(marker);
  const width = Math.max(state.columns.length, ...state.preview.map((item) => item.length));
  for (let i = 0; i < width; i++) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = state.columns[i] ?? `額外儲存格 ${i + 1}`;
    row.append(cell);
  }
  state.preview.forEach((record, index) => {
    const row = table.tBodies[0].insertRow();
    const number = row.insertCell();
    number.className = "row-number";
    number.textContent = String(index + 1).padStart(2, "0");
    for (let i = 0; i < width; i++) {
      const cell = row.insertCell();
      const value = document.createElement("div");
      value.className = "cell-content";
      if (i >= record.length) {
        value.textContent = "—";
        value.classList.add("empty-cell");
        value.title = "此 record 缺少儲存格，完整轉換時會檢查欄位數。";
      } else if (record[i] === "") {
        value.textContent = "空字串";
        value.classList.add("empty-cell");
        value.title = '原始值為 ""，尚未轉型。';
      } else value.textContent = record[i];
      cell.append(value);
    }
  });
  $("preview-count").textContent = `${state.preview.length} / 5 筆預覽`;
  $("no-rows").hidden = state.preview.length !== 0;
}

function showError(message, target = "error") {
  $(target).textContent = message;
  $(target).hidden = false;
}
function errorText(data) {
  const error = data.error || {};
  const details = error.details || {};
  const parts = [error.message || "無法處理請求。"];
  if (details.line !== undefined) parts.push(`資料 record 起始行：${details.line}`);
  if (details.column !== undefined) parts.push(`欄位：${details.column}；預期型別：${details.expected_type}`);
  if (details.raw_value !== undefined) parts.push(`原始值：${JSON.stringify(details.raw_value)}${details.raw_value_truncated ? "（已截斷）" : ""}`);
  return parts.join("\n");
}

function renderRules() {
  const list = $("rules-list");
  list.replaceChildren();
  const active = names();
  $("rules-count").textContent = String(active.length);
  for (const name of active) {
    const config = state.rules.get(name);
    const missing = !state.columns.includes(name);
    const row = document.createElement("div");
    row.className = "rule-row";
    const title = document.createElement("div");
    title.className = "rule-name";
    const text = document.createElement("strong");
    text.textContent = name;
    title.append(text);
    if (missing) {
      const badge = document.createElement("small");
      badge.className = "missing-badge";
      badge.textContent = "CSV 沒有此欄位";
      title.append(badge);
    }
    const typeLabel = document.createElement("label");
    typeLabel.className = "rule-label";
    const caption = document.createElement("span");
    caption.textContent = "型別";
    const select = document.createElement("select");
    select.setAttribute("aria-label", name + " 型別");
    for (const type of ["str", "int", "float"]) {
      const option = document.createElement("option");
      option.value = type;
      option.textContent = type;
      select.append(option);
    }
    select.value = config.type;
    select.addEventListener("change", () => {
      invalidateResult();
      config.type = select.value;
      $("rule-status").textContent = "規則已修改，舊結果已失效。請重新驗證。";
      updateSelection();
    });
    typeLabel.append(caption, select);
    const requiredLabel = document.createElement("label");
    requiredLabel.className = "required-option";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = config.required;
    checkbox.setAttribute("aria-label", name + " 必填");
    const requiredText = document.createElement("span");
    requiredText.textContent = "必填";
    checkbox.addEventListener("change", () => {
      invalidateResult();
      config.required = checkbox.checked;
      $("rule-status").textContent = "規則已修改，舊結果已失效。請重新驗證。";
      renderRules();
    });
    requiredLabel.append(checkbox, requiredText);
    const hint = document.createElement("p");
    hint.className = "rule-hint";
    hint.textContent = missing
      ? config.required ? "完整驗證時將報必要欄位缺失" : "輸出保留此欄位，值為 null"
      : config.required ? "欄位與儲存格都不可缺失／空白" : "空白或缺失時轉為 null";
    row.append(title, typeLabel, requiredLabel, hint);
    list.append(row);
  }
  updateSelection();
}

function reset(file) {
  if (state) invalidateResult();
  state = {file, columns: [], selected: new Set(), preview: [], rules: new Map(), ruleOrder: [], result: null};
  schemaController?.abort();
  schemaRequest++;
  importing = false;
  $("column-search").value = "";
  $("column-list").replaceChildren();
  $("rules-list").replaceChildren();
  $("preview-table").tHead.replaceChildren();
  $("preview-table").tBodies[0].replaceChildren();
  for (const id of ["error", "rule-error"]) { $(id).hidden = true; $(id).textContent = ""; }
  for (const id of ["filename", "file-size", "column-count", "rule-status", "upload-status"]) $(id).textContent = "";
  $("dropzone").removeAttribute("aria-busy");
  showStep("explore");
  updateSelection();
}

async function inspect(file) {
  const current = ++generation;
  controller?.abort();
  loading = Boolean(file);
  reset(file);
  if (!file) return;
  if (file.size > LIMIT) {
    loading = false;
    showError("檔案超過 5 MiB，請選擇較小的 CSV。");
    updateSelection();
    return;
  }
  controller = new AbortController();
  $("upload-status").textContent = `正在讀取 ${file.name}…`;
  $("dropzone").setAttribute("aria-busy", "true");
  try {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch("/api/csv/inspect", {method: "POST", body: form, signal: controller.signal});
    const data = await response.json();
    if (current !== generation) return;
    if (!response.ok) throw new Error(errorText(data));
    state.columns = [...data.columns];
    state.preview = data.preview.map((row) => [...row]);
    state.selected = new Set(state.columns);
    state.ruleOrder = [...state.columns];
    state.rules = new Map(state.columns.map((name) => [name, defaultRule()]));
    $("filename").textContent = data.filename;
    $("file-size").textContent = file.size >= 1024 ? `${(file.size / 1024).toFixed(1)} KiB` : `${file.size} bytes`;
    $("column-count").textContent = String(state.columns.length);
    renderColumns();
    renderPreview();
    showStep("explore");
    $("upload-status").textContent = "已讀取表頭與預覽；尚未執行完整資料驗證。";
  } catch (error) {
    if (current !== generation || error.name === "AbortError") return;
    $("upload-status").textContent = "";
    showError(error instanceof TypeError ? "無法連線至伺服器，請確認服務後重試。" : error.message);
  } finally {
    if (current === generation) {
      loading = false;
      $("dropzone").removeAttribute("aria-busy");
      updateSelection();
    }
  }
}

async function importSchema(file) {
  if (!file || !state.file) return;
  invalidateResult();
  const requestId = ++schemaRequest;
  const current = revision;
  const fileGeneration = generation;
  schemaController?.abort();
  $("rule-error").hidden = true;
  if (file.size > SCHEMA_LIMIT) {
    importing = false;
    $("rule-status").textContent = "";
    showError("Schema 超過 128 KiB。原有規則未被取代。", "rule-error");
    updateSelection();
    return;
  }
  schemaController = new AbortController();
  importing = true;
  $("rule-status").textContent = "正在驗證匯入 Schema…";
  updateSelection();
  try {
    const form = new FormData();
    form.append("file", file);
    const response = await fetch("/api/schema/validate", {method: "POST", body: form, signal: schemaController.signal});
    const data = await response.json();
    if (current !== revision || fileGeneration !== generation) return;
    if (!response.ok) throw new Error(errorText(data));
    state.ruleOrder = [...data.column_order];
    state.rules = new Map(state.ruleOrder.map((name) => [name, {
      type: data.schema.columns[name].type, required: data.schema.columns[name].required,
    }]));
    state.selected = new Set(state.columns.filter((name) => state.rules.has(name)));
    renderColumns();
    renderRules();
    $("rule-status").textContent = "已取代目前規則，保留全部匯入欄位及 Schema 順序。";
  } catch (error) {
    if (current !== revision || fileGeneration !== generation || error.name === "AbortError") return;
    showError(error.message + "\n匯入失敗，原有規則未被取代。", "rule-error");
    $("rule-status").textContent = "";
  } finally {
    if (fileGeneration === generation && requestId === schemaRequest) {
      importing = false;
      if (current !== revision) $("rule-status").textContent = "設定已變更，已忽略較早的 Schema 匯入回應。";
      updateSelection();
    }
  }
}

async function convert() {
  if (converting || importing || !state.file || !names().length) return;
  invalidateResult();
  const current = revision;
  const order = names();
  converting = true;
  conversionController = new AbortController();
  $("rule-error").hidden = true;
  $("rule-status").textContent = "正在完整驗證 CSV，成功後才提供 JSON。";
  updateSelection();
  try {
    const form = new FormData();
    form.append("file", state.file);
    form.append("schema", new Blob([serializeSchema(order, state.rules)], {type:"application/json"}), "schema.json");
    const response = await fetch("/api/csv/convert", {method:"POST", body:form, signal:conversionController.signal});
    if (current !== revision) return;
    if (!response.ok) throw new Error(errorText(await response.json()));
    const blob = await response.blob();
    const preview = firstJsonRecords(await blob.text());
    const rowCount = Number(response.headers.get("X-Row-Count"));
    const columnCount = Number(response.headers.get("X-Column-Count"));
    if (current !== revision) return;
    if (!Number.isSafeInteger(rowCount) || rowCount < 0 ||
        !Number.isSafeInteger(columnCount) || columnCount !== order.length) {
      throw new Error("伺服器回傳的結果摘要不正確。");
    }
    state.result = {url:URL.createObjectURL(blob)};
    $("download-json").href = state.result.url;
    $("result-rows").textContent = String(rowCount);
    $("result-columns").textContent = String(columnCount);
    $("json-preview").textContent = preview;
    $("json-preview-count").textContent = `顯示 ${Math.min(rowCount, 5)} / ${rowCount} 筆`;
    $("result-status").textContent = "完整驗證與轉換成功";
    $("rule-status").textContent = "";
    $("upload-status").textContent = "此結果已通過本次 Schema；修改規則或重傳 CSV 後必須重新驗證。";
    showStep("results");
  } catch (error) {
    if (current !== revision || error.name === "AbortError") return;
    $("rule-status").textContent = "";
    showError(error instanceof TypeError ? "無法連線至伺服器，請重試。" : error.message, "rule-error");
    showStep("rules");
  } finally {
    if (current === revision) { converting = false; updateSelection(); }
  }
}

$("csv-file").addEventListener("change", (event) => {
  const file = event.target.files[0] || null;
  event.target.value = "";
  void inspect(file);
});
$("column-search").addEventListener("input", renderColumns);
$("select-all").addEventListener("click", () => {
  invalidateResult();
  state.selected = new Set(state.columns);
  state.columns.forEach(ensureRule);
  renderColumns(); updateSelection();
});
$("clear-all").addEventListener("click", () => {
  invalidateResult();
  state.selected.clear();
  renderColumns(); updateSelection();
});
$("next-step").addEventListener("click", () => {
  if (loading || !names().length) return;
  renderRules(); showStep("rules");
});
$("back-to-explorer").addEventListener("click", () => showStep("explore"));
$("back-to-rules").addEventListener("click", () => { renderRules(); showStep("rules"); });
$("schema-file").addEventListener("change", (event) => {
  const file = event.target.files[0];
  event.target.value = "";
  void importSchema(file);
});
$("download-schema").addEventListener("click", () => {
  if (!names().length) return;
  const blob = new Blob([serializeSchema(names(), state.rules)], {type:"application/json;charset=utf-8"});
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = "schema.json"; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$("rules-form").addEventListener("submit", (event) => { event.preventDefault(); void convert(); });
for (const name of ["dragenter", "dragover"]) {
  $("dropzone").addEventListener(name, (event) => { event.preventDefault(); $("dropzone").classList.add("dragging"); });
}
$("dropzone").addEventListener("dragleave", () => $("dropzone").classList.remove("dragging"));
$("dropzone").addEventListener("drop", (event) => {
  event.preventDefault(); $("dropzone").classList.remove("dragging");
  const files = event.dataTransfer.files;
  if (files.length === 1) void inspect(files[0]);
  else { void inspect(null); showError("請一次只選擇一個 CSV 檔案。"); }
});
reset(null);

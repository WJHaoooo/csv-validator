const $ = (id) => document.getElementById(id);
const LIMIT = 5 * 1024 * 1024;
let state = { file: null, columns: [], selected: new Set(), preview: [] };
let generation = 0;
let controller = null;
let loading = false;

// W2 can consume this handoff without browser storage or a server session.
// Copies protect the explorer arrays; the original browser File stays intact.
export function getExplorerState() {
  return {
    file: state.file,
    columns: [...state.columns],
    selectedColumns: state.columns.filter((name) => state.selected.has(name)),
    preview: state.preview.map((row) => [...row]),
  };
}

function updateSelection() {
  $("selected-count").textContent = `已選擇 ${state.selected.size} / ${state.columns.length} 個欄位`;
  $("selection-hint").textContent = state.selected.size
    ? "選擇僅保存在此頁面，尚未建立 Schema。"
    : "至少保留一個欄位才能繼續。";
  $("next-step").disabled = loading || state.selected.size === 0;
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
      if (checkbox.checked) state.selected.add(name);
      else state.selected.delete(name);
      updateSelection();
    });
    const text = document.createElement("span");
    text.className = "column-name";
    text.textContent = name;
    const number = document.createElement("span");
    number.className = "column-index";
    number.textContent = String(index + 1).padStart(2, "0");
    label.append(checkbox, text, number);
    list.append(label);
  });
  $("visible-count").textContent = `${visible} / ${state.columns.length}`;
  $("no-results").hidden = visible !== 0;
}

function renderPreview() {
  const table = $("preview-table");
  const head = table.tHead;
  const body = table.tBodies[0];
  head.replaceChildren();
  body.replaceChildren();
  const row = head.insertRow();
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
    const row = body.insertRow();
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
        value.title = "此 record 沒有這個儲存格，尚未進行欄位數驗證。";
      } else if (record[i] === "") {
        value.textContent = "空字串";
        value.classList.add("empty-cell");
        value.title = '原始值為 ""，尚未轉型。';
      } else {
        value.textContent = record[i];
      }
      cell.append(value);
    }
  });
  $("preview-count").textContent = `${state.preview.length} / 5 筆預覽`;
  $("no-rows").hidden = state.preview.length !== 0;
}

function reset(file) {
  state = { file, columns: [], selected: new Set(), preview: [] };
  $("column-search").value = "";
  $("column-list").replaceChildren();
  $("preview-table").tHead.replaceChildren();
  $("preview-table").tBodies[0].replaceChildren();
  $("workspace").hidden = true;
  $("next-placeholder").hidden = true;
  $("empty-state").hidden = false;
  $("error").hidden = true;
  $("error").textContent = "";
  $("filename").textContent = "";
  $("file-size").textContent = "";
  $("column-count").textContent = "";
  $("upload-status").textContent = "";
  $("dropzone").removeAttribute("aria-busy");
  updateSelection();
}

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = false;
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
    const response = await fetch("/api/csv/inspect", {
      method: "POST", body: form, signal: controller.signal,
    });
    const data = await response.json();
    if (current !== generation) return;
    if (!response.ok) throw new Error(data.error?.message || "無法讀取 CSV，請稍後重試。");
    state.columns = [...data.columns];
    state.preview = data.preview.map((row) => [...row]);
    state.selected = new Set(state.columns);
    $("filename").textContent = data.filename;
    $("file-size").textContent = file.size >= 1024
      ? `${(file.size / 1024).toFixed(1)} KiB` : `${file.size} bytes`;
    $("column-count").textContent = String(state.columns.length);
    renderColumns();
    renderPreview();
    $("empty-state").hidden = true;
    $("workspace").hidden = false;
    $("upload-status").textContent = "已讀取表頭與預覽；尚未執行完整資料驗證。";
  } catch (error) {
    if (current !== generation || error.name === "AbortError") return;
    $("upload-status").textContent = "";
    showError(error instanceof TypeError
      ? "無法連線至伺服器，請確認本機服務仍在執行後重試。"
      : error.message);
  } finally {
    if (current === generation) {
      loading = false;
      $("dropzone").removeAttribute("aria-busy");
      updateSelection();
    }
  }
}

$("csv-file").addEventListener("change", (event) => {
  const file = event.target.files[0] || null;
  event.target.value = "";
  void inspect(file);
});
$("column-search").addEventListener("input", renderColumns);
$("select-all").addEventListener("click", () => {
  state.selected = new Set(state.columns);
  renderColumns();
  updateSelection();
});
$("clear-all").addEventListener("click", () => {
  state.selected.clear();
  renderColumns();
  updateSelection();
});
$("next-step").addEventListener("click", () => {
  if (loading || !state.selected.size) return;
  const handoff = getExplorerState();
  $("workspace").hidden = true;
  $("next-placeholder").hidden = false;
  $("handoff-summary").textContent = `已保留 ${handoff.file.name} 與 ${handoff.selectedColumns.length} 個欄位，供後續 W2 使用。`;
});
$("back-to-explorer").addEventListener("click", () => {
  $("next-placeholder").hidden = true;
  $("workspace").hidden = false;
});
for (const name of ["dragenter", "dragover"]) {
  $("dropzone").addEventListener(name, (event) => {
    event.preventDefault();
    $("dropzone").classList.add("dragging");
  });
}
$("dropzone").addEventListener("dragleave", () => $("dropzone").classList.remove("dragging"));
$("dropzone").addEventListener("drop", (event) => {
  event.preventDefault();
  $("dropzone").classList.remove("dragging");
  const files = event.dataTransfer.files;
  if (files.length === 1) void inspect(files[0]);
  else {
    void inspect(null);
    showError("請一次只選擇一個 CSV 檔案。");
  }
});
reset(null);

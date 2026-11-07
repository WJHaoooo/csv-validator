# Configurable CSV Validator & Converter

A schema-driven CSV validation and transformation tool built with Python.

在資料匯入正式系統前，依使用者定義的 Schema 驗證 CSV、轉換型別，再輸出 JSON。
工具會拒絕不合法資料並指出問題；只有所有 record 驗證成功，才發布完整 JSON 檔案。

專案以 Python 標準函式庫實作，採用可獨立測試的模組，適合作為小型資料匯入流程的基礎。

## Features

- 自訂 JSON 格式 Schema，動態定義欄位與必填規則。
- CSV 表頭驗證：精確比對、拒絕空白與重複名稱。
- 支援 `int`、`float`、`str`，明確限制可接受的數字格式。
- 非必填欄位缺失或儲存格空白時，輸出 JSON `null`。
- 額外 CSV 欄位不驗證內容、不輸出；每筆 record 的欄位數仍必須正確。
- Fail Fast，錯誤包含路徑、實體行數及適用的欄位、原始值、預期型別與原因。
- 保留 Schema key 順序與資料列順序。
- 安全 JSON 輸出：UTF-8、Unicode、2 spaces 縮排、不覆寫既有檔案。
- argparse CLI、pytest 單元及端到端測試，無第三方執行期依賴。

## Installation — Windows PowerShell

需要 Python **3.12+**；Git 用於版本管理。下載或複製專案後，從包含 `csv-validator` 的父目錄執行：

```powershell
Set-Location .\csv-validator
python --version
python -c "import sys; assert sys.version_info >= (3, 12), 'Python 3.12+ is required'"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

`.[dev]` 會安裝本專案與 pytest，建置時使用 setuptools。
第一次安裝通常需要存取套件索引。若任一步驟失敗，先處理錯誤再繼續。

以下指令直接使用 venv Python，不需啟用腳本或變更 PowerShell Execution Policy。
若出現 `No module named csv_validator` 或 `pytest`，確認在專案根目錄，並使用同一個 venv Python 重跑 editable install；不要靠 PYTHONPATH 掩蓋安裝問題。

已驗證環境為 Windows / Python 3.14.8；Python 3.12 及其他版本尚未實測。
macOS/Linux 可使用 `python3 -m venv .venv` 與 `.venv/bin/python`，但本次未在這些平台驗證。

## Usage

先確認輸出檔案 **不存在**。若已存在，請改用新的檔名；工具不會覆寫，也不會自動建立輸出目錄。

```powershell
.\.venv\Scripts\python.exe -m csv_validator.cli --help
.\.venv\Scripts\python.exe -m csv_validator.cli --csv examples/valid.csv --schema examples/schema.json --output output.json
Get-Content -LiteralPath output.json -Encoding utf8
```

在已啟用或選定的 Python 環境中，等價用法為：

```text
python -m csv_validator.cli --csv examples/valid.csv --schema examples/schema.json --output output.json
```

成功訊息為 `Converted 3 records to ...\output.json`，退出碼 0。
此範例輸出包含 Unicode、數字與 null：

```json
[
  {
    "id": 1,
    "name": "Example Alpha",
    "score": 95.5
  },
  {
    "id": 2,
    "name": "範例乙",
    "score": null
  },
  {
    "id": -3,
    "name": "  Example Gamma  ",
    "score": 80.0
  }
]
```

確認輸出與版本庫的預期檔完全一致：

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; assert Path('output.json').read_bytes() == Path('examples/expected.json').read_bytes(); print('Output matches expected.json')"
```

### Examples

所有範例均為虛構、非敏感資料：

| 檔案 | 用途 |
|---|---|
| [schema.json](examples/schema.json) | id、name 必填，score 非必填 |
| [valid.csv](examples/valid.csv) | 欄位重新排列、前導零、負數、科學記號、空值、Unicode、額外 city 欄位 |
| [expected.json](examples/expected.json) | 與合法範例的實際輸出逐 byte 一致 |
| [invalid.csv](examples/invalid.csv) | 唯一錯誤為第二實體行 id 的 `not-an-int` |

執行錯誤範例；請讓 `invalid-output.json` 保持不存在：

```powershell
.\.venv\Scripts\python.exe -m csv_validator.cli --csv examples/invalid.csv --schema examples/schema.json --output invalid-output.json
$LASTEXITCODE
Test-Path -LiteralPath invalid-output.json
```

預期退出碼為 1，Test-Path 為 False，stderr 類似：

```text
Error: ...invalid.csv: line 2: column 'id', raw value 'not-an-int', expected int: expected an ASCII decimal integer with optional sign
```

若再次對已存在的 `output.json` 執行合法轉換，會退出 1 並顯示 `output already exists; refusing to overwrite`，原檔不變。

## Schema Format

本專案使用 **自訂 JSON 格式 Schema**，不宣稱支援完整 JSON Schema 標準。

```json
{
  "columns": {
    "id": {"type": "int", "required": true},
    "name": {"type": "str", "required": true},
    "score": {"type": "float", "required": false}
  }
}
```

- 根節點只能包含 `columns`，其值必須為非空 object。
- 欄位名稱不得為空或純空白；名稱原樣保留。
- 每個欄位只能包含 `type` 與 `required`，兩者皆必填。
- `type` 大小寫敏感，僅接受 int、float、str。
- `required` 只接受 JSON boolean，不接受 0、1 或字串。
- JSON 任意層級的重複 key、未知屬性及非標準 NaN／Infinity 均拒絕。

### 欄位、空值與順序

| 狀況 | 結果 |
|---|---|
| 必填欄位不在表頭 | 拒絕 |
| 必填儲存格為空或純空白 | 拒絕 |
| 非必填欄位不在表頭 | 保留輸出 key，值為 null |
| 非必填儲存格為空或純空白 | null |
| 非必填儲存格非空但型別錯誤 | 拒絕 |
| CSV 額外欄位 | 不驗證內容、不輸出 |

表頭大小寫敏感、不 trim；包含額外欄位在內的所有空白或重複表頭都拒絕。
每筆 record 欄位數須與表頭完全相同；空尾端儲存格必須有對應分隔符號。
CSV 欄位可任意排列，輸出 key 依 Schema 順序，資料列不排序。

### 型別轉換

| 型別 | 規則 |
|---|---|
| int | strip 後只接受 `[+-]?[0-9]+`；允許前導零 |
| float | strip 後接受 ASCII 十進位、小數及科學記號，包括 .5、5.；結果必須有限 |
| str | 非空時保留原始內容，不移除前後空白 |

數字拒絕千分位、底線、十六進位及非 ASCII 數字等未約定格式。
空值在轉型前依 required 規則處理。

## Error Handling

| 錯誤 | 說明 |
|---|---|
| SchemaError | 檔案、UTF-8、JSON 語法或 Schema 結構錯誤；先於 CSV 處理 |
| CSVHeaderError | CSV 開檔、空檔、表頭解析、重複／空白表頭或必要欄位缺失 |
| CSVRowError | record 解析、UTF-8、欄位數、必填儲存格或轉型錯誤 |
| JSONWriteError | 輸出路徑、JSON 序列化、暫存寫入或發布失敗 |

例如：缺少 Schema 會指出該檔案與讀取原因；重複 id 表頭會指出名稱；
儲存格錯誤會包含路徑、record 起始實體行數、欄位、原始字串、預期型別與原因。
欄位數錯誤提供預期與實際數量，無法解析的 record 不虛構儲存格資訊。

| 退出碼 | 意義 | 輸出位置 |
|---:|---|---|
| 0 | 正式 JSON 已成功寫入 | stdout 成功訊息 |
| 1 | Schema、CSV 驗證或輸出失敗 | stderr |
| 2 | 缺少必要參數等 CLI 使用錯誤 | stderr，argparse 說明 |

一般輸入錯誤不顯示 traceback；非預期程式錯誤不會被廣泛捕捉而隱藏。
遇到第一個問題即停止，不跳過列、不彙整錯誤、不回傳部分成功結果。

## Architecture

```text
CLI
 → Schema Validation
 → Output Path Check
 → CSV Validation & Conversion
 → JSON Writer
```

| 模組 | 責任 |
|---|---|
| cli.py | 解析參數、協調流程、stdout／stderr 與退出碼 |
| schema.py | UTF-8 載入、JSON 解析與重複 key／結構驗證 |
| csv_reader.py | 標準 CSV 解析、表頭規則、共用檔案生命週期 |
| converter.py | record 欄位數、required／空值、型別轉換，回傳 list[dict] |
| writer.py | 路徑檢查、標準 JSON 序列化、暫存及不覆寫發布 |

CSV record 可跨多個實體行，因此用讀取前的 `reader.line_num + 1` 定位起始行，不用資料列索引加 2。
表頭先驗證重複名稱，再建立位置對應，避免 dict 同名 key 覆寫造成資料遺失。

文字串流預讀的無效 UTF-8 位元組會暫存至對應實體行被 parser 消耗時，再嚴格拒絕，
以區分表頭與資料 record 的錯誤；這不是接受錯誤編碼的容錯模式。

### Safe JSON Output

驗證成功與寫入成功是不同階段：

1. 所有資料驗證完成後，先完整序列化，設定 `ensure_ascii=False`、`allow_nan=False`、`indent=2`。
2. 在同目錄建立獨占暫存檔，write、flush、fsync 並關閉。
3. Windows 使用拒絕既有目的地的 rename；其他平台用 hard link 建立新名稱，無覆寫 fallback。
4. 發布成功才回報成功；失敗盡可能清除暫存檔，不刪除競爭者或既有輸出。

早期 exists 檢查提供友善訊息，最後的不覆寫操作才是競爭保護。
Windows 行為見 [Python os.rename 文件](https://docs.python.org/3/library/os.html#os.rename)。

輸出不得與 CSV／Schema 路徑相同。若清理暫存失敗會另外警告；正式發布已成功時，
警告代表可能殘留暫存名稱，不代表正式 JSON 不完整。

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q tests/test_examples.py
.\.venv\Scripts\python.exe -m pip check
```

測試包含 Schema、CSV 表頭、逐列轉型、實體行數、Fail Fast、CLI subprocess、
JSON 內容與型別、Unicode、null、輸出保護、並行 writer 與 I/O 故障注入。
公開 examples 也透過真正 CLI 自動驗收，合法輸出須逐 byte 符合 expected.json。

2026-11-07，在獨立暫存專案、全新 venv 與 Windows PowerShell 中實際重跑上方所有 PowerShell 區塊：

- Python 3.14.8 / pytest 9.2.0：完整測試 **236 passed**（5.47 秒）。
- 公開範例：**2 passed**；正常輸出逐 byte 符合 expected.json。
- 錯誤範例退出 1、不產生輸出；重複輸出退出 1、原檔不變。
- Editable install、CLI help、pip check 均成功；確認匯入的是乾淨副本的 src package。
- 另以 core.autocrlf=true 的一次性 Git checkout 驗證 LF 範例一致，範例測試 2 passed。
- 此次文件整理僅新增範例與測試、更新設定與文件，沒有修改核心驗證邏輯。

## Limitations

- 僅支援 UTF-8、逗號分隔 CSV；不偵測編碼或分隔符號，也不自動移除 BOM。
- 僅支援 int、float、str，自訂 Schema 不是完整 JSON Schema 標準。
- 僅採 Fail Fast，不支援 Skip Invalid Rows、Collect Errors 或自動修復。
- 結果與序列化內容保存在記憶體，不適合宣稱為大型資料串流系統。
- float 使用二進位浮點數，有一般捨入與極小值下溢；超長 int 受 Python 轉換長度限制。
- 沿用 csv 欄位長度限制；strict 模式不保證識別所有非典型 CSV 變體。
- 預設拒絕覆寫既有輸出，目前沒有覆寫選項；父目錄必須已存在。
- 中斷或清理權限問題可能殘留暫存檔；不保證斷電後目錄 metadata 持久性。
- 非 Windows 發布依賴 hard link，目前未在非 Windows 平台實測。
- Python 3.12 及其他版本尚未實測。
- 尚無 Web UI、GUI、API、資料庫、Docker 或雲端部署。

## Project Layout

```text
csv-validator/
├── examples/
│   ├── schema.json
│   ├── valid.csv
│   ├── expected.json
│   └── invalid.csv
├── src/csv_validator/
│   ├── __init__.py
│   ├── cli.py
│   ├── schema.py
│   ├── csv_reader.py
│   ├── converter.py
│   └── writer.py
├── tests/
│   ├── test_project_setup.py
│   ├── test_schema.py
│   ├── test_csv_reader.py
│   ├── test_converter.py
│   ├── test_writer.py
│   ├── test_cli.py
│   └── test_examples.py
├── pyproject.toml
├── .gitattributes
├── .gitignore
└── README.md
```

本機 venv、快取、暫存與根目錄手動驗收檔不屬於公開範例；公開資料僅使用 examples/。

.gitattributes 將文字檔固定為 LF，避免 Windows Git 自動換行改變範例輸出的逐 byte 驗收。

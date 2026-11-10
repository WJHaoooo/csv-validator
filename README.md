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
- argparse CLI、pytest 單元及端到端測試；CLI 核心無第三方執行期依賴，Web 使用選用依賴。

## Installation — Windows PowerShell

需要 Python **3.12+**；Git 用於版本管理。下載或複製專案後，從包含 `csv-validator` 的父目錄執行：

```powershell
Set-Location .\csv-validator
python --version
python -c "import sys; assert sys.version_info >= (3, 12), 'Python 3.12+ is required'"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[web,dev]"
```

`.[web,dev]` 會安裝本專案、Web 選用依賴與測試工具，建置時使用 setuptools。僅需 CLI 時可用 `pip install -e .`。
第一次安裝通常需要存取套件索引。若任一步驟失敗，先處理錯誤再繼續。

以下指令直接使用 venv Python，不需啟用腳本或變更 PowerShell Execution Policy。
若出現 `No module named csv_validator` 或 `pytest`，確認在專案根目錄，並使用同一個 venv Python 重跑 editable install；不要靠 PYTHONPATH 掩蓋安裝問題。

已驗證 Windows / Python 3.14.8 與 WSL Ubuntu / Python 3.14.10；Python 3.12、macOS 與 Render 實際環境尚未驗證。
Linux 可使用 python3 -m venv .venv 與 .venv/bin/python；詳細隔離驗證步驟見 Render 指南。

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
| web.py | Web 頁面、multipart／HTTP 邊界、Inspect／Schema／Convert 路由 |
| web_service.py | 有界輸入、共用核心適配、可定位且安全的錯誤及有界 JSON |
| schema.py | UTF-8 載入、JSON 解析與重複 key／結構驗證 |
| csv_reader.py | 標準 CSV 解析、共用表頭名稱規則、Schema 必要欄位與檔案生命週期 |
| converter.py | 共用逐列 iterator；CLI 仍透過 convert_csv 回傳完整 list[dict] |
| writer.py | 共用嚴格 JSON encoder；CLI 的暫存及不覆寫發布不變 |

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

## Web v1 Schema Editor & Conversion（W2）

獨立 ASGI app：`csv_validator.web:app`。沿用原生 HTML/CSS/JavaScript，
沒有 React、伺服器 Session、資料庫或永久檔案儲存。

### 啟動與三階段操作

```powershell
Set-Location C:\Hao\csv-validator
.\.venv\Scripts\python.exe -m pip install -e ".[web,dev]"
.\.venv\Scripts\python.exe -m uvicorn csv_validator.web:app --host 127.0.0.1 --port 8002
```

開啟 http://127.0.0.1:8002/。若埠已被占用，另選未使用埠；此指令只綁定 localhost，並非公開部署。

1. **Upload & Explore**：上傳 CSV，預覽前五筆原始字串並勾選欄位。
2. **Configure Rules**：每欄預設 `str`、`required: false`；設定型別、必填或匯入 Schema。
3. **Results**：完整驗證成功後顯示筆數、欄位數、前五筆 JSON 與完整下載按鈕。

返回欄位選擇會保留已設定規則。取消勾選的 CSV 欄位不納入視覺化 Schema；
重新勾選可找回先前設定。重新上傳 CSV 會清除舊規則與結果。
所有狀態只存於頁面記憶體，不使用 localStorage；重新整理即清除。

轉換中停用提交按鈕，避免重複點擊。修改規則、改變選取、匯入 Schema 或重傳 CSV
都會使舊結果失效、撤銷下載 URL；過期的非同步回應不會覆蓋目前狀態。
錯誤時保留 CSV 與規則，可修改後重試，不提供部分成功下載。

### Schema 匯入與下載

「匯入並取代 Schema」會先送至後端既有 Schema Validator。
合法匯入取代目前規則，不合併；失敗則保留原設定並顯示原因。
僅接受本專案自訂 JSON 格式，不是任意 JSON Schema 標準。

- 匯入後保留全部定義與原順序，不默默刪除 CSV 沒有的欄位。
- 缺失欄位明確標示「CSV 沒有此欄位」：必填會在轉換時失敗，非必填輸出 null。
- CSV 沒有的匯入欄位不因返回／取消選取 CSV 欄位而消失；
  如需移除，可匯入修改後的 Schema，或重新上傳 CSV 重建規則。
- 下載的 schema.json 可直接供 CLI 使用，也可再次匯入。
- 前端用 Map 與獨立順序陣列保存規則；即使欄名為 "10"、"2"，也不讓 JavaScript object 的數字 key 排序改變 Schema 順序。
- 檔名、欄名、原始值與 JSON 預覽皆以安全文字方式渲染，不當成 HTML。

### API 契約

| 路由 | multipart 檔案欄位 | 成功 |
|---|---|---|
| GET /health | 無 | 200，`{"status":"ok"}` |
| POST /api/csv/inspect | `file`：CSV | 200，status、filename、columns、preview、preview_count |
| POST /api/schema/validate | `file`：Schema JSON | 200，status、schema、column_order |
| POST /api/csv/convert | `file`：CSV；`schema`：Schema JSON | 200，完整 UTF-8 JSON array |

三個 POST 都只接受指定的檔案欄位，不接受普通表單欄位或客戶端本機輸出路徑。
原始上傳檔名不決定伺服器路徑。

Inspect 保持 W1 契約：整份檔案檢查大小與 UTF-8，只解析表頭及前五筆 record，
拒絕空白／重複表頭；成功不代表完整資料驗證。

Schema 驗證回應例如：

```json
{
  "status": "ok",
  "schema": {
    "columns": {
      "id": {"type": "int", "required": true},
      "missing": {"type": "str", "required": false}
    }
  },
  "column_order": ["id", "missing"]
}
```

Convert 先驗證 Schema，再呼叫共用逐列 Converter。
完整 JSON 在回應前全部驗證與序列化完成；沒有 HTTP 部分成功串流。
UTF-8、資料型別與錯誤順序交由同一 Converter 判斷，與 CLI Fail Fast 一致。

成功的 response body 是 JSON array 本身，不是包裝物件：

```json
[
  {
    "id": 1,
    "missing": null
  }
]
```

回應 headers：

- Content-Type: application/json（內容 UTF-8）
- Content-Disposition: attachment; filename="converted.json"
- X-Row-Count：完整資料筆數
- X-Column-Count：Schema 欄位數
- Cache-Control: no-store
- X-Content-Type-Options: nosniff

前端保存原始 response Blob 供下載，不重新序列化結果。
畫面從伺服器 JSON 文字只擷取前五個完整 object，不把資料數值轉成 JS Number，
因此保留大整數、80.0、Unicode 與 key 順序；不建立完整結果的 JavaScript object 清單。
完整 body 仍以有上限的 Blob／文字留在瀏覽器記憶體。

### 錯誤契約

沿用 `{"error":{"code":"...","message":"..."}}`；
正式資料錯誤另外提供適用的 details：

```json
{
  "error": {
    "code": "CSV_ROW_ERROR",
    "message": "expected an ASCII decimal integer with optional sign",
    "details": {
      "line": 3,
      "column": "id",
      "raw_value": "bad",
      "raw_value_truncated": false,
      "expected_type": "int"
    }
  }
}
```

line 是 record 起始實體行數。原始值最多回傳 256 字元，截斷時明確標記；
無法解析的 record 不虛構欄位或原始值。錯誤不回傳內部檔案路徑或 traceback，日誌不記錄 CSV 原文。

| HTTP | code | 說明 |
|---:|---|---|
| 400 | MISSING_FILE / MISSING_SCHEMA / INVALID_UPLOAD / EMPTY_FILE | 請求或檔案缺失 |
| 413 | FILE_TOO_LARGE / SCHEMA_TOO_LARGE / OUTPUT_TOO_LARGE | 輸入或輸出超限 |
| 422 | SCHEMA_ERROR | 自訂 Schema 語法、結構、UTF-8 或過深巢狀錯誤 |
| 422 | CSV_HEADER_ERROR | 正式驗證的表頭或必要欄位錯誤 |
| 422 | CSV_ROW_ERROR | 欄位數、必填儲存格或型別錯誤 |
| 422 | INVALID_UTF8 / INVALID_CSV / INVALID_REQUEST | 編碼、Inspect 格式或請求錯誤 |
| 500 | JSON_WRITE_ERROR / INTERNAL_ERROR | 安全的序列化或內部失敗訊息 |
| 400 / 403 | INVALID_HOST / ORIGIN_NOT_ALLOWED | 主機或跨來源請求被拒絕 |
| 408 | UPLOAD_TIMEOUT | 上傳接收期限已到 |
| 503 | SERVER_BUSY | 活躍 API 已達上限；Retry-After: 1 |

只有 HTTP 200 的 Convert 回應才是可下載結果；失敗不包含 Content-Disposition。
預期錯誤只回報第一個，不跳過錯誤列、不收集其他錯誤。

### 安全與資源上限

- CSV：5 MiB（5,242,880 bytes）。
- Schema：128 KiB（131,072 bytes），分塊讀取、以既有 parse_schema 驗證。
- JSON 輸出：8 MiB（8,388,608 bytes），包含縮排與換行。
- Convert 整體 multipart body：5 MiB + 128 KiB + 64 KiB；最多兩個檔案、零個普通欄位。
- Inspect body 保持 5 MiB + 64 KiB；Schema 驗證 body 為 128 KiB + 64 KiB。
- 依實際串流計數，不信任 Content-Length；每次最多讀取 64 KiB。
- 透過安全暫存路徑適配共用 Converter，正常、失敗與輸出超限皆關閉檔案、清理副本及框架 spool。
- Web 逐列使用共用 iterator／JSON encoder，在超限時立刻停止，不先建立可能巨大的 list。
- 最終 JSON 僅有界緩存在記憶體，全部成功才回傳；伺服器不永久保存 CSV、Schema 或 JSON。
- 不使用 NaN／Infinity；重用 CLI 的 ensure_ascii=False、allow_nan=False、indent=2。
- 靜態資源加入 W2 版本識別，避免舊快取模組與新頁面不一致。

W3-A 已增加每 worker 活躍 API 上限、合作式上傳接收期限、Host／Origin 檢查與安全標頭。
這些不是完整公開部署防護。入口速率／連線限制、程序硬性 CPU／記憶體／執行期限、
暫存磁碟配額、HTTPS／代理設定、監控與中斷清理政策仍待 W3-B 驗收。
大欄位／大量 Schema 欄位仍可能增加 DOM 或記憶體負擔；下載和預覽也保留有上限的瀏覽器記憶體副本。
沒有 Docker、登入、資料庫或公開部署。

## Testing

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q tests/test_examples.py
.\.venv\Scripts\python.exe -m pip check
```

測試包含 Schema、CSV 表頭、逐列轉型、實體行數、Fail Fast、CLI subprocess、
JSON 內容與型別、Unicode、null、輸出保護、並行 writer 與 I/O 故障注入。
公開 examples 也透過真正 CLI 自動驗收，合法輸出須逐 byte 符合 expected.json。

W2 驗收（2026-11-08，Windows / Python 3.14.8 / pytest 9.2.0）：

- 完整 pytest：**319 passed**（7.26 秒）；W2 新增 41 項 API／整合與邊界測試。
- 測試涵蓋實際 CLI 位元組等價、型別／空值、缺失欄位、順序、Unicode、完整 CSV 語法、
  無部分下載、Schema／CSV／輸出上限、暫存清理、原始值截斷、深層 Schema 及首錯順序。
- 可選前端單元測試 `node tests/frontend_rules.mjs` 通過；只用 Node 內建功能，沒有 npm 或 Web 執行期 Node 依賴。
- 真正瀏覽器驗收：預設 str／false、取消欄位、返回保留規則、必填錯誤與重試、
  匯入取代、缺失必填失敗／非必填 null、Schema 下載再匯入、結果失效與重傳重設。
- 瀏覽器下載 JSON 已與同一份下載 Schema 下的 CLI 核心比對等價；
  預覽另確認 80.0 保留，前端單元測試確認大整數不捨入且最多五筆。
- 390px 規則設定頁無整頁水平溢出，維持 W1 視覺。
- 真實 HTTP Convert 成功結果與 examples/expected.json 位元組一致；失敗為 422、無下載 header，且首錯順序與 CLI 一致。
- 實際 wheel 打包後，從暫存副本驗證頁面、新靜態模組、web_service 與大整數轉換可用。
- W1 提交為 1178240；W2 已於 W3-A 前結案提交為 724e98f，未 Push。

W1 驗收（2026-11-08，Windows / Python 3.14.8 / pytest 9.2.0）：

- 完整 pytest：**278 passed**（10.40 秒）；新增 Explorer 測試可獨立執行，11 passed。
- JavaScript ES module 語法檢查、CLI --help、pip check 均通過。
- 真正瀏覽器驗收：預設全選、取消全選停用下一步、搜尋不改勾選、重傳重設、
  重複表頭錯誤、錯誤後重新上傳恢復、最多五筆預覽、多行／逗號／空字串及 W2 佔位。
- 390px 手機版檢查無整頁水平溢出；預覽表格在自身區塊內水平捲動。
- 實際 wheel 打包後，從暫存解壓副本驗證首頁、CSS、JS 與 API 可用。
- W0 提交為 7cd27bc；W1 保持未提交、未 Push。未新增外部依賴。

W0 驗收（2026-11-08，Windows / Python 3.14.8 / pytest 9.2.0）：

- 完整 pytest：**267 passed**（6.74 秒），包含既有 236 項與新增 Web 31 項。
- API 測試使用 FastAPI TestClient，未關閉 server exception 傳遞；測試預期錯誤、精確 5 MiB／超限、串流截斷、UTF-8 跨塊、內部失敗、日誌與資源清理。
- 實際啟動 Uvicorn：health 200、Windows curl.exe 上傳 200、缺檔 400，OpenAPI 上傳欄位正確；驗收伺服器已停止。
- CLI --help、既有端到端測試、pip check 均通過；CLI 單獨匯入不載入 FastAPI。
- 套件實測版本：FastAPI 0.162.2、Starlette 1.10.0、python-multipart 0.0.33、Uvicorn 0.54.0、httpx2 2.16.0。
- httpx2 為目前 Starlette TestClient 的建議後端，見 [官方文件](https://starlette.dev/testclient/)。
- W0 變更保持未提交，沒有公開部署，也沒有進入 W1。

CLI MVP 歷史驗收（2026-11-07，Web 開發前）：在獨立暫存專案與全新 venv 中實際重跑當時 CLI 文件的 PowerShell 步驟：

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
- 非 Windows 發布依賴 hard link；已在 WSL Linux 的完整測試驗證，Render 實際環境仍待確認。
- Python 3.12 及上述 Windows／WSL 驗證版本以外的版本尚未實測。
- Web 已提供 W2 規則編輯與轉換；尚無登入、資料庫、Docker、批次轉換或公開部署。

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
│   ├── writer.py
│   ├── web.py
│   ├── web_service.py
│   ├── web_security.py
│   └── static/
│       ├── index.html
│       ├── style.css
│       ├── app.js
│       └── rules.js
├── tests/
│   ├── test_project_setup.py
│   ├── test_schema.py
│   ├── test_csv_reader.py
│   ├── test_converter.py
│   ├── test_writer.py
│   ├── test_cli.py
│   ├── test_examples.py
│   ├── test_web.py
│   ├── test_explorer.py
│   ├── test_web_conversion.py
│   ├── test_web_security.py
│   └── frontend_rules.mjs
├── docs/
│   ├── SECURITY.md
│   └── dependency-audit.json
├── scripts/audit_dependencies.py
├── pyproject.toml
├── .gitattributes
├── .gitignore
└── README.md
```

本機 venv、快取、暫存與根目錄手動驗收檔不屬於公開範例；公開資料僅使用 examples/。

.gitattributes 將文字檔固定為 LF，避免 Windows Git 自動換行改變範例輸出的逐 byte 驗收。

## Security & Release Review — W3-A

匿名公開服務目前**尚不可直接發布**。CSV／Schema 會傳至伺服器處理，請勿上傳機密或敏感資料。

完整威脅模型、已完成防護、設定、依賴掃描、停用與日誌政策及 W3-B 阻塞清單：
[Security / Deployment Checklist](docs/SECURITY.md)。

- Web 應用入口仍為 csv_validator.web:app；create_app(SecuritySettings(...)) 可建立隔離測試／部署實例。
- 預設 Host 僅 localhost／127.0.0.1／::1；正式域名須設定 CSV_VALIDATOR_ALLOWED_HOSTS。
- 每 worker 最多 2 個活躍 POST API，超額立即 503；此限制不是全域速率限制。
- 上傳接收預設 15 秒合作式期限，不能終止同步 CPU 轉換；硬性限制必須由平台提供。
- CSP／同源檢查／安全標頭已加入，debug、docs／OpenAPI 預設關閉，API／HTML 不快取。
- UTF-8 Schema 中以 JSON escape 表示的孤立 surrogate 會作為 Web 輸入錯誤拒絕，
  避免回應序列化例外；CLI 核心規則未變。
- W3-A 完整 pytest：**356 passed**（13.81 秒，Windows／Python 3.14.8）。
  新增 37 項測試，包含實際 8 MiB 輸出超限、multipart header limits、上傳逾時清理、
  Host／Origin、突發請求拒絕、合作式取消保留 worker 許可、XSS 文字與安全錯誤。
- Editable install、pip check、CLI --help、前端 rules／lossless preview 測試通過。
- 本機 Uvicorn 真實 HTTP 6 項檢查通過（health、精確 JSON、跨來源拒絕、multipart 錯誤、HTML、JS），驗收程序已停止。
- [依賴掃描快照](docs/dependency-audit.json)：26 個已安裝 distributions、OSV 0 匹配（另記原建置／測試下限公告）；
  不代表未來或其他環境沒有漏洞。可執行 python scripts/audit_dependencies.py 重新掃描。
- W2 Commit：724e98f；W3-A 已於 W3-B 前提交為 496ad25。沒有 Push、雲端資源或公開部署。

## Render Deployment Preparation — W3-B

[Hao 的 Render 操作指南與發布阻塞清單](docs/RENDER.md)。

- Python 3.14.10 固定於 .python-version；render.yaml 僅為 Free／單 instance／auto-deploy off 草稿。
- Build：bash scripts/render-build.sh；Start：python scripts/start_render.py；Health：/health。
- 以 requirements/render.txt／build.txt 固定 Web runtime 與建置版本；production 不裝 dev extra。
- launcher 使用 0.0.0.0／PORT／單 worker，要求已驗證的 CSV_VALIDATOR_TRUSTED_PROXY_IPS；
  不繼承 Render 的 FORWARDED_ALLOW_IPS=*。缺值即停止，不以 wildcard 繞過。
- Windows Python 3.14.8：374 passed；WSL Linux Python 3.14.10：373 passed、1 Windows-only skipped。
- 兩環境的本機 HTTP smoke 均 14 項通過；python scripts/smoke_web.py 可重現，會自行停止本機程序。
- Linux production 新建環境／非 editable wheel：pip check 通過，未裝 pytest／httpx2；
  [OSV 掃描](docs/dependency-audit-render.json) 17 distributions、0 匹配。
- WSL 不是 Render 實際 image。Render 建置、代理信任、限流、硬性資源限制及費用設定仍未驗收。
- W3-A 已提交 496ad25；W3-B 結案與推送狀態以 Git 歷史為準。沒有建立 Web Service、付費資源或公開部署。

**準備檔案不等於准許公開。** 未解除指南中的阻塞前，不按 Create Web Service／Apply Blueprint；
auto-deploy off 也不能阻止首次公開部署。

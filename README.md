# Configurable CSV Validator & Converter

**Schema-driven CSV validation and JSON conversion tool built with Python and FastAPI.**

上傳 CSV，選擇保留欄位並設定型別與必填規則；全部資料通過檢查後，預覽並下載 JSON。
適合展示「資料匯入前先驗證、再轉換」的 Backend 流程，CLI 與 Web API 共用同一套 Python 驗證核心。

**[Live Demo](https://csv-validator-uw1g.onrender.com/) · [GitHub Repository](https://github.com/WJHaoooo/csv-validator)**

Demo 部署於 Render Free，閒置後可能休眠，首次開啟約需一分鐘啟動。
僅供學習、作品展示與非敏感測試資料使用，不保證正式營運等級的可用性。
CSV／Schema 會傳至伺服器處理，請勿上傳個資、公司機密或其他敏感資訊。
[Render Free 限制](https://render.com/docs/free)

## Features

- **CSV Upload & Header Validation**：UTF-8、逗號分隔、標準引號／多行 record；拒絕空白與重複表頭。
- **Preview First 5 Records**：保留原始字串與順序，預覽不代表整份資料已驗證。
- **Column Selection**：全選／取消全選、搜尋；搜尋不改變勾選狀態。
- **Custom Schema Editor**：`int`／`float`／`str`、Required／Optional Fields。
- **Schema Import / Export**：重用自訂 JSON 格式，保留匯入 Schema 定義與順序。
- **Fail Fast Validation**：第一個錯誤即停止，提供適用的行數、欄位、原因與原始值。
- **JSON Preview & Download**：前五筆預覽、完整 UTF-8 JSON、Unicode／null 與 Schema key 順序。
- **CLI Interface**：argparse 入口，完整成功後才安全發布檔案，拒絕覆寫既有輸出。
- **Structured API Errors**：一致的 JSON 錯誤契約，Web 不顯示內部路徑或 traceback。
- **Basic Upload Security Controls**：有界讀取、輸入／輸出上限、暫存清理、並行限制、Host／Origin 檢查與安全標頭。

## Engineering Highlights

| 設計 | 實際做法 |
| --- | --- |
| Modular Architecture | CLI／FastAPI 分離，重用 Schema、CSV Reader、Converter 及嚴格 JSON encoder |
| Schema-Driven Validation | 欄位名稱動態定義；明確處理型別、必填、空值、額外欄位與首錯順序 |
| Safe Web Integration | HTTP 層適配上傳與安全錯誤，核心不依賴 FastAPI，不複製第二套驗證規則 |

## Architecture

~~~mermaid
flowchart TD
    B[Browser] --> UI[HTML / CSS / JavaScript]
    UI --> API[FastAPI]
    API --> WS[Web Service Layer]
    WS --> CORE[Shared Python Validation Core]
    CORE --> WS
    WS --> JSON[Complete JSON Response]
    JSON --> UI
    CLI[CLI / argparse] --> CORE
    CORE --> WRITER[Safe JSON File Writer]
~~~

| 模組 | 責任 |
| --- | --- |
| `schema.py` | Schema 檔案／JSON 載入、重複 key 與結構驗證 |
| `csv_reader.py` | 標準 CSV 解析、表頭名稱與必要欄位驗證 |
| `converter.py` | record 欄位數、空值與型別轉換、實體起始行數 |
| `writer.py` | 共用標準 JSON encoder；CLI 暫存寫入與不覆寫發布 |
| `web_service.py` | 有界上傳、暫存適配、共用 Converter 與有界 JSON |
| `web.py` / `web_security.py` | HTTP 路由、錯誤契約、Host／Origin、標頭與並行限制 |
| `cli.py` | 參數解析與流程協調，無逐列驗證邏輯 |

## Tech Stack

Python 3.12+、FastAPI、Uvicorn、HTML／CSS／JavaScript、pytest、Git／GitHub、Render。
CSV、JSON 與 CLI 核心使用 Python 標準函式庫；Web／測試依賴以選用 extra 安裝。
沒有 React、登入、資料庫或 Docker。

## Web Usage

1. 開啟 [Live Demo](https://csv-validator-uw1g.onrender.com/)。
2. 上傳 CSV，例如 [valid.csv](examples/valid.csv)。
3. 查看前五筆原始資料並選擇欄位。
4. 設定型別／必填，或匯入 [schema.json](examples/schema.json)；也可下載設定。
5. 執行 Validate and Convert。
6. 成功後預覽並下載完整 JSON；失敗時修正規則或資料後重試。

預設規則為 `str`、`required: false`。重新上傳會清除舊狀態；修改規則後舊下載結果失效。
匯入 Schema 中缺失於 CSV 的欄位會保留：必填缺失報錯，非必填缺失輸出 null。

## Installation — Windows PowerShell

從希望放置專案的父目錄開始，需要 Git 與 Python 3.12+：

~~~powershell
git clone https://github.com/WJHaoooo/csv-validator.git
Set-Location .\csv-validator
python --version
python -c "import sys; assert sys.version_info >= (3, 12), 'Python 3.12+ is required'"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -c requirements/render.txt -e ".[web,dev]"
~~~

直接使用 venv Python，不需改 PowerShell Execution Policy。
`.[web,dev]` 包含 Web 與測試依賴；只需要 CLI 時，可在乾淨 venv 改用：

~~~powershell
.\.venv\Scripts\python.exe -m pip install -e .
~~~

如果匯入失敗或找不到 pytest，確認使用同一個 venv，重跑適用的安裝指令，不靠 PYTHONPATH 掩蓋問題。
Python 3.12 是最低宣告版本，尚未實測；已驗證 Windows 3.14.8、WSL Linux 3.14.10。
Render 使用 .python-version 指定 3.14.10；macOS 尚未驗證。

## CLI Usage

輸出檔案必須尚不存在，父目錄必須已存在；若已有同名檔案，請使用新檔名。
以下指令不要用來覆蓋自己的資料。

~~~powershell
.\.venv\Scripts\python.exe -m csv_validator.cli --help
.\.venv\Scripts\python.exe -m csv_validator.cli --csv examples/valid.csv --schema examples/schema.json --output output.json
Get-Content -LiteralPath output.json -Encoding utf8
.\.venv\Scripts\python.exe -c "from pathlib import Path; assert Path('output.json').read_bytes() == Path('examples/expected.json').read_bytes(); print('Output matches expected.json')"
~~~

合法範例轉換為：

~~~json
[
  {"id": 1, "name": "Example Alpha", "score": 95.5},
  {"id": 2, "name": "範例乙", "score": null},
  {"id": -3, "name": "  Example Gamma  ", "score": 80.0}
]
~~~

非法範例（先確認 `invalid-output.json` 不存在）：

~~~powershell
.\.venv\Scripts\python.exe -m csv_validator.cli --csv examples/invalid.csv --schema examples/schema.json --output invalid-output.json
$LASTEXITCODE
Test-Path -LiteralPath invalid-output.json
~~~

預期退出 1、無輸出檔；第一個錯誤為第二實體行的 `id='not-an-int'`，預期型別 int。
CLI 退出碼：0 成功、1 驗證／輸出失敗、2 參數錯誤；錯誤至 stderr。

### Examples

全部使用虛構資料：

| 檔案 | 用途 |
| --- | --- |
| [schema.json](examples/schema.json) | id、name 必填，score 非必填 |
| [valid.csv](examples/valid.csv) | 重新排列、前導零、空值、科學記號、Unicode、額外欄位 |
| [expected.json](examples/expected.json) | 與 CLI 實際輸出逐 byte 一致 |
| [invalid.csv](examples/invalid.csv) | 一個明確的非法 int |

## Schema Format

使用自訂 JSON 格式，**不是完整 JSON Schema 標準**：

~~~json
{
  "columns": {
    "id": {"type": "int", "required": true},
    "name": {"type": "str", "required": true},
    "score": {"type": "float", "required": false}
  }
}
~~~

- Schema 先於 CSV 驗證；拒絕重複 JSON key、未知屬性、非法型別與非 boolean required。
- 表頭精確比對、大小寫敏感，不 trim。額外 CSV 欄位不驗證內容、不輸出。
- required=true：欄位必須存在，儲存格不得為空或純空白。
- required=false：欄位缺失／儲存格空白轉成 None／JSON null；非空型別錯誤仍拒絕。
- 每筆 record 欄位數須與表頭一致，包括額外欄位與空的尾端儲存格。
- int：可選正負號的 ASCII 十進位整數，允許前導零，拒絕小數／底線／非 ASCII 數字。
- float：十進位／科學記號，接受 .5 與 5.，拒絕 NaN／Infinity／非有限數值／底線。
- 數字轉型前 trim；非空 str 保留原始空白。保留 Schema key 與 CSV record 順序。

## API Overview

上傳均為 multipart/form-data 的**檔案 part**，不是一般文字欄位：

| Method / Path | 輸入 | 成功回應 |
| --- | --- | --- |
| GET /health | 無 | `{"status":"ok"}` |
| POST /api/csv/inspect | `file`：CSV | status、filename、columns、preview、preview_count |
| POST /api/schema/validate | `file`：Schema JSON | status、schema、column_order |
| POST /api/csv/convert | `file`：CSV；`schema`：JSON 檔案 | 完整 JSON array、attachment、列數／欄數 headers |

Inspect 只解析表頭與前五筆 record，並檢查整份 UTF-8／檔案大小；不代表全部資料通過驗證。
Convert 成功回應是 JSON array 本身，失敗只有首個錯誤，無部分下載。
詳細 request／response、錯誤 code 與 headers 見 [API Contract](docs/API.md)。

## Run Web Locally

~~~powershell
.\.venv\Scripts\python.exe -m uvicorn csv_validator.web:app --host 127.0.0.1 --port 8002 --no-access-log
~~~

開啟 [本機頁面](http://127.0.0.1:8002/)，Ctrl+C 停止。
本機使用 HTTP；Render 的啟動器與 HTTPS 設定見 [部署與運維指南](docs/RENDER.md)。
不要把 Render 專用環境變數搬到一般本機啟動。

## Testing & Acceptance

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pytest -q tests/test_examples.py
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/smoke_web.py
.\.venv\Scripts\python.exe scripts/smoke_web.py --trusted-proxy
~~~

可選前端純函式測試（需 Node，沒有 npm／Web 執行期 Node 依賴）：

~~~powershell
node tests/frontend_rules.mjs
~~~

2026-11-11 本次重新執行完整 pytest：**382 passed**（Windows／Python 3.14.8）。
另在全新 clone／venv 重跑 README 指令，382 passed；相對連結與 anchor 檢查 29 項均通過。
涵蓋 Schema、表頭、逐列轉型、空值、實體行數、CLI、API、範例、輸出保護、限制、清理與代理安全。
W007 的 WSL Python 3.14.10 紀錄為 381 passed／1 Windows-only skipped，非本次重新執行數量。

Hao 已完成八項公開驗收：首頁資源、上傳預覽、欄位規則、完整轉換、下載內容、
首錯無部分下載、手機行動網路操作及 Render Logs 檢查（使用者提供的驗收結果）。
本次獨立 GET 確認公開首頁及 /health 均回 200；沒有對公開服務上傳資料或壓測。

## Security & Limitations

| 項目 | 現況 |
| --- | --- |
| 上限 | CSV 5 MiB、Schema 128 KiB、JSON 8 MiB；另有 multipart 總長與檔數限制 |
| 資料生命週期 | 每請求私有暫存目錄／spool，一般成功與失敗皆清理；不提供永久儲存 |
| 錯誤／日誌 | 結構化安全錯誤，Web 不洩漏內部路徑／traceback，不主動記錄原文 |
| HTTP／前端 | 精確 Host／Origin、安全標頭、文字渲染，沒有開放 wildcard CORS |
| 並行／代理 | 每 worker 活躍 API 2；預設不信任 forwarded headers，可能只看到平台代理 IP |
| 尚未具備 | 每使用者 IP 限流、完整硬性 CPU／RSS／轉換期限、正式服務 SLA |
| 記憶體 | CLI 收集完整結果；Web 逐列轉換但完整 JSON 有界緩存在記憶體，並非無界大型串流 |
| 格式 | 僅 UTF-8、逗號 CSV、int／float／str；不偵測編碼，不支援 XLSX／Skip Invalid Rows |
| 平台 | Render Free 可能休眠、冷啟動或因額度／資源受限；不保證可用性 |
| 其他 | 浮點數有一般二進位捨入；csv 欄位長度有限，strict 不保證辨識所有 CSV 變體 |

不保證 kill／斷電後執行清理或安全抹除；上傳期限不會殺死 CPU thread。
本專案沒有宣稱完全安全或通過滲透測試。[安全審查紀錄](docs/SECURITY.md)

## Project Layout & Documentation

~~~text
src/csv_validator/       # CLI、共用核心、Web adapters 與 static/
tests/                  # 單元、整合、端到端與安全回歸
examples/               # 虛構成功／失敗資料與 expected JSON
scripts/                # Render build/start、本機 smoke、依賴公告查詢
requirements/           # 正式環境 runtime／build 約束
docs/                   # API、部署、安全、Release 草稿、面試準備
~~~

- [API Contract](docs/API.md)
- [Render Deployment & Operations](docs/RENDER.md)
- [Security Review](docs/SECURITY.md)
- [v0.2.0 Release Notes Draft](docs/RELEASE_NOTES_v0.2.0.md)
- [三分鐘面試介紹與 AI 協作說明](docs/INTERVIEW.md)

## Version Status

公開驗收的程式碼為 `9436f21`；v0.2.0 是 Web v1 + Public Demo 的**待確認發行版本**。
查核時無既有 Git Tag／公開 GitHub Release；帳號內未公開的 Draft 未查閱。
v0.1.0 僅代表 CLI MVP 規劃里程碑，不宣稱曾建立 Release。
Python package／ASGI metadata 目前仍為 0.1.0，本次僅更新文件；是否在正式標記前對齊為 0.2.0，
列於 Release 草稿待 Hao 確認。尚未發布 PyPI 套件。

本專案使用 AI／Codex 協助開發，需求、規則與驗收由 Hao 參與確認；面試資料明列協作方式與設計取捨。

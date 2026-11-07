# Configurable CSV Validator & Converter

Python CLI side project：未來依使用者提供的 CSV 與自訂 JSON Schema 設定，驗證資料並轉換成 JSON。這是自訂 Schema 格式，不宣稱完整支援 JSON Schema 標準。

## 目前狀態

Task 001 已完成專案骨架：`src` layout、editable install、CLI 說明入口與 pytest 環境。Task 002A 已加入自訂 Schema 的 UTF-8 載入、JSON 解析與基本結構驗證。Task 003A 已加入 CSV 第一筆 record 的表頭讀取與驗證。尚未實作 CSV 資料列驗證、資料型別轉換與 JSON 輸出。

執行 CLI 時目前只有 `--help` 可用，沒有 CSV、Schema 或輸出路徑參數；不帶參數會直接退出，不會執行轉換。

## 預期完整 MVP（資料列與輸出功能尚未實作）

- 先驗證自訂 Schema，再依其欄位設定處理 CSV，不使用固定欄位。
- 支援 `int`、`float`、`str`。
- `required: true` 要求欄位存在，每筆資料不得為空或僅含空白。
- 採 Fail Fast；資料錯誤包含行數、欄位、原始值、預期型別與原因。
- 全部驗證成功後才輸出 JSON；失敗時不能留下部分正式輸出。

Decision 009～012 已確認：非必填欄位可缺失，未來輸出保留為 null；非必填儲存格為空或純空白時，未來轉為 null。額外欄位允許存在，未來不驗證也不輸出。表頭精確比對，大小寫敏感、不 trim，所有重複表頭都拒絕。本階段只實作表頭行為，尚未實作 null 補值與儲存格處理。MVP 不包含 GUI、Web API、資料庫、登入、雲端部署或大型規則引擎。

## 環境需求

- Windows PowerShell、Git、Python 3.12 或更新版本。
- 專案沒有第三方執行期依賴；開發依賴為 pytest，建置後端為 setuptools。
- `requires-python = ">=3.12"` 定義最低安裝版本，不代表所有更新版本均已實測。
- 本次環境為 Python 3.14.8；驗證範圍請見下方「驗證紀錄」。

## Windows PowerShell 快速開始

在專案根目錄 `csv-validator` 執行。`python` 必須指向預計使用的 Python 3.12+；不依賴 `py` 啟動器，也不需要啟用 venv 或變更 PowerShell Execution Policy。

```powershell
python --version
python -c "import sys; print(sys.executable); assert sys.version_info >= (3, 12), 'Python 3.12+ is required'"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -c "import csv_validator; print(csv_validator.__file__)"
.\.venv\Scripts\python.exe -m csv_validator.cli --help
.\.venv\Scripts\python.exe -m pytest
```

安裝指令會安裝本專案與 pytest，並在建置隔離環境安裝 setuptools；第一次安裝通常需要存取套件索引。Editable install 會讓 `src` 中的修改直接生效。

若要啟用虛擬環境，可選擇執行 `.\.venv\Scripts\Activate.ps1`，之後使用 `python -m csv_validator.cli --help` 與 `python -m pytest`。若 PowerShell 阻擋啟用腳本，直接使用上述完整 venv Python 路徑即可。

## 常見環境問題

- Python 低於 3.12：先安裝受支援版本，使用正確的 Python 執行檔重新建立 venv。pip 也會依 `requires-python` 拒絕不相容版本。
- 安裝失敗：查看 pip 錯誤，確認網路、套件索引及 Python 版本，再重新執行 editable install；未成功安裝前不能視為驗證通過。
- `No module named pytest`：使用同一個 venv Python 重新執行 `-m pip install -e ".[dev]"`。
- 無法匯入 `csv_validator` 或執行 CLI：確認目前在專案根目錄、editable install 成功，且使用的是同一個 venv Python。不要藉由手動設定 `PYTHONPATH` 掩蓋安裝問題。

## Schema API（Task 002A）

本階段透過 Python API 使用 Schema，CLI 維持原本的 help-only 行為。

```python
from csv_validator.schema import SchemaError, load_schema

try:
    schema = load_schema("schema.json")
except SchemaError as error:
    print(error)
else:
    print(schema["columns"])
```

最小合法的 UTF-8 `schema.json`：

```json
{
  "columns": {
    "id": {"type": "int", "required": true}
  }
}
```

- `load_schema(path)`：接受字串或 PathLike，讀取 UTF-8 檔案，解析並驗證後回傳 dict。
- `parse_schema(text)`：解析 JSON 字串，拒絕任何層級的重複 object key，再檢查結構。
- `validate_schema(data)`：驗證已解析的 Python 結構，回傳原 dict；不複製或正規化欄位名稱，也不修改資料。
- `SchemaError(ValueError)`：讀取、解碼、JSON 語法或結構錯誤；訊息提供檔案路徑（透過 loader）、問題位置與原因。原始例外保留於 `__cause__`。

Schema 契約：

1. 根節點只能包含 `columns`，且 `columns` 必須是非空 object。
2. 欄位名稱不得為空或純空白；非空白名稱原樣保留。
3. 欄位設定只能包含 `type` 與 `required`，兩者皆必填。
4. `type` 僅接受大小寫敏感的 `int`、`float`、`str`。
5. `required` 僅接受 JSON boolean，數字與字串均拒絕。
6. 接受 JSON 合法的空白與換行；拒絕重複 key 與非標準的 `NaN` / `Infinity` 常數。

遇到錯誤即拋出例外，不收集全部錯誤。例如：
`$["columns"]["id"]["required"]: expected a JSON boolean`。
讀取與 JSON 解析先於結構檢查；多個問題同時存在時，不保證跨階段按文字位置回報。
若資料已被其他解析器轉成 dict，重複 key 的資訊已遺失；需使用 `load_schema` 或 `parse_schema` 才能保證檢查重複 key。

Schema 回傳值仍可修改；呼叫者應保留驗證結果，不應在修改後假設仍然合法。
本模組只讀取檔案，不產生輸出。檔案一次載入記憶體，目前不設定檔案大小或巢狀深度限制。
`required` 的 CSV 資料驗證行為尚未實作。

## CSV 表頭 API（Task 003A）

正式檔案處理請使用整合入口，先載入 Schema，再讀 CSV：

```python
from csv_validator.schema import load_schema
from csv_validator.csv_reader import load_csv_header

schema = load_schema("schema.json")
headers = load_csv_header("input.csv", schema)
print(headers)
```

- `load_csv_header(path, schema)`：先重用 `validate_schema` 確認 Schema，再開啟 CSV，讀取並驗證表頭。成功回傳依原順序保留名稱的 list。
- `read_csv_header(path)`：低階讀取函式，只解析第一筆 CSV record，不保證名稱合法或符合 Schema。不可把它的回傳值當作已通過驗證的表頭。
- `validate_headers(headers, schema)`：獨立驗證表頭，也會重用既有 Schema Validator，成功回傳原 list。整合入口與此函式都保留 Schema 防護，未另寫 Schema 驗證規則。
- `CSVHeaderError(ValueError)`：檔案、UTF-8、CSV 解析與表頭錯誤。整合入口的 CSV 錯誤附檔案路徑，適用時附表頭名稱；Schema 本身錯誤維持 `SchemaError`。

UTF-8、逗號分隔，採用 `csv.reader(..., strict=True)` 與 `newline=""`。
第一筆 record 就是表頭，不跳過開頭空白 record。空檔、空 record、空字串或純空白名稱皆拒絕。
表頭名稱完全精確比對，保留大小寫、前後空白、引號內逗號與換行。
所有名稱（含額外欄位）都先檢查重複，再檢查 Schema 必要欄位。

`required: false` 不要求欄位出現在表頭，因此 `id,name,city` 可符合有必要欄位 `id`、`name` 及非必填欄位 `score` 的 Schema。
本階段不產生 JSON，故不補 `score: null`，也不刪除回傳表頭中的額外欄位 `city`。

不能直接使用 `split(",")`，因為 `"full,name",age` 是兩個欄位；CSV parser 還須處理跳脫雙引號與跨實體行的 record。
重複表頭若直接與資料列組成 dict，同名 key 可能覆寫先前值而遺失資料，因此必須先拒絕。

範圍與限制：

- 只解析第一筆 record，不檢查後續 record 的語法、欄位數量或資料值。
- 文字串流可能預讀並解碼表頭之後的位元組，因此附近的無效 UTF-8 也可能使讀取失敗；成功不代表整份 CSV 已驗證。
- `strict=True` 不是所有 CSV 變體的完整格式檢查器；例如未加引號欄位內的單獨雙引號，標準函式庫可能視為文字接受。
- 未提供其他編碼、自動偵測、其他分隔符號或 BOM 特殊處理；UTF-8 BOM 不會自動從名稱移除。
- 沿用標準函式庫的欄位長度限制；超限會回報 CSV 解析錯誤。
- 無資料列驗證、型別轉換或任何正式輸出，CLI 保持原有 `--help`。

## 專案結構

```text
csv-validator/
├── src/
│   └── csv_validator/
│       ├── __init__.py
│       ├── cli.py
│       ├── csv_reader.py
│       └── schema.py
├── tests/
│   ├── test_csv_reader.py
│   ├── test_project_setup.py
│   └── test_schema.py
├── pyproject.toml
├── .gitignore
└── README.md
```

## 驗證紀錄

2026-11-07，在 Windows / Python 3.14.8 / pytest 9.2.0 上實測：

- `python -m venv .venv` 與 editable install 成功。
- Package import 與 CLI `--help` 成功（退出碼 0）。
- `python -m pytest`：3 項測試通過。
- `python -m pip check`：無損壞的依賴需求。
- Git 忽略規則已檢查，涵蓋 venv、快取、bytecode 與 build/packaging 產物。

Codex 沙箱首次建立 venv 時曾阻擋暫存目錄寫入，已經授權流程在沙箱外重試成功。一般 PowerShell 可直接使用上述指令。

Python 3.12 及其他 Python 版本尚未實測；本機 `py` 啟動器未找到已登錄的 Python，因此操作步驟採用可用的 `python` 指令。

### Task 002A 驗證紀錄

2026-11-07，Windows / Python 3.14.8 / pytest 9.2.0：

- Task 001 初始提交：`4b1eeec`（`chore: initialize csv validator project`）。
- `.\.venv\Scripts\python.exe -m pytest`：69 項通過（原有 3 項與 Schema 66 項）。
- CLI `--help` 回歸驗證成功。
- 未新增第三方依賴；Task 002A 於 Task 003A 開始前提交為 `000b0b4`（`feat: add schema validation`）。
- Python 3.12 及其他版本尚未實測。

### Task 003A 驗證紀錄

2026-11-07，Windows / Python 3.14.8 / pytest 9.2.0：

- 完整 pytest：111 項通過（既有 69 項，新增 CSV 表頭 42 項）。
- CLI `--help` 回歸驗證成功。
- Task 002A 提交前僅清除兩個檔案末尾的多餘空白行，無功能重構。
- 本次 Task 003A 變更保留未提交；未新增依賴或遠端設定。
- 沙箱內首次測試因 pytest 暫存目錄權限發生 9 個 setup error，沙箱外重跑既有 69 項與完整 111 項均通過。
- Python 3.12 及其他版本尚未實測。

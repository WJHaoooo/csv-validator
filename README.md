# Configurable CSV Validator & Converter

Python CLI side project：未來依使用者提供的 CSV 與自訂 JSON Schema 設定，驗證資料並轉換成 JSON。這是自訂 Schema 格式，不宣稱完整支援 JSON Schema 標準。

## 目前狀態

Task 001 僅完成專案骨架：`src` layout、editable install、CLI 說明入口與 pytest 環境。尚未實作 CSV 讀取、Schema 解析或驗證、型別轉換與 JSON 輸出。

執行 CLI 時目前只有 `--help` 可用，沒有 CSV、Schema 或輸出路徑參數；不帶參數會直接退出，不會執行轉換。

## 預期 MVP（尚未實作）

- 先驗證自訂 Schema，再依其欄位設定處理 CSV，不使用固定欄位。
- 支援 `int`、`float`、`str`。
- `required: true` 要求欄位存在，每筆資料不得為空或僅含空白。
- 採 Fail Fast；資料錯誤包含行數、欄位、原始值、預期型別與原因。
- 全部驗證成功後才輸出 JSON；失敗時不能留下部分正式輸出。

Optional 欄位與額外 CSV 欄位的處理方式尚待確認。MVP 不包含 GUI、Web API、資料庫、登入、雲端部署或大型規則引擎。

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

## 專案結構

```text
csv-validator/
├── src/
│   └── csv_validator/
│       ├── __init__.py
│       └── cli.py
├── tests/
│   └── test_project_setup.py
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

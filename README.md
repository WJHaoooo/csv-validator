# Configurable CSV Validator & Converter

使用自訂 JSON Schema 設定驗證 UTF-8 CSV，將合法資料轉型並安全輸出 JSON 的 Python CLI side project。
這是自訂 Schema 格式，不宣稱支援完整 JSON Schema 標準。

目前已完成 Schema 驗證、CSV 表頭與逐列驗證、型別轉換、CLI 整合及安全 JSON Writer。
未提供 Web UI、GUI、資料庫、部署、自動修復、跳過錯誤列或錯誤彙整。

## Windows PowerShell 安裝

需要 Python 3.12+、Git。請確認 `python` 指向預計使用的版本。
本機實測 Python 3.14.8；最低版本設定不代表所有 Python 版本均已實測。

```powershell
Set-Location C:\Hao\csv-validator
python --version
python -c "import sys; assert sys.version_info >= (3, 12), 'Python 3.12+ is required'"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m csv_validator.cli --help
.\.venv\Scripts\python.exe -m pytest -q
```

直接使用 venv Python，不需啟用腳本或調整 Execution Policy。
無第三方執行期依賴；開發依賴只有 pytest 及其必要依賴，setuptools 為建置後端。
首次安裝通常需要連線至套件索引。

若 pytest 或 package 無法匯入，使用同一個 venv Python 重跑 editable install。
不要用手動設定 PYTHONPATH 掩蓋安裝問題。Python 版本不足時，改用正確的 Python 重新建立 venv。

## 使用 CLI

準備 UTF-8 `schema.json`：

```json
{
  "columns": {
    "id": {"type": "int", "required": true},
    "name": {"type": "str", "required": true},
    "score": {"type": "float", "required": false}
  }
}
```

準備 UTF-8 `input.csv`：

```csv
id,name,score,city
001,Hao,95.5,Taipei
2,Amy,,Taichung
3,Bob,80,Kaohsiung
```

若目錄已經有同名驗收檔，請保留原檔或另選檔名，勿直接覆寫。

```powershell
.\.venv\Scripts\python.exe -m csv_validator.cli --csv input.csv --schema schema.json --output output.json
Get-Content -LiteralPath output.json -Encoding utf8
```

成功會顯示 `Converted 3 records to ...`，退出碼為 0。
輸出為 UTF-8 JSON，縮排 2 spaces、保留 Unicode、不排序 key：

```json
[
  {
    "id": 1,
    "name": "Hao",
    "score": 95.5
  },
  {
    "id": 2,
    "name": "Amy",
    "score": null
  },
  {
    "id": 3,
    "name": "Bob",
    "score": 80.0
  }
]
```

只有表頭、沒有資料 record 時輸出空陣列。
CLI 不帶參數或缺少任何必要參數時，由 argparse 顯示說明並以 2 退出。

| 結果 | 退出碼 | 訊息 |
|---|---:|---|
| 完成寫入 | 0 | stdout 成功訊息 |
| CLI 參數錯誤 | 2 | stderr 使用說明 |
| Schema、CSV 或輸出失敗 | 1 | stderr 路徑及原因；資料錯誤保留行數與欄位資訊 |

一般輸入錯誤不顯示 traceback。非預期程式錯誤不會被廣泛捕捉而隱藏。

## 資料契約

- Schema 根節點只能包含非空 `columns` object。
- 欄位名稱不得為空或純空白。設定只能包含必填的 `type`、`required`。
- type 大小寫敏感，僅接受 `int`、`float`、`str`；required 必須為 JSON boolean。
- JSON 任何層級的重複 key 均拒絕，亦拒絕 NaN、Infinity 等非標準常數。
- Schema 先驗證，才檢查輸出路徑及處理 CSV。
- CSV 為 UTF-8、逗號分隔、標準雙引號規則；使用 `csv.reader(strict=True)` 與 `newline=""`。
- 第一筆 record 為表頭，不跳過開頭空 record。表頭空白或重複均拒絕，包含額外欄位。
- 表頭精確比對：大小寫敏感、不 trim。欄位依名稱對應，不依固定位置。
- 必填欄位必須存在，且每筆儲存格不可為空或純空白。
- 非必填欄位缺失或儲存格空白時填 None，寫成 JSON null；非空但型別錯誤仍拒絕。
- 額外欄位不驗證內容、不輸出，但每筆 record 欄位數仍須與整份表頭完全相同。
- 缺少尾端儲存格也報欄位數錯誤；空尾端儲存格必須保留逗號。
- int 先 strip，只接受 `[+-]?[0-9]+`，允許前導零。
- float 先 strip，接受 ASCII 十進位、正負號、小數與科學記號，包括 `.5`、`5.`；拒絕底線、千分位與非有限結果。
- str 非空時保留原始字串，不去除前後空白。
- dict key 依 Schema 順序，結果 list 保留 CSV record 順序。
- Fail Fast：欄位數先於儲存格檢查，同列儲存格依 Schema 順序檢查。

## 安全 JSON 輸出

本次暫行限制為「輸出已存在就拒絕」，不提供覆寫選項。

1. CLI 載入並驗證 Schema。
2. 檢查輸出路徑：不得與 CSV／Schema 路徑相同，不接受既有目的地，父目錄必須存在。
3. 呼叫 converter，全部資料成功後才交給 writer。
4. Writer 再檢查路徑，完整序列化為 UTF-8 bytes，設定 `allow_nan=False`。
5. 在輸出同目錄建立獨占暫存檔，完成 write、flush、fsync 並關閉。
6. Windows 用 `os.rename` 發布，目的地在競爭期間被建立時仍拒絕覆寫。
   其他平台用 `os.link` 建立新名稱，無覆寫型 fallback。
7. 寫入／發布成功後才顯示成功訊息；失敗時盡可能清理暫存檔。

早期 exists 檢查只是友善錯誤，真正的競爭保護在最後的 no-replace 發布操作。
不使用 `os.replace`，也不直接打開正式路徑逐步寫入。
既有檔案、目錄與 dangling symlink 都會被拒絕；輸入路徑比較會解析相對路徑及 symlink alias。

如果暫存清理失敗，會發出警告並保留原本發布錯誤。
若發布已成功，清理警告代表正式 JSON 已完整寫入、但可能殘留暫存名稱，不代表正式輸出不完整。

Windows rename 的不覆寫行為見 [Python 官方文件](https://docs.python.org/3/library/os.html#os.rename)。
此策略保護正常並行 writer 的同名競爭，不承諾斷電後目錄 metadata 的持久性或抵禦惡意替換整個父目錄。

## Python API 與模組責任

```python
from csv_validator.schema import load_schema
from csv_validator.converter import convert_csv
from csv_validator.writer import write_json

schema = load_schema("schema.json")
rows = convert_csv("input.csv", schema)
write_json(rows, "output.json", input_paths=("input.csv", "schema.json"))
```

- schema.py：`load_schema` 負責 UTF-8 I/O；`parse_schema` 解析並拒絕重複 key；`validate_schema` 驗證結構，回傳原 dict。
- csv_reader.py：`read_csv_header` 只解析；`validate_headers` 驗證；`load_csv_header` 整合兩者。共用 reader 支援 converter 使用同一串流。
- converter.py：`convert_csv` 驗證所有 record，成功後回傳 list，不寫檔。
- writer.py：`check_output_path` 檢查路徑；`write_json` 接收已驗證資料，負責序列化、暫存與發布，不重做資料驗證。
- cli.py：只協調以上模組、訊息及退出碼，不含逐列規則。

錯誤類型為 `SchemaError`、`CSVHeaderError`、`CSVRowError`、`JSONWriteError`。
資料錯誤含路徑、record 起始實體行數，適用時含欄位、原始值、預期型別與原因。
起始行數使用讀取前的 `reader.line_num + 1`，支援引號中的換行，不以列索引加 2 推算。

文字串流先用 surrogateescape 暫存預讀的無效位元組，再於實體行被 parser 消耗時嚴格解碼，
因此無效 UTF-8 仍會拒絕，且可正確歸屬表頭或資料 record。
只有低階表頭讀取成功不代表整份 CSV 合法。

## 專案結構

```text
csv-validator/
├── src/csv_validator/
│   ├── __init__.py
│   ├── cli.py
│   ├── converter.py
│   ├── csv_reader.py
│   ├── schema.py
│   └── writer.py
├── tests/
│   ├── test_cli.py
│   ├── test_converter.py
│   ├── test_csv_reader.py
│   ├── test_project_setup.py
│   ├── test_schema.py
│   └── test_writer.py
├── pyproject.toml
├── .gitignore
└── README.md
```

## 測試與限制

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

2026-11-07：Windows / Python 3.14.8 / pytest 9.2.0，Task 004 最終完整測試 234 passed（4.98 秒）。
包括既有 191 項（help 測試改為檢查新 CLI 選項），新增 43 項 CLI／Writer 測試。
測試含真正 subprocess CLI、Unicode/null/順序、錯誤退出碼、無部分輸出、競爭發布及暫存故障注入。

Task 003B 已提交為 `3cc717f`；Task 004 變更保持未提交，未加入使用者的 input.csv、schema.json，未 push。
專案仍無第三方執行期依賴。

限制：

- Python 3.12、其他 Python 版本及非 Windows 發布分支尚未實測。
- 結果、JSON 字串與 UTF-8 bytes 存於記憶體；未設計大型資料串流框架。
- float 使用二進位浮點數，存在一般捨入與極小值下溢；超長 int 受 Python 轉換長度限制。
- 沿用 csv 欄位長度限制；strict 模式不是所有 CSV 變體的完整格式檢查器。
- 不自動偵測編碼／分隔符號，也不移除 UTF-8 BOM。
- Schema dict 可修改；修改後須重新驗證。若其他 JSON parser 已覆寫重複 key，結構驗證無法還原，需使用本專案 loader/parser。
- POSIX 發布依賴同檔案系統 hard link；不支援時明確失敗，不退回覆寫方案。
- 磁碟或程序突然中止可能殘留暫存檔；不保證斷電後 metadata 持久性。

另以現有 input.csv、schema.json 在獨立暫存目錄完成 CLI 實測：第一次退出碼 0；再次寫入同一路徑退出碼 1，輸出原始內容不變。驗收輸入檔未修改，測試輸出已清除。

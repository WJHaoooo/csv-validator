# Web API Contract

此文件核對現有 web.py／web_service.py；不代表提供額外 API 功能。
服務網址：[Live Demo](https://csv-validator-uw1g.onrender.com/)。
正式互動應先閱讀 [資料與安全限制](../README.md#security--limitations)。

## Routes

| Method / Path | multipart 檔案欄位 | 成功 |
| --- | --- | --- |
| GET /health | 無 | 200，`{"status":"ok"}` |
| POST /api/csv/inspect | file：CSV | 200，原始表頭與最多五筆預覽 |
| POST /api/schema/validate | file：自訂 Schema JSON | 200，驗證後 schema 與 column_order |
| POST /api/csv/convert | file：CSV；schema：JSON 檔案 | 200，完整 JSON array 下載 |

上傳必須是 multipart/form-data 的檔案 part，不接受一般文字欄位或任意伺服器輸出路徑。
Inspect／Schema 最多一個檔案，Convert 最多兩個；拒絕未知／重複欄位。
沒有開放額外 CORS；瀏覽器應從同一個 Web app 呼叫。

## Inspect

CSV `id,name` 加一筆 `001,Amy`，以 input.csv 上傳：

~~~json
{
  "status": "ok",
  "filename": "input.csv",
  "columns": ["id", "name"],
  "preview": [["001", "Amy"]],
  "preview_count": 1
}
~~~

檔名只作顯示，不決定暫存路徑。保留原始欄位名／字串與順序，正確處理 quoted commas／multiline。
拒絕空檔案、非法 UTF-8、空白或重複表頭；只有表頭時 preview 為空。
整份檔案檢查大小與 UTF-8，但只解析表頭和前五筆資料；成功不是完整資料驗證。

## Schema Validate

使用 [自訂格式](../README.md#schema-format)，非完整 JSON Schema 標準：

~~~json
{
  "status": "ok",
  "schema": {
    "columns": {
      "id": {"type": "int", "required": true},
      "name": {"type": "str", "required": false}
    }
  },
  "column_order": ["id", "name"]
}
~~~

重用既有 Schema Validator，拒絕未知屬性、重複 key、非法 type／required、過深結構及非法文字。
column_order 使前端可保留數字形式欄位名稱的 Schema 順序，不靠 JavaScript object enumeration。

## Convert

先驗證 Schema，再驗證表頭、逐列資料、轉型並序列化；保留共用核心的首錯順序。
成功 body 是 JSON array 本身，沒有 status／data 包裝：

~~~json
[
  {
    "id": 1,
    "name": "Amy"
  }
]
~~~

成功 headers：
- Content-Type: application/json，UTF-8
- Content-Disposition: attachment; filename="converted.json"
- X-Row-Count: 完整筆數
- X-Column-Count: Schema 欄位數
- Cache-Control: no-store
- X-Content-Type-Options: nosniff

只有全部成功才回傳完整 JSON，不提供部分成功下載或永久儲存。
前端只顯示前五筆 JSON，完整內容以原始 response Blob 下載，不重新將大整數轉成 JS Number。

## Error Envelope

~~~json
{
  "error": {
    "code": "CSV_ROW_ERROR",
    "message": "expected an ASCII decimal integer with optional sign",
    "details": {
      "line": 2,
      "column": "id",
      "raw_value": "not-an-int",
      "raw_value_truncated": false,
      "expected_type": "int"
    }
  }
}
~~~

details 只在適用時提供。line 為 record 起始實體行數，不能用列索引加二推算多行 CSV。
raw_value 最多 256 字元；Web 診斷文字安全輸出，不顯示內部暫存路徑／traceback。
錯誤回應沒有可下載結果的 Content-Disposition。

| HTTP | code |
| --- | --- |
| 400 | MISSING_FILE、MISSING_SCHEMA、INVALID_UPLOAD、EMPTY_FILE、INVALID_HOST |
| 403 | ORIGIN_NOT_ALLOWED |
| 408 | UPLOAD_TIMEOUT |
| 413 | FILE_TOO_LARGE、SCHEMA_TOO_LARGE、OUTPUT_TOO_LARGE |
| 422 | SCHEMA_ERROR、CSV_HEADER_ERROR、CSV_ROW_ERROR、INVALID_UTF8、INVALID_CSV、INVALID_REQUEST |
| 500 | JSON_WRITE_ERROR、INTERNAL_ERROR |
| 503 | SERVER_BUSY，附 Retry-After: 1 |

其他 HTTP 路由錯誤使用 HTTP_ERROR。一般使用者錯誤不以 traceback 回應。

## Resource Boundaries

CSV 5 MiB、Schema 128 KiB、JSON 8 MiB。另設 multipart 總 body 上限：
Inspect 5 MiB+64 KiB；Schema 128 KiB+64 KiB；Convert 5 MiB+128 KiB+64 KiB。
按實際 bytes 計數，不信任 Content-Length。

每 worker 預設最多兩個活躍 POST API，超額立即 503，不代表每訪客 IP 限流。
合作式上傳期限預設 15 秒，不能殺死轉換 thread。
Render 預設不信任 forwarded headers；公開 HTTPS 的 Origin／HSTS 判斷來自部署設定。
詳見 [Render 運維](RENDER.md) 與 [歷史安全審查](SECURITY.md)。

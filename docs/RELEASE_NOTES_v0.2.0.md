# v0.2.0 Release Notes

## Release Title

v0.2.0 — Web v1: Schema Editor, CSV Validation & JSON Download

## Features

- Browser CSV upload、精確表頭驗證與前五筆原始 record 預覽。
- 欄位勾選／搜尋、自訂 str／int／float 與 required 規則。
- 自訂 Schema JSON 匯入／匯出，保留定義、缺失欄位與 Schema 順序。
- Fail Fast 完整驗證，支援 optional 缺失／空白轉 null，忽略額外欄位的內容與輸出。
- 完整成功才提供 JSON；前五筆結果預覽、Unicode／null／順序與原始 JSON 下載。
- 保留 Python module CLI 與安全、不覆寫的檔案輸出。
- FastAPI health、inspect、schema validate、convert API 與結構化錯誤。

## Architecture Highlights

- CLI／Web adapters 分離，共用 Schema、CSV Header、Row Converter 及 JSON encoder。
- 依表頭名稱配對，保留 Schema key 與 CSV record 順序，處理多行 CSV 的實體起始行數。
- Web 透過有界上傳／私有暫存路徑適配共用核心，沒有複製驗證規則。
- 型別格式明確，拒絕非標準 JSON 數值；前端文字渲染與原始 Blob 下載。

## Security & Limitations

- CSV 5 MiB／Schema 128 KiB／JSON 8 MiB，另有 multipart 與並行限制。
- 一般成功／失敗自動關閉 spool、清理副本，不提供永久儲存。
- 精確 Host／Origin、安全標頭、統一安全錯誤；預設不信任 forwarded headers。
- 匿名 Demo，不適合個資、公司機密或任何敏感資料。
- 無每訪客 IP 限流、硬性 CPU／RSS／單筆轉換期限、正式 SLA 或滲透測試保證。
- 僅 UTF-8、逗號 CSV、自訂 Schema、int／float／str；不支援 XLSX、Skip Invalid Rows。
- Render Free 會休眠／冷啟動並受用量及資源限制，不代表正式營運等級服務。
- Python 最低宣告 3.12，但本次未驗證 3.12／macOS。

## Live Demo

[Open CSV Validator Web v1](https://csv-validator-uw1g.onrender.com/)

Hao 已回報完成八項公開驗收，包含手機與 Logs；本次獨立確認首頁及 /health 為 200。
沒有對公開 Demo 進行資料上傳或壓測。

## Usage / Documentation

- [README / CLI & Web Usage](../README.md)
- [API Contract](API.md)
- [Render Operations](RENDER.md)
- [Security Review](SECURITY.md)
- [Example CSV](../examples/valid.csv)／[Schema](../examples/schema.json)／[Expected JSON](../examples/expected.json)

## Validation

- W009 將 Python package／FastAPI metadata 統一為 0.2.0；API 契約、依賴與驗證規則不變。
- W009 完整 pytest：382 passed（9.53 秒），CLI help／pip check／範例與本機 HTTP smoke 通過。

- 2026-11-11 重新執行完整 Windows pytest：382 passed，Python 3.14.8。
- CLI help、pip check、範例 2 項測試、兩模式本機 HTTP smoke、前端規則通過。
- 全新 clone／venv 實際重跑 README 安裝／操作：382 passed（12.36 秒），thread warning 視為錯誤仍通過；CLI-only 不安裝 FastAPI。
- README 原樣 Uvicorn 指令驗證本機 health／首頁／CSS／JS，完成後停止；29 項相對連結與 anchor 通過。
- W007 Linux Python 3.14.10 曾驗證 381 passed／1 Windows-only skipped；不是本次 Linux 重跑結果。
- 沒有新增產品功能、修改核心規則或部署。


## Release & Maintenance

- [GitHub Release v0.2.0](https://github.com/WJHaoooo/csv-validator/releases/tag/v0.2.0)
- [Project Closure](PROJECT_CLOSURE.md)
- Status: Completed — Maintenance Only
- v0.1.0 僅為 CLI MVP 功能里程碑，未建立該 Tag／Release；本次沒有發佈 PyPI 套件。
- Render 最後由 Hao 確認的部署 Commit 為 9436f21；Auto-Deploy Off，本次不強制重新部署。
  與發布版僅差文件及版本 metadata，功能相同。平台實際 Deploy SHA 請以 Dashboard 為準。
- 僅在 Hao 主動要求時處理 Bug、必要安全更新或主機問題，不再啟動新功能開發。

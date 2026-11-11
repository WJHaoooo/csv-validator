# v0.2.0 GitHub Release Notes — Draft

**狀態：文字草稿，尚未建立 Tag 或 GitHub Release。**
2026-11-11 查核本機／遠端無 Git Tag，GitHub 公開 Releases 清單為空。
v0.1.0 是 CLI MVP 功能里程碑，不宣稱曾實際建立發行。
程式碼部署版本為 9436f21；本次文件 Commit 不更動已部署的程式。

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

- 2026-11-11 重新執行完整 Windows pytest：382 passed，Python 3.14.8。
- CLI help、pip check、範例 2 項測試、兩模式本機 HTTP smoke、前端規則通過。
- 全新 clone／venv 實際重跑 README 安裝／操作：382 passed（12.36 秒），thread warning 視為錯誤仍通過；CLI-only 不安裝 FastAPI。
- README 原樣 Uvicorn 指令驗證本機 health／首頁／CSS／JS，完成後停止；29 項相對連結與 anchor 通過。
- W007 Linux Python 3.14.10 曾驗證 381 passed／1 Windows-only skipped；不是本次 Linux 重跑結果。
- 沒有新增產品功能、修改核心規則或部署。

## Before Publishing — Hao Confirmation

- [ ] 審閱 README、API、此草稿與目前本機文件 Commit。
- [ ] 決定版本 metadata：Python package／ASGI app 仍為 0.1.0；本次只改文件。
  若要與 GitHub v0.2.0 完全一致，另行授權小幅版本 metadata 更新、重測、Commit，再選定最終目標。
  本次沒有發布 PyPI 套件。
- [ ] 明確授權正常 Push 最新文件／版本 Commit，確認 GitHub 內容及實際 deploy 設定。
- [ ] 再核對無重複的 v0.2.0 Tag／Release，包含帳號內未公開 Draft（本次公開 API 無法查閱），確認 Tag 指向獲准的最終 Commit。
- [ ] 另行授權建立／Push Tag、建立 GitHub Release；不覆寫 Tag、不 force push、不改歷史。

此檔不是已儲存在 GitHub 的 Draft Release，待 Hao 確認後才建立。沒有 Full Changelog 對不存在的 v0.1.0 Tag。

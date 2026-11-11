# Project Closure — CSV Validator Web v1

**Status: Completed — Maintenance Only**

結案日期：2026-11-11。正式發行版本：**v0.2.0**。
原訂開發範圍完成，不再開始新產品功能；只有 Hao 主動要求時處理 Bug、必要安全更新或主機問題。
這是開發範圍的結案，不將 GitHub repository 改為唯讀，也不停止正常運作的 Render 服務。

## 專案目的

Configurable CSV Validator & Converter 在資料匯入前，依使用者自訂 Schema 驗證 CSV、
轉換型別並輸出完整 JSON。提供 CLI 與 Web 介面，使用者可預覽資料、選欄位、設定規則及下載結果。

## 原訂里程碑

| 範圍 | 完成成果 | 狀態 |
| --- | --- | --- |
| CLI M0～M4 | 專案初始化、Schema、CSV 表頭／逐列驗證、轉型、安全 JSON、測試與 GitHub 文件 | Completed |
| W0 | FastAPI、health、上傳與統一錯誤契約 | Completed |
| W1 | 原始表頭／前五筆預覽、欄位選擇與搜尋 | Completed |
| W2 | Schema Editor／匯入匯出、完整轉換、預覽下載 | Completed |
| W3-A | 基本安全審查、上限、清理與回歸測試 | Completed |
| W3-B | Render Free 設定及公開 Demo | Completed |
| W3-C | Hao 公開環境 8/8 功能驗收 | Completed |
| W008／W009 | 求職文件、0.2.0 版本同步、正式發行與結案紀錄 | Completed |

## 最終功能與架構

- 自訂 JSON 格式 Schema；int／float／str、required／optional、空值、首錯與實體行數。
- 精確表頭、拒絕空白／重複名稱、依名稱對應欄位、保留 Schema key／CSV record 順序。
- Browser CSV 上傳、前五筆預覽、欄位勾選、規則設定、Schema 匯入／匯出。
- 全部驗證成功才提供 JSON 預覽／完整下載；CLI 拒絕覆寫既有輸出。
- Python module CLI、四個 FastAPI endpoints 與結構化錯誤，不複製第二套核心規則。

技術：Python、標準 csv／json／argparse、FastAPI／Uvicorn、原生 HTML／CSS／JavaScript、
pytest、Git／GitHub、Render。

資料流：Browser → 原生前端 → FastAPI → Web adapters → Shared Python Validation Core → 完整 JSON。
CLI 同樣呼叫 Schema／Reader／Converter／JSON encoder，再由安全 Writer 發布檔案。
詳見 [README](../README.md) 與 [API Contract](API.md)。

## 驗收證據

- W009 metadata 同步後，Windows Python 3.14.8 完整 pytest：**382 passed，9.53 秒**。
- 範例測試：2 passed；Schema／CSV／JSON、byte 等價、錯誤無輸出與不覆寫皆通過。
- CLI --help、pip check、版本 metadata 一致性、前端規則及 Git diff --check 通過；37 個相對連結／anchor 檢查通過。
- 本機 HTTP smoke：預設直接來源模式 16 項、明確本機代理模式 14 項通過；
  覆蓋三個上傳 API、health、HTML／CSS／JS、正常／異常資料、Host／Origin、清理與 CLI 等價。
- W008 已在全新 clone／venv 重現 README 指令；W007 Linux Python 3.14.10 為
  381 passed／1 Windows-only skipped。不是本次 Linux 重跑結果。
- Hao 提供公開環境 8/8 驗收：首頁、上傳預覽、欄位規則、轉換、下載、
  非法資料無部分下載、手機行動網路、Logs 無異常或敏感原文。
  Codex 未重新執行公開上傳／壓測，也未登入 Render 查閱私有 Logs。

## 公開連結與版本

- [Live Demo](https://csv-validator-uw1g.onrender.com/)（數字 1）
- [GitHub Repository](https://github.com/WJHaoooo/csv-validator)
- [GitHub Release v0.2.0](https://github.com/WJHaoooo/csv-validator/releases/tag/v0.2.0)
- [Version Tag](https://github.com/WJHaoooo/csv-validator/tree/v0.2.0)
- [Release Notes](RELEASE_NOTES_v0.2.0.md)

Python package 與 FastAPI app metadata 同步為 **0.2.0**；Tag 指向結案發布 Commit。
v0.1.0 僅為 CLI MVP 功能里程碑，未建立該 Tag／Release；本次不發佈 PyPI 套件。
GitHub 發布狀態以對應 Release／Tag 頁面為準。

## 基本安全與既知限制

CSV 5 MiB、Schema 128 KiB、JSON 8 MiB，另有 multipart／並行限制、有界讀取、
一般成功／失敗的私有暫存清理、安全錯誤、Host／Origin 檢查、安全標頭與文字渲染。
預設不信任 forwarded headers；Render 公開 HTTPS 來自部署設定。

這些是低流量匿名 Demo 的基本防護，不代表完全安全、滲透測試或正式服務 SLA。
沒有可靠的每訪客 IP 限流／硬性 CPU、RSS、轉換期限；直接來源可能只是平台代理。
kill／斷電後不保證清理或安全抹除，資料會離開本機，因此不得上傳個資或機密資料。
Free 有休眠、冷啟動、資源與用量限制。只支援 UTF-8、逗號 CSV 與三種型別；
Python 3.12／macOS 未驗證，浮點數保留一般二進位捨入限制。這些是已知邊界，不是未完成的開發任務。

## Render 現況與維護

最後由 Hao 提供／公開驗收的 Deploy Commit：**9436f21**；當時 metadata 為 0.1.0。
Auto-Deploy Off，本次未登入 Render，因此不能從 health 獨立核對實際 Deploy SHA。
相較 9436f21，本次發行只差文件與兩處版本 metadata，無 API／CSV 規則／依賴／部署架構變動。

不強制重部署或停止服務。Hao 若希望線上 metadata 也為 0.2.0，
可在現有服務 Manual Deploy → Deploy latest commit，維持原方案與環境變數；
操作與回滾見 [Render 維護指南](RENDER.md#w009-結案版本與可選-manual-deploy)。

## AI / Codex 協作

Hao 參與需求、產品規則、範圍／設計取捨與本機／公開驗收；
Codex 協助實作、測試、文件及依授權進行版本管理。
不宣稱所有程式完全獨立手寫；可說明與展示的內容見 [面試準備](INTERVIEW.md)。
不新增 Roadmap、後續開發 Task 或新階段 Prompt。

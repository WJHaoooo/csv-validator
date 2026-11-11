# 三分鐘專案介紹與面試準備

這是可練習的講稿架構，不應把未親自理解或驗證的內容說成已經掌握。
[Live Demo](https://csv-validator-uw1g.onrender.com/)／[README](../README.md)

## 0:00–0:25｜問題與成果

「這個專案是 Schema-driven CSV Validator。使用者上傳 CSV、選欄位、設定型別及必填規則，
只有全部資料驗證成功才下載 JSON。它處理的是資料進入正式系統前的品質檢查，
而不只是把逗號文字換成 JSON。現在有 CLI 與 Render 上的 Web Demo。」

## 0:25–1:05｜共用核心與責任拆分

「我把 Schema、CSV Reader、Converter、Writer 分成明確模組。CLI 負責參數和流程，
FastAPI 負責上傳及 HTTP 錯誤，兩者呼叫同一套驗證核心。
這讓 Web 不需要重寫另一套轉型規則；也能用單元測試驗證核心，用端到端測試驗證整合。
例如調換 CSV 欄位順序，程式仍依名稱取值，輸出則依 Schema 的 key 順序。」

## 1:05–1:45｜資料契約與錯誤

「Schema 是自訂 JSON 格式，不是完整 JSON Schema。支援 int、float、str，
先驗證 Schema 再處理 CSV。必填不能缺失或空白；非必填缺失或空白轉 null，
非空但型別錯誤還是拒絕。每筆 record 欄位數要符合表頭。
採 Fail Fast，錯誤提供欄位、原始值與起始實體行數，多行 CSV 不能只用索引加二。」

## 1:45–2:25｜安全與測試證據

「Web 設 CSV、Schema、輸出大小和並行上限，用私有暫存檔適配核心，一般失敗也清理。
結果全部成功才回傳，前端用文字方式顯示原始資料，避免當 HTML 執行。
我用 pytest 驗證合法、非法和故障情境，也比對 Web 下載與 CLI 的 bytes。
最新 Windows 重跑是 382 passed；這能說明涵蓋範圍，但不是零漏洞或滲透測試保證。」

## 2:25–3:00｜取捨、AI 協作與下一步

「這是低流量求職 Demo，我保留簡單原生前端，沒有先加入登入、資料庫或大型框架。
Render 會休眠，預設直接來源可能只是平台代理，也沒有可靠的每訪客 IP 限流或硬性轉換期限。
開發過程有 Codex 協助程式、測試和文件；我的參與包括需求與規則確認、設計取捨、
本機與公開驗收。下一步若要正式營運，會先根據量測補足平台資源與流量控制。」

## 三個可展示的例子

| 工程亮點 | Demo / Code 證據 |
| --- | --- |
| Modular Architecture | 同一份 examples 經 CLI 與 Web，得到等價 JSON；核心不 import FastAPI |
| Schema-Driven Validation | 匯入 Schema、改 int／required，展示非法值首錯與 optional null |
| Safe Web Integration | 非法 CSV 無部分下載；閱讀清理／大小限制測試與安全錯誤契約 |

## 面試前應能自行回答

- 為何用 csv.reader 而不是 split(",")？引號中的逗號、雙引號與換行是 record 語法。
- 為何拒絕重複表頭？直接映射 dictionary 會靜默覆蓋，導致資料遺失。
- required=false 與「錯誤可跳過」有何差別？只有缺失／空白可轉 null，非法非空資料仍失敗。
- 為何無部分 JSON？先完整驗證；CLI 另用同目錄暫存與不覆寫發布，Web 先完成有界序列化。
- 15 秒上傳期限能殺死 CPU thread 嗎？不能；不能把 async timeout 當硬性程序資源隔離。
- 為何不相信 X-Forwarded-For？沒有可信代理證據時保留直接來源，不能宣稱每個訪客都有正確 IP。
- 測試數量代表什麼？是目前平台下的案例數；還需說明內容、skip、未測版本及公開驗收來源。

## AI / Codex 協作的誠實說法

可以說：「我使用 AI 協助迭代，但需求、接受／拒絕哪些產品範圍和驗收標準需要我確認。
我會用程式碼、測試和實際操作說明結果，不宣稱所有程式碼都是完全獨立手寫。」

避免說自己獨立手寫所有模組、通過完整安全認證、具備企業級限流、已測所有 Python／OS，
或親自執行了實際由別人／工具完成的測試。未熟悉的段落先補理解，再拿來作面試亮點。

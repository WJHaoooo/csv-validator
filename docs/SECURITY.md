# Web v1 安全審查與部署前清單（W3-A）

審查日期：2026-11-09。對象：免登入、匿名上傳 CSV／Schema、下載 JSON 的 Web v1。
本階段未部署、未建立雲端資源、未 Push；W3-B 需要另外驗收。

**CSV 與 Schema 會傳至伺服器處理，不是僅在本機進行私密轉換。請勿上傳機密或敏感資料。**
程式不永久保存檔案，但處理期間會使用作業系統暫存磁碟與記憶體；不保證安全抹除。
瀏覽器也保留 File／結果 Blob，直到重傳、修改規則或離開頁面。

## 威脅模型與證據

嚴重度代表匿名公開環境的影響；「待平台驗收」不是已確認存在可利用漏洞。
測試證據主要為 tests/test_web_security.py、test_web.py、test_web_conversion.py。

| 風險 | 嚴重度 | 審查證據 | 現況／修正 |
| --- | --- | --- | --- |
| 大量／同時請求耗盡資源 | 高 | W2 未限制活躍 API，工作使用 threadpool | 已加每 worker 預設 2 個 POST API 許可，超額立即 503；平台全域速率與連線上限仍為發布阻塞 |
| CPU、RSS、處理時間、磁碟耗盡 | 高 | 5 MiB 可含大量列／欄；輸出長度不是 RSS 上限 | 有界輸入輸出、15 秒合作式上傳期限；硬性程序資源限制仍待平台 |
| multipart 放大／不完整上傳 | 高 | 已有總 body／檔數上限與 EOF completion 檢查 | 保留分塊接收，新增逾時取消／partial spool 清理測試；提高 multipart 安全版本下限 |
| 安裝舊依賴漏洞版本 | 高 | 原 python-multipart>=0.0.20 允許受公告影響版本 | 改為 >=0.0.33；當前已安裝 0.0.33 原本未命中公告，詳見 dependency-audit.json |
| 路徑穿越／資料污染 | 中 | 客戶檔名只回 basename，從不作為寫入路徑；每請求私有 TempDir | ../、Windows 路徑、HTML 檔名測試；不接受伺服器 output path，正常／失敗皆清理 |
| DOM XSS | 高影響，未確認注入漏洞 | textContent／createElement，未發現 HTML 字串 sink | 保留安全文字渲染，新增自站 CSP、nosniff、禁止 framing；Script 欄名／值測試 |
| Host／跨來源請求濫用 | 中 | W2 未限制 Host／Origin；匿名服務無帳號權限 | 精確 Host allowlist、API 同源 Origin／Fetch Metadata；無 CORS。不構成認證或速率限制 |
| 路徑／traceback／資料日誌洩漏 | 中 | Web 錯誤適配、固定日誌，不輸出 exception text | 故障注入測試；debug=False，停用 docs/OpenAPI；回應序列化例外亦經安全邊界處理，非法 Unicode Schema 回 422；平台仍須禁用 body／query 記錄 |
| 資料快取／傳輸截取 | 高影響，平台待定 | API／HTML no-store；HTTPS scope 才回 HSTS | TLS／代理 trust、強制 HTTPS、日誌與備份政策待平台；不以 localhost 測試聲稱完成 |
| 強制中止後暫存殘留 | 中 | finally 不能保證 kill／斷電後執行 | 專屬暫存目錄、磁碟配額、停機清理政策仍須平台提供 |

沒有登入／cookies／帳號異動，所以同源檢查主要降低瀏覽器跨站濫用，不是完整 CSRF 認證。
未來若加入登入，必須重新審查 CSRF／cookie 設計。無 Origin 的非瀏覽器客戶端仍允許使用。

## 已完成的資源限制

- CSV 5 MiB、Schema 128 KiB、完整 JSON 8 MiB（bytes）。
- multipart 總 body：inspect = 5 MiB + 64 KiB；schema = 128 KiB + 64 KiB；
  convert = 5 MiB + 128 KiB + 64 KiB。計算實際接收 bytes，不信任 Content-Length。
- inspect／schema 最多一個檔案，convert 最多兩個，不接受一般 form 欄位或額外檔案。
- csv.reader strict 解析，保留預設欄位長度限制（本機 131072 字元）。
  strict 不保證識別所有 CSV 變體；inspect 只解析前五筆，正式 convert 才驗證全部。
- Schema 重用既有嚴格驗證，拒絕未知屬性、重複 key、非法型別及過深 JSON。
- 每 worker 最多 2 個 POST API（含上傳、處理、回應傳送），跨三個 API 共用。
  超額在讀取 body 前回 503 SERVER_BUSY／Retry-After: 1，不建立 spool 或無界等待佇列。
  health／靜態資源不受此許可影響。
- 這不是每 IP／每秒速率限制；worker／replica 數量增加會相乘，拒絕請求本身仍有網路／CPU 成本。
- 上傳接收／multipart parsing 15 秒合作式期限，超時 408 UPLOAD_TIMEOUT 並清理 partial spool。
  只有 async checkpoint 能讓期限生效，不能中斷阻塞事件迴圈的同步解析。
- **沒有轉換硬性逾時**。run_in_threadpool 預設不 abandon worker；AnyIO 合作式取消會等待 worker。
  timeout 或取消 await 不能殺死 Python thread。外部強制 task／process 中止後的工作與清理不在此保證內，
  必須以程序／平台硬性時間與資源限制補足，見 [AnyIO 官方說明](https://anyio.readthedocs.io/en/stable/threads.html)。
- 不將 CSV 原文或原始值寫入應用日誌。JSON 僅全部成功才回傳，失敗不提供部分下載。

沒有新增資料型別或改變 Decision 001～016。

## 本機重現與設定（PowerShell）

Python 最低 3.12；實測 Windows／Python 3.14.8，其他版本／Linux／雲端尚未實測。
Web 為選用 extra，CLI 不需 FastAPI。目前版本範圍不是 lockfile；正式環境須鎖定完整依賴並重測。

~~~powershell
Set-Location C:\Hao\csv-validator
.\.venv\Scripts\python.exe -m pip install -e ".[web,dev]"
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m csv_validator.cli --help
node tests/frontend_rules.mjs
.\.venv\Scripts\python.exe scripts/audit_dependencies.py
.\.venv\Scripts\python.exe -m uvicorn csv_validator.web:app --host 127.0.0.1 --port 8002 --workers 1 --no-access-log
~~~

開啟 http://127.0.0.1:8002；Ctrl+C 停止。Node 只用於可選測試，不是服務依賴。
新 API 拒絕碼：400 INVALID_HOST、403 ORIGIN_NOT_ALLOWED、408 UPLOAD_TIMEOUT、
503 SERVER_BUSY，沿用 error.code／message。

| 環境變數（app 建立時讀取） | 預設 | 範圍 |
| --- | --- | --- |
| CSV_VALIDATOR_ALLOWED_HOSTS | localhost,127.0.0.1,::1 | 精確主機，不含協定／port／路徑，不允許 wildcard |
| CSV_VALIDATOR_MAX_ACTIVE_REQUESTS | 2 | 每 worker 1～8，未壓測前不建議調高 |
| CSV_VALIDATOR_UPLOAD_TIMEOUT_SECONDS | 15 | 大於 0、最多 60 秒，僅上傳接收 |

錯誤設定阻止啟動。正式域名必須明列；Origin 比對包含 scheme／port。
TLS 終止於代理時，ASGI scheme 須由受信任代理正確傳入，不得信任任意來源的 Forwarded 標頭。
不啟用 wildcard CORS。

安全標頭：self-only script/style/connect CSP，禁止 object/base/frame，
X-Frame-Options DENY、nosniff、Referrer-Policy no-referrer、
Permissions-Policy 禁用 camera/microphone/geolocation、CORP same-origin。
HTTPS scope 回 HSTS max-age=86400，未啟用 preload／includeSubDomains。

## 依賴公告審查

scripts/audit_dependencies.py 以標準函式庫查詢 [OSV batch API](https://google.github.io/osv.dev/post-v1-querybatch/)。
**只傳已安裝套件名稱／版本**，不傳原始碼、環境變數、CSV、Schema 或憑證。
退出碼 0 無匹配、1 有公告、2 無法完成；查詢失敗不能視為安全。
結果只是當時資料庫匹配，不涵蓋 OS／Python interpreter／尚未安裝版本，也不代表零漏洞。

2026-11-09：26 個已安裝 distributions（含開發工具），0 匹配。結果見 dependency-audit.json。
主要版本 FastAPI 0.162.2、Starlette 1.10.0、AnyIO 4.16.0、python-multipart 0.0.33、Uvicorn 0.54.0。
提高 multipart／Uvicorn 最低版本，AnyIO 明列直接依賴。
建置／測試下限另提高為 setuptools>=84.2.1、pytest>=9.2、httpx2>=2.16；
setuptools 84.2.1 另外查詢 OSV 為 0 匹配，不列入上述 26 個已安裝環境套件。

原下限 python-multipart 0.0.20 查得 7 個 GHSA（另有 PYSEC alias，不重複計數）：
5rvq-cxj2-64vf、6jv3-5f52-599m、mj87-hwqh-73pj、pp6c-gr5w-3c5g、
v9pg-7xvm-68hf、vffw-93wf-4j4q、wp53-j4wj-2cfg。
不是所有公告路徑都被本專案使用，不可全部稱為已部署可利用漏洞。
例如 [part headers DoS 公告](https://github.com/advisories/GHSA-pp6c-gr5w-3c5g) 影響 <0.0.27，
當前 0.0.33 不受此公告影響。正式部署前須再次掃描。

另查原建置／開發下限：
setuptools 68.0.0 命中 GHSA-5rjg-fvgr-3xxf、cx63-2mw6-8hw5、
h35f-9h28-mq5c、xmj3-9gf7-h52w；
pytest 8.0.0 命中 GHSA-6w46-j5rx-g56g；
httpx2 2.0.0 命中 GHSA-8xx6-hgc6-gc2m、h4x7-gw46-3wm6、pf96-p4fj-6566。
這些是原允許範圍的安全問題，不代表目前 Web 執行路徑皆可利用。
修復版本、公告摘要與查詢時點記於 dependency-audit.json 的 minimum_version_review。

## W3-B 公開發布阻塞清單

**目前不建議直接公開服務**；以下尚未實作或實測：

- [ ] 入口／代理限制 body（容納合法 convert multipart）、HTTP headers、連線數、
  上傳／閒置／總請求期限，不能先將任意大 body 緩存至無界磁碟。
- [ ] 全域／每來源速率及突發限制，測試 429／Retry-After、代理 IP 信任及跨 worker 效果。
- [ ] 選定 worker／replica 數量；程序 CPU／RSS／wall-clock 上限、專屬暫存磁碟配額、
  response timeout、超限 worker 終止重啟；在隔離環境量測。
  Uvicorn keep-alive timeout 不是轉換期限。
- [ ] HTTPS／HTTP redirect、正式 Host allowlist、僅信任指定代理；實測 Host／Origin／CSP／HSTS，
  不用 reload／debug。
- [ ] 實際部署平台與 Python 版本全新安裝，鎖定 transitive dependencies、重新測試／掃描。
- [ ] 低權限服務帳號、應用程式碼唯讀、專屬暫存位置、檔案權限與中斷清理政策。
- [ ] 監控 4xx／5xx／503／408、CPU／RSS／磁碟、告警、復原與停用演練。
- [ ] 平台禁記 multipart body、CSV／Schema 原文、原始值、敏感 query、traceback；
  設定日誌權限、保留期限、備份與使用者資料告知。

本機應用內部錯誤日誌為固定 Unexpected CSV web request failure.，不含 exception text 或 CSV 原文。
正式平台以受限日誌查詢 status／時間／錯誤 code；不要為排錯加入 body dump／exc_info。
保留必要聚合診斷，避免可用性事故只剩無上下文訊息。

停用：先關閉公開路由／平台服務，停止新請求，等待有界 drain；
超過平台硬性期限則終止 worker，確認無工作程序後只清理此服務專屬暫存，
不得刪除其他服務／使用者檔案。檢查 5xx／資源告警後才重啟。
以上平台操作只是待執行清單，本次沒有對外部署或公共服務壓力測試。

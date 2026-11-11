# Render Web v1 部署與運維指南

更新：2026-11-11。對象為低流量、非正式營運、學習／求職展示的匿名公開 Demo。
本文件取代 W3-B／W006「一定要提供可信 Proxy IP 才能啟動」的指示。
Web v1 已由 Hao 部署至 [Live Demo](https://csv-validator-uw1g.onrender.com/)，公開驗收程式碼為 9436f21。
Hao 回報八項公開驗收通過，包含手機與 Logs；W008 僅整理文件，沒有重新部署或變更方案。

**CSV／Schema 會傳至伺服器，不是只在本機私密轉換；不要上傳敏感或機密資料。**

## 1. 最終設定

| Render 欄位 | 值 |
| --- | --- |
| Repository / Branch | WJHaoooo/csv-validator / main，核對本次修正已推送 |
| Type / Language | Web Service / Python 3，非 Static Site |
| Root Directory | 留空，repository root |
| Python | .python-version 固定 3.14.10 |
| Build Command | bash scripts/render-build.sh |
| Start Command | python scripts/start_render.py |
| Health Check Path | /health |
| Instance Type / Count | Free / 1 |
| Auto-Deploy | Off，初期手動部署 |
| Database / Disk | 不建立 |

Build 固定 pip==26.2.1、隔離建置 setuptools==84.2.1，依 requirements/render.txt 安裝 .[web]，
再執行 pip check。不安裝 dev extra、pytest、httpx2、Node 或驗證工具。
15 個 runtime 依賴採精確版本約束，但不是帶 hashes 的完整供應鏈 lock；更新時須重測、重掃。

啟動為 Uvicorn 單 worker，使用 0.0.0.0／PORT，沒有 reload。
見 [Render Web Services](https://render.com/docs/web-services)、
[Python 設定](https://render.com/docs/python-version)、
[Blueprint](https://render.com/docs/blueprint-spec)。
PYTHON_VERSION 若曾於 Dashboard 設定，會優先於檔案；須移除或同樣設為 3.14.10。

## 2. Proxy／HTTPS 的最小安全修正

### 預設：不設定可信代理（建議首次 Demo 使用）

CSV_VALIDATOR_TRUSTED_PROXY_IPS 未設定或空值時：
- Uvicorn proxy_headers=False，forwarded_allow_ips=""，覆寫 Render 環境的廣泛信任預設。
- 不採信 X-Forwarded-For、X-Forwarded-Proto、X-Forwarded-Host、Forwarded 或轉送 port。
- ASGI client 保留直接 TCP 來源；ASGI scheme 保留內部實際連線協定，不由請求標頭改寫。
- Render 平台自動提供 RENDER=true 和精確 RENDER_EXTERNAL_HOSTNAME；啟動器驗證 hostname，
  以部署設定將公開 scheme 固定為 https，傳給安全層做 Origin 比對與 HSTS。
  這是伺服器設定，不是從上傳、Origin、Host 或 X-Forwarded-* 接受的宣告。
- Host 仍須精確符合 allowlist，Origin 須符合 https + 實際 Host + port；
  不因此放行其他網域、HTTP Origin 或 wildcard。
- 非 Render 的本機啟動不固定公開 scheme，正常使用內部 HTTP；不要自行設定 RENDER=true 作一般本機開發。

依據是 Render 公開文件明確說明：入口將公開 HTTP redirect 至 HTTPS，
由 load balancer 終止 TLS，再以 HTTP 傳入 app；app port 不直接公開。
所以不必為判斷公開 HTTPS 而信任客戶端可偽造的協定標頭。
這項平台假設必須在首次實際部署驗證；其他主機／平台不能直接套用。
來源：[Render 入口／TLS](https://render.com/docs/web-services)、
[平台環境變數](https://render.com/docs/environment-variables)。

CSV_VALIDATOR_PUBLIC_SCHEME 是 launcher 傳給安全層的內部設定，不必在 Dashboard 填；
只支援 https 或未設定，不會改寫 client／transport，也不代表內部 socket 已加密。
目前 UI 使用相對 URL，不靠轉送標頭產生公開下載 URL。未來若新增絕對 URL 或其他代理平台，須另行審查。

**限制：直接來源可能全部是平台代理，不能可靠實現每位使用者的獨立 IP 限流。**
未設定 Origin 的非瀏覽器請求仍可使用 API，這不代表可信；本專案沒有宣稱具備 IP 限流或認證。

### 選用：已確認的明確可信代理

只有取得官方文件／支援對實際 ingress 來源及 header 清洗規則的證據時，才設定
CSV_VALIDATOR_TRUSTED_PROXY_IPS。使用逗號分隔的窄 IP／CIDR；
拒絕 *、0.0.0.0/0、::/0、合併後涵蓋全網的 CIDR 清單、非 IP 名稱及非法值，設定錯誤會停止啟動。
程式只能驗證格式，無法證明填入值本身可信。
不得用 Outbound IP、DNS 解析或單次觀察到的 IP 猜測來源，也不要把本機測試 127.0.0.1 搬到 Render。
此模式才啟用 Uvicorn proxy headers；Forwarded 不是額外授權的信任來源。
參見 [Uvicorn proxy 說明](https://uvicorn.dev/deployment/)。

## 3. 環境變數：哪些需手動填

| 變數 | 必填／來源 | 安全設定 |
| --- | --- | --- |
| PORT | Render 自動提供 | 不自行寫死 |
| RENDER | Render 自動提供 true | 不由客戶端控制，不手動偽造 |
| RENDER_EXTERNAL_HOSTNAME | Render 自動提供 | 使用實際 onrender.com hostname |
| CSV_VALIDATOR_ALLOWED_HOSTS | 通常不用填 | 預設精確取平台 hostname；自訂網域時填所有有效主機，逗號分隔，無 scheme／port／path／wildcard |
| CSV_VALIDATOR_TRUSTED_PROXY_IPS | **非必填，首次建議不設** | 刪除舊的猜測／placeholder；沒有證據就留空 |
| CSV_VALIDATOR_MAX_ACTIVE_REQUESTS | 建議 2；程式預設 2 | 保持單 worker／低並行 |
| CSV_VALIDATOR_UPLOAD_TIMEOUT_SECONDS | 建議 15；程式預設 15 | 合作式上傳期限，非轉換硬性期限 |
| PYTHONDONTWRITEBYTECODE | 建議 1 | render.yaml 已列 |
| PYTHONUNBUFFERED | 建議 1 | render.yaml 已列 |
| PYTHON_VERSION | 不必填 | 若有，須與 .python-version 一致 |

沒有必填的使用者秘密或 Proxy IP。render.yaml 移除原本 sync:false 的代理變數要求。
Render health check 的 Host 可能是已驗證自訂網域，新增網域須同步更新 allowlist，
不可為了 health 通過而關閉 Host 檢查。見 [Health Checks](https://render.com/docs/health-checks)。

## 4. 保留的基本防護與 Demo 風險

保留 CSV 5 MiB、Schema 128 KiB、JSON 8 MiB、multipart 總長／檔數限制、有界讀取、
Fail Fast、完整成功才下載、安全 JSON 錯誤、文字 DOM 渲染、精確 Host／Origin、安全標頭與自動暫存清理。
API 活躍上限 2；Uvicorn limit_concurrency=8、backlog=16，無等待中的無界轉換佇列。
安全標頭包含 CSP、nosniff、禁止 framing、no-store；沒有額外開 CORS。

本次定位允許 Hao 開始首次 Free Demo 驗證，不再把所有企業級平台防護視為永久啟動門檻；
以下仍是**未解決的殘餘風險**，不是已完成防護：

- 無每使用者 IP 限流／全域速率限制；匿名流量可能造成 503、服務不可用或用量耗盡。
  Render 的 DDoS／inbound 防護不等於本 app 已驗證的精確限流；管理 REST API 限流也不保護 CSV API。
- 15 秒只限制合作式上傳接收，不能中斷同步解析／CPU 轉換 thread；
  keep-alive 5 秒、graceful shutdown 20 秒都不是單請求硬性執行期限。
- 沒有本 app 保證的硬性 CPU／RSS／處理時間／暫存磁碟配額。
  方案資源上限、超限重啟行為與監控須於 Render 實際確認，不承諾抗 DoS 或 production SLA。
- 一般成功／失敗關閉 spool、刪除私有暫存副本，不永久儲存資料；kill／斷電不保證 finally 或安全抹除。
- 不記錄 CSV／Schema 原文、原始值或 exception traceback；Uvicorn access log 關閉。
  平台日誌留存／備份不是程式能全面保證，勿用 body dump 排錯。
- 只適合虛構、非敏感示範資料；沒有登入、歷史紀錄、資料庫、disk 或敏感資料處理保證。
- Linux 本機通過不等於 Render 的實際 TLS／網路／檔案系統已驗收，也不是滲透測試。

若觀察異常大量請求、資源耗盡、超額費用風險或資料外洩疑慮，先 Suspend Demo，
再評估平台防護／調整方案，不為了維持上線而放寬檢查。

## 5. Hao 在 Dashboard 的完整操作順序

目前服務已存在，**不用為文件收尾重複建立服務**。第 1～5 步保留給未來另建服務時參考，
現有服務的 Logs、驗收、重部署與停用見第 6～10 步；這些動作由 Hao 親自操作。

1. 登入 Render，確認 GitHub 授權只涵蓋需要的 csv-validator。
2. New → Web Service → Git Provider，選 WJHaoooo/csv-validator；
   branch main，核對含本次修正的 commit，Language Python 3，Root Directory 留空。
3. 填第 1 節 Build／Start，Free、單 instance，Auto-Deploy Off；不要新增 DB／disk 或付費選項。
4. Advanced → Health Check Path 填 /health；按第 3 節核對環境變數。
   **不要填 Proxy IP，不需要設定 FORWARDED_ALLOW_IPS，也不用手填 PUBLIC_SCHEME。**
5. 查看 Workspace Billing／付款方式／用量與通知；確認 Free 與可接受的剩餘額度。
   Hao 決定開始首次 Demo 後才按 Create Web Service；這一步會公開部署，
   auto-deploy off 也不會阻止首次部署。套用 Blueprint 亦同，不是 dry run。
6. Deploys／Events 選本次 deploy 看 Build／Deploy Logs；確認 Python 3.14.10、
   pip check、服務監聽與 /health 成功。Runtime Logs 在 Logs 頁。
7. 用實際 HTTPS 網址驗收：首頁、CSS／JS、上傳 examples/valid.csv、匯入 examples/schema.json、
   轉換及下載等價 expected.json；invalid.csv 應清楚報錯且無部分下載。
   看瀏覽器 Network 的 HTTPS、CSP／HSTS／no-store、API status，確認 health／Host／Origin 正常。
   不拿真實敏感資料測試，也不對公開服務壓測。
8. 修改後重部署：先確認獲准修改已 Push，再到 Manual Deploy → Deploy latest commit。
   Clear build cache & deploy 僅在快取造成問題時使用；都會消耗 build 用量。
9. 回滾：Deploys 找保留的成功部署 → Rollback → 核對版本後確認。
   Free 可回滾版本數有限；沒有成功 deploy 時先 Suspend 排錯。Rollback 後重查 health／設定，
   不假設所有平台設定一併還原。見 [Rollbacks](https://render.com/docs/rollbacks)。
10. 暫停／停止：服務 Settings／操作選單 → Suspend Web Service／Suspend，
    核對服務後確認；關閉 auto-deploy／取消 build 不會停止舊服務。
    永久刪除用 Delete Web Service／Delete，確認不可逆影響與其他資源費用；不刪 GitHub repo。
    未觀察實際帳號 UI，若標籤改版，核對對應功能再操作。

## 6. Free 限制與費用

Free 適合此學習 Demo，不適合正式營運：閒置 15 分鐘會休眠，冷啟動約一分鐘，
重啟／重部署／休眠丟失本機檔案；每 workspace 每月共用 750 Free instance hours。
另有 outbound bandwidth 與 build pipeline 用量；綁付款方式後超額可能計費。
pipeline spend limit 不是全部費用的硬上限。定期看 Billing、方案、付款方式、用量及通知，
不要用自動 ping 規避休眠；不承諾選 Free 就永遠零費用。
來源：[Free](https://render.com/docs/free)、[FAQ](https://render.com/docs/faq)、
[Billing](https://render.com/docs/render-dashboard)、[Build pipeline](https://render.com/docs/build-pipeline)。

## 7. 常見失敗與排查

| 現象 | 檢查 |
| --- | --- |
| Build 找不到檔案／安裝失敗 | root 是否 repository root、commit 是否最新、Build command、Python 與依賴約束；看第一個 build error |
| Port scan／502 | Start command、PORT、0.0.0.0、啟動日誌；沒有 PORT 會拒絕啟動 |
| Proxy configuration error | 是否殘留 *／placeholder／非法 CIDR；預設應刪除該選用設定 |
| Host 400／health 失敗 | RENDER_EXTERNAL_HOSTNAME、實際網址、自訂網域 allowlist，不加 wildcard |
| Origin 403 | HTTPS 網址、精確 Host／port、RENDER=true 及 launcher；不用開放 CORS 或偽造 X-Forwarded-Proto 修復 |
| 413 | CSV／Schema／JSON 或 multipart 上限；不在 Demo 任意調高 |
| 408／503／啟動慢 | 上傳期限／並行已滿／Free 冷啟動；觀察 Logs／Metrics，不假設資料驗證錯誤 |
| 內部 500／OOM／異常重啟 | 先 Suspend；檢查固定錯誤日誌、記憶體／磁碟／用量，不印上傳原文 |

[官方排錯](https://render.com/docs/troubleshooting-deploys)、
[Logs](https://render.com/docs/logging)。沒有取得帳號資料，真實帳號費用與防護設定仍由 Hao 核對。

## 8. 本機可重現驗證

Windows PowerShell：
~~~powershell
Set-Location C:\Hao\csv-validator
.\.venv\Scripts\python.exe -m pip install -c requirements/render.txt -e ".[web,dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m csv_validator.cli --help
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/smoke_web.py
.\.venv\Scripts\python.exe scripts/smoke_web.py --trusted-proxy
~~~

本機 smoke 只使用 loopback 與虛構資料，模擬 Render 的部署環境；
預設不提供 Proxy IP，測試缺少／偽造轉送標頭；選用模式只用本機可信代理，不是 Render IP 建議。
兩種模式都會停止本機服務並檢查暫存清理，不呼叫 Render。

Linux 隔離副本，先備妥 Python 3.14.10：
~~~bash
python3.14 -m venv .venv-render
source .venv-render/bin/activate
bash scripts/render-build.sh
python -m csv_validator.cli --help
python scripts/smoke_web.py
python scripts/smoke_web.py --trusted-proxy
python scripts/audit_dependencies.py
~~~

另建 .venv-test 安裝 .[web,dev] 後跑 pytest，不將 dev 混入 production。
本機結果與日期見 [README](../README.md)。Hao 已完成公開環境八項功能驗收；
本次僅獨立 GET 確認公開首頁及 /health 為 200，沒有重跑公開上傳、查閱私有 Logs 或變更帳務。
未來每次改版仍須核對實際 Render 建置、TLS、Host／Origin、用量、日誌與費用。

## W009 結案版本與可選 Manual Deploy

正式發行為 v0.2.0，package／FastAPI metadata 為 0.2.0。
最後由 Hao 提供／公開驗收的 Render Commit 為 9436f21，當時 metadata 為 0.1.0；
未登入 Render，不能從 /health 獨立查得 Deploy SHA，請以 Dashboard → Deploys 顯示為準。

Auto-Deploy Off。本次最終版與 9436f21 僅差 README／文件及兩處版本 metadata，
沒有變更 CSV 規則、API 契約、執行依賴、啟動或部署架構，所以不必為結案重部署；
目前服務不應停止。

若 Hao 希望線上 metadata 也為 0.2.0：
1. Dashboard 選現有 csv-validator Web Service，不建立新服務。
2. Deploys 核對目前 SHA；Manual Deploy → Deploy latest commit，確認 main 的 v0.2.0 發布 Commit。
3. 保持既有 Free、Auto-Deploy Off、環境變數與方案，正常部署會消耗 build 用量。
4. 查看 Build／Deploy Logs、/health 與基本 Web 流程；失敗時依前述 rollback／Suspend 流程處理。

此操作為選用，由 Hao 自行決定；本次未執行，也未變更方案、環境變數或費用設定。

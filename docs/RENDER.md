# Render 部署準備與 Hao 操作指南（W3-B）

日期：2026-11-09。此文件與 render.yaml 是**部署草稿，不是已上線服務**。
本次沒有 Push、登入 Render、建立服務、付費資源、網域或公開端點。

**先讀發布阻塞清單。不要按 Create Web Service／Apply Blueprint 來測試設定。**
Render Web Service 建立後會公開接收網路流量；關閉 auto-deploy 也不會阻止首次部署。
目前沒有滿足全部公開服務安全條件。

## 1. 實際專案設定

| Render 欄位 | 值 |
| --- | --- |
| Repository | https://github.com/WJHaoooo/csv-validator |
| Service type / Runtime | Web Service / Python 3（Linux native runtime） |
| Branch / Root Directory | main / 留空，使用 repository root |
| Python | .python-version：3.14.10；不依賴 Render 隨時間改變的預設 |
| Build Command | bash scripts/render-build.sh |
| Start Command | python scripts/start_render.py |
| Health Check Path | /health |
| Instance Type / Count | Free / 1（僅初期評估目標，不是正式服務安全背書） |
| Auto-Deploy | Off |
| Persistent Disk / Database | 不建立 |

Render 要求監聽 0.0.0.0 與 PORT；啟動腳本使用 PORT（平台預設 10000），只開一個 Uvicorn worker，
沒有 reload，也不受 WEB_CONCURRENCY 自動放大。
參見 [Web Services](https://render.com/docs/web-services)、[Python version](https://render.com/docs/python-version)、
[Blueprint 規格](https://render.com/docs/blueprint-spec)。

Build 實際順序：
1. 安裝 pip==26.2.1，以固定支援 build constraints 的 installer。
2. 以 requirements/build.txt 固定隔離建置的 setuptools==84.2.1。
3. 以 requirements/render.txt 固定 15 個 Web runtime 依賴版本，再安裝非 editable 的 .[web]。
4. pip check。正式環境不安裝 .[dev]、pytest、httpx2、Node 或 Linux 驗證工具。

這是精確版本約束，不是含 artifact hashes 的供應鏈 lock；升版須重跑 Linux 安裝／測試與公告掃描。
專案仍宣告 Python>=3.12；本次未驗證 3.12。PYTHON_VERSION 環境變數會優先於 .python-version，
若曾設定，須移除或設為同樣 3.14.10，不能無意使用不同版本。

## 2. 環境變數與代理信任

| 變數 | 設定／預期值 |
| --- | --- |
| PORT | Render 提供，不自行寫死 |
| RENDER_EXTERNAL_HOSTNAME | Render 提供，例如 csv-validator-abcd.onrender.com；這只是示例 |
| CSV_VALIDATOR_ALLOWED_HOSTS | 可省略，launcher 從上述 hostname 建立單一精確 allowlist；自訂網域時明列所有有效主機，逗號分隔 |
| CSV_VALIDATOR_TRUSTED_PROXY_IPS | **必填、尚待確認**：平台驗證過的實際 ingress IP／CIDR，逗號分隔 |
| CSV_VALIDATOR_MAX_ACTIVE_REQUESTS | 2，每 worker 活躍 POST API 上限 |
| CSV_VALIDATOR_UPLOAD_TIMEOUT_SECONDS | 15，只限制合作式上傳接收 |
| PYTHONDONTWRITEBYTECODE | 1 |
| PYTHONUNBUFFERED | 1 |

Host 值不可含 scheme、port、路徑或 wildcard。不猜測 onrender.com 子網域；使用平台實際指派值。
Render 的 HTTP health check 使用自訂網域（若有），否則使用 onrender.com hostname，
所以新增自訂網域時必須同步更新 allowlist，不能靠免檢查 health 來繞過。
見 [health checks](https://render.com/docs/health-checks)。

**Proxy trust 目前仍為發布阻塞：**

- Render 文件列出 Python 預設 FORWARDED_ALLOW_IPS=*；本專案不沿用這個廣泛信任值。
- launcher 僅接受 CSV_VALIDATOR_TRUSTED_PROXY_IPS 的明確 IP／CIDR，拒絕空值、*、0.0.0.0/0、::/0；
  把窄化後的值明確傳給 Uvicorn，並覆寫繼承的 FORWARDED_ALLOW_IPS。
- 缺值時會退出 2，**不開監聽 socket**。render.yaml 使用 sync:false 要求操作人填入，不提供臆測範圍。
- 必須向 Render 確認實際入口來源、是否有直接／內網繞過路徑、是否覆寫不可信 X-Forwarded-*，
  以及入口 IP／CIDR 的穩定性和變更方式；不能從某次 client IP 推定整個可信範圍。
- 若平台無法提供可驗證的窄範圍／等效信任邊界，需集中做安全方案決策，不能改成 * 只為讓表單通過。
- 本機驗收的 127.0.0.1/32 是本機模擬代理，**不可直接當成 Render ingress 設定**。
- 無 Origin 的 CLI／直接客戶端仍可呼叫 API，這不表示請求可信。Origin／Fetch Metadata／CORS 都不是認證或限流。

Render 在 load balancer 終止 TLS 並對公開 HTTP redirect；app 必須從受信任代理取得正確 HTTPS scheme，
才能正確執行同源檢查並發 HSTS。沒有開放 CORS、沒有信任 X-Forwarded-Host 更改 Host。
來源：[Render 預設環境變數](https://render.com/docs/environment-variables)、
[Uvicorn proxy trust](https://uvicorn.dev/deployment/)。

## 3. 已完成與尚未完成的安全條件

已完成：
- 既有 CSV 5 MiB／Schema 128 KiB／JSON 8 MiB，分塊讀取、multipart 總長／檔數限制、Fail Fast。
- 每 worker 活躍 API 2；Uvicorn 額外以 limit_concurrency=8 限制連線／task，backlog=16。
  此數字是保守起點，會影響連線重用與可用性，不是每來源速率限制或全域安全保證。
- keep-alive 5 秒、graceful shutdown 20 秒；兩者**都不是轉換硬性執行期限**。
- 精確 Host、同源檢查、安全文字渲染、CSP／nosniff／framing／no-store；不顯示 traceback／內部路徑。
- 每請求私有暫存路徑，不使用客戶檔名寫入，不接受伺服器 output path；一般成功／失敗清理。
- 不永久保存上傳或結果；沒有資料庫／persistent disk。kill／斷電後不保證執行 finally 或安全抹除。
- 應用程式不主動記錄 CSV／Schema 原文；Uvicorn access log 關閉，內部錯誤僅固定訊息。
  平台自己的日誌、留存及備份仍需另外確認，不能由程式宣稱全部不留資料。
- 首頁明確告知資料傳至伺服器，勿上傳機密／敏感資料。

**公開部署阻塞（目前未解除）：**

| 項目 | 目前證據／欠缺 |
| --- | --- |
| Ingress proxy trust | 沒有取得選定服務的已驗證代理範圍與 header 清洗／不可繞過證據 |
| 匿名公開限流 | Render 有 DDoS／inbound 限制，但公開文件不足以驗證本服務每來源速率／突發額度、大小／header／慢上傳限制；REST API rate limits 不保護本 CSV API |
| CPU／RSS／磁碟／處理時間 | 尚未確認選定 Free 方案的可用額度、硬性配額／超限行為／單請求 wall-clock 終止機制；軟性 timeout 不能殺死 Python thread |
| 實際平台驗收 | WSL Linux 不等於 Render image／網路；尚無 Render build、TLS／host／health／瀏覽器／資源量測結果 |
| 運維與費用 | 日誌權限／留存、監控告警、停用／復原、支出限制尚未在真實帳號設定 |

Render [故障排除](https://render.com/docs/troubleshooting-deploys) 提及 ingress 429；
這不是本應用已驗證且可配置的公平限流 SLA。不能把 Render [管理 REST API 限流](https://api-docs.render.com/reference/rate-limiting)
當成上傳服務的防護。若選定方案無必要能力，須調整部署安全方案或保持不公開；本次沒有代為選付費方案。

## 4. Hao 操作順序（先準備，解除阻塞前不建立）

1. 開啟 [Render Dashboard](https://dashboard.render.com/)，自行登入／註冊；不提供密碼或 Token 給 Codex。
2. 在 Render 連接 GitHub，僅授權需要的 csv-validator repository；確認擁有者為 WJHaoooo。
3. 檢查本機 Git 與 origin/main；本機 Commit 不會自動同步至 GitHub。
   確認 GitHub 已包含獲准推送的設定版本，再準備平台表單。
4. 日後獲准建立時，選 New → Web Service → Git Provider，選 csv-validator、main、Python 3。
   不是 Static Site。依第 1 節填 Build／Start／Health；Root Directory 留空。
5. 選 Free、單 instance；不勾選資料庫、磁碟或付費升級。Auto-Deploy 設 Off。
6. 依第 2 節準備環境變數，確認 Python 3.14.10；proxy trust 未確認就停止，不以 wildcard 替代。
7. **到此先停。** Create Web Service／Blueprint Apply 會觸發首次公開部署；
   只有發布阻塞解除、費用與安全條件經 Hao 確認後，才進行該步驟。
8. 日後部署時，在 Deploys／Events 選對應 deploy 看 Build／Deploy Logs，
   核對 commit、Python、pip check、啟動成功；Runtime Logs 在 Logs 頁查看。
   不以打印 body／完整 Schema 排查故障。見 [Render logging](https://render.com/docs/logging)。
9. 部署後以虛構 examples 驗收 health／三個 API／靜態檔、TLS／安全標頭、Host／Origin、
   413／503／失敗無下載／暫存清理；本機 smoke 不是遠端驗收。
   scripts/smoke_web.py **只啟動本機**，不會對 Render 做負載測試。
10. Workspace → Billing 檢查 Free hours、outbound bandwidth、pipeline minutes、
    付款方式、預估費用／通知；pipeline spend limit 不能當作全部費用的硬性上限。
11. 停用時到服務 Settings／服務操作選單找 Suspend Web Service／Suspend，
    核對服務名稱再確認。這才是停止服務；取消 deploy／關閉 auto-deploy 不會停止現有服務。
    要永久移除則用服務 Settings 的 Delete Web Service／Delete，核對名稱及不可逆影響；
    本專案無資料庫／disk，仍需檢查帳號有無其他資源產生費用。不要刪除 GitHub repo。
12. 回滾：Deploys 選保留中的成功 deploy → Rollback → 核對目標版本再確認。
    之後重新檢查 health／安全設定；Dashboard rollback 會關閉 auto-deploy，
    但不能假設平台版本／所有設定都回到過去。沒有成功 deploy 時無法 rollback，先 Suspend 排障。
    見 [官方 rollback 文件](https://render.com/docs/rollbacks)。

本次只查詢公開文件，沒有登入帳號檢查即時 Dashboard；按鈕名稱若改版，依實際服務的同名功能核對。
使用 [Blueprint](https://render.com/docs/blueprint-spec) 也必須先審閱資源／費用，不能把 YAML 當成 dry run。

## 5. Free 服務與資料保護注意事項

依 [Render Free 文件](https://render.com/docs/free)／[FAQ](https://render.com/docs/faq)：
Free 閒置 15 分鐘會休眠，下一次請求冷啟動約一分鐘；重啟／重部署／休眠會丟失本機檔案。
每 workspace 每月共用 750 Free instance hours；另有 outbound bandwidth／build pipeline 用量。
已綁付款方式時超額仍可能計費，不能因選 Free 就宣稱零費用；pipeline 可設定 spend limit，
其他費用項目仍需 Billing 確認。不要用自動 ping 規避休眠或製造額外流量。
Free 不適合作為本專案已完成防護的正式 production；不建立 persistent disk 來保存使用者上傳。

參見 [Dashboard/Billing](https://render.com/docs/render-dashboard)、
[Build pipeline 費用限制](https://render.com/docs/build-pipeline)。

## 6. 本機重現與本次證據

Windows PowerShell：

~~~powershell
Set-Location C:\Hao\csv-validator
.\.venv\Scripts\python.exe -m pip install -c requirements/render.txt -e ".[web,dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m csv_validator.cli --help
.\.venv\Scripts\python.exe scripts/smoke_web.py
.\.venv\Scripts\python.exe scripts/audit_dependencies.py
~~~

Linux 隔離副本（先備妥 Python 3.14.10 與 venv，不修改系統 Python）：

~~~bash
python3.14 -m venv .venv-render
source .venv-render/bin/activate
bash scripts/render-build.sh
python -m csv_validator.cli --help
python scripts/smoke_web.py
python scripts/audit_dependencies.py
~~~

測試使用另一個 venv，才不會把 dev 依賴混進 production：

~~~bash
python3.14 -m venv .venv-test
source .venv-test/bin/activate
python -m pip install pip==26.2.1
python -m pip install --build-constraint requirements/build.txt -c requirements/render.txt ".[web,dev]" pytest==9.2.0 httpx2==2.16.0
python -m pytest -q
python -m pip check
~~~

本次執行結果：
- W3-A baseline：356 passed，8.33 秒；Commit 496ad25。
- Windows／Python 3.14.8：374 passed，8.78 秒；pip check／CLI help 通過。
- WSL Ubuntu／x86_64／由 uv 0.13.7 取得的獨立 CPython 3.14.10：373 passed、1 skipped，3.41 秒。
  skip 為 Windows 大小寫路徑專屬測試，不是功能失敗。
- 實際 Linux production build 安裝非 editable wheel，確認無 pytest／httpx2，
  從 site-packages 載入，靜態資源隨套件安裝正確。
- Windows／Linux production 的本機 smoke 均 14 項通過：
  health、HTML／CSS／兩個 JS、三個 API、CLI bytes 等價、非法資料無下載、
  Host／Origin、multipart、安全標頭、暫存清理與停止／日誌。
- [Linux production OSV 快照](dependency-audit-render.json)：17 個 distributions，0 匹配；
  僅傳套件名稱／版本，不傳使用者資料。build backend 84.2.1 已於 W3-A 另查。
  不代表通過滲透測試、沒有未知漏洞，或其他日期／平台皆安全。
- Render 實際 Build／Deploy／TLS／代理來源／資源及安全限流：**尚未驗證**。
- render.yaml 以隔離工具對照 [Render 官方 JSON Schema](https://render.com/schema/render.yaml.json) 驗證結構通過；
  PyYAML／jsonschema 僅在隔離驗證工具環境，未加入專案／production 依賴。
  未用 Render API／Dashboard 驗證、建立或套用 Blueprint。

目前完成的是可重現的部署準備。是否能正式建立公開 Web Service，仍取決於第 3 節阻塞清單。

## 7. W006 結案重驗（2026-11-11）

- 工作目錄為原 W3-B 13 個檔案，未發現不相關變更。
- Windows Python 3.14.8：374 passed（13.94 秒）；Linux Python 3.14.10：373 passed、1 skipped（4.90 秒）。
  skip 仍為 Windows 路徑大小寫測試。兩個環境 smoke 均 14 項通過，pip check 通過，程序已停止。
- 前端規則測試通過；Blueprint 再次對照官方 JSON Schema 驗證通過。
- 重新查詢 OSV：Windows 26、Linux production 17 個 distributions，均 0 匹配；不代表零漏洞。
- 46 個追蹤／候選檔案與 67 個既有歷史 blobs 的常見秘密特徵掃描無匹配，
  沒有 Agent／雲端授權設定、環境檔、快取或手動資料進入追蹤候選範圍；模式掃描不取代人工審查。
- 本機提交名稱為 chore: prepare render deployment；實際 Commit／Push 狀態見 Git。
- 沒有登入 Render、建立服務或降低安全設定。第 3 節公開部署阻塞全部保留。

### 設定 TRUSTED_PROXY_IPS 前需要的可信證據

以下須來自 Render 官方文件、對應服務的可驗證設定或官方支援確認，並保留確認日期與適用範圍：

1. 該服務／region／方案實際 ingress 到 app 的來源 IP 或 CIDR，包含健康檢查路徑；
   確認範圍是可信入口，不是一般共享內網或其他工作負載可自行連入的來源。
2. 公開 HTTP／HTTPS、其他網路入口與內部存取的路由邊界，是否可能繞過受控代理直接連入 app。
3. 對客戶端自帶 X-Forwarded-Proto／X-Forwarded-For 的覆寫或安全鏈結規則，
   TLS 終止方式與傳入 app 的 scheme，不能讓客戶端任意宣稱協定／來源。
4. 來源範圍的穩定性、變更通知與更新方式，及重新驗證 Host／Origin／HSTS／偽造標頭的紀錄。

Outbound IP 清單、網域 DNS 解析結果、單次觀察到的 IP、隨機私有網段，以及本機 127.0.0.1，
都不能單獨作為 Render ingress 信任證據。程式只能檢查設定格式，不能證明填入的 IP 值值得信任。
若拿不到上述證據，保持未設定／停止啟動，集中討論等效信任邊界，不改用 wildcard。

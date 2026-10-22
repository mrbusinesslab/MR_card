# 小如如的秘書：共用主機、獨立資料

## 已確認

- LINE OA：`@345lcfso`；Messaging API Channel ID：`2012149818`。
- 客戶空間：`xiaoruru`；顯示名稱：小如如的秘書。
- 使用新的 Google 日曆；不匯入現有 MR 行程、待辦、使用者或邀請碼。
- 沿用現有 Render MR 服務，不新增第二台主機。新 LINE 的路由固定為 `/clients/xiaoruru/`，原 MR 路由保留。
- 設定檔：`clients/xiaoruru.json`，預設停用。Channel ID 只是識別資料，不能代替 token 或 secret。
- 此分支整合正式版的最新行程補資料、名稱修改與清單確認流程；MR 模式保留原圖文選單啟動。

## 尚待取得與設定

1. 新建「小如如 Life OS」Google 日曆，確認時區為 Asia/Taipei，記錄 calendar ID；將該日曆共享給服務帳號並授予變更活動權限。若小如如需要 Google／手機查看，另共享給她的 Google 帳號。
2. 新 Channel 的 Channel secret 和 Channel access token，僅填入現有 MR 服務的私密環境變數 `CLIENT_XIAORURU_LINE_CHANNEL_SECRET`、`CLIENT_XIAORURU_LINE_CHANNEL_ACCESS_TOKEN`，勿覆蓋原本 MR 的同類變數，亦勿提交至 Git 或貼在交付文件中。
3. 小如如在新 Provider 下的 LINE user ID。不得假設與舊 Provider 的 ID 相同，也不得直接使用建置者的 Your user ID 當作小如如的身分。
4. 以 `provision_lifeos.py` 產生專用 gateway／提醒金鑰及短效啟用碼，base URL 使用 `https://mr-6c1r.onrender.com`。不可複用舊 MR 的邀請碼或金鑰。Google 服務帳號與 gateway URL 可以沿用現有私密設定，但日曆、LINE channel 與兩種金鑰不可共用。

## 部署次序

先依 `LIFEOS_CUSTOMER_SETUP.md` 驗證正式資料庫 schema、備份、套用隔離 migration 並部署 gateway；不得將此次本機測試當作正式部署成功。

沿用 MR 服務的根目錄、安裝及啟動命令。保留 MR 原環境變數，新增 `LIFEOS_CLIENTS_FILE=clients/xiaoruru.json` 與新空間的私密設定；**不可在 MR 服務設定 `LIFEOS_STANDALONE=1`**。停用的 profile 不會啟用正式功能，也不會查詢新空間後端；啟用時會驗證日曆與後端 tenant 相符，並拒絕新 profile 複用 MR 的日曆、LINE 憑證或金鑰。

### 取得新 Provider 的本人身分

在正式啟用前，可將 `CLIENT_XIAORURU_SETUP_ENABLED=1`。此時只註冊設定用 callback 與受專用 `LIFEOS_CRON_KEY` 保護的連線檢查，不讀寫 MR 或新空間的待辦資料。

- `GET /clients/xiaoruru/setup-check`：驗證 LINE token 對應正確的 basic ID、Google 服務帳號可讀取新日曆。回應僅包含狀態，不含憑證或行程內容。
- `POST /clients/xiaoruru/setup-calendar-test`：由設定人員以新空間 Bearer key 呼叫，建立一筆無邀請人、無 Meet、無提醒的私人測試活動，讀回後立即刪除；若清除失敗會回傳測試 ID 供清理，不可宣稱成功。
- 正確簽章的 LINE 一對一訊息「取得綁定碼」只回覆傳訊者自己的 LINE user ID；其他訊息回覆尚未啟用。群組不回覆識別碼，也不自動將任何人設為管理者。
- 收到小如如本人識別碼後才設定 owner、建立邀請與正式啟用。正式 profile 啟用後不再掛載這些設定用路由。

依實際產生的設定登錄 tenant，完成後端驗證後才啟用 tenant 與 profile。預定 Webhook 為 `https://mr-6c1r.onrender.com/clients/xiaoruru/callback`；目前路由尚未部署或啟用，不能先填入 LINE 驗證為已接通。

關閉這個新 LINE OA 的自動回覆，啟用 Webhook 並驗證。管理者以一次性啟用指令加入後，驗收新增／改期／取消、待辦、逐日補資料、週圖與提醒，確認舊日曆及待辦沒有出現在新空間。提醒另需配置新空間的排程與金鑰，不能只以 Webhook 成功作為驗收。

## 目前狀態

程式整合與設定用入口已準備，200 項 Python 測試通過；共用主機測試涵蓋原 callback 保留、不同 channel 簽章、新 LINE 回覆憑證、提醒金鑰、請求設定還原及阻擋複用 MR 日曆。設定入口另外驗證只回覆本人識別碼、群組不洩漏識別碼、錯誤憑證不存取日曆、私人測試活動會清除，以及 Google DELETE 的 204 空回應處理。沒有把任何真實憑證存入此分支。

新日曆已由使用者建立並提供 ID，已存放於新空間的 Render 私密設定；尚未註冊正式客戶資料或啟用新 LINE 的日常功能。

正式資料庫檢查時，尚未套用 tenant migration；MR 有 2 位使用者、0 筆待辦、44 筆行程索引，使用單一日曆。這些是部署前的比對基準，不是已完成隔離上線。

# 小如如的秘書：獨立安裝

## 已確認

- LINE OA：`@345lcfso`；Messaging API Channel ID：`2012149818`。
- 客戶空間：`xiaoruru`；顯示名稱：小如如的秘書。
- 使用新的 Google 日曆；不匯入現有 MR 行程、待辦、使用者或邀請碼。
- 設定檔：`clients/xiaoruru.json`，預設停用。Channel ID 只是識別資料，不能代替 token 或 secret。
- 此分支整合正式版的最新行程補資料、名稱修改與清單確認流程；MR 模式保留原圖文選單啟動。

## 尚待取得與設定

1. 新建「小如如 Life OS」Google 日曆，確認時區為 Asia/Taipei，記錄 calendar ID；將該日曆共享給服務帳號並授予變更活動權限。若小如如需要 Google／手機查看，另共享給她的 Google 帳號。
2. 新 Channel 的 Channel secret 和 Channel access token，僅填入新服務的私密環境變數，勿提交至 Git 或貼在交付文件中。
3. 小如如在新 Provider 下的 LINE user ID。不得假設與舊 Provider 的 ID 相同，也不得直接使用建置者的 Your user ID 當作小如如的身分。
4. 選定新服務 URL 後，以 `provision_lifeos.py` 產生專用 gateway／提醒金鑰及短效啟用碼。不可複用舊 MR 的邀請碼或金鑰。

## 部署次序

先依 `LIFEOS_CUSTOMER_SETUP.md` 驗證正式資料庫 schema、備份、套用隔離 migration 並部署 gateway；不得將此次本機測試當作正式部署成功。

新服務以 `ai-MRbot` 為根目錄，安裝 `requirements.lifeos.txt`，啟動命令為 `gunicorn app:app`。設定 `LIFEOS_STANDALONE=1`、`LIFEOS_CLIENTS_FILE=clients/xiaoruru.json`，以及設定檔列出的私密環境變數。

依實際產生的設定登錄 tenant，完成後端驗證後才啟用 tenant 與 profile。Webhook 路徑為 `/clients/xiaoruru/callback`；主機名稱必須以實際部署結果為準，目前沒有可使用的新 Webhook URL。

關閉這個新 LINE OA 的自動回覆，啟用 Webhook 並驗證。管理者以一次性啟用指令加入後，驗收新增／改期／取消、待辦、逐日補資料、週圖與提醒，確認舊日曆及待辦沒有出現在新空間。提醒另需配置新空間的排程與金鑰，不能只以 Webhook 成功作為驗收。

## 目前狀態

程式整合與停用設定已準備；184 項 Python 測試、gateway 金鑰綁定測試及記憶體 PostgreSQL 隔離驗證通過。尚未建立新雲端服務、日曆或正式客戶資料，尚未串接新 LINE。沒有把任何真實憑證存入此分支。

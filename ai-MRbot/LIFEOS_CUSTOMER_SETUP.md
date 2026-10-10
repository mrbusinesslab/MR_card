# Life OS 客戶複製準備

## 目前交付狀態

程式、獨立入口、客戶設定、建立工具與驗證腳本已準備。本分支尚未合併到 main，也未部署到現有 MR 服務。

**資料庫隔離尚未上線**：Supabase 寫入工具回報 `Invalid or expired requestState`。需連線恢復後套用 SQL、完成實際資料庫測試，再部署新版 gateway。不可把這份準備版本直接當成已可接客的正式版。

MR 和小如如維持同一個客戶空間。既有使用者 ID、待辦、行程及建立者不重建。未来不同客戶各自使用不同 LINE channel、日曆、gateway 金鑰及提醒金鑰。可以由同一個 MR Google 帳號管理多個客戶日曆。

## 已準備的內容

| 檔案 | 用途 |
| --- | --- |
| lifeos_app.py | 獨立 Life OS 入口，不載入電子名片、BNI、人物查詢 |
| lifeos_settings.py | 每次請求使用各自設定，不修改全域環境變數 |
| provision_lifeos.py | 產生新客戶設定、金鑰、啟用碼和登錄 SQL；預設停用 |
| lifeos_tenants.sql | 加入客戶欄位、同一 LINE 人員跨客戶的識別、跨客戶隔離 |
| lifeos_gateway/index.ts | 依金鑰決定客戶，拒絕偽造的客戶 ID |
| test_lifeos_clients.py | 設定、入口、金鑰、日曆、圖片位置及建立工具測試 |
| tests/test_gateway.mjs | Gateway 身分綁定及拒絕跨客戶請求測試 |
| tests/test_lifeos_tenants.sql | 在隔離測試資料上驗證資料庫行為，最後回滾 |

獨立入口啟動前會比對 gateway 的客戶 ID 和日曆 ID。後端未準備完成就停止啟動。每位客戶的圖片使用獨立目錄及簽名；提醒保留原有用量限制。

## 第一次安裝：連線恢復後

1. 先備份、在測試資料庫套用 `lifeos_tenants.sql`。執行 `tests/test_lifeos_tenants.sql`，確認不同客戶互相看不到或修改不到資料；同客戶共享和建立者紀錄保留。
2. 對正式 MR 資料庫套用同一份 SQL，確認 MR 使用者、待辦及行程數量和原先一致，RLS 與函式執行權限只允許後端角色。
3. 部署 `lifeos_gateway/index.ts` 到原本的 `lifeos-gateway`（保留自訂金鑰驗證；`verify_jwt=false`）。MR 舊金鑰由 `lifeos_tenants` 的 MR 紀錄識別，既有程式未帶 tenant_id 時也接受。
4. 先驗收 MR 和小如如的查詢、新增、完成、改期、週圖與提醒；再合併程式。勿在現有 MR 服務設定 `LIFEOS_STANDALONE=1`。

SQL 不是重複執行用的腳本；若已成功套用，先檢查 schema 後再處理，勿再次整份執行。

## 未來第一位客戶

先取得：客戶的 LINE OA Messaging API channel secret/token、管理者 LINE user ID、MR 建立的專用 Google calendar ID，以及 Google service account 的日曆寫入權限。客戶如需在 Google 看行程，以其 Google 帳號取得該專用日曆的唯讀共享權限；LINE 是否能編輯由 Life OS 設定控制。

產生範本（參數全為示範，請換成真實資料）：

```bash
python provision_lifeos.py --tenant client01 --name 客戶一 \
  --calendar customer-calendar-id --owner U11111111111111111111111111111111 \
  --base-url https://your-lifeos-service.example --output /private/client01
```

此命令不建立雲端服務、不更改 MR、不啟用客戶。輸出資料夾預設不納入 Git；`environment.json` 和 `activation.txt` 只有檔案擁有者可讀寫。不要把實際金鑰或啟用碼上傳 GitHub。

1. 補齊 `environment.json` 的空白值，將每個鍵值放入服務的私密環境變數。Google service account JSON 需放成一個完整字串。
2. 檢查並執行 `register.sql`，客戶仍維持停用。啟用碼為一次性，期限 7 天；接近交付時才產生。
3. 完成 LINE、Google、gateway 設定驗證後，才將該客戶 `lifeos_tenants.enabled` 設為 true，並將 `clients.json` 該客戶的 enabled 設為 true。
4. 獨立服務設定 `LIFEOS_STANDALONE=1`、`LIFEOS_CLIENTS_FILE` 指向設定檔；安裝 `requirements.lifeos.txt`，使用 `gunicorn app:app`。根目錄 `/health` 用於健康檢查。
5. LINE webhook：`https://your-lifeos-service.example/clients/client01/callback`。管理者在一對一聊天室輸入 `activation.txt` 內的指令。
6. 週圖網址根目錄須為 `https://your-lifeos-service.example/clients/client01`，已由工具產生。
7. 提醒端點：`/clients/client01/lifeos/reminders`；測試提醒端點：`/clients/client01/lifeos/test-reminders`。排程器以该客戶 `LIFEOS_CRON_KEY` 放在 `Authorization: Bearer ...`；不要用 MR 的金鑰。每日提醒預設關閉。
8. 測試錯誤啟用碼、跨客戶 ID、不同金鑰、同一 LINE 使用者加入兩個客戶、共享者權限及金鑰停用，再交付。

若加入第二位共享者，先由管理者決定是否開啟 share_tasks/share_calendar，再產生該客戶的共享邀請。shared_owner 使用資料庫內該客戶管理者的 user_id；不要直接填原始 LINE ID（MR 本身除外）。建立者欄位保留，日後可獨立關閉共享。

## 成本與範圍

這次範本不自動購買服務或增加雲端資源。未來客戶實際啟用後，LINE 推播、主機、資料庫與日曆 API 會有各自用量，交付前須依實際方案評估。程式不透過 Codex 處理 LINE 日常訊息。

目前不是完整的收費平台：沒有自助註冊、付款、訂閱停權或客戶後台。分類仍沿用現有美容／商會規則。這些不阻礙先準備管理者手動複製，但不應對外宣稱已完成自動開通。

## 驗證

```bash
python -m unittest test_lifeos test_lifeos_calendar test_lifeos_week_image test_lifeos_shared test_lifeos_clients -q
node tests/test_gateway.mjs
```

資料庫腳本需在完成 migration 的測試 PostgreSQL 上執行，**目前尚未驗收實際資料庫行為**。不應只用 Python 測試結果判定客戶資料已安全隔離。

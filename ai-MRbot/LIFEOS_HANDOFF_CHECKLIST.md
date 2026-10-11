# Life OS 標準複製與交付清單

適用：由 MR 管理者手動安裝到另一個官方 LINE。準備版本預設停用。每個客戶空間從空白資料開始；同一空間可有多位使用者。

## 客戶需提供

| 資料 | 用途 | 必要性 |
|---|---|---|
| 客戶名稱、官方 LINE 帳號 | 顯示名称、確認安裝對象 | 必填 |
| Messaging API Channel ID | 安裝紀錄與核對 | 必填 |
| Channel Access Token、Channel Secret | 回覆與驗證 webhook | 必填，私密提供 |
| 管理者 LINE user ID | 綁定該空間管理者 | 必填，非 LINE 顯示名稱 |
| Google 日曆管理方式 | MR 帳號建立獨立日曆，或客戶帳號擁有日曆 | 必選 |
| 專用 Calendar ID | 行程讀寫與隔離 | 必填，不可重用 MR 日曆 |
| 日曆查看者 Google email | 日曆唯讀共享 | 如需 Google 查看 |
| Google service account 授權 | 對專用日曆授予寫入權限 | 必填，由建置者設定；不用 Gmail 密碼 |
| 其他使用者與共享需求 | 決定待辦／行程是否共享 | 選填 |
| 提醒需求、分類、舊資料匯入範圍 | 交付內容確認 | 選填；提醒預設關閉、匯入預設不做 |

現行 Google 授權使用 service account，不是使用者 Google 登入。每個客戶可替換授權 JSON 和日曆 ID；同一客戶的共享者可共用其日曆。若要求同一客戶每個人各自連結 Google OAuth／私人日曆，屬後續功能，尚未實作。

## 權限管理

| 身分 | 管理方式 | 可操作內容 |
|---|---|---|
| MR 建置管理者 | 私密環境設定與後端登錄 | 登錄／停用客戶、發邀請、設定共享及 Google 授權 |
| 客戶管理者 | 專用 owner LINE ID、一次性啟用碼 | 自己的待辦與指定日曆；共享開關由建置者設定 |
| 獨立一般使用者 | 該客戶的獨立邀請，shared_owner 為空 | 自己的待辦；不自動取得客戶主日曆權限 |
| 共享使用者 | 該客戶邀請，shared_owner 指向管理者的內部 ID | 依 share_tasks／share_calendar 管理共用內容 |

目前沒有客戶自行管理成員或權限的後台。共享權限不是唯讀：啟用共享後，成員可操作授權內容。Google 唯讀共享是另一層權限，不能代替 LINE 權限。建立者與修改者都保留，關閉共享後原有資料仍保留。

## 安裝順序

- [ ] 記錄準備分支 commit、客戶識別碼與安裝者；確認專用日曆未混入 MR 資料。
- [ ] 首次上線先備份正式資料庫，套用 tenant migration、gateway；核對舊 MR 使用者、待辦及行程紀錄。
- [ ] 執行 provision_lifeos.py 產生停用設定，不複製資料庫內容、圖片、草稿或舊啟用碼。
- [ ] 將該客戶 Token、Secret、gateway／提醒金鑰、Google 授權填入私密環境設定。
- [ ] 依 register.sql 登錄；確認 Calendar ID／LINE Channel／金鑰彼此獨立。
- [ ] 對專用日曆授權 service account；Google 查看者依需求設定唯讀。
- [ ] 安裝 requirements.lifeos.txt；LIFEOS_STANDALONE=1，設定 clients.json 路徑與 HTTPS 公開網址。
- [ ] 完成設定比對後啟用該客戶；確認 /health 通過。
- [ ] 將 webhook 設為 /clients/客戶識別碼/callback；驗證 LINE 簽名與正確 Channel。
- [ ] 管理者輸入一次性啟用碼；依需求發獨立或共享邀請。
- [ ] 若需提醒，另設該客戶排程及 Authorization；確認 LINE 推播配額。
- [ ] 完成以下驗收；記錄結果後交付。

## 功能驗收

| 檢查 | 通過條件 |
|---|---|
| 空白開始 | 無 MR 的行程、待辦、個人資料、草稿、圖片或預設共享者 |
| 啟用 | 正確碼可使用一次；錯誤、過期、另一客戶碼均拒絕 |
| 新增行程 | 先顯示確認，確認後只寫該客戶日曆；預設無 Google Meet |
| 改期／取消 | 正確指定目標，多筆提供選擇；其他客戶目標不可操作 |
| 待辦 | 新增、完成、延期、逾期、取消正常，建立者不變 |
| 日期查詢 | 直接輸入 MM/DD 查當日待辦與行程，無效日期提示修正 |
| 週／月圖 | 顯示最新專用日曆，週一至週日；圖片簽名不可跨客戶使用 |
| 行程清單卡片 | 修改／移除候選項正常；同人跨客戶不混用修改狀態 |
| 提醒 | 錯誤金鑰拒絕；正確設定只送該客戶 LINE；配額不足停止 |
| 共享 | 只授予指定內容；關閉共享後無法取得其他人的內容 |
| 隔離 | 同一 LINE 人員加入兩個客戶，待辦、草稿及日曆均分開 |
| 停用 | 停用客戶後 gateway 拒絕其金鑰；其他客戶正常 |
| 舊 MR 回歸 | 原有電子名片、BNI 查詢與 Life OS 正常 |

新增客戶的驗收資料須獨立標記並於交付前清除；不得用刪除整個日曆或清空全部待辦作為清理方式。

## 準備驗證與正式驗收的區別

準備版本已通過 Python、gateway 模擬與暫時 PostgreSQL 隔離測試。正式 Supabase migration／gateway 尚未部署；真實 LINE、Google、排程的端到端驗收要在取得客戶設定後執行。這份清單是標準交付流程，不代表已開通另一套系統。

## 新增成員的離線工具

一般使用者（私人待辦，不自動分享管理者日曆）：

```bash
python provision_lifeos_member.py --tenant client01 --label 成員甲 --output /private/member-a
```

共享使用者：

```bash
python provision_lifeos_member.py --tenant client01 --label 成員乙 --shared-owner U11111111111111111111111111111111 --output /private/member-b
```

--shared-owner 使用管理者原始 LINE user ID；SQL 在指定客戶內查找已啟用的管理者，找不到就整筆中止，不接受其他客戶或共享成員當管理者。工具不改共享開關；建置者先核對 share_tasks／share_calendar，再執行 register-member.sql。activation.txt 的一次性碼效期從登錄起七天，只私下交給指定成員。此邀請為持碼者可使用的邀請，尚未綁定收件人的 LINE ID，不可公開張貼。

關閉共享的驗收：關閉 owner 的 share_tasks／share_calendar，確認共享者立即不能取得其內容，管理者仍可查自己的資料，原建立者紀錄不變。此案例已加入 PostgreSQL 回滾測試。

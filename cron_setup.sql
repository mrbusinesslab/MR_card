-- 執行前準備：
-- 1. 到 Supabase Dashboard -> Database -> Extensions，搜尋並啟用 "pg_cron" 和 "pg_net" 這兩個擴充功能
-- 2. 把下面的 <your-project-ref> 換成你的專案 ref
-- 3. 把 <CRON_SECRET的值> 換成你用 `supabase secrets set CRON_SECRET=...` 設定的同一組值
--    （這組密鑰只是用來保護 send-followups 這個網址，避免被別人亂打）

select cron.schedule(
  'send-followups-daily',
  '0 2 * * *', -- UTC 時間每天 02:00，等於台灣時間每天早上 10:00
  $$
  select net.http_post(
    url := 'https://<your-project-ref>.functions.supabase.co/send-followups',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-cron-secret', '<CRON_SECRET的值>'
    ),
    body := '{}'::jsonb
  );
  $$
);

-- 如果之後想確認排程有沒有設定成功，可以查詢：
-- select * from cron.job;

-- 如果想手動測試一次（不用等排程時間到）：
-- select net.http_post(
--   url := 'https://<your-project-ref>.functions.supabase.co/send-followups',
--   headers := jsonb_build_object('Content-Type','application/json','x-cron-secret','<CRON_SECRET的值>'),
--   body := '{}'::jsonb
-- );

-- 如果之後想取消排程：
-- select cron.unschedule('send-followups-daily');


-- ============================================================
-- 每週品牌小技巧推播（weekly-tip-broadcast）
-- 一樣需要先設定 CRON_SECRET，並確認上面的 pg_cron / pg_net 已啟用
-- ============================================================

select cron.schedule(
  'weekly-tip-broadcast',
  '0 1 * * 1', -- UTC 時間每週一 01:00，等於台灣時間每週一早上 09:00
  $$
  select net.http_post(
    url := 'https://<your-project-ref>.functions.supabase.co/weekly-tip-broadcast',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-cron-secret', '<CRON_SECRET的值>'
    ),
    body := '{}'::jsonb
  );
  $$
);

-- 手動測試一次（不用等到下週一）：
-- select net.http_post(
--   url := 'https://<your-project-ref>.functions.supabase.co/weekly-tip-broadcast',
--   headers := jsonb_build_object('Content-Type','application/json','x-cron-secret','<CRON_SECRET的值>'),
--   body := '{}'::jsonb
-- );

-- 如果之後想取消排程：
-- select cron.unschedule('weekly-tip-broadcast');

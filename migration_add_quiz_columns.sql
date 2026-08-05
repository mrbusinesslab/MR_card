-- 你已經有 line_sessions 這張表（先前是勾選+文字題版本），
-- 這段只補上新版單題量表流程需要的欄位，不會刪掉舊欄位或舊資料。
-- 在 Supabase SQL Editor 執行一次即可。

alter table line_sessions
  add column if not exists quiz_index int not null default 0,
  add column if not exists quiz_answers jsonb not null default '{}';

-- 保險起見，重新確認權限（跟之前修過的一樣）
grant usage on schema public to service_role;
grant select, insert, update, delete on public.line_sessions to service_role;
grant select, insert, update, delete on public.line_diagnosis_results to service_role;

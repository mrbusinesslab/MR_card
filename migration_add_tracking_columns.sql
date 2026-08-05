-- 在 Supabase SQL Editor 執行這段，補上後續追蹤 + 轉介機制需要的欄位
-- 不會刪掉任何舊資料

alter table line_sessions
  add column if not exists consulted boolean not null default false,
  add column if not exists consulted_at timestamptz,
  add column if not exists diagnosis_completed_at timestamptz,
  add column if not exists followup_sent_at timestamptz,
  add column if not exists referral_code text,
  add column if not exists referred_by text,
  add column if not exists referral_count int not null default 0;

-- Postgres 的 unique index 允許多個 NULL 值共存，所以舊資料的 referral_code
-- 在還沒被機器人自動補上之前維持 NULL 也沒關係，不會撞到這個限制
create unique index if not exists line_sessions_referral_code_idx on line_sessions (referral_code);

grant select, insert, update, delete on public.line_sessions to service_role;
grant select, insert, update, delete on public.line_diagnosis_results to service_role;

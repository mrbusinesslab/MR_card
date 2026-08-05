-- 全新安裝：在 Supabase SQL Editor 執行這段建立資料表

create table if not exists line_sessions (
  user_id text primary key,           -- LINE userId
  state text not null default 'IDLE', -- IDLE | QUIZ | DONE
  quiz_index int not null default 0,  -- 目前問到第幾題（0-based）
  quiz_answers jsonb not null default '{}', -- { "1": 100, "2": 66, ... }
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists line_diagnosis_results (
  id uuid primary key default gen_random_uuid(),
  user_id text not null references line_sessions(user_id),
  primary_category text,
  selected_tags jsonb,
  answers jsonb,
  created_at timestamptz not null default now()
);

grant usage on schema public to service_role;
grant select, insert, update, delete on public.line_sessions to service_role;
grant select, insert, update, delete on public.line_diagnosis_results to service_role;

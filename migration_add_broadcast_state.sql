-- 每週品牌小技巧推播使用，記錄目前推播到第幾則（12 則循環）
-- 在 Supabase SQL Editor 執行一次即可

create table if not exists broadcast_state (
  id int primary key default 1,
  current_index int not null default 0,
  updated_at timestamptz not null default now(),
  constraint broadcast_state_single_row check (id = 1)
);

insert into broadcast_state (id, current_index)
values (1, 0)
on conflict (id) do nothing;

grant select, insert, update, delete on public.broadcast_state to service_role;

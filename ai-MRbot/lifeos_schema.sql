-- Life OS uses the existing MR project. No public/client access to private tasks.
create table public.lifeos_config (
  key text primary key,
  value text not null
);
create table public.lifeos_invites (
  id uuid primary key default gen_random_uuid(),
  code_hash text not null unique,
  label text not null,
  expires_at timestamptz not null,
  claimed_by text,
  claimed_at timestamptz
);
create table public.lifeos_users (
  user_id text primary key,
  label text not null,
  assistant_mode boolean not null default false,
  notifications boolean not null default false,
  draft jsonb,
  updated_at timestamptz not null default now()
);
create table public.lifeos_tasks (
  id bigint generated always as identity primary key,
  user_id text not null references public.lifeos_users(user_id),
  title text not null check (length(title) between 1 and 500),
  category text not null default '生活',
  status text not null default '未開始' check (status in ('未開始','進行中','等待對方','完成','取消')),
  priority text not null default '一般' check (priority in ('一般','重要')),
  due_at timestamptz,
  remind_at timestamptz,
  original_text text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz
);
create index lifeos_tasks_owner_status on public.lifeos_tasks(user_id,status,due_at);
create table public.lifeos_events (
  event_id text primary key,
  user_id text not null,
  result jsonb not null,
  created_at timestamptz not null default now()
);
create table public.lifeos_notifications (
  id uuid primary key default gen_random_uuid(),
  user_id text not null references public.lifeos_users(user_id),
  notification_key text not null,
  state text not null check (state in ('claimed','sent','failed')),
  retry_key uuid not null default gen_random_uuid(),
  claimed_at timestamptz not null default now(),
  sent_at timestamptz,
  unique(user_id,notification_key)
);
create index lifeos_notifications_month on public.lifeos_notifications(user_id,claimed_at);

alter table public.lifeos_config enable row level security;
alter table public.lifeos_invites enable row level security;
alter table public.lifeos_users enable row level security;
alter table public.lifeos_tasks enable row level security;
alter table public.lifeos_events enable row level security;
alter table public.lifeos_notifications enable row level security;
revoke all on public.lifeos_config, public.lifeos_invites, public.lifeos_users,
  public.lifeos_tasks, public.lifeos_events, public.lifeos_notifications from anon, authenticated;
grant all on public.lifeos_config, public.lifeos_invites, public.lifeos_users,
  public.lifeos_tasks, public.lifeos_events, public.lifeos_notifications to service_role;
grant usage, select on sequence public.lifeos_tasks_id_seq to service_role;

create function public.lifeos_dispatch(p jsonb) returns jsonb
language plpgsql security invoker set search_path = public, pg_temp as $$
declare
  a text := p->>'action';
  uid text := p->>'user_id';
  eid text := p->>'event_id';
  u public.lifeos_users%rowtype;
  inv public.lifeos_invites%rowtype;
  t jsonb;
  res jsonb;
  rows jsonb := '[]'::jsonb;
  nt public.lifeos_tasks%rowtype;
  n public.lifeos_notifications%rowtype;
begin
  if a = 'notification_users' then
    select coalesce(jsonb_agg(to_jsonb(x)), '[]'::jsonb) into rows
      from (select user_id, label from public.lifeos_users where notifications) x;
    return jsonb_build_object('users',rows);
  end if;
  if uid is null or uid !~ '^U[0-9a-f]{32}$' then
    return jsonb_build_object('error','invalid_user');
  end if;
  -- Serialize operations per user and make webhook retries idempotent.
  perform pg_advisory_xact_lock(hashtextextended(uid,0));
  if eid is not null then
    select result into res from public.lifeos_events where event_id=eid and user_id=uid;
    if found then return res; end if;
  end if;
  select * into u from public.lifeos_users where user_id=uid;
  if a = 'enroll' then
    if found then
      res := jsonb_build_object('user',to_jsonb(u),'already_enrolled',true);
    else
      select * into inv from public.lifeos_invites
        where code_hash=p->>'code_hash' and claimed_by is null and expires_at>now() for update;
      if not found then return jsonb_build_object('error','invalid_invite'); end if;
      update public.lifeos_invites set claimed_by=uid,claimed_at=now() where id=inv.id;
      insert into public.lifeos_users(user_id,label,assistant_mode) values(uid,inv.label,true) returning * into u;
      res := jsonb_build_object('user',to_jsonb(u));
    end if;
  elsif not found then
    return jsonb_build_object('error','not_enrolled');
  elsif a = 'get_user' then
    return jsonb_build_object('user',to_jsonb(u));
  elsif a = 'mode' then
    update public.lifeos_users set assistant_mode=(p->>'enabled')::boolean, updated_at=now() where user_id=uid;
    res := jsonb_build_object('ok',true);
  elsif a = 'notifications' then
    update public.lifeos_users set notifications=(p->>'enabled')::boolean, updated_at=now() where user_id=uid;
    res := jsonb_build_object('ok',true);
  elsif a = 'draft' then
    if jsonb_typeof(p->'tasks') <> 'array' or jsonb_array_length(p->'tasks') not between 1 and 10 then
      return jsonb_build_object('error','invalid_draft');
    end if;
    update public.lifeos_users set draft=jsonb_build_object('tasks',p->'tasks','created_at',now()),updated_at=now() where user_id=uid;
    res := jsonb_build_object('ok',true);
  elsif a = 'discard' then
    update public.lifeos_users set draft=null,updated_at=now() where user_id=uid;
    res := jsonb_build_object('ok',true);
  elsif a = 'confirm' then
    if u.draft is null then return jsonb_build_object('error','no_draft'); end if;
    if (u.draft->>'created_at')::timestamptz < now()-interval '1 day' then
      update public.lifeos_users set draft=null where user_id=uid;
      return jsonb_build_object('error','expired_draft');
    end if;
    for t in select value from jsonb_array_elements(u.draft->'tasks') loop
      select * into nt from public.lifeos_tasks
        where user_id=uid and status not in ('完成','取消') and title=t->>'title'
        and due_at is not distinct from nullif(t->>'due_at','')::timestamptz limit 1;
      if not found then
        insert into public.lifeos_tasks(user_id,title,category,priority,due_at,remind_at,original_text)
          values(uid,t->>'title',coalesce(t->>'category','生活'),coalesce(t->>'priority','一般'),
            nullif(t->>'due_at','')::timestamptz,nullif(t->>'remind_at','')::timestamptz,t->>'original_text') returning * into nt;
      end if;
      rows := rows || jsonb_build_array(to_jsonb(nt));
    end loop;
    update public.lifeos_users set draft=null,updated_at=now() where user_id=uid;
    res := jsonb_build_object('tasks',rows);
  elsif a = 'list' then
    select coalesce(jsonb_agg(to_jsonb(x)), '[]'::jsonb) into rows from
      (select * from public.lifeos_tasks where user_id=uid and
        (coalesce((p->>'include_closed')::boolean,false) or status not in ('完成','取消'))
        order by due_at nulls last, id limit 200) x;
    return jsonb_build_object('tasks',rows,'truncated',
      (select count(*)>200 from public.lifeos_tasks where user_id=uid and
        (coalesce((p->>'include_closed')::boolean,false) or status not in ('完成','取消'))));
  elsif a = 'update' then
    if p ? 'status' and p->>'status' not in ('未開始','進行中','等待對方','完成','取消') then
      return jsonb_build_object('error','invalid_status');
    end if;
    update public.lifeos_tasks set
      status=coalesce(p->>'status',status),
      due_at=case when p ? 'due_at' then nullif(p->>'due_at','')::timestamptz else due_at end,
      -- A postponement invalidates the old reminder.
      remind_at=case when p ? 'due_at' then null else remind_at end,
      completed_at=case when p->>'status'='完成' then now()
        when p ? 'status' then null else completed_at end,
      updated_at=now()
      where user_id=uid and id=(p->>'task_id')::bigint returning * into nt;
    if not found then return jsonb_build_object('error','not_found'); end if;
    res := jsonb_build_object('task',to_jsonb(nt));
  elsif a = 'notification_claim' then
    if not u.notifications then return jsonb_build_object('error','disabled'); end if;
    if (select count(*) from public.lifeos_notifications where user_id=uid
        and claimed_at >= date_trunc('month', now() at time zone 'Asia/Taipei') at time zone 'Asia/Taipei') >= 60 then
      return jsonb_build_object('error','monthly_cap');
    end if;
    insert into public.lifeos_notifications(user_id,notification_key,state)
      values(uid,p->>'key','claimed') on conflict do nothing returning * into n;
    if not found then
      select * into n from public.lifeos_notifications where user_id=uid and notification_key=p->>'key' for update;
      if n.state='sent' or (n.state='claimed' and n.claimed_at>now()-interval '10 minutes')
        or n.claimed_at<now()-interval '23 hours' then
        return jsonb_build_object('error','already_claimed');
      end if;
      update public.lifeos_notifications set state='claimed',claimed_at=now() where id=n.id;
    end if;
    return jsonb_build_object('notification',to_jsonb(n));
  elsif a = 'notification_finish' then
    update public.lifeos_notifications set state=case when (p->>'sent')::boolean then 'sent' else 'failed' end,
      sent_at=case when (p->>'sent')::boolean then now() else null end
      where user_id=uid and id=(p->>'notification_id')::uuid;
    res := jsonb_build_object('ok',true);
  else
    return jsonb_build_object('error','invalid_action');
  end if;
  if eid is not null then insert into public.lifeos_events(event_id,user_id,result) values(eid,uid,res) on conflict do nothing; end if;
  return res;
end;
$$;
revoke all on function public.lifeos_dispatch(jsonb) from public, anon, authenticated;
grant execute on function public.lifeos_dispatch(jsonb) to service_role;

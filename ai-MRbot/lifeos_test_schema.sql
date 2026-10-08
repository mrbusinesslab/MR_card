create table public.lifeos_test_reminders (
  user_id text primary key references public.lifeos_users(user_id),
  scheduled_at timestamptz not null default now(),
  due_at timestamptz not null,
  state text not null default 'pending' check(state in ('pending','claimed','sent','failed')),
  retry_key uuid not null default gen_random_uuid(),
  claimed_at timestamptz,
  sent_at timestamptz
);
alter table public.lifeos_test_reminders enable row level security;
revoke all on public.lifeos_test_reminders from anon, authenticated;
grant all on public.lifeos_test_reminders to service_role;
create function public.lifeos_test_dispatch(p jsonb) returns jsonb
language plpgsql security invoker set search_path=public,pg_temp as $$
declare uid text:=p->>'user_id'; a text:=p->>'action'; r public.lifeos_test_reminders%rowtype; rows jsonb;
begin
  if a='test_users' then
    select coalesce(jsonb_agg(to_jsonb(x)),'[]'::jsonb) into rows from
      (select user_id from public.lifeos_test_reminders where state<>'sent' and due_at<=now()
        and due_at>now()-interval '15 minutes' limit 20) x;
    return jsonb_build_object('users',rows);
  end if;
  if uid is null or uid !~ '^U[0-9a-f]{32}$' or not exists(select 1 from public.lifeos_users where user_id=uid) then
    return jsonb_build_object('error','not_enrolled');
  end if;
  perform pg_advisory_xact_lock(hashtextextended(uid,0));
  select * into r from public.lifeos_test_reminders where user_id=uid for update;
  if a='test_schedule' then
    if found and (r.scheduled_at at time zone 'Asia/Taipei')::date=(now() at time zone 'Asia/Taipei')::date then
      return jsonb_build_object('already_scheduled',true,'state',r.state,'due_at',r.due_at);
    end if;
    insert into public.lifeos_test_reminders(user_id,due_at) values(uid,now()+interval '1 minute')
      on conflict(user_id) do update set scheduled_at=now(),due_at=now()+interval '1 minute',state='pending',
        retry_key=gen_random_uuid(),claimed_at=null,sent_at=null returning * into r;
    return jsonb_build_object('state',r.state,'due_at',r.due_at);
  elsif not found then return jsonb_build_object('error','not_found');
  elsif a='test_claim' then
    if r.state='sent' or r.due_at>now() or r.due_at<now()-interval '15 minutes' or
      (r.state='claimed' and r.claimed_at>now()-interval '2 minutes') then
      return jsonb_build_object('error','not_due');
    end if;
    update public.lifeos_test_reminders set state='claimed',claimed_at=now() where user_id=uid returning * into r;
    return jsonb_build_object('notification',to_jsonb(r));
  elsif a='test_finish' then
    update public.lifeos_test_reminders set state=case when (p->>'sent')::boolean then 'sent' else 'failed' end,
      sent_at=case when (p->>'sent')::boolean then now() else null end
      where user_id=uid and retry_key=(p->>'retry_key')::uuid;
    return jsonb_build_object('ok',true);
  end if;
  return jsonb_build_object('error','invalid_action');
end $$;
revoke all on function public.lifeos_test_dispatch(jsonb) from public,anon,authenticated;
grant execute on function public.lifeos_test_dispatch(jsonb) to service_role;

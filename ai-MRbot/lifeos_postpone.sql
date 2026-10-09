create table public.lifeos_pending_postpone (
 user_id text primary key references public.lifeos_users(user_id),
 task_id bigint not null references public.lifeos_tasks(id),
 expires_at timestamptz not null default now()+interval '1 day'
);
alter table public.lifeos_pending_postpone enable row level security;
revoke all on public.lifeos_pending_postpone from public,anon,authenticated;
grant all on public.lifeos_pending_postpone to service_role;
create function public.lifeos_postpone_dispatch(p jsonb) returns jsonb
language plpgsql security invoker set search_path=public,pg_temp as $$
declare uid text:=p->>'user_id'; a text:=p->>'action'; nt public.lifeos_tasks%rowtype; pending public.lifeos_pending_postpone%rowtype; r jsonb;
begin
 if uid is null or uid !~ '^U[0-9a-f]{32}$' or not exists(select 1 from public.lifeos_users where user_id=uid) then return jsonb_build_object('error','not_enrolled'); end if;
 perform pg_advisory_xact_lock(hashtextextended(uid,0));
 if a='postpone_get' then
  select jsonb_build_object('task_id',t.id,'title',t.title,'expires_at',x.expires_at) into r
   from public.lifeos_pending_postpone x join public.lifeos_tasks t on t.id=x.task_id and t.user_id=x.user_id
   where x.user_id=uid and x.expires_at>now() and t.status not in ('完成','取消');
  return jsonb_build_object('pending',r);
 elsif a='postpone_start' then
  select * into nt from public.lifeos_tasks where user_id=uid and id=(p->>'task_id')::bigint and status not in ('完成','取消');
  if not found then return jsonb_build_object('error','task_closed'); end if;
  insert into public.lifeos_pending_postpone(user_id,task_id) values(uid,nt.id)
   on conflict(user_id) do update set task_id=excluded.task_id,expires_at=now()+interval '1 day';
  return jsonb_build_object('ok',true);
 elsif a='postpone_cancel' then
  delete from public.lifeos_pending_postpone where user_id=uid;
  return jsonb_build_object('ok',true);
 elsif a='postpone_finish' then
  if p->>'event_id' is not null then
   select result into r from public.lifeos_events where event_id=p->>'event_id' and user_id=uid;
   if found then return r; end if;
  end if;
  select * into pending from public.lifeos_pending_postpone where user_id=uid and expires_at>now();
  if not found then return jsonb_build_object('error','no_pending'); end if;
  update public.lifeos_tasks set due_at=(p->>'due_at')::timestamptz,remind_at=null,updated_at=now()
   where user_id=uid and id=pending.task_id and status not in ('完成','取消') returning * into nt;
  if not found then return jsonb_build_object('error','task_closed'); end if;
  delete from public.lifeos_pending_postpone where user_id=uid;
  r:=jsonb_build_object('task',to_jsonb(nt));
  if p->>'event_id' is not null then insert into public.lifeos_events(event_id,user_id,result) values(p->>'event_id',uid,r) on conflict do nothing; end if;
  return r;
 end if;
 return jsonb_build_object('error','invalid_action');
end $$;
revoke all on function public.lifeos_postpone_dispatch(jsonb) from public,anon,authenticated;
grant execute on function public.lifeos_postpone_dispatch(jsonb) to service_role;

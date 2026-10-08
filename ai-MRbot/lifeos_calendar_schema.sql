create table public.lifeos_calendar_drafts (
 user_id text primary key references public.lifeos_users(user_id),
 payload jsonb not null, expires_at timestamptz not null default now()+interval '1 day'
);
create table public.lifeos_calendar_events (
 id bigint generated always as identity primary key,
 user_id text not null references public.lifeos_users(user_id),
 calendar_id text not null, event_id text not null, title text not null,
 unique(user_id,calendar_id,event_id)
);
alter table public.lifeos_calendar_drafts enable row level security;
alter table public.lifeos_calendar_events enable row level security;
revoke all on public.lifeos_calendar_drafts,public.lifeos_calendar_events from anon,authenticated;
grant all on public.lifeos_calendar_drafts,public.lifeos_calendar_events to service_role;
grant usage,select on sequence public.lifeos_calendar_events_id_seq to service_role;
create function public.lifeos_calendar_dispatch(p jsonb) returns jsonb
language plpgsql security invoker set search_path=public,pg_temp as $$
declare uid text:=p->>'user_id'; a text:=p->>'action'; r jsonb;
begin
 if uid is null or uid !~ '^U[0-9a-f]{32}$' or not exists(select 1 from public.lifeos_users where user_id=uid) then
  return jsonb_build_object('error','not_enrolled');
 end if;
 perform pg_advisory_xact_lock(hashtextextended(uid,0));
 if a='calendar_draft' then
  insert into public.lifeos_calendar_drafts(user_id,payload) values(uid,p->'payload')
   on conflict(user_id) do update set payload=excluded.payload,expires_at=now()+interval '1 day';
  return jsonb_build_object('ok',true);
 elsif a='calendar_get_draft' then
  select payload into r from public.lifeos_calendar_drafts where user_id=uid and expires_at>now();
  return jsonb_build_object('draft',r);
 elsif a='calendar_discard' then
  delete from public.lifeos_calendar_drafts where user_id=uid;
  return jsonb_build_object('ok',true);
 elsif a='calendar_save' then
  insert into public.lifeos_calendar_events(user_id,calendar_id,event_id,title)
    values(uid,p->>'calendar_id',p->>'event_id',p->>'title')
    on conflict(user_id,calendar_id,event_id) do update set title=excluded.title returning to_jsonb(lifeos_calendar_events.*) into r;
  delete from public.lifeos_calendar_drafts where user_id=uid and payload->>'event_id'=p->>'event_id';
  return jsonb_build_object('event',r);
 elsif a='calendar_events' then
  select coalesce(jsonb_agg(to_jsonb(e)),'[]'::jsonb) into r from public.lifeos_calendar_events e where user_id=uid;
  return jsonb_build_object('events',r);
 elsif a='calendar_event' then
  select to_jsonb(e) into r from public.lifeos_calendar_events e where user_id=uid and id=(p->>'id')::bigint;
  return jsonb_build_object('event',r);
 end if;
 return jsonb_build_object('error','invalid_action');
end $$;
revoke all on function public.lifeos_calendar_dispatch(jsonb) from public,anon,authenticated;
grant execute on function public.lifeos_calendar_dispatch(jsonb) to service_role;

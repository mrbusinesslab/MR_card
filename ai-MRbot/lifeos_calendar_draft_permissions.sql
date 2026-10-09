CREATE OR REPLACE FUNCTION public.lifeos_calendar_dispatch(p jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
declare uid text:=p->>'user_id'; a text:=p->>'action'; r jsonb;
begin
 if uid is null or uid !~ '^U[0-9a-f]{32}$' or not exists(select 1 from public.lifeos_users where user_id=uid) then
  return jsonb_build_object('error','not_enrolled');
 end if;
 perform set_config('lifeos.actor',uid,true);
 perform pg_advisory_xact_lock(hashtextextended(coalesce((select shared_owner from public.lifeos_users where user_id=uid),uid),0));
 if a='calendar_draft' then
  insert into public.lifeos_calendar_drafts(user_id,payload) values(uid,p->'payload')
   on conflict(user_id) do update set payload=excluded.payload,expires_at=now()+interval '1 day';
  return jsonb_build_object('ok',true);
 elsif a='calendar_get_draft' then
  select payload into r from public.lifeos_calendar_drafts where user_id=uid and expires_at>now();
  if r->>'operation' in ('update','cancel') and not exists(select 1 from public.lifeos_calendar_events e where e.calendar_id=r->>'calendar_id' and e.event_id=r->>'event_id' and public.lifeos_can_access(uid,e.user_id,'calendar')) then
   delete from public.lifeos_calendar_drafts where user_id=uid;
   r:=null;
  end if;
  return jsonb_build_object('draft',r);
 elsif a='calendar_discard' then
  delete from public.lifeos_calendar_drafts where user_id=uid;
  return jsonb_build_object('ok',true);
 elsif a='calendar_save' then
  if exists(select 1 from public.lifeos_calendar_events where calendar_id=p->>'calendar_id' and event_id=p->>'event_id' and not public.lifeos_can_access(uid,user_id,'calendar')) then return jsonb_build_object('error','not_authorized'); end if;
  update public.lifeos_calendar_events set title=p->>'title' where calendar_id=p->>'calendar_id' and event_id=p->>'event_id' and public.lifeos_can_access(uid,user_id,'calendar') returning to_jsonb(lifeos_calendar_events.*) into r;
  if not found then
  insert into public.lifeos_calendar_events(user_id,calendar_id,event_id,title)
    values(uid,p->>'calendar_id',p->>'event_id',p->>'title')
    on conflict(user_id,calendar_id,event_id) do update set title=excluded.title returning to_jsonb(lifeos_calendar_events.*) into r;
  end if;
  delete from public.lifeos_calendar_drafts where user_id=uid and payload->>'event_id'=p->>'event_id';
  return jsonb_build_object('event',r);
 elsif a='calendar_events' then
  select coalesce(jsonb_agg(to_jsonb(e)),'[]'::jsonb) into r from public.lifeos_calendar_events e where public.lifeos_can_access(uid,user_id,'calendar');
  return jsonb_build_object('events',r);
 elsif a='calendar_event' then
  select to_jsonb(e) into r from public.lifeos_calendar_events e where public.lifeos_can_access(uid,user_id,'calendar') and id=(p->>'id')::bigint;
  return jsonb_build_object('event',r);
 end if;
 return jsonb_build_object('error','invalid_action');
end $function$;


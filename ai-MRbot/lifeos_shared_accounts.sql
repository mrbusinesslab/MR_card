alter table public.lifeos_users add column shared_owner text, add column share_tasks boolean not null default false, add column share_calendar boolean not null default false;
alter table public.lifeos_invites add column shared_owner text;
alter table public.lifeos_tasks add column last_modified_by text;
alter table public.lifeos_calendar_events add column last_modified_by text;
update public.lifeos_tasks set last_modified_by=user_id;
update public.lifeos_calendar_events set last_modified_by=user_id;
create table public.lifeos_change_log(id bigint generated always as identity primary key, entity text not null, record_id bigint not null, creator text not null, actor text not null, operation text not null, changed_at timestamptz not null default now());
alter table public.lifeos_change_log enable row level security;
revoke all on public.lifeos_change_log from anon,authenticated;
grant all on public.lifeos_change_log to service_role;
grant usage,select on sequence public.lifeos_change_log_id_seq to service_role;
create function public.lifeos_can_access(actor text, creator text, kind text) returns boolean language sql stable set search_path=public,pg_temp as $$
select exists(select 1 from lifeos_users a join lifeos_users c on c.user_id=creator join lifeos_users owner on owner.user_id=coalesce(a.shared_owner,a.user_id)
where a.user_id=actor and (actor=creator or (coalesce(a.shared_owner,a.user_id)=coalesce(c.shared_owner,c.user_id) and case kind when 'task' then owner.share_tasks when 'calendar' then owner.share_calendar else false end)));
$$;
revoke all on function public.lifeos_can_access(text,text,text) from public,anon,authenticated;
grant execute on function public.lifeos_can_access(text,text,text) to service_role;
create function public.lifeos_record_change() returns trigger language plpgsql set search_path=public,pg_temp as $$
declare actor text:=coalesce(nullif(current_setting('lifeos.actor',true),''),new.user_id);
begin
 if tg_op='UPDATE' and new.user_id is distinct from old.user_id then raise exception 'Creator cannot change'; end if;
 new.last_modified_by:=actor;
 insert into lifeos_change_log(entity,record_id,creator,actor,operation) values(tg_table_name,new.id,new.user_id,actor,tg_op);
 return new;
end $$;
revoke all on function public.lifeos_record_change() from public,anon,authenticated;
create trigger lifeos_task_history before insert or update on public.lifeos_tasks for each row execute function public.lifeos_record_change();
create trigger lifeos_calendar_history before insert or update on public.lifeos_calendar_events for each row execute function public.lifeos_record_change();
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

CREATE OR REPLACE FUNCTION public.lifeos_confirm_tasks(p jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
declare
 uid text:=p->>'user_id'; eid text:=p->>'event_id';
 d jsonb; res jsonb; item jsonb; rows jsonb:='[]'::jsonb;
 old_ids bigint[]; task public.lifeos_tasks%rowtype;
begin
 if p->>'action' is distinct from 'confirm_tasks' or uid is null or uid !~ '^U[0-9a-f]{32}$' then
   return jsonb_build_object('error','invalid_action');
 end if;
 perform set_config('lifeos.actor',uid,true);
 perform pg_advisory_xact_lock(hashtextextended(coalesce((select shared_owner from public.lifeos_users where user_id=uid),uid),0));
 if eid is not null then
   select result into res from public.lifeos_events where user_id=uid and event_id=eid;
   if found then return res; end if;
 end if;
 select draft into d from public.lifeos_users where user_id=uid;
 select coalesce(array_agg(id),'{}'::bigint[]) into old_ids from public.lifeos_tasks where public.lifeos_can_access(uid,user_id,'task');
 res:=public.lifeos_dispatch(p||jsonb_build_object('action','confirm'));
 if res ? 'error' then return res; end if;
 for item in select value from jsonb_array_elements(res->'tasks') loop
   select * into task from public.lifeos_tasks where public.lifeos_can_access(uid,user_id,'task') and id=(item->>'id')::bigint;
   if not found then raise exception 'Owned task missing'; end if;
   -- Only initialize new tasks. Never overwrite status of a merged existing task.
   if not(task.id=any(old_ids)) and task.status='未開始' and exists(
     select 1 from jsonb_array_elements(d->'tasks') x where x->>'title'=task.title
       and x->>'original_text'=task.original_text and x->>'status'='等待對方') then
     update public.lifeos_tasks set status='等待對方',updated_at=now() where id=task.id and public.lifeos_can_access(uid,user_id,'task') returning * into task;
   end if;
   rows:=rows||jsonb_build_array(to_jsonb(task));
 end loop;
 res:=jsonb_build_object('tasks',rows);
 if eid is not null then update public.lifeos_events set result=res where user_id=uid and event_id=eid; end if;
 return res;
end $function$;

CREATE OR REPLACE FUNCTION public.lifeos_dispatch(p jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
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
  perform set_config('lifeos.actor',uid,true);
 perform pg_advisory_xact_lock(hashtextextended(coalesce((select shared_owner from public.lifeos_users where user_id=uid),uid),0));
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
      insert into public.lifeos_users(user_id,label,assistant_mode,shared_owner) values(uid,inv.label,true,inv.shared_owner) returning * into u;
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
        where public.lifeos_can_access(uid,user_id,'task') and status not in ('完成','取消') and title=t->>'title'
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
      (select * from public.lifeos_tasks where public.lifeos_can_access(uid,user_id,'task') and
        (coalesce((p->>'include_closed')::boolean,false) or status not in ('完成','取消'))
        order by due_at nulls last, id limit 200) x;
    return jsonb_build_object('tasks',rows,'truncated',
      (select count(*)>200 from public.lifeos_tasks where public.lifeos_can_access(uid,user_id,'task') and
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
      where public.lifeos_can_access(uid,user_id,'task') and id=(p->>'task_id')::bigint returning * into nt;
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
$function$;

CREATE OR REPLACE FUNCTION public.lifeos_postpone_dispatch(p jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
declare uid text:=p->>'user_id'; a text:=p->>'action'; nt public.lifeos_tasks%rowtype; pending public.lifeos_pending_postpone%rowtype; r jsonb;
begin
 if uid is null or uid !~ '^U[0-9a-f]{32}$' or not exists(select 1 from public.lifeos_users where user_id=uid) then return jsonb_build_object('error','not_enrolled'); end if;
 perform set_config('lifeos.actor',uid,true);
 perform pg_advisory_xact_lock(hashtextextended(coalesce((select shared_owner from public.lifeos_users where user_id=uid),uid),0));
 if a='postpone_get' then
  select jsonb_build_object('task_id',t.id,'title',t.title,'expires_at',x.expires_at) into r
   from public.lifeos_pending_postpone x join public.lifeos_tasks t on t.id=x.task_id and public.lifeos_can_access(x.user_id,t.user_id,'task')
   where x.user_id=uid and x.expires_at>now() and t.status not in ('完成','取消');
  return jsonb_build_object('pending',r);
 elsif a='postpone_start' then
  select * into nt from public.lifeos_tasks where public.lifeos_can_access(uid,user_id,'task') and id=(p->>'task_id')::bigint and status not in ('完成','取消');
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
   where public.lifeos_can_access(uid,user_id,'task') and id=pending.task_id and status not in ('完成','取消') returning * into nt;
  if not found then return jsonb_build_object('error','task_closed'); end if;
  delete from public.lifeos_pending_postpone where user_id=uid;
  r:=jsonb_build_object('task',to_jsonb(nt));
  if p->>'event_id' is not null then insert into public.lifeos_events(event_id,user_id,result) values(p->>'event_id',uid,r) on conflict do nothing; end if;
  return r;
 end if;
 return jsonb_build_object('error','invalid_action');
end $function$;

CREATE OR REPLACE FUNCTION public.lifeos_dispatch(p jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'public', 'pg_temp'
AS $function$
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
  perform set_config('lifeos.actor',uid,true);
 perform pg_advisory_xact_lock(hashtextextended(coalesce((select shared_owner from public.lifeos_users where user_id=uid),uid),0));
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
      insert into public.lifeos_users(user_id,label,assistant_mode,shared_owner) values(uid,inv.label,true,inv.shared_owner) returning * into u;
      res := jsonb_build_object('user',to_jsonb(u));
    end if;
  elsif not found then
    return jsonb_build_object('error','not_enrolled');
  elsif a = 'get_user' then
    return jsonb_build_object('user',to_jsonb(u)||jsonb_build_object('calendar_shared',coalesce((select share_calendar from public.lifeos_users where user_id=coalesce(u.shared_owner,uid)),false)));
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
        where public.lifeos_can_access(uid,user_id,'task') and status not in ('完成','取消') and title=t->>'title'
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
      (select * from public.lifeos_tasks where public.lifeos_can_access(uid,user_id,'task') and
        (coalesce((p->>'include_closed')::boolean,false) or status not in ('完成','取消'))
        order by due_at nulls last, id limit 200) x;
    return jsonb_build_object('tasks',rows,'truncated',
      (select count(*)>200 from public.lifeos_tasks where public.lifeos_can_access(uid,user_id,'task') and
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
      where public.lifeos_can_access(uid,user_id,'task') and id=(p->>'task_id')::bigint returning * into nt;
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
$function$;



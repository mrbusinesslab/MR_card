-- Additive preparation migration. Existing MR data keeps its IDs and ownership.
create table public.lifeos_tenants (
 id text primary key check(id ~ '^[a-z][a-z0-9_-]{1,39}$'),
 name text not null,
 calendar_id text not null unique,
 gateway_key_hash text not null unique check(gateway_key_hash ~ '^[0-9a-f]{64}$'),
 enabled boolean not null default true,
 created_at timestamptz not null default now()
);
alter table public.lifeos_tenants enable row level security;
revoke all on public.lifeos_tenants from public,anon,authenticated;
grant select,insert,update,delete on public.lifeos_tenants to service_role;
do $$ begin
 if (select count(distinct calendar_id) from public.lifeos_calendar_events)<>1 then
  raise exception 'MR calendar must be verified before preparation migration';
 end if;
 insert into public.lifeos_tenants(id,name,calendar_id,gateway_key_hash)
 select 'mr','MR Life OS',(select min(calendar_id) from public.lifeos_calendar_events),value
 from public.lifeos_config where key='gateway_key_hash';
 if not found then raise exception 'MR gateway configuration missing'; end if;
end $$;

do $$ declare tab text; begin
 foreach tab in array array['lifeos_users','lifeos_tasks','lifeos_invites','lifeos_events',
 'lifeos_notifications','lifeos_pending_postpone','lifeos_calendar_drafts','lifeos_calendar_events',
 'lifeos_test_reminders','lifeos_change_log'] loop
  execute format('alter table public.%I add column tenant_id text not null default ''mr'' references public.lifeos_tenants(id)',tab);
  execute format('create index on public.%I(tenant_id)',tab);
 end loop;
end $$;
alter table public.lifeos_users add column line_user_id text;
update public.lifeos_users set line_user_id=user_id;
alter table public.lifeos_users alter column line_user_id set not null;
create unique index lifeos_users_tenant_line on public.lifeos_users(tenant_id,line_user_id);

create function public.lifeos_stamp_tenant() returns trigger language plpgsql
set search_path=public,pg_temp as $$
declare active text:=nullif(current_setting('lifeos.tenant',true),'');
begin
 if tg_op='UPDATE' and new.tenant_id is distinct from old.tenant_id then
  raise exception 'Tenant cannot change';
 end if;
 if active is not null then
  if tg_op='UPDATE' and old.tenant_id<>active then raise exception 'Tenant mismatch'; end if;
  if tg_op='INSERT' then
   if new.tenant_id<>'mr' and new.tenant_id<>active then raise exception 'Tenant mismatch'; end if;
   new.tenant_id:=active;
  end if;
 end if;
 if tg_table_name='lifeos_users' then
  if tg_op='INSERT' then
   new.line_user_id:=coalesce(nullif(current_setting('lifeos.line_user',true),''),new.line_user_id,new.user_id);
  elsif new.line_user_id is distinct from old.line_user_id then raise exception 'LINE identity cannot change';
  end if;
  if new.shared_owner is not null and not exists(select 1 from lifeos_users where user_id=new.shared_owner and tenant_id=new.tenant_id) then
   raise exception 'Shared owner must belong to the same tenant';
  end if;
 end if;
 return new;
end $$;
revoke all on function public.lifeos_stamp_tenant() from public,anon,authenticated;
do $$ declare tab text; begin
 foreach tab in array array['lifeos_users','lifeos_tasks','lifeos_events','lifeos_notifications',
 'lifeos_pending_postpone','lifeos_calendar_drafts','lifeos_calendar_events','lifeos_test_reminders','lifeos_change_log'] loop
  execute format('create trigger aa_lifeos_tenant before insert or update on public.%I for each row execute function public.lifeos_stamp_tenant()',tab);
 end loop;
end $$;

create or replace function public.lifeos_can_access(actor text, creator text, kind text)
returns boolean language sql stable set search_path=public,pg_temp as $$
select exists(select 1 from lifeos_users a join lifeos_users c on c.user_id=creator
join lifeos_users owner on owner.user_id=coalesce(a.shared_owner,a.user_id)
where a.user_id=actor and a.tenant_id=c.tenant_id and owner.tenant_id=a.tenant_id
and (actor=creator or (coalesce(a.shared_owner,a.user_id)=coalesce(c.shared_owner,c.user_id)
and case kind when 'task' then owner.share_tasks when 'calendar' then owner.share_calendar else false end)));
$$;

-- Called only by the gateway with tenant_id determined from its secret.
-- A LINE user may belong to several customers: namespace internal identity,
-- retain the original LINE ID for push delivery and ownership lookup.
create function public.lifeos_tenant_dispatch(p jsonb) returns jsonb language plpgsql
set search_path=public,pg_temp as $$
declare tid text:=p->>'tenant_id'; action text:=p->>'action'; raw_uid text:=p->>'user_id';
 uid text; tenant public.lifeos_tenants%rowtype; payload jsonb:=p; r jsonb;
 user_row public.lifeos_users%rowtype; rows jsonb;
begin
 select * into tenant from lifeos_tenants where id=tid and enabled;
 if not found then return jsonb_build_object('error','invalid_tenant'); end if;
 perform set_config('lifeos.tenant',tid,true);
 if action='tenant_info' then
  return jsonb_build_object('tenant_id',tid,'calendar_id',tenant.calendar_id,'enabled',true);
 end if;
 if action='test_users' then
  select coalesce(jsonb_agg(jsonb_build_object('user_id',x.line_user_id)),'[]'::jsonb) into rows
  from (select u.line_user_id from lifeos_test_reminders t join lifeos_users u on u.user_id=t.user_id
        where u.tenant_id=tid and t.state<>'sent' and t.due_at<=now()
        and t.due_at>now()-interval '15 minutes' limit 20) x;
  return jsonb_build_object('users',rows);
 end if;
 if raw_uid is not null then
  if raw_uid !~ '^U[0-9a-f]{32}$' then return jsonb_build_object('error','invalid_user'); end if;
  uid:=case when tid='mr' then raw_uid else 'U'||md5(tid||':'||raw_uid) end;
  perform set_config('lifeos.line_user',raw_uid,true);
  payload:=payload||jsonb_build_object('user_id',uid);
  if p->>'event_id' is not null and tid<>'mr' and action<>'calendar_save' then payload:=payload||jsonb_build_object('event_id',tid||':'||(p->>'event_id')); end if;
  select * into user_row from lifeos_users where user_id=uid;
  if found and user_row.tenant_id<>tid then return jsonb_build_object('error','tenant_mismatch'); end if;
  if action='enroll' and user_row.user_id is null and not exists(
   select 1 from lifeos_invites inv where inv.tenant_id=tid and inv.code_hash=p->>'code_hash'
   and inv.claimed_by is null and inv.expires_at>now()
   and (inv.shared_owner is null or exists(select 1 from lifeos_users u where u.user_id=inv.shared_owner and u.tenant_id=tid))) then
   return jsonb_build_object('error','invalid_invite');
  end if;
 end if;
 if action='calendar_save' and p->>'calendar_id' is distinct from tenant.calendar_id then
  return jsonb_build_object('error','calendar_mismatch');
 elsif action='calendar_draft' and p->'payload'->>'calendar_id' is distinct from tenant.calendar_id then
  return jsonb_build_object('error','calendar_mismatch');
 end if;
 if action='confirm_tasks' then r:=lifeos_confirm_tasks(payload);
 elsif action like 'postpone_%' then r:=lifeos_postpone_dispatch(payload);
 elsif action like 'calendar_%' then r:=lifeos_calendar_dispatch(payload);
 elsif action like 'test_%' then r:=lifeos_test_dispatch(payload);
 else r:=lifeos_dispatch(payload);
 end if;
 if action in ('notification_users','test_users') then
  select coalesce(jsonb_agg(x.value||jsonb_build_object('user_id',u.line_user_id)),'[]'::jsonb) into rows
  from jsonb_array_elements(r->'users') x join lifeos_users u on u.user_id=x.value->>'user_id'
  where u.tenant_id=tid;
  r:=jsonb_build_object('users',rows);
 elsif action='get_user' and r->'user' is not null and r->'user'<>'null'::jsonb then
  select * into user_row from lifeos_users where user_id=uid and tenant_id=tid;
  r:=jsonb_build_object('user',r->'user'||jsonb_build_object(
   'tenant_id',tid,'tenant_calendar_id',tenant.calendar_id,
   'calendar_owner_line_id',(select line_user_id from lifeos_users where user_id=coalesce(user_row.shared_owner,uid) and tenant_id=tid)));
 end if;
 return r;
end $$;
revoke all on function public.lifeos_tenant_dispatch(jsonb) from public,anon,authenticated;
grant execute on function public.lifeos_tenant_dispatch(jsonb) to service_role;
notify pgrst,'reload schema';

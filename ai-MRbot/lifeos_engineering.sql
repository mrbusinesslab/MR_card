-- Engineering cases are private backend data; existing task permissions apply.
create table public.lifeos_engineering_cases (
 id uuid primary key default gen_random_uuid(),
 tenant_id text not null references public.lifeos_tenants(id),
 user_id text not null references public.lifeos_users(user_id),
 name text not null check(length(name) between 1 and 80),
 location text not null default '' check(length(location)<=300),
 scope text not null default '' check(length(scope)<=500),
 stage text not null default '待場勘' check(stage in ('待場勘','待報價','待確認','待施工','施工中','待驗收','已結案')),
 demo boolean not null default false,
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now(),
 unique(tenant_id,user_id,name)
);
create table public.lifeos_engineering_task_links (
 case_id uuid not null references public.lifeos_engineering_cases(id),
 task_id bigint primary key references public.lifeos_tasks(id),
 kind text not null check(kind in ('報價','備料','施工','追加','驗收','請款','其他'))
);
create index on public.lifeos_engineering_cases(tenant_id,user_id,stage);
create index on public.lifeos_engineering_task_links(case_id);
alter table public.lifeos_engineering_cases enable row level security;
alter table public.lifeos_engineering_task_links enable row level security;
revoke all on public.lifeos_engineering_cases, public.lifeos_engineering_task_links from public,anon,authenticated;
grant select,insert,update on public.lifeos_engineering_cases, public.lifeos_engineering_task_links to service_role;

create function public.lifeos_engineering_dispatch(p jsonb) returns jsonb
language plpgsql security invoker set search_path=public,pg_temp as $$
declare
 tid text:=p->>'tenant_id'; raw_uid text:=p->>'user_id'; uid text;
 action text:=p->>'action'; eid text:=p->>'event_id'; result jsonb;
 c public.lifeos_engineering_cases%rowtype; t public.lifeos_tasks%rowtype;
begin
 if raw_uid is null or raw_uid !~ '^U[0-9a-f]{32}$' then return jsonb_build_object('error','invalid_user'); end if;
 if not exists(select 1 from lifeos_tenants where id=tid and enabled) then return jsonb_build_object('error','invalid_tenant'); end if;
 uid:=case when tid='mr' then raw_uid else 'U'||md5(tid||':'||raw_uid) end;
 if not exists(select 1 from lifeos_users where user_id=uid and tenant_id=tid) then return jsonb_build_object('error','not_enrolled'); end if;
 perform set_config('lifeos.tenant',tid,true);
 perform set_config('lifeos.line_user',raw_uid,true);
 perform set_config('lifeos.actor',uid,true);
 perform pg_advisory_xact_lock(hashtextextended(tid||':engineering:'||uid,0));
 if eid is not null then
  eid:=tid||':engineering:'||eid;
  select e.result into result from lifeos_events e where e.event_id=eid and e.user_id=uid;
  if found then return result; end if;
 end if;
 if action='engineering_list' then
  select jsonb_build_object('cases',coalesce(jsonb_agg(to_jsonb(x)),'[]'::jsonb)) into result from
   (select cas.*,(select count(*) from lifeos_engineering_task_links k join lifeos_tasks item on item.id=k.task_id
      where k.case_id=cas.id and item.status not in ('完成','取消') and lifeos_can_access(uid,item.user_id,'task')) as open_tasks
    from lifeos_engineering_cases cas where cas.tenant_id=tid and lifeos_can_access(uid,cas.user_id,'task')
    order by cas.demo desc,cas.updated_at desc,cas.id limit 100) x;
  return result;
 elsif action='engineering_create' then
  if nullif(btrim(p->>'name'),'') is null or length(p->>'name')>80 or length(coalesce(p->>'location',''))>300 or length(coalesce(p->>'scope',''))>500 then
   return jsonb_build_object('error','invalid_case');
  end if;
  insert into lifeos_engineering_cases(tenant_id,user_id,name,location,scope)
   values(tid,uid,btrim(p->>'name'),coalesce(p->>'location',''),coalesce(p->>'scope',''))
   on conflict(tenant_id,user_id,name) do nothing returning * into c;
  if not found then return jsonb_build_object('error','duplicate_case'); end if;
  result:=jsonb_build_object('case',to_jsonb(c));
 else
  select * into c from lifeos_engineering_cases where id=(p->>'case_id')::uuid and tenant_id=tid;
  if not found or not lifeos_can_access(uid,c.user_id,'task') then return jsonb_build_object('error','not_found'); end if;
  if action='engineering_detail' then
   select jsonb_build_object('case',to_jsonb(c),'tasks',coalesce(jsonb_agg(to_jsonb(x)),'[]'::jsonb)) into result from
    (select item.*,k.kind from lifeos_engineering_task_links k join lifeos_tasks item on item.id=k.task_id
     where k.case_id=c.id and item.tenant_id=tid and lifeos_can_access(uid,item.user_id,'task')
     order by item.due_at nulls last,item.id limit 200) x;
   return result;
  elsif action='engineering_stage' then
   if p->>'stage' not in ('待場勘','待報價','待確認','待施工','施工中','待驗收','已結案') or p->>'stage' is null then
    return jsonb_build_object('error','invalid_stage');
   end if;
   update lifeos_engineering_cases set stage=p->>'stage',updated_at=now() where id=c.id returning * into c;
   result:=jsonb_build_object('case',to_jsonb(c));
  elsif action='engineering_add_task' then
   if nullif(btrim(p->>'title'),'') is null or length(p->>'title')>300 or p->>'kind' is null or p->>'kind' not in ('報價','備料','施工','追加','驗收','請款','其他') then
    return jsonb_build_object('error','invalid_task');
   end if;
   insert into lifeos_tasks(user_id,tenant_id,title,category,due_at,original_text,last_modified_by)
    values(c.user_id,tid,(case when c.demo then '【示範】' else '' end)||c.name||'｜'||btrim(p->>'title'),
     '工程／'||(p->>'kind'),nullif(p->>'due_at','')::timestamptz,
     jsonb_build_object('engineering_case_id',c.id,'text',p->>'title')::text,uid) returning * into t;
   insert into lifeos_engineering_task_links(case_id,task_id,kind) values(c.id,t.id,p->>'kind');
   result:=jsonb_build_object('task',to_jsonb(t),'case',to_jsonb(c));
  else return jsonb_build_object('error','invalid_action'); end if;
 end if;
 if eid is not null then insert into lifeos_events(event_id,user_id,result) values(eid,uid,result) on conflict do nothing; end if;
 return result;
end $$;
revoke all on function public.lifeos_engineering_dispatch(jsonb) from public,anon,authenticated;
grant execute on function public.lifeos_engineering_dispatch(jsonb) to service_role;

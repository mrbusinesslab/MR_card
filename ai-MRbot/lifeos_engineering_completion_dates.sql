-- Record actual phase completion dates from this release onward.
-- Historical phases retain unknown dates; no dates are inferred or fabricated.
create or replace function public.lifeos_engineering_workflow_dispatch(p jsonb) returns jsonb
language plpgsql security invoker set search_path=public,pg_temp as $$
declare tid text:=p->>'tenant_id'; raw_uid text:=p->>'user_id'; uid text;
 action text:=p->>'action'; eid text:=p->>'event_id'; c lifeos_engineering_cases%rowtype;
 phase_index int; current_index int; result jsonb; state text; finish_date date; completed_date date; old_state text;
begin
 if raw_uid is null or raw_uid !~ '^U[0-9a-f]{32}$' then return jsonb_build_object('error','invalid_user'); end if;
 if not exists(select 1 from lifeos_tenants where id=tid and enabled) then return jsonb_build_object('error','invalid_tenant'); end if;
 uid:=case when tid='mr' then raw_uid else 'U'||md5(tid||':'||raw_uid) end;
 if not exists(select 1 from lifeos_users where user_id=uid and tenant_id=tid) then return jsonb_build_object('error','not_enrolled'); end if;
 perform pg_advisory_xact_lock(hashtextextended(tid||':workflow:'||uid,0));
 select * into c from lifeos_engineering_cases where id=(p->>'case_id')::uuid and tenant_id=tid for update;
 if not found or not lifeos_can_access(uid,c.user_id,'task') then return jsonb_build_object('error','not_found'); end if;
 if action='engineering_workflow_get' then return jsonb_build_object('case',to_jsonb(c)); end if;
 if eid is not null then
  eid:=tid||':engineering-workflow:'||eid;
  select e.result into result from lifeos_events e where e.event_id=eid and e.user_id=uid;
  if found then return result; end if;
 end if;
 if action in ('engineering_workflow_status','engineering_workflow_note') then
  phase_index:=array_position(array['appointment','quote','contract','materials','construction','finishing','acceptance'],p->>'phase')-1;
  if phase_index is null then return jsonb_build_object('error','invalid_phase'); end if;
  if action='engineering_workflow_status' then
   state:=p->>'status';
   if state is null or state not in ('未開始','進行中','已完成','不適用') then return jsonb_build_object('error','invalid_status'); end if;
   old_state:=c.workflow->phase_index->>'status';
   if p ? 'expected_status' and p->>'expected_status' is distinct from old_state then
    return jsonb_build_object('error','status_conflict');
   end if;
   if p ? 'completed_on' then
    if state<>'已完成' then return jsonb_build_object('error','invalid_date'); end if;
    begin completed_date:=nullif(p->>'completed_on','')::date;
    exception when invalid_datetime_format or datetime_field_overflow then return jsonb_build_object('error','invalid_date'); end;
    if completed_date is null or completed_date>(now() at time zone 'Asia/Taipei')::date then
     return jsonb_build_object('error','invalid_date');
    end if;
    c.workflow:=jsonb_set(c.workflow,array[phase_index::text,'completed_on'],to_jsonb(completed_date));
   elsif state='已完成' and old_state<>'已完成' then
    c.workflow:=jsonb_set(c.workflow,array[phase_index::text,'completed_on'],to_jsonb((now() at time zone 'Asia/Taipei')::date));
   elsif state<>'已完成' then
    c.workflow:=jsonb_set(c.workflow,array[phase_index::text],(c.workflow->phase_index)-'completed_on');
   end if;
   c.workflow:=jsonb_set(c.workflow,array[phase_index::text,'status'],to_jsonb(state));
  else
   if p->>'note' is null or length(p->>'note')>4000 then return jsonb_build_object('error','invalid_note'); end if;
   if p ? 'expected_note' and p->>'expected_note' is distinct from c.workflow->phase_index->>'note' then
    return jsonb_build_object('error','note_conflict');
   end if;
   c.workflow:=jsonb_set(c.workflow,array[phase_index::text,'note'],to_jsonb(p->>'note'));
  end if;
 elsif action='engineering_workflow_finish' then
  begin finish_date:=nullif(p->>'expected_finish','')::date;
  exception when invalid_datetime_format or datetime_field_overflow then return jsonb_build_object('error','invalid_date'); end;
  c.expected_finish:=finish_date;
 else return jsonb_build_object('error','invalid_action'); end if;
 select (ord-1)::int into current_index from jsonb_array_elements(c.workflow) with ordinality x(v,ord)
 where v->>'status'='進行中' order by ord limit 1;
 if current_index is null then
  select (ord-1)::int into current_index from jsonb_array_elements(c.workflow) with ordinality x(v,ord)
  where v->>'status'='未開始' order by ord limit 1;
 end if;
 c.stage:=case when current_index is not null then (array['待場勘','待報價','待確認','待施工','施工中','施工中','待驗收'])[current_index+1]
  when exists(select 1 from jsonb_array_elements(c.workflow)x where x->>'status'='已完成') then '已結案' else '待場勘' end;
 update lifeos_engineering_cases set workflow=c.workflow,expected_finish=c.expected_finish,stage=c.stage,updated_at=now() where id=c.id returning * into c;
 result:=jsonb_build_object('case',to_jsonb(c));
 perform set_config('lifeos.tenant',tid,true);
 if eid is not null then insert into lifeos_events(event_id,user_id,result) values(eid,uid,result) on conflict do nothing; end if;
 return result;
end $$;
revoke all on function public.lifeos_engineering_workflow_dispatch(jsonb) from public,anon,authenticated;
grant execute on function public.lifeos_engineering_workflow_dispatch(jsonb) to service_role;

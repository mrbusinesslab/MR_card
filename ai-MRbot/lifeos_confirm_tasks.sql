-- Isolated confirmation extension; existing dispatcher and tables remain intact.
create function public.lifeos_confirm_tasks(p jsonb) returns jsonb
language plpgsql security invoker set search_path=public,pg_temp as $$
declare
 uid text:=p->>'user_id'; eid text:=p->>'event_id';
 d jsonb; res jsonb; item jsonb; rows jsonb:='[]'::jsonb;
 old_ids bigint[]; task public.lifeos_tasks%rowtype;
begin
 if p->>'action' is distinct from 'confirm_tasks' or uid is null or uid !~ '^U[0-9a-f]{32}$' then
   return jsonb_build_object('error','invalid_action');
 end if;
 perform pg_advisory_xact_lock(hashtextextended(uid,0));
 if eid is not null then
   select result into res from public.lifeos_events where user_id=uid and event_id=eid;
   if found then return res; end if;
 end if;
 select draft into d from public.lifeos_users where user_id=uid;
 select coalesce(array_agg(id),'{}'::bigint[]) into old_ids from public.lifeos_tasks where user_id=uid;
 res:=public.lifeos_dispatch(p||jsonb_build_object('action','confirm'));
 if res ? 'error' then return res; end if;
 for item in select value from jsonb_array_elements(res->'tasks') loop
   select * into task from public.lifeos_tasks where user_id=uid and id=(item->>'id')::bigint;
   if not found then raise exception 'Owned task missing'; end if;
   -- Only initialize new tasks. Never overwrite status of a merged existing task.
   if not(task.id=any(old_ids)) and task.status='未開始' and exists(
     select 1 from jsonb_array_elements(d->'tasks') x where x->>'title'=task.title
       and x->>'original_text'=task.original_text and x->>'status'='等待對方') then
     update public.lifeos_tasks set status='等待對方',updated_at=now() where id=task.id and user_id=uid returning * into task;
   end if;
   rows:=rows||jsonb_build_array(to_jsonb(task));
 end loop;
 res:=jsonb_build_object('tasks',rows);
 if eid is not null then update public.lifeos_events set result=res where user_id=uid and event_id=eid; end if;
 return res;
end $$;
revoke all on function public.lifeos_confirm_tasks(jsonb) from public,anon,authenticated;
grant execute on function public.lifeos_confirm_tasks(jsonb) to service_role;

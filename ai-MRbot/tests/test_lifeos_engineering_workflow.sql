begin;
do $test$
declare raw_uid text:='U'||repeat('7',32); member text:='U'||repeat('8',32); uid text; cid uuid; r jsonb; initial jsonb;
begin
 perform set_config('lifeos.tenant','',true);
 insert into lifeos_tenants(id,name,calendar_id,gateway_key_hash) values
 ('flow_verify_a','workflow A','flow-cal-a',repeat('f',64)),('flow_verify_b','workflow B','flow-cal-b',repeat('0',64));
 insert into lifeos_invites(tenant_id,code_hash,label,expires_at) values
 ('flow_verify_a','flow-code-a','A',now()+interval '1 hour'),('flow_verify_b','flow-code-b','B',now()+interval '1 hour');
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','enroll','user_id',raw_uid,'code_hash','flow-code-a'));
 uid:=r->'user'->>'user_id';
 perform lifeos_tenant_dispatch(jsonb_build_object('tenant_id','flow_verify_b','action','enroll','user_id',raw_uid,'code_hash','flow-code-b'));
 r:=lifeos_engineering_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_create','user_id',raw_uid,'name','流程測試'));
 cid:=(r->'case'->>'id')::uuid;initial:=r->'case'->'workflow';assert jsonb_array_length(initial)=7,'missing default phases';
 assert initial->3->>'status'='未開始','default wrongly advances progress';
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_workflow_note','user_id',raw_uid,'case_id',cid,'phase','materials','note','缺兩個接頭','expected_note',''));
 assert r->'case'->'workflow'->3->>'note'='缺兩個接頭','note not saved';
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_workflow_status','user_id',raw_uid,'case_id',cid,'phase','materials','status','不適用','event_id','skip'));
 assert r->'case'->'workflow'->3->>'note'='缺兩個接頭','status update lost notes';
 assert r->'case'->'workflow'->3->>'status'='不適用','skip not stored';
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_workflow_status','user_id',raw_uid,'case_id',cid,'phase','materials','status','已完成','event_id','skip'));
 assert r->'case'->'workflow'->3->>'status'='不適用','webhook retry overwrote status';
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_workflow_note','user_id',raw_uid,'case_id',cid,'phase','materials','note','錯誤覆蓋','expected_note',''));
 assert r->>'error'='note_conflict','concurrent note edit not protected';
 -- Newly completed phases get a Taipei date; notes and other phases survive.
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_workflow_status','user_id',raw_uid,'case_id',cid,'phase','materials','status','已完成','event_id','done-date'));
 assert r->'case'->'workflow'->3->>'completed_on'=((now() at time zone 'Asia/Taipei')::date)::text,'missing Taipei completion date';
 assert r->'case'->'workflow'->3->>'note'='缺兩個接頭','completion lost note';
 assert r->'case'->'workflow'->2=initial->2,'completion changed other phase';
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_workflow_status','user_id',raw_uid,'case_id',cid,'phase','materials','status','已完成','expected_status','已完成','completed_on','2020-10-20','event_id','date-backfill'));
 assert r->'case'->'workflow'->3->>'completed_on'='2020-10-20','backfill failed';
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_workflow_status','user_id',raw_uid,'case_id',cid,'phase','materials','status','已完成'));
 assert r->'case'->'workflow'->3->>'completed_on'='2020-10-20','same status reset completion date';
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_workflow_status','user_id',raw_uid,'case_id',cid,'phase','materials','status','已完成','completed_on','2099-01-01'));
 assert r->>'error'='invalid_date','future completion accepted';
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_workflow_status','user_id',raw_uid,'case_id',cid,'phase','materials','status','已完成','completed_on','invalid'));
 assert r->>'error'='invalid_date','invalid date accepted';
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_workflow_status','user_id',raw_uid,'case_id',cid,'phase','materials','status','不適用'));
 assert not (r->'case'->'workflow'->3 ? 'completed_on'),'reopened date remained';
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_workflow_status','user_id',raw_uid,'case_id',cid,'phase','materials','status','已完成','expected_status','已完成','completed_on','2020-10-20'));
 assert r->>'error'='status_conflict','backfill overwrote concurrent status';
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_workflow_status','user_id',raw_uid,'case_id',cid,'phase','materials','status','已完成','completed_on','2020-10-21','event_id','date-backfill'));
 assert r->'case'->'workflow'->3->>'completed_on'='2020-10-20','retry changed date';
 -- Restores the persisted skipped state for the original permission/date tests.
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_b','action','engineering_workflow_get','user_id',raw_uid,'case_id',cid));
 assert r->>'error'='not_found','workflow crossed tenant';
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_b','action','engineering_workflow_status','user_id',raw_uid,'case_id',cid,'phase','materials','status','已完成'));
 assert r->>'error'='not_found','cross-tenant update accepted';
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_workflow_status','user_id',raw_uid,'case_id',cid,'phase','fake','status','已完成'));
 assert r->>'error'='invalid_phase','invalid phase accepted';
 perform set_config('lifeos.tenant','',true);
 update lifeos_users set share_tasks=true where user_id=uid;
 insert into lifeos_invites(tenant_id,code_hash,label,expires_at,shared_owner) values('flow_verify_a','flow-member-code','member',now()+interval '1 hour',uid);
 perform lifeos_tenant_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','enroll','user_id',member,'code_hash','flow-member-code'));
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_workflow_finish','user_id',member,'case_id',cid,'expected_finish','2026-10-30'));
 assert r->'case'->>'expected_finish'='2026-10-30','shared member date failed';
 assert r->'case'->'workflow'->3->>'status'='不適用','date changed phases';
 perform set_config('lifeos.tenant','',true);
 update lifeos_users set share_tasks=false where user_id=uid;
 r:=lifeos_engineering_workflow_dispatch(jsonb_build_object('tenant_id','flow_verify_a','action','engineering_workflow_get','user_id',member,'case_id',cid));
 assert r->>'error'='not_found','revoked member retained workflow access';
 assert not has_function_privilege('authenticated','lifeos_engineering_workflow_dispatch(jsonb)','EXECUTE'),'public workflow RPC';
 assert lifeos_engineering_initial_workflow('施工中')->4->>'status'='進行中','legacy phase mapping wrong';
end $test$;
rollback;

begin;
do $test$
declare raw_uid text:='U'||repeat('7',32); member text:='U'||repeat('8',32); uid text; r jsonb; cid uuid; taskid bigint;
begin
 perform set_config('lifeos.tenant','',true);
 insert into lifeos_tenants(id,name,calendar_id,gateway_key_hash) values
 ('eng_verify_a','engineering A','eng-verify-a',repeat('d',64)),('eng_verify_b','engineering B','eng-verify-b',repeat('e',64));
 insert into lifeos_invites(tenant_id,code_hash,label,expires_at) values
 ('eng_verify_a','eng-code-a','A',now()+interval '1 hour'),('eng_verify_b','eng-code-b','B',now()+interval '1 hour');
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id','eng_verify_a','action','enroll','user_id',raw_uid,'code_hash','eng-code-a'));
 uid:=r->'user'->>'user_id';
 perform lifeos_tenant_dispatch(jsonb_build_object('tenant_id','eng_verify_b','action','enroll','user_id',raw_uid,'code_hash','eng-code-b'));
 r:=lifeos_engineering_dispatch(jsonb_build_object('tenant_id','eng_verify_a','action','engineering_create','user_id',raw_uid,'event_id','same','name','工程測試','location','虛構','scope','水電'));
 cid:=(r->'case'->>'id')::uuid;assert cid is not null,'case create failed';
 r:=lifeos_engineering_dispatch(jsonb_build_object('tenant_id','eng_verify_a','action','engineering_list','user_id',raw_uid));
 assert jsonb_array_length(r->'cases')=1,'case list failed';
 r:=lifeos_engineering_dispatch(jsonb_build_object('tenant_id','eng_verify_a','action','engineering_create','user_id',raw_uid,'event_id','same','name','工程測試','location','虛構','scope','水電'));
 assert (r->'case'->>'id')::uuid=cid,'webhook retry created another case';
 r:=lifeos_engineering_dispatch(jsonb_build_object('tenant_id','eng_verify_b','action','engineering_detail','user_id',raw_uid,'case_id',cid));
 assert r->>'error'='not_found','case leaked across tenants';
 r:=lifeos_engineering_dispatch(jsonb_build_object('tenant_id','eng_verify_b','action','engineering_stage','user_id',raw_uid,'case_id',cid,'stage','已結案'));
 assert r->>'error'='not_found','cross tenant mutation accepted';
 r:=lifeos_engineering_dispatch(jsonb_build_object('tenant_id','eng_verify_a','action','engineering_add_task','user_id',raw_uid,'case_id',cid,'kind','備料','title','買材料','due_at',now()+interval '1 day'));
 taskid:=(r->'task'->>'id')::bigint;assert taskid is not null,'linked task missing';
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id','eng_verify_a','action','list','user_id',raw_uid));
 assert exists(select 1 from jsonb_array_elements(r->'tasks')t where (t->>'id')::bigint=taskid),'linked item absent from reminder task list';
 perform set_config('lifeos.tenant','',true);
 update lifeos_users set share_tasks=true where user_id=uid;
 insert into lifeos_invites(tenant_id,code_hash,label,expires_at,shared_owner) values('eng_verify_a','eng-member-code','member',now()+interval '1 hour',uid);
 perform lifeos_tenant_dispatch(jsonb_build_object('tenant_id','eng_verify_a','action','enroll','user_id',member,'code_hash','eng-member-code'));
 r:=lifeos_engineering_dispatch(jsonb_build_object('tenant_id','eng_verify_a','action','engineering_detail','user_id',member,'case_id',cid));
 assert jsonb_array_length(r->'tasks')=1,'shared member cannot see case items';
 r:=lifeos_engineering_dispatch(jsonb_build_object('tenant_id','eng_verify_a','action','engineering_stage','user_id',member,'case_id',cid,'stage','待驗收'));
 assert r->'case'->>'stage'='待驗收','member progress update failed';
 perform set_config('lifeos.tenant','',true);
 update lifeos_users set share_tasks=false where user_id=uid;
 r:=lifeos_engineering_dispatch(jsonb_build_object('tenant_id','eng_verify_a','action','engineering_detail','user_id',member,'case_id',cid));
 assert r->>'error'='not_found','revoked case access remained';
 assert not has_table_privilege('anon','lifeos_engineering_cases','SELECT'),'cases public';
 assert not has_function_privilege('authenticated','lifeos_engineering_dispatch(jsonb)','EXECUTE'),'RPC public';
end $test$;
rollback;

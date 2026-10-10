-- Run only after lifeos_tenants.sql. All fixtures roll back, including invites.
BEGIN;
DO $test$
DECLARE
 raw_user text:='U'||repeat('1',32); member text:='U'||repeat('2',32);
 a text:='verify_aa'; b text:='verify_bb'; au text; bu text; mu text;
 r jsonb; atask bigint; btask bigint; event_record bigint;
BEGIN
 perform set_config('lifeos.tenant','',true);
 perform set_config('lifeos.line_user','',true);
 insert into lifeos_tenants(id,name,calendar_id,gateway_key_hash) values
 (a,'verification A','verify-calendar-aa',repeat('b',64)),
 (b,'verification B','verify-calendar-bb',repeat('c',64));
 insert into lifeos_invites(tenant_id,code_hash,label,expires_at) values
 (a,'verify-code-aa','A',now()+interval '1 hour'),
 (b,'verify-code-bb','B',now()+interval '1 hour');
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',a,'action','enroll','user_id',raw_user,'code_hash','verify-code-bb'));
 assert r->>'error'='invalid_invite','Other customer invite accepted';
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',a,'action','enroll','user_id',raw_user,'code_hash','verify-code-aa'));
 au:=r->'user'->>'user_id'; assert au is not null,'A enrollment failed';
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',b,'action','enroll','user_id',raw_user,'code_hash','verify-code-bb'));
 bu:=r->'user'->>'user_id'; assert bu is not null and au<>bu,'Same LINE account was not isolated';
 assert (select count(*) from lifeos_users where line_user_id=raw_user and tenant_id in(a,b))=2,'Original LINE identity missing';
 perform lifeos_tenant_dispatch(jsonb_build_object('tenant_id',a,'action','draft','user_id',raw_user,'event_id','same-webhook-id','tasks',jsonb_build_array(jsonb_build_object('title','A task','original_text','A task','status','未開始'))));
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',a,'action','confirm_tasks','user_id',raw_user));
 atask:=(r->'tasks'->0->>'id')::bigint; assert atask is not null,'A task failed';
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',b,'action','get_user','user_id',raw_user));
 assert coalesce(jsonb_array_length(r->'user'->'pending_tasks'),0)=0,'Pending tasks crossed customers';
 perform lifeos_tenant_dispatch(jsonb_build_object('tenant_id',b,'action','draft','user_id',raw_user,'event_id','same-webhook-id','tasks',jsonb_build_array(jsonb_build_object('title','B task','original_text','B task','status','未開始'))));
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',b,'action','confirm_tasks','user_id',raw_user));
 btask:=(r->'tasks'->0->>'id')::bigint; assert btask is not null and btask<>atask,'Webhook identity crossed customers';
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',b,'action','list','user_id',raw_user));
 assert jsonb_array_length(r->'tasks')=1 and (r->'tasks'->0->>'id')::bigint=btask,'A task leaked into B';
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',b,'action','update','user_id',raw_user,'task_id',atask,'status','完成'));
 assert r->>'error'='not_found','B changed A task';
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',a,'action','calendar_save','user_id',raw_user,'calendar_id','verify-calendar-bb','event_id','abcdef','title','wrong calendar'));
 assert r->>'error'='calendar_mismatch','Wrong calendar accepted';
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',a,'action','calendar_save','user_id',raw_user,'calendar_id','verify-calendar-aa','event_id','abcdef','title','A event'));
 event_record:=(r->'event'->>'id')::bigint;
 assert r->'event'->>'event_id'='abcdef','Google event ID must remain unchanged';
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',b,'action','calendar_event','user_id',raw_user,'id',event_record));
 assert r->'event'='null'::jsonb,'Calendar record crossed customers';
 perform lifeos_tenant_dispatch(jsonb_build_object('tenant_id',a,'action','calendar_draft','user_id',raw_user,'payload',jsonb_build_object('calendar_id','verify-calendar-aa','operation','create')));
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',b,'action','calendar_get_draft','user_id',raw_user));
 assert r->'draft'='null'::jsonb,'Calendar draft crossed customers';
 perform set_config('lifeos.tenant','',true); perform set_config('lifeos.line_user','',true);
 update lifeos_users set share_tasks=true,share_calendar=true,notifications=true where user_id=au;
 insert into lifeos_invites(tenant_id,code_hash,label,expires_at,shared_owner) values(a,'verify-member-aa','member',now()+interval '1 hour',au);
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',a,'action','enroll','user_id',member,'code_hash','verify-member-aa'));
 mu:=r->'user'->>'user_id'; assert lifeos_can_access(mu,au,'task') and not lifeos_can_access(mu,bu,'task'),'Shared group escaped tenant';
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',a,'action','update','user_id',member,'task_id',atask,'status','完成'));
 assert r->'task'->>'user_id'=au and r->'task'->>'last_modified_by'=mu,'Creator or modifier lost';
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',a,'action','notification_users'));
 assert jsonb_array_length(r->'users')=1 and r->'users'->0->>'user_id'=raw_user,'Push recipients not mapped to original LINE ID';
 r:=lifeos_tenant_dispatch(jsonb_build_object('tenant_id',b,'action','notification_users'));
 assert jsonb_array_length(r->'users')=0,'Other tenant push recipients exposed';
 assert not has_table_privilege('anon','lifeos_tenants','SELECT'),'Tenant registry publicly readable';
 assert not has_function_privilege('authenticated','lifeos_tenant_dispatch(jsonb)','EXECUTE'),'Tenant dispatcher publicly callable';
END $test$;
ROLLBACK;

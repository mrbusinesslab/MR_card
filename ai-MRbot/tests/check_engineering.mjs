import {PGlite} from '@electric-sql/pglite';
import {readFileSync} from 'node:fs';
import assert from 'node:assert/strict';
const db=new PGlite();
try {
await db.exec(readFileSync('tests/lifeos_baseline.sql','utf8'));
await db.exec("insert into lifeos_config values('gateway_key_hash',repeat('a',64));insert into lifeos_users(user_id,label) values('U'||repeat('9',32),'baseline MR');insert into lifeos_calendar_events(user_id,calendar_id,event_id,title) values('U'||repeat('9',32),'fixture-mr-calendar','fixture-event','baseline event');");
await db.exec(readFileSync('lifeos_tenants.sql','utf8'));
await db.exec(readFileSync('lifeos_engineering.sql','utf8'));
await db.exec(readFileSync('tests/test_lifeos_engineering.sql','utf8'));
await db.exec(`select set_config('lifeos.tenant','',false);select set_config('lifeos.line_user','',false);
insert into lifeos_tenants(id,name,calendar_id,gateway_key_hash) values('flow_migrate_fixture','migration','flow-migration-cal',repeat('1',64));
insert into lifeos_users(user_id,line_user_id,tenant_id,label) values('U'||repeat('4',32),'U'||repeat('4',32),'flow_migrate_fixture','migration');
do $$ declare cid uuid; tid bigint; begin
insert into lifeos_engineering_cases(tenant_id,user_id,name,stage) values('flow_migrate_fixture','U'||repeat('4',32),'migration case','施工中') returning id into cid;
insert into lifeos_tasks(user_id,tenant_id,title,original_text,category) values('U'||repeat('4',32),'flow_migrate_fixture','migration case｜缺小接頭','note','工程／備料') returning id into tid;
insert into lifeos_engineering_task_links values(cid,tid,'備料');end $$;`);
const before=(await db.query('select to_jsonb(t) as row from lifeos_tasks t order by id')).rows;
await db.exec(readFileSync('lifeos_engineering_workflow.sql','utf8'));
assert.deepEqual((await db.query('select to_jsonb(t) as row from lifeos_tasks t order by id')).rows,before);
const workflow=(await db.query("select workflow from lifeos_engineering_cases where tenant_id='flow_migrate_fixture'")).rows[0].workflow;
assert.ok(workflow[3].note.includes('缺小接頭'));
assert.equal(workflow[4].status,'進行中');
await db.exec(readFileSync('tests/test_lifeos_engineering_workflow.sql','utf8'));
console.log('Engineering PostgreSQL checks passed: persistence, idempotency, task linkage, sharing, revocation, tenant isolation, privileges.');
} catch(e) {console.error(e.message,e.detail,e.where);process.exitCode=1;} finally {await db.close();}

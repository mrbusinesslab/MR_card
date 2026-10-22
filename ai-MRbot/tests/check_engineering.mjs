import {PGlite} from '@electric-sql/pglite';
import {readFileSync} from 'node:fs';
const db=new PGlite();
try {
await db.exec(readFileSync('tests/lifeos_baseline.sql','utf8'));
await db.exec("insert into lifeos_config values('gateway_key_hash',repeat('a',64));insert into lifeos_users(user_id,label) values('U'||repeat('9',32),'baseline MR');insert into lifeos_calendar_events(user_id,calendar_id,event_id,title) values('U'||repeat('9',32),'fixture-mr-calendar','fixture-event','baseline event');");
await db.exec(readFileSync('lifeos_tenants.sql','utf8'));
await db.exec(readFileSync('lifeos_engineering.sql','utf8'));
await db.exec(readFileSync('tests/test_lifeos_engineering.sql','utf8'));
console.log('Engineering PostgreSQL checks passed: persistence, idempotency, task linkage, sharing, revocation, tenant isolation, privileges.');
} catch(e) {console.error(e.message,e.detail,e.where);process.exitCode=1;} finally {await db.close();}

import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
let handler; let requests=[]; let authorized=true;
const context={Deno:{env:{get:()=> 'fixture'},serve:fn=>{handler=fn}},crypto:webcrypto,TextEncoder,Uint8Array,Response,
 fetch:async(url,options)=>{requests.push({url,options});return new Response(JSON.stringify(url.includes('/lifeos_tenants?')?(authorized?[{id:'aa'}]:[]):{ok:true}));}};
vm.runInNewContext(readFileSync('lifeos_gateway/index.ts','utf8'),context);
const request=body=>new Request('https://fixture',{method:'POST',headers:{'X-LifeOS-Key':'x'.repeat(48)},body:JSON.stringify(body)});
assert.equal((await handler(request({action:'get_user',tenant_id:'bb'}))).status,403);
assert.equal(requests.length,1);
requests=[];
assert.equal((await handler(request({action:'get_user'}))).status,200);
assert.equal(JSON.parse(requests[1].options.body).p.tenant_id,'aa');
requests=[];authorized=false;
assert.equal((await handler(request({action:'get_user'}))).status,401);
assert.equal(requests.length,1);
console.log('Gateway checks passed: secret binding, forged tenant rejection, legacy MR payload compatibility, unauthorized request rejection.');

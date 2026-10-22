// Deploy only after lifeos_tenants.sql has passed verification.
const url = Deno.env.get('SUPABASE_URL');
const key = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY');
const headers = {apikey:key, Authorization:`Bearer ${key}`, 'Content-Type':'application/json'};
const actions = new Set(['tenant_info','confirm_tasks','postpone_get','postpone_start','postpone_cancel','postpone_finish','get_user','enroll','mode','notifications','draft','discard','confirm','list','update','notification_users','notification_claim','notification_finish','test_schedule','test_users','test_claim','test_finish','calendar_draft','calendar_get_draft','calendar_discard','calendar_save','calendar_events','calendar_event']);
Deno.serve(async req => {
  if (req.method !== 'POST') return new Response('Method not allowed',{status:405});
  const secret=req.headers.get('X-LifeOS-Key') || '';
  if (secret.length<40 || secret.length>200) return new Response('Unauthorized',{status:401});
  try {
    const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(secret)))].map(x=>x.toString(16).padStart(2,'0')).join('');
    const check=await fetch(`${url}/rest/v1/lifeos_tenants?gateway_key_hash=eq.${hash}&enabled=eq.true&select=id`,{headers});
    if (!check.ok) throw new Error('configuration unavailable');
    const tenants=await check.json();
    if (tenants.length !== 1) return new Response('Unauthorized',{status:401});
    const raw=await req.text();
    if (raw.length>20000) return new Response('Payload too large',{status:413});
    let data;
    try {data=JSON.parse(raw);} catch {return new Response('Invalid JSON',{status:400});}
    if (!data || Array.isArray(data) || !actions.has(data.action)) return new Response('Invalid action',{status:400});
    const tenant=tenants[0].id;
    if (data.tenant_id !== undefined && data.tenant_id !== tenant) return new Response('Tenant mismatch',{status:403});
    // The secret, never the request body, decides the customer's identity.
    data.tenant_id=tenant;
    const response=await fetch(`${url}/rest/v1/rpc/lifeos_tenant_dispatch`,{method:'POST',headers,body:JSON.stringify({p:data})});
    if (!response.ok) throw new Error('database unavailable');
    return new Response(await response.text(),{headers:{'Content-Type':'application/json'}});
  } catch {
    return new Response(JSON.stringify({error:'storage_unavailable'}),{status:503,headers:{'Content-Type':'application/json'}});
  }
});

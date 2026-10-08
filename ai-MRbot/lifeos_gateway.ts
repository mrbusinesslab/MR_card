// Server-to-server gateway. Secret is generated at deployment, never in source.
const url = Deno.env.get("SUPABASE_URL")!;
const key = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const headers = { apikey: key, Authorization: `Bearer ${key}`, "Content-Type": "application/json" };
const actions = new Set(["get_user","enroll","mode","notifications","draft","discard","confirm","list","update","notification_users","notification_claim","notification_finish"]);

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return new Response("Method not allowed", {status:405});
  const secret = req.headers.get("X-LifeOS-Key") || "";
  if (secret.length < 40 || secret.length > 200) return new Response("Unauthorized", {status:401});
  try {
    const hash = [...new Uint8Array(await crypto.subtle.digest("SHA-256",new TextEncoder().encode(secret)))].map(x=>x.toString(16).padStart(2,"0")).join("");
    const check = await fetch(`${url}/rest/v1/lifeos_config?key=eq.gateway_key_hash&select=value`, {headers});
    if (!check.ok) throw new Error("configuration unavailable");
    const config = await check.json();
    if (config.length !== 1 || config[0].value !== hash) return new Response("Unauthorized", {status:401});
    const raw = await req.text();
    if (raw.length > 20000) return new Response("Payload too large", {status:413});
    const data = JSON.parse(raw);
    if (!actions.has(data.action)) return new Response("Invalid action", {status:400});
    const response = await fetch(`${url}/rest/v1/rpc/lifeos_dispatch`, {method:"POST",headers,body:JSON.stringify({p:data})});
    if (!response.ok) throw new Error("database operation failed");
    return new Response(await response.text(), {headers:{"Content-Type":"application/json"}});
  } catch {
    return new Response(JSON.stringify({error:"storage_unavailable"}), {status:503,headers:{"Content-Type":"application/json"}});
  }
});

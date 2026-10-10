"""Generate offline customer setup files. Never provisions cloud resources."""
import argparse
import hashlib
import json
import os
import re
import secrets
from pathlib import Path
from lifeos_settings import TENANT_PATTERN, REQUIRED

def generate(tenant, name, calendar, owner, base_url, output):
    if not TENANT_PATTERN.fullmatch(tenant) or tenant == 'mr':
        raise ValueError('Use a new customer identifier, not mr')
    if not re.fullmatch(r'U[0-9a-f]{32}', owner):
        raise ValueError('Invalid owner LINE user ID')
    if not calendar or any(c in calendar for c in '\r\n'):
        raise ValueError('Calendar ID is required')
    if not base_url.startswith('https://'):
        raise ValueError('HTTPS public URL is required')
    output = Path(output)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    prefix = 'CLIENT_' + tenant.upper().replace('-','_DASH_') + '_'
    refs = {key: prefix+key for key in REQUIRED}
    gateway, cron, invite = (secrets.token_urlsafe(48) for _ in range(3))
    values = {key:'' for key in REQUIRED}
    values.update(LIFEOS_GATEWAY_KEY=gateway, LIFEOS_CRON_KEY=cron,
                  LIFEOS_GOOGLE_CALENDAR_ID=calendar, LIFEOS_GOOGLE_USER_ID=owner,
                  LIFEOS_PUBLIC_BASE_URL=base_url.rstrip('/')+'/clients/'+tenant)
    def private_file(filename, content):
        fd = os.open(output/filename, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        with os.fdopen(fd,'w') as stream: stream.write(content)
    private_file('environment.json',json.dumps({refs[k]:v for k,v in values.items()},ensure_ascii=False,indent=2)+'\n')
    private_file('activation.txt','啟用助理 '+invite+'\n')
    manifest = {'version':1,'clients':[{'tenant_id':tenant,'name':name,'enabled':False,'reminder_hour':9,'env':refs}]}
    (output/'clients.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    quote = lambda value: "'"+value.replace("'","''")+"'"
    # Disabled until configuration and isolation checks are complete.
    sql = ('BEGIN;\nINSERT INTO public.lifeos_tenants(id,name,calendar_id,gateway_key_hash,enabled) VALUES ('
           + ','.join(map(quote,[tenant,name,calendar,hashlib.sha256(gateway.encode()).hexdigest()]))+',false);\n'
           + 'INSERT INTO public.lifeos_invites(code_hash,label,expires_at,tenant_id) VALUES ('
           + quote(hashlib.sha256(invite.encode()).hexdigest())+','+quote(name+' owner')+",now()+interval '7 days',"+quote(tenant)+');\nCOMMIT;\n')
    (output/'register.sql').write_text(sql)
    (output/'.gitignore').write_text('*\n')
    return output

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for flag in ('tenant','name','calendar','owner','base-url','output'):
        parser.add_argument('--'+flag,required=True)
    args=parser.parse_args()
    generate(args.tenant,args.name,args.calendar,args.owner,args.base_url,args.output)
    print('Setup files created; customer remains disabled. No cloud resources were created.')
if __name__=='__main__': main()

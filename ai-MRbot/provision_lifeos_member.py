"""Prepare a private one-use member invite; never connects to a database."""
import argparse
import hashlib
import os
import re
import secrets
from pathlib import Path
from lifeos_settings import TENANT_PATTERN

def generate(tenant, label, output, owner=None):
    if not TENANT_PATTERN.fullmatch(tenant) or tenant=='mr':
        raise ValueError('Use a customer tenant identifier other than mr')
    if not label or len(label)>100:
        raise ValueError('Member label must contain 1–100 characters')
    if owner and not re.fullmatch(r'U[0-9a-f]{32}',owner):
        raise ValueError('Owner must be the original LINE user ID')
    out=Path(output);out.mkdir(mode=0o700,parents=True,exist_ok=False)
    token=secrets.token_urlsafe(48)
    quote=lambda x:"'"+x.replace("'","''")+"'"
    tid=quote(tenant)
    # Resolve inside the named tenant, never trust an owner from another tenant.
    shared='NULL'
    guard=f"IF NOT EXISTS(SELECT 1 FROM public.lifeos_tenants WHERE id={tid} AND enabled) THEN RAISE EXCEPTION 'Customer not enabled'; END IF;\n"
    if owner:
        select=f"SELECT user_id FROM public.lifeos_users WHERE tenant_id={tid} AND line_user_id={quote(owner)} AND shared_owner IS NULL"
        guard+=f"IF NOT EXISTS({select}) THEN RAISE EXCEPTION 'Owner missing in this customer'; END IF;\n"
        shared='('+select+')'
    sql='BEGIN;\nDO $invite$ BEGIN\n'+guard+'END $invite$;\n'
    sql+=f"INSERT INTO public.lifeos_invites(tenant_id,code_hash,label,expires_at,shared_owner) VALUES ({tid},{quote(hashlib.sha256(token.encode()).hexdigest())},{quote(label)},now()+interval '7 days',{shared});\nCOMMIT;\n"
    for name,content in [('activation.txt','啟用助理 '+token+'\n'),('register-member.sql',sql),('.gitignore','*\n')]:
        fd=os.open(out/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as f:f.write(content)
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('tenant','label','output'):p.add_argument('--'+name,required=True)
    p.add_argument('--shared-owner',help='Original LINE ID of the enrolled customer owner')
    args=p.parse_args();generate(args.tenant,args.label,args.output,args.shared_owner)
    print('Private invite files prepared; no user created and no sharing settings changed.')

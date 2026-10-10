"""Request-local settings: never change process environment to switch clients."""
import json
import os
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

_active = ContextVar('lifeos_profile', default=None)
TENANT_PATTERN = re.compile(r'^[a-z][a-z0-9_-]{1,39}$')
REQUIRED = ('LINE_CHANNEL_SECRET','LINE_CHANNEL_ACCESS_TOKEN','LIFEOS_GATEWAY_URL',
            'LIFEOS_GATEWAY_KEY','LIFEOS_CRON_KEY','LIFEOS_PUBLIC_BASE_URL',
            'GOOGLE_SERVICE_ACCOUNT_JSON','LIFEOS_GOOGLE_CALENDAR_ID','LIFEOS_GOOGLE_USER_ID')

@dataclass(frozen=True)
class Profile:
    tenant_id: str
    name: str
    settings: dict

def getenv(key, default=None):
    profile = _active.get()
    return profile.settings.get(key, default) if profile else os.getenv(key, default)

def tenant_id():
    return getenv('LIFEOS_TENANT_ID','mr')

@contextmanager
def use_profile(profile):
    token = _active.set(profile)
    try:
        yield profile
    finally:
        _active.reset(token)

def load_profiles(path):
    document = json.loads(Path(path).read_text())
    if document.get('version') != 1 or not isinstance(document.get('clients'), list):
        raise ValueError('Invalid Life OS profile file')
    result = []
    seen = {key:set() for key in ('tenant','calendar','token','gateway','cron','secret')}
    for item in document['clients']:
        if item.get('enabled') is not True:
            continue
        tid = item.get('tenant_id','')
        if not TENANT_PATTERN.fullmatch(tid) or tid == 'mr':
            raise ValueError('Client tenant_id must be a unique identifier other than mr')
        refs = item.get('env',{})
        if not isinstance(refs,dict) or any(key not in REQUIRED for key in refs):
            raise ValueError('Invalid environment references for '+tid)
        settings = {key:os.environ.get(ref,'') for key,ref in refs.items()
                    if isinstance(ref,str) and re.fullmatch(r'[A-Z][A-Z0-9_]*',ref)}
        missing = [key for key in REQUIRED if not settings.get(key)]
        if missing:
            raise ValueError('Missing settings for '+tid+': '+', '.join(missing))
        if len(settings['LIFEOS_GATEWAY_KEY']) < 40 or len(settings['LIFEOS_CRON_KEY']) < 40:
            raise ValueError('Gateway and cron secrets must contain at least 40 characters')
        if not re.fullmatch(r'U[0-9a-f]{32}',settings['LIFEOS_GOOGLE_USER_ID']):
            raise ValueError('Invalid owner LINE user ID for '+tid)
        for key in ('LIFEOS_GATEWAY_URL','LIFEOS_PUBLIC_BASE_URL'):
            parsed = urlparse(settings[key])
            if parsed.scheme != 'https' or not parsed.netloc or parsed.username or parsed.password:
                raise ValueError('HTTPS is required for '+tid)
        public_url = urlparse(settings['LIFEOS_PUBLIC_BASE_URL'])
        if public_url.path.rstrip('/') != '/clients/'+tid or public_url.query or public_url.fragment:
            raise ValueError('Public URL must end in /clients/'+tid)
        info = json.loads(settings['GOOGLE_SERVICE_ACCOUNT_JSON'])
        if not info.get('client_email') or not info.get('private_key'):
            raise ValueError('Invalid Google service account for '+tid)
        for key,value in zip(seen,(tid,settings['LIFEOS_GOOGLE_CALENDAR_ID'],settings['LINE_CHANNEL_ACCESS_TOKEN'],settings['LIFEOS_GATEWAY_KEY'],settings['LIFEOS_CRON_KEY'],settings['LINE_CHANNEL_SECRET'])):
            if value in seen[key]:
                raise ValueError('Clients cannot share '+key+' settings')
            seen[key].add(value)
        settings.update(LIFEOS_TENANT_ID=tid,LIFEOS_ENABLED='1',
                        LIFEOS_STANDALONE='1',LIFEOS_DISPLAY_NAME=item.get('name','Life OS'))
        # Conservative defaults preserve current quota protection.
        settings['LIFEOS_REMINDER_HOUR'] = str(item.get('reminder_hour',9))
        if not 0 <= int(settings['LIFEOS_REMINDER_HOUR']) <= 23:
            raise ValueError('Invalid reminder hour')
        result.append(Profile(tid,item.get('name','Life OS'),settings))
    if not result:
        raise ValueError('No enabled Life OS clients')
    return result

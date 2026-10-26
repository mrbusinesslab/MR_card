"""Backend-only Google address geocoding; never fall back to text search."""
import json
import time
from urllib.parse import quote
from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession
from lifeos_settings import getenv,tenant_id

_CACHE={}
class LocationError(Exception):pass

def resolve(address):
    address=address.strip()
    if not address:raise LocationError('missing_address')
    key=(tenant_id(),address)
    service=_CACHE.get((tenant_id(),'__service'))
    if service and service['until']>time.monotonic():raise LocationError(service['error'])
    cached=_CACHE.get(key)
    if cached and cached['until']>time.monotonic():
        if cached.get('error'):raise LocationError(cached['error'])
        return cached['place_id']
    try:
        info=json.loads(getenv('GOOGLE_SERVICE_ACCOUNT_JSON','{}'))
        if not info.get('client_email'):raise LocationError('not_configured')
        creds=service_account.Credentials.from_service_account_info(info,scopes=['https://www.googleapis.com/auth/maps-platform.geocode.address'])
        with AuthorizedSession(creds,refresh_timeout=5) as session:
            response=session.get('https://geocode.googleapis.com/v4/geocode/address/'+quote(address,safe=''),
                headers={'X-Goog-User-Project':info['project_id']},timeout=7)
        data=response.json()
        if response.status_code!=200:
            details=data.get('error',{}).get('details',[])
            reason=next((x.get('reason') for x in details if x.get('reason')),data.get('error',{}).get('status','unavailable'))
            raise LocationError(reason)
        rows=data.get('results',[])
        if len(rows)!=1:raise LocationError('ambiguous' if rows else 'not_found')
        row=rows[0]
        if row.get('granularity') not in ('ROOFTOP','RANGE_INTERPOLATED') or not row.get('placeId'):raise LocationError('not_precise')
        place_id=row['placeId']
        _CACHE[key]={'place_id':place_id,'until':time.monotonic()+86400}
        return place_id
    except LocationError as exc:
        _CACHE[key]={'error':str(exc),'until':time.monotonic()+60}
        if str(exc) in ('SERVICE_DISABLED','BILLING_DISABLED','PERMISSION_DENIED','USER_PROJECT_DENIED'):
            _CACHE[(tenant_id(),'__service')]=_CACHE[key]
        raise
    except Exception:
        raise LocationError('unavailable')

def map_url(address,place_id=None):
    place_id=place_id or resolve(address)
    # The original address is a readable fallback; Place ID determines the actual pin.
    url='https://www.google.com/maps/search/?api=1&query='+quote(address,safe='')+'&query_place_id='+quote(place_id,safe='')
    if len(url)>1000: # Keep LINE URI actions valid for unusually long addresses.
        url='https://www.google.com/maps/search/?api=1&query='+quote(place_id,safe='')+'&query_place_id='+quote(place_id,safe='')
    return url

def map_component(address,place_id=None):
    try:
        return {'type':'button','style':'link','height':'sm','action':{'type':'uri','label':'Google 地圖定位','uri':map_url(address,place_id)}}
    except LocationError as exc:
        reason=str(exc)
        message='地圖定位服務尚未啟用，地址仍會保留。' if reason in ('SERVICE_DISABLED','BILLING_DISABLED','PERMISSION_DENIED','USER_PROJECT_DENIED','not_configured','API_KEY_SERVICE_BLOCKED') else '地址尚未取得精確定位，請確認門牌或稍後重試。'
        return {'type':'text','text':message,'size':'xs','color':'#64748B','wrap':True}

"""Temporary setup routes: verify connections and identify the owner, no data access."""
import hmac
import json
import os
import re
import uuid
from pathlib import Path

import requests
from flask import Blueprint, request
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import ApiClient, Configuration, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent

import lifeos_calendar as calendar
from lifeos_settings import Profile, REQUIRED, TENANT_PATTERN, use_profile


def install_setup_clients(app, path):
    document=json.loads(Path(path).read_text())
    if document.get('version') != 1 or not isinstance(document.get('clients'),list):
        raise ValueError('Invalid Life OS setup file')
    count=0
    for item in document['clients']:
        switch=item.get('setup_enabled_env','')
        if item.get('enabled') is True or not re.fullmatch(r'[A-Z][A-Z0-9_]*',switch) or os.getenv(switch)!='1':
            continue
        tid=item.get('tenant_id','')
        if not TENANT_PATTERN.fullmatch(tid) or tid=='mr':
            raise ValueError('Invalid setup client identifier')
        refs=item.get('env',{})
        settings={key:os.getenv(ref,'') for key,ref in refs.items()
                  if key in REQUIRED and isinstance(ref,str) and re.fullmatch(r'[A-Z][A-Z0-9_]*',ref)}
        settings.update(LIFEOS_TENANT_ID=tid,LIFEOS_ENABLED='0',LIFEOS_STANDALONE='1')
        profile=Profile(tid,item.get('name','Life OS'),settings)
        key=settings.get('LIFEOS_CRON_KEY','')
        if len(key)<40 or key==os.getenv('LIFEOS_CRON_KEY'):
            raise ValueError('A separate setup authorization key is required')
        app.register_blueprint(setup_blueprint(profile,item.get('line_basic_id','')),
                               url_prefix='/clients/'+tid)
        count+=1
    return count


def setup_blueprint(profile, expected_bot):
    bp=Blueprint('lifeos_setup_'+profile.tenant_id,__name__)
    settings=profile.settings
    required=('LINE_CHANNEL_SECRET','LINE_CHANNEL_ACCESS_TOKEN',
              'GOOGLE_SERVICE_ACCOUNT_JSON','LIFEOS_GOOGLE_CALENDAR_ID')

    def problems():
        missing=[key for key in required if not settings.get(key)]
        reused=[key for key in ('LINE_CHANNEL_SECRET','LINE_CHANNEL_ACCESS_TOKEN','LIFEOS_GOOGLE_CALENDAR_ID')
                if os.getenv(key) and settings.get(key)==os.getenv(key)]
        return missing,reused

    def authorized():
        key=settings.get('LIFEOS_CRON_KEY','')
        return len(key)>=40 and hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+key)

    @bp.get('/setup-check')
    def setup_check():
        if not authorized(): return {'error':'unauthorized'},401
        missing,reused=problems()
        if missing or reused: return {'ready':False,'missing':missing,'reused_mr_settings':reused},503
        try:
            response=requests.get('https://api.line.me/v2/bot/info',
                headers={'Authorization':'Bearer '+settings['LINE_CHANNEL_ACCESS_TOKEN']},timeout=12)
            response.raise_for_status()
            bot=response.json()
            if not expected_bot or bot.get('basicId')!=expected_bot:
                return {'ready':False,'error':'wrong_line_channel'},503
        except (requests.RequestException,ValueError):
            return {'ready':False,'error':'line_credentials_unavailable'},503
        try:
            with use_profile(profile):
                metadata=calendar.call('GET',calendar_metadata=True)
                if metadata.get('id')!=settings['LIFEOS_GOOGLE_CALENDAR_ID']:
                    return {'ready':False,'error':'wrong_calendar'},503
                calendar.call('GET',params={'maxResults':1})
        except calendar.CalendarError:
            return {'ready':False,'error':'calendar_unavailable'},503
        return {'ready':True,'mode':'setup_only','line_basic_id':bot['basicId'],
                'calendar_name':metadata.get('summary'),'calendar_timezone':metadata.get('timeZone'),
                'calendar_write_verified':False}

    @bp.post('/setup-calendar-test')
    def calendar_test():
        if not authorized(): return {'error':'unauthorized'},401
        if any(problems()): return {'error':'configuration_incomplete'},503
        # Explicit operator check: create a private, invite-free probe only on
        # the new calendar and always remove its known ID, including retries.
        event_id='lifeossetup'+uuid.uuid4().hex
        created=False
        verified=False
        removed=False
        with use_profile(profile):
            try:
                calendar.call('POST',body={'id':event_id,'summary':'Life OS 連線測試（自動移除）',
                    'visibility':'private','reminders':{'useDefault':False},
                    'start':{'dateTime':'2030-01-01T00:00:00+08:00','timeZone':'Asia/Taipei'},
                    'end':{'dateTime':'2030-01-01T00:05:00+08:00','timeZone':'Asia/Taipei'}},
                    params={'sendUpdates':'none'})
                created=True
                verified=calendar.call('GET','/'+event_id).get('id')==event_id
            except calendar.CalendarError:
                pass
            finally:
                # Also clean up a POST whose response may have timed out.
                try:
                    calendar.call('DELETE','/'+event_id,params={'sendUpdates':'none'})
                    removed=True
                except calendar.CalendarError as exc:
                    removed=exc.reason in ('404','410','notFound','gone')
        if not removed:
            return {'write_verified':created and verified,'removed':False,'probe_event_id':event_id},503
        return {'write_verified':created and verified,'removed':True},200 if created and verified else 503

    handler=WebhookHandler(settings.get('LINE_CHANNEL_SECRET',''))

    @handler.add(MessageEvent,message=TextMessageContent)
    def on_text(event):
        if getattr(event.source,'type',None)!='user': return
        uid=getattr(event.source,'user_id','')
        if not re.fullmatch(r'U[0-9a-f]{32}',uid): return
        if event.message.text.strip()=='取得綁定碼':
            body='你的秘書綁定識別碼：\n'+uid+'\n\n請將這則訊息交給設定人員。秘書尚未正式啟用。'
        else:
            body='秘書正在設定中，尚未讀寫行程或待辦。\n請由小如如本人輸入「取得綁定碼」，完成帳號綁定。'
        with ApiClient(Configuration(access_token=settings['LINE_CHANNEL_ACCESS_TOKEN'])) as api:
            MessagingApi(api).reply_message(ReplyMessageRequest(reply_token=event.reply_token,messages=[TextMessage(text=body)]))

    @bp.post('/callback')
    def callback():
        missing,reused=problems()
        if missing or reused: return {'error':'setup_not_ready'},503
        try:
            handler.handle(request.get_data(as_text=True),request.headers.get('X-Line-Signature',''))
        except InvalidSignatureError:
            return {'error':'invalid_signature'},400
        except (ValueError,TypeError):
            return {'error':'invalid_payload'},400
        return 'OK'

    return bp

"""Isolated Life OS routes for standalone or shared hosting."""
import os
from flask import Flask, Blueprint, request, g
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhooks import MessageEvent, TextMessageContent, AudioMessageContent
from linebot.v3.messaging import ApiClient, Configuration, MessagingApi, ReplyMessageRequest, TextMessage
import lifeos as tasks
import lifeos_calendar as calendar
import lifeos_engineering as engineering
from lifeos_settings import load_profiles, use_profile, getenv

def install_clients(app, profiles=None, *, verify_backend=True, shared=False):
    profiles = profiles if profiles is not None else load_profiles(
        os.environ['LIFEOS_CLIENTS_FILE'], allow_empty=shared)
    # A shared process must not accidentally reuse the original MR channel,
    # calendar or authorization keys. Google credentials and gateway URL may
    # be shared, but each customer's calendar and keys must be distinct.
    if shared:
        isolated_keys = ('LINE_CHANNEL_SECRET', 'LINE_CHANNEL_ACCESS_TOKEN',
                         'LIFEOS_GATEWAY_KEY', 'LIFEOS_CRON_KEY',
                         'LIFEOS_GOOGLE_CALENDAR_ID')
        for profile in profiles:
            for key in isolated_keys:
                original = os.environ.get(key)
                if original and profile.settings.get(key) == original:
                    raise ValueError('Client must not reuse MR setting: '+key)
    if verify_backend:
        for profile in profiles:
            with use_profile(profile):
                status = tasks.gateway('tenant_info')
                if status.get('tenant_id') != profile.tenant_id or status.get('calendar_id') != getenv('LIFEOS_GOOGLE_CALENDAR_ID'):
                    raise ValueError('Customer backend is not ready: '+profile.tenant_id)
    for profile in profiles:
        app.register_blueprint(client_blueprint(profile),url_prefix='/clients/'+profile.tenant_id)
    return len(profiles)

def create_app(profiles=None, *, verify_backend=True):
    app = Flask(__name__)
    count = install_clients(app, profiles, verify_backend=verify_backend)
    @app.get('/health')
    def health():
        return {'service':'lifeos','ready':True,'clients':count}
    return app

def client_blueprint(profile):
    bp = Blueprint('lifeos_'+profile.tenant_id,__name__)
    handler = WebhookHandler(profile.settings['LINE_CHANNEL_SECRET'])
    @bp.before_request
    def bind_profile():
        context = use_profile(profile)
        context.__enter__()
        g.lifeos_context = context
    @bp.teardown_request
    def clear_profile(error):
        context = g.pop('lifeos_context',None)
        if context:
            context.__exit__(None,None,None)

    def reply(event,message):
        messages = message if isinstance(message,list) else [message]
        with ApiClient(Configuration(access_token=getenv('LINE_CHANNEL_ACCESS_TOKEN'))) as api:
            MessagingApi(api).reply_message(ReplyMessageRequest(reply_token=event.reply_token,messages=messages))

    @handler.add(MessageEvent,message=TextMessageContent)
    def on_text(event):
        uid = getattr(event.source,'user_id',None)
        source = getattr(event.source,'type','unknown')
        body = engineering.handle(uid,event.message.text,event.webhook_event_id,source)
        if body is None:
            body = calendar.handle(uid,event.message.text,event.webhook_event_id,source)
        if body is None:
            body = tasks.handle_text(uid,event.message.text,event.webhook_event_id,source)
            if body is not None:
                body = tasks.button_message(body)
        if body is None:
            body = TextMessage(text='請輸入「生活助理」查看功能；第一次使用請輸入管理者提供的啟用指令。')
        reply(event,body)

    @handler.add(MessageEvent,message=AudioMessageContent)
    def on_audio(event):
        body = tasks.handle_audio(getattr(event.source,'user_id',None),getattr(event.source,'type','unknown'))
        reply(event,tasks.button_message(body or '請使用手機鍵盤的麥克風轉成文字再傳送。'))

    @bp.post('/callback')
    def callback():
        try:
            handler.handle(request.get_data(as_text=True),request.headers.get('X-Line-Signature',''))
        except InvalidSignatureError:
            return {'error':'invalid_signature'},400
        return 'OK'
    tasks.install_routes(bp)
    calendar.install_routes(bp)
    engineering.install_routes(bp)
    return bp

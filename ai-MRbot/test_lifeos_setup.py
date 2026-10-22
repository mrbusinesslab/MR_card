import base64
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from flask import Flask
import lifeos_calendar as calendar
from lifeos_settings import Profile, REQUIRED, tenant_id
from lifeos_setup import install_setup_clients, setup_blueprint

UID='U'+'7'*32


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.settings={'LINE_CHANNEL_SECRET':'new-line-secret',
            'LINE_CHANNEL_ACCESS_TOKEN':'new-line-token','LIFEOS_CRON_KEY':'setup-key-'*8,
            'GOOGLE_SERVICE_ACCOUNT_JSON':json.dumps({'client_email':'fixture@example.com','private_key':'fixture'}),
            'LIFEOS_GOOGLE_CALENDAR_ID':'new-calendar','LIFEOS_TENANT_ID':'aa','LIFEOS_ENABLED':'0'}
        self.profile=Profile('aa','Fixture',self.settings)
        app=Flask(__name__)
        app.register_blueprint(setup_blueprint(self.profile,'@fixture'),url_prefix='/clients/aa')
        self.client=app.test_client()
        self.auth={'Authorization':'Bearer '+self.settings['LIFEOS_CRON_KEY']}

    def message(self,text='取得綁定碼',source='user',signature=True):
        body=json.dumps({'events':[{'type':'message','mode':'active','timestamp':1470747837840,
            'source':{'type':source,'userId':UID,'groupId':'G'+'1'*32},'replyToken':'r'*32,
            'webhookEventId':'fixture-event','deliveryContext':{'isRedelivery':False},
            'message':{'type':'text','id':'1','text':text,'quoteToken':'fixture-quote'}}]})
        sign=base64.b64encode(hmac.new(self.settings['LINE_CHANNEL_SECRET'].encode(),body.encode(),hashlib.sha256).digest()).decode()
        return self.client.post('/clients/aa/callback',data=body,headers={'X-Line-Signature':sign if signature else 'invalid'})

    def test_wrong_setup_key_cannot_check_or_write_calendar(self):
        with patch('lifeos_setup.requests.get') as line,patch('lifeos_setup.calendar.call') as api:
            self.assertEqual(self.client.get('/clients/aa/setup-check').status_code,401)
            self.assertEqual(self.client.post('/clients/aa/setup-calendar-test').status_code,401)
            line.assert_not_called();api.assert_not_called()

    def test_signed_owner_identification_never_enrolls_or_reads_old_data(self):
        with patch('lifeos_setup.ApiClient') as client,patch('lifeos_setup.MessagingApi') as messaging,patch('lifeos.gateway') as gateway,patch('lifeos_setup.calendar.call') as api:
            self.assertEqual(self.message().status_code,200)
            self.assertEqual(client.call_args.args[0].access_token,'new-line-token')
            text=messaging.return_value.reply_message.call_args.args[0].messages[0].text
            self.assertIn(UID,text)
            self.assertIn('尚未正式啟用',text)
            gateway.assert_not_called();api.assert_not_called()
        self.assertEqual(tenant_id(),'mr')

    def test_setup_never_handles_calendar_commands(self):
        with patch('lifeos_setup.ApiClient'),patch('lifeos_setup.MessagingApi') as messaging,patch('lifeos.gateway') as gateway,patch('lifeos_setup.calendar.call') as api:
            self.assertEqual(self.message('明天下午三點 林小姐 F').status_code,200)
            self.assertIn('尚未讀寫',messaging.return_value.reply_message.call_args.args[0].messages[0].text)
            gateway.assert_not_called();api.assert_not_called()

    def test_wrong_signature_and_group_do_not_disclose_binding_id(self):
        with patch('lifeos_setup.MessagingApi') as messaging:
            self.assertEqual(self.message(signature=False).status_code,400)
            self.assertEqual(self.message(source='group').status_code,200)
            messaging.assert_not_called()

    def test_check_validates_bot_and_new_calendar_without_returning_secrets(self):
        response=Mock();response.json.return_value={'basicId':'@fixture'}
        with patch('lifeos_setup.requests.get',return_value=response),patch('lifeos_setup.calendar.call',side_effect=[{'id':'new-calendar','summary':'New calendar','timeZone':'Asia/Taipei'},{'items':[]}]) as api:
            result=self.client.get('/clients/aa/setup-check',headers=self.auth)
            self.assertEqual(result.status_code,200)
            self.assertTrue(result.json['ready'])
            self.assertFalse(result.json['calendar_write_verified'])
            self.assertEqual(api.call_count,2)
            for key in ('LINE_CHANNEL_SECRET','LINE_CHANNEL_ACCESS_TOKEN','LIFEOS_CRON_KEY','GOOGLE_SERVICE_ACCOUNT_JSON'):
                self.assertNotIn(self.settings[key],result.get_data(as_text=True))
        self.assertEqual(tenant_id(),'mr')

    def test_wrong_bot_stops_before_calendar_access(self):
        response=Mock();response.json.return_value={'basicId':'@wrong'}
        with patch('lifeos_setup.requests.get',return_value=response),patch('lifeos_setup.calendar.call') as api:
            result=self.client.get('/clients/aa/setup-check',headers=self.auth)
            self.assertEqual(result.status_code,503)
            self.assertEqual(result.json['error'],'wrong_line_channel')
            api.assert_not_called()

    def test_reused_original_calendar_is_rejected_before_any_api_call(self):
        with patch.dict(os.environ,{'LIFEOS_GOOGLE_CALENDAR_ID':'new-calendar'}),patch('lifeos_setup.calendar.call') as api:
            result=self.client.post('/clients/aa/setup-calendar-test',headers=self.auth)
            self.assertEqual(result.status_code,503)
            api.assert_not_called()

    def test_probe_is_private_invite_free_and_removed(self):
        def call(method,path='',body=None,params=None,**kwargs):
            self.assertEqual(tenant_id(),'aa')
            if method=='POST':
                self.probe=body
                self.assertEqual(body['visibility'],'private')
                self.assertNotIn('attendees',body)
                self.assertNotIn('conferenceData',body)
                self.assertEqual(params['sendUpdates'],'none')
                return {'id':body['id']}
            if method=='GET':return {'id':self.probe['id']}
            self.assertEqual(method,'DELETE')
            self.assertEqual(path,'/'+self.probe['id'])
            return {}
        with patch('lifeos_setup.calendar.call',side_effect=call):
            result=self.client.post('/clients/aa/setup-calendar-test',headers=self.auth)
            self.assertEqual(result.json,{'write_verified':True,'removed':True})
            self.assertEqual(result.status_code,200)
        self.assertEqual(tenant_id(),'mr')

    def test_probe_cleanup_runs_after_timeout(self):
        with patch('lifeos_setup.calendar.call',side_effect=[calendar.CalendarError('connection_failed'),{}]) as api:
            result=self.client.post('/clients/aa/setup-calendar-test',headers=self.auth)
            self.assertEqual(result.status_code,503)
            self.assertTrue(result.json['removed'])
            self.assertEqual(api.call_args.args[0],'DELETE')

    def test_loader_requires_explicit_switch_and_skips_active_clients(self):
        refs={key:'SETUP_'+key for key in REQUIRED}
        env={refs[key]:self.settings.get(key,'') for key in REQUIRED}
        env['SETUP_SWITCH']='1'
        item={'tenant_id':'aa','name':'Fixture','enabled':False,'setup_enabled_env':'SETUP_SWITCH','line_basic_id':'@fixture','env':refs}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'clients.json';path.write_text(json.dumps({'version':1,'clients':[item]}))
            with patch.dict(os.environ,env):
                app=Flask(__name__)
                self.assertEqual(install_setup_clients(app,path),1)
            item['enabled']=True;path.write_text(json.dumps({'version':1,'clients':[item]}))
            with patch.dict(os.environ,env):
                self.assertEqual(install_setup_clients(Flask(__name__),path),0)
            item['enabled']=False;path.write_text(json.dumps({'version':1,'clients':[item]}))
            env['SETUP_SWITCH']='0'
            with patch.dict(os.environ,env):
                self.assertEqual(install_setup_clients(Flask(__name__),path),0)

    def test_calendar_delete_accepts_empty_204_response(self):
        response=Mock(status_code=204)
        response.json.side_effect=ValueError('empty response')
        session=Mock();session.request.return_value=response
        with patch('lifeos_calendar.config',return_value=({'client_email':'fixture@example.com'},'new-calendar','')),patch('lifeos_calendar.service_account.Credentials.from_service_account_info'),patch('lifeos_calendar.AuthorizedSession') as authorized:
            authorized.return_value.__enter__.return_value=session
            self.assertEqual(calendar.call('DELETE','/probe'),{})
            response.json.assert_not_called()


if __name__=='__main__':unittest.main()

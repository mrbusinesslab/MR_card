import hashlib
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch, Mock
from lifeos_settings import Profile, use_profile, getenv, tenant_id, load_profiles, REQUIRED
from provision_lifeos import generate
import lifeos
import lifeos_calendar
import lifeos_week_image
from lifeos_app import create_app

UID='U'+'1'*32

def profile(tid):
    return Profile(tid,tid,{'LIFEOS_TENANT_ID':tid,'LINE_CHANNEL_SECRET':tid*32,
        'LINE_CHANNEL_ACCESS_TOKEN':tid+'-token','LIFEOS_GATEWAY_KEY':tid*48,
        'LIFEOS_GATEWAY_URL':'https://example.com/gateway', 'LIFEOS_CRON_KEY':tid*48,
        'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':tid+'-calendar',
        'LIFEOS_PUBLIC_BASE_URL':'https://example.com/clients/'+tid,
        'LIFEOS_STANDALONE':'1'})

class ClientTests(unittest.TestCase):
    def test_edit_context_isolated_for_same_line_user(self):
        import time
        import lifeos_calendar_list_flow as flow
        with use_profile(profile('aa')):
            flow._PENDING[('aa',UID)]={'until':time.monotonic()+600}
            self.assertTrue(flow.is_editing(UID))
        with use_profile(profile('bb')):
            self.assertFalse(flow.is_editing(UID))
        flow._PENDING.pop(('aa',UID),None)
    def test_customer_does_not_inherit_mr_person_rule(self):
        with use_profile(profile('aa')):
            self.assertFalse(lifeos_calendar.is_xiaomeng('小孟'))
        self.assertTrue(lifeos_calendar.is_xiaomeng('小孟'))
    def test_customer_blueprint_does_not_run_mr_import(self):
        with patch('lifeos_moon_labels.start') as migration:
            create_app([profile('aa')],verify_backend=False)
            migration.assert_not_called()
    def test_thread_settings_and_restore(self):
        def work(tid):
            with use_profile(profile(tid)):
                return tenant_id(),getenv('LINE_CHANNEL_ACCESS_TOKEN'),getenv('MR_ONLY')
        with patch.dict(os.environ,{'MR_ONLY':'private'}):
            with ThreadPoolExecutor(max_workers=2) as pool:
                self.assertEqual(list(pool.map(work,['aa','bb'])),[('aa','aa-token',None),('bb','bb-token',None)])
            self.assertEqual(getenv('MR_ONLY'),'private')
    def test_gateway_binds_customer(self):
        response=Mock(); response.json.return_value={'user':None}
        with use_profile(profile('aa')),patch('lifeos.requests.post',return_value=response) as post:
            lifeos.gateway('get_user',UID,tenant_id='bb')
        self.assertEqual(post.call_args.kwargs['json']['tenant_id'],'aa')
        self.assertEqual(post.call_args.kwargs['headers']['X-LifeOS-Key'],'aa'*48)
    def test_same_line_user_has_distinct_images(self):
        with use_profile(profile('aa')): a=lifeos_week_image.asset_root()
        with use_profile(profile('bb')): b=lifeos_week_image.asset_root()
        self.assertNotEqual(a,b)
    def test_owner_requires_enrollment_and_matching_calendar(self):
        with use_profile(profile('aa')),patch('lifeos.gateway',return_value={'user':None}):
            self.assertFalse(lifeos_calendar.calendar_access(UID))
        with use_profile(profile('aa')),patch('lifeos.gateway',return_value={'user':{'tenant_id':'bb','tenant_calendar_id':'aa-calendar','calendar_owner_line_id':UID}}):
            self.assertFalse(lifeos_calendar.calendar_access(UID))
        with use_profile(profile('aa')),patch('lifeos.gateway',return_value={'user':{'tenant_id':'aa','tenant_calendar_id':'aa-calendar','calendar_owner_line_id':UID}}):
            self.assertTrue(lifeos_calendar.calendar_access(UID))
    def test_blueprints_keys_and_invalid_signature(self):
        app=create_app([profile('aa'),profile('bb')],verify_backend=False); client=app.test_client()
        self.assertEqual(client.get('/health').status_code,200)
        self.assertEqual(client.post('/clients/aa/callback',data='{}').status_code,400)
        with patch('lifeos.reminder_run',return_value={'ok':True}) as run:
            self.assertEqual(client.post('/clients/aa/lifeos/reminders',headers={'Authorization':'Bearer '+'bb'*48}).status_code,401)
            self.assertEqual(client.post('/clients/aa/lifeos/reminders',headers={'Authorization':'Bearer '+'aa'*48}).status_code,200)
            run.assert_called_once()
        with patch('lifeos.reminder_run',side_effect=RuntimeError('test')):
            self.assertEqual(client.post('/clients/aa/lifeos/reminders',headers={'Authorization':'Bearer '+'aa'*48}).status_code,503)
        self.assertEqual(tenant_id(),'mr')
    def test_startup_rejects_wrong_backend(self):
        with patch('lifeos.gateway',return_value={'tenant_id':'mr','calendar_id':'aa-calendar'}),self.assertRaises(ValueError):
            create_app([profile('aa')])
        with patch('lifeos.gateway',return_value={'tenant_id':'aa','calendar_id':'aa-calendar'}):
            self.assertEqual(create_app([profile('aa')]).test_client().get('/health').status_code,200)
    def test_no_legacy_in_customer_help(self):
        with use_profile(profile('aa')):
            self.assertNotIn('查客戶',lifeos.help_text())
    def test_provision_disabled_private_secrets_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=generate('aa',"O'Brien",'aa-calendar',UID,'https://example.com',Path(tmp)/'aa')
            manifest=json.loads((out/'clients.json').read_text())
            self.assertFalse(manifest['clients'][0]['enabled'])
            secrets=json.loads((out/'environment.json').read_text())
            key=secrets['CLIENT_AA_LIFEOS_GATEWAY_KEY']
            self.assertEqual((out/'environment.json').stat().st_mode&0o777,0o600)
            self.assertNotIn(key,(out/'register.sql').read_text())
            self.assertIn(hashlib.sha256(key.encode()).hexdigest(),(out/'register.sql').read_text())
            self.assertIn("O''Brien owner",(out/'register.sql').read_text())
            with self.assertRaises(FileExistsError):
                generate('aa','x','aa-calendar',UID,'https://example.com',out)
    def test_manifest_rejects_duplicate_calendar(self):
        with tempfile.TemporaryDirectory() as tmp:
            clients=[]; env={}
            for tid in ('aa','bb'):
                values=profile(tid).settings.copy()
                values['GOOGLE_SERVICE_ACCOUNT_JSON']=json.dumps({'client_email':'x@example.com','private_key':'fixture'})
                values['LIFEOS_GOOGLE_CALENDAR_ID']='shared-calendar'
                refs={key:tid.upper()+'_'+key for key in REQUIRED}
                env.update({refs[key]:values[key] for key in REQUIRED})
                clients.append({'tenant_id':tid,'enabled':True,'env':refs})
            path=Path(tmp)/'clients.json';path.write_text(json.dumps({'version':1,'clients':clients}))
            with patch.dict(os.environ,env),self.assertRaisesRegex(ValueError,'calendar'):
                load_profiles(path)
if __name__=='__main__':unittest.main()

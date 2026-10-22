import unittest
from unittest.mock import patch
from datetime import datetime
from lifeos_settings import Profile,use_profile
import lifeos_engineering as e
import lifeos as l
import lifeos_calendar as c

UID='U'+'1'*32
KEY='10000000-0000-0000-0000-000000000001'
CASE={'id':KEY,'name':'陳先生浴室','stage':'待報價','location':'台中北區（虛構）','scope':'抓漏','demo':True,'open_tasks':1}
PROFILE=Profile('fixture','工程示範',{'LIFEOS_INDUSTRY':'engineering','LIFEOS_TENANT_ID':'fixture','LIFEOS_DISPLAY_NAME':'工程示範'})

def gateway(action,*args,**kw):
    if action=='get_user': return {'user':{'label':'test'}}
    if action=='engineering_list': return {'cases':[CASE]}
    if action=='engineering_detail': return {'case':CASE,'tasks':[]}
    return {'case':CASE}


class EngineeringTests(unittest.TestCase):
    def test_general_profile_preserves_existing_flow(self):
        with patch('lifeos.gateway') as db:
            self.assertIsNone(e.handle(UID,'生活助理'));db.assert_not_called()

    def test_group_and_unbound_cannot_read_cases(self):
        with use_profile(PROFILE),patch('lifeos.gateway') as db:
            self.assertIn('私人',e.handle(UID,'案件總覽',source_type='group').alt_text);db.assert_not_called()
            db.return_value={'user':None}
            self.assertIn('尚未綁定',e.handle(UID,'案件總覽').alt_text)
            self.assertEqual(db.call_count,1)

    def test_home_and_case_search(self):
        with use_profile(PROFILE),patch('lifeos.gateway',side_effect=gateway):
            home=e.handle(UID,'生活助理').to_dict()
            self.assertIn('工程秘書',str(home));self.assertNotIn('美容',str(home))
            self.assertEqual(e.handle(UID,'案件 陳先生').alt_text,'案場詳情')

    def test_stage_preview_does_not_write(self):
        with use_profile(PROFILE),patch('lifeos.gateway',side_effect=gateway) as db:
            result=e.handle(UID,'工程進度 陳先生｜施工中','webhook-1')
            self.assertEqual(result.alt_text,'確認更新進度')
            self.assertNotIn('engineering_stage',[call.args[0] for call in db.call_args_list])

    def test_stage_confirm_uses_case_id_and_webhook_id(self):
        with use_profile(PROFILE),patch('lifeos.gateway',side_effect=gateway) as db:
            e.handle(UID,'確認工程進度 '+KEY+'｜施工中','webhook-2')
            calls=[x for x in db.call_args_list if x.args[0]=='engineering_stage']
            self.assertEqual(calls[0].args,('engineering_stage',UID,'webhook-2'))
            self.assertEqual(calls[0].kwargs,{'case_id':KEY,'stage':'施工中'})

    def test_case_create_preview_does_not_write(self):
        with use_profile(PROFILE),patch('lifeos.gateway',side_effect=gateway) as db:
            self.assertEqual(e.handle(UID,'建立案件 林先生｜北區｜修水管').alt_text,'確認建立工程案件')
            self.assertNotIn('engineering_create',[x.args[0] for x in db.call_args_list])

    def test_add_item_parses_due_date_and_preserves_general_draft(self):
        with use_profile(PROFILE),patch('lifeos.gateway',side_effect=gateway) as db,patch('lifeos.clock',return_value=datetime(2026,10,22,18,tzinfo=l.TZ)):
            self.assertEqual(e.handle(UID,'工程事項 陳先生浴室｜備料｜明天下午五點前買材料').alt_text,'確認工程事項')
            e.handle(UID,'確認工程事項 陳先生浴室｜備料｜明天下午五點前買材料','webhook-3')
            call=next(x for x in db.call_args_list if x.args[0]=='engineering_add_task')
            self.assertIn('2026-10-23T17:00',call.kwargs['due_at'])
            self.assertNotIn('draft',[x.args[0] for x in db.call_args_list])

    def test_engineering_does_not_inherit_beauty_duration(self):
        with use_profile(PROFILE):
            self.assertEqual(l.beauty_title('B棟施工'),'B棟施工')
            with self.assertRaises(l.InputError): c.parse_booking('明天下午兩點 陳先生 F')
            self.assertEqual(l.category_style('陳先生場勘')[0],'場勘')
            draft={'event':{'summary':'test'}};c.set_category(draft,'施工')
            self.assertEqual(draft['event']['colorId'],'6')

    def test_task_board_keeps_only_engineering_tasks(self):
        def db(action,*args,**kw):
            if action=='get_user': return {'user':{}}
            return {'tasks':[{'id':1,'title':'工程事項','category':'工程／備料','status':'未開始'},
                             {'id':2,'title':'私人資料','category':'生活','status':'未開始'}]}
        with use_profile(PROFILE),patch('lifeos.gateway',side_effect=db):
            card=e.board(UID).to_dict()
            self.assertIn('工程事項',str(card));self.assertNotIn('私人資料',str(card))

    def test_malformed_case_commands_do_not_mutate(self):
        with use_profile(PROFILE),patch('lifeos.gateway',side_effect=gateway) as db:
            self.assertEqual(e.handle(UID,'建立案件 缺欄位').alt_text,'請補充工程資料')
            self.assertNotIn('engineering_create',[x.args[0] for x in db.call_args_list])

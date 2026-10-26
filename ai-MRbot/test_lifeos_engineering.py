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
    def setUp(self):
        e._FLOWS.clear();e._FLOW_REPLIES.clear()

    def tearDown(self):
        e._FLOWS.clear();e._FLOW_REPLIES.clear()

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

    def test_batch_events_use_engineering_categories(self):
        from lifeos_calendar_batch import payload
        entry={'kind':'complete','title':'09:00～10:00 陳先生場勘','date':'2026-10-23','times':['09:00','10:00']}
        with use_profile(PROFILE):
            event=payload(entry,c)
            self.assertEqual(event['colorId'],'9')
            self.assertEqual(event['extendedProperties']['private']['lifeos_category'],'場勘')

    def test_malformed_case_commands_do_not_mutate(self):
        with use_profile(PROFILE),patch('lifeos.gateway',side_effect=gateway) as db:
            self.assertEqual(e.handle(UID,'建立案件 缺欄位').alt_text,'請補充工程資料')
            self.assertNotIn('engineering_create',[x.args[0] for x in db.call_args_list])

    def test_overview_each_case_has_own_card_and_next_task(self):
        def db(action,*a,**kw):
            if action=='engineering_list':return {'cases':[CASE,{**CASE,'id':'10000000-0000-0000-0000-000000000002','name':'林小姐廚房'}]}
            return {'tasks':[{'id':10,'title':'【示範】陳先生浴室｜傳報價','original_text':'{"engineering_case_id":"'+KEY+'","text":"傳報價"}',
                              'due_at':'2026-10-27T17:00:00+08:00','status':'未開始'}]}
        with use_profile(PROFILE),patch('lifeos.gateway',side_effect=db):
            data=e.overview(UID).to_dict()['contents']
            self.assertEqual(data['type'],'carousel');self.assertEqual(len(data['contents']),2)
            first=data['contents'][0]
            self.assertIn('傳報價',str(first));self.assertNotIn(CASE['location'],str(first))
            self.assertEqual(len(first['footer']['contents']),1)

    def test_detail_shows_next_step_and_hides_address(self):
        with use_profile(PROFILE),patch('lifeos.gateway',side_effect=gateway):
            data=e.detail(UID,KEY).to_dict()['contents']
            self.assertNotIn(CASE['location'],str(data));self.assertEqual(len(data['footer']['contents']),3)
            full=e.handle(UID,'工程案件資料 '+KEY).to_dict()
            self.assertIn(CASE['location'],str(full))

    def test_task_rows_are_clickable_without_number_buttons(self):
        row={'id':10,'title':'【示範】陳先生浴室｜買材料','status':'未開始','category':'工程／備料'}
        with use_profile(PROFILE),patch('lifeos.gateway',return_value={'tasks':[row]}):
            data=e.board(UID).to_dict()['contents']
            self.assertNotIn('處理 #',str(data))
            action=data['body']['contents'][1]['action']
            self.assertEqual(action['text'],'工程待辦操作 10')
            self.assertNotIn('footer',data)

    def test_stage_picker_has_three_choices_and_update_ack_is_short(self):
        with use_profile(PROFILE),patch('lifeos.gateway',side_effect=gateway):
            picker=e.handle(UID,'工程階段 '+KEY).to_dict()['contents']
            self.assertEqual(len(picker['footer']['contents']),3)
            ack=e.handle(UID,'確認工程進度 '+KEY+'｜施工中','change').to_dict()
            self.assertEqual(ack['altText'],'進度已更新')
            self.assertEqual(len(ack['contents']['footer']['contents']),1)

    def test_case_wizard_has_no_write_until_confirmation_and_deduplicates(self):
        with use_profile(PROFILE),patch('lifeos.gateway',side_effect=gateway) as db:
            e.handle(UID,'新增案件','start')
            e.handle(UID,'林先生廚房','name')
            e.handle(UID,'林先生廚房','name')
            self.assertEqual(len(e._FLOWS[('fixture',UID)]['values']),1)
            e.handle(UID,'台中北屯','place')
            final=e.handle(UID,'水管更新','scope')
            self.assertEqual(final.alt_text,'確認新增案件')
            self.assertEqual(e.handle(UID,'水管更新','scope').alt_text,'確認新增案件')
            self.assertNotIn('engineering_create',[x.args[0] for x in db.call_args_list])
            self.assertNotIn(('fixture',UID),e._FLOWS)

    def test_task_wizard_prompts_one_field_at_a_time(self):
        with use_profile(PROFILE),patch('lifeos.gateway',side_effect=gateway) as db:
            e.handle(UID,'工程新增事項 '+KEY,'start')
            self.assertEqual(e.handle(UID,'備料','kind').alt_text,'要處理什麼事情？')
            self.assertEqual(e.handle(UID,'買材料','title').alt_text,'什麼時候要完成？')
            final=e.handle(UID,'不設期限','due')
            self.assertEqual(final.alt_text,'確認新增待辦')
            self.assertIn('確認工程事項 陳先生浴室｜備料｜買材料',str(final.to_dict()))
            self.assertNotIn('engineering_add_task',[x.args[0] for x in db.call_args_list])

    def test_wizard_cancel_and_tenant_isolation(self):
        other=Profile('other','other',{'LIFEOS_INDUSTRY':'engineering','LIFEOS_TENANT_ID':'other'})
        with patch('lifeos.gateway',side_effect=gateway):
            with use_profile(PROFILE):e.handle(UID,'新增案件')
            with use_profile(other):self.assertIsNone(e.handle(UID,'林先生廚房'))
            with use_profile(PROFILE):
                self.assertEqual(e.handle(UID,'停止新增').alt_text,'已停止新增')
                self.assertNotIn(('fixture',UID),e._FLOWS)

    def test_completion_ack_returns_to_case(self):
        row={'id':10,'title':'【示範】陳先生浴室｜買材料','status':'完成','category':'工程／備料',
             'original_text':'{"engineering_case_id":"'+KEY+'","text":"買材料"}'}
        with use_profile(PROFILE),patch('lifeos.gateway',return_value={'tasks':[row]}):
            ack=e.task_reply(UID,'已更新\n#10 【示範】陳先生浴室｜買材料\n  到期日：10/27｜完成').to_dict()
            self.assertEqual(ack['altText'],'已完成');self.assertEqual(len(ack['contents']['footer']['contents']),1)
            self.assertNotIn('#10',str(ack))

import copy
import unittest
from unittest.mock import patch
from datetime import datetime
from lifeos_settings import Profile,use_profile
import lifeos as tasks
import lifeos_engineering as ui
import lifeos_engineering_workflow as w

UID='U'+'1'*32
KEY='10000000-0000-0000-0000-000000000001'
PROFILE=Profile('fixture','工程示範',{'LIFEOS_INDUSTRY':'engineering','LIFEOS_TENANT_ID':'fixture','LIFEOS_ENGINEERING_WORKFLOW':'1'})

def fixture():
    rows=[{'key':k,'status':'未開始','note':''} for k,_ in w.PHASES]
    rows[0]['status']='已完成';rows[1]['status']='已完成';rows[2]['status']='不適用'
    rows[3].update(status='進行中',note='缺兩個接頭，星期五到貨。')
    return {'id':KEY,'name':'陳先生浴室','demo':True,'stage':'待施工','workflow':rows,'expected_finish':'2026-10-30'}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.case=fixture();w._PENDING.clear();w._REPLIES.clear()
        def db(action,*args,**kw):
            if action=='get_user':return {'user':{'label':'test'}}
            if action=='engineering_list':return {'cases':[copy.deepcopy(self.case)]}
            if action=='list':return {'tasks':[]}
            return {'case':copy.deepcopy(self.case)}
        self.db=patch('lifeos.gateway',side_effect=db).start();self.addCleanup(patch.stopall)
        self.ctx=use_profile(PROFILE);self.ctx.__enter__();self.addCleanup(lambda:self.ctx.__exit__(None,None,None))

    def tearDown(self):w._PENDING.clear();w._REPLIES.clear()

    def test_progress_excludes_skipped_and_does_not_count_in_progress_as_done(self):
        rows,done,total,current=w.progress(self.case)
        self.assertEqual((done,total,current['key']),(2,6,'materials'))
        self.assertEqual(len(w.progress_bar(self.case)[0]['contents']),7)
        self.assertIn('2／6',str(w.progress_bar(self.case)))

    def test_all_skipped_is_not_reported_as_completed(self):
        for s in self.case['workflow']:s['status']='不適用'
        self.assertEqual(w.progress(self.case)[1:4],(0,0,None))
        self.assertIn('所有階段均不適用',str(w.progress_bar(self.case)))

    def test_detail_has_seven_clickable_phases_without_task_buttons(self):
        card=ui.handle(UID,'工程案件 '+KEY).to_dict()
        self.assertEqual(card['altText'],'七階段工程進度')
        for _,label in w.PHASES:self.assertIn(label,str(card))
        self.assertNotIn('處理 #',str(card));self.assertNotIn('待辦事項',str(card))
        rows=[x for x in card['contents']['body']['contents'] if x.get('action',{}).get('text','').startswith('工程流程 ')]
        self.assertEqual(len(rows),7)

    def test_phase_shows_note_and_status(self):
        card=ui.handle(UID,'工程流程 '+KEY+' materials').to_dict()
        self.assertIn('缺兩個接頭',str(card));self.assertIn('進行中',str(card))

    def test_status_uses_isolated_rpc(self):
        card=ui.handle(UID,'確認階段狀態 '+KEY+' materials 不適用','event-status')
        self.assertEqual(card.alt_text,'階段狀態已更新')
        call=next(x for x in self.db.call_args_list if x.args[0]=='engineering_workflow_status')
        self.assertEqual(call.kwargs,{'case_id':KEY,'phase':'materials','status':'不適用'})
        self.assertEqual(call.args[1:],(UID,'event-status'))

    def test_notes_require_confirmation_and_preserve_expected_value(self):
        ui.handle(UID,'工程流程備註 '+KEY+' materials','note-start')
        self.assertEqual(ui.handle(UID,'缺三個接頭','note-text').alt_text,'確認備註')
        self.assertFalse(any(x.args[0]=='engineering_workflow_note' for x in self.db.call_args_list))
        ui.handle(UID,'確認流程編輯','note-confirm')
        call=next(x for x in self.db.call_args_list if x.args[0]=='engineering_workflow_note')
        self.assertEqual(call.kwargs['note'],'缺三個接頭')
        self.assertEqual(call.kwargs['expected_note'],'缺兩個接頭，星期五到貨。')
        ui.handle(UID,'確認流程編輯','note-confirm')
        self.assertEqual(len([x for x in self.db.call_args_list if x.args[0]=='engineering_workflow_note']),1)

    def test_note_cancel_does_not_write(self):
        ui.handle(UID,'工程流程備註 '+KEY+' materials')
        ui.handle(UID,'清空備註');ui.handle(UID,'取消流程編輯')
        self.assertFalse(any(x.args[0]=='engineering_workflow_note' for x in self.db.call_args_list))

    def test_finish_date_is_separate_from_stage(self):
        with patch('lifeos.clock',return_value=datetime(2026,10,26,12,tzinfo=tasks.TZ)):
            ui.handle(UID,'工程完工日期 '+KEY)
            self.assertEqual(ui.handle(UID,'10/30').alt_text,'確認預計完工日')
            ui.handle(UID,'確認流程編輯','finish')
        call=next(x for x in self.db.call_args_list if x.args[0]=='engineering_workflow_finish')
        self.assertEqual(call.kwargs['expected_finish'],'2026-10-30')

    def test_groups_cannot_read_or_edit(self):
        self.db.reset_mock()
        self.assertEqual(ui.handle(UID,'工程案件 '+KEY,source_type='group').alt_text,'請使用私人聊天室')
        self.db.assert_not_called()

    def test_old_task_menu_routes_to_workflow_not_small_items(self):
        self.assertEqual(ui.handle(UID,'工程待辦').alt_text,'工程進度總覽')
        self.assertEqual(ui.handle(UID,'工程事項 陳先生｜備料｜買材料').alt_text,'事項改記在階段備註')

    def test_archived_linked_tasks_hidden_only_in_workflow_profile(self):
        rows=[{'id':1,'original_text':'{"engineering_case_id":"'+KEY+'"}'},{'id':2,'original_text':'私人事項'}]
        self.assertEqual([x['id'] for x in tasks.visible_task_rows(rows)],[2])
        with use_profile(Profile('mr','MR',{})):
            self.assertEqual(len(tasks.visible_task_rows(rows)),2)

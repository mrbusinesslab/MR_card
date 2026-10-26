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
        self.assertEqual(card['altText'],'查看工程進度')
        for _,label in w.PHASES:self.assertIn(label,str(card))
        self.assertNotIn('處理 #',str(card));self.assertNotIn('待辦事項',str(card))
        rows=[x for x in card['contents']['body']['contents'] if x.get('action',{}).get('data','').startswith('lifeos:工程流程 ')]
        self.assertEqual(len(rows),7)

    def test_phase_shows_note_and_status(self):
        card=ui.handle(UID,'工程流程 '+KEY+' materials').to_dict()
        self.assertIn('缺兩個接頭',str(card));self.assertIn('進行中',str(card))

    def test_status_uses_isolated_rpc(self):
        card=ui.handle(UID,'確認階段狀態 '+KEY+' materials 不適用','event-status')
        self.assertEqual(card.alt_text,'備料準備')
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
        self.assertEqual(ui.handle(UID,'工程待辦').alt_text,'工程進度')
        self.assertEqual(ui.handle(UID,'工程事項 陳先生｜備料｜買材料').alt_text,'事項改記在階段備註')

    def test_archived_linked_tasks_hidden_only_in_workflow_profile(self):
        rows=[{'id':1,'original_text':'{"engineering_case_id":"'+KEY+'"}'},{'id':2,'original_text':'私人事項'}]
        self.assertEqual([x['id'] for x in tasks.visible_task_rows(rows)],[2])
        with use_profile(Profile('mr','MR',{})):
            self.assertEqual(len(tasks.visible_task_rows(rows)),2)

    def test_completion_date_elapsed_and_unknown_history(self):
        self.case['workflow'][0]['completed_on']='2026-10-20'
        with patch('lifeos.clock',return_value=datetime(2026,10,26,0,5,tzinfo=tasks.TZ)):
            card=w.detail(UID,KEY).to_dict()
            self.assertIn('2026/10/20 完成 · 已過 6 天',str(card))
            self.assertIn('完成日期未記錄',str(card))
            self.assertNotIn('有備註',str(card))
            self.assertNotIn('缺兩個接頭',str(w.overview(UID).to_dict()))
            self.assertEqual(w.completion_label({'status':'已完成','completed_on':'2026-10-26'}),'2026/10/26 完成 · 今天')

    def test_note_preview_is_short_and_full_note_remains_accessible(self):
        long_note='缺少材料'+'甲'*200+'\n第二行\n第三行'
        self.case['workflow'][3]['note']=long_note
        card=w.phase_card(UID,KEY,'materials').to_dict()
        self.assertNotIn(long_note,str(card));self.assertIn('查看完整備註',str(card))
        self.assertEqual(long_note,ui.handle(UID,'工程完整備註 '+KEY+' materials').to_dict()['contents']['body']['contents'][0]['text'])

    def test_buttons_display_exact_label_with_private_postback_commands(self):
        def visit(x):
            if isinstance(x,dict):
                if 'action' in x:
                    a=x['action'];self.assertEqual(a['type'],'postback')
                    self.assertEqual(a['displayText'],a['label']);self.assertTrue(a['data'].startswith('lifeos:'))
                    self.assertLessEqual(len(a['data']),300)
                for v in x.values():visit(v)
            elif isinstance(x,list):
                for v in x:visit(v)
        for card in [w.overview(UID),w.detail(UID,KEY),w.phase_card(UID,KEY,'materials')]:visit(card.to_dict())
        self.assertEqual(ui.handle(UID,'工程流程狀態 '+KEY+' materials').alt_text,'變更狀態')
        self.assertEqual(ui.handle(UID,'工程流程備註 '+KEY+' materials').alt_text,'編輯備註')

    def test_completion_date_backfill_requires_confirmation_and_rejects_future(self):
        with patch('lifeos.clock',return_value=datetime(2026,10,26,12,tzinfo=tasks.TZ)):
            ui.handle(UID,'工程完成日期 '+KEY+' appointment')
            self.assertEqual(ui.handle(UID,'10/27').alt_text,'尚未更新')
            self.assertEqual(ui.handle(UID,'10/20').alt_text,'確認完成日期')
            self.assertFalse(any(c.args[0]=='engineering_workflow_status' for c in self.db.call_args_list))
            ui.handle(UID,'確認流程編輯','date-confirm')
        call=next(c for c in self.db.call_args_list if c.args[0]=='engineering_workflow_status')
        self.assertEqual(call.kwargs['completed_on'],'2026-10-20')
        self.assertEqual(call.kwargs['expected_status'],'已完成')
        self.assertEqual(ui.handle(UID,'工程完成日期 '+KEY+' materials').alt_text,'尚未更新')

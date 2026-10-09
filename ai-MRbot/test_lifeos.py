import os
import unittest
from datetime import datetime
from unittest.mock import patch, Mock
from flask import Flask
import lifeos as l

NOW = datetime(2026,10,8,14,0,tzinfo=l.TZ)
UID = 'U' + '1'*32

class ParserTests(unittest.TestCase):
    def test_friday(self):
        task=l.parse_tasks('星期五前把資料傳給林威',NOW)[0]
        self.assertEqual(task['title'],'把資料傳給林威')
        self.assertEqual(task['due_at'],'2026-10-09T23:59:00+08:00')
    def test_next_week(self):
        self.assertEqual(l.parse_date('下星期一',NOW)[0].day,12)
    def test_unscheduled(self):
        self.assertIsNone(l.parse_tasks('買耗材',NOW)[0]['due_at'])
    def test_ambiguous_time(self):
        with self.assertRaises(l.InputError): l.parse_date('明天2點',NOW)
    def test_invalid_date(self):
        with self.assertRaises(l.InputError): l.parse_date('2026年2月30日',NOW)
    def test_no_calendar_guess(self):
        with self.assertRaises(l.InputError): l.parse_tasks('客人預約前一天準備產品',NOW)
    def test_no_recurring_guess(self):
        with self.assertRaises(l.InputError): l.parse_tasks('每月繳電話費',NOW)
    def test_half_hour(self):
        self.assertEqual(l.parse_date('明天下午兩點半',NOW)[0].hour,14)
        self.assertEqual(l.parse_date('明天下午兩點半',NOW)[0].minute,30)
    def test_multi(self):
        self.assertEqual(len(l.parse_tasks('明天買紙巾；星期五傳資料',NOW)),2)
    def test_no_date_for_time(self):
        with self.assertRaises(l.InputError): l.parse_date('下午2點',NOW)
    def test_ambiguous_target(self):
        with self.assertRaises(l.InputError): l.choose_task('資料',[{'id':1,'title':'資料A'},{'id':2,'title':'資料B'}])
    def test_completed_excluded(self):
        self.assertNotIn('秘密',l.summary([{'id':1,'title':'秘密','status':'完成'}],NOW))

class HandlerTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'LIFEOS_ENABLED':'1'});self.env.start()
    def tearDown(self): self.env.stop()
    @patch('lifeos.gateway')
    def test_unbound_original(self,g):
        g.return_value={'error':'not_enrolled'}
        self.assertIsNone(l.handle_text(UID,'林威'))
    @patch('lifeos.gateway')
    def test_private_only(self,g):
        self.assertIn('一對一',l.handle_text(UID,'我的待辦',source_type='group'));g.assert_not_called()
    @patch('lifeos.gateway')
    def test_draft_not_confirmed(self,g):
        g.side_effect=[{'user':{'assistant_mode':True}},{'ok':True}]
        self.assertIn('尚未存成',l.handle_text(UID,'買耗材','evt'))
        self.assertEqual(g.call_args.args,('draft',UID,'evt'))
    @patch('lifeos.gateway')
    def test_no_false_save(self,g):
        g.side_effect=[{'user':{'assistant_mode':True}},l.StorageError()]
        self.assertIn('未確認成功',l.handle_text(UID,'確認存檔'))
    @patch('lifeos.gateway')
    def test_client_lookup(self,g):
        g.return_value={'user':{'assistant_mode':True}}
        self.assertIsNone(l.handle_text(UID,'查客戶 林威'))
    @patch('lifeos.gateway')
    def test_audio_no_paid_api(self,g):
        g.return_value={'user':{'assistant_mode':True}}
        self.assertIn('尚未辨識',l.handle_audio(UID))
        g.assert_called_once_with('get_user',UID)
    @patch('lifeos.gateway')
    def test_exit_keeps_data(self,g):
        g.side_effect=[{'user':{'assistant_mode':True}},{'ok':True}]
        self.assertIn('仍保留',l.handle_text(UID,'離開助理','evt'))
        self.assertEqual(g.call_args.kwargs,{'enabled':False})
    def test_routes_auth(self):
        app=Flask(__name__);l.install_routes(app)
        self.assertEqual(app.test_client().post('/lifeos/reminders').status_code,401)
        self.assertFalse(app.test_client().get('/lifeos/health').json['audio_transcription'])

class SimpleInteractionTests(unittest.TestCase):
    def test_menu_only_five_buttons(self):
        card=l.button_message('生活助理').to_dict()['contents']
        self.assertNotIn('header',card);self.assertNotIn('footer',card)
        rows=card['body']['contents']
        self.assertEqual([r['action']['label'] for r in rows[:3]],['今天','本周','本月'])
        self.assertEqual([r['action']['label'] for r in rows[-1]['contents']],['逾期事項','提醒設定'])
    def test_week_and_month_boundaries(self):
        start,end=l.period_bounds(NOW,'week')
        self.assertEqual((start.day,end.day),(5,12))
        start,end=l.period_bounds(NOW,'month')
        self.assertEqual((start.month,start.day,end.month,end.day),(10,1,11,1))
    def test_week_excludes_other_dates(self):
        tasks=[{'id':i,'title':title,'status':'未開始','due_at':date} for i,title,date in [(1,'本周事情','2026-10-10T18:00:00+08:00'),(2,'下周事情','2026-10-12T18:00:00+08:00')]]
        with patch('lifeos_calendar.today_events',return_value=(None,None)):
            card=str(l.digest_message(l.summary(tasks,NOW,mode='week')).to_dict())
        self.assertIn('本周事情',card);self.assertNotIn('下周事情',card)
    @patch.dict(os.environ,{'LIFEOS_ENABLED':'1'})
    @patch('lifeos.gateway')
    def test_cancel_requires_confirmation(self,g):
        task={'id':12,'title':'傳資料','status':'未開始'}
        g.side_effect=[{'user':{'assistant_mode':True}},{'tasks':[task]}]
        result=l.handle_text(UID,'取消 12','evt')
        self.assertIn('確定取消',result);self.assertEqual(g.call_count,2)
        buttons=l.button_message(result).to_dict()['contents']['footer']['contents']
        self.assertEqual(buttons[0]['action']['text'],'確認取消 12')
    def test_detail_has_only_three_actions(self):
        message=l.button_message('待辦操作\n#12 傳資料\n  2026/10/09 18:00｜未開始').to_dict()
        buttons=message['contents']['footer']['contents']
        self.assertEqual([b['action']['label'] for b in buttons],['完成','取消','延期'])
    def test_summary_plain_and_tappable(self):
        task={'id':12,'title':'美容備品','category':'新客','status':'未開始','due_at':'2026-10-08T18:00:00+08:00'}
        with patch('lifeos_calendar.today_events',return_value=(None,None)):
            msg=l.digest_message(l.summary([task],NOW)).to_dict()
        self.assertNotIn('footer',msg['contents'])
        self.assertNotIn('更多操作',str(msg));self.assertNotIn('#AC93CC',str(msg))
        self.assertIn('延期 12',str(msg))
        self.assertIn('取消 12',str(msg))
        self.assertIn('完成 12',str(msg))
    @patch.dict(os.environ,{'LIFEOS_ENABLED':'1'})
    @patch('lifeos.gateway')
    @patch('lifeos.clock',return_value=NOW)
    def test_date_reply_updates_same_task(self,clock,g):
        task={'id':12,'title':'傳資料','status':'未開始','due_at':'2026-10-12T23:59:00+08:00'}
        g.side_effect=[{'user':{'assistant_mode':True,'pending_postpone':{'task_id':12,'title':'傳資料'}}},{'task':task}]
        self.assertIn('已延期',l.handle_text(UID,'10/12','evt'))
        self.assertEqual(g.call_args.args,('postpone_finish',UID,'evt'))
        self.assertEqual(g.call_args.kwargs['due_at'],'2026-10-12T23:59:00+08:00')
    @patch.dict(os.environ,{'LIFEOS_ENABLED':'1'})
    @patch('lifeos.gateway')
    def test_closed_task_does_not_change(self,g):
        g.side_effect=[{'user':{'assistant_mode':True}},{'tasks':[{'id':12,'title':'傳資料','status':'完成'}]}]
        self.assertIn('目前狀態：完成',l.handle_text(UID,'取消 12','evt'))
        self.assertEqual(g.call_count,2)
    def test_result_card_has_no_navigation(self):
        self.assertNotIn('footer',l.button_message('已更新\n#12 傳資料\n  2026/10/09 18:00｜完成').to_dict()['contents'])

class ReminderTests(unittest.TestCase):
    @patch.dict(os.environ,{'LIFEOS_ENABLED':'1'})
    @patch('lifeos.requests.post')
    @patch('lifeos.requests.get')
    def test_quota_reserved(self,get,post):
        get.side_effect=[Mock(json=lambda:{'type':'limited','value':200}),Mock(json=lambda:{'totalUsage':180})]
        self.assertEqual(l.reminder_run(NOW.replace(hour=9))['skipped'],'quota_reserved');post.assert_not_called()
    @patch.dict(os.environ,{'LIFEOS_ENABLED':'1'})
    @patch('lifeos.requests.post')
    @patch('lifeos.requests.get')
    def test_unknown_quota(self,get,post):
        get.side_effect=[Mock(json=lambda:{'type':'unlimited'}),Mock(json=lambda:{'totalUsage':0})]
        self.assertEqual(l.reminder_run(NOW.replace(hour=9))['skipped'],'quota_not_verified');post.assert_not_called()
    @patch.dict(os.environ,{'LIFEOS_ENABLED':'1'})
    @patch('lifeos.gateway')
    @patch('lifeos.requests.post')
    @patch('lifeos.requests.get')
    def test_retry_key(self,get,post,g):
        get.side_effect=[Mock(json=lambda:{'type':'limited','value':200}),Mock(json=lambda:{'totalUsage':0})]
        g.side_effect=[{'users':[{'user_id':UID}]},{'tasks':[{'id':1,'title':'買紙','status':'未開始'}]},
          {'notification':{'id':'n','retry_key':'retry'}},{'ok':True}]
        post.return_value.status_code=409
        self.assertEqual(l.reminder_run(NOW.replace(hour=9))['sent'],1)
        self.assertEqual(post.call_args.kwargs['headers']['X-Line-Retry-Key'],'retry')

if __name__=='__main__': unittest.main()

class NaturalTaskTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'LIFEOS_ENABLED':'1'});self.env.start();self.addCleanup(self.env.stop)
    @patch('lifeos.gateway')
    def test_purchase_does_not_complete_inventory(self,g):
        task={'id':2,'title':'買耗材','status':'未開始'}
        g.side_effect=[{'user':{'assistant_mode':True}},{'tasks':[task,{'id':6,'title':'清點面膜與耗材','status':'未開始'}]},{'task':{**task,'status':'完成'}}]
        self.assertIn('已更新',l.handle_text(UID,'耗材買好了','evt'))
        self.assertEqual(g.call_args.kwargs,{'task_id':2,'status':'完成'})
    @patch('lifeos.gateway')
    def test_ambiguous_postpone_only_shows_choices(self,g):
        g.side_effect=[{'user':{'assistant_mode':True}},{'tasks':[{'id':2,'title':'林威 傳資料','status':'未開始'},{'id':3,'title':'max 傳資料','status':'未開始'}]}]
        with patch('lifeos.clock',return_value=NOW): body=l.handle_text(UID,'資料延到星期五','evt')
        self.assertIsInstance(body,l.TaskChoice)
        self.assertEqual(g.call_count,2)
        self.assertEqual(body.choices[0][1],'延後 2 到 2026/10/09 23:59')
        self.assertIn('延後 2',str(l.button_message(body).to_dict()))
    @patch('lifeos.gateway')
    def test_no_match_does_not_create_a_task(self,g):
        g.side_effect=[{'user':{'assistant_mode':True}},{'tasks':[]}]
        self.assertIn('沒有更新或新增',l.handle_text(UID,'耗材買好了'))
        self.assertEqual(g.call_count,2)
    def test_reply_only_matches_waiting(self):
        tasks=[{'title':'等傑哥回覆','status':'等待對方'},{'title':'傑哥 電子名片','status':'未開始'}]
        self.assertEqual(l.matching_tasks('傑哥',tasks,'等待對方'),tasks[:1])
    def test_waiting_and_own_commitment(self):
        self.assertEqual(l.parse_tasks('星期五等傑哥回覆',NOW)[0]['status'],'等待對方')
        self.assertEqual(l.parse_tasks('星期五前傳資料給林威',NOW)[0]['status'],'未開始')
        self.assertIn('追蹤日',l.task_line(l.parse_tasks('星期五等傑哥回覆',NOW)[0]))
    @patch('lifeos.gateway')
    def test_waiting_draft_is_not_update_command(self,g):
        g.side_effect=[{'user':{'assistant_mode':True}},{'ok':True}]
        self.assertIn('尚未存成',l.handle_text(UID,'等待傑哥回覆'))
        self.assertEqual(g.call_args.args[0],'draft')
    @patch('lifeos.gateway')
    def test_confirm_uses_atomic_waiting_extension(self,g):
        g.side_effect=[{'user':{'assistant_mode':True}},{'tasks':[{'id':1,'title':'等傑哥回覆','status':'等待對方'}]}]
        self.assertIn('等待對方',l.handle_text(UID,'確認存檔','evt'))
        self.assertEqual(g.call_args.args,('confirm_tasks',UID,'evt'))

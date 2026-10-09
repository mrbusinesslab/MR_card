import os
import unittest
from datetime import datetime
from unittest.mock import patch
import lifeos as l
import lifeos_calendar as c

UID='U'+'1'*32
NOW=datetime(2026,10,8,15,tzinfo=l.TZ)

class CalendarTests(unittest.TestCase):
 def test_parse(self):
  title,start,end=c.parse_range('明天下午2點到下午3點 美容預約',NOW)
  self.assertEqual(title,'美容預約');self.assertEqual(start.hour,14);self.assertEqual(end.hour,15)
  self.assertEqual(start.day,9)
 def test_no_end(self):
  with self.assertRaises(l.InputError): c.parse_range('明天下午2點 美容',NOW)
 def test_no_invented_period(self):
  with self.assertRaises(l.InputError): c.parse_range('明天2點到3點 美容',NOW)
 def test_no_cross_day(self):
  with self.assertRaises(l.InputError): c.parse_range('10月9日14:00到10月10日15:00 美容',NOW)
 def test_not_other_user(self):
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID}),patch('lifeos_calendar.call') as api:
   message=c.handle('U'+'2'*32,'Google日曆');self.assertIn('尚未啟用',message.alt_text);api.assert_not_called()
 def test_group(self):
  with patch('lifeos_calendar.call') as api:
   self.assertIn('私人',c.handle(UID,'Google日曆',source_type='group').alt_text);api.assert_not_called()
 def test_draft_without_write(self):
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos.gateway') as db,patch('lifeos_calendar.call') as api:
   db.return_value={'ok':True}
   self.assertIn('確認',c.handle(UID,'行程 明天下午2點到下午3點 美容','evt').alt_text)
   api.assert_not_called();self.assertEqual(db.call_args.args,('calendar_draft',UID,'evt'))
 def test_automatic_range(self):
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos.gateway',return_value={'ok':True}),patch('lifeos_calendar.call') as api:
   self.assertIn('請選擇排程類型',c.handle(UID,'明天下午2點到下午3點 日曆串接測試','evt').alt_text)
   api.assert_not_called()
 def test_person_names_do_not_guess(self):
  self.assertEqual(l.category_style('傑哥 電子名片')[0],'其他')
  self.assertEqual(l.category_style('max 開會')[0],'其他')
  self.assertEqual(l.category_style('林小姐 F')[0],'美容')
 def test_pending_category_blocks_write(self):
  draft={'calendar_id':'cal','needs_category':True,'event':{'summary':'max 開會','start':{'dateTime':'2026-10-09T14:00:00+08:00'},'end':{'dateTime':'2026-10-09T15:00:00+08:00'}}}
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos.gateway',return_value={'draft':draft}),patch('lifeos_calendar.call') as api:
   result=c.handle(UID,'確認行程')
   self.assertIn('請選擇',result.alt_text);api.assert_not_called()
 def test_business_choice_preserves_title(self):
  draft={'calendar_id':'cal','needs_category':True,'event':{'summary':'max 開會','start':{'dateTime':'2026-10-09T14:00:00+08:00'},'end':{'dateTime':'2026-10-09T15:00:00+08:00'}}}
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos.gateway') as db,patch('lifeos_calendar.call') as api:
   db.side_effect=[{'draft':draft},{'ok':True}]
   self.assertIn('確認',c.handle(UID,'分類行程 商會').alt_text)
   saved=db.call_args.kwargs['payload']
   self.assertEqual(saved['event']['summary'],'max 開會')
   self.assertEqual(saved['category'],'交流');self.assertNotIn('needs_category',saved)
   api.assert_not_called()
 def test_named_label_uses_custom_id(self):
  with patch('lifeos_calendar.event_labels',return_value=[{'name':'美容美體','id':'custom-blue','backgroundColor':'#123456'}]):
   result=c.apply_label({'summary':'林小姐 F','colorId':'9'},'美容')
   self.assertEqual(result['eventLabelId'],'custom-blue');self.assertNotIn('colorId',result)
 def test_deadline_stays_task(self):
  self.assertIsNone(c.handle(UID,'明天下午3點前傳資料'))
 def test_digest_with_calendar(self):
  event={'summary':'美容預約','start':{'dateTime':'2026-10-08T14:00:00+08:00'},'end':{'dateTime':'2026-10-08T15:00:00+08:00'}}
  with patch('lifeos_calendar.today_events',return_value=([event],None)):
   data=str(l.button_message(l.summary([],NOW,user_id=UID)).to_dict())
   self.assertIn('今日預計行程',data);self.assertIn('美容預約',data)
 def test_missing_draft_no_write(self):
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos.gateway',return_value={'draft':None}),patch('lifeos_calendar.call') as api:
   self.assertIn('沒有行程草稿',c.handle(UID,'確認行程').alt_text);api.assert_not_called()
 def test_duplicate_create_recovers(self):
  event={'summary':'Test','start':{'dateTime':'2026-10-09T14:00:00+08:00'},'end':{'dateTime':'2026-10-09T15:00:00+08:00'}}
  draft={'operation':'create','calendar_id':'cal','event_id':'fixed','event':event}
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos.gateway') as db,patch('lifeos_calendar.call') as api:
   db.side_effect=[{'draft':draft},{'event':{'id':1}}];api.side_effect=[c.CalendarError('duplicate'),event]
   self.assertIn('已更新',c.handle(UID,'確認行程').alt_text)
   self.assertEqual(api.call_args.args,('GET','/fixed'))
 def test_not_own_event(self):
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos.gateway',return_value={'event':None}),patch('lifeos_calendar.call') as api:
   self.assertIn('補充',c.handle(UID,'改期行程 1 明天下午2點到下午3點').alt_text);api.assert_not_called()

if __name__=='__main__': unittest.main()

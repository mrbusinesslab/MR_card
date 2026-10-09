import os
import unittest
from datetime import datetime
from unittest.mock import patch
import lifeos as l
import lifeos_calendar as c

UID='U'+'1'*32
NOW=datetime(2026,10,8,15,tzinfo=l.TZ)
REAL_DAY_BOOKINGS=c.day_bookings

class CalendarTests(unittest.TestCase):
 def setUp(self):
  self.bookings=patch("lifeos_calendar.day_bookings",return_value=([],[]));self.bookings.start();self.addCleanup(self.bookings.stop)
 def test_default_beauty_duration(self):
  for title in ('林小姐 F','林小姐 B','陳小姐 F+B（新客）'):
   _,start,end=c.parse_booking('明天下午2點 '+title,NOW)
   self.assertEqual((end-start).total_seconds(),10800 if 'F+B' in title else 5400)
  _,start,end=c.parse_booking('明天下午2點到下午3點 林小姐 F',NOW)
  self.assertEqual((end-start).total_seconds(),3600)
 def test_overlap_requires_second_confirmation(self):
  event={'id':'busy','summary':'林小姐 F','start':{'dateTime':'2026-10-09T14:00:00+08:00'},'end':{'dateTime':'2026-10-09T15:30:00+08:00'}}
  draft={'calendar_id':'cal','event_id':'new','operation':'create','event':{**event,'summary':'陳小姐 F'}}
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos.gateway') as db,patch('lifeos_calendar.call') as api,patch('lifeos_calendar.day_bookings',return_value=([event],[event])):
   db.side_effect=[{'draft':draft},{'ok':True}]
   self.assertEqual(c.handle(UID,'確認行程').alt_text,'預約時間重疊');api.assert_not_called()
 def test_adjacent_events_do_not_overlap(self):
  target={'start':{'dateTime':'2026-10-09T14:00:00+08:00'},'end':{'dateTime':'2026-10-09T15:30:00+08:00'}}
  events=[{'id':'adjacent','start':{'dateTime':'2026-10-09T13:00:00+08:00'},'end':{'dateTime':'2026-10-09T14:00:00+08:00'}},{'id':'overlap','start':{'dateTime':'2026-10-09T15:00:00+08:00'},'end':{'dateTime':'2026-10-09T16:00:00+08:00'}}]
  with patch('lifeos_calendar.call',return_value={'items':events}):
   _,conflicts=REAL_DAY_BOOKINGS(target)
   self.assertEqual([e['id'] for e in conflicts],['overlap'])
 def test_duplicate_preview_does_not_create(self):
  event={'id':'existing','summary':'林小姐 F','start':{'dateTime':'2026-10-09T14:00:00+08:00'},'end':{'dateTime':'2026-10-09T15:30:00+08:00'}}
  with patch('lifeos_calendar.day_bookings',return_value=([event],[event])),patch('lifeos_calendar.call') as api:
   result=c.preview({'event':event,'operation':'create','event_id':'new'},UID)
   self.assertIn('已經建立',result.alt_text);api.assert_not_called()
 def test_name_move_keeps_duration(self):
  current={'id':'existing','etag':'etag','summary':'林小姐 F','start':{'dateTime':'2026-10-09T14:00:00+08:00'},'end':{'dateTime':'2026-10-09T15:30:00+08:00'}}
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos.clock',return_value=NOW),patch('lifeos_calendar.named_candidates',return_value=[current]),patch('lifeos_calendar.call',return_value=current) as api,patch('lifeos.gateway',return_value={'ok':True}) as db:
   result=c.handle(UID,'林小姐改到明天下午三點','evt')
   self.assertIn('確認改期',result.alt_text)
   event=db.call_args.kwargs['payload']['event']
   self.assertIn('T15:00:00',event['start']['dateTime']);self.assertIn('T16:30:00',event['end']['dateTime'])
   self.assertEqual(api.call_count,1)
 def test_name_not_found_never_creates(self):
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos_calendar.named_candidates',return_value=[]),patch('lifeos_calendar.call') as api:
   self.assertIn('找不到',c.handle(UID,'林小姐改到明天下午三點').alt_text);api.assert_not_called()
 def test_multiple_names_asks_before_write(self):
  event={'id':'one','local_id':1,'summary':'林小姐 F','start':{'dateTime':'2026-10-09T14:00:00+08:00'},'end':{'dateTime':'2026-10-09T15:30:00+08:00'}}
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos_calendar.named_candidates',return_value=[event,{**event,'id':'two','local_id':2}]),patch('lifeos.gateway',return_value={'ok':True}),patch('lifeos_calendar.call') as api:
   result=c.handle(UID,'取消林小姐的預約','evt')
   self.assertIn('請選擇',result.alt_text);api.assert_not_called()
 def test_cancel_confirmation_updates_google(self):
  event={'summary':'林小姐 F','start':{'dateTime':'2026-10-09T14:00:00+08:00'},'end':{'dateTime':'2026-10-09T15:30:00+08:00'}}
  draft={'calendar_id':'cal','event_id':'existing','operation':'cancel','etag':'expected','event':event}
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos.gateway') as db,patch('lifeos_calendar.call') as api:
   db.side_effect=[{'draft':draft},{'ok':True}];api.side_effect=[event,{'status':'cancelled'}]
   self.assertIn('已取消',c.handle(UID,'確認取消行程').alt_text)
   self.assertEqual(api.call_args.kwargs['body'],{'status':'cancelled'})
   self.assertEqual(api.call_args.kwargs['etag'],'expected')
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
  self.assertEqual(l.category_style('傑哥 電子名片')[0],'交流')
  self.assertEqual(l.category_style('max 開會')[0],'交流')
  self.assertEqual(l.category_style('林小姐 F')[0],'美容')
  self.assertEqual(l.category_style('max')[0],'其他')
  self.assertEqual(l.category_style('傑哥')[0],'其他')
 def test_business_details_skip_category_buttons(self):
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos.gateway',return_value={'ok':True}) as db,patch('lifeos_calendar.call') as api:
   for title in ('max 開會','傑哥 電子名片'):
    self.assertEqual(c.handle(UID,'明天下午2點到下午3點 '+title,'evt').alt_text,'確認Google行程')
    self.assertEqual(db.call_args.kwargs['payload']['category'],'交流')
    self.assertNotIn('needs_category',db.call_args.kwargs['payload'])
   api.assert_not_called()
 def test_name_only_asks_category(self):
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos.gateway',return_value={'ok':True}),patch('lifeos_calendar.call') as api:
   self.assertEqual(c.handle(UID,'明天下午2點到下午3點 max','evt').alt_text,'請選擇排程類型')
   api.assert_not_called()
 def test_pending_category_blocks_write(self):
  draft={'calendar_id':'cal','operation':'create','needs_category':True,'event':{'summary':'max 開會','start':{'dateTime':'2026-10-09T14:00:00+08:00'},'end':{'dateTime':'2026-10-09T15:00:00+08:00'}}}
  with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':UID,'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos.gateway',return_value={'draft':draft}),patch('lifeos_calendar.call') as api:
   result=c.handle(UID,'確認行程')
   self.assertIn('請選擇',result.alt_text);api.assert_not_called()
 def test_business_choice_preserves_title(self):
  draft={'calendar_id':'cal','operation':'create','needs_category':True,'event':{'summary':'max 開會','start':{'dateTime':'2026-10-09T14:00:00+08:00'},'end':{'dateTime':'2026-10-09T15:00:00+08:00'}}}
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

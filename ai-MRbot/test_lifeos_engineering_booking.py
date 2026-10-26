import unittest
from datetime import datetime
from unittest.mock import patch
import lifeos as l
import lifeos_calendar as c
import lifeos_engineering_booking as b
from lifeos_settings import Profile,use_profile
REAL_DAY_BOOKINGS=c.day_bookings
UID='U'+'1'*32
FORM='日期：10/30 下午2點到3點\n案場名稱：測試案場\n預約工程：場勘\n地點：台中市北屯區測試路1號'
class BookingTests(unittest.TestCase):
 def setUp(self):
  b._PARTIAL.clear()
  self.ctx=use_profile(Profile('fixture','工程',{'LIFEOS_TENANT_ID':'fixture','LIFEOS_INDUSTRY':'engineering','LIFEOS_ENGINEERING_WORKFLOW':'1'}));self.ctx.__enter__()
  self.addCleanup(lambda:self.ctx.__exit__(None,None,None));self.addCleanup(patch.stopall)
  patch('lifeos.clock',return_value=datetime(2026,10,26,12,tzinfo=l.TZ)).start()
  patch('lifeos_calendar.calendar_access',return_value=True).start()
  patch('lifeos_calendar.config',return_value=({},'fixture-cal',UID)).start()
  self.db=patch('lifeos.gateway',return_value={'ok':True}).start()
  patch('lifeos_calendar.day_bookings',return_value=([],[])).start()
 def test_four_fields_create_only_draft_with_location_and_map(self):
  result=b.handle(c,UID,FORM,'evt','user')
  self.assertEqual(result.alt_text,'確認工程預約')
  self.assertIn('Google 地圖',str(result.to_dict()))
  draft=self.db.call_args.kwargs['payload']
  self.assertIn('T14:00',draft['event']['start']['dateTime']);self.assertIn('T15:00',draft['event']['end']['dateTime'])
  self.assertEqual(draft['event']['location'],'台中市北屯區測試路1號')
  self.assertEqual(draft['category'],'場勘')
  self.assertEqual([x.args[0] for x in self.db.call_args_list],['calendar_draft'])
 def test_date_only_is_all_day_and_duplicate_safe(self):
  result=b.handle(c,UID,FORM.replace('10/30 下午2點到3點','10/30'),'evt','user')
  draft=self.db.call_args.kwargs['payload'];event=draft['event']
  self.assertEqual(event['start'],{'date':'2026-10-30'});self.assertEqual(event['end'],{'date':'2026-10-31'})
  self.assertEqual(c.duplicate_event(event,[event]),event)
 def test_missing_location_can_be_completed_and_cancelled(self):
  self.assertIn('請補上：地點',str(b.handle(c,UID,FORM.split('\n地點：')[0],'evt','user').to_dict()))
  self.db.assert_not_called()
  self.assertEqual(b.handle(c,UID,'台中車站','evt2','user').alt_text,'確認工程預約')
  b.handle(c,UID,FORM.split('\n地點：')[0],'evt3','user')
  b.handle(c,UID,'取消工程預約','evt4','user');self.assertNotIn(('fixture',UID),b._PARTIAL)
 def test_single_sentence_and_invalid_time(self):
  self.assertEqual(b.handle(c,UID,'10/30下午2點到3點，測試案場場勘，地點台中車站','evt','user').alt_text,'確認工程預約')
  self.db.reset_mock()
  self.assertEqual(b.handle(c,UID,FORM.replace('下午2點到3點','下午2點'),'bad','user').alt_text,'新增工程預約')
  self.db.assert_not_called()
 def test_all_day_overlap_checks_timed_events(self):
  event={'start':{'date':'2026-10-30'},'end':{'date':'2026-10-31'}}
  existing={'id':'event','start':{'dateTime':'2026-10-30T14:00:00+08:00'},'end':{'dateTime':'2026-10-30T15:00:00+08:00'}}
  with patch('lifeos_calendar.call',return_value={'items':[existing]}):
   self.assertEqual(REAL_DAY_BOOKINGS(event)[1],[existing])
 def test_case_creation_is_only_after_confirmation_and_does_not_replace_existing(self):
  draft={'event_id':'fixed','engineering_booking':b.fields(FORM)}
  with patch('lifeos_engineering.cases',return_value=[{'name':'測試案場'}]):b.ensure_case(UID,draft)
  self.db.assert_not_called()
  with patch('lifeos_engineering.cases',return_value=[]):b.ensure_case(UID,draft)
  self.assertEqual(self.db.call_args.args[:3],('engineering_create',UID,'booking-case:fixed'))
 def test_confirmation_saves_google_location_then_creates_case(self):
  b.handle(c,UID,FORM,'draft','user');draft=self.db.call_args.kwargs['payload'];self.db.reset_mock()
  self.db.side_effect=lambda action,*args,**kw: {'draft':draft} if action=='calendar_get_draft' else {'ok':True}
  with patch('lifeos_calendar_list_flow.handle',return_value=None),patch('lifeos_engineering.cases',return_value=[]),patch('lifeos_calendar.call',return_value={**draft['event'],'id':draft['event_id']}) as google:
   result=c.handle(UID,'確認行程','confirm')
  self.assertEqual(result.alt_text,'Google行程已更新')
  self.assertEqual(google.call_args.kwargs['body']['location'],'台中市北屯區測試路1號')
  actions=[x.args[0] for x in self.db.call_args_list]
  self.assertLess(actions.index('calendar_save'),actions.index('engineering_create'))
  self.assertIn('Google 地圖',str(result.to_dict()))

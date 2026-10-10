import unittest
from unittest.mock import patch
from datetime import datetime
import lifeos as l
from mr_message_routing import is_date_query, is_lifeos_command
class DateQueryTests(unittest.TestCase):
 def test_pattern_only_bare_dates(self):
  for x in ('10/12','2026/10/12','1/2'):self.assertTrue(is_date_query(x));self.assertTrue(is_lifeos_command(x))
  for x in ('10/12 13:30 小孟','阮凱程','2026/10'):self.assertFalse(is_date_query(x))
 def test_target_day_tasks_calendar_and_no_write(self):
  tasks=[{'id':1,'title':'當天事項','due_at':'2026-10-12T00:00:00+08:00'},{'id':2,'title':'其他天事項','due_at':'2026-10-13T00:00:00+08:00'}]
  def gateway(action,*a,**kw):
   if action=='get_user':return {'user':{}}
   if action=='list':return {'tasks':tasks}
   raise AssertionError(action)
  import lifeos_calendar as c
  with patch.dict('os.environ',{'LIFEOS_ENABLED':'1'}),patch.object(l,'gateway',side_effect=lambda a,*args,**kw: {'user':{'active':True}} if a=='get_user' else gateway(a,*args,**kw)),patch.object(l,'clock',return_value=datetime(2026,10,10,tzinfo=l.TZ)),patch.object(c,'today_events',return_value=([],None)) as events:
   d=l.handle_text('user','10/12');self.assertEqual(d.now.day,12)
   msg=str(l.button_message(d).to_dict());self.assertIn('當天事項',msg);self.assertNotIn('其他天事項',msg)
   self.assertEqual(events.call_args.args[1].day,12)
   self.assertIn('日期無效',l.handle_text('user','2/30'))
 def test_pending_postpone_preserved(self):
  with patch.dict('os.environ',{'LIFEOS_ENABLED':'1'}),patch.object(l,'gateway',side_effect=[{'user':{'pending_postpone':{'title':'任務'}}},{'task':{'id':1,'title':'任務','due_at':'2026-10-12T15:59:00Z'}}]) as db:
   l.handle_text('user','10/12')
   self.assertEqual(db.call_args.args[0],'postpone_finish')

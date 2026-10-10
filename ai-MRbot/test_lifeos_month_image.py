import io
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
from PIL import Image
import lifeos_week_image as w
import lifeos_month_image as m
class MonthImageTests(unittest.TestCase):
 def now(self,y=2026,mo=10):return datetime(y,mo,10,18,tzinfo=ZoneInfo('Asia/Taipei'))
 def test_six_week_month_and_label_color(self):
  now=self.now(2026,8);start=now.replace(day=1,hour=0)
  e={'summary':'跨日美容預約','eventLabelId':'label','start':{'date':'2026-08-30'},'end':{'date':'2026-09-02'}}
  data=m.render_month([e],start,now,{'label':'#81b7dd'})
  img=Image.open(io.BytesIO(data));self.assertEqual(img.width,2100);self.assertGreaterEqual(img.height,1845)
  self.assertTrue(any(color==(129,183,221) for _,color in img.getcolors(img.width*img.height)))
 def test_monthly_message_uses_month_bounds_and_private_filter(self):
  import lifeos_calendar as c
  now=self.now()
  with patch.object(c,'config',return_value=({},'cal','owner')),patch.object(c,'calendar_access',return_value=True),patch.object(w,'week_events',return_value=[]) as fetch,patch.object(c,'visible_events',return_value=[]) as visible,patch.object(c,'event_labels',return_value=[]),patch.object(m,'render_month',return_value=b'png'),patch.object(w,'signature',return_value='sig'):
   msg=w.weekly_message('owner',now,period='month')
   self.assertEqual(fetch.call_args.args[0].day,1);self.assertEqual(fetch.call_args.args[1].month,11)
   visible.assert_called_once_with('owner',[]);self.assertIn('signature=sig',msg.original_content_url)
 def test_month_digest_returns_image_plus_tasks(self):
  import lifeos as l
  with patch.object(w,'weekly_message',return_value='image') as render:
   digest=l.Digest('',[],self.now(),'month');digest.user_id='owner'
   result=l.button_message(digest)
   self.assertEqual(result[0],'image');self.assertEqual(render.call_args.kwargs['period'],'month')

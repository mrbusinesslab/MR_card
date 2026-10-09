import io
import os
import tempfile
import time
import unittest
from datetime import datetime,timedelta
from pathlib import Path
from unittest.mock import patch
from flask import Flask
from PIL import Image
import lifeos as l
import lifeos_week_image as w

NOW=datetime(2026,10,9,18,30,tzinfo=l.TZ)
START,END=l.period_bounds(NOW,'week')

class WeekImageTests(unittest.TestCase):
    def test_monday_to_sunday_and_exclusive_all_day_end(self):
        event={'start':{'date':'2026-10-05'},'end':{'date':'2026-10-07'}}
        self.assertEqual(w.event_days(event,START,END),[(0,'全天'),(1,'全天')])
        event={'start':{'dateTime':'2026-10-11T23:00:00+08:00'},'end':{'dateTime':'2026-10-12T01:00:00+08:00'}}
        self.assertEqual(w.event_days(event,START,END),[(6,'23:00～01:00')])

    def test_reads_all_pages_and_omits_cancelled(self):
        with patch('lifeos_calendar.call',side_effect=[{'items':[{'id':'one'}],'nextPageToken':'next'},{'items':[{'id':'two'},{'id':'gone','status':'cancelled'}]}]) as api:
            self.assertEqual([e['id'] for e in w.week_events(START,END)],['one','two'])
            self.assertEqual(api.call_args.kwargs['params']['pageToken'],'next')

    def test_signed_image_rejects_tampering_and_expiry(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(w,'ROOT',Path(directory)),patch.dict(os.environ,{'LIFEOS_CRON_KEY':'test-secret'}):
            key='a'*48; expiry=int(time.time())+60
            (Path(directory)/(key+'.png')).write_bytes(b'test-image')
            app=Flask(__name__);w.install_routes(app);client=app.test_client()
            url='/lifeos/week-image/'+key+'.png?expires='+str(expiry)+'&signature='+w.signature(key,expiry)
            response=client.get(url)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.mimetype,'image/png')
            self.assertEqual(client.get(url+'x').status_code,404)
            with patch('lifeos_week_image.time.time',return_value=expiry+1):
                self.assertEqual(client.get(url).status_code,404)

    def test_other_user_never_reads_calendar(self):
        with patch('lifeos_calendar.config',return_value=({},'calendar','approved')),patch.object(w,'week_events') as api:
            self.assertIsNone(w.weekly_message('someone-else',NOW))
            api.assert_not_called()

if __name__=='__main__': unittest.main()

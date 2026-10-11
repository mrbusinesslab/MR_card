import copy
import unittest
from unittest.mock import Mock
import lifeos_calendar as c
from lifeos_calendar_batch import import_batch
from lifeos_calendar_list import review_list

class BatchTests(unittest.TestCase):
    def test_partial_retry_same_id_no_meet(self):
        fake=Mock(wraps=c);fake.l=Mock(wraps=c.l);fake.l.gateway=Mock(return_value={});fake.l.TZ=c.l.TZ;fake.l.StorageError=c.l.StorageError;fake.CalendarError=c.CalendarError
        fake.apply_label=lambda body,group:body
        draft={'calendar_id':'test','review_id':'abc','review':review_list('2026/10/12\n09:00–10:00 測試會議\n講座待補',2026)}
        fake.call=Mock(side_effect=lambda method,**kw:kw['body'])
        fake.l.gateway.side_effect=lambda action,*a,**k: (_ for _ in ()).throw(c.l.StorageError('fail')) if action=='calendar_save' else {}
        import_batch(fake,'one',draft,None)
        key=fake.call.call_args.kwargs['body']['id']
        self.assertIsNone(fake.call.call_args.kwargs['body']['conferenceData'])
        self.assertEqual(fake.call.call_args.kwargs['body']['summary'],'測試會議')
        self.assertTrue(draft['review']['entries'][0]['write_started'])
        fake.l.gateway.side_effect=None
        fake.call.side_effect=[c.CalendarError('409'),{'summary':'測試會議','start':{'dateTime':'2026-10-12T09:00:00+08:00','timeZone':'Asia/Taipei'},'end':{'dateTime':'2026-10-12T10:00:00+08:00','timeZone':'Asia/Taipei'}}]
        import_batch(fake,'one',draft,None)
        self.assertEqual(fake.call.call_args_list[-2].kwargs['body']['id'],key)
        self.assertTrue(draft['review']['entries'][0]['imported'])
        self.assertFalse(draft['review']['entries'][1].get('imported',False))
        calls=fake.call.call_count;import_batch(fake,'one',draft,None)
        self.assertEqual(fake.call.call_count,calls)
    def test_background_returns_before_slow_import(self):
        import threading
        from unittest.mock import patch
        import lifeos_calendar_batch as batch
        entered=threading.Event();release=threading.Event()
        fake=Mock(wraps=c)
        draft={'calendar_id':'test','review_id':'async','review':{'errors':[],'entries':[]}}
        def slow(*args):entered.set();release.wait(2)
        try:
            with patch.object(batch,'import_batch',side_effect=slow) as run:
                result=batch.start_import(fake,'one',draft,None)
                self.assertTrue(entered.wait(1))
                self.assertEqual(result.alt_text,'正在加入日曆')
                batch.start_import(fake,'one',draft,None)
                self.assertEqual(run.call_count,1)
        finally:release.set()
    def test_completion_uses_reply_only_once(self):
        from unittest.mock import patch
        from lifeos_calendar_batch import FreeReply
        r=FreeReply(c,'one',{'review_id':'token'});r.token='fixture'
        with patch('requests.post') as post:
            r.send(c.card('已完成',['11 筆']));r.send(c.card('已完成',['11 筆']))
            post.assert_called_once()
            self.assertTrue(post.call_args.args[0].endswith('/message/reply'))
    def test_errors_block_writes(self):
        fake=Mock(wraps=c)
        import_batch(fake,'one',{'review':{'errors':['bad weekday']}},None)
        fake.call.assert_not_called()
if __name__=='__main__':unittest.main()

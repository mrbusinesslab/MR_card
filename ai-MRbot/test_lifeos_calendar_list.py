import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
from lifeos_calendar_list import review_list, reply_text

EXAMPLE='''📅 10/12（一）
* 均均休假
* 換引擎腳
* 13:30 講座
* 吳佳蓉 B（截圖文字不完整）
📅 10/13（二）
* 內部（名片）
* 均均休假
📅 10/14（三）
* Yumi 老…（文字不完整）
* 陳婉文 F（截圖文字不完整）'''

class ReviewTests(unittest.TestCase):
    def test_user_list_categories_and_dates(self):
        r=review_list(EXAMPLE,2026)
        self.assertEqual(len(r['entries']),8)
        self.assertFalse(r['errors'])
        self.assertEqual([e['kind'] for e in r['entries']],['all_day','needs_time','start_only','needs_time','needs_time','all_day','needs_time','needs_time'])
        self.assertEqual(sum(e['incomplete'] for e in r['entries']),3)
        self.assertEqual(r['entries'][2]['times'],['13:30'])
        self.assertEqual(r['entries'][7]['date'],'2026-10-14')
        self.assertIn('先保留原文',reply_text(r))
        self.assertIn('尚未加入Google日曆',reply_text(r))
    def test_markdown_headers_and_bullets(self):
        r=review_list('[📅](https://example.com/calendar.png) **10/12（一）**\\\n\\\n* 均均休假\\',2026)
        self.assertEqual(r['entries'][0]['title'],'均均休假')
    def test_timed_events_and_overlapping_leave_word(self):
        r=review_list('10/12（一）\n18:00～21:00 吳佳蓉 B\n09:00～10:00 討論休假\n1:30 講座',2026)
        self.assertEqual([e['kind'] for e in r['entries']],['complete','complete','start_only'])
        self.assertIn('上午或下午','；'.join(r['entries'][2]['notes']))
    def test_invalid_date_weekday_and_time_remain_unconfirmed(self):
        r=review_list('2026/10/12（二）\n25:00 講座\n10/32\n不能遺失的事項',2026)
        self.assertEqual(r['entries'][0]['kind'],'needs_time')
        self.assertEqual(len(r['errors']),3)
        self.assertIn('日期與星期需確認',r['entries'][0]['notes'])
    def test_ad_and_emoji_not_invented_as_named_event(self):
        r=review_list('10/12\n😇😇😇',2026)
        self.assertIn('沒有可辨識','；'.join(r['entries'][0]['notes']))
    def test_non_calendar_input_does_not_intercept_original_features(self):
        for text in ('生活助理','阮凱程','明天買耗材','行程 明天15:00～16:00 開會','10/12 明天的任務'):
            self.assertIsNone(review_list(text,2026),text)
    def test_multiple_times_or_overnight_require_confirmation(self):
        for line in ('18:00 或19:00 講座','23:00～01:00 活動','13:00 14:00 15:00 活動'):
            self.assertEqual(review_list('10/12\n'+line,2026)['entries'][0]['kind'],'needs_time')
    def test_size_limit_never_silently_saves_partial_batch(self):
        r=review_list('10/12\n'+'\n'.join('事件'+str(i) for i in range(31)),2026)
        self.assertTrue(r['limited']);self.assertEqual(len(r['entries']),30)
        self.assertIn('最多整理30筆',reply_text(r))

class CalendarIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import lifeos_calendar
        cls.calendar=lifeos_calendar
    def test_review_saves_only_draft_and_returns_cards(self):
        with patch.object(self.calendar,'calendar_access',return_value=True),patch.object(self.calendar,'call') as google,patch.object(self.calendar.l,'gateway') as db:
            result=self.calendar.handle('fixture-user',EXAMPLE,'fixture-event')
        self.assertIn('8筆',result.alt_text)
        self.assertEqual(len(result.contents.contents),9)
        google.assert_not_called()
        self.assertEqual(db.call_args.args[0],'calendar_draft')
        self.assertEqual(db.call_args.kwargs['payload']['operation'],'list_review')
    def test_private_and_enrolled_access_required(self):
        with patch.object(self.calendar,'calendar_access',return_value=False):
            result=self.calendar.handle('fixture-user',EXAMPLE,'fixture-event')
            self.assertEqual(result.alt_text,'Google日曆尚未啟用')
        result=self.calendar.handle('fixture-user',EXAMPLE,'fixture-event','group')
        self.assertEqual(result.alt_text,'私人日曆')
if __name__=='__main__':unittest.main()

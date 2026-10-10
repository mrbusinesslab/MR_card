import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
import lifeos_calendar as c
class PersonBookingTests(unittest.TestCase):
    def test_xiaomeng_without_service_suffix_has_three_hours(self):
        now=datetime(2026,10,10,12,tzinfo=ZoneInfo('Asia/Taipei'))
        for title in ('小孟','🏠小孟','小孟 F'):
            name,start,end=c.parse_booking('2026/10/20 13:30 '+title,now)
            self.assertEqual((end-start).total_seconds(),10800)
            self.assertEqual(name,title)
            self.assertEqual(c.booking_category(title),'美容')
    def test_explicit_end_is_preserved(self):
        _,start,end=c.parse_booking('2026/10/20 13:30～17:30 小孟')
        self.assertEqual((end-start).total_seconds(),14400)
    def test_other_names_not_matched(self):
        for title in ('小孟老師','大小孟','小孟子'):
            self.assertFalse(c.is_xiaomeng(title))

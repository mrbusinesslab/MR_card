import unittest
import lifeos_calendar as c
from test_lifeos_calendar_list_flow import FlowTests


class DayFillTests(FlowTests):
    def begin(self,text):
        c.handle('one',text)
        return self.press('清單補齊')

    def press(self,command):
        return c.handle('one',command+' '+self.drafts['one']['review_id'])

    def test_whole_day_then_explicit_next_day(self):
        msg=self.begin('2026/10/12\n王小姐 B\n13:30 講座\n2026/10/13\n小孟')
        self.assertIn('2026-10-12',msg.alt_text)
        msg=c.handle('one','王小姐下午兩點，講座到下午三點半')
        e=self.drafts['one']['review']['entries']
        self.assertEqual(e[0]['times'],['14:00','15:30'])
        self.assertEqual(e[1]['times'],['13:30','15:30'])
        self.assertEqual(e[2]['times'],[])
        self.assertIn('確認當天',msg.alt_text)
        self.assertIn('2026-10-13',self.press('清單當天').alt_text)
        c.handle('one','14:00')
        self.assertEqual(self.drafts['one']['review']['entries'][2]['times'],['14:00','17:00'])
        self.assertEqual(self.press('清單當天').alt_text,'所有日期已補齊')

    def test_incomplete_day_cannot_advance(self):
        self.begin('2026/10/12\n王小姐 B\n13:30 講座\n2026/10/13\n小孟')
        c.handle('one','王小姐14:00')
        msg=self.press('清單當天')
        self.assertIn('2026-10-12',msg.alt_text)
        self.assertEqual(self.drafts['one']['review']['entries'][1]['kind'],'start_only')

    def test_numbers_duplicate_names_and_unrecognized_text(self):
        self.begin('2026/10/12\n王小姐 B\n王小姐 F')
        msg=c.handle('one','王小姐下午兩點')
        self.assertEqual(self.drafts['one']['review']['entries'][0]['times'],[])
        c.handle('one','1 下午兩點\n2 下午四點\n完全不相關')
        e=self.drafts['one']['review']['entries']
        self.assertEqual(e[0]['times'],['14:00','15:30'])
        self.assertEqual(e[1]['times'],['16:00','17:30'])

    def test_invalid_date_can_be_repaired_for_day(self):
        self.begin('2026/10/32\n10:00～11:00 A會議\n14:00～15:00 B會議')
        msg=c.handle('one','2026/10/16')
        self.assertIn('確認當天',msg.alt_text)
        self.assertTrue(all(e['date']=='2026-10-16' for e in self.drafts['one']['review']['entries']))

    def test_stale_confirmation_and_other_user_blocked(self):
        self.begin('2026/10/12\n王小姐 B')
        old=self.drafts['one']['review_id']
        c.handle('one','下午兩點')
        self.assertEqual(c.handle('one','清單當天 '+old).alt_text,'這張卡片已更新')
        self.assertEqual(c.handle('two','清單當天 '+self.drafts['one']['review_id']).alt_text,'清單草稿已失效')

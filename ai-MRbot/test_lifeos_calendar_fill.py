import unittest
from unittest.mock import Mock,patch
import lifeos_calendar as c
import lifeos_calendar_list_flow as f
from lifeos_calendar_list import review_list
from lifeos_calendar_fill import fill_entry
from lifeos_calendar_batch import payload
from test_lifeos_calendar_list_flow import FlowTests

class FillTests(unittest.TestCase):
    def test_short_answers(self):
        cases=[('王小姐 B','下午兩點','14:00～15:30'),('13:30 講座','下午三點','13:30～15:00'),('王小姐 F+B','14:00','14:00～17:00')]
        for title,answer,times in cases:
            e=review_list('2026/10/12\n'+title,2026)['entries'][0]
            self.assertIn(times,fill_entry(c,e,answer))
    def test_invalid_date_preserved_and_blocked_individually(self):
        r=review_list('2026/10/12\n09:00～10:00 正常會議\n2026/10/15（一）\n09:00～10:00 日期有問題\n2026/10/32\n10:00～11:00 不可遺失',2026)
        self.assertEqual(len(r['entries']),3)
        self.assertTrue(r['entries'][1]['date_problem']);self.assertTrue(r['entries'][2]['date_problem'])
        self.assertIsNone(payload(r['entries'][1],c));self.assertIsNone(payload(r['entries'][2],c))
        self.assertEqual(fill_entry(c,r['entries'][2],'2026/10/16'),'2026-10-16\n10:00～11:00 不可遺失')
        f.cards({'review':r,'review_id':'test'})
    def test_no_guess_ambiguous_time(self):
        e=review_list('2026/10/12\n王小姐 B',2026)['entries'][0]
        self.assertIsNone(fill_entry(c,e,'兩點'))

class GuidedFlowTests(FlowTests):
    def assert_valid_text(self,message):
        def walk(node):
            if isinstance(node,dict):
                if node.get('type')=='text':self.assertTrue(node.get('text','').strip(),node)
                for value in node.values():walk(value)
            elif isinstance(node,list):
                for value in node:walk(value)
        walk(message.contents.to_dict())

    def test_initial_and_already_complete_cards_have_no_empty_text(self):
        for title in ('王小姐 B','09:00～10:00 會議'):
            c.handle('one','2026/10/12\n'+title)
            token=self.drafts['one']['review_id']
            self.assert_valid_text(c.handle('one','清單補齊 '+token))

    def test_guided_answer_updates_original_entry(self):
        c.handle('one','2026/10/12\n王小姐 B\n13:30 講座')
        token=self.drafts['one']['review_id']
        msg=c.handle('one','清單補齊 '+token)
        self.assertIn('補當天資料',msg.alt_text)
        self.assert_valid_text(msg)
        msg=c.handle('one','王小姐下午兩點')
        self.assertIn('補當天資料',msg.alt_text)
        self.assert_valid_text(msg)
        self.assertEqual(self.drafts['one']['review']['entries'][0]['times'],['14:00','15:30'])
        msg=c.handle('one','下午三點')
        self.assertIn('確認當天',msg.alt_text)
        self.assert_valid_text(msg)
        token=self.drafts['one']['review_id']
        self.assertEqual(c.handle('one','清單當天 '+token).alt_text,'所有日期已補齊')
if __name__=='__main__':unittest.main()

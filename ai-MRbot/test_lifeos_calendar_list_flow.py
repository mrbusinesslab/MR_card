import copy
import unittest
from unittest.mock import patch
import lifeos_calendar as c
import lifeos_calendar_list_flow as f
from test_lifeos_calendar_list import EXAMPLE

class FlowTests(unittest.TestCase):
    def setUp(self):
        f._PENDING.clear();self.drafts={}
        def gateway(action,uid,*args,**kw):
            if action=='calendar_draft':self.drafts[uid]=copy.deepcopy(kw['payload']);return {}
            if action=='calendar_get_draft':return {'draft':copy.deepcopy(self.drafts.get(uid))}
            raise AssertionError(action)
        self.patches=[patch.object(c,'calendar_access',return_value=True),patch.object(c,'config',return_value=({},'calendar','owner')),patch.object(c.l,'gateway',side_effect=gateway),patch.object(c,'call',side_effect=AssertionError('Google must not be called'))]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        c.handle('one',EXAMPLE,'first')
    def command(self,action,idx,uid='one',token=None):
        return c.handle(uid,f'{action} {token or self.drafts[uid]["review_id"]} {idx}','event')
    def test_edit_name_and_time_then_stale_button(self):
        token=self.drafts['one']['review_id'];self.command('清單修改',3)
        c.handle('one','18:00～21:00 吳佳蓉 B','edit')
        e=self.drafts['one']['review']['entries'][3]
        self.assertEqual(e['kind'],'complete');self.assertFalse(e['incomplete'])
        self.assertFalse(f.is_editing('one'))
        self.assertEqual(self.command('清單移除',3,token=token).alt_text,'這張卡片已更新')
        self.assertEqual(len(self.drafts['one']['review']['entries']),8)
    def test_other_user_cannot_edit_and_calendar_scope(self):
        token=self.drafts['one']['review_id']
        self.assertEqual(c.handle('two',f'清單移除 {token} 0').alt_text,'清單草稿已失效')
        with patch.object(c,'config',return_value=({},'different','owner')):
            self.assertEqual(self.command('清單移除',0).alt_text,'清單草稿已失效')
        self.assertEqual(len(self.drafts['one']['review']['entries']),8)
    def test_all_day_remove_and_changed_date(self):
        self.command('清單全天',2)
        self.assertEqual(self.drafts['one']['review']['entries'][2]['kind'],'all_day')
        self.command('清單修改',2);c.handle('one','2026/10/15\n15:00～16:00 講座')
        self.assertEqual(self.drafts['one']['review']['entries'][2]['date'],'2026-10-15')
        self.command('清單移除',2)
        self.assertEqual(len(self.drafts['one']['review']['entries']),7)
    def test_bad_edit_and_exit(self):
        self.command('清單修改',0)
        self.assertEqual(c.handle('one','10/15\n第一筆\n第二筆').alt_text,'請只修改一筆')
        self.assertTrue(f.is_editing('one'))
        self.assertFalse(f.claims('one','查資料'));self.assertFalse(f.is_editing('one'))
    def test_pagination_and_expired(self):
        c.handle('one','10/12\n'+'\n'.join('行程'+str(i) for i in range(30)))
        msg=self.command('清單分頁',3)
        self.assertEqual(len(msg.contents.contents),7)
        self.drafts.clear()
        self.assertEqual(c.handle('one','清單總覽').alt_text,'清單草稿已失效')
    def test_confirm_cannot_save_review_as_google_event(self):
        result=c.handle('one','確認行程')
        self.assertIn('確認按鈕',str(result))

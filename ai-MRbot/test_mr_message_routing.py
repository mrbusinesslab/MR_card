import ast
import unittest
from pathlib import Path
from unittest.mock import Mock
from types import SimpleNamespace
from mr_message_routing import prefer_people, PeopleQueryMode, may_be_person_name

class RoutingTests(unittest.TestCase):
    def test_known_names_bypass_without_keyword_matching_sentences(self):
        self.assertTrue(prefer_people('潘 昱如',names=['潘昱如']))
        self.assertTrue(prefer_people('Emma',names=['emma']))
        self.assertFalse(prefer_people('明天把資料傳給林威',names=['林威']))
    def test_pending_search_yields_to_task_commands(self):
        for text in ('本周','新增待辦','完成 12','延期 12','行程 明天下午三點開會','林小姐改到明天下午三點'):
            self.assertFalse(prefer_people(text,pending_search=True),text)
        self.assertTrue(prefer_people('防水',pending_search=True))
    def test_explicit_people_and_categories(self):
        for text in ('電子名片','展示','最近查看的名片','人物資料|林威|card','人物完整|林威|basic','查客戶 阮凱程','追蹤更新|林威|狀態|完成'):
            self.assertTrue(prefer_people(text),text)
        self.assertTrue(prefer_people('建築組',categories=['建築組']))

class HandlerTests(unittest.TestCase):
    """Execute the actual handler with network boundaries replaced, not a copy."""
    def setUp(self):
        tree=ast.parse(Path('people_app.py').read_text())
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='handle_message')
        fn.decorator_list=[]
        module=ast.Module(body=[fn],type_ignores=[])
        self.uid='U'+'1'*32
        self.pending=set()
        self.legacy=SimpleNamespace(CASE_LIST=[{'keyword':'林威','name_keywords':['林威']}],PENDING_SEARCH_USERS=self.pending,
            build_demo_flex=Mock(return_value='demo'),build_recent_flex=Mock(return_value='recent'),CATEGORY_QUICK_REPLIES=[('建築組','建築組')],search_cases=Mock(return_value=[{'case':'test','keyword':'林威'}]),record_view=Mock())
        self.calendar=SimpleNamespace(handle=Mock(return_value=None))
        self.tasks=SimpleNamespace(handle_text=Mock(return_value='incorrect task intercept'),button_message=lambda x:x)
        self.reply=Mock()
        api=Mock();api.__enter__=Mock(return_value=api);api.__exit__=Mock(return_value=False)
        from mr_message_routing import is_lifeos_command
        self.env={'ApiClient':Mock(return_value=api),'configuration':None,'MessagingApi':Mock(),
            'legacy':self.legacy,'lifeos_calendar':self.calendar,'lifeos':self.tasks,
            'prefer_people':prefer_people,'is_lifeos_command':is_lifeos_command,'reply':self.reply,
            'people_query_mode':PeopleQueryMode(),'may_be_person_name':may_be_person_name,
            'normalize':lambda x:''.join(x.split()).lower(),
            'find_card_for_person':Mock(return_value=None),'resolve_people':Mock(return_value=[{'姓名':'林威'}]),
            'build_person_menu':Mock(return_value='person-menu'),'card_delivery_messages':Mock(return_value=['card','url']),
            'TextMessage':lambda **kw:kw,'QuickReplyItem':lambda **kw:kw,'MessageAction':lambda **kw:kw,'QuickReply':lambda **kw:kw}
        exec(compile(module,'people_app.py','exec'),self.env)
    def send(self,text):
        event=SimpleNamespace(message=SimpleNamespace(text=text),source=SimpleNamespace(user_id=self.uid,type='user'),webhook_event_id='event')
        self.env['handle_message'](event)
    def test_card_button_then_search_beats_active_assistant(self):
        self.send('電子名片');self.assertIn(self.uid,self.pending)
        self.send('林威');self.tasks.handle_text.assert_not_called();self.calendar.handle.assert_not_called()
        self.assertEqual(self.reply.call_args.args[2],['card','url'])
        self.assertNotIn(self.uid,self.pending)
    def test_name_and_people_button_bypass_pending_postpone(self):
        self.send('林威');self.tasks.handle_text.assert_not_called()
        self.assertEqual(self.reply.call_args.args[2],'person-menu')
    def test_task_command_clears_old_card_search(self):
        self.pending.add(self.uid);self.send('新增待辦')
        self.tasks.handle_text.assert_called_once();self.assertNotIn(self.uid,self.pending)
    def test_pending_industry_search_is_not_drafted_as_task(self):
        self.pending.add(self.uid);self.send('防水')
        self.legacy.search_cases.assert_called_once_with('防水');self.tasks.handle_text.assert_not_called()
    def test_query_mode_repeats_names_and_switches_back(self):
        self.env['resolve_people'].return_value=[{'姓名':'阮凱程'}]
        self.send('查資料')
        self.assertTrue(self.env['people_query_mode'].active(self.uid))
        self.send('阮凱程');self.send('凱程')
        self.tasks.handle_text.assert_not_called()
        self.assertEqual(self.reply.call_args.args[2],'person-menu')
        self.send('生活助理')
        self.assertFalse(self.env['people_query_mode'].active(self.uid))
        self.tasks.handle_text.assert_called_once()
    def test_exact_bni_name_bypasses_active_task_mode(self):
        self.env['resolve_people'].return_value=[{'姓名':'阮凱程'}]
        self.send('阮凱程')
        self.tasks.handle_text.assert_not_called()
        self.assertEqual(self.reply.call_args.args[2],'person-menu')
    def test_task_sentence_mentioning_name_is_still_task(self):
        self.send('明天把資料傳給阮凱程')
        self.tasks.handle_text.assert_called_once()
        self.env['resolve_people'].assert_not_called()
    def test_query_mode_isolated_and_bounded(self):
        mode=PeopleQueryMode(maximum=2)
        mode.enter('a');mode.enter('b');mode.enter('c')
        self.assertFalse(mode.active('a'));self.assertTrue(mode.active('b'))
        self.assertFalse(mode.active('other'))
        with unittest.mock.patch('mr_message_routing.time.monotonic',return_value=10**15):
            self.assertFalse(mode.active('b'))
    def test_card_tools_stay_inside_data_mode(self):
        self.send('查資料');self.send('電子名片');self.send('林威')
        self.assertTrue(self.env['people_query_mode'].active(self.uid))
        self.send('展示');self.send('最近查看的名片')
        self.assertTrue(self.env['people_query_mode'].active(self.uid))
        self.send('阮凱程');self.tasks.handle_text.assert_not_called()
    def test_card_search_falls_back_to_bni_only_person(self):
        self.legacy.search_cases.return_value=[]
        self.env['resolve_people'].return_value=[{'姓名':'王小明'}]
        self.send('電子名片');self.send('王小明')
        self.assertEqual(self.reply.call_args.args[2],'person-menu')
        self.tasks.handle_text.assert_not_called()
    def test_card_only_person_available_without_bni_row(self):
        self.env['resolve_people'].return_value=[]
        self.env['find_card_for_person'].return_value={'case':'test'}
        self.send('查資料');self.send('林威')
        self.assertEqual(self.reply.call_args.args[2],['card','url'])
    def test_beauty_keyword_stays_in_data_mode(self):
        self.send('查資料');self.send('美容')
        self.tasks.handle_text.assert_not_called()
        self.assertTrue(self.env['people_query_mode'].active(self.uid))
    def test_data_mode_does_not_run_task_actions(self):
        self.send('查資料');self.send('完成 12');self.send('本周')
        self.tasks.handle_text.assert_not_called()
        self.calendar.handle.assert_not_called()
        self.assertTrue(self.env['people_query_mode'].active(self.uid))
if __name__=='__main__': unittest.main()

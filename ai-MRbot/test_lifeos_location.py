import unittest
import inspect
from unittest.mock import patch
import lifeos_location as m
class AddressCopyTests(unittest.TestCase):
 def test_exact_address_is_copied_without_query_or_date(self):
  address='台中市北區測試路32巷21號'
  node=m.address_component(address)
  self.assertEqual(node['action'],{'type':'clipboard','label':'複製地址','clipboardText':address})
  self.assertNotIn('uri',node['action'])
 def test_empty_address_has_no_copy_button(self):
  self.assertNotIn('action',m.address_component('  '))
 def test_surrounding_whitespace_only_is_removed(self):
  self.assertEqual(m.address_component(' 台中市 北區 1號\n')['action']['clipboardText'],'台中市 北區 1號')
 def test_clipboard_action_round_trips_through_line_sdk(self):
  from linebot.v3.messaging import FlexContainer
  bubble={'type':'bubble','body':{'type':'box','layout':'vertical','contents':[m.address_component('地址')]}}
  saved=FlexContainer.from_dict(bubble).to_dict()
  self.assertEqual(saved['body']['contents'][0]['action']['clipboardText'],'地址')

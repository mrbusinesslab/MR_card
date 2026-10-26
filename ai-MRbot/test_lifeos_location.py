import unittest
from unittest.mock import patch,Mock
import lifeos_location as m
class LocationTests(unittest.TestCase):
 def setUp(self):m._CACHE.clear();self.addCleanup(patch.stopall)
 def response(self,rows,status=200,error=None):
  patch('lifeos_location.getenv',return_value='{"client_email":"fixture@example.com","project_id":"fixture"}').start()
  patch('lifeos_location.service_account.Credentials.from_service_account_info',return_value=Mock()).start()
  session=patch('lifeos_location.AuthorizedSession').start().return_value.__enter__.return_value
  session.get.return_value.status_code=status
  session.get.return_value.json.return_value={'results':rows,'error':error or {}}
  return session
 def test_exact_pin_uses_place_id_not_just_search_and_caches(self):
  session=self.response([{'placeId':'ChIJ-fixture','granularity':'ROOFTOP'}])
  url=m.map_url('台中市北區測試路1號')
  self.assertIn('query_place_id=ChIJ-fixture',url)
  self.assertIn('%E5',url)
  m.map_url('台中市北區測試路1號');self.assertEqual(session.get.call_count,1)
 def test_ambiguous_or_imprecise_results_never_have_uri(self):
  for rows in ([],[{'placeId':'one','granularity':'APPROXIMATE'}],[{'placeId':'one'},{'placeId':'two'}]):
   m._CACHE.clear();self.response(rows)
   node=m.map_component('地址');self.assertEqual(node['type'],'text');self.assertNotIn('action',node)
 def test_api_disabled_is_explicit(self):
  self.response([],403,{'details':[{'reason':'SERVICE_DISABLED'}]})
  self.assertIn('尚未啟用',m.map_component('地址')['text'])
 def test_bad_config_never_returns_search_link(self):
  with patch('lifeos_location.getenv',return_value='{}'):
   self.assertEqual(m.map_component('地址')['type'],'text')
 def test_long_address_keeps_line_link_valid(self):
  url=m.map_url('測試地址'*100,place_id='ChIJ-fixture')
  self.assertLessEqual(len(url),1000);self.assertIn('query_place_id=',url)

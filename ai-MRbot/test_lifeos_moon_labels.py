import unittest
from unittest.mock import Mock
import lifeos_moon_labels as m
class LabelImportTests(unittest.TestCase):
 def fixture(self):
  c=Mock();c.config.return_value=({},m.CALENDAR,'owner');c.event_labels.return_value=[{'name':x,'id':x} for x in ('美容美體','新客','講座','均均休假')]
  events={t['id']:{'summary':t['title'],'description':'TimeTree UID: source','etag':'version','extendedProperties':{'private':{'lifeos_created_by':'original'}}} for t in m.TARGETS}
  def call(method,path,**kw):
   event=events[path[1:]]
   if method=='PATCH':event.update(kw['body'])
   return event
  c.call.side_effect=call
  c.actor_metadata.side_effect=lambda e,u:{'private':{**e['extendedProperties']['private'],'lifeos_modified_by':u}}
  return c,events
 def test_exact_labels_preserve_creator_and_never_reset_later_changes(self):
  c,events=self.fixture();m.run(c,Mock())
  self.assertEqual(sum(x.args[0]=='PATCH' for x in c.call.call_args_list),len(m.TARGETS))
  for t in m.TARGETS:
   self.assertEqual(events[t['id']]['eventLabelId'],t['label'])
   self.assertEqual(events[t['id']]['extendedProperties']['private']['lifeos_created_by'],'original')
  c.call.reset_mock();events[m.TARGETS[0]['id']]['eventLabelId']='user later choice';m.run(c,Mock())
  self.assertFalse(any(x.args[0]=='PATCH' for x in c.call.call_args_list))
 def test_wrong_calendar_no_writes(self):
  c,_=self.fixture();c.config.return_value=({},'other','owner');m.run(c,Mock());c.call.assert_not_called()
 def test_renamed_event_not_overwritten(self):
  c,events=self.fixture();events[m.TARGETS[0]['id']]['summary']='changed';m.run(c,Mock())
  self.assertEqual(sum(x.args[0]=='PATCH' for x in c.call.call_args_list),len(m.TARGETS)-1)

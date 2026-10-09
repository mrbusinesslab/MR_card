import os
import unittest
from unittest.mock import patch
import lifeos_calendar as c

OWNER='U'+'1'*32
MEMBER='U'+'2'*32

class SharedCalendarTests(unittest.TestCase):
    def test_only_enrolled_member_of_owner_can_access(self):
        with patch.dict(os.environ,{'LIFEOS_GOOGLE_USER_ID':OWNER}):
            for user,allowed in [({'shared_owner':OWNER},True),({'shared_owner':'other'},False),(None,False)]:
                with patch('lifeos.gateway',return_value={'user':user}):
                    self.assertEqual(c.calendar_access(MEMBER),allowed)

    def test_creator_and_existing_metadata_survive_edit(self):
        event={'extendedProperties':{'private':{'lifeos_created_by':OWNER,'lifeos_category':'美容'},'shared':{'other':'value'}}}
        result=c.actor_metadata(event,MEMBER)
        self.assertEqual(result['private']['lifeos_created_by'],OWNER)
        self.assertEqual(result['private']['lifeos_modified_by'],MEMBER)
        self.assertEqual(result['private']['lifeos_category'],'美容')
        self.assertEqual(result['shared'],{'other':'value'})
        self.assertNotIn('lifeos_modified_by',event['extendedProperties']['private'])

    def test_create_records_actual_line_member(self):
        self.assertEqual(c.actor_metadata({},MEMBER,creating=True)['private'],{'lifeos_created_by':MEMBER,'lifeos_modified_by':MEMBER})

    def test_private_calendar_filters_other_member(self):
        with patch.dict(os.environ,{'LIFEOS_GOOGLE_CALENDAR_ID':'cal'}),patch('lifeos.gateway',side_effect=[{'user':{'calendar_shared':False}},{'events':[{'event_id':'mine','calendar_id':'cal'}]}]):
            self.assertEqual(c.visible_events(MEMBER,[{'id':'mine'},{'id':'other'},{'id':'unknown'}]),[{'id':'mine'}])

if __name__=='__main__': unittest.main()

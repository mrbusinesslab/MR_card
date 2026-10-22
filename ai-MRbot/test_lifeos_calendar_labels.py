import unittest
from unittest.mock import patch
import lifeos_calendar as calendar


class CalendarLabelTests(unittest.TestCase):
    def test_fresh_calendar_uses_its_own_blue_and_purple_labels(self):
        labels=[{'id':'new-blue','backgroundColor':'#039be5'},
                {'id':'new-purple','backgroundColor':'#8e24aa'}]
        with patch.object(calendar,'event_labels',return_value=labels):
            self.assertEqual(calendar.apply_label({'colorId':'1'},'美容'),{'eventLabelId':'new-blue'})
            self.assertEqual(calendar.apply_label({},'新客'),{'eventLabelId':'new-purple'})

    def test_existing_named_label_takes_precedence(self):
        labels=[{'id':'default-blue','backgroundColor':'#039be5'},
                {'id':'custom-blue','name':'美容美體','backgroundColor':'#123456'}]
        with patch.object(calendar,'event_labels',return_value=labels):
            self.assertEqual(calendar.apply_label({},'美容'),{'eventLabelId':'custom-blue'})

    def test_missing_matching_label_preserves_event_payload(self):
        payload={'summary':'test','colorId':'1'}
        with patch.object(calendar,'event_labels',return_value=[]):
            self.assertEqual(calendar.apply_label(payload,'美容'),payload)

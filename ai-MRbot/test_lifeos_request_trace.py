import unittest
from unittest.mock import Mock
from lifeos_request_trace import RequestTrace


class TraceTests(unittest.TestCase):
    def test_slow_report_identifies_location_without_local_secret(self):
        logger = Mock()
        secret = 'secret-must-not-be-logged'
        trace = RequestTrace(logger)
        trace.mark('calendar_handle')
        trace.report_slow()
        args = logger.error.call_args.args
        self.assertEqual(args[2], 'calendar_handle')
        self.assertIn('test_slow_report', args[3])
        self.assertNotIn(secret, str(logger.mock_calls))

    def test_completed_request_cancels_diagnostic(self):
        logger = Mock()
        with RequestTrace(logger, delay=60) as trace:
            trace.mark('line_reply_done')
        trace.report_slow()
        logger.error.assert_not_called()
        self.assertEqual(trace.stage, 'finished')

    def test_exception_is_not_swallowed(self):
        logger = Mock()
        with self.assertRaises(ValueError):
            with RequestTrace(logger, delay=60) as trace:
                raise ValueError('test')
        self.assertTrue(trace.done.is_set())
        self.assertEqual(trace.stage, 'failed')

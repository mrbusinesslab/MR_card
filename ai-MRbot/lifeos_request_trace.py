"""Bounded webhook diagnostics, without message text or authentication data."""
import sys
import threading
import time
import traceback
import uuid


class RequestTrace:
    def __init__(self, logger, delay=20):
        self.logger = logger
        self.id = uuid.uuid4().hex[:12]
        self.started = time.monotonic()
        self.thread_id = threading.get_ident()
        self.stage = 'received'
        self.done = threading.Event()
        self.timer = threading.Timer(delay, self.report_slow)
        self.timer.daemon = True

    def mark(self, stage):
        self.stage = stage
        self.logger.warning('LINE trace=%s stage=%s elapsed=%.3f',
                            self.id, stage, time.monotonic() - self.started)

    def report_slow(self):
        if self.done.is_set():
            return
        frame = sys._current_frames().get(self.thread_id)
        # Stack locations only: never source lines, arguments, or local values.
        locations = [] if frame is None else [
            '%s:%s:%s' % (item.filename, item.lineno, item.name)
            for item in traceback.extract_stack(frame)]
        self.logger.error('LINE trace=%s slow stage=%s stack=%s',
                          self.id, self.stage, ' > '.join(locations))

    def __enter__(self):
        self.mark('received')
        self.timer.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.done.set()
        self.timer.cancel()
        self.mark('failed' if exc_type else 'finished')

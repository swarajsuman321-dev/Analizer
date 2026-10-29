"""A missed acceptance deadline remains failed after safe worker cleanup."""
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import patch
import zlib

from app_release_acceptance import acceptance_worker_events, wait_for_acceptance_workers


class AcceptanceWorkerDeadlineTests(unittest.TestCase):
    def test_worker_polling_delivers_gui_events_and_explicitly_yields_python(self):
        calls = []
        app = SimpleNamespace(processEvents=lambda: calls.append('events'))
        with patch('app_release_acceptance.time.sleep', side_effect=lambda duration: calls.append(duration)):
            acceptance_worker_events(app)
        self.assertEqual(calls, ['events', .025, 'events'])

    def test_real_python_worker_and_queued_gui_completion_without_qtest_wait(self):
        from PySide6 import QtCore, QtWidgets, QtTest
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        class Results(QtCore.QObject):
            finished = QtCore.Signal(bytes)
            def __init__(self):
                super().__init__()
                self.busy = True
                self.workers = {'writer'}
                self.payload = None
                self.finished.connect(self.complete, QtCore.Qt.ConnectionType.QueuedConnection)
            @QtCore.Slot(bytes)
            def complete(self, payload):
                self.payload = payload
                self.busy = False
                self.workers.clear()
            def cancel_operation(self):
                raise AssertionError('A small worker unexpectedly exceeded its deadline')
        result = Results()
        payload = b'Actual compression worker and queued Qt delivery.\n'*2048
        worker = threading.Thread(target=lambda: result.finished.emit(zlib.compress(payload)))
        worker.start()
        try:
            # Keep QTest available for interactive acceptance scenarios, but
            # never use its GIL-holding polling to await this Python worker.
            with patch.object(QtTest.QTest, 'qWait', side_effect=AssertionError('QTest wait used during worker')):
                wait_for_acceptance_workers(result, lambda: acceptance_worker_events(app), timeout=10)
            self.assertFalse(result.busy)
            self.assertEqual(zlib.decompress(result.payload), payload)
        finally:
            worker.join(timeout=2)

    def run_wait(self, *, finish_after=None, cancel_finishes=True):
        clock = [0.]
        cancelled = []
        window = SimpleNamespace(busy=True, workers={'worker'})
        def cancel():
            cancelled.append(True)
        window.cancel_operation = cancel
        def events():
            clock[0] += 1
            if ((finish_after is not None and clock[0] >= finish_after)
                    or (cancelled and cancel_finishes)):
                window.busy = False
                window.workers.clear()
        return clock, cancelled, window, events

    def test_successful_queued_completion_does_not_request_cancellation(self):
        clock, cancelled, window, events = self.run_wait(finish_after=2)
        with patch('app_release_acceptance.time.monotonic', side_effect=lambda: clock[0]):
            wait_for_acceptance_workers(window, events, timeout=3, cancel_timeout=2)
        self.assertFalse(window.busy)
        self.assertEqual(cancelled, [])

    def test_deadline_failure_is_preserved_when_cancellation_completes(self):
        clock, cancelled, window, events = self.run_wait()
        with patch('app_release_acceptance.time.monotonic', side_effect=lambda: clock[0]):
            with self.assertRaisesRegex(AssertionError, 'six minutes; cancellation completed'):
                wait_for_acceptance_workers(window, events, timeout=3, cancel_timeout=2)
        self.assertEqual(cancelled, [True])
        self.assertFalse(window.busy)
        self.assertFalse(window.workers)

    def test_uncooperative_worker_cleanup_has_its_own_finite_bound(self):
        clock, cancelled, window, events = self.run_wait(cancel_finishes=False)
        with patch('app_release_acceptance.time.monotonic', side_effect=lambda: clock[0]):
            with self.assertRaisesRegex(AssertionError, 'cancellation is still pending'):
                wait_for_acceptance_workers(window, events, timeout=3, cancel_timeout=2)
        self.assertEqual(cancelled, [True])
        self.assertEqual(clock[0], 5.)
        self.assertTrue(window.busy)


if __name__ == '__main__':
    unittest.main()

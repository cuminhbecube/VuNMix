"""Bounded resource telemetry: no Windows hardware required."""
import pathlib
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from resource_monitor import ProcessResourceTracker


class _FakeProcess:
    def __init__(self):
        self.rss = 64 * 1024 * 1024
        self.handles = 40

    def memory_info(self):
        return SimpleNamespace(rss=self.rss, private=self.rss - 1024 * 1024)

    def num_threads(self):
        return 7

    def num_handles(self):
        return self.handles


class ProcessMemoryRegressionTests(unittest.TestCase):
    def test_sample_has_private_memory_handles_and_bounded_history(self):
        process = _FakeProcess()
        tracker = ProcessResourceTracker(process, capacity=4)
        for tick in range(50):
            process.rss = (64 + tick) * 1024 * 1024
            tracker.capture(tick * 300)
        self.assertEqual(len(tracker.samples), 4)
        sample = tracker.samples[-1]
        self.assertEqual(sample.threads, 7)
        self.assertEqual(sample.handles, 40)
        self.assertIn("private=", tracker.format(sample))
        self.assertIn("handles=40", tracker.format(sample))

    def test_hour_long_consistent_growth_is_reported(self):
        process = _FakeProcess()
        tracker = ProcessResourceTracker(process, capacity=10)
        for tick in range(8):
            process.rss = (70 + tick * 24) * 1024 * 1024
            tracker.capture(tick * 600)
        self.assertTrue(tracker.suspected_growth())

    def test_short_burst_or_recovered_cache_is_not_leak(self):
        process = _FakeProcess()
        tracker = ProcessResourceTracker(process)
        for tick, mib in enumerate((60, 100, 180, 65, 66, 64)):
            process.rss = mib * 1024 * 1024
            tracker.capture(tick * 600)
        self.assertFalse(tracker.suspected_growth())


if __name__ == "__main__":
    unittest.main()

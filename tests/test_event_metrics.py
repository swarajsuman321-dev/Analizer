"""Regression tests for generic event analysis."""
import unittest
from app_event_metrics import analyse_binary, simultaneous_on


class TestEvents(unittest.TestCase):
    def test_transitions_and_censoring(self):
        r=analyse_binary([0,1,2,3],[0,1,1,0],max_gap_s=2)
        self.assertEqual((r['observed_on_edges'],r['observed_off_edges']),(1,1))
        self.assertEqual(r['on_duration_s'],2)
        self.assertEqual(r['episodes'][0]['start_s'],1)

    def test_gaps_are_not_off(self):
        r=analyse_binary([0,1,20,21],[1,1,1,0],max_gap_s=2)
        self.assertEqual(r['known_duration_s'],2)
        self.assertEqual(r['observed_on_edges'],0)
        self.assertTrue(r['episodes'][0]['right_censored'])

    def test_overlap(self):
        r=simultaneous_on([0,1,3,4],[0,1,1,0],[0,2,4],[1,1,0],max_gap_s=3)
        self.assertEqual(r['common_known_s'],4)
        self.assertEqual(r['simultaneous_on_s'],3)

    def test_unknown(self):
        r=analyse_binary([0,1,2],[1,None,1],max_gap_s=2)
        self.assertEqual(r['known_duration_s'],0)
        self.assertIsNone(r['duty_fraction'])


if __name__=='__main__':
    unittest.main()

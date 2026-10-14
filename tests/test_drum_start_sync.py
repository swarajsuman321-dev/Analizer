"""First observed drum start / first power-rise alignment, without GUI or real data."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from app_data import DataEngine, DataReadError, DRUM_SYNC_STRATEGY, BUILTIN_SYNC_STRATEGIES


class DrumStartSyncTests(unittest.TestCase):
    def frames(self):
        power = pd.DataFrame({'time':range(6),'P-E1':[2,3,2,53,53,2]})
        machine = pd.DataFrame({'timestamp':pd.date_range('2026-10-03 10:25:56',periods=6,freq='s'),
                                'Drump speed feedback':[6,0,0,23,30,0],
                                'Drump Speed':[0,30,30,30,30,0]})
        return power, machine

    def engine(self, power, machine, strategy=DRUM_SYNC_STRATEGY):
        with patch('app_data.smart_read_file',side_effect=[power.copy(deep=True),machine.copy(deep=True)]):
            return DataEngine('power.csv','machine.csv',strategy)

    def test_feedback_start_and_power_rise_align_despite_different_clock_origins(self):
        power, machine = self.frames()
        engine = self.engine(power,machine)
        report = engine.sync_report
        self.assertEqual(report['drum_speed_column'],'Drump speed feedback')
        self.assertTrue(report['drum_uses_feedback'])
        self.assertEqual(report['drum_event_elapsed_seconds'],3)
        self.assertEqual(report['power_event_elapsed_seconds'],3)
        self.assertEqual(report['drum_event_timestamp'],report['power_event_timestamp_aligned'])
        self.assertEqual(report['power_start_relative_to_machine_seconds'],0)
        aligned = engine.get_data()
        np.testing.assert_array_equal(aligned['P-E1'],power['P-E1'])
        np.testing.assert_array_equal(aligned['Drump speed feedback'],machine['Drump speed feedback'])
        np.testing.assert_allclose(aligned['datetime'].diff().dt.total_seconds().iloc[1:],1)
        self.assertNotIn('datetime',power)
        self.assertNotIn('datetime',machine)

    def test_noise_reverse_rotation_and_one_sample_spikes(self):
        times = pd.date_range('2026-01-01',periods=8,freq='s')
        result = DataEngine._first_sustained_rise(times,pd.Series([6,0,25,0,0,23,30,0]).abs(),10)
        self.assertEqual(result,5)
        result = DataEngine._first_sustained_rise(times,pd.Series([6,0,-25,0,0,-23,-30,0]).abs(),10)
        self.assertEqual(result,5)

    def test_first_power_pulse_is_rejected_when_it_does_not_persist(self):
        power, machine = self.frames()
        power = pd.DataFrame({'time':range(9),'P-E1':[2,3,2,60,2,3,4,53,52]})
        engine = self.engine(power,machine)
        self.assertEqual(engine.sync_report['power_event_elapsed_seconds'],7)
        self.assertEqual(engine.sync_report['power_start_relative_to_machine_seconds'],-4)

    def test_unknown_samples_and_large_gaps_do_not_confirm_an_event(self):
        times = pd.date_range('2026-01-01',periods=6,freq='s')
        self.assertIsNone(DataEngine._first_sustained_rise(times,[0,0,25,np.nan,25,25],10))
        times = pd.Timestamp('2026-01-01')+pd.to_timedelta([0,1,2,102],unit='s')
        self.assertIsNone(DataEngine._first_sustained_rise(times,[0,0,25,25],10))
        times = pd.date_range('2026-01-01',periods=8,freq='s')
        self.assertEqual(DataEngine._first_sustained_rise(times,[0,0,25,np.nan,0,0,25,25],10),6)

    def test_missing_feedback_is_not_replaced_by_command(self):
        power, machine = self.frames()
        machine['Drump speed feedback'] = np.nan
        with self.assertRaisesRegex(DataReadError,'No reliable first drum start'):
            self.engine(power,machine)

    def test_motor_speed_is_excluded_and_command_fallback_is_disclosed(self):
        power, machine = self.frames()
        machine = machine.drop(columns='Drump speed feedback')
        machine['Drump Speed'] = [0,0,0,30,30,0]
        machine['Motor speed feedback'] = [0,5000,5000,5000,5000,0]
        engine = self.engine(power,machine)
        self.assertFalse(engine.sync_report['drum_uses_feedback'])
        self.assertEqual(engine.sync_report['drum_speed_column'],'Drump Speed')
        self.assertTrue(any('commanded speed' in warning for warning in engine.warnings))
        machine = machine.drop(columns='Drump Speed')
        with self.assertRaisesRegex(DataReadError,'needs a drum speed/feedback channel'):
            self.engine(power,machine)

    def test_no_rotation_and_no_power_rise_report_a_clear_failure(self):
        power, machine = self.frames()
        machine['Drump speed feedback'] = 6
        with self.assertRaisesRegex(DataReadError,'No reliable first drum start'):
            self.engine(power,machine)
        power, machine = self.frames()
        power['P-E1'] = [2,3,2,4,3,2]
        with self.assertRaisesRegex(DataReadError,'No reliable first power rise'):
            self.engine(power,machine)

    def test_unknown_and_unstable_initial_power_baselines_are_rejected(self):
        power, machine = self.frames()
        power.loc[1,'P-E1'] = np.nan
        with self.assertRaisesRegex(DataReadError,'initial known standby power samples'):
            self.engine(power,machine)
        power, machine = self.frames()
        power['P-E1'] = [2,50,51,100,100,2]
        with self.assertRaisesRegex(DataReadError,'standby baseline is unavailable'):
            self.engine(power,machine)

    def test_explicit_kw_and_rps_are_used_only_for_event_detection(self):
        power, machine = self.frames()
        power['P-E1'] /= 1000
        power.attrs['column_units'] = {'P-E1':'kW'}
        machine['Drump speed feedback'] /= 60
        machine.attrs['column_units'] = {'Drump speed feedback':'rps'}
        engine = self.engine(power,machine)
        self.assertEqual(engine.sync_report['power_baseline_W'],2)
        self.assertEqual(engine.sync_report['drum_event_elapsed_seconds'],3)
        np.testing.assert_allclose(engine.get_data()['P-E1'],power['P-E1'])
        np.testing.assert_allclose(engine.get_data()['Drump speed feedback'],machine['Drump speed feedback'])

    def test_raw_timestamp_mode_does_not_implicitly_select_event_alignment(self):
        power, machine = self.frames()
        with self.assertRaisesRegex(DataReadError,'do not overlap'):
            self.engine(power,machine,'Raw Timestamps (No Shift)')

    def test_existing_heater_sync_still_works(self):
        power, machine = self.frames()
        power['P-E1'] = [2,3,2,1700,1700,2]
        machine['Heat Valve'] = [0,0,0,128,128,0]
        engine = self.engine(power,machine,'Intelligent (Heater ON to >1.5kW Spike)')
        self.assertEqual(len(engine.get_data()),6)
        self.assertNotIn('event_alignment',engine.sync_report)



if __name__=='__main__':
    unittest.main()

"""Regression tests for CSV comparison; no GUI display is required."""
import logging
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from app_data import DataReadError, convert_signal_units
from app_simulation import SimulationCsvAdapter, CSV_LEGEND_SPECS, specs_for_curves, display_samples
from app_comparator import ComparisonEngine, SIMULATION_LEGEND_SPECS
from app_inspection import prepare_trace, sample_trace, comparison_traces


def fixture():
    return pd.DataFrame({
        'time': [0, 1, 1, 1, 2, 3], 'drum_speed': [0, -1200, 1100, 1000, 1000, 0],
        'water_volume': [0, 3, 3, 3, 1, 0], 'water_pressure': [0, 500, 400, 300, 100, 0],
        'water_temp': [15, 20, 31, 25, 22, 20], 'water_amount': [0, 3, 3, 3, 3, 3],
        'process_state': [0, 3, 11, 26, 49, 0], 'stwf_number': [0, 41, 159, 2907, 73, 0],
        'vt_line': [0, 2, 10, 50, 51, 0], 'pre_wash_valve_open': ['false','false','true','false','false','false'],
        'main_wash_valve_open': [0,0,0,0,0,0], 'drain_open': [0,0,1,0,1,0],
        'drain_process_active': [0,0,0,0,1,0], 'heater_power': [0,1000,2000,1000,0,0],
        'remainTime': [3,2,2,2,1,0], 'displayRemainTime': [3,2,2,2,1,0], 'cp_active': [0,1,0,0,0,0]})


class CsvTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'renamed.csv'
        fixture().to_csv(self.path, sep=';', index=False)
        self.run = SimulationCsvAdapter(self.path, pressure_unit='Pa')

    def tearDown(self):
        plt.close('all')
        self.temp.cleanup()

    def test_minutes_duplicates_codes_and_boolean_words(self):
        self.assertEqual(len(self.run.frame), 6)
        self.assertEqual(self.run.duration_min, 3)
        self.assertEqual(self.run.curves['stwf_number']['value'].max(), 2907)
        self.assertEqual(self.run.frame['process_state'].max(), 49)
        self.assertEqual(self.run.curves['pre_wash_valve_open']['value'].tolist(), [0,0,1,0,0,0])
        self.assertEqual([s['key'] for s in specs_for_curves(self.run.curves)], [s['key'] for s in CSV_LEGEND_SPECS])

    def test_pressure_and_heater_units(self):
        self.assertEqual(self.run.curves['pressure']['value'].max(), 500)
        self.assertEqual(self.run.curves['heater_power']['value'].max(), 2000)
        self.assertEqual(self.run.curves['actual_remaining_time']['value'].tolist(), [3,2,2,2,1,0])

    def test_unit_overrides(self):
        data = fixture()
        data['time'] *= 60
        data['remainTime'] *= 60
        data['displayRemainTime'] *= 60
        data['water_pressure'] /= 100
        data.to_csv(self.path, sep=';', index=False)
        run = SimulationCsvAdapter(self.path, time_unit='s', pressure_unit='mbar', remaining_time_unit='s')
        self.assertEqual(run.duration_min, 3)
        self.assertEqual(run.curves['pressure']['value'].max(), 500)
        self.assertEqual(run.curves['actual_remaining_time']['value'].max(), 3)

    def test_explicit_unit_metadata_wins(self):
        data = fixture()
        data['time'] *= 60
        data.attrs['column_units'] = {'time': 's', 'water_pressure': 'mbar'}
        with patch('app_simulation.smart_read_file', return_value=data):
            run = SimulationCsvAdapter(self.path)
        self.assertEqual(run.duration_min, 3)
        self.assertEqual(run.curves['pressure']['value'].max(), 50000)

    def test_exact_requested_profile(self):
        expected = ['temperature','pressure','pre_wash_valve_open','wash_valve_open',
                    'water','stwf_number','drain_open','actual_remaining_time','drum_speed','heater_power']
        self.assertEqual(list(self.run.curves), expected)
        self.assertEqual(self.run.curves['water']['value'].tolist(),[0,3,3,3,3,3])
        self.assertEqual(self.run.curves['water'].attrs['source_column'],'water_amount')
        self.assertEqual([s['key'] for s in specs_for_curves(self.run.curves)], expected)
        fig, axes, _, error = ComparisonEngine.render_comparison_figure(self.run.frame, self.run.curves)
        self.assertIsNone(error)
        self.assertEqual(len(axes), 10)
        fig.canvas.draw()

    def test_unconfirmed_pressure_keeps_raw_and_has_no_bench_match(self):
        run = SimulationCsvAdapter(self.path,pressure_unit='unknown')
        self.assertEqual(run.curves['pressure']['value'].max(), 500)
        self.assertEqual(run.curves['pressure'].attrs['unit'], 'unknown')
        self.assertFalse(run.curves['pressure'].attrs['y_calibration_verified'])
        specs = specs_for_curves(run.curves)
        self.assertIsNone(ComparisonEngine.find_bench_columns(self.run.frame, specs)['pressure'])
        fig, axes, _, error = ComparisonEngine.render_comparison_figure(self.run.frame, run.curves)
        self.assertIsNone(error)
        self.assertEqual(axes[1].lines[0].get_ydata().max(), 500)
        self.assertEqual(len(axes[1].lines), 1)
        empty = pd.DataFrame({'time_min': []})
        self.assertIsNone(ComparisonEngine.find_bench_columns(empty, specs)['actual_remaining_time'])

    def test_actual_countdown_ignores_both_estimates_for_sim_and_bench(self):
        data = fixture()
        data['time'] += 12
        data['remainTime'] = 999
        data['displayRemainTime'] = 888
        data.to_csv(self.path, index=False)
        run = SimulationCsvAdapter(self.path)
        self.assertEqual(run.curves['actual_remaining_time']['value'].tolist(), [3,2,2,2,1,0])
        bench = pd.DataFrame({'time_min': [4,5,8], 'wash left time': [999,777,123]})
        specs = specs_for_curves(run.curves)
        cols = ComparisonEngine.find_bench_columns(bench, specs)
        self.assertEqual(cols['actual_remaining_time'], 'time_min')
        traces = comparison_traces(bench,run.curves,cols,specs)
        self.assertEqual(sample_trace(traces['actual_remaining_time']['bench'],5), 3)
        self.assertEqual(sample_trace(traces['actual_remaining_time']['bench'],8), 0)
        fig,axes,_,error = ComparisonEngine.render_comparison_figure(bench,run.curves)
        self.assertIsNone(error)
        np.testing.assert_array_equal(axes[7].lines[1].get_ydata(), [4,3,0])

    def test_confirmed_pressure_equivalent_sources(self):
        for unit, maximum in [('Pa', 500), ('kPa', .5), ('mbar',5), ('bar',.005)]:
            data = fixture(); data['water_pressure'] *= maximum / 500
            data.to_csv(self.path,index=False)
            run = SimulationCsvAdapter(self.path,pressure_unit=unit)
            self.assertAlmostEqual(run.curves['pressure']['value'].max(),500)
            specs=specs_for_curves(run.curves)
            bench=pd.DataFrame({'time_min':[0,3], 'water pressure [Pa]':[0,500]})
            cols=ComparisonEngine.find_bench_columns(bench,specs)
            traces=comparison_traces(bench,run.curves,cols,specs)
            self.assertEqual(sample_trace(traces['pressure']['bench'],3),500)

    def test_invalid_or_restarted_time_is_rejected(self):
        for time in ([0,1,np.nan,1,2,3], [0,1,0,1,2,3]):
            data = fixture(); data['time'] = time
            data.to_csv(self.path, index=False)
            with self.assertRaises(DataReadError):
                SimulationCsvAdapter(self.path)

    def test_optional_signals_do_not_block(self):
        data = fixture()[['time','drum_speed','water_volume','process_state']]
        data.to_csv(self.path, index=False)
        run = SimulationCsvAdapter(self.path)
        card = ComparisonEngine.generate_scorecard(run.frame, run.curves)
        self.assertEqual(card.iloc[0]['status'], 'GREEN')
        self.assertNotIn('drain_open', run.curves)

    def test_metrics_retain_duplicate_extrema_and_pulses(self):
        card = ComparisonEngine.generate_scorecard(self.run.frame, self.run.curves).set_index('parameter')
        self.assertEqual(card.loc['Peak Spin Extraction Speed','sim_val'], '1200.00 RPM')
        self.assertEqual(card.loc['Peak Spin Extraction Speed','raw_val'], '1200.00 RPM')
        self.assertEqual(card.loc['Water Intake Bursts','sim_val'], '1 activations')
        self.assertEqual(card.loc['Water Intake Bursts','raw_val'], '1 activations')
        self.assertEqual(card.loc['Drain Pump Evacuations','sim_val'], '2 activations')
        self.assertEqual(card.loc['Peak Water Temperature','sim_val'], '31.00 °C')
        self.assertEqual(card.loc['Total Heating Active Duration','sim_val'], '1.00 min')
        self.assertEqual(card.loc['Total Cycle Duration','status'], 'GREEN')
        self.assertEqual(len(self.run.curves['drain_open']), 6)

    def test_bench_unit_conversion_and_matching(self):
        bench = pd.DataFrame({'time_min':[0,1], 'water pressure [Pa]':[0,500],
                              'water temperature [°C]':[15,30], 'drain_open':[False,True],
                              'wash stage':[1,3], 'displayRemainTime':[3,2]})
        cols = ComparisonEngine.find_bench_columns(bench, CSV_LEGEND_SPECS)
        self.assertIsNone(cols['stwf_number'])
        self.assertEqual(cols['actual_remaining_time'], 'time_min')
        self.assertNotIn('display_remaining_time', cols)
        self.assertEqual(cols['drain_open'], 'drain_open')
        self.assertEqual(ComparisonEngine._bench_values(bench,'pressure',cols['pressure'],CSV_LEGEND_SPECS).tolist(), [0,500])

    def test_cursor_codes_are_steps_and_equal_time_uses_last(self):
        trace = prepare_trace(self.run.frame['time_min'], self.run.frame['stwf_number'], 'code')
        self.assertEqual(sample_trace(trace,1),2907)
        self.assertEqual(sample_trace(trace,1.5),2907)
        self.assertTrue(np.isnan(sample_trace(trace,4)))
        specs = specs_for_curves(self.run.curves)
        cols = ComparisonEngine.find_bench_columns(self.run.frame, specs)
        traces = comparison_traces(self.run.frame,self.run.curves,cols,specs)
        self.assertEqual(sample_trace(traces['pressure']['bench'],1),300)

    def test_plot_reduction_keeps_peaks_gaps_and_edges(self):
        t=np.arange(50000,dtype=float); y=np.zeros(50000); y[24789]=999; y[32456]=np.nan
        tx,vy=display_samples(t,y,'analog',1000)
        self.assertIn(999,vy); self.assertTrue(np.isnan(vy).any()); self.assertLess(len(tx),1100)
        t=np.array([0,1,1,1,2],float); y=np.array([0,0,1,0,0],float)
        tx,vy=display_samples(t,y,'digital')
        self.assertIn(1,vy); self.assertEqual(tx[np.argmax(vy)],1)

    def test_render_code_scale_and_visibility(self):
        visible={spec['key']:{'sim':False,'bench':False} for spec in CSV_LEGEND_SPECS}
        visible['stwf_number']={'sim':True,'bench':True}
        fig,axes,_,error=ComparisonEngine.render_comparison_figure(self.run.frame,self.run.curves,visible)
        self.assertIsNone(error); self.assertEqual(len(axes),1)
        self.assertGreater(axes[0].get_ylim()[1],2907)
        self.assertEqual(len(axes[0].lines),2)
        fig.canvas.draw()

    def test_image_specs_and_uncalibrated_scorecard_still_work(self):
        curves={'drum_speed':pd.DataFrame({'time_min':[0,1,2], 'value':[0,1000,0]})}
        self.assertIs(specs_for_curves(curves), SIMULATION_LEGEND_SPECS)
        card=ComparisonEngine.generate_scorecard(self.run.frame,curves)
        self.assertEqual(card.iloc[0]['status'],'REVIEW')
        self.assertIn('image pixels',card.attrs['assumptions'][0])

    def test_service_csv_preserves_original_rows(self):
        from app_analysis_service import compare_recordings
        store,score=compare_recordings(str(self.path),str(self.path))
        self.assertEqual(len(store.datasets),2)
        self.assertTrue(all(len(ds.frame)==6 for ds in store.datasets.values()))
        pressure=score.set_index('parameter').loc['Peak Water Pressure']
        self.assertEqual(pressure['sim_val'],'500.00 Pa')
        self.assertEqual(pressure['raw_val'],'500.00 Pa')


if __name__ == '__main__':
    unittest.main()

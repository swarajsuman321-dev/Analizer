"""Confirmed logger schema, variable timing and display-band regressions."""
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from openpyxl import load_workbook

from app_comparator import ComparisonEngine as C
from app_data import normalize_control_series, infer_pressure_units
from app_simulation import CSV_LEGEND_SPECS, SimulationCsvAdapter, specs_for_curves
from app_inspection import comparison_traces, sample_trace
from test_csv_comparison import fixture
from app_support import write_excel_frame


def curve(times, values, unit='min'):
    result = pd.DataFrame({'time_min':times,'value':values})
    result.attrs.update(source_type='csv',unit=unit,x_calibration_verified=True,y_calibration_verified=True)
    return result


class ConfirmedBenchRules(unittest.TestCase):
    def test_colour_boundaries_and_negative_differences(self):
        for value, expected in [(0,'GREEN'),(9.999,'GREEN'),(10,'YELLOW'),(20,'YELLOW'),
                                (20.001,'RED'),(-9,'GREEN'),(-10,'YELLOW'),(-20,'YELLOW'),(-21,'RED')]:
            self.assertEqual(C.difference_band(value),expected)
        self.assertEqual(C.difference_band(np.nan),'VALUE')

    def test_variable_cadence_retains_spin_and_heating_time(self):
        seconds = np.r_[np.arange(0,40,.1),np.arange(40,121,1.)]
        times = seconds / 60
        speed = np.where(seconds >= 40,1200,0)
        self.assertAlmostEqual(C._last_sustained_threshold_entry(times,speed,600),40/60)
        states = ((seconds >= 10)&(seconds < 30)).astype(float)
        self.assertAlmostEqual(C._active_duration_minutes(times,states),20/60)

    def test_outages_and_unknown_heater_samples_remain_unavailable(self):
        seconds = np.r_[np.arange(0,60,1.),np.arange(90,120,1.)]
        times = seconds/60
        self.assertTrue(np.isnan(C._active_duration_minutes(times,np.ones(len(times)))))
        self.assertTrue(np.isnan(C._last_sustained_threshold_entry([0,.01,.02,2.],[1200]*4,600)))
        self.assertTrue(np.isnan(C._active_duration_minutes([0,1,2],[0,np.nan,0])))

    def test_positive_integer_states_and_invalid_numeric_values(self):
        states = normalize_control_series(pd.Series([0,1,2,128,255,1.0,.5,-1,np.nan,'OFF','ON','true','false']),'Heat Valve')
        self.assertEqual(states.iloc[:6].tolist(),[0,1,1,1,1,1])
        self.assertTrue(states.iloc[[6,8]].isna().all());self.assertEqual(states.iloc[7],1)
        self.assertEqual(states.iloc[9:].tolist(),[0,1,1,0])

    def test_feedback_wins_and_missing_feedback_does_not_use_command(self):
        frame = pd.DataFrame({'time_min':[0,1], 'Motor speed feedback':[0,5000],
                              'Drump Speed':[0,1200], 'Drump speed feedback':[0,1100]})
        self.assertEqual(C.find_bench_columns(frame,CSV_LEGEND_SPECS)['drum_speed'],'Drump speed feedback')
        frame['Drump speed feedback'] = np.nan
        self.assertEqual(C.find_bench_columns(frame,CSV_LEGEND_SPECS)['drum_speed'],'Drump speed feedback')

    def test_paired_mbar_and_raw_sensor_channels_remain_distinct(self):
        frame = pd.DataFrame({'time_min':[0,1], 'Water Pressure':[1606,1729],
                              'water  pressure':[47,992], 'Water pressure Dst':[0,863]})
        C.apply_pressure_default(frame)
        units = infer_pressure_units(frame)
        self.assertEqual(units['Water Pressure'],'µs')
        self.assertEqual(units['water  pressure'],'mbar')
        self.assertEqual(C.find_bench_columns(frame,CSV_LEGEND_SPECS)['pressure'],'water  pressure')
        self.assertEqual(C._bench_values(frame,'pressure','water  pressure',CSV_LEGEND_SPECS).tolist(),[4700,99200])

    def test_original_pressure_mode_keeps_numbers_despite_source_and_display_units(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'run.csv'
            fixture().to_csv(path,index=False)
            for unit in ('unknown','Pa','mbar','kPa','bar'):
                frame = fixture()
                frame.attrs['column_units'] = {'water_pressure':unit}
                with patch('app_simulation.smart_read_file',return_value=frame):
                    adapter = SimulationCsvAdapter(path,pressure_unit=unit,
                                                   pressure_display_unit='mbar',preserve_pressure_numbers=True)
                pressure = adapter.curves['pressure']
                self.assertEqual(pressure['value'].tolist(),fixture()['water_pressure'].tolist())
                self.assertEqual(pressure.attrs['unit'],'Pa')
                self.assertEqual(pressure.attrs['source_unit'],unit)
                self.assertTrue(specs_for_curves(adapter.curves)[1]['preserve_pressure_numbers'])
                self.assertIn('unchanged',adapter.analysis_info()['unit_policy'])

    def test_original_pressure_comparison_cursor_chart_and_export(self):
        simulation = curve([0,1],[0,863],'Pa')
        simulation.attrs.update(preserve_pressure_numbers=True,source_unit='unknown')
        curves = {'pressure':simulation}
        specs = specs_for_curves(curves)
        bench = pd.DataFrame({'time_min':[0,1], 'Water Pressure':[1606,1729],
                              'water  pressure':[47,992], 'Water pressure Dst':[0,863]})
        C.apply_pressure_default(bench,'Pa')
        columns = C.find_bench_columns(bench,specs)
        self.assertEqual(columns['pressure'],'water  pressure')
        self.assertEqual(C._bench_values(bench,'pressure',columns['pressure'],specs).tolist(),[47,992])
        # Explicit bench unit declarations must not trigger scaling either.
        bench.attrs['column_units']['water  pressure'] = 'mbar'
        traces = comparison_traces(bench,curves,columns,specs)['pressure']
        self.assertEqual(sample_trace(traces['bench'],1),992)
        card = C.generate_scorecard(bench,curves)
        row = card.set_index('parameter').loc['Peak Water Pressure']
        self.assertEqual(row['sim_val'],'863.00 Pa')
        self.assertEqual(row['raw_val'],'992.00 Pa')
        self.assertEqual(row['delta'],'+129.00 Pa')
        self.assertEqual(row['percent'],'+14.95%')
        self.assertEqual(row['status'],'YELLOW')
        import matplotlib.pyplot as plt
        fig,axes,_,error = C.render_comparison_figure(bench,curves)
        self.assertIsNone(error)
        np.testing.assert_array_equal(axes[0].lines[0].get_ydata(),[0,863])
        np.testing.assert_array_equal(axes[0].lines[1].get_ydata(),[47,992])
        self.assertEqual(axes[0].get_ylabel(),'Pa')
        self.assertEqual(axes[0].get_ylim(),(0,3000))
        plt.close(fig)
        bench.loc[1,'water  pressure'] = 4000
        fig,axes,_,error = C.render_comparison_figure(bench,curves)
        self.assertGreater(axes[0].get_ylim()[1],4000)
        plt.close(fig)
        buffer = BytesIO()
        with pd.ExcelWriter(buffer,engine='openpyxl') as writer:
            write_excel_frame(writer,card,'Scorecard_Summary')
        exported = pd.read_excel(BytesIO(buffer.getvalue())).set_index('parameter')
        self.assertEqual(exported.loc['Peak Water Pressure','raw_val'],'992.00 Pa')
        self.assertEqual(exported.loc['Peak Water Pressure','colour_band'],'YELLOW')

    def test_heater_128_and_other_positive_integers_measure_on_intervals(self):
        bench = pd.DataFrame({'time_min':[0,1,2,3,4], 'Heat Valve':[0,128,2,1,0]})
        curves = {'heater_power':curve([0,1,2,3,4],[0,2000,2000,2000,0],'W')}
        card = C.generate_scorecard(bench,curves).set_index('parameter')
        row = card.loc['Total Heating Active Duration']
        self.assertEqual(row['raw_val'],'3.00 min')
        self.assertEqual(row['percent'],'+0.00%')
        self.assertEqual(row['status'],'GREEN')
        bench['Heat Valve'] = bench['Heat Valve'].astype(float)
        bench.loc[2,'Heat Valve'] = .5
        card = C.generate_scorecard(bench,curves).set_index('parameter')
        self.assertEqual(card.loc['Total Heating Active Duration','raw_val'],'Unavailable')

    def test_individual_actuator_counts_and_zero_baseline_percentage(self):
        bench = pd.DataFrame({'time_min':[0,1,2,3,4], 'Inlet Valve':[0,128,0,2,0],
                              'out Vavle':[0,128,128,128,0], 'Drain Valve':[0,2,0,3,0], 'Current Temperature':[0]*5})
        curves = {'pre_wash_valve_open':curve([0,1,2,3,4],[0,1,1,1,0],'state'),
                  'wash_valve_open':curve([0,1,2,3,4],[0,1,1,1,0],'state'),
                  'drain_open':curve([0,1,2,3,4],[0,1,1,1,0],'state'),
                  'temperature':curve([0,1,2,3,4],[0]*5,'°C')}
        card = C.generate_scorecard(bench,curves).set_index('parameter')
        for key,difference in [('Pre-wash Valve Activations','+1'),('Main-wash Valve Activations','+0'),('Drain Pump Evacuations','+1')]:
            self.assertEqual(card.loc[key,'delta'],difference)
            self.assertEqual(card.loc[key,'percent'],'—')
            self.assertEqual(card.loc[key,'status'],'VALUE')
        self.assertEqual(card.loc['Peak Water Temperature','percent'],'—')
        self.assertEqual(card.loc['Peak Water Temperature','status'],'VALUE')

    def test_export_contains_colour_bands_without_acceptance_verdicts(self):
        frame = pd.DataFrame([{'parameter':'Temperature','sim_val':'10 °C','raw_val':'9 °C','delta':'-1 °C',
                               'percent':'-10.00%','notes':'','status':'YELLOW'}])
        buffer = BytesIO()
        with pd.ExcelWriter(buffer,engine='openpyxl') as writer:
            write_excel_frame(writer,frame,'Scorecard_Summary')
        book = load_workbook(BytesIO(buffer.getvalue()))
        sheet = book['Scorecard_Summary']
        self.assertEqual(sheet['G1'].value,'colour_band')
        self.assertEqual(sheet['G2'].value,'YELLOW')
        self.assertEqual(sheet['A2'].fill.fgColor.rgb,'00FFF3B0')
        self.assertEqual(sheet['E2'].value,'-10.00%')


if __name__=='__main__':
    unittest.main()

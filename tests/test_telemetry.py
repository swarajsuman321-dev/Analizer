"""Presentation must preserve recorded values, states and the original workspace."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pandas as pd
from app_telemetry import (normalized_values, signals_from_curves, signals_from_aligned,
                           recorded_phase_spans, demo_signals)
from app_inspection import sample_trace
from app_simulation import SimulationCsvAdapter
from test_csv_comparison import fixture


class TelemetryDataTests(unittest.TestCase):
    def test_normalization_preserves_missing_values_and_input(self):
        data = np.array([2., 4., np.nan, 8.])
        before = data.copy()
        np.testing.assert_allclose(normalized_values(data), [0., 1/3, np.nan, 1.])
        np.testing.assert_equal(data,before)
        np.testing.assert_allclose(normalized_values([4., np.nan, 4.]), [.5,np.nan,.5])

    def test_simulation_channels_keep_units_values_and_step_states(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'run.csv';fixture().to_csv(path,index=False)
            adapter=SimulationCsvAdapter(path, pressure_display_unit='Pa', preserve_pressure_numbers=True)
            signals={s.key:s for s in signals_from_curves(adapter.extract_curves())}
            self.assertEqual(len(signals),10)
            self.assertEqual(signals['pressure'].unit,'Pa')
            self.assertEqual(sample_trace(signals['pressure'].trace,1),300)
            self.assertEqual(sample_trace(signals['heater_power'].trace,1.5),1000)
            self.assertEqual(sample_trace(signals['actual_remaining_time'].trace,3),0)
            self.assertEqual(signals['stwf_number'].kind,'code')
            self.assertEqual(sample_trace(signals['stwf_number'].trace,1.5),2907)

    def test_aligned_states_use_existing_mapping_and_preserve_unknowns(self):
        frame=pd.DataFrame({'relative_minutes':[0,1,2,3], 'Heat Valve':[0,128,-1,0],
                            'Custom voltage [V]':[0,10,20,30]})
        settings={'heater':{'enabled':True,'name':'Heater state','source_col':'Heat Valve','data_col':'Heat Valve'},
                  'custom':{'enabled':True,'name':'Custom voltage (V)','data_col':'Custom voltage [V]'}}
        before=frame.copy(deep=True)
        signals={s.key:s for s in signals_from_aligned(frame,settings)}
        self.assertEqual(signals['heater'].kind,'digital')
        self.assertEqual(sample_trace(signals['heater'].trace,1.5),1)
        self.assertTrue(np.isnan(sample_trace(signals['heater'].trace,2)))
        self.assertEqual(signals['custom'].unit,'V')
        self.assertEqual(sample_trace(signals['custom'].trace,1.5),15)
        pd.testing.assert_frame_equal(frame,before)

    def test_real_phase_names_are_not_invented(self):
        signals=demo_signals()
        phases=recorded_phase_spans(signals,0,186)
        self.assertTrue(all('Wash' not in label for _,_,label,_ in phases))
        self.assertTrue(any(label=='STWF 31' for _,_,label,_ in phases))
        self.assertEqual(recorded_phase_spans([],0,10)[0][2],
                         'Recording timeline · Phase names unavailable')


@unittest.skipUnless(sys.platform=='win32' or os.environ.get('DISPLAY'), 'Requires a graphical display')
class TelemetryGuiTests(unittest.TestCase):
    def setUp(self):
        from main import ApplianceSignalStudioPro
        self.error_patch = patch('tkinter.messagebox.showerror', side_effect=lambda title, message, **kw: (_ for _ in ()).throw(AssertionError(f'{title}: {message}')))
        self.error_patch.start()
        self.app=ApplianceSignalStudioPro()
        self.app.geometry('1200x750')
        self.app.update()
        self.panel=self.app.telemetry

    def tearDown(self):
        self.app._close_application()
        self.error_patch.stop()

    def test_all_views_seek_zoom_export_and_compact_layout(self):
        self.panel.load_demo();self.app.update()
        self.assertEqual(len(self.app.tabs.tabs()),5)
        for view,count in ((0,10),(1,2),(2,1),(3,5),(4,2)):
            self.panel.view.current(view);self.panel.draw();self.app.update()
            self.assertEqual(len(self.panel.axes),count)
            self.panel.seek(99.6)
            self.assertTrue(all(line.get_xdata()[0]==99.6 for line in self.panel.cursor_lines))
        self.assertIn('STWF Code', [s.label for s in self.panel.visible])
        before=self.panel.axes[0].get_xlim()
        event=SimpleNamespace(inaxes=self.panel.axes[0],xdata=99.6,button='up')
        self.panel._scroll(event)
        after=self.panel.axes[0].get_xlim()
        self.assertLess(after[1]-after[0], before[1]-before[0])
        self.panel._click(SimpleNamespace(inaxes=self.panel.axes[0],xdata=99.6,dblclick=True))
        self.assertEqual(self.panel.axes[0].get_xlim(),before)
        self.panel.toggle_play()
        self.assertTrue(self.panel.playing)
        self.panel.pause()
        self.assertFalse(self.panel.playing)
        self.assertIsNone(self.panel._job)
        button=self.panel.play_button
        self.assertLess(button.winfo_rooty()+button.winfo_height(),self.app.winfo_rooty()+self.app.winfo_height())
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'chart.png')
            with patch('app_telemetry.filedialog.asksaveasfilename',return_value=path):
                self.panel.export_image()
            self.assertGreater(Path(path).stat().st_size,1000)
        self.panel.set_signals([], 'Reset');self.app.update()
        self.assertFalse(self.panel.visible)

    def test_import_recording_and_original_workspaces_remain_available(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'run.csv';fixture().to_csv(path,index=False)
            with patch('app_telemetry.filedialog.askopenfilename',return_value=str(path)):
                self.panel.open_reference()
            self.app.update()
            self.assertFalse(self.panel.demo)
            self.assertEqual(len(self.panel.signals),10)
            self.panel.seek(3)
            self.assertEqual(sample_trace(next(s for s in self.panel.signals if s.key=='actual_remaining_time').trace,3),0)
        for tab in (self.app.tab_config,self.app.tab_dashboard,self.app.tab_comparator,self.app.tab_patches):
            self.app.tabs.select(tab);self.app.update()
            self.assertTrue(tab.winfo_viewable())
        self.assertTrue(callable(self.app.export_excel))
        self.assertTrue(callable(self.app.export_comp_excel))

    def test_bench_render_keeps_engineering_results_and_excel_export(self):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory)
            primary=directory/'power.csv';machine=directory/'machine.csv'
            pd.DataFrame({'timestamp':pd.date_range('2026-10-03',periods=6,freq='s'),
                          'Power [W]':[2,3,2,53,53,2]}).to_csv(primary,index=False)
            pd.DataFrame({'timestamp':pd.date_range('2026-10-03',periods=6,freq='s'),
                          'Drump speed feedback':[0,0,0,23,30,0],
                          'Heat Valve':[0,0,128,128,0,0]}).to_csv(machine,index=False)
            self.app.pd_path=str(primary);self.app.rd_path=str(machine)
            self.app.sync_mode.set('Raw Timestamps (No Shift)')
            self.app.populate_signal_grid()
            self.app.execute_and_view();self.app.update()
            self.assertIsNotNone(self.app.current_fig)
            self.assertEqual(len(self.app.aligned_df),6)
            self.assertTrue(self.panel.signals)
            self.assertFalse(self.panel.demo)
            self.assertEqual(self.app.tabs.select(),str(self.app.tab_telemetry))
            target=directory/'bench.xlsx'
            with patch('main.filedialog.asksaveasfilename',return_value=str(target)), patch('main.messagebox.showinfo'):
                self.app.export_excel()
            self.assertTrue(target.exists())
            with pd.ExcelFile(target) as workbook:
                self.assertIn('Synchronized_Series',workbook.sheet_names)
            self.assertEqual(len(pd.read_excel(target,sheet_name='Synchronized_Series')),6)
            self.app._quick_replot();self.app.update()
            self.assertTrue(self.panel.signals)

"""Earlier-version capabilities exercised through current services and Qt tools."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from PySide6 import QtCore,QtWidgets,QtGui
from app_channel_store import Channel,ChannelStore
from app_analysis_service import align_recordings,compare_recordings,load_reference
from app_extensions import PluginManager
from app_studio_state import validate_preset,recorded_phases,export_full_workbook


def recordings(root):
    power=root/'power.csv';machine=root/'machine.csv';sim=root/'sim.csv'
    pd.DataFrame({'timestamp':pd.date_range('2026-10-03 10:25:56',periods=6,freq='s'),'P-E1':[2,2,2,53,53,2],'Energy [Wh]':[0,1,2,3,4,5]}).to_csv(power,index=False)
    pd.DataFrame({'timestamp':pd.date_range('2026-10-03 10:25:56',periods=6,freq='s'),
                  'Drump speed feedback':[0,0,0,23,30,0],'Current Temperature':[20,22,24,26,28,30],
                  'Heat Valve':[0,0,0,128,128,0],'water pressure':[0,100,200,300,400,0]}).to_csv(machine,index=False)
    pd.DataFrame({'time':np.arange(6)/60,'water_temp':[20,22,24,26,28,30],'water_pressure':[0,100,200,300,400,0],
                  'drum_speed':[0,0,0,23,30,0],'heater_power':[0,0,0,2000,2000,0],'water_amount':[0,1,2,3,4,5],
                  'water_volume':[0,1,2,3,4,0],'pre_wash_valve_open':[0,1,0,0,0,0],
                  'main_wash_valve_open':[0,0,1,0,0,0],'drain_open':[0,0,0,0,1,0],
                  'stwf_number':[0,1,2,2,3,3],'process_state':[0,1,2,2,3,3]}).to_csv(sim,index=False)
    return power,machine,sim


class EngineeringParityTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.power,self.machine,self.sim=recordings(self.root)
    def tearDown(self):self.temp.cleanup()
    def test_single_input_and_full_kpi_quality_tables(self):
        store,frame=align_recordings(str(self.power),'','Raw Timestamps (No Shift)')
        self.assertEqual(len(frame),6);sheets={d.frame.attrs.get('studio_sheet'):d.frame for d in store.datasets.values()}
        self.assertIn('Summary_KPIs',sheets);self.assertIn('Data_Quality',sheets)
        self.assertIn('Energy Counter Increase',sheets['Summary_KPIs'].Parameter.tolist())
        self.assertEqual(len(sheets['Original_power']),6)
        self.assertTrue(any(c.unit=='Wh' for c in store.channels.values()))
    def test_manual_offset_seconds_are_not_treated_as_minutes(self):
        store,frame=align_recordings(str(self.power),str(self.machine),'Manual Time Offset (Minutes)',1.5)
        self.assertEqual(frame.attrs['sync_report']['power_shift_seconds'],1.5)
    def test_drum_sync_and_full_diagnostic_workbook(self):
        from app_data import DRUM_SYNC_STRATEGY
        store,frame=align_recordings(str(self.power),str(self.machine),DRUM_SYNC_STRATEGY)
        self.assertEqual(frame.attrs['sync_report']['power_shift_seconds'],0)
        path=self.root/'engineering.xlsx';export_full_workbook(path,store)
        with pd.ExcelFile(path) as book:
            self.assertIn('Summary_KPIs',book.sheet_names);self.assertIn('Data_Quality',book.sheet_names)
            self.assertEqual(len(pd.read_excel(book,sheet_name='Original_power')),6)
            self.assertEqual(len(pd.read_excel(book,sheet_name='Original_machine')),6)
            self.assertEqual(len(pd.read_excel(book,sheet_name='Synchronized_Series')),6)
    def test_comparison_exports_all_rows_and_trace_diagnostics(self):
        result=compare_recordings(str(self.machine),str(self.sim),detailed=True)
        path=self.root/'comparison.xlsx';export_full_workbook(path,result.store)
        with pd.ExcelFile(path) as book:
            for name in ('Original_Bench','Raw_Test_Log','Simulation_CSV','CSV_Trace_Quality','CSV_Units','Heater_State_Comparison','Comparison_Info','Scorecard_Summary'):self.assertIn(name,book.sheet_names)
            self.assertEqual(len(pd.read_excel(book,sheet_name='Original_Bench')),6)
            self.assertEqual(len(pd.read_excel(book,sheet_name='Simulation_CSV')),6)
            self.assertNotIn('status',pd.read_excel(book,sheet_name='Scorecard_Summary').columns)
    def test_explicit_bench_mapping_changes_both_trace_and_scorecard(self):
        frame=pd.read_csv(self.machine).rename(columns={'Current Temperature':'Custom probe'});frame.to_csv(self.machine,index=False)
        result=compare_recordings(str(self.machine),str(self.sim),bench_columns={'temperature':'Custom probe'},detailed=True)
        self.assertEqual(result.columns['temperature'],'Custom probe')
        temperature=next(c for c in result.store.channels.values() if c.attributes['parameter']=='temperature' and c.attributes['comparison_source']=='bench')
        np.testing.assert_equal(temperature.y,frame['Custom probe'])
        with self.assertRaisesRegex(ValueError,'missing'):compare_recordings(str(self.machine),str(self.sim),bench_columns={'temperature':'missing'})
    def test_reference_opens_without_bench_and_preserves_source(self):
        store=load_reference(self.sim);self.assertEqual(len(store.channels),10)
        source=next(d for d in store.datasets.values() if d.name=='Simulation reference')
        self.assertEqual(len(source.frame),6);self.assertTrue(any(c.attributes['parameter']=='actual_remaining_time' for c in store.channels.values()))
    def test_phase_intervals_use_only_observed_states(self):
        c=Channel('STWF code',np.arange(6.),np.array([1,1,np.nan,3,3,5]),kind='discrete')
        spans=recorded_phases([c]);self.assertEqual([v['label'] for v in spans],['1','Unknown','3'])
        self.assertEqual(spans[0]['end'],2);self.assertEqual(recorded_phases([Channel('Temperature',np.arange(3.),np.arange(3.))]),[])
    def test_preset_validation_rejects_invalid_values_before_mutation(self):
        for entry in ({'width':-1},{'width':np.nan},{'ymin':3,'ymax':2},{'color':'bad color'},{'panel':'Panel 11'},{'enabled':'yes'}):
            with self.assertRaises(ValueError):validate_preset({'version':2,'signals':{'Probe':entry}})
    def test_old_plugin_hooks_execute_disable_reload_and_rollback(self):
        manager=PluginManager(self.root/'extensions');plugin=self.root/'custom.py'
        plugin.write_text('''"""Custom engineering hooks."""
def register_patch(manager):
 manager.custom_kpi_hooks.append(lambda frame:[('Custom KPI',len(frame))])
 manager.custom_sync_hooks['Custom sync']=lambda frame:frame
 manager.custom_plot_hooks.append(lambda fig,axes,frame:axes[0].plot(frame.relative_minutes,frame['P-E1']))
''')
        manager.install(plugin);self.assertIn('Custom sync',manager.custom_sync_hooks)
        store,frame=align_recordings(str(self.power),str(self.machine),'Custom sync',plugins=manager)
        kpis=next(d.frame for d in store.datasets.values() if d.frame.attrs.get('studio_sheet')=='Summary_KPIs')
        self.assertIn('Custom KPI',kpis.Parameter.tolist())
        manager.set_enabled('custom.py',False);self.assertEqual(manager.custom_sync_hooks,{})
        manager.set_enabled('custom.py',True);self.assertIn('Custom sync',manager.custom_sync_hooks)
        broken=self.root/'broken.py';broken.write_text("def register_patch(manager):\n manager.custom_kpi_hooks.append('not callable')\n")
        with self.assertRaises(ValueError):manager.install(broken)
        self.assertEqual(len(manager.custom_kpi_hooks),1);self.assertIn('broken.py',manager.patch_errors)
        manager.remove('broken.py');self.assertNotIn('broken.py',manager.files())
        manager.remove('custom.py');self.assertEqual(manager.custom_sync_hooks,{})
    def test_plugin_bad_config_does_not_activate_extensions(self):
        manager=PluginManager(self.root/'extensions');manager.directory.mkdir();manager.config.write_text('{broken')
        with self.assertRaises(ValueError):manager.reload()
        self.assertEqual(manager.custom_kpi_hooks,[])

    def test_image_reference_calibration_and_quality_are_restored(self):
        from PIL import Image,ImageDraw
        from app_reference_image import SimulationImageAnalyzer
        path=self.root/'reference.png';image=Image.new('RGB',(2500,704),'white');draw=ImageDraw.Draw(image)
        draw.rectangle((50,40,2450,620),outline='black',width=2);draw.line((55,250,2445,250),fill=(32,32,32),width=3);draw.line((55,220,2445,220),fill=(32,188,255),width=3);image.save(path)
        calibration={'duration_min':10,'reference_height':704,'plot_bounds':[50,2450,40,620],'time_verified':False,'axis_verified':False}
        analyzer=SimulationImageAnalyzer(path,calibration=calibration);curves=analyzer.extract_curves()
        self.assertTrue(np.isfinite(curves['temperature']['value']).any())
        self.assertFalse(analyzer.analysis_info()['calibration_verified'])
        store=load_reference(path,calibration=calibration);self.assertGreater(len(store.channels),0)
        self.assertTrue(any(d.frame.attrs.get('studio_sheet')=='Image_Calibration' for d in store.datasets.values()))
        result=compare_recordings(str(self.machine),str(path),calibration=calibration,detailed=True)
        self.assertIn('REVIEW',result.score.status.tolist())
        with self.assertRaises(ValueError):SimulationImageAnalyzer(path,calibration={'duration_min':-1})


class QtParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def setUp(self):
        from app_workbench import AdvancedStudioWindow
        self.window=AdvancedStudioWindow();self.window.resize(1280,850);self.window.show();self.app.processEvents()
        self.errors=[];self.warning=patch.object(QtWidgets.QMessageBox,'warning',side_effect=lambda *args:self.errors.append(args[-1]));self.warning.start()
    def tearDown(self):
        self.window.close();self.app.processEvents();self.app.sendPostedEvents(None,QtCore.QEvent.Type.DeferredDelete);self.warning.stop();self.assertEqual(self.errors,[])
    def add(self,name='Probe',unit='V',**kwargs):return self.window.store.add(Channel(name,np.arange(11.),np.arange(11.)*2,unit=unit,coordinate_unit='min',**kwargs))
    def test_tools_keep_two_workspaces_with_all_view_panels_enabled(self):
        w=self.window;self.assertEqual(w.tabs.count(),2);self.assertTrue(any(a.text()=='Tools' for a in w.menuBar().actions()))
        self.assertTrue(all(d.toggleViewAction().isChecked() for d in w.docks.values()))
    def test_channel_mapping_style_manual_bounds_and_ten_panels(self):
        w=self.window;a=self.add();b=self.add('Power','W');w.dashboard.assign([a.id,b.id])
        entry=lambda name,panel,color,side:{'name':name,'unit':'W' if name=='Power' else 'V','enabled':True,'panel':panel,'twin':side,'style':'Dashed (--)','width':2,'color':color,'ymin':'-1','ymax':'30'}
        w.studio.apply_channel_entries({a.id:entry('Renamed','Panel 1','#cc2244',False),b.id:entry('Power','Panel 10','#22aa66',True)})
        self.assertEqual(w.store.channels[a.id].name,'Renamed');self.assertEqual(w.dashboard.layout_name,'10 panels')
        self.assertEqual(w.dashboard.panes[9].ids,[b.id]);curve=w.dashboard.panes[0].curves[a.id][1]
        self.assertEqual(curve.pen.color().name(),'#cc2244');self.assertEqual(curve.pen.widthF(),2)
        np.testing.assert_allclose(w.dashboard.panes[0].getViewBox().viewRange()[1],[-1,30])
    def test_extra_left_axis_and_right_primary_are_supported(self):
        w=self.window;a=self.add(attributes={'plot_style':{'side':'left'}});b=self.add('Power','W',attributes={'plot_style':{'side':'left'}})
        w.dashboard.assign([a.id,b.id]);self.app.processEvents();pane=w.dashboard.active
        self.assertEqual(pane.axes['W'][0].orientation,'left')
        self.assertLess(pane.axes['W'][0].sceneBoundingRect().right(),pane.getViewBox().sceneBoundingRect().left()+5)
        w.store.update(a.id,attributes={'plot_style':{'side':'right'}});pane.bind([a.id])
        self.assertTrue(pane.getAxis('right').isVisible());self.assertFalse(pane.getAxis('left').isVisible())
    def test_old_presets_and_deferred_presets_apply_to_real_channels(self):
        w=self.window;record={'version':2,'signals':{'Probe':{'name':'Voltage','panel':'Panel 1','enabled':True,'width':'2','color':'#ff0055','style':'Dotted (:)','ymin':'','ymax':''}},'options':{'offset_minutes':1.5,'title':'Imported preset'}}
        self.assertEqual(w.studio.apply_preset(record),0);self.assertIsNotNone(w.studio.pending_preset)
        other=ChannelStore();c=other.add(Channel('Probe',np.arange(11.),np.arange(11.),unit='V',attributes={'source_column':'Probe'}));w.merge_store(other)
        self.assertEqual(w.store.channels[c.id].name,'Voltage');self.assertEqual(w.offset.value(),90)
        self.assertEqual(w.studio.options['title'],'Imported preset');self.assertIsNone(w.studio.pending_preset)
    def test_normalized_display_keeps_original_readouts_and_source(self):
        w=self.window;a=self.add();b=self.add('Power','W');w.dashboard.assign([a.id,b.id]);before=w.store.channels[a.id].y.copy()
        w.studio.toggle_normalized();pane=w.dashboard.active;pane._render()
        self.assertTrue(pane.normalized);self.assertEqual(len(pane.axes),0)
        self.assertGreaterEqual(np.nanmin(pane.curves[b.id][1].yData),1)
        pane.cursor_lines[0].setValue(4);self.assertEqual(pane.measurements()[a.id]['A'],8)
        np.testing.assert_equal(w.store.channels[a.id].y,before);w.studio.toggle_normalized();self.assertFalse(pane.normalized)
    def test_zoom_history_and_export_copy(self):
        w=self.window;a=self.add();w.dashboard.assign([a.id]);pane=w.dashboard.active;pane.remember_view();original=pane.getViewBox().viewRange()[0]
        pane.setXRange(2,6,padding=0);pane.remember_view();pane.navigate_history(-1);np.testing.assert_allclose(pane.getViewBox().viewRange()[0],original)
        pane.navigate_history(1);np.testing.assert_allclose(pane.getViewBox().viewRange()[0],[2,6]);w.studio.copy_readout();self.assertIn('Probe',self.app.clipboard().text())
    def test_sparse_playback_advances_seek_and_stops_on_close(self):
        w=self.window;a=self.add();w.dashboard.assign([a.id]);dialog=w.studio.playback();context=w.studio.play_context
        context['speed'].setValue(60);w.studio._last_tick=time.monotonic()-.2;start=context['pane'].cursor_lines[0].value();w.studio.tick();w.studio._last_tick=time.monotonic()-.9;w.studio.tick()
        self.assertGreater(context['pane'].cursor_lines[0].value(),start)
        w.studio.seek(1);self.assertEqual(context['position'],1);self.assertEqual(context['pane'].cursor_lines[0].value(),1)
        w.studio.play_timer.start();dialog.close();self.app.processEvents();self.assertFalse(w.studio.play_timer.isActive());self.assertIsNone(w.studio.play_context)
    def test_illustrative_signals_load_directly_no_preview_window(self):
        w=self.window;w.studio.illustrative();self.assertEqual(len(w.store.channels),10);self.assertEqual(sum(len(p.ids) for p in w.dashboard.panes if not p.isHidden()),10)
        self.assertTrue(all(c.attributes['illustrative'] for c in w.store.channels.values()));self.assertEqual(w.tabs.count(),2)
        self.assertFalse(hasattr(w,'preview_plot'))
    def test_studio_settings_and_report_tables_survive_snapshot(self):
        from app_workspace_io import save_workspace
        from app_analysis_service import add_table
        w=self.window;a=self.add();w.dashboard.assign([a.id]);w.studio.options['title']='Saved title';w.studio.calibration={'duration_min':120,'time_verified':False}
        add_table(w.store,'KPIs',pd.DataFrame({'Parameter':['Example'],'Value':[4]}),sheet='Summary_KPIs')
        with tempfile.TemporaryDirectory() as root:
            path=save_workspace(Path(root)/'workspace.json',w.store,[p.state() for p in w.workspaces],w.ui_state())
            w.studio.options['title']='Changed';w.restore_path(path)
            self.assertEqual(w.studio.options['title'],'Saved title');self.assertEqual(w.studio.calibration['duration_min'],120)
            self.assertTrue(any(d.frame.attrs.get('studio_sheet')=='Summary_KPIs' for d in w.store.datasets.values()))
    def test_tool_dialogs_open_and_close_without_running_jobs(self):
        w=self.window;a=self.add();w.dashboard.assign([a.id])
        for method in (w.studio.channel_settings,w.studio.display_options):
            dialog=method();self.app.processEvents();self.assertTrue(dialog.isVisible());dialog.close();self.app.processEvents()
        w.studio.diagnostics().close()

    def test_ten_hidden_panels_survive_session_restore(self):
        w=self.window;c=self.add();workspace=w.dashboard;workspace.set_layout('10 panels');workspace.panes[9].bind([c.id]);workspace.set_layout('Single')
        state=workspace.state();workspace.restore(state);workspace.set_layout('10 panels')
        self.assertEqual(workspace.panes[9].ids,[c.id])

    def test_many_units_use_readable_full_width_plots(self):
        w=self.window;other=ChannelStore()
        for i,unit in enumerate(('°C','Pa','state','L','code','RPM','W','Wh')):
            other.add(Channel(f'Signal {i}',np.arange(11.),np.arange(11.),unit=unit,coordinate_unit='min'))
        w.merge_store(other);self.app.processEvents()
        self.assertEqual(w.dashboard.layout_name,'3 stacked')
        self.assertTrue(all(len(set(pane.bindings.values()))<=3 for pane in w.dashboard.visible_panes()))
        self.assertEqual(sum(len(pane.ids) for pane in w.dashboard.visible_panes()),8)
        self.assertTrue(all(pane.getViewBox().width()>=350 for pane in w.dashboard.visible_panes()))


if __name__=='__main__':unittest.main()

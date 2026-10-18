"""User-facing compact actions, mapping setup and safe persisted state."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from PySide6 import QtCore,QtWidgets
from app_channel_store import Channel,Dataset
from app_workbench import AdvancedStudioWindow
from app_workspace_io import save_workspace
from app_studio_state import channel_preset
from app_trace_colors import channel_colors
from app_engineering_session import analyze_session


class CompactUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def setUp(self):
        self.root=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'ANALIZER_OUTPUT_DIR':self.root.name,'ANALIZER_SETTINGS_DIR':self.root.name});self.env.start()
        self.w=AdvancedStudioWindow();self.w.resize(1280,900);self.w.show();self.app.processEvents()
        ds=Dataset('Run A',pd.DataFrame(),'');self.w.store.datasets[ds.id]=ds;self.ds=ds
        self.c=self.w.store.add(Channel('Power',[0,1,2],[100,200,100],unit='W',coordinate_unit='min',dataset_id=ds.id));self.w.dashboard.assign([self.c.id]);self.app.processEvents()
    def tearDown(self):self.w.close();self.app.processEvents();self.env.stop();self.root.cleanup()
    def test_one_click_toggles_are_isolated_and_do_not_rebind(self):
        w=self.w;p=w.dashboard.active;curve=p.curves[self.c.id][1]
        w.compact.toggles['show_legends'].trigger();self.assertFalse(p.legend.isVisible());self.assertIs(p.curves[self.c.id][1],curve)
        w.compact.toggles['show_grid'].trigger();self.assertFalse(p.show_grid)
        w.tabs.setCurrentIndex(1);self.assertTrue(w.compact.toggles['show_grid'].isChecked())
        w.tabs.setCurrentIndex(0);self.assertFalse(w.compact.toggles['show_grid'].isChecked())
    def test_legend_rendered_text_tracks_dark_light_dark(self):
        for theme,color in [('Dark','#e3eaf5'),('Light','#182033'),('Dark','#e3eaf5')]:
            self.w.theme.apply(theme);self.app.processEvents()
            labels=self.w.dashboard.active.legend.items
            self.assertTrue(labels)
            for _,label in labels:self.assertIn(color,label.item.toHtml().lower())

    def test_inline_playback_has_no_popup_and_handles_no_phase(self):
        strip=self.w.studio.playback();self.app.processEvents()
        self.assertFalse(strip.isWindow());self.assertLess(strip.height(),150);self.assertEqual(len(strip.findChildren(QtWidgets.QTableView)),0)
        context=self.w.studio.play_context;context['button'].click();self.assertTrue(self.w.studio.play_timer.isActive());strip.close();self.assertIsNone(self.w.studio.play_context)
    def test_inline_playback_phase_details_are_collapsible(self):
        state=self.w.store.add(Channel('Cycle stage',[0,1,2],[0,1,1],unit='code',coordinate_unit='min',kind='discrete',dataset_id=self.ds.id));self.w.dashboard.assign([state.id])
        strip=self.w.studio.playback();button=next(b for b in strip.findChildren(QtWidgets.QToolButton) if b.text()=='Observed Phase Details');button.click();self.app.processEvents();self.assertTrue(button.isChecked());strip.close()
    def test_focus_restores_exact_saved_dock_visibility(self):
        w=self.w;w.docks['Properties'].hide();self.app.processEvents();prior=bytes(w.saveState())
        w.compact.focus_action.setChecked(True);self.assertTrue(all(d.isHidden() for d in w.docks.values()))
        w.compact.focus_action.setChecked(False);self.assertEqual(bytes(w.saveState()),prior)
    def test_small_settings_fit_and_screen_geometry_is_respected(self):
        dialog=self.w.studio.display_options();self.app.processEvents();area=dialog.screen().availableGeometry()
        self.assertLess(dialog.height(),450);self.assertLessEqual(dialog.width(),area.width());self.assertLessEqual(dialog.height(),area.height());dialog.close()
        dialog=self.w.engineering.configure();self.app.processEvents();self.assertLessEqual(dialog.width(),area.width());self.assertLessEqual(dialog.height(),area.height());dialog.close()
    def test_many_channel_legend_is_outside_canvas_and_complete(self):
        ids=[self.c.id]
        for index in range(35):ids.append(self.w.store.add(Channel('Valve '+str(index),[0,1,2],[0,1,0],unit='state',coordinate_unit='min',dataset_id=self.ds.id)).id)
        ws=self.w.dashboard;ws.assign(ids);self.app.processEvents();ws.update_channel_legend();self.app.processEvents()
        self.assertFalse(ws.active.legend.isVisible());self.assertTrue(ws.channel_legend.isVisible());self.assertEqual(ws.channel_legend.count(),36);self.assertLessEqual(ws.channel_legend.height(),70)
        self.assertLess(ws.channel_legend.mapToGlobal(ws.channel_legend.rect().bottomLeft()).y(),ws.active.mapToGlobal(ws.active.rect().topLeft()).y())
    def test_automatic_colors_persist_in_presets_and_copies_are_distinct(self):
        second=self.w.store.add(Channel('Drain Valve',[0,1],[0,1],unit='state'));colors=channel_colors(self.w.store);record=channel_preset(self.w.store,self.w.dashboard,{})
        self.assertEqual(record['signals']['Drain Valve']['color'],colors[second.id]);copy=self.w.store.duplicate(second.id);self.assertNotEqual(channel_colors(self.w.store)[copy.id],colors[second.id])
    def test_engineering_session_and_workspace_specific_toggles_roundtrip(self):
        self.w.engineering.session['runs']['analysis']=self.ds.id;self.w.engineering.session['profile']['acceptance']={'peak_power':{'max':190,'unit':'W'}}
        self.w.compact.toggles['show_grid'].trigger()
        path=save_workspace(Path(self.root.name)/'saved.json',self.w.store,[ws.state() for ws in self.w.workspaces],self.w.ui_state())
        self.w.restore_path(path);self.assertEqual(self.w.engineering.session['runs']['analysis'],self.ds.id);self.assertFalse(self.w.dashboard.active.show_grid);self.assertTrue(self.w.comparison.active.show_grid)
    def test_engineering_results_plots_and_overlays_leave_originals_unchanged(self):
        ds=Dataset('Run B',pd.DataFrame(),'');self.w.store.datasets[ds.id]=ds;b=self.w.store.add(Channel('Power',[0,1,2],[100,220,100],unit='W',coordinate_unit='min',dataset_id=ds.id))
        engine=self.w.engineering;engine.session['runs'].update(reference=self.ds.id,candidate=ds.id);engine.session['profile']['tolerances']={'power':{'relative_percent':5}}
        source=self.c.y.copy();engine.result=analyze_session(self.w.store,engine.session,True);engine.plot_comparison();self.app.processEvents()
        self.assertTrue(engine.overlays);np.testing.assert_array_equal(self.c.y,source);self.assertIs(self.w.store.channels[self.c.id],self.c)
        engine.toggle_envelopes(False);self.assertFalse(engine.overlays)

    def test_cancel_action_targets_current_worker_and_preserves_prior_result(self):
        from PySide6 import QtTest
        w=self.w;engine=w.engineering;old=analyze_session(w.store,engine.session);engine.result=old
        def work(token):
            if token.wait(5):raise InterruptedError('cancelled')
            return 42
        completed=[];engine.task(work,completed.append);self.assertTrue(w.busy);token=engine.cancel_token
        with self.assertRaises(ValueError):engine.task(work,completed.append)
        self.assertIs(engine.cancel_token,token);engine.cancel_action.trigger()
        for _ in range(100):
            QtTest.QTest.qWait(10)
            if not w.busy:break
        self.assertFalse(w.busy);self.assertTrue(token.is_set());self.assertFalse(completed)
        self.assertIs(engine.result,old)
        engine.result=None

    def test_focus_normal_layout_and_playback_speed_survive_workspace_restore(self):
        w=self.w;normal=bytes(w.saveState());panels={name:(dock.isHidden(),w.dockWidgetArea(dock),set(peer.objectName() for peer in w.tabifiedDockWidgets(dock))) for name,dock in w.docks.items()};w.dashboard.playback_speed=24;w.compact.focus_action.setChecked(True)
        path=save_workspace(Path(self.root.name)/'focus.json',w.store,[ws.state() for ws in w.workspaces],w.ui_state())
        w.compact.focus_action.setChecked(False);w.restore_path(path)
        self.assertTrue(w.compact.focus_action.isChecked());self.assertEqual(w.dashboard.playback_speed,24)
        self.assertEqual(bytes(w.compact.focus_state),normal)
        w.compact.focus_action.setChecked(False);self.app.processEvents()
        self.assertEqual({name:(dock.isHidden(),w.dockWidgetArea(dock),set(peer.objectName() for peer in w.tabifiedDockWidgets(dock))) for name,dock in w.docks.items()},panels)

    def test_invalid_engineering_profile_does_not_replace_current_workspace(self):
        from copy import deepcopy
        state=wstate=self.w.ui_state();state['engineering_session']=deepcopy(state['engineering_session']);state['engineering_session']['profile']['schema_version']=999
        old=self.w.store
        with self.assertRaises(ValueError):self.w.restore_loaded(old,[ws.state() for ws in self.w.workspaces],state)
        self.assertIs(self.w.store,old);self.assertIn(self.c.id,self.w.dashboard.active.ids)

    def test_playback_is_paused_and_closed_before_restored_panes_are_used(self):
        w=self.w;strip=w.studio.playback();context=w.studio.play_context
        path=save_workspace(Path(self.root.name)/'playback.json',w.store,[ws.state() for ws in w.workspaces],w.ui_state())
        w.restore_path(path);self.app.processEvents();self.assertIsNone(w.studio.play_context);self.assertFalse(strip.isVisible())

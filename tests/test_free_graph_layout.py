"""User-created graphs retain their sources, arrangement and visibility homes."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PySide6 import QtCore, QtTest, QtWidgets

from app_channel_store import Channel, ChannelStore
from app_plot_workspace import PlotWorkspace, graph_positions, layout_shape


class FreeGraphLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.store=ChannelStore();self.x=np.arange(101,dtype=float)
        self.channels=[self.store.add(Channel(name,self.x,values,unit=unit,coordinate_unit='min'))
                       for name,unit,values in [('Temperature','°C',self.x/5+20),('Pressure','Pa',self.x*20),('Speed','RPM',self.x*10)]]
        self.workspace=PlotWorkspace(self.store);self.workspace.resize(1280,1000);self.workspace.show()
        self.app.processEvents()

    def tearDown(self):
        self.workspace.close();self.workspace.deleteLater();self.app.processEvents()

    def settle(self):
        for _ in range(5):self.app.processEvents();QtTest.QTest.qWait(20)

    def test_add_blank_graph_below_right_and_move_keep_every_existing_trace(self):
        first=self.workspace.active;first.bind([self.channels[0].id])
        second=self.workspace.add_graph();self.assertIs(self.workspace.active,second)
        self.assertEqual(second.ids,[]);second.bind([self.channels[1].id])
        third=self.workspace.add_graph('right');third.bind([self.channels[2].id])
        self.assertEqual(self.workspace.layout_name,'Custom')
        self.assertEqual(self.workspace.positions(),[(0,0),(1,0),(1,1)])
        self.assertEqual(self.workspace.shape(),(2,2))
        self.workspace.move_graph(third,'left')
        self.assertEqual(self.workspace.positions(),[(0,0),(1,1),(1,0)])
        self.assertEqual([pane.ids for pane in self.workspace.visible_panes()],[[c.id] for c in self.channels])
        self.assertEqual(self.workspace.visible_count(),3)

    def test_add_is_not_limited_to_fixed_presets_and_never_reuses_hidden_data(self):
        self.workspace.set_layout('2×2')
        self.workspace.panes[3].bind([self.channels[2].id])
        self.workspace.set_layout('Single')
        blank=self.workspace.add_graph()
        self.assertEqual(blank.ids,[])
        self.assertIn(self.channels[2].id,self.workspace.panes[4].ids)
        for _ in range(10):self.workspace.add_graph()
        self.assertEqual(self.workspace.visible_count(),12)
        self.assertEqual(self.workspace.shape(),(12,1))

    def test_remove_graph_keeps_source_and_other_views_then_adds_fresh_empty_graph(self):
        first=self.workspace.active;first.bind([self.channels[0].id])
        second=self.workspace.add_graph();second.bind([self.channels[1].id])
        self.assertTrue(self.workspace.remove_graph(first))
        self.assertEqual(self.workspace.visible_panes(),[second])
        self.assertIn(self.channels[0].id,self.store.channels)
        self.assertEqual(second.ids,[self.channels[1].id])
        fresh=self.workspace.add_graph()
        self.assertEqual(fresh.ids,[])
        self.assertEqual(second.ids,[self.channels[1].id])

    def test_deselect_and_reselect_retains_pane_homes_axis_bindings_and_ranges(self):
        self.workspace.set_layout('Vertical split')
        first,second=self.workspace.visible_panes()
        first.bind([self.channels[0].id,self.channels[1].id],{self.channels[0].id:'Temperature',self.channels[1].id:'Pressure'})
        second.bind([self.channels[2].id])
        self.workspace.link();first.setXRange(20,80,padding=0);self.settle()
        expected=[(list(p.ids),dict(p.bindings),deepcopy(p.getViewBox().viewRange())) for p in (first,second)]
        ids=[c.id for c in self.channels]
        self.workspace.set_visible(ids,False)
        self.assertEqual([p.ids for p in (first,second)],[[],[]])
        self.workspace.set_visible(ids,True)
        for pane,(channel_ids,bindings,ranges) in zip((first,second),expected):
            self.assertEqual(pane.ids,channel_ids);self.assertEqual(pane.bindings,bindings)
            np.testing.assert_allclose(pane.getViewBox().viewRange(),ranges)
        # File ordering and a user's legend ordering can legitimately differ.
        first.bind([self.channels[1].id,self.channels[0].id])
        self.workspace.set_visible(ids,False)
        self.workspace.set_visible(list(reversed(ids)),True)
        self.assertEqual(first.ids,[self.channels[1].id,self.channels[0].id])

    def test_custom_layout_and_hidden_homes_roundtrip_through_workspace(self):
        from app_workspace_io import load_workspace,save_workspace
        a=self.workspace.active;a.bind([self.channels[0].id])
        b=self.workspace.add_graph('right');b.bind([self.channels[1].id])
        self.workspace.add_graph('below')
        self.workspace.set_visible([self.channels[0].id],False)
        self.workspace.set_pane_proportions(columns=[1,2],rows=[2,1])
        state=deepcopy(self.workspace.state())
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'layout.json';save_workspace(path,self.store,[state],{})
            restored,views,_=load_workspace(path)
        fresh=PlotWorkspace(restored)
        try:
            fresh.restore(views[0])
            self.assertEqual(fresh.positions(),self.workspace.positions())
            self.assertEqual(fresh.layout_proportions,self.workspace.layout_proportions)
            fresh.set_visible([self.channels[0].id],True)
            self.assertEqual(fresh.panes[0].ids,[self.channels[0].id])
            self.assertEqual(fresh.panes[1].ids,[self.channels[1].id])
        finally:fresh.close();fresh.deleteLater();self.app.processEvents()

    def test_divider_drag_resizes_rows_without_changing_plot_ranges(self):
        first=self.workspace.active;first.bind([self.channels[0].id])
        second=self.workspace.add_graph();second.bind([self.channels[1].id])
        self.workspace.link();self.settle()
        old=[deepcopy(p.getViewBox().viewRange()) for p in (first,second)]
        divider=next(d for d in self.workspace._dividers if d.orientation=='rows')
        before=first.height()
        point=divider.rect().center();origin=divider.mapToGlobal(point)
        QtTest.QTest.mousePress(divider,QtCore.Qt.MouseButton.LeftButton,pos=point)
        event=QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove,QtCore.QPointF(point.x(),point.y()+100),QtCore.QPointF(origin.x(),origin.y()+100),QtCore.Qt.MouseButton.NoButton,QtCore.Qt.MouseButton.LeftButton,QtCore.Qt.KeyboardModifier.NoModifier)
        self.app.sendEvent(divider,event)
        QtTest.QTest.mouseRelease(divider,QtCore.Qt.MouseButton.LeftButton,pos=point)
        self.settle()
        self.assertGreater(first.height(),before+50)
        self.assertNotEqual(self.workspace.layout_proportions['Custom']['rows'],[1,1])
        for pane,ranges in zip((first,second),old):np.testing.assert_allclose(pane.getViewBox().viewRange(),ranges)

    def test_custom_export_includes_visible_graphs_once_and_excludes_hidden_history(self):
        from app_reporting import interval_tables
        from app_workspace_io import render_report
        for channel in self.channels:
            self.workspace.active.bind([channel.id])
            if channel is not self.channels[-1]:self.workspace.add_graph('right' if channel is self.channels[0] else 'below')
        self.settle();state=self.workspace.state()
        frames,summary=interval_tables(self.store,state)
        self.assertEqual(set(summary.channel_id),{c.id for c in self.channels})
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'custom.pdf'
            statistics=render_report(path,self.store,state)
            self.assertTrue(path.is_file());self.assertGreater(path.stat().st_size,1000)
        self.assertEqual(len(statistics),3)

    def test_invalid_custom_positions_are_rejected_before_layout_changes(self):
        for cells in ([],[[0,0],[0,0]],[[-1,0]],[[True,0]],[[1000,0]]):
            with self.assertRaises(ValueError):graph_positions({'layout':'Custom','graph_grid':{'positions':cells}})
        self.assertEqual(layout_shape('Vertical split'),(2,1))

    def test_first_selection_in_added_blank_graph_fits_instead_of_restoring_empty_limits(self):
        self.workspace.active.bind([self.channels[0].id])
        blank=self.workspace.add_graph()
        self.workspace.set_visible([self.channels[1].id],True)
        self.assertEqual(blank.ids,[self.channels[1].id])
        left,right=blank.getViewBox().viewRange()[0]
        self.assertLessEqual(left,self.x[0]);self.assertGreaterEqual(right,self.x[-1])


from PySide6 import QtGui


class CustomGraphDatasetUndoTests(unittest.TestCase):
    """Undo keeps later incompatible plots without collapsing user layouts."""
    @classmethod
    def setUpClass(cls):
        cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def scenario(self,populate_all):
        import os
        from unittest.mock import patch
        import pandas as pd
        from app_channel_store import Dataset
        from app_workbench import AdvancedStudioWindow
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{
                'ANALIZER_SETTINGS_DIR':directory+'/settings','ANALIZER_OUTPUT_DIR':directory+'/output'}):
            window=AdvancedStudioWindow()
            try:
                a=Dataset('Reference',pd.DataFrame({'value':[1,2]}),'synthetic-a')
                b=Dataset('Candidate',pd.DataFrame({'value':[3,4]}),'synthetic-b')
                window.store.datasets.update({a.id:a,b.id:b})
                source=window.store.add(Channel('Source',[0,1],[1,2],dataset_id=a.id,coordinate_unit='min'))
                other=window.store.add(Channel('Remaining',[0,1],[3,4],dataset_id=b.id,coordinate_unit='min'))
                workspace=window.dashboard;workspace.active.bind([source.id])
                for index in range(11):
                    graph=workspace.add_graph('right' if index==0 else 'below')
                    if populate_all or index==0:graph.bind([other.id])
                original_positions=workspace.positions()
                window.drop_recordings([a.id])
                # A later calculation legitimately uses frequency coordinates
                # in the now-empty original source graph.
                frequency=window.store.add(Channel('Calculated spectrum',[0,1],[5,6],dataset_id=b.id,
                    coordinate_kind='frequency',coordinate_unit='Hz',unit='W'))
                workspace.set_active(workspace.panes[0]);workspace.assign([frequency.id])
                window.undo_recording_removal();self.app.processEvents()
                self.assertEqual(workspace.layout_name,'Custom')
                self.assertEqual(workspace.positions()[:12],original_positions)
                self.assertEqual(workspace.visible_count(),13 if populate_all else 12)
                self.assertIn(source.id,workspace.panes[0].ids)
                self.assertNotIn(frequency.id,workspace.panes[0].ids)
                frequency_panes=[p for p in workspace.visible_panes() if frequency.id in p.ids]
                self.assertEqual(len(frequency_panes),1)
                self.assertEqual(frequency_panes[0].coordinate,('frequency','Hz'))
                self.assertIn(other.id,workspace.panes[1].ids)
                self.assertIsNone(window.removal_undo)
            finally:
                window.close();self.app.processEvents()

    def test_undo_uses_an_empty_custom_graph_without_collapsing_the_arrangement(self):
        self.scenario(False)

    def test_undo_adds_a_custom_graph_when_twelve_user_graphs_are_already_occupied(self):
        self.scenario(True)

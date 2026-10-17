"""Visible header modes and non-obstructing mouse readouts."""
import os
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PySide6 import QtWidgets,QtCore,QtTest
from app_channel_store import Channel
from app_workbench import AdvancedStudioWindow


class HeaderNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'ANALIZER_OUTPUT_DIR':self.temp.name});self.env.start()
        self.w=AdvancedStudioWindow();self.w.resize(1280,900);self.w.show();self.app.processEvents()
        self.c=self.w.store.add(Channel('Temperature',[0,1,2],[20,30,40],unit='°C',coordinate_unit='min'))
        self.w.dashboard.assign([self.c.id]);self.app.processEvents()
    def tearDown(self):self.w.close();self.app.processEvents();self.env.stop();self.temp.cleanup()
    def click(self,workspace,command):
        action=workspace.navigation_actions[command];button=workspace.navigation_bar.widgetForAction(action)
        self.assertTrue(button.isVisible());QtTest.QTest.mouseClick(button,QtCore.Qt.MouseButton.LeftButton);self.app.processEvents()

    def test_header_modes_remain_explicit_and_new_panes_inherit_constraints(self):
        ws=self.w.dashboard;ws.set_layout('Vertical split');ws.set_time_lock(False);self.app.processEvents()
        for command,enabled in [('x',(True,False)),('y',(False,True)),('xy',(True,True)),('pan',(True,True))]:
            self.click(ws,command);self.assertEqual(ws.navigation_mode,command)
            self.assertTrue(ws.navigation_actions[command].isChecked())
            self.assertEqual(sum(ws.navigation_actions[key].isChecked() for key in ('x','y','xy','pan')),1)
            for pane in ws.visible_panes():
                view=pane.getViewBox();self.assertEqual(tuple(view.state['mouseEnabled']),enabled)
                self.assertEqual(view.state['mouseMode'],view.PanMode if command=='pan' else view.RectMode)
        self.w.studio.navigation('y');ws.set_layout('3 stacked')
        self.assertTrue(ws.navigation_actions['y'].isChecked())
        self.assertTrue(all(tuple(p.getViewBox().state['mouseEnabled'])==(False,True) for p in ws.visible_panes()))

    def test_active_header_and_cursor_lock_survive_tab_switch_and_minimum_width(self):
        w=self.w;w.resize(1024,768);self.app.processEvents()
        for index,ws in enumerate(w.workspaces):
            w.tabs.setCurrentIndex(index);self.app.processEvents()
            bar=ws.navigation_bar;self.assertIs(bar.parentWidget(),w);self.assertTrue(bar.isVisible())
            self.assertFalse(w.workspaces[1-index].navigation_bar.isVisible())
            self.assertLess(bar.mapToGlobal(bar.rect().bottomLeft()).y(),ws.active.mapToGlobal(ws.active.rect().topLeft()).y())
            for command in ('x','y','xy','pan','reset'):
                self.assertTrue(bar.widgetForAction(ws.navigation_actions[command]).isVisible())
            lock=next(action for action in bar.actions() if action.text()=='Lock Cursors…')
            with patch.object(w.studio,'cursor_lock_dialog') as dialog:lock.trigger();dialog.assert_called_once()
        w.tabs.setCurrentIndex(0);w.dashboard.navigate('x');w.tabs.setCurrentIndex(1);w.comparison.navigate('y');w.tabs.setCurrentIndex(0)
        self.assertTrue(w.dashboard.navigation_actions['x'].isChecked());self.assertTrue(w.comparison.navigation_actions['y'].isChecked())

    def test_hover_strip_never_overlaps_canvas_and_does_not_resize_during_motion(self):
        ws=self.w.dashboard;p=ws.active;readout=ws.hover_readout
        label_bottom=readout.mapToGlobal(readout.rect().bottomLeft()).y();plot_top=p.mapToGlobal(p.rect().topLeft()).y()
        self.assertLess(label_bottom,plot_top);self.assertFalse(hasattr(p,'hover_label'))
        initial=p.geometry();before=[line.value() for line in p.cursor_lines]
        for fraction in (.1,.5,.9):
            rect=p.getViewBox().sceneBoundingRect();position=QtCore.QPointF(rect.left()+rect.width()*fraction,rect.center().y())
            p._mouse_hover((position,));self.app.processEvents()
            self.assertIn('Mouse X',readout.text());self.assertIn('Mouse Y',readout.text());self.assertIn('Temperature',readout.toolTip())
            self.assertEqual(p.geometry(),initial);self.assertEqual([line.value() for line in p.cursor_lines],before)
        self.w.resize(1024,768);self.app.processEvents()
        self.assertEqual(readout.height(),48);self.assertLess(readout.mapToGlobal(readout.rect().bottomLeft()).y(),p.mapToGlobal(p.rect().topLeft()).y())
        p.clear_hover();self.assertIn('Move over',readout.text());self.assertIsNone(ws._hover_pane)

    def test_hover_in_another_pane_is_not_cleared_by_unrelated_view(self):
        ws=self.w.dashboard;ws.set_layout('Vertical split');p,q=ws.visible_panes();q.bind([self.c.id]);self.app.processEvents()
        for pane in (p,q):pane._mouse_hover((pane.getViewBox().sceneBoundingRect().center(),))
        self.assertIs(ws._hover_pane,q);p.clear_hover();self.assertIs(ws._hover_pane,q)
        self.assertIn('Temperature',ws.hover_readout.toolTip());q.clear_hover();self.assertIsNone(ws._hover_pane)

    def test_navigation_mode_roundtrips_and_legacy_default_is_pan(self):
        ws=self.w.dashboard;ws.navigate('y');state=ws.state();ws.navigate('x');ws.restore(state)
        self.assertEqual(ws.navigation_mode,'y');self.assertTrue(ws.navigation_actions['y'].isChecked())
        self.assertEqual(tuple(ws.active.getViewBox().state['mouseEnabled']),(False,True))
        state.pop('navigation_mode');ws.restore(state);self.assertEqual(ws.navigation_mode,'pan')

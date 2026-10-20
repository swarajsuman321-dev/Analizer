"""Visible header modes and non-obstructing mouse readouts."""
import os
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PySide6 import QtWidgets,QtCore,QtTest,QtGui
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
        # Native fonts, DPI and visible dock widths determine how many actions
        # fit beside the tabs. Exercise the same accessible QAction through the
        # visible toolbar button or its real overflow menu, never a hidden click.
        bar=workspace.navigation_bar;action=workspace.navigation_actions[command];button=bar.widgetForAction(action)
        self.assertTrue(bar.isVisible());self.assertTrue(action.isEnabled())
        if button.isVisible():
            QtTest.QTest.mouseClick(button,QtCore.Qt.MouseButton.LeftButton)
            route='button'
        else:
            overflow=bar.findChild(QtWidgets.QToolButton,'qt_toolbar_ext_button')
            self.assertIsNotNone(overflow);self.assertTrue(overflow.isVisible(),command+' has no visible overflow access')
            selected=[];errors=[];attempts=[0]
            def choose():
                menu=self.app.activePopupWidget()
                if not isinstance(menu,QtWidgets.QMenu) or not menu.isVisible():
                    attempts[0]+=1
                    if attempts[0]<100:
                        QtCore.QTimer.singleShot(5,choose);return
                    errors.append(AssertionError('The visible toolbar overflow did not open its menu'))
                    return
                try:
                    self.assertIn(action,menu.actions(),command+' is absent from the overflow menu')
                    rectangle=menu.actionGeometry(action)
                    self.assertTrue(rectangle.isValid());self.assertTrue(menu.rect().contains(rectangle.center()))
                    self.assertTrue(action.isVisible());self.assertTrue(action.isEnabled())
                    QtTest.QTest.mouseClick(menu,QtCore.Qt.MouseButton.LeftButton,pos=rectangle.center())
                    selected.append(action)
                except Exception as error:errors.append(error)
                finally:menu.close()
            # Some Qt styles enter a nested menu loop while mouseClick is still
            # running. A queued menu interaction works with both native styles
            # and the nonblocking offscreen popup implementation.
            QtCore.QTimer.singleShot(0,choose)
            QtTest.QTest.mouseClick(overflow,QtCore.Qt.MouseButton.LeftButton)
            for _ in range(100):
                if selected or errors:break
                QtTest.QTest.qWait(5)
            if errors:raise errors[0]
            self.assertEqual(selected,[action],command+' was not selected from the visible menu')
            route='overflow'
        self.app.processEvents();return route

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
            header=w.tabs.cornerWidget(QtCore.Qt.Corner.TopRightCorner)
            bar=ws.navigation_bar;self.assertIs(bar.parentWidget(),header);self.assertTrue(bar.isVisible())
            self.assertFalse(w.workspaces[1-index].navigation_bar.isVisible())
            self.assertLess(bar.mapToGlobal(bar.rect().bottomLeft()).y(),ws.active.mapToGlobal(ws.active.rect().topLeft()).y())
            overflow=bar.findChild(QtWidgets.QToolButton,'qt_toolbar_ext_button')
            for command in ('x','y','xy','pan','reset'):
                button=bar.widgetForAction(ws.navigation_actions[command])
                self.assertTrue(button.isVisible() or (overflow is not None and overflow.isVisible()),command+' must be visible or reachable through overflow')
            lock=next(action for action in bar.actions() if action.text()=='Lock Cursors…')
            with patch.object(w.studio,'cursor_lock_dialog') as dialog:lock.trigger();dialog.assert_called_once()
        w.tabs.setCurrentIndex(0);w.dashboard.navigate('x');w.tabs.setCurrentIndex(1);w.comparison.navigate('y');w.tabs.setCurrentIndex(0)
        self.assertTrue(w.dashboard.navigation_actions['x'].isChecked());self.assertTrue(w.comparison.navigation_actions['y'].isChecked())

    def test_hover_strip_never_overlaps_canvas_and_does_not_resize_during_motion(self):
        ws=self.w.dashboard;p=ws.active;readout=ws.hover_readout
        # Native window exposure and axis sizing finish asynchronously. Exercise
        # the real pointer/proxy path after that settles, rather than injecting
        # hover while the physical pointer is outside and a Leave is queued.
        self.w.activateWindow();self.w.raise_();p.setFocus()
        QtTest.QTest.qWait(150)
        QtTest.QTest.mouseMove(p.viewport(),QtCore.QPoint(0,0));QtTest.QTest.qWait(60)
        label_bottom=readout.mapToGlobal(readout.rect().bottomLeft()).y();plot_top=p.mapToGlobal(p.rect().topLeft()).y()
        self.assertLess(label_bottom,plot_top);self.assertFalse(hasattr(p,'hover_label'))
        initial=p.geometry();before=[line.value() for line in p.cursor_lines]
        # The requested window can exceed a small/DPI-scaled CI desktop. Native
        # pointer movement is clipped to that desktop, so sample visible data
        # within its intersection instead of asking for an offscreen position.
        view=p.getViewBox();drawable=p.mapFromScene(view.sceneBoundingRect()).boundingRect()
        visible=QtCore.QRect(p.viewport().mapToGlobal(drawable.topLeft()),drawable.size()).intersected(self.w.screen().availableGeometry()).adjusted(2,2,-2,-2)
        first=p.viewport().mapToGlobal(p.mapFromScene(view.mapViewToScene(QtCore.QPointF(0,20))))
        last=p.viewport().mapToGlobal(p.mapFromScene(view.mapViewToScene(QtCore.QPointF(2,40))))
        visible.setLeft(max(visible.left(),first.x()+2));visible.setRight(min(visible.right(),last.x()-2))
        self.assertGreater(visible.width(),6);self.assertGreater(visible.height(),6)
        moves=QtTest.QSignalSpy(p.scene().sigMouseMoved)
        changes=QtTest.QSignalSpy(p.hoverChanged)
        for fraction in (.1,.5,.9):
            position=QtCore.QPoint(round(visible.left()+visible.width()*fraction),visible.center().y())
            QtTest.QTest.mouseMove(p.viewport(),p.viewport().mapFromGlobal(position))
            QtTest.QTest.qWait(80)  # Passive hover is deliberately limited to 30 Hz.
            owner=self.app.widgetAt(QtGui.QCursor.pos());popup=self.app.activePopupWidget()
            diagnostic=f'active={self.w.isActiveWindow()}, underMouse={p.viewport().underMouse()}, pointer={QtGui.QCursor.pos()}, target={position}, owner={owner}, popup={popup}, moves={moves.count()}, changes={changes.count()}, hover={p.hover_state}, raw={p.hover_text}, range={p.viewRange()}'
            self.assertRegex(readout.text().splitlines()[0],r'(?:Mouse )?X .*\b(?:Mouse )?Y ',diagnostic);self.assertIn('°C',readout.text().splitlines()[0]);self.assertIn('Mouse X',readout.toolTip());self.assertIn('Mouse Y',readout.toolTip());self.assertIn('Temperature',readout.toolTip())
            self.assertEqual(p.geometry(),initial);self.assertEqual([line.value() for line in p.cursor_lines],before)
        self.w.resize(1024,768);self.app.processEvents()
        self.assertEqual(readout.height(),48);self.assertLess(readout.mapToGlobal(readout.rect().bottomLeft()).y(),p.mapToGlobal(p.rect().topLeft()).y())
        p.clear_hover();self.assertIn('Move over',readout.text());self.assertIsNone(ws._hover_pane)

    def test_live_hover_uses_current_owned_pointer_and_rejects_late_or_obscured_motion(self):
        p=self.w.dashboard.active;view=p.getViewBox();viewport=p.viewport()
        actual=view.mapViewToScene(QtCore.QPointF(.5,25));stale=view.mapViewToScene(QtCore.QPointF(1.5,35))
        local=p.mapFromScene(actual);position=viewport.mapToGlobal(local)
        with patch.object(viewport,'underMouse',return_value=False),patch.object(QtGui.QCursor,'pos',return_value=position),patch.object(QtWidgets.QApplication,'widgetAt',return_value=viewport):
            p._live_hover((stale,))
            self.assertIsNotNone(p.hover_state)
            self.assertAlmostEqual(p.hover_state['x'],view.mapSceneToView(p.mapToScene(local)).x())
            self.assertLess(p.hover_state['x'],1)
        # A queued old scene point must not bring the hover back after Leave,
        # or display data through another widget that now covers the pointer.
        outside=viewport.mapToGlobal(QtCore.QPoint(-10,-10))
        with patch.object(QtGui.QCursor,'pos',return_value=outside),patch.object(QtWidgets.QApplication,'widgetAt',return_value=viewport):
            p._live_hover((actual,));self.assertIsNone(p.hover_state)
        with patch.object(QtGui.QCursor,'pos',return_value=position),patch.object(QtWidgets.QApplication,'widgetAt',return_value=self.w.tabs):
            p._live_hover((actual,));self.assertIsNone(p.hover_state)

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

    def test_quick_zoom_shares_actions_and_respects_axis_mode(self):
        ws=self.w.dashboard;ws.set_layout('Vertical split');p,q=ws.visible_panes();q.bind([self.c.id]);ws.link();self.app.processEvents()
        self.assertFalse(hasattr(ws,'quick_zoom_bar'))
        ws.navigate('x');self.assertTrue(ws.navigation_actions['x'].isChecked())
        beforex=np.diff(p.viewRange()[0])[0];beforey=[list(pane.viewRange()[1]) for pane in (p,q)]
        self.click(ws,'in')
        self.assertAlmostEqual(np.diff(p.viewRange()[0])[0]/beforex,.8)
        np.testing.assert_allclose(p.viewRange()[0],q.viewRange()[0])
        for pane,expected in zip((p,q),beforey):np.testing.assert_allclose(pane.viewRange()[1],expected)
        self.click(ws,'out')
        self.assertAlmostEqual(np.diff(p.viewRange()[0])[0],beforex)
        self.click(ws,'reset')
        self.assertLessEqual(p.viewRange()[0][0],0);self.assertGreaterEqual(p.viewRange()[0][1],2)
        ws.navigation_actions['y'].trigger();self.assertTrue(ws.navigation_actions['y'].isChecked())

    def test_narrow_header_overflow_activates_the_shared_navigation_actions(self):
        ws=self.w.dashboard;bar=ws.navigation_bar
        self.w.tabs.cornerWidget(QtCore.Qt.Corner.TopRightCorner).setFixedWidth(80)
        self.app.processEvents()
        self.assertFalse(bar.widgetForAction(ws.navigation_actions['in']).isVisible())
        before=np.diff(ws.active.viewRange()[0])[0]
        ws.navigate('x')
        self.assertEqual(self.click(ws,'in'),'overflow')
        self.assertAlmostEqual(np.diff(ws.active.viewRange()[0])[0]/before,.8)
        self.assertEqual(self.click(ws,'y'),'overflow')
        self.assertEqual(ws.navigation_mode,'y');self.assertTrue(ws.navigation_actions['y'].isChecked())

    def test_only_primary_navigation_is_visible_and_icons_are_accessible(self):
        w=self.w
        for index,ws in enumerate(w.workspaces):
            w.tabs.setCurrentIndex(index);self.app.processEvents()
            header=w.tabs.cornerWidget(QtCore.Qt.Corner.TopRightCorner)
            self.assertIsNotNone(header);self.assertIs(ws.navigation_bar.parentWidget(),header)
            self.assertFalse(hasattr(ws,'quick_zoom_bar'))
            for key in ('in','out','reset','pan'):
                action=ws.navigation_actions[key];self.assertFalse(action.icon().isNull());self.assertTrue(action.toolTip())
                self.assertEqual(ws.navigation_bar.widgetForAction(action).accessibleName(),action.text())
            self.assertFalse(w.workspaces[1-index].navigation_bar.isVisible())

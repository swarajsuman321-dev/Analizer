"""Keep the app's chart controls without allocating hidden framework menus."""
import gc
import importlib
import unittest
from unittest.mock import patch

import numpy as np
from PySide6 import QtCore, QtTest, QtWidgets

from app_channel_store import Channel, ChannelStore
from app_plot_workspace import PlotWorkspace


class ChartMenuLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make_store(self):
        store=ChannelStore()
        for name,unit in [('Temperature','°C'),('Power','W')]:
            store.add(Channel(name,np.arange(11.),np.arange(11.)+10,unit=unit,coordinate_unit='min'))
        return store

    def test_repeated_multi_axis_restore_never_constructs_hidden_viewbox_menu(self):
        framework=importlib.import_module('pyqtgraph.graphicsItems.ViewBox.ViewBox')
        store=self.make_store();work=None
        with patch.object(framework,'ViewBoxMenu',side_effect=AssertionError('Unexpected hidden framework menu')):
            try:
                work=PlotWorkspace(store);work.resize(1200,900);work.show();work.set_layout('2×2')
                for pane in work.visible_panes():pane.bind(list(store.channels))
                work.active.cursor_lines[0].setValue(2);work.active.cursor_lines[1].setValue(8)
                work.active.setXRange(1,9,padding=0)
                for _ in range(8):
                    saved=work.state();work.restore(saved)
                    gc.collect()
                    QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.Type.DeferredDelete)
                    self.app.processEvents()
                    for pane in work.visible_panes():
                        self.assertIsNone(pane.getViewBox().menu)
                        self.assertTrue(all(view.menu is None for _,view in pane.axes.values()))
                        np.testing.assert_allclose(pane.getViewBox().viewRange()[0],[1,9])
                        self.assertEqual([line.value() for line in pane.cursor_lines],[2,8])
            finally:
                if work is not None:work.close();work.deleteLater()
                QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.Type.DeferredDelete)
                self.app.processEvents()

    def test_real_right_click_retains_app_menu_without_native_menu(self):
        store=self.make_store();work=PlotWorkspace(store);work.resize(1100,700);work.show()
        try:
            work.assign(list(store.channels));self.app.processEvents()
            pane=work.active
            position=pane.mapFromScene(pane.getViewBox().sceneBoundingRect().center())
            QtTest.QTest.mouseClick(pane.viewport(),QtCore.Qt.MouseButton.RightButton,pos=position)
            self.app.processEvents()
            menu=pane._context_menu
            self.assertTrue(menu.isVisible())
            self.assertEqual(menu.objectName(),'paneChartMenu')
            labels=[action.text() for action in menu.actions()]
            self.assertIn('Full Screen Graph',labels)
            self.assertIn('Arrange Graphs',labels)
            self.assertIn('Add Graph Channels to Comparison',labels)
            self.assertIsNone(pane.getViewBox().menu)
            menu.close()
        finally:
            work.close();work.deleteLater()
            QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.Type.DeferredDelete)
            self.app.processEvents()

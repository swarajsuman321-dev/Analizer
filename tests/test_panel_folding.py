"""Native panel folds preserve workspace content and saved dock layouts."""
import json
import unittest
from PySide6 import QtCore, QtWidgets, QtTest
from app_panel_folding import PanelFoldingControls


class PanelFoldingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.window = QtWidgets.QMainWindow()
        self.window.resize(1280, 850)
        self.graph = QtWidgets.QLabel('Active graph')
        self.graph.setMinimumSize(250, 200)
        self.window.setCentralWidget(self.graph)
        self.window.docks = {}
        for name, area in (
                ('Properties', QtCore.Qt.DockWidgetArea.RightDockWidgetArea),
                ('Channel Math', QtCore.Qt.DockWidgetArea.RightDockWidgetArea),
                ('Data Portal', QtCore.Qt.DockWidgetArea.LeftDockWidgetArea),
                ('Engineering Controls', QtCore.Qt.DockWidgetArea.LeftDockWidgetArea),
                ('Readout', QtCore.Qt.DockWidgetArea.BottomDockWidgetArea),
                ('Channel Table', QtCore.Qt.DockWidgetArea.BottomDockWidgetArea),
                ('Interval Measurements', QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)):
            dock = QtWidgets.QDockWidget(name, self.window)
            dock.setObjectName(name)
            content = QtWidgets.QTableWidget(1, 1)
            content.setItem(0, 0, QtWidgets.QTableWidgetItem(name + ' source value'))
            content.setMinimumSize(180, 70)
            dock.setWidget(content)
            self.window.addDockWidget(area, dock)
            self.window.docks[name] = dock
        for first, second in (('Properties', 'Channel Math'), ('Data Portal', 'Engineering Controls'),
                              ('Readout', 'Channel Table'), ('Readout', 'Interval Measurements')):
            self.window.tabifyDockWidget(self.window.docks[first], self.window.docks[second])
        self.window.docks['Properties'].raise_()
        self.window.docks['Engineering Controls'].raise_()
        self.window.docks['Readout'].raise_()
        self.controls = PanelFoldingControls(self.window)
        toolbar = self.window.addToolBar('Panels')
        toolbar.setObjectName('testPanelsToolbar')
        toolbar.addWidget(self.controls.button)
        self.window.show()
        self.pump()

    def tearDown(self):
        self.window.close()
        self.pump()
        self.window.deleteLater()
        self.pump()

    def pump(self):
        self.app.processEvents()
        QtTest.QTest.qWait(10)
        self.app.processEvents()

    def test_properties_only_does_not_hide_tabbed_math_or_readout(self):
        self.controls.apply_defaults(['Properties'])
        self.pump()
        self.assertTrue(self.controls.is_folded('Properties'))
        for name in ('Channel Math', 'Engineering Controls', 'Readout'):
            self.assertFalse(self.controls.is_folded(name), name)
        self.assertTrue(self.controls.button.isVisible())
        self.assertIn('Expand', self.controls.actions['Properties'].text())
        self.assertTrue(self.controls.button.accessibleName())

    def test_authorized_right_group_fold_gains_graph_width_and_keeps_readout(self):
        before = self.graph.width()
        readout = self.window.docks['Readout'].widget()
        readout.item(0, 0).setText('Cursor A 12.5 min: 42 °C; Cursor B 18.5 min: 48 °C')
        cursor_text = readout.item(0, 0).text()
        self.controls.apply_defaults(['Properties', 'Channel Math', 'Channel Table', 'Interval Measurements'])
        self.pump()
        self.assertGreater(self.graph.width(), before + 100)
        for name in ('Engineering Controls', 'Readout'):
            self.assertFalse(self.controls.is_folded(name))
            self.assertTrue(self.window.docks[name].isVisible(), name)
        for name in ('Properties', 'Channel Math', 'Channel Table', 'Interval Measurements'):
            self.assertTrue(self.controls.is_folded(name))
        self.assertIs(self.window.docks['Readout'].widget(), readout)
        self.assertEqual(readout.item(0, 0).text(), cursor_text)

    def test_dropdown_and_native_view_action_agree_without_replacing_data(self):
        dock = self.window.docks['Properties']
        widget = dock.widget()
        item = widget.item(0, 0)
        dock.raise_()
        self.controls.set_folded('Properties', True)
        self.pump()
        self.assertFalse(dock.toggleViewAction().isChecked())
        self.assertFalse(self.controls.actions['Properties'].isChecked())
        self.controls.actions['Properties'].trigger()
        self.pump()
        self.assertFalse(self.controls.is_folded('Properties'))
        self.assertTrue(dock.toggleViewAction().isChecked())
        self.assertIs(dock.widget(), widget)
        self.assertIs(widget.item(0, 0), item)
        self.assertEqual(item.text(), 'Properties source value')
        dock.close()
        self.pump()
        self.assertTrue(self.controls.is_folded('Properties'))
        self.assertFalse(self.controls.actions['Properties'].isChecked())
        dock.toggleViewAction().trigger()
        self.pump()
        self.assertTrue(self.controls.actions['Properties'].isChecked())

    def test_inactive_tabs_are_open_and_show_all_clears_folds(self):
        self.window.docks['Channel Math'].raise_()
        self.pump()
        self.assertFalse(self.controls.is_folded('Properties'))
        self.assertTrue(self.controls.actions['Properties'].isChecked())
        self.controls.apply_defaults(['Properties', 'Channel Math'])
        for dock in self.window.docks.values():
            dock.show()
        self.window.docks['Engineering Controls'].raise_()
        self.window.docks['Readout'].raise_()
        self.pump()
        self.assertTrue(all(action.isChecked() for action in self.controls.actions.values()))

    def test_size_and_floating_state_survive_fold_unfold(self):
        dock = self.window.docks['Properties']
        dock.setFloating(True)
        dock.resize(360, 280)
        self.pump()
        before = dock.size()
        position = dock.pos()
        floating_widget = dock.widget()
        self.controls.set_folded('Properties', True)
        self.window.resize(1100, 720)
        self.pump()
        self.controls.toggle('Properties')
        self.pump()
        self.assertTrue(dock.isFloating())
        self.assertEqual(dock.size(), before)
        self.assertEqual(dock.pos(), position)
        self.assertIs(dock.widget(), floating_widget)

    def test_docked_width_is_recovered_after_the_whole_group_was_folded(self):
        dock = self.window.docks['Properties']
        self.window.resizeDocks([dock], [300], QtCore.Qt.Orientation.Horizontal)
        self.pump()
        before = dock.width()
        self.controls.apply_defaults(['Properties', 'Channel Math'])
        self.pump()
        self.controls.set_folded('Properties', False)
        self.pump()
        self.assertFalse(dock.isFloating())
        self.assertAlmostEqual(dock.width(), before, delta=4)

    def test_native_saved_and_legacy_layouts_keep_their_explicit_visibility(self):
        self.controls.set_folded('Properties', False)
        self.controls.set_folded('Channel Math', True)
        saved_native = self.window.saveState()
        saved_folding = json.loads(json.dumps(self.controls.state()))
        self.controls.apply_defaults(['Properties', 'Channel Math', 'Channel Table', 'Interval Measurements'])
        self.assertTrue(self.window.restoreState(saved_native))
        self.assertTrue(self.controls.restore(saved_folding))
        self.pump()
        self.assertFalse(self.controls.is_folded('Properties'))
        self.assertTrue(self.controls.is_folded('Channel Math'))
        # Old workspaces have native dock data without any folding metadata.
        self.controls.apply_defaults(['Properties'])
        self.assertTrue(self.window.restoreState(saved_native))
        self.assertFalse(self.controls.restore(None))
        self.pump()
        self.assertFalse(self.controls.is_folded('Properties'))
        self.assertTrue(self.controls.is_folded('Channel Math'))

    def test_folding_restore_preserves_native_selected_tabs(self):
        def selected_tabs():
            return {frozenset(bar.tabText(index) for index in range(bar.count())):
                    bar.tabText(bar.currentIndex())
                    for bar in self.window.findChildren(QtWidgets.QTabBar)
                    if bar.count() > 1}

        # Each selected tab comes before another open panel in the saved
        # folding record. Iterating over open panels must not select the last.
        for name in ('Properties', 'Data Portal', 'Readout'):
            self.window.docks[name].raise_()
        self.pump()
        selected = selected_tabs()
        self.assertEqual(set(selected.values()), {'Properties', 'Data Portal', 'Readout'})
        saved_native = self.window.saveState()
        saved_folding = json.loads(json.dumps(self.controls.state()))
        for name in ('Channel Math', 'Engineering Controls', 'Interval Measurements'):
            self.window.docks[name].raise_()
        self.pump()
        self.assertNotEqual(selected_tabs(), selected)
        self.assertTrue(self.window.restoreState(saved_native))
        self.pump()
        self.assertEqual(selected_tabs(), selected)
        self.assertTrue(self.controls.restore(saved_folding))
        self.pump()
        self.assertEqual(selected_tabs(), selected)
        # Folding metadata may also need to reopen a tab. That must leave the
        # native selected neighbour active instead of raising the reopened tab.
        self.controls.set_folded('Channel Math', True)
        self.pump()
        self.assertTrue(self.controls.restore({'schema': 1, 'panels': {
            'Channel Math': {'folded': False}}}))
        self.pump()
        self.assertEqual(selected_tabs(), selected)

    def test_invalid_or_unknown_saved_panels_do_not_hide_other_features(self):
        before = {name: self.controls.is_folded(name) for name in self.window.docks}
        self.assertFalse(self.controls.restore({'schema': 99, 'panels': {'Readout': {'folded': True}}}))
        self.assertTrue(self.controls.restore({'schema': 1, 'panels': {
            'Removed future panel': {'folded': True}, 'Readout': {'folded': 'yes'}}}))
        self.assertEqual(before, {name: self.controls.is_folded(name) for name in self.window.docks})
        with self.assertRaises(KeyError):
            self.controls.apply_defaults(['Properties', 'Unknown panel'])
        self.assertFalse(self.controls.is_folded('Properties'))


if __name__ == '__main__':
    unittest.main()

"""A recording's sample plots keep one X view through real navigation gestures."""
import unittest

import numpy as np
import pandas as pd
from PySide6 import QtCore, QtGui, QtTest, QtWidgets

from app_channel_store import Channel, ChannelStore, Dataset
from app_plot_workspace import PlotWorkspace


class AlignedSampleNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.store = ChannelStore()
        self.recording = Dataset('Same recording', pd.DataFrame())
        self.other = Dataset('Unrelated recording', pd.DataFrame())
        self.store.datasets.update({d.id: d for d in (self.recording, self.other)})
        self.long = self.channel('Speed', 101, 'RPM', self.recording)
        self.secondary = self.channel('Pressure', 101, 'Pa', self.recording)
        self.short = self.channel('Valve', 31, 'V', self.recording)
        self.unrelated = self.channel('Other run', 101, 'W', self.other)
        self.work = PlotWorkspace(self.store)
        self.work.resize(1200, 1100)
        self.work.set_layout('3 stacked')
        self.work.show()
        self.p, self.q, self.r = self.work.visible_panes()
        self.p.bind([self.long.id, self.secondary.id])
        self.q.bind([self.short.id])
        self.r.bind([self.unrelated.id])
        self.work.link()
        self.work.set_time_lock(False)
        self.app.processEvents()

    def channel(self, name, length, unit, dataset):
        x = np.arange(length, dtype=float)
        return self.store.add(Channel(name, x, x + 10, unit=unit,
            coordinate_kind='sample', coordinate_unit='sample', dataset_id=dataset.id))

    def tearDown(self):
        self.work.close()
        self.work.deleteLater()
        self.app.processEvents()
        QtCore.QCoreApplication.sendPostedEvents(None, QtCore.QEvent.Type.DeferredDelete)

    def cursors(self, pane):
        return [line.value() for line in pane.cursor_lines]

    def test_sample_pan_and_zoom_preserve_shared_cursors_and_original_data(self):
        original = [c.x.copy() for c in (self.long, self.short)]
        self.p.cursor_lines[0].setValue(60)
        self.p.cursor_lines[1].setValue(90)
        unrelated = self.r.viewRange()[0]
        for source, bounds in ((self.p, [10, 70]), (self.q, [40, 80])):
            source.setXRange(*bounds, padding=0)
            self.app.processEvents()
            for pane in (self.p, self.q):
                np.testing.assert_allclose(pane.viewRange()[0], bounds)
                self.assertEqual(self.cursors(pane), [60, 90])
            np.testing.assert_allclose(self.r.viewRange()[0], unrelated)
        self.work.set_active(self.q)
        self.work.navigate('x')
        before = np.diff(self.q.viewRange()[0])[0]
        self.work.navigate('in')
        np.testing.assert_allclose(self.p.viewRange()[0], self.q.viewRange()[0])
        self.assertAlmostEqual(np.diff(self.p.viewRange()[0])[0], before * .8)
        self.assertTrue(np.isnan(self.q.measurements()[self.short.id]['A']))
        for channel, expected in zip((self.long, self.short), original):
            np.testing.assert_array_equal(channel.x, expected)
            self.assertEqual(channel.shift, 0)

    def test_real_horizontal_drag_from_either_pane_moves_the_aligned_group_only(self):
        self.work.navigate('pan')
        self.p.cursor_lines[0].setValue(20)
        self.p.cursor_lines[1].setValue(80)
        self.work.activateWindow()
        QtTest.QTest.qWait(60)
        for pane in (self.p, self.q):
            with self.subTest(source=pane.ids):
                self.p.setXRange(0, 100, padding=0)
                view = pane.getViewBox()
                view.setMouseEnabled(x=True, y=False)
                region = pane.mapFromScene(view.sceneBoundingRect()).boundingRect()
                region = region.intersected(pane.viewport().visibleRegion().boundingRect())
                start = region.center()
                end = start + QtCore.QPoint(60, 0)
                self.assertTrue(region.contains(end))
                before = list(view.viewRange()[0])
                y_ranges = [[list(v.viewRange()[1]) for v in p.y_views()] for p in (self.p, self.q)]
                unrelated = list(self.r.viewRange()[0])
                QtTest.QTest.mouseMove(pane.viewport(), start)
                QtTest.QTest.mousePress(pane.viewport(), QtCore.Qt.MouseButton.MiddleButton, pos=start)
                for point in (start + QtCore.QPoint(30, 0), end):
                    event = QtGui.QMouseEvent(QtCore.QEvent.Type.MouseMove,
                        QtCore.QPointF(point), QtCore.QPointF(pane.viewport().mapToGlobal(point)),
                        QtCore.Qt.MouseButton.NoButton, QtCore.Qt.MouseButton.MiddleButton,
                        QtCore.Qt.KeyboardModifier.NoModifier)
                    QtWidgets.QApplication.sendEvent(pane.viewport(), event)
                    self.app.processEvents()
                QtTest.QTest.mouseRelease(pane.viewport(), QtCore.Qt.MouseButton.MiddleButton, pos=end)
                self.app.processEvents()
                self.assertGreater(abs(view.viewRange()[0][0] - before[0]), 1)
                np.testing.assert_allclose(self.p.viewRange()[0], self.q.viewRange()[0])
                np.testing.assert_allclose(self.r.viewRange()[0], unrelated)
                for target, expected in zip((self.p, self.q), y_ranges):
                    self.assertEqual(self.cursors(target), [20, 80])
                    for axis, bounds in zip(target.y_views(), expected):
                        np.testing.assert_allclose(axis.viewRange()[1], bounds)

    def test_unrelated_sample_runs_and_frequency_stay_independent_even_with_time_lock(self):
        self.work.set_time_lock(True)
        other_cursors = self.cursors(self.r)
        other_bounds = list(self.r.viewRange()[0])
        self.p.cursor_lines[0].setValue(70)
        self.assertEqual(self.cursors(self.r), other_cursors)
        self.q.setXRange(40, 90, padding=0)
        np.testing.assert_allclose(self.p.viewRange()[0], [40, 90])
        np.testing.assert_allclose(self.r.viewRange()[0], other_bounds)
        self.assertEqual(self.cursors(self.r), other_cursors)
        spectrum = self.store.add(Channel('Spectrum', np.arange(11.), np.arange(11.),
            coordinate_kind='frequency', coordinate_unit='Hz', dataset_id=self.recording.id))
        self.r.bind([spectrum.id])
        frequency_range = list(self.r.viewRange()[0])
        self.p.setXRange(10, 50, padding=0)
        np.testing.assert_allclose(self.r.viewRange()[0], frequency_range)

    def test_three_aligned_graphs_share_numeric_ranges_and_cursor_screen_positions(self):
        self.r.bind([self.long.id])
        self.q.setXRange(10, 95, padding=0)
        self.p.cursor_lines[0].setValue(60)
        self.p.cursor_lines[1].setValue(90)
        for _ in range(10):
            self.app.processEvents()
            self.work.grab()
            QtTest.QTest.qWait(15)
        pixels = [[], []]
        for pane in (self.p, self.q, self.r):
            np.testing.assert_allclose(pane.viewRange()[0], [10, 95])
            self.assertEqual(self.cursors(pane), [60, 90])
            for index, point in enumerate((60, 90)):
                scene = pane.getViewBox().mapViewToScene(QtCore.QPointF(point, 0))
                local = pane.viewportTransform().map(scene)
                pixels[index].append(pane.viewport().mapToGlobal(QtCore.QPoint()).x() + local.x())
        for positions in pixels:
            np.testing.assert_allclose(positions, positions[0], rtol=0, atol=.5)

    def test_restore_and_short_trace_fit_keep_one_sample_range_and_cursor_pair(self):
        state = self.work.state()
        state['active'] = 0
        state['panes'][0]['cursors'] = [60., 90.]
        state['panes'][1]['cursors'] = [3., 6.]
        self.work.restore(state)
        self.p, self.q, self.r = self.work.visible_panes()
        self.app.processEvents()
        for pane in (self.p, self.q):
            self.assertEqual(self.cursors(pane), [60, 90])
        self.work.set_active(self.q)
        self.work.navigate('reset')
        np.testing.assert_allclose(self.p.viewRange()[0], self.q.viewRange()[0])
        self.assertGreaterEqual(self.q.viewRange()[0][1], 100)


if __name__ == '__main__':
    unittest.main()

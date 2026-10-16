import json
import tempfile
import unittest
from pathlib import Path
from PySide6 import QtWidgets,QtGui
from app_workbench import AdvancedStudioWindow
from app_workspace_io import save_workspace
from app_version import VERSION


class ManualAndViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def setUp(self):self.window=AdvancedStudioWindow();self.window.show();self.app.processEvents()
    def tearDown(self):self.window.close();self.app.processEvents()

    def test_top_toolbar_opens_manual_without_changing_analysis(self):
        w=self.window
        self.assertEqual([w.tabs.tabText(i) for i in range(w.tabs.count())],['Analysis','Comparison'])
        toolbar=next(t for t in w.findChildren(QtWidgets.QToolBar) if t.objectName()=='Workbench')
        self.assertIn(w.info_action,toolbar.actions());w.tabs.setCurrentIndex(1);w.info_action.trigger();self.app.processEvents()
        self.assertTrue(w.info_dialog.isVisible());self.assertIs(w.active_workspace,w.comparison)
        self.assertEqual(w.info.parentWidget(),w.info_dialog)
        w.info_dialog.close();self.assertTrue(w.isVisible());self.assertEqual(w.tabs.currentIndex(),1)
        w.info_action.trigger();self.assertTrue(w.info_dialog.isVisible())

    def test_every_view_panel_enabled_by_default_and_saved_layout_wins(self):
        w=self.window
        self.assertTrue(all(d.toggleViewAction().isChecked() for d in w.docks.values()))
        self.assertFalse(w.portal.tree.isColumnHidden(2))
        w.docks['Properties'].toggleViewAction().trigger();w.channel_kind_action.setChecked(False);self.app.processEvents()
        self.assertTrue(w.docks['Properties'].isHidden())
        with tempfile.TemporaryDirectory() as directory:
            saved=save_workspace(Path(directory)/'layout.json',w.store,[p.state() for p in w.workspaces],w.ui_state())
            w.docks['Properties'].show();w.restore_path(saved);self.app.processEvents()
            self.assertTrue(w.docks['Properties'].isHidden());self.assertTrue(w.portal.tree.isColumnHidden(2))
            record=json.loads(saved.read_text());record['ui'].pop('app_version');saved.write_text(json.dumps(record))
            w.restore_path(saved,upgrade_defaults=True);self.app.processEvents()
            self.assertTrue(all(d.toggleViewAction().isChecked() for d in w.docks.values()));self.assertFalse(w.portal.tree.isColumnHidden(2))

    def test_manual_topic_navigation_search_wrap_and_no_match(self):
        w=self.window;w.show_info();info=w.info;self.app.processEvents()
        index=info.topics.findText('Butterworth low-pass');self.assertGreaterEqual(index,0);info.topics.setCurrentIndex(index)
        self.assertEqual(info.manual.textCursor().block().text(),'Butterworth low-pass')
        info.search.setText('MissingManualTerm_98765');info.find_manual()
        # A missing term does not discard the current reading position.
        self.assertIn('No matches',info.search_status.text())
        info.search.setText('Cutoff');info.find_manual();self.assertEqual(info.manual.textCursor().selectedText().lower(),'cutoff')
        info.manual.moveCursor(QtGui.QTextCursor.MoveOperation.End);info.find_manual();self.assertEqual(info.manual.textCursor().selectedText().lower(),'cutoff')
        before=info.manual.textCursor().position();info.search.setText('NoSuchFeature_12345');info.find_manual();self.assertEqual(info.manual.textCursor().position(),before)

    def test_version_manuals_cover_features_without_future_features(self):
        info=self.window.info
        required=['View menu and panel layout','Channel presets','Extensions','Comparison mapping and match colours','Resampling','FFT','Welch PSD','Cumulative integration','Save and restore workspace','TDMS recordings','Info toolbar, version manuals and search']
        current=info.manuals[VERSION].read_text(encoding='utf-8')
        from app_workbench import OPERATIONS
        for topic in required+OPERATIONS:self.assertIn('## '+topic,current)
        for name in self.window.docks:self.assertIn(name,current)
        old=info.manuals['2.1.0'].read_text(encoding='utf-8')
        self.assertIn('## Channel presets',old);self.assertNotIn('## TDMS recordings',old);self.assertNotIn('## Actuator interpretation',old)
        self.assertNotIn('## Info toolbar',info.manuals['2.1.6'].read_text(encoding='utf-8'))
        info.versions.setCurrentText('2.1.4');self.assertGreaterEqual(info.topics.findText('Actuator interpretation and ON duration'),0);self.assertEqual(info.topics.findText('TDMS recordings'),-1)

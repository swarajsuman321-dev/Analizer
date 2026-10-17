"""User-visible isolation, navigation, legacy restore and cleanup invariants."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from PySide6 import QtCore,QtWidgets,QtGui,QtTest
from app_channel_store import Dataset,Channel
from app_workbench import AdvancedStudioWindow
from app_workspace_io import save_workspace
from app_config_migration import read_configuration,migrate_configuration
from app_lifecycle import migrate_user_files,cleanup_inventory,settings_directory,digest,PRODUCT


class DesktopFinalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'ANALIZER_OUTPUT_DIR':self.temp.name});self.env.start()
        self.w=AdvancedStudioWindow();self.w.resize(1500,1000);self.w.show();self.app.processEvents()
    def tearDown(self):self.w.close();self.app.processEvents();self.env.stop();self.temp.cleanup()
    def add_file(self,name,unit='°C'):
        ds=Dataset(name,pd.DataFrame({'Sensor':[1,2,3]}));self.w.store.datasets[ds.id]=ds
        with self.w.store.batch():
            a=self.w.store.add(Channel('Sensor',np.arange(11.),np.arange(11.),unit=unit,coordinate_unit='min',dataset_id=ds.id))
            b=self.w.store.add(Channel('Other',np.arange(11.),np.arange(11.)*2,unit=unit,coordinate_unit='min',dataset_id=ds.id))
        return ds,[a.id,b.id]
    def click_check(self,item):
        tree=self.w.portal.tree;tree.scrollToItem(item);self.app.processEvents();index=tree.indexFromItem(item)
        option=QtWidgets.QStyleOptionViewItem();option.initFrom(tree);tree.itemDelegate().initStyleOption(option,index);option.rect=tree.visualRect(index)
        rect=tree.style().subElementRect(QtWidgets.QStyle.SubElement.SE_ItemViewItemCheckIndicator,option,tree)
        self.assertTrue(option.rect.contains(rect));QtTest.QTest.mouseClick(tree.viewport(),QtCore.Qt.MouseButton.LeftButton,pos=rect.center());self.app.processEvents()
    def test_engineering_is_default_tab_and_help_about_are_separate(self):
        w=self.w;self.assertIn(w.docks['Data Portal'],w.tabifiedDockWidgets(w.docks['Engineering Controls']))
        self.assertTrue(w.docks['Engineering Controls'].visibleRegion().isEmpty()==False)
        self.assertTrue(w.docks['Data Portal'].visibleRegion().isEmpty())
        self.assertTrue(w.info_dialog.isModal());self.assertFalse(w.help_dialog.isModal())
        self.assertIs(w.help.parentWidget(),w.help_dialog);self.assertIs(w.info.parentWidget(),w.info_dialog)
        w.help_action.trigger();self.app.processEvents();self.assertTrue(w.help_dialog.isVisible())
        self.assertIsNone(w.info.findChild(QtWidgets.QTextBrowser, 'manualBrowser'))
        w.info_action.trigger();self.app.processEvents();self.assertTrue(w.info_dialog.isVisible());w.info_dialog.close()
    def test_native_per_file_check_and_close_leave_other_file_unchanged(self):
        w=self.w;da,a=self.add_file('File A.csv');db,b=self.add_file('File B.csv');w.show_dock('Data Portal');self.app.processEvents()
        self.assertFalse(hasattr(w.portal,'select_all'))
        self.click_check(w.portal.dataset_roots[da.id]);self.assertEqual(set(w.dashboard.active.ids),set(a))
        self.assertEqual(w.portal.dataset_roots[db.id].checkState(0),QtCore.Qt.CheckState.Unchecked)
        self.click_check(w.portal.dataset_roots[db.id]);self.assertEqual(set(w.dashboard.active.ids),set(a+b))
        w.portal.search.setText('Sensor');self.click_check(w.portal.dataset_roots[db.id]);self.assertEqual(set(w.dashboard.active.ids),set(a))
        w.portal.search.clear();root=w.portal.dataset_roots[db.id]
        button=w.portal.tree.itemWidget(root,3);self.assertEqual(button.text(),'Close Dataset');button.click();self.app.processEvents()
        self.assertEqual(set(w.store.channels),set(a));self.assertEqual(set(w.dashboard.active.ids),set(a));self.assertNotIn(db.id,w.store.datasets)
    def test_corner_bar_scales_synchronized_views_once_and_follows_focus(self):
        w=self.w;_,a=self.add_file('A');_,b=self.add_file('B','W');workspace=w.dashboard;workspace.set_layout('Vertical split')
        p,q=workspace.visible_panes();p.bind(a);q.bind(b);workspace.link();workspace.active=p;workspace.activeChanged.emit(p);self.app.processEvents()
        bar=workspace.navigation_bar;self.assertIs(bar.parentWidget(),p.viewport());self.assertLessEqual(abs(bar.geometry().right()-(p.viewport().width()-9)),1)
        beforex=list(p.getViewBox().viewRange()[0]);beforey=[list(v.viewRange()[1]) for pane in (p,q) for v in pane.y_views()]
        workspace.navigation_actions['in'].trigger();self.app.processEvents()
        np.testing.assert_allclose(p.getViewBox().viewRange()[0],q.getViewBox().viewRange()[0]);self.assertAlmostEqual(np.diff(p.getViewBox().viewRange()[0])[0]/np.diff(beforex)[0],.8)
        aftery=[v.viewRange()[1] for pane in (p,q) for v in pane.y_views()]
        for old,new in zip(beforey,aftery):self.assertAlmostEqual(np.diff(new)[0]/np.diff(old)[0],.8)
        workspace.active=q;workspace.activeChanged.emit(q);self.assertIs(bar.parentWidget(),q.viewport())
        workspace.navigation_actions['box'].trigger();self.assertTrue(all(pane.getViewBox().state['mouseMode']==pane.getViewBox().RectMode for pane in (p,q)))
        workspace.navigation_actions['reset'].trigger();self.app.processEvents();self.assertLessEqual(p.viewRange()[0][0],0);self.assertGreaterEqual(q.viewRange()[0][1],10)
    def test_previous_workspace_axis_rules_and_locked_cursors_restore(self):
        w=self.w;_,ids=self.add_file('Previous.csv');p=w.dashboard.active;w.dashboard.assign(ids)
        w.store.update(ids[0],attributes={'plot_style':{'color':'#ff3355'},'match_percent':91})
        p.cursor_lines[0].setValue(3);p.cursor_lines[1].setValue(7);p.lock_cursor(0,ids[0]);p.setXRange(1,8,padding=0)
        state=w.dashboard.state();ui=w.ui_state();ui['app_version']='2.1.9'
        path=save_workspace(Path(self.temp.name)/'legacy.json',w.store,[state,w.comparison.state()],ui)
        for suffix in ('json','xml','ini'):
            source=path
            if suffix=='xml':
                import xml.etree.ElementTree as ET
                root=ET.Element('workspace');ET.SubElement(root,'json').text=path.read_text();source=path.with_suffix('.xml');source.write_text(ET.tostring(root,encoding='unicode'))
            elif suffix=='ini':
                source=path.with_suffix('.ini');source.write_text('[workspace]\npayload = '+path.read_text())
            w.restore_path(source);self.app.processEvents();restored=w.dashboard.active
            self.assertEqual(restored.bindings,state['panes'][0]['bindings']);self.assertEqual(restored.cursor_locks,state['panes'][0]['cursor_locks'])
            np.testing.assert_allclose(restored.viewRange()[0],state['panes'][0]['range'][0]);self.assertEqual(w.store.channels[ids[0]].attributes['match_percent'],91)
            self.assertEqual(w.store.channels[ids[0]].attributes['plot_style']['color'],'#ff3355')
    def test_invalid_legacy_view_is_rejected_before_replacing_workspace(self):
        w=self.w;_,ids=self.add_file('A');w.dashboard.assign(ids);original=w.store
        path=save_workspace(Path(self.temp.name)/'invalid.json',w.store,[w.dashboard.state()],w.ui_state())
        record=json.loads(path.read_text());record['views'][0]['panes'][0]['range']=[[0,float('nan')],[0,1]];path.write_text(json.dumps(record))
        with self.assertRaises(ValueError):w.restore_path(path)
        self.assertIs(w.store,original);self.assertEqual(set(w.dashboard.active.ids),set(ids))

    def test_early_source_only_workspace_rebinds_every_viewport(self):
        w=self.w;_,ids=self.add_file('A');w.dashboard.assign(ids)
        path=save_workspace(Path(self.temp.name)/'source-only.json',w.store,[],{'app_version':'2.1.0'})
        w.restore_path(path)
        for workspace in w.workspaces:
            self.assertIs(workspace.store,w.store);self.assertFalse(workspace.active.ids)
        self.assertEqual(set(w.store.channels),set(ids))

    def test_crossed_cursor_hud_has_absolute_differences(self):
        _,ids=self.add_file('A');w=self.w;w.dashboard.assign(ids);p=w.dashboard.active
        p.cursor_lines[0].setValue(8);p.cursor_lines[1].setValue(2);w._readouts()
        self.assertIn('ΔX 6',w.interval_card.text());self.assertIn('|ΔY| 6',w.interval_card.text())
        self.assertEqual(p.measurements()[ids[0]]['ΔY'],-6)


class MigrationLifecycleTests(unittest.TestCase):
    def test_xml_ini_and_legacy_json_presets_preserve_unknown_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            xml=root/'preset.xml';xml.write_text('<preset version="2"><signals><channel name="Probe" color="#ff3355" enabled="true" panel="Panel 2"/></signals><options><show_grid>false</show_grid><custom>{"rule":91}</custom></options></preset>')
            ini=root/'preset.ini';ini.write_text('[channel:Probe]\ncolor=#ff3355\nenabled=True\npanel=Panel 2\n[options]\nshow_grid=False\ncustom={"rule":91}\n')
            for path in (xml,ini):
                record=read_configuration(path);self.assertEqual(record['version'],3);self.assertEqual(record['signals']['Probe']['color'],'#ff3355');self.assertIs(record['signals']['Probe']['enabled'],True)
                self.assertIs(record['options']['show_grid'],False);self.assertEqual(record['options']['custom'],{'rule':91})
            wrapped=migrate_configuration({'preset':{'version':2,'signals':{}},'custom':'keep'})
            self.assertEqual(wrapped['legacy_wrapper'],{'custom':'keep'});json.dumps(wrapped)
            xml.write_text('<!DOCTYPE x [<!ENTITY a "x">]><preset>&a;</preset>')
            with self.assertRaises(ValueError):read_configuration(xml)
    def test_migration_verifies_copies_preserves_conflicts_and_originals(self):
        with tempfile.TemporaryDirectory() as folder:
            old=Path(folder)/'old';new=Path(folder)/'new';(old/'templates').mkdir(parents=True);(new/'templates').mkdir(parents=True)
            (old/'templates'/'custom.ini').write_text('old settings');(new/'templates'/'custom.ini').write_text('new settings')
            (old/'presets').mkdir();(old/'presets'/'view.xml').write_text('<preset/>')
            report=migrate_user_files([old],new);self.assertEqual(len(report),2);self.assertEqual((new/'templates'/'custom.ini').read_text(),'new settings')
            self.assertEqual((new/'presets'/'view.xml').read_text(),'<preset/>');self.assertTrue((old/'templates'/'custom.ini').exists())
            self.assertEqual(next((new/'legacy-imports').rglob('custom.ini')).read_text(),'old settings')
    def test_cleanup_is_inventory_limited_and_keeps_modified_user_running_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);exe=root/'ApplianceSignalStudio.exe';exe.write_bytes(b'old');internal=root/'_internal';internal.mkdir();library=internal/'old.dll';library.write_bytes(b'lib');modified=internal/'modified.dll';modified.write_bytes(b'changed');user=root/'report.csv';user.write_bytes(b'private');outside=root.parent/'outside.dll'
            files={exe.name:digest(exe),'_internal/old.dll':digest(library),'_internal/modified.dll':'0'*64,'report.csv':digest(user),'../outside.dll':'0'*64}
            inventory={'product':PRODUCT,'version':'2.1.9','files':files}
            removed,retained=cleanup_inventory(root,inventory,root/'current.exe');self.assertFalse(exe.exists());self.assertFalse(library.exists());self.assertTrue(user.exists());self.assertTrue(modified.exists());self.assertIn(str(modified),retained)
            exe.write_bytes(b'current');inventory['files']={exe.name:digest(exe)}
            cleanup_inventory(root,inventory,exe);self.assertTrue(exe.exists())
            inventory['product']='Other product';self.assertEqual(cleanup_inventory(root,inventory,root/'different.exe')[0],[])


if __name__=='__main__':unittest.main()

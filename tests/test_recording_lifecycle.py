"""User workflows: remove recordings, review TDMS once and reopen safely."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from PySide6 import QtWidgets,QtCore,QtTest
from app_channel_store import ChannelStore,Channel,Dataset
from app_ingestion import ingest
from app_tdms_templates import ParameterTemplates,ParameterReview,identity,suggested_name
from app_output import output_directory,output_path


class ImportClockTests(unittest.TestCase):
    def test_split_date_clock_and_remaining_time_are_not_confused(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'power.csv'
            path.write_text('Date,Time,Power\n2026/10/07,23:59:30,20\n2026/10/08,00:00:30,30\n')
            s=ChannelStore();ingest(s,path);c=next(iter(s.channels.values()))
            self.assertEqual(len(s.channels),1);np.testing.assert_allclose(c.x,[0,1])
            path.write_text('remaining_time,Signal\n60,20\n59,30\n')
            s=ChannelStore();ingest(s,path)
            self.assertTrue(all(c.coordinate_kind=='sample' for c in s.channels.values()))

    def test_motor_temperature_typo_is_not_an_actuator(self):
        from app_actuators import interpret_channel
        c=interpret_channel(Channel('Motor_temperatuer',[0,1],[25,30]))
        self.assertFalse(c.attributes.get('actuator_binary'));np.testing.assert_equal(c.y,[25,30])


class LifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'ANALIZER_OUTPUT_DIR':self.folder.name,'ANALIZER_SETTINGS_DIR':str(Path(self.folder.name)/'settings')});self.env.start()
    def tearDown(self):self.env.stop();self.folder.cleanup()
    def tdms(self,name='PDH_AAS_B_V1_0_R',values=(0,128,-2)):
        store=ChannelStore();ds=Dataset('test',pd.DataFrame({'raw':values}));store.datasets[ds.id]=ds
        store.add(Channel(name,np.arange(len(values)),values,dataset_id=ds.id,attributes={'format':'TDMS','source_column':"/'Group'/'"+name+"_Value'",'actuator_command':True}))
        return store

    def test_template_survives_restart_known_reused_unknown_only_and_raw_preserved(self):
        s=self.tdms();c=next(iter(s.channels.values()));t=ParameterTemplates();self.assertEqual(len(t.unknown(s)),1)
        entry={'name':'Inlet valve','unit':'','interpretation':'actuator'};t.save({identity(c):entry})
        restarted=ParameterTemplates();self.assertEqual(restarted.unknown(s),[]);restarted.apply(s)
        c=s.channels[c.id];self.assertEqual(c.name,'Inlet valve');np.testing.assert_equal(c.y,[0,1,1]);np.testing.assert_equal(c.raw_y,[0,128,-2])
        restarted.apply(s);np.testing.assert_equal(s.channels[c.id].raw_y,[0,128,-2])
        unknown=self.tdms('Unseen signal');s.channels.update(unknown.channels)
        self.assertEqual([c.name for c in restarted.unknown(s)],['Unseen signal'])
        restarted.save({identity(c):{**entry,'interpretation':'numeric'}});restarted.apply(s)
        np.testing.assert_equal(s.channels[c.id].y,[0,128,-2])

    def test_review_validation_short_names_and_corrupt_template(self):
        s=self.tdms();dialog=ParameterReview(s.channels.values())
        self.assertEqual(dialog.table.item(0,1).text(),'Valve 1')
        dialog.table.item(0,1).setText('');dialog.accept();self.assertIn('display name',dialog.error.text())
        dialog.table.item(0,1).setText('Intake');self.assertEqual(next(iter(dialog.entries().values()))['name'],'Intake');dialog.close()
        path=output_path('tdms-parameters.json','templates');path.write_text('{broken')
        t=ParameterTemplates();self.assertTrue(t.warning);self.assertEqual(len(t.unknown(s)),1);self.assertEqual(path.read_text(),'{broken')

    def test_first_review_cancel_is_atomic_known_import_does_not_prompt(self):
        from app_workbench import AdvancedStudioWindow
        w=AdvancedStudioWindow();s=self.tdms();c=next(iter(s.channels.values()))
        with patch.object(ParameterReview,'exec',return_value=QtWidgets.QDialog.DialogCode.Rejected):w.finish_import(s)
        self.assertEqual(len(w.store.channels),0);self.assertFalse(output_path('tdms-parameters.json','templates').exists())
        ParameterTemplates().save({identity(c):{'name':'Valve','unit':'','interpretation':'auto'}})
        with patch.object(ParameterReview,'exec',side_effect=AssertionError('Known parameters should not prompt')):w.finish_import(s)
        self.assertEqual(next(iter(w.store.channels.values())).name,'Valve');w.close();self.app.processEvents()

    def test_remove_dataset_clears_both_plots_locks_source_and_dependencies(self):
        from app_workbench import AdvancedStudioWindow
        w=AdvancedStudioWindow();ds=Dataset('A',pd.DataFrame({'x':[1,2]}));other=Dataset('B',pd.DataFrame({'x':[3,4]}))
        w.store.datasets.update({ds.id:ds,other.id:other})
        with w.store.batch():
            a=w.store.add(Channel('A',[0,1],[1,2],dataset_id=ds.id));b=w.store.add(Channel('B',[0,1],[3,4],dataset_id=other.id))
            derived=w.store.add(Channel('Derived',[0,1],[4,5],dataset_id=other.id,parents=[a.id]))
        w.dashboard.assign([a.id,b.id]);w.comparison.assign([a.id,derived.id]);w.dashboard.active.lock_cursor(0,a.id)
        w.source_selector.setCurrentIndex(w.source_selector.findData(ds.id));w.drop_recordings([ds.id]);self.app.processEvents()
        self.assertEqual(set(w.store.channels),{b.id});self.assertNotIn(ds.id,w.store.datasets)
        for workspace in w.workspaces:
            for pane in workspace.panes:
                self.assertNotIn(a.id,pane.ids);self.assertNotIn(derived.id,pane.ids);self.assertFalse(any(pane.cursor_locks))
        self.assertNotEqual(w.source_selector.currentData(),ds.id)
        w.drop_recordings(list(w.store.datasets),clear_all=True);self.app.processEvents()
        self.assertFalse(w.store.channels);self.assertFalse(w.store.datasets);self.assertEqual(w.readout.rowCount(),0)
        for workspace in w.workspaces:
            self.assertEqual(workspace.active.ids,[]);self.assertFalse(workspace.active.axes)
        w.close();self.app.processEvents()

    def test_outputs_and_save_dialogs_use_persistent_folder(self):
        self.assertEqual(output_directory(),Path(self.folder.name));self.assertTrue(output_path('report.pdf').parent.is_dir())
        from app_workbench import AdvancedStudioWindow
        w=AdvancedStudioWindow()
        with patch.object(QtWidgets.QFileDialog,'getSaveFileName',return_value=('','')) as dialog:
            w.save();proposed=Path(dialog.call_args.args[2])
            # Resolve Windows 8.3/long-name aliases while still requiring the
            # exact configured workspace directory and suggested filename.
            self.assertEqual(proposed.parent.resolve(),(Path(self.folder.name)/'workspaces').resolve())
            self.assertEqual(proposed.name,'Workspace.json')
        w.close();self.app.processEvents()

    def test_workspace_save_and_restore_keep_event_loop_responsive(self):
        import threading
        from app_workbench import AdvancedStudioWindow
        from app_workspace_io import save_workspace,load_workspace
        w=AdvancedStudioWindow();c=w.store.add(Channel('Signal',[0,1],[2,3]));w.dashboard.assign([c.id]);path=Path(self.folder.name)/'session.json'
        gate=threading.Event();ticks=[]
        def saving(*args):
            if not gate.wait(3):raise RuntimeError('Test save did not resume')
            return save_workspace(*args)
        try:
            with patch.object(QtWidgets.QFileDialog,'getSaveFileName',return_value=(str(path),'')),patch('app_workbench.save_workspace',side_effect=saving):
                w.save();self.assertTrue(w.busy);QtCore.QTimer.singleShot(0,lambda:ticks.append(True));QtTest.QTest.qWait(30)
                self.assertTrue(ticks)
                with self.assertRaises(ValueError):w.drop_recordings([],clear_all=True)
                gate.set()
                for _ in range(500):
                    if not w.busy:break
                    QtTest.QTest.qWait(10)
                self.assertFalse(w.busy);self.assertTrue(path.exists());self.assertIn('Saved',w.statusBar().currentMessage())
            w.drop_recordings([],clear_all=True)
            with patch.object(QtWidgets.QFileDialog,'getOpenFileName',return_value=(str(path),'')):
                w.restore();self.assertTrue(w.busy)
                for _ in range(500):
                    if not w.busy:break
                    QtTest.QTest.qWait(10)
            self.assertFalse(w.busy);self.assertIn(c.id,w.store.channels)
        finally:gate.set();w.close();self.app.processEvents()


if __name__=='__main__':unittest.main()

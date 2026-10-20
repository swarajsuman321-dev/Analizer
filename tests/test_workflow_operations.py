"""User-visible worker cancellation, processing preflight and atomic recovery."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from PySide6 import QtCore,QtWidgets,QtTest
from app_channel_store import Channel,ChannelStore
from app_operation_context import operation_context
from app_processing_preflight import processing_preflight
from app_reporting import export_report
from app_workspace_io import save_workspace,load_workspace
from app_workbench import AdvancedStudioWindow


class WorkflowOperationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.environment=patch.dict(os.environ,{'ANALIZER_SETTINGS_DIR':str(self.folder/'settings'),'ANALIZER_OUTPUT_DIR':str(self.folder/'outputs')});self.environment.start()
        self.window=AdvancedStudioWindow();self.window.show();self.app.processEvents()
        self.channel=self.window.store.add(Channel('Power',[0,1,2],[10,20,30],unit='W',coordinate_unit='min'))
        self.window.dashboard.assign([self.channel.id]);self.app.processEvents()
    def tearDown(self):self.window.close();self.app.processEvents();self.environment.stop();self.temp.cleanup()
    def finish(self):
        for _ in range(1000):
            if not self.window.busy:return
            QtTest.QTest.qWait(10)
        self.fail('Worker did not complete')

    def test_cancel_export_keeps_old_file_and_event_loop_responsive(self):
        window=self.window;destination=self.folder/'interval.csv';destination.write_text('previous complete output')
        gate=threading.Event();started=threading.Event();ticks=[];original=pd.DataFrame.to_csv
        def write(frame,*args,**kwargs):
            started.set()
            if not gate.wait(5):raise RuntimeError('Writer test gate timed out')
            return original(frame,*args,**kwargs)
        try:
            with patch.object(QtWidgets.QFileDialog,'getSaveFileName',return_value=(str(destination),'CSV interval samples (*.csv)')),patch.object(pd.DataFrame,'to_csv',write):
                window.report();self.assertTrue(window.busy)
                QtCore.QTimer.singleShot(0,lambda:ticks.append(True))
                for _ in range(200):
                    QtTest.QTest.qWait(5)
                    if started.is_set():break
                self.assertTrue(started.is_set());self.assertTrue(ticks)
                with self.assertRaises(ValueError):window.drop_recordings([],clear_all=True)
                window.cancel_operation();gate.set();self.finish()
            self.assertEqual(destination.read_text(),'previous complete output')
            self.assertEqual(list(self.folder.glob('.interval-*')),[])
            self.assertIn('cancel',window.statusBar().currentMessage().lower())
            self.assertFalse(window.open_export_button.isVisible())
        finally:gate.set()

    def test_export_failure_keeps_previous_complete_artifact(self):
        destination=self.folder/'report.pdf';destination.write_bytes(b'previous complete report')
        with patch('app_workspace_io.render_report',side_effect=OSError('Disk full')):
            with self.assertRaisesRegex(OSError,'Disk full'):export_report(destination,self.window.store,self.window.dashboard.state())
        self.assertEqual(destination.read_bytes(),b'previous complete report')
        self.assertEqual(list(self.folder.glob('.report-*')),[])

    def test_cancel_save_preserves_previous_json_and_companion(self):
        destination=self.folder/'workspace.json';views=[workspace.state() for workspace in self.window.workspaces]
        save_workspace(destination,self.window.store,views)
        original=destination.read_bytes();files=set(self.folder.iterdir());cancel=threading.Event()
        def progress(stage,value):
            if stage=='Writing source-preserving workspace':cancel.set()
        with operation_context(cancel,progress):
            with self.assertRaises(InterruptedError):save_workspace(destination,self.window.store,views)
        self.assertEqual(destination.read_bytes(),original);self.assertEqual(set(self.folder.iterdir()),files)
        store,_,_=load_workspace(destination);np.testing.assert_equal(store.channels[self.channel.id].y,self.channel.y)

    def test_processing_explains_clock_and_unknown_units(self):
        regular=Channel('Unknown',[0,1,2],[10,20,30],coordinate_unit='min')
        info=processing_preflight(regular,'Butterworth low-pass',1)
        self.assertFalse(info['valid']);self.assertAlmostEqual(info['nyquist'],1/120);self.assertIn('cutoff',info['message'])
        self.assertTrue(processing_preflight(regular,'Butterworth low-pass',1/240)['valid'])
        irregular=Channel('Irregular',[0,1,1,3],[1,2,3,4],coordinate_unit='min')
        for cutoff in (.1,.0001):
            record=processing_preflight(irregular,'Butterworth low-pass',cutoff)
            self.assertFalse(record['valid']);self.assertIn('resampl',record['message'].lower())
        self.assertIn('unknown physical',processing_preflight(regular,'Cumulative integration')['message'].lower())

    def test_cancel_formula_does_not_add_result(self):
        window=self.window;gate=threading.Event();started=threading.Event()
        from app_signal_processing import formula
        def calculate(*args):
            started.set()
            if not gate.wait(5):raise RuntimeError('Formula test gate timed out')
            return formula(*args)
        try:
            window.expression.setText('Ch("Power") * 2')
            with patch('app_workbench.formula',side_effect=calculate):
                window.apply_formula();self.assertTrue(window.busy)
                for _ in range(200):
                    QtTest.QTest.qWait(5)
                    if started.is_set():break
                self.assertTrue(started.is_set());window.cancel_operation();gate.set();self.finish()
            self.assertEqual(list(window.store.channels),[self.channel.id]);np.testing.assert_equal(self.channel.y,[10,20,30])
        finally:gate.set()

    def test_update_preparation_freezes_payload_and_stages_in_worker(self):
        from app_updates import RELEASES
        window=self.window;info=window.info;gate=threading.Event();started=threading.Event();calls=[]
        payload=self.folder/'update.exe';payload.write_bytes(b'fixture')
        manifest={'version':'99.0.0','kind':'portable','url':RELEASES+'/download/v99.0.0/ApplianceSignalStudio.exe','size':7,'sha256':'0'*64}
        info.download=payload;info.manifest=manifest
        update_directory=self.folder/'updates';update_directory.mkdir()
        def launch(*args,**kwargs):
            calls.append((args,kwargs));started.set()
            if not gate.wait(5):raise RuntimeError('Staging test gate timed out')
            return {'request':'test request'}
        try:
            with patch('app_info.launch_installer',side_effect=launch),patch.object(info,'update_directory',return_value=update_directory),patch.object(window,'close') as close:
                info.update();self.assertTrue(window.busy);self.assertFalse(info.check_button.isEnabled());self.assertFalse(info.install_button.isEnabled());self.assertFalse(info.offline_button.isEnabled())
                for _ in range(200):
                    QtTest.QTest.qWait(5)
                    if started.is_set():break
                self.assertTrue(started.is_set());info.download=self.folder/'another.exe';info.manifest={**manifest,'version':'100.0.0'}
                gate.set();self.finish();close.assert_called_once()
            self.assertEqual(calls[0][0][0],payload);self.assertEqual(calls[0][1]['manifest']['version'],'99.0.0')
            recovery=Path(calls[0][0][1]);record=json.loads(recovery.read_text())
            self.assertTrue((recovery.parent/record['arrays']).is_file())
        finally:gate.set()


if __name__=='__main__':unittest.main()

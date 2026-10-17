"""One TDMS review contract across native Open, alignment and comparison."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from PySide6 import QtWidgets
from app_channel_store import ChannelStore
from app_ingestion import ingest
from app_tdms_templates import ParameterTemplates,ParameterReview,identity
from test_tdms_hover import labsys,write


class EngineeringTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.env=patch.dict(os.environ,{'ANALIZER_OUTPUT_DIR':str(self.root/'outputs'),'ANALIZER_SETTINGS_DIR':str(self.root/'settings')});self.env.start()
        self.path=self.root/'machine.tdms'
        write(self.path,labsys('PDH_AAS_B_V1_0_R',[0,2,4],[0,128,-2])+labsys('Current Temperature',[0,2,4],[20,30,40],'°C'))
        self.native=ChannelStore();ingest(self.native,self.path)
        from app_workbench import AdvancedStudioWindow
        self.w=AdvancedStudioWindow();self.w.machine_path.setText(str(self.path))
        self.w.sync.setCurrentText('Raw Timestamps (No Shift)')
        # Run the actual calculations and UI completion deterministically. The
        # existing worker lifecycle suite separately covers background delivery.
        self.background=patch.object(self.w,'background',side_effect=lambda fn,done:done(fn()));self.background.start()

    def tearDown(self):
        self.background.stop();self.w.close();self.app.processEvents();self.env.stop();self.temp.cleanup()

    def entries(self):
        return {identity(c):{'name':'Reviewed '+c.name,'unit':c.attributes.get('raw_unit',c.unit),
                              'interpretation':'numeric'} for c in self.native.channels.values()}

    def test_open_template_reused_in_both_alignment_fields_and_realignment(self):
        templates=ParameterTemplates();templates.save(self.entries())
        with patch.object(ParameterReview,'exec',side_effect=AssertionError('Known TDMS must not prompt')):
            self.w.align()
            channels=list(self.w.store.channels.values())
            self.assertEqual(len(channels),2)
            valve=next(c for c in channels if 'V1' in c.name)
            self.assertTrue(valve.name.startswith('Reviewed '));self.assertFalse(valve.attributes['actuator_binary'])
            self.assertIn(128,valve.y);self.assertEqual(valve.source,str(self.path))
            ids=set(self.w.store.channels);self.w.align();self.assertEqual(set(self.w.store.channels),ids)
            np.testing.assert_equal(self.w.store.channels[valve.id].y,valve.y)
            # TDMS can be used in the power slot too. Its source must stay TDMS,
            # rather than the empty machine slot, for review and refresh identity.
            self.w.machine_path.clear();self.w.power_path.setText(str(self.path));self.w.align()
            power=[c for c in self.w.store.channels.values() if c.id not in ids]
            self.assertEqual(len(power),2);self.assertTrue(all(c.source==str(self.path) and c.name.startswith('Reviewed ') for c in power))

    def test_refreshed_template_updates_labels_and_units_without_losing_custom_names(self):
        template=ParameterTemplates();entries=self.entries();template.save(entries);self.w.align()
        initial={identity(c):c for c in self.w.store.channels.values()}
        for key,entry in entries.items():entry.update(name='New '+entry['name'],unit='K' if 'Temperature' in entry['name'] else 'code')
        custom=next(iter(initial.values()));self.w.store.update(custom.id,name='My custom trace')
        template.save(entries);self.w.align()
        for key,old in initial.items():
            current=self.w.store.channels[old.id]
            self.assertEqual(current.unit,entries[key]['unit'])
            self.assertEqual(current.name,'My custom trace' if old.id==custom.id else entries[key]['name'])

    def test_background_review_runs_on_ui_thread_then_loads_alignment(self):
        from PySide6 import QtCore,QtTest
        self.background.stop()
        reviewed=[]
        def accept(dialog):
            reviewed.append(QtCore.QThread.currentThread()==self.app.thread())
            return QtWidgets.QDialog.DialogCode.Accepted
        with patch.object(ParameterReview,'exec',accept),patch.object(ParameterReview,'entries',return_value=self.entries()):
            self.w.align()
            for _ in range(1000):
                self.app.processEvents();QtTest.QTest.qWait(10)
                if not self.w.busy:break
        self.assertEqual(reviewed,[True]);self.assertFalse(self.w.busy)
        self.assertEqual(len(self.w.store.channels),2)
        self.assertTrue(all(c.name.startswith('Reviewed ') for c in self.w.store.channels.values()))
        self.assertNotEqual(self.w.statusBar().currentMessage(),'Working…')

    def test_two_tdms_sources_keep_distinct_projection_and_template_identities(self):
        from app_analysis_service import align_recordings
        second=self.root/'second.tdms';second.write_bytes(self.path.read_bytes())
        result,frame=align_recordings(str(self.path),str(second),'Raw Timestamps (No Shift)')
        template=ParameterTemplates();template.save(self.entries());template.apply(result)
        tdms=[c for c in result.channels.values() if c.attributes.get('format')=='TDMS']
        self.assertEqual(len(tdms),4)
        self.assertEqual({c.source for c in tdms},{str(self.path),str(second)})
        self.assertTrue(all(c.name.startswith('Reviewed ') for c in tdms))
        self.assertEqual(len({(c.source,c.attributes['data_column']) for c in tdms}),4)

    def test_first_engineering_review_saves_template_reused_by_open(self):
        with patch.object(ParameterReview,'exec',return_value=QtWidgets.QDialog.DialogCode.Accepted) as dialog,patch.object(ParameterReview,'entries',return_value=self.entries()):
            self.w.align();self.assertEqual(dialog.call_count,1)
        self.assertEqual(ParameterTemplates().unknown(self.native),[])
        with patch.object(ParameterReview,'exec',side_effect=AssertionError('Open must reuse engineering review')):
            self.w.finish_import(self.native)
        self.assertTrue(all(c.name.startswith('Reviewed ') for c in self.w.store.channels.values()))

    def test_cancel_unknown_parameter_preserves_workspace_and_analysis(self):
        from app_channel_store import Channel
        existing=self.w.store.add(Channel('Existing',[0,1],[1,2]))
        sentinel=object();self.w.aligned_frame=sentinel;self.w.comparison_result=sentinel
        # With one reviewed parameter, the dialog must contain only the new one.
        entries=self.entries();ParameterTemplates().save({next(iter(entries)):next(iter(entries.values()))})
        seen=[]
        def cancel(dialog):seen.extend(c.name for c in dialog.channels);return QtWidgets.QDialog.DialogCode.Rejected
        with patch.object(ParameterReview,'exec',cancel),patch('app_analysis_service.align_recordings',side_effect=AssertionError('Cancelled review cannot calculate')):
            self.w.align()
        self.assertEqual(seen,['Current Temperature']);self.assertEqual(set(self.w.store.channels),{existing.id})
        self.assertIs(self.w.aligned_frame,sentinel)
        self.w.simulation_path.setText('unused.csv')
        with patch.object(ParameterReview,'exec',cancel),patch('app_analysis_service.compare_recordings',side_effect=AssertionError('Cancelled review cannot compare')):self.w.compare()
        self.assertIs(self.w.comparison_result,sentinel);self.assertEqual(set(self.w.store.channels),{existing.id})

    def test_comparison_uses_reviewed_bench_label_and_retains_reference_units(self):
        sim=self.root/'sim.csv';pd.DataFrame({'time':[0,1,2],'water_temp':[20,30,40],'drum_speed':[0,100,0],'water_pressure':[0,100,0],'water_volume':[0,1,0],'process_state':[0,1,2]}).to_csv(sim,index=False)
        self.w.simulation_path.setText(str(sim));ParameterTemplates().save(self.entries())
        with patch.object(ParameterReview,'exec',side_effect=AssertionError('Known TDMS must not prompt')):self.w.compare()
        bench=[c for c in self.w.store.channels.values() if c.attributes.get('comparison_source')=='bench' and c.attributes.get('format')=='TDMS']
        self.assertEqual(len(bench),1);self.assertEqual(bench[0].name,'Reviewed Current Temperature · bench');self.assertEqual(bench[0].unit,'°C')
        reference=[c for c in self.w.store.channels.values() if c.attributes.get('comparison_source')=='sim']
        self.assertTrue(reference);self.assertTrue(all(not c.name.startswith('Reviewed ') for c in reference))
        self.assertIsNotNone(self.w.comparison_result)

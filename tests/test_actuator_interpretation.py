import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from PySide6 import QtWidgets,QtCore
from app_channel_store import ChannelStore,Channel,Dataset
from app_actuators import interpret_channel
from app_ingestion import ingest

class ActuatorTests(unittest.TestCase):
    def test_zero_nonzero_integer_and_unknown(self):
        c=Channel('Inlet Valve',np.arange(9.),np.array([0,1,128,-1,255,0,.5,np.nan,np.inf]))
        result=interpret_channel(c)
        np.testing.assert_equal(result.y,[0,1,1,1,1,0,np.nan,np.nan,np.nan]);self.assertEqual(result.kind,'discrete');np.testing.assert_equal(result.raw_y,c.y)
    def test_commands_not_measured_power_or_enumerated_programs(self):
        for name,unit,expected in [('Door lock','',True),('Heater','',True),('Inlet valvs','',True),('Drain Valve','state',True),('Heater power','W',False),('Valve current','A',False),('Valve position','%',False),('Program state','',False),('Unknown status','',False)]:
            with self.subTest(name=name):
                c=interpret_channel(Channel(name,np.arange(3.),np.array([0,2,128.]),unit=unit))
                self.assertEqual(bool(c.attributes.get('actuator_binary')),expected)
                np.testing.assert_equal(c.y,[0,1,1] if expected else [0,2,128])
    def test_override_is_reversible_and_derived_values_stay_numeric(self):
        c=Channel('Valve',np.arange(3.),np.array([0,128,-2.]))
        binary=interpret_channel(c);original=interpret_channel(binary,'numeric');np.testing.assert_equal(original.y,c.y)
        np.testing.assert_equal(interpret_channel(original,'auto').y,[0,1,1])
        typed=interpret_channel(Channel('Heater power',c.x,c.y,unit='state',attributes={'actuator_command':True}));np.testing.assert_equal(typed.y,[0,1,1])
        forced=interpret_channel(Channel('Custom command',c.x,c.y),'actuator');np.testing.assert_equal(forced.y,[0,1,1])
        fallback=interpret_channel(forced,'auto');np.testing.assert_equal(fallback.y,c.y)
        import json
        json.dumps(fallback.attributes)
        derived=Channel('Valve average',c.x,np.array([.5,.75,1]),parents=[c.id]);np.testing.assert_equal(interpret_channel(derived).y,derived.y)
    def test_import_words_units_and_original_tables(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'actuators.csv';pd.DataFrame({'time [min]':[0,1,2,3],'Door lock':['UNLOCKED','LOCKED',None,'ON'],'Heater':[0,128,-2,.5],'Heater power [W]':[0,2000,1000,.5],'Program stage':[0,7,49,3],'Running status':['ON','OFF',None,'ON']}).to_csv(path,index=False)
            store=ChannelStore();ingest(store,path);channels={c.name:c for c in store.channels.values()}
            np.testing.assert_equal(channels['Door lock'].y,[0,1,np.nan,1]);np.testing.assert_equal(channels['Heater'].y,[0,1,1,np.nan]);np.testing.assert_equal(channels['Heater power [W]'].y,[0,2000,1000,.5]);self.assertEqual(channels['Heater power [W]'].kind,'analog');np.testing.assert_equal(channels['Running status'].y,[1,0,np.nan,1])
            self.assertEqual(next(iter(store.datasets.values())).frame['Heater'].iloc[1],128)
    def test_alignment_refresh_preserves_numeric_override_and_new_raw_codes(self):
        from app_analysis_service import align_recordings
        from app_alignment_merge import merge_alignment
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'machine.csv'
            def write(value):pd.DataFrame({'timestamp':pd.date_range('2026-10-15',periods=3,freq='min'),'Heat Valve':[0,value,-2]}).to_csv(path,index=False)
            def result():return align_recordings('',str(path),'Raw Timestamps (No Shift)')[0]
            write(128);target=ChannelStore();merge_alignment(target,result());c=next(c for c in target.channels.values() if c.name=='Heat Valve');np.testing.assert_equal(c.y,[0,1,1]);target.channels[c.id]=interpret_channel(c,'numeric')
            write(255);merge_alignment(target,result());np.testing.assert_equal(target.channels[c.id].y,[0,255,-2]);self.assertEqual(target.channels[c.id].attributes['value_interpretation'],'numeric')

class ActuatorGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    def test_binary_readout_step_trace_override_icon_and_snapshot(self):
        from app_workbench import AdvancedStudioWindow
        from app_workspace_io import save_workspace,load_workspace,render_report
        from app_reporting import interval_tables
        w=AdvancedStudioWindow();w.show();store=ChannelStore();c=store.add(Channel('Drain Valve',np.array([0.,1,2,3]),np.array([0.,128,128,0]),coordinate_unit='min'))
        w.merge_store(store);p=w.dashboard.active;p.cursor_lines[0].setValue(0);p.cursor_lines[1].setValue(3);w._readouts()
        self.assertFalse(w.windowIcon().isNull());self.assertFalse(self.app.windowIcon().isNull());self.assertEqual(w.readout.item(0,2).text(),'OFF');self.assertEqual(w.readout.item(0,3).text(),'OFF');self.assertIn('% ON',w.readout.item(0,8).text());self.assertIn('ON time 2 min',w.interval_card.text())
        p._render();x=p.curves[c.id][1].xData;self.assertTrue(np.any(np.diff(x)==0))
        data,summary=interval_tables(w.store,w.dashboard.state());np.testing.assert_equal(data.original_value.to_numpy(),[0,128,128,0]);self.assertEqual(summary.iloc[0]['ON_time'],2)
        with tempfile.TemporaryDirectory() as root:
            render_report(Path(root)/'binary.svg',w.store,w.dashboard.state())
            path=save_workspace(Path(root)/'states.json',w.store,[ws.state() for ws in w.workspaces],w.ui_state());loaded,_,_=load_workspace(path);np.testing.assert_equal(loaded.channels[c.id].raw_y,[0,128,128,0])
        iterator=QtWidgets.QTreeWidgetItemIterator(w.portal.tree)
        while iterator.value():
            item=iterator.value()
            if item.data(0,QtCore.Qt.ItemDataRole.UserRole)==c.id:w.portal.tree.setCurrentItem(item);item.setSelected(True);break
            iterator+=1
        w.selection([c.id]);w.prop_interpretation.setCurrentIndex(w.prop_interpretation.findData('numeric'));w.prop_unit.setText('V');w.apply_properties();self.assertEqual(w.store.channels[c.id].unit,'V');self.assertGreater(p.getViewBox().viewRange()[1][1],128);self.assertEqual([line.value() for line in p.cursor_lines],[0,3]);np.testing.assert_equal(w.store.channels[c.id].y,[0,128,128,0])
        with tempfile.TemporaryDirectory() as root:
            old=ChannelStore();ds=Dataset('Aligned',pd.DataFrame({'Inlet Valve':[0,128,128,0]}));old.datasets[ds.id]=ds;previous=old.add(Channel('Inlet Valve',np.array([0.,1,2,3]),np.array([0.,1,1,0]),unit='state',coordinate_unit='min',dataset_id=ds.id,attributes={'data_column':'Inlet Valve'}))
            view={'layout':'Single','panes':[{'ids':[previous.id],'bindings':{previous.id:'state'},'range':[[0,3],[0,255]],'cursors':[0,3]}]}
            path=save_workspace(Path(root)/'old.json',old,[view,{'layout':'Single','panes':[{'ids':[]}]}]);w.restore_path(path);np.testing.assert_equal(w.store.channels[previous.id].y,[0,1,1,0]);np.testing.assert_equal(w.store.channels[previous.id].raw_y,[0,128,128,0]);self.assertLess(np.ptp(w.dashboard.active.getViewBox().viewRange()[1]),2)
        w.close();self.app.processEvents();self.app.sendPostedEvents(None,QtCore.QEvent.Type.DeferredDelete)

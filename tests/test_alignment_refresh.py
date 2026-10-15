import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from app_channel_store import ChannelStore
from app_analysis_service import align_recordings
from app_alignment_merge import merge_alignment

class AlignmentRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'machine.csv';self.write(4)
    def tearDown(self):self.temp.cleanup()
    def write(self,n):
        pd.DataFrame({'timestamp':pd.date_range('2026-10-15',periods=n,freq='min'),'water_temp':np.arange(n)+20}).to_csv(self.path,index=False)
    def result(self):return align_recordings('',str(self.path),'Raw Timestamps (No Shift)')[0]
    def test_identical_alignment_keeps_ids_counts_and_source_tables(self):
        target=ChannelStore();merge_alignment(target,self.result());ids=list(target.channels);datasets=list(target.datasets);revisions=[c.revision for c in target.channels.values()]
        added,updated,_=merge_alignment(target,self.result())
        self.assertEqual(added,[]);self.assertEqual(updated,0);self.assertEqual(list(target.channels),ids);self.assertEqual(list(target.datasets),datasets);self.assertEqual([c.revision for c in target.channels.values()],revisions)
    def test_new_samples_update_existing_channel_preserving_style(self):
        target=ChannelStore();merge_alignment(target,self.result());c=next(c for c in target.channels.values() if c.attributes.get('data_column')=='water_temp')
        target.update(c.id,name='My probe',attributes={**c.attributes,'plot_style':{'color':'#cc3344'}});self.write(6)
        added,updated,_=merge_alignment(target,self.result());new=target.channels[c.id]
        self.assertEqual(added,[]);self.assertGreater(updated,0);self.assertEqual(len(new.x),6);self.assertEqual(new.name,'My probe');self.assertEqual(new.attributes['plot_style']['color'],'#cc3344')
    def test_new_column_adds_only_one_channel(self):
        target=ChannelStore();merge_alignment(target,self.result());count=len(target.channels);frame=pd.read_csv(self.path);frame['water_pressure']=100;frame.to_csv(self.path,index=False)
        added,_,_=merge_alignment(target,self.result());self.assertEqual(len(added),1);self.assertEqual(len(target.channels),count+1)
    def test_older_unkeyed_alignment_channels_are_reused(self):
        target=self.result()
        for c in target.channels.values():c.attributes.pop('alignment_key')
        for d in target.datasets.values():d.frame.attrs.pop('alignment_key')
        ids=list(target.channels);merge_alignment(target,self.result());self.assertEqual(list(target.channels),ids)

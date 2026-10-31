"""Three-plus signals share program origins, typed metrics and gap-aware overlap."""
import json
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd
from app_channel_store import Channel,ChannelStore,Dataset
from app_multi_comparison import compare_many,export_multi_bundle
from app_program_alignment import align_program_start


class MultiComparisonTests(unittest.TestCase):
    def fixture(self):
        store=ChannelStore();ids=[]
        for index in range(3):
            dataset=Dataset('Run '+str(index),pd.DataFrame());store.datasets[dataset.id]=dataset
            x=np.arange(7.)+index*5
            c=store.add(Channel('Voltage '+str(index),x,np.arange(7.)-2+index,unit='V',coordinate_unit='min',dataset_id=dataset.id))
            align_program_start(store,dataset.id,index*5+2,'Reviewed program start')
            ids.append(c.id)
        return store,ids

    def test_three_runs_compare_each_candidate_with_explicit_reference(self):
        store,ids=self.fixture();result=compare_many(store,ids[0],ids[1:])
        self.assertEqual(len(result['pairs']),2)
        self.assertTrue(all(p['status']=='compared' for p in result['pairs']))
        self.assertEqual([p['metrics']['mean_bias'] for p in result['pairs']],[1.,2.])
        self.assertTrue(all(p['alignment']['mode']=='program' for p in result['pairs']))
        self.assertTrue(all(s['program_time_min'][0]==-2 for s in result['sources']))

    def test_incompatible_candidate_stays_visible_as_blocked(self):
        store,ids=self.fixture();store.update(ids[-1],unit='W')
        result=compare_many(store,ids[0],ids[1:])
        self.assertEqual(result['pairs'][0]['status'],'compared')
        self.assertEqual(result['pairs'][1]['status'],'blocked')
        self.assertTrue(result['pairs'][1]['reason'])
        self.assertEqual(len(result['sources']),3)

    def test_confirmed_same_run_valves_have_pairwise_overlap_and_exclude_gaps(self):
        store=ChannelStore();ds=Dataset('One run',pd.DataFrame());store.datasets[ds.id]=ds
        ids=[]
        for index,states in enumerate(([0,1,1,0,1,1],[0,0,1,0,1,1],[0,1,0,0,1,1])):
            c=store.add(Channel('Valve '+str(index),np.array([0,1,2,3,10,11.]),np.asarray(states),unit='state',kind='discrete',coordinate_unit='s',dataset_id=ds.id,attributes={'actuator_binary':True}))
            ids.append(c.id)
        align_program_start(store,ds.id,1/60,'Reviewed program start')
        result=compare_many(store,ids[0],ids[1:],max_gap_seconds=2)
        self.assertEqual(len(result['overlaps']),3)
        self.assertTrue(all(row['common_known_s']==4 for row in result['overlaps']))
        self.assertEqual([row['simultaneous_on_s'] for row in result['overlaps']],[2.,2.,1.])
        self.assertTrue(all(p['status']=='compared' for p in result['pairs']))
        store.update(ids[-1],attributes={})
        self.assertEqual(len(compare_many(store,ids[0],ids[1:],max_gap_seconds=2)['overlaps']),1)

    def test_export_publishes_complete_sources_intervals_and_same_result(self):
        store,ids=self.fixture();result=compare_many(store,ids[0],ids[1:])
        with tempfile.TemporaryDirectory() as root:
            bundle=export_multi_bundle(Path(root)/'comparison.pdf',result,{'Conclusions':'User reviewed evidence'})
            self.assertTrue(all(Path(path).stat().st_size>100 for path in bundle.values()))
            evidence=json.loads(Path(bundle['evidence']).read_text())
            self.assertEqual(evidence['result'],result)
            self.assertEqual(evidence['metadata']['Conclusions'],'User reviewed evidence')
            sheets=pd.read_excel(bundle['workbook'],sheet_name=None)
            self.assertEqual(len(sheets['Comparison summary']),2)
            for index in range(1,4):self.assertEqual(len(sheets[f'Source {index}']),7)
            for index,pair in enumerate(result['pairs'],1):self.assertEqual(len(sheets[f'Differences {index}']),len(pair['differences']))


if __name__=='__main__':unittest.main()

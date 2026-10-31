"""Program start is an evidenced source-wide origin, never first recording row."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from app_channel_store import Channel, ChannelStore, Dataset
from app_program_alignment import align_program_start, program_start
from app_signal_comparison import compare_signals
from app_workspace_io import save_workspace, load_workspace


class ProgramAlignmentTests(unittest.TestCase):
    def fixture(self):
        store=ChannelStore();ids=[]
        for name,origin in [('A',2.),('B',7.)]:
            ds=Dataset(name,pd.DataFrame({'original':['unchanged']}));store.datasets[ds.id]=ds
            # Same program waveform despite five extra minutes of pre-recording.
            x=np.arange(origin-2,origin+5)
            channel=store.add(Channel('Voltage',x,x-origin,unit='V',coordinate_unit='min',dataset_id=ds.id))
            ids.append(channel.id)
        return store,ids

    def test_missing_program_start_blocks_instead_of_using_recording_start(self):
        store,ids=self.fixture();result=compare_signals(store,*ids,alignment='program')
        self.assertEqual(result['status'],'blocked');self.assertIn('Confirm program start',result['reason'])

    def test_alignment_preserves_sources_negative_time_and_comparison(self):
        store,ids=self.fixture();a,b=[store.channels[id] for id in ids]
        late=store.add(Channel('Late channel',np.array([3.,4.]),np.array([10.,11.]),unit='V',coordinate_unit='min',dataset_id=a.dataset_id))
        seconds=store.add(Channel('Seconds channel',np.array([60.,180.]),np.array([1.,2.]),coordinate_unit='s',dataset_id=a.dataset_id))
        a=store.update(a.id,masks=[(1.,1.5)])
        original={id:(c.x.copy(),c.y.copy()) for id,c in store.channels.items()}
        align_program_start(store,a.dataset_id,2,'Reviewed controller start')
        align_program_start(store,b.dataset_id,7,'Reviewed controller start')
        np.testing.assert_equal(store.channels[a.id].values()[0],np.arange(-2,5))
        np.testing.assert_equal(store.channels[late.id].values()[0],[1,2])
        np.testing.assert_equal(store.channels[seconds.id].values()[0],[-60,60])
        self.assertEqual(store.channels[a.id].masks,[(-1.,-.5)])
        for id,(x,y) in original.items():
            np.testing.assert_equal(store.channels[id].x,x);np.testing.assert_equal(store.channels[id].y,y)
        self.assertEqual(store.datasets[a.dataset_id].frame.iloc[0,0],'unchanged')
        result=compare_signals(store,*ids,alignment='program')
        self.assertEqual(result['status'],'compared',result.get('reason'))
        self.assertAlmostEqual(result['metrics']['rmse'],0.)
        self.assertEqual(result['alignment']['mode'],'program')
        self.assertEqual(result['reference']['program_origin_min'],2.)
        self.assertEqual(result['reference']['recording_origin_min'],0.)
        self.assertEqual(result['candidate']['program_origin_min'],7.)
        self.assertEqual(result['candidate']['recording_origin_min'],5.)
        self.assertEqual(result['scope']['start_min'],-2.)
        # Reapplying the same start does not compound shifts or move masks.
        align_program_start(store,a.dataset_id,2,'Reviewed controller start')
        self.assertEqual(store.channels[a.id].shift,-2.)
        self.assertEqual(store.channels[a.id].masks,[(-1.,-.5)])

    def test_program_confirmation_roundtrips_with_workspace(self):
        store,ids=self.fixture();dataset=store.channels[ids[0]].dataset_id
        align_program_start(store,dataset,2,'User reviewed program transition')
        with tempfile.TemporaryDirectory() as root:
            path=save_workspace(Path(root)/'run.json',store,[])
            restored,_,_=load_workspace(path)
        self.assertEqual(program_start(restored,dataset)['source_min'],2.)
        np.testing.assert_equal(restored.channels[ids[0]].values()[0],np.arange(-2,5))

    def test_invalid_or_unexplained_start_is_rejected_without_changes(self):
        store,ids=self.fixture();c=store.channels[ids[0]]
        for point,note in [(100,'reviewed'),(float('nan'),'reviewed'),(1,''),(True,'reviewed')]:
            with self.subTest(point=point),self.assertRaises(ValueError):align_program_start(store,c.dataset_id,point,note)
        self.assertEqual(store.channels[c.id].shift,0)
        self.assertNotIn('program_start',store.datasets[c.dataset_id].frame.attrs)

    def test_engineering_comparison_defaults_to_confirmed_program_start(self):
        from app_engineering_session import default_session,analyze_session
        store,ids=self.fixture();a,b=[store.channels[id] for id in ids]
        session=default_session();session['runs'].update(reference=a.dataset_id,candidate=b.dataset_id)
        with self.assertRaisesRegex(ValueError,'Confirm program start'):analyze_session(store,session,True)
        align_program_start(store,a.dataset_id,2,'Reviewed program start')
        align_program_start(store,b.dataset_id,7,'Reviewed program start')
        result=analyze_session(store,session,True)
        self.assertEqual([run['program_start']['source_min'] for run in result['runs']],[2.,7.])
        self.assertEqual([run['offset_s'] for run in result['runs']],[0.,0.])

    def test_existing_engineering_projection_is_not_shifted_twice(self):
        store,ids=self.fixture();a,b=[store.channels[id] for id in ids]
        align_program_start(store,a.dataset_id,2,'Reviewed initial start')
        align_program_start(store,b.dataset_id,7,'Reviewed initial start')
        projected=store.add(Channel('Voltage engineering projection',a.x-2,a.y,unit='V',coordinate_unit='min',dataset_id=a.dataset_id,parents=[a.id],attributes={'engineering_projection':True}))
        align_program_start(store,a.dataset_id,3,'Reviewed corrected start')
        align_program_start(store,b.dataset_id,8,'Reviewed corrected start')
        np.testing.assert_allclose(store.channels[projected.id].values()[0],store.channels[a.id].values()[0])
        result=compare_signals(store,projected.id,b.id,alignment='program')
        self.assertEqual(result['status'],'compared',result['reason'])
        self.assertAlmostEqual(result['metrics']['rmse'],0.)


if __name__=='__main__':unittest.main()

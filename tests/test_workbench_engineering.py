import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from app_analysis_service import compare_recordings


class EngineeringTests(unittest.TestCase):
    def test_established_scorecard_channels_and_original_sources(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);bench=root/'bench.csv';sim=root/'sim.csv'
            pd.DataFrame({'time_min':[0,1,2,3],'Current Temperature':[20,30,40,25],'water pressure':[0,500,800,0],
                          'Drump speed feedback':[0,40,800,0],'Heat Valve':[0,128,128,0]}).to_csv(bench,index=False)
            pd.DataFrame({'time':[0,1,2,3],'water_temp':[20,25,40,25],'water_pressure':[0,400,800,0],
                          'drum_speed':[0,40,800,0],'heater_power':[0,2000,2000,0],'water_amount':[0,5,5,5],
                          'pre_wash_valve_open':[0,1,0,0],'main_wash_valve_open':[0,0,1,0],'drain_open':[0,0,0,1],
                          'stwf_number':[0,1,2,3],'water_volume':[0,5,5,0],'process_state':[0,1,2,3]}).to_csv(sim,index=False)
            store,score=compare_recordings(str(bench),str(sim))
            self.assertGreater(len(store.channels),8);self.assertGreater(len(score),5)
            self.assertEqual(len([ds for ds in store.datasets.values() if ds.name in ('Original bench comparison','Simulation reference')]),2);source=next(ds for ds in store.datasets.values() if ds.source==str(bench))
            pd.testing.assert_frame_equal(source.frame,pd.read_csv(bench))
            heaters=[c for c in store.channels.values() if c.unit=='state' and c.attributes['parameter']=='heater_power'];self.assertEqual(len(heaters),1)

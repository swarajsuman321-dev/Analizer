"""Run-specific unit evidence and completed-package integration."""
from pathlib import Path
import tempfile
import unittest
import zipfile

import numpy as np
import pandas as pd

from app_data import DataReadError
from app_simulation import load_simulation_reference, specs_for_curves
from app_comparator import ComparisonEngine
from app_inspection import comparison_traces, sample_trace
from test_csv_comparison import fixture


MAIN = '''<config><dataStore>
<fields headerName="time" recordEntry="accumulated_deltaTMin"/>
<fields headerName="water_pressure" recordEntry="currentPressure"/>
</dataStore><interfaceFunction name="get_pressure"><statement value="currentPressure"/></interfaceFunction>
<statement variable="accumulated_deltaTMin" value="accumulated_deltaTS/60"/></config>'''
SCENARIO = '''<config xmlns:xi="http://www.w3.org/2001/XInclude">
<scenario id="Selected"><definition id="loadMass" value="8"/></scenario>
<scenario id="Other"><definition id="loadMass" value="5"/></scenario>
<xi:include href="../../main.simconfig.xml"/></config>'''
BATCH = '''<tasks><executionTask><scenarioId>Selected</scenarioId>
<configPath>C:\\machine\\test\\scenario.simconfig.xml</configPath>
<resultFilePrefix>run</resultFilePrefix></executionTask></tasks>'''
INTERFACE = '''/**
 * @return pressure - evaluated pressure value (absolut) in Pa.
 */
readonly interfaceFunction get_pressure returns pressure ofType number
'''


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name)/'package.zip'

    def tearDown(self):
        self.temp.cleanup()

    def package(self, *, metadata=True, documentation=INTERFACE, extra=None, frame=None):
        with zipfile.ZipFile(self.path, 'w') as z:
            z.writestr('test/run_simulated_values.csv', (frame if frame is not None else fixture()).to_csv(index=False))
            if metadata:
                z.writestr('main.simconfig.xml', MAIN)
                z.writestr('machine/test/scenario.simconfig.xml', SCENARIO)
                z.writestr('run.batch.xml', BATCH)
                z.writestr('machine/source/interfaces.raciflib', documentation)
            for name, data in (extra or {}).items():
                z.writestr(name, data)

    def test_documented_pressure_active_scenario_and_bench_units(self):
        self.package()
        run = load_simulation_reference(self.path)
        try:
            self.assertEqual(run.curves['pressure'].attrs['source_unit'], 'Pa')
            self.assertEqual(run.curves['pressure'].attrs['unit'], 'Pa')
            self.assertEqual(run.curves['pressure']['value'].max(),500)
            self.assertEqual(run.package_metadata['scenario_definitions']['loadMass'], '8')
            self.assertTrue(any('get_pressure return unit Pa' in line for line in run.unit_evidence))
            bench=pd.DataFrame({'time_min':[0,3], 'water pressure [mbar]':[0,5]})
            specs=specs_for_curves(run.curves)
            cols=ComparisonEngine.find_bench_columns(bench,specs)
            traces=comparison_traces(bench,run.curves,cols,specs)
            self.assertEqual(sample_trace(traces['pressure']['bench'],3),500)
        finally: run.close()

    def test_other_pressure_comment_cannot_establish_return_units(self):
        self.package(documentation='/** @return pressure in Pa */ readonly interfaceFunction unrelated')
        run=load_simulation_reference(self.path)
        try:
            self.assertEqual(run.curves['pressure'].attrs['unit'],'unknown')
            self.assertEqual(run.curves['pressure']['value'].max(),500)
        finally: run.close()

    def test_optional_files_absent_and_no_stale_unit_reuse(self):
        self.package(metadata=False)
        run=load_simulation_reference(self.path)
        try:
            self.assertEqual(len(run.curves),10)
            self.assertEqual(run.curves['pressure'].attrs['unit'],'unknown')
        finally: run.close()

    def test_multiple_result_csvs_are_not_silently_selected(self):
        self.package(extra={'test/other_simulated_values.csv':fixture().to_csv(index=False)})
        with self.assertRaisesRegex(DataReadError, 'exactly one'):
            load_simulation_reference(self.path)

    def test_display_override_and_explicit_unit_row(self):
        self.package()
        run=load_simulation_reference(self.path,pressure_display_unit='mbar')
        try: self.assertEqual(run.curves['pressure']['value'].max(),5)
        finally: run.close()
        from unittest.mock import patch
        frame=fixture();frame.attrs['column_units']={'water_pressure':'mbar'}
        with patch('app_simulation.smart_read_file',return_value=frame):
            run=load_simulation_reference(self.path)
        try:
            self.assertEqual(run.curves['pressure']['value'].max(),50000)
            self.assertEqual(run.curves['pressure'].attrs['source_unit'],'mbar')
        finally: run.close()

    def test_documented_precise_time_and_actual_countdown(self):
        frame=fixture();frame['time']=[0,0,0,.01,.01,.01]
        frame['accumulated_deltaTS']=[0,.1,.2,.3,.4,.5]
        self.package(frame=frame)
        run=load_simulation_reference(self.path)
        try:
            self.assertEqual(run.time_source,'accumulated_deltaTS')
            self.assertEqual(run.duration_min,.5/60)
            np.testing.assert_allclose(run.curves['actual_remaining_time']['value'],np.array([.5,.4,.3,.2,.1,0])/60)
            self.assertEqual(run.frame['time_min'].duplicated().sum(),0)
        finally: run.close()
        frame['accumulated_deltaTS']=[0,1,2,3,4,5]
        self.package(frame=frame)
        run=load_simulation_reference(self.path)
        try:
            self.assertEqual(run.time_source,'time')
            self.assertIn('inconsistent',run.time_source_note)
        finally: run.close()

    def test_xml_cannot_fetch_external_entities(self):
        self.package(extra={'unsafe.simconfig.xml':'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///anything">]><x/>'})
        with self.assertRaisesRegex(DataReadError,'external entities'):
            load_simulation_reference(self.path)

    def test_service_zip_comparison_preserves_sources(self):
        from app_analysis_service import compare_recordings
        self.package()
        csv=Path(self.temp.name)/'bench.csv';fixture().to_csv(csv,index=False)
        store,score=compare_recordings(str(csv),str(self.path))
        sources=[ds for ds in store.datasets.values() if ds.name in ('Original bench comparison','Simulation reference')]
        self.assertEqual(len(sources),2)
        self.assertGreater(len(store.channels),10)
        self.assertTrue(all(len(ds.frame)==6 for ds in sources))
        self.assertEqual(score.set_index('parameter').loc['Peak Water Pressure','sim_val'],'500.00 Pa')


if __name__ == '__main__': unittest.main()

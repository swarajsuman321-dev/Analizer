"""Synthetic source evidence tests; no private recording data is embedded."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from nptdms import ChannelObject, GroupObject, RootObject, TdmsWriter

from app_channel_store import ChannelStore, Dataset
from app_ingestion import ingest, read_tables
from app_parameter_inventory import inventory_runs, source_field
from app_reader_registry import ReaderSpec, UnsupportedFormatError, register_reader
from app_workspace_io import encode_cell, decode_cell, load_workspace, save_workspace


class SourceInventoryTests(unittest.TestCase):
    def test_unknown_numeric_text_empty_and_invalid_fields_are_all_accounted_for(self):
        frame=pd.DataFrame({'Unfamiliar': [7.,7.,7.], 'Category':['dry','wet',None],
                            'No readings':[np.nan,np.nan,np.nan], 'Complex':[1+2j,3+4j,5+6j]})
        store=ChannelStore();ds=Dataset('Unknown',frame);store.datasets[ds.id]=ds
        fields={f['original_name']:f for f in inventory_runs(store)[0]['fields']}
        self.assertEqual(set(fields),set(frame.columns))
        self.assertEqual(fields['Unfamiliar']['disposition'],'analysed')
        self.assertTrue(fields['Unfamiliar']['quality']['constant'])
        self.assertEqual(fields['Category']['disposition'],'analysed')
        self.assertEqual(fields['No readings']['disposition'],'invalid')
        self.assertEqual(fields['Complex']['disposition'],'unsupported')
        self.assertTrue(all(f['clock']['kind']=='sample' for f in fields.values()))
        before=frame.copy(deep=True)
        values=source_field(store,fields['Unfamiliar'])['values']
        with self.assertRaises(ValueError):values[0]=99
        pd.testing.assert_frame_equal(frame,before)
        empty=Dataset('Empty',pd.DataFrame({'No readings':pd.Series([],dtype='float64')}))
        store.datasets[empty.id]=empty
        self.assertEqual(inventory_runs(store,[empty.id])[0]['fields'][0]['disposition'],'invalid')

    def test_original_clock_order_quality_and_sorted_plot_are_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'mixed.csv'
            path.write_text('Time [s],Unfamiliar\n3,30\n1,10\n1,11\n,80\n2,20\n',encoding='utf8')
            store=ChannelStore();ingest(store,path,reader_options={'time_column':'Time [s]','unit':'s','acquisition_policy':'sampled'})
            run=inventory_runs(store)[0];field=next(f for f in run['fields'] if f['original_name']=='Unfamiliar')
            raw=source_field(store,field)
            np.testing.assert_allclose(raw['x'],[3,1,1,np.nan,2],equal_nan=True)
            np.testing.assert_array_equal(raw['values'],[30,10,11,80,20])
            np.testing.assert_array_equal(raw['source_indices'],[0,1,2,3,4])
            self.assertEqual(field['clock']['quality']['duplicates'],1)
            self.assertEqual(field['clock']['quality']['backwards'],1)
            self.assertEqual(field['clock']['quality']['invalid_timestamps'],1)
            self.assertEqual(field['clock']['trust'],'declared')
            np.testing.assert_allclose(next(iter(store.channels.values())).x,np.array([1,1,2,3])/60)
            self.assertEqual(run['metadata']['source_identity']['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())

    def test_unit_row_keeps_original_source_positions_and_combined_datetime(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'units.csv';path.write_text('Time,Value\ns,Pa\n60,10\n120,20\n')
            store=ChannelStore();ingest(store,path)
            field=next(f for f in inventory_runs(store)[0]['fields'] if f['original_name']=='Value')
            raw=source_field(store,field)
            np.testing.assert_array_equal(raw['source_indices'],[1,2])
            np.testing.assert_allclose(raw['x'],[60,120])
            self.assertEqual(field['unit'],'Pa')
            self.assertEqual(next(iter(store.datasets.values())).frame.iloc[0,1],'Pa')
            path=Path(directory)/'datetime.csv'
            path.write_text('Date,Time,Value\n2026-01-01,23:59:59,10\n2026-01-02,00:00:01,20\n')
            store=ChannelStore();ingest(store,path)
            field=next(f for f in inventory_runs(store)[0]['fields'] if f['original_name']=='Value')
            np.testing.assert_allclose(source_field(store,field)['x'],[0,2])
            self.assertEqual(field['clock']['domain'],'absolute')
            self.assertEqual(sum(f['disposition']=='supporting clock' for f in inventory_runs(store)[0]['fields']),2)

    def test_tdms_retains_unsupported_status_metadata_empty_and_native_precision(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'inventory.tdms'
            with TdmsWriter(path) as writer:
                writer.write_segment([
                    RootObject(properties={'Comment':'synthetic inventory'}),
                    GroupObject('Signals',properties={'Bench':'Synthetic'}),
                    ChannelObject('Signals','Time',np.array([0.,1.,2.,3.])),
                    ChannelObject('Signals','New_Value',np.array([5.,6.,7.])),
                    ChannelObject('Signals','New_dTime',np.array([.1,1.1,2.1])),
                    ChannelObject('Signals','New_Status',['OK','BAD','OK']),
                    ChannelObject('Signals','Labels',['warm','cool']),
                    ChannelObject('Signals','Empty',np.array([],float)),
                    ChannelObject('Signals','Integer',np.array([2**63+3,2**63+9],dtype='uint64')),
                ])
            store=ChannelStore();ingest(store,path)
            run=inventory_runs(store)[0];fields={f['original_name']:f for f in run['fields']}
            self.assertEqual(fields['New_Status']['disposition'],'quality/status source')
            np.testing.assert_array_equal(source_field(store,fields['New_Value'])['quality_valid'],[True,False,True])
            self.assertEqual(fields['Empty']['native_samples'],0)
            self.assertEqual(fields['Empty']['disposition'],'invalid')
            self.assertEqual(fields['Labels']['native_samples'],2)
            np.testing.assert_array_equal(source_field(store,fields['Labels'])['values'],['warm','cool'])
            np.testing.assert_array_equal(source_field(store,fields['Integer'])['values'],np.array([2**63+3,2**63+9],dtype='uint64'))
            self.assertEqual(fields['Integer']['dtype'],'uint64')
            self.assertEqual(fields['Comment']['disposition'],'metadata')
            self.assertEqual(source_field(store,fields['Comment'])['values'][0],'synthetic inventory')
            self.assertEqual(fields['Bench']['disposition'],'metadata')
            saved=save_workspace(Path(directory)/'roundtrip.json',store,[])
            restored,_,_=load_workspace(saved)
            restored_fields={f['original_name']:f for f in inventory_runs(restored)[0]['fields']}
            np.testing.assert_array_equal(source_field(restored,restored_fields['Integer'])['values'],source_field(store,fields['Integer'])['values'])
            self.assertEqual(source_field(restored,restored_fields['Bench'])['values'][0],'Synthetic')

    def test_tdms_metadata_only_is_a_valid_inspectable_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'metadata.tdms'
            with TdmsWriter(path) as writer:writer.write_segment([RootObject(properties={'Run':'demo'}),GroupObject('Meta',properties={'Site':'lab'})])
            store=ChannelStore();self.assertEqual(ingest(store,path),[])
            self.assertEqual(len(store.datasets),1)
            fields=inventory_runs(store)[0]['fields']
            self.assertEqual(len(fields),2)
            self.assertTrue(all(f['disposition']=='metadata' for f in fields))

    def test_declared_tdms_complex_vector_and_scaled_reader_arrays_remain_available(self):
        # npTDMS's writer cannot emit every vendor type its reader can return.
        # Exercise the adapter boundary with typed reader arrays, not private data.
        class NativeChannel:
            def __init__(self,name,data,raw=None):
                self.name=name;self.path="/'Vendor'/'"+name+"'";self.properties={}
                self.data=np.array(data);self.raw_data=self.data if raw is None else np.array(raw)
            def __len__(self):return len(self.data)
            def __getitem__(self,key):return self.data[key]
        class NativeGroup:
            name='Vendor';properties={}
            def __init__(self):self.items=[NativeChannel('Complex',[1+2j,3+4j]),NativeChannel('Vector',[[1,2],[3,4]]),NativeChannel('Scaled',[10.,20.],raw=[1,2])]
            def channels(self):return self.items
            def __contains__(self,name):return any(c.name==name for c in self.items)
            def __getitem__(self,name):return next(c for c in self.items if c.name==name)
        class NativeFile:
            properties={}
            def __init__(self):self.group=NativeGroup()
            def groups(self):return [self.group]
            def __getitem__(self,name):return self.group
        with tempfile.TemporaryDirectory() as directory,patch('nptdms.TdmsFile.read',return_value=NativeFile()):
            path=Path(directory)/'vendor.tdms';path.write_bytes(b'synthetic reader boundary')
            store=ChannelStore();ingest(store,path)
            fields={f['original_name']:f for f in inventory_runs(store)[0]['fields']}
            self.assertEqual(fields['Complex']['disposition'],'unsupported')
            self.assertEqual(fields['Vector']['disposition'],'unsupported')
            complex_values=source_field(store,fields['Complex'])['values']
            np.testing.assert_array_equal(complex_values,[1+2j,3+4j])
            vectors=source_field(store,fields['Vector'])['values']
            np.testing.assert_array_equal(vectors,[[1,2],[3,4]])
            self.assertFalse(vectors.flags.writeable)
            scaled=source_field(store,fields['Scaled'])
            np.testing.assert_array_equal(scaled['raw_values'],[1,2])
            np.testing.assert_array_equal(scaled['values'],[10,20])
            self.assertTrue(fields['Scaled']['metadata']['reader_operations'][0]['reader_transformed'])


class ReaderAndSerializationTests(unittest.TestCase):
    def test_malformed_or_cancelled_import_leaves_existing_store_intact(self):
        import threading
        from app_operation_context import operation_context
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'valid.csv';path.write_text('Time,Value\n0,10\n1,20\n')
            store=ChannelStore();ingest(store,path);datasets=set(store.datasets);channels=set(store.channels)
            path=Path(directory)/'invalid.csv';path.write_text('Time,Value\nnot-a-clock,30\ninvalid,40\n')
            with self.assertRaises(ValueError):ingest(store,path)
            self.assertEqual(set(store.datasets),datasets);self.assertEqual(set(store.channels),channels)
            cancel=threading.Event();cancel.set()
            with operation_context(cancel,lambda stage,percent:None):
                with self.assertRaises(InterruptedError):inventory_runs(store)
            self.assertEqual(set(store.datasets),datasets);self.assertEqual(set(store.channels),channels)

    def test_unknown_format_requires_explicit_reader_and_options(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'instrument.unknown';path.write_text('Elapsed;Sensor\n0;1,5\n2;2,5\n')
            with self.assertRaises(UnsupportedFormatError) as error:read_tables(path)
            self.assertEqual(error.exception.result['status'],'unsupported')
            self.assertIn('delimiter',error.exception.result['import_options'])
            store=ChannelStore();ingest(store,path,reader_options={'reader_id':'tabular','delimiter':';','decimal':',',
                'header':0,'time_column':'Elapsed','unit':'s','acquisition_policy':'sampled'})
            channel=next(iter(store.channels.values()))
            np.testing.assert_allclose(channel.y,[1.5,2.5]);np.testing.assert_allclose(channel.x,[0,2/60])

    def test_new_adapter_needs_no_metric_changes_and_accepts_declared_options(self):
        import app_reader_registry as registry
        with patch.dict(registry._READERS,clear=False):
            register_reader(ReaderSpec('synthetic-adapter','7',('.newformat',),
                lambda path,options:[('new',pd.DataFrame({'Custom':[options['gain'],2*options['gain']]}))],{'gain':'gain factor'}))
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'run.newformat';path.write_bytes(b'synthetic opaque input')
                store=ChannelStore();ingest(store,path,reader_options={'gain':3})
                self.assertEqual(inventory_runs(store)[0]['metadata']['reader_version'],'7')
                np.testing.assert_array_equal(next(iter(store.channels.values())).y,[3,6])
            with self.assertRaisesRegex(ValueError,'Duplicate'):register_reader(ReaderSpec('synthetic-adapter','8',('.otherformat',),lambda p,o:[]))

    def test_adapter_native_field_clocks_and_quality_are_not_overwritten(self):
        import app_reader_registry as registry
        def read(path,options):
            frame=pd.DataFrame({'TA':[0.,1.,2.],'A':[10.,20.,30.],
                                'TB':[5.,7.,np.nan],'B':[100.,200.,np.nan],'Q':['OK','BAD',None]})
            frame.attrs['inventory_fields']={
                'TA':{'disposition':'supporting clock'},'TB':{'disposition':'supporting clock'},'Q':{'disposition':'quality/status source'},
                'A':{'clock':'TA','coordinate_unit':'s','clock_description':{'kind':'time','trust':'declared','acquisition_policy':'sampled'}},
                'B':{'clock':'TB','coordinate_unit':'s','length':2,'source_row_positions':[0,1],'status':'Q',
                     'clock_description':{'kind':'time','trust':'declared','acquisition_policy':'sampled'}}}
            return [('native',frame)]
        with patch.dict(registry._READERS,clear=False):
            register_reader(ReaderSpec('native-synthetic','1',('.nativefixture',),read))
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'example.nativefixture';path.write_bytes(b'synthetic')
                store=ChannelStore();ingest(store,path)
                channels={c.name:c for c in store.channels.values()}
                self.assertEqual(set(channels),{'A','B'})
                np.testing.assert_allclose(channels['A'].x,np.array([0,1,2])/60)
                np.testing.assert_allclose(channels['B'].x,np.array([5,7])/60)
                np.testing.assert_allclose(channels['B'].y,[100,np.nan],equal_nan=True)
                fields={f['original_name']:f for f in inventory_runs(store)[0]['fields']}
                self.assertEqual(fields['B']['native_samples'],2)
                self.assertEqual(fields['B']['clock']['trust'],'declared')
                np.testing.assert_array_equal(source_field(store,fields['B'])['values'],[100,200])
                np.testing.assert_array_equal(source_field(store,fields['B'])['quality_valid'],[True,False])

    def test_typed_cells_and_native_metadata_roundtrip_without_pickle(self):
        structured=np.array([(3,[(4.,5.)])],dtype=[('code','i2'),('samples',[('x','f8'),('y','f8')],(1,))])
        vector=np.array([1.,np.nan,3.])
        objects=np.empty(2,dtype=object);objects[:]=[{'state':3},b'\x00\xff']
        for value in [complex(2,-3),b'\x00\xff',np.timedelta64(7,'ms'),np.datetime64('2026-01-01'),vector,objects,structured]:
            restored=decode_cell(json.loads(json.dumps(encode_cell(value))))
            if isinstance(value,np.ndarray):np.testing.assert_equal(restored,value)
            else:self.assertEqual(restored,value)
        with tempfile.TemporaryDirectory() as directory:
            frame=pd.DataFrame({'Vectors':[vector,np.array([9.])],'Complex':[1+2j,3-4j],
                'States':pd.Categorical(['idle','run'],categories=['idle','run','unused'],ordered=True)})
            frame.attrs={'source_raw_arrays':{'vector':structured},'binary':b'\x00\x01'}
            store=ChannelStore();ds=Dataset('Structured',frame);store.datasets[ds.id]=ds
            path=save_workspace(Path(directory)/'snapshot.json',store,[])
            record=json.loads(path.read_text());self.assertEqual(record['source_encoding'],'typed-v1')
            with np.load(path.parent/record['arrays'],allow_pickle=False) as arrays:
                self.assertFalse(any(arrays[key].dtype.hasobject for key in arrays.files))
            restored,_,_=load_workspace(path);out=restored.datasets[ds.id].frame
            np.testing.assert_equal(out.iloc[0,0],vector)
            np.testing.assert_equal(out.attrs['source_raw_arrays']['vector'],structured)
            self.assertEqual(out.attrs['binary'],b'\x00\x01')
            self.assertEqual(list(out['States'].cat.categories),['idle','run','unused'])
            self.assertTrue(out['States'].cat.ordered)

    def test_legacy_workspace_without_typed_encoding_still_loads(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'legacy.json';np.savez(path.with_suffix('.npz'))
            path.write_text(json.dumps({'version':1,'arrays':'legacy.npz','channels':[],
                'datasets':[{'id':'old','name':'old','source':'old.csv','columns':['Value'],'dtypes':['int64'],
                    'index':[{'type':'int','value':0}], 'attributes':{'note':'legacy'},'cells':[[{'type':'int','value':42}]]}],
                'views':[],'ui':{'legacy_setting':True}}))
            store,_,ui=load_workspace(path)
            self.assertEqual(store.datasets['old'].frame.iloc[0,0],42)
            self.assertEqual(store.datasets['old'].frame.attrs['note'],'legacy')
            self.assertTrue(ui['legacy_setting'])


if __name__=='__main__':unittest.main()

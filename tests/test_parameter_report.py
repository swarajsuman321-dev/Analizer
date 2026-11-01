"""Completed records are identical in readable and complete parameter exports."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from app_parameter_contracts import metric_record, result_bundle
from app_parameter_report import build_parameter_evidence, export_parameter_report, _comparison_rows
from app_presentation import CURSOR_COLORS
from app_report_appearance import CURSOR_LINES_OPTION


class ParameterReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.metric=metric_record('generic.peak',12.3456789012345,'raw',run_id='run-a',
            field_id='field-a',sample_count=4,supported_duration_s=3,
            coverage_denominator_s=4,provenance={'source_indices':[0,1,3,4]})
        self.unavailable=metric_record('physical.speed',None,'RPM',status='needs_scaling',
            run_id='run-a',field_id='field-a',
            reasons=['Review source scaling authority before a physical RPM result.'])
        self.bundle=result_bundle('comparison',
            [{'run_id':'run-a','name':'Run A','role':'reference'},
             {'run_id':'run-b','name':'Run B','role':'candidate'}],
            [{'id':'field-a','run_id':'run-a','source_key':'Unfamiliar sensor',
              'original_name':'Unfamiliar sensor','dtype':'float64','unit':'raw',
              'native_samples':5,'disposition':'analysed','metadata':{'inert':'scale_function'}},
             {'id':'field-text','run_id':'run-a','source_key':'Recipe text',
              'original_name':'Recipe text','dtype':'object','disposition':'metadata'}],
            [self.metric,self.unavailable],
            comparisons=[{'metric_id':'generic.peak','reference_metric':self.metric,
                          'candidate_metric':{**self.metric,'run_id':'run-b','value':13.3456789012345},
                          'delta':1.0,'relative_delta_percent':8.1000000729,
                          'status':'computed','acceptance':{'status':'not_evaluated'}}],
            events=[{'event_id':'event-a','name':'Observed activity','start_s':1,'end_s':2,
                     'left_censored':False,'right_censored':True,'onset_bracket_s':[.9,1]}],
            stages=[{'stage_id':'stage-a','name':'Reviewed stage','start_s':0,'end_s':3,
                     'rule':{'version':'1','source':'confirmed stage dictionary'}}],
            pairings=[{'reference_field_id':'field-a','candidate_field_id':'field-b','status':'confirmed'}],
            readiness=[{'metric_id':'physical.speed','status':'needs_scaling',
                        'reason':'Review source scaling authority before a physical RPM result.',
                        'remedy':'Confirm one documented transform.'}],
            quality=[{'field_id':'field-a','invalid_samples':1}],
            provenance={'engine_version':'synthetic-v2','source_clock':'declared seconds'},
            plot_series=[{'label':'Unfamiliar sensor','original_x':[10,11,12,13],
                          'aligned_x':[0,1,2,3],'y':[1,None,3,12.3456789012345],
                          'coordinate_unit':'s','unit':'raw','source_indices':[0,1,3,4],
                          'cursors':[1,2],'cursor_mode':'dual',
                          'cursor_markers':[{'cursor_index':0,'x':1,'y':1}]}])

    def test_real_pdf_workbook_json_share_the_completed_records_and_reasons(self):
        from matplotlib.backends.backend_pdf import PdfPages
        from matplotlib.text import Text
        before=deepcopy(self.bundle);original=PdfPages.savefig;content=[];plots=[];sizes=[]
        def inspect(pdf,figure,*args,**kwargs):
            content.extend(item.get_text() for item in figure.findobj(Text))
            sizes.append(list(figure.get_size_inches()))
            for axis in figure.axes:
                if axis.lines:plots.append([(list(line.get_xdata()),line.get_color()) for line in axis.lines])
            return original(pdf,figure,*args,**kwargs)
        with patch.object(PdfPages,'savefig',inspect):
            result=export_parameter_report(self.root/'Parameters.pdf',self.bundle)
        self.assertEqual(self.bundle,before)
        evidence=json.loads(Path(result['evidence']).read_text())
        for key,value in before.items():self.assertEqual(evidence[key],value)
        self.assertEqual(Path(result['pdf']).read_bytes()[:5],b'%PDF-')
        sheets=pd.read_excel(result['workbook'],sheet_name=None)
        self.assertTrue({'Runs','Parameter inventory','Metrics','Comparisons','Events','Stages',
                         'Pairings','Readiness','Quality','Provenance','Plot series'}<=set(sheets))
        self.assertEqual(sheets['Metrics'].iloc[0].value,self.metric['value'])
        self.assertEqual(json.loads(sheets['Metrics'].iloc[1].reasons),self.unavailable['reasons'])
        self.assertEqual(json.loads(sheets['Comparisons'].iloc[0].reference_metric),self.metric)
        self.assertEqual(list(sheets['Parameter inventory'].original_name),['Unfamiliar sensor','Recipe text'])
        self.assertEqual(json.loads(sheets['Plot series'].iloc[0].source_indices),[0,1,3,4])
        joined='\n'.join(content)
        for value in ('12.3456789012345',self.unavailable['reasons'][0],'Confirm one documented transform.',
                      'Recipe text','Original acquisition coordinates','Declared aligned coordinates',
                      'Observed event raster','Declared stage timeline'):
            self.assertIn(value,joined)
        for section in ('1. Overview and review','2. Graphs','3. Measurements and comparisons',
                        '4. Quality, inventory and readiness'):
            self.assertIn(section,joined)
        self.assertTrue(all(np.allclose(size,[8.27,11.69]) for size in sizes))
        self.assertTrue(all(color not in CURSOR_COLORS for lines in plots for _,color in lines))
        projected=[coordinates for lines in plots for coordinates,color in lines if color=='#075985']
        self.assertIn([10,11,12,13],projected)
        self.assertIn([0,1,2,3],projected)

    def test_cursor_opt_in_changes_only_plot_overlays_and_respects_point_mode(self):
        from matplotlib.backends.backend_pdf import PdfPages
        original=PdfPages.savefig;states=[]
        def inspect(pdf,figure,*args,**kwargs):
            for axis in figure.axes:
                lines=[line for line in axis.lines if line.get_color() in CURSOR_COLORS]
                if lines:states.append((len(lines),len(axis.collections)))
            return original(pdf,figure,*args,**kwargs)
        self.bundle['plot_series'][0]['cursor_mode']='point'
        with patch.object(PdfPages,'savefig',inspect):
            shown=export_parameter_report(self.root/'Shown.pdf',self.bundle,
                                          metadata={CURSOR_LINES_OPTION:True})
        self.assertEqual(states,[(1,1),(1,1)])
        evidence=json.loads(Path(shown['evidence']).read_text())
        self.assertEqual(evidence['metrics'],self.bundle['metrics'])
        self.assertEqual(evidence['plot_series'],self.bundle['plot_series'])

    def test_complete_long_inventory_metadata_and_literal_notes_survive_direct_workbook(self):
        long_note='start '+('reviewed metadata '*2000)+' end'
        self.bundle['inventory'][0]['metadata']['long_note']=long_note
        result=export_parameter_report(self.root/'Parameters.xlsx',self.bundle,
                                       metadata={'Observations':'=SUM(1,2)'})
        sheets=pd.read_excel(result['workbook'],sheet_name=None)
        self.assertIn('Extended text',sheets)
        rows=sheets['Extended text']
        extended=''.join(rows[rows.Sheet=='Parameter inventory'].sort_values('Part').Text)
        self.assertEqual(json.loads(extended)['long_note'],long_note)
        self.assertEqual(sheets['Report details'].set_index('Field').loc['Metadata.Observations','Value'],'=SUM(1,2)')
        self.assertEqual(json.loads(Path(result['evidence']).read_text())['inventory'],self.bundle['inventory'])
        self.assertIsNone(result['pdf'])

    def test_failed_bundle_keeps_existing_outputs_together(self):
        paths=[self.root/'Existing.pdf',self.root/'Existing.xlsx',self.root/'Existing.evidence.json']
        for path in paths:path.write_bytes(b'previous '+path.suffix.encode())
        before={path:path.read_bytes() for path in paths}
        with patch('app_parameter_report.render_parameter_pdf',side_effect=OSError('Disk full')):
            with self.assertRaisesRegex(OSError,'Disk full'):
                export_parameter_report(paths[0],self.bundle)
        self.assertEqual({path:path.read_bytes() for path in paths},before)
        self.assertEqual(sorted(path.name for path in self.root.iterdir()),sorted(path.name for path in paths))

    def test_result_schema_is_explicit_and_json_only_export_preserves_all_records(self):
        with self.assertRaisesRegex(ValueError,'version-2'):
            build_parameter_evidence({'schema_version':1,'kind':'comparison'})
        result=export_parameter_report(self.root/'Only.json',self.bundle)
        self.assertIsNone(result['pdf']);self.assertIsNone(result['workbook'])
        evidence=json.loads(Path(result['evidence']).read_text())
        self.assertEqual(evidence['comparisons'],self.bundle['comparisons'])

    def test_invalid_nonfinite_completed_result_is_rejected_without_rewriting_it(self):
        # A result producer must supply null + a reason for unavailable values.
        # Export cannot silently make a different result out of a NaN value.
        self.bundle['metrics'][0]['value']=float('nan')
        existing=self.root/'Existing.json';existing.write_text('previous',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'NaN or infinity'):
            export_parameter_report(existing,self.bundle)
        self.assertTrue(np.isnan(self.bundle['metrics'][0]['value']))
        self.assertEqual(existing.read_text(),'previous')

    def test_typed_comparison_rows_use_engine_units_and_leave_categorical_delta_unavailable(self):
        self.bundle['comparisons']=[
            {'comparison_type':'full_scope_metric','metric_id':'minimum',
             'reference_metric':{'value':20,'unit':'°C'},
             'candidate_metric':{'value':77,'unit':'°F'},
             'candidate_in_reference_unit':25,'unit':'°C','delta_unit':'°C','delta':5,
             'relative_percent':None,'relative_reason':'Absolute temperature has no relative change',
             'conversion':{'source_unit':'°F','target_unit':'°C'},'status':'computed'},
            {'comparison_type':'full_scope_metric','metric_id':'duty_fraction',
             'reference_metric':{'value':.4,'unit':'fraction'},
             'candidate_metric':{'value':.5,'unit':'fraction'},
             'unit':'fraction','delta_unit':'percentage points','delta':10,
             'relative_percent':None,'status':'computed'},
            {'comparison_type':'full_scope_metric','metric_id':'state.label',
             'reference_metric':{'value':'idle','unit':''},
             'candidate_metric':{'value':'ready','unit':''},
             'delta':None,'delta_semantics':'categorical equality only','status':'computed'},
            {'comparison_type':'common_window_analog','unit':'RPM',
             'supported_duration_s':12,'coverage_fraction':.75,'mean_bias':2,'mae':3,
             'rmse':4,'max_absolute_difference':8,'absolute_difference_area':36,
             'area_unit':'RPM·s','status':'computed'},
            {'comparison_type':'common_window_state','supported_duration_s':12,
             'agreement_duration_s':8,'mismatch_duration_s':4,'agreement_fraction':2/3,
             'status':'computed'}]
        rows=_comparison_rows(self.bundle)
        temperature=rows[0]
        self.assertEqual(temperature['Run A'],'20 °C')
        self.assertEqual(temperature['Run B'],'25 °C')
        self.assertIn('77 °F',temperature['Evidence / comparability'])
        self.assertEqual(temperature['Delta / error'],5)
        self.assertEqual(temperature['Relative'],'Not applicable')
        self.assertEqual(rows[1]['Unit'],'percentage points')
        self.assertEqual(rows[1]['Run A'],'0.4 fraction')
        self.assertIsNone(rows[2]['Delta / error'])
        pointwise={row['Measure']:row for row in rows[3:]}
        self.assertEqual(pointwise['Root mean square difference']['Delta / error'],4)
        self.assertEqual(pointwise['Absolute difference area']['Unit'],'RPM·s')
        self.assertEqual(pointwise['State mismatch duration']['Delta / error'],4)
        self.assertFalse(any('_signed_change' in row for row in rows[3:]))

    def test_explicit_pairs_overlay_without_merging_native_coordinates(self):
        from matplotlib.backends.backend_pdf import PdfPages
        original=PdfPages.savefig;plots=[]
        self.bundle['plot_series']=[
            {'field_id':'field-a','label':'Reference','original_x':[10,11,13],
             'aligned_x':[0,1,3],'y':[1,2,3],'coordinate_unit':'s','unit':'raw','structure':'binary'},
            {'field_id':'field-b','label':'Candidate','original_x':[100,102,103,104],
             'aligned_x':[0,2,3,4],'y':[0,1,0,1],'coordinate_unit':'s','unit':'raw','structure':'binary'}]
        self.bundle['pairings'][0]['confirmed']=True
        def inspect(pdf,figure,*args,**kwargs):
            for axis in figure.axes:
                if axis.lines and axis.get_title(loc='left') in ('Original acquisition coordinates','Declared aligned coordinates'):
                    plots.append([(list(line.get_xdata()),line.get_drawstyle()) for line in axis.lines])
            return original(pdf,figure,*args,**kwargs)
        with patch.object(PdfPages,'savefig',inspect):
            exported=export_parameter_report(self.root/'Paired.pdf',self.bundle)
        self.assertEqual(len(plots),2)
        self.assertEqual([item[0] for item in plots[0]],[[10,11,13],[100,102,103,104]])
        self.assertEqual([item[0] for item in plots[1]],[[0,1,3],[0,2,3,4]])
        self.assertTrue(all(style=='steps-post' for plot in plots for _,style in plot))
        evidence=json.loads(Path(exported['evidence']).read_text())
        self.assertEqual(evidence['plot_series'],self.bundle['plot_series'])

    def test_large_event_display_is_bounded_while_complete_records_and_readiness_survive(self):
        from matplotlib.backends.backend_pdf import PdfPages
        from matplotlib.text import Text
        original=PdfPages.savefig;content=[];page_count=[];markers=[]
        self.bundle['plot_series']=[]
        self.bundle['events']=[{'event_id':f'event-{i}','field_id':'field-a','type':'active_episode',
            'start_s':i*3,'end_s':i*3+1,'left_censored':i==0,'right_censored':i==2004}
            for i in range(2005)]
        self.bundle['readiness'].append({'metric_id':'state.duty','status':'needs_mapping',
                                         'reason':'No reviewed state dictionary.'})
        def inspect(pdf,figure,*args,**kwargs):
            page_count.append(1)
            content.extend(item.get_text() for item in figure.findobj(Text))
            markers.extend(line.get_marker() for axis in figure.axes for line in axis.lines)
            return original(pdf,figure,*args,**kwargs)
        with patch.object(PdfPages,'savefig',inspect):
            result=export_parameter_report(self.root/'Large.pdf',self.bundle)
        evidence=json.loads(Path(result['evidence']).read_text())
        self.assertEqual(evidence['events'],self.bundle['events'])
        self.assertLess(len(page_count),25)
        self.assertIn('<',markers)
        joined='\n'.join(content)
        self.assertIn('first 2000 of 2005',joined)
        self.assertIn('No reviewed state dictionary.',joined)
        self.assertIn('Review the field structure, semantic role and any required state dictionary.',joined)
        self.assertIn('unshaded time does not imply OFF',joined)


if __name__=='__main__':unittest.main()

"""Cursor overlays are export-only choices; their measurement evidence is unchanged."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from app_channel_store import Channel, ChannelStore
from app_comparison_report import export_comparison_bundle
from app_presentation import CURSOR_COLORS
from app_report_appearance import CURSOR_LINES_OPTION
from app_reporting import export_report, interval_tables
from app_workspace_io import render_report


def plot_state(figure):
    """Inspect actual artists before the real writer clears its figure."""
    cursor_lines=[];cursor_labels=[];markers=[];traces=[];annotations=[]
    for axis in figure.axes:
        for line in axis.lines:
            if line.get_color() in CURSOR_COLORS:cursor_lines.append(list(line.get_xdata()))
            elif line.get_label()=='Signal':traces.append(list(line.get_ydata()))
            elif line.get_color()=='purple':annotations.append(line.get_linestyle())
        cursor_labels.extend(item.get_text() for item in axis.texts
                             if item.get_text().startswith(('A ', 'B ')))
        markers.extend(collection.get_offsets().tolist() for collection in axis.collections)
    return {'lines':cursor_lines,'labels':cursor_labels,'markers':markers,
            'traces':traces,'annotations':annotations}


class ExportCursorAppearanceTests(unittest.TestCase):
    def test_engineering_pdf_hides_only_cursor_artists_and_retains_both_values(self):
        from matplotlib.backends.backend_pdf import PdfPages
        from tests.test_engineering_report_details import EngineeringReportDetailsTests
        from app_engineering_reports import export_engineering
        store,runs,comparison,selected=EngineeringReportDetailsTests().fixture(count=1,comparison=False)
        original=PdfPages.savefig
        appearances=[];evidence=[]
        for shown in (False,True):
            artists=[]
            def inspect(pdf,figure,*args,**kwargs):
                artists.extend(line.get_color() for axis in figure.axes for line in axis.lines
                               if line.get_color() in CURSOR_COLORS)
                return original(pdf,figure,*args,**kwargs)
            path=self.root/('Engineering-'+str(shown)+'.pdf')
            with patch.object(PdfPages,'savefig',inspect):
                export_engineering(path,store,runs,comparison,
                    {CURSOR_LINES_OPTION:shown,'Report ID':'export-appearance-test'},
                    {'cursors':[1.,4.],'cursor_mode':'dual','snap':True},selected_ids=selected)
            appearances.append(artists)
            evidence.append(json.loads(path.with_suffix('.evidence.json').read_text())['metadata']['Cursor interval evidence'])
        self.assertEqual(appearances[0],[])
        self.assertTrue(appearances[1])
        self.assertEqual(evidence[0],evidence[1])
        self.assertEqual(evidence[0][0]['A_value'],1.)
        self.assertEqual(evidence[0][0]['B_value'],4.)

    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root=Path(self.temporary.name)
        self.store=ChannelStore()
        self.channel=self.store.add(Channel('Signal',[0,1,2,3,4],[2,4,8,16,32],unit='V',
            raw_y=[20,40,80,160,320],attributes={'plot_style':{'color':'#075985'}}))
        self.workspace={'layout':'Single','panes':[{
            'ids':[self.channel.id],'range':[[0,4],[0,35]],'cursors':[1,3],
            'cursor_mode':'dual','cursor_locks':[{'channel':self.channel.id,'index':1},
                                               {'channel':self.channel.id,'index':3}],
            'annotations':[{'kind':'Event','start':2,'text':'Retain annotation'},
                           {'kind':'Threshold','start':10}]}]}

    def render(self, suffix, metadata=None):
        from matplotlib.figure import Figure
        original=Figure.savefig;states=[]
        def inspect(figure,*args,**kwargs):
            states.append(plot_state(figure))
            return original(figure,*args,**kwargs)
        path=self.root/('Analysis'+suffix)
        with patch.object(Figure,'savefig',inspect):
            statistics=render_report(path,self.store,self.workspace,metadata=metadata)
        self.assertGreater(path.stat().st_size,100)
        return states[-1],statistics

    def test_analysis_saved_formats_default_to_clean_plots_and_identical_statistics(self):
        before=deepcopy(self.workspace)
        data,summary=interval_tables(self.store,self.workspace)
        for suffix in ('.pdf','.png','.svg'):
            with self.subTest(suffix=suffix):
                state,statistics=self.render(suffix)
                self.assertEqual(state['lines'],[])
                self.assertEqual(state['labels'],[])
                self.assertEqual(state['markers'],[])
                self.assertEqual(state['traces'],[[2,4,8,16,32]])
                self.assertEqual(len(state['annotations']),2)
                pd.testing.assert_frame_equal(pd.DataFrame(statistics),summary)
        after_data,after_summary=interval_tables(self.store,self.workspace)
        pd.testing.assert_frame_equal(after_data,data)
        pd.testing.assert_frame_equal(after_summary,summary)
        np.testing.assert_array_equal(data.original_value,[40,80,160])
        self.assertEqual(self.workspace,before)

    def test_explicit_opt_in_respects_dual_point_and_off_without_changing_statistics(self):
        for mode,count in (('dual',2),('point',1),('off',0)):
            with self.subTest(mode=mode):
                self.workspace['panes'][0]['cursor_mode']=mode
                clean,statistics=self.render('.svg')
                shown,shown_statistics=self.render('.svg',{CURSOR_LINES_OPTION:True})
                self.assertEqual(clean['lines'],[])
                self.assertEqual(len(shown['lines']),count)
                self.assertEqual(len(shown['labels']),count)
                self.assertEqual(len(shown['markers']),count)
                pd.testing.assert_frame_equal(pd.DataFrame(statistics),pd.DataFrame(shown_statistics))
                self.assertEqual(self.workspace['panes'][0]['cursor_mode'],mode)

    def test_analysis_export_forwards_the_explicit_option_to_the_saved_png(self):
        from matplotlib.figure import Figure
        original=Figure.savefig;states=[]
        def inspect(figure,*args,**kwargs):
            states.append(plot_state(figure))
            return original(figure,*args,**kwargs)
        with patch.object(Figure,'savefig',inspect):
            export_report(self.root/'clean.png',self.store,self.workspace)
            export_report(self.root/'shown.png',self.store,self.workspace,
                          metadata={CURSOR_LINES_OPTION:True})
        self.assertEqual(len(states[0]['lines']),0)
        self.assertEqual(len(states[1]['lines']),2)
        self.assertEqual((self.root/'shown.png').read_bytes()[:8],b'\x89PNG\r\n\x1a\n')

    def test_comparison_pdf_and_companions_keep_cursor_evidence_for_both_appearances(self):
        from matplotlib.backends.backend_pdf import PdfPages
        original=PdfPages.savefig;states=[]
        def inspect(pdf,figure,*args,**kwargs):
            if any('original workspace coordinates' in item.get_text() for item in figure.texts):
                states.append(plot_state(figure))
            return original(pdf,figure,*args,**kwargs)
        before=deepcopy(self.workspace)
        evidence=[]
        with patch.object(PdfPages,'savefig',inspect):
            for show in (False,True):
                result=export_comparison_bundle(self.root/('Shown.pdf' if show else 'Clean.pdf'),
                    self.store,self.workspace,{CURSOR_LINES_OPTION:show})
                evidence.append(json.loads(Path(result['evidence']).read_text()))
                self.assertEqual(Path(result['pdf']).read_bytes()[:5],b'%PDF-')
                sheets=pd.read_excel(result['workbook'],sheet_name=None)
                self.assertEqual(sheets['Cursor summary'].iloc[0].cursor_A_X,1)
                self.assertEqual(sheets['Cursor summary'].iloc[0].cursor_B_X,3)
                np.testing.assert_array_equal(sheets['Active interval'].original_value,[40,80,160])
        self.assertEqual(len(states[0]['lines']),0)
        self.assertEqual(states[0]['labels'],[])
        self.assertEqual(states[0]['markers'],[])
        self.assertEqual(len(states[1]['lines']),2)
        self.assertEqual(len(states[1]['labels']),2)
        self.assertEqual(len(states[1]['markers']),2)
        for key in ('workspace','cursor_summary','raw_interval_samples'):
            self.assertEqual(evidence[0][key],evidence[1][key])
        self.assertEqual(evidence[0]['workspace'],before)
        self.assertEqual(self.workspace,before)


if __name__=='__main__':unittest.main()

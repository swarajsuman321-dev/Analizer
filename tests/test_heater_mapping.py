import unittest
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from app_simulation import CSV_LEGEND_SPECS
from app_comparator import ComparisonEngine
from app_inspection import comparison_traces, sample_trace, format_comparison_samples


class HeaterTests(unittest.TestCase):
    def setUp(self):
        curve=pd.DataFrame({'time_min':[0,1,2,3], 'value':[0,2000,2000,0]})
        curve.attrs.update(source_type='csv',unit='W',x_calibration_verified=True,y_calibration_verified=True)
        self.curves={'heater_power':curve}
        self.spec=next(s for s in CSV_LEGEND_SPECS if s['key']=='heater_power')

    def tearDown(self): plt.close('all')

    def bench(self, values=None):
        return pd.DataFrame({'time_min':[0,1,2,3], 'heat valve':values or ['OFF','ON','ON','OFF']})

    def test_state_aliases_words_numbers_and_unknown(self):
        for name,values in [('heat valve',['OFF','ON','ON','OFF']),
                            ('heater relay',[False,True,True,False]),
                            ('heater status',[0,1,1,0]),('heater_power',[0,1,1,0])]:
            frame=pd.DataFrame({'time_min':[0,1,2,3],name:values})
            cols=ComparisonEngine.find_bench_columns(frame,CSV_LEGEND_SPECS)
            self.assertEqual(cols['heater_power'],name)
            self.assertEqual(ComparisonEngine._bench_values(frame,'heater_power',name).tolist(),[0,1,1,0])
        frame=self.bench(['OFF','ON',np.nan,'invalid'])
        values=ComparisonEngine._bench_values(frame,'heater_power','heat valve')
        self.assertTrue(values.iloc[2:].isna().all())

    def test_cursor_state_matching_preserves_watts_and_steps(self):
        frame=self.bench()
        cols=ComparisonEngine.find_bench_columns(frame,CSV_LEGEND_SPECS)
        traces=comparison_traces(frame,self.curves,cols,CSV_LEGEND_SPECS)['heater_power']
        self.assertEqual(sample_trace(traces['sim'],.5),0)
        self.assertEqual(sample_trace(traces['sim'],1.5),2000)
        self.assertEqual(sample_trace(traces['bench'],1.5),1)
        self.assertEqual(format_comparison_samples(self.spec,2000,1,traces['bench_kind']),
                         ('2000.00 W · ON','ON','MATCH'))
        self.assertEqual(format_comparison_samples(self.spec,2000,0,'digital')[2],'DIFFERENT')
        self.assertEqual(format_comparison_samples(self.spec,0,0,'digital')[2],'MATCH')
        self.assertEqual(format_comparison_samples(self.spec,2000,np.nan,'digital')[2],'—')

    def test_watts_and_state_use_separate_axes(self):
        fig,axes,twins,error=ComparisonEngine.render_comparison_figure(self.bench(),self.curves)
        self.assertIsNone(error)
        self.assertEqual(len(twins),1)
        self.assertEqual(axes[-1].lines[0].get_ydata().max(),2000)
        self.assertEqual(twins[0].lines[0].get_ydata().max(),1)
        self.assertEqual([tick.get_text() for tick in twins[0].get_yticklabels()],['OFF','ON'])
        fig.canvas.draw()
        self.assertAlmostEqual(axes[-1].transData.transform((1,2000))[1], twins[0].transData.transform((1,1))[1])
        visible={'heater_power':{'sim':False,'bench':True},'actual_remaining_time':{'sim':False,'bench':False}}
        fig,axes,twins,error=ComparisonEngine.render_comparison_figure(self.bench(),self.curves,visible)
        self.assertEqual(len(axes),1);self.assertEqual(len(twins),1)
        self.assertEqual(axes[0].get_ylabel(),'')
        fig.canvas.draw()

    def test_measured_bench_watts_stay_watts(self):
        frame=pd.DataFrame({'time_min':[0,1,2,3],'heater power [W]':[0,1900,1950,0]})
        self.assertFalse(ComparisonEngine.heater_bench_is_state(frame,'heater power [W]'))
        values=ComparisonEngine._bench_values(frame,'heater_power','heater power [W]')
        self.assertEqual(values.max(),1950)
        self.assertEqual(format_comparison_samples(self.spec,2000,1950,'analog')[2],'-50.00 W')

    def test_export_states_and_heating_duration_do_not_invent_bench_watts(self):
        frame=self.bench()
        report=ComparisonEngine.heater_state_report(frame,self.curves)
        bench=report[report.source=='Bench']
        self.assertEqual(bench.heater_on.tolist(),[0,1,1,0])
        self.assertTrue(bench.recorded_power_W.isna().all())
        self.assertEqual(report[report.source=='Simulation'].recorded_power_W.max(),2000)
        card=ComparisonEngine.generate_scorecard(frame,self.curves).set_index('parameter')
        self.assertEqual(card.loc['Total Heating Active Duration','sim_val'],'2.00 min')
        self.assertEqual(card.loc['Total Heating Active Duration','raw_val'],'2.00 min')
        self.assertFalse(any('heat valve: comparison assumes W' in x for x in card.attrs['assumptions']))

    def test_pressure_default_respects_declared_units_and_pulse_channels(self):
        frame=pd.DataFrame({'water pressure':[0,500],'water pressure [mbar]':[0,5],
                            'water pressure [µs]':[1600,1700]})
        ComparisonEngine.apply_pressure_default(frame,'Pa')
        self.assertEqual(frame.attrs['column_units']['water pressure'],'Pa')
        self.assertNotIn('water pressure [mbar]',frame.attrs['column_units'])
        self.assertNotIn('water pressure [µs]',frame.attrs['column_units'])


if __name__=='__main__':unittest.main()

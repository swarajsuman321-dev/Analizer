"""Hand-calculated, native-clock evidence and sequence correspondence cases."""
import copy
import unittest

import numpy as np

from app_parameter_events import (state_timeline, actuator_relationships,
                                  analyse_relationships, event_registry)
from app_parameter_stages import (resolve_stages, assign_events_to_stages,
                                  match_sequences, StageResolverRegistry)


def projection(x,y,**extra):
    return dict(x_s=np.array(x,float),values=np.array(y),valid=np.ones(len(y),bool),
                structure='binary',acquisition_policy={'mode':'held'},**extra)


def event(identifier,a,b,kind='pulse',**extra):
    return dict(id=identifier,type=kind,onset_s=a,offset_s=b,**extra)


class NativeStateTests(unittest.TestCase):
    def test_three_valves_exact_half_open_occupancy_and_orders(self):
        x=np.arange(8)
        p={str(i):projection(x,((x>=a)&(x<b)).astype(int))
           for i,(a,b) in enumerate([(1,4),(2,5),(3,6)])}
        before=copy.deepcopy(p)
        r=actuator_relationships(p)
        self.assertEqual([t['summary']['on_duration_s'] for t in r['timelines'].values()],[3,3,3])
        self.assertEqual([q['duration_s'] for q in r['overlaps']],[2,1,2])
        self.assertEqual(r['all_on_duration_s'],1)
        self.assertEqual(r['union_duration_s'],5)
        self.assertEqual(r['shared_supported_duration_s'],7)
        self.assertEqual([t['summary']['rising_count'] for t in r['timelines'].values()],[1,1,1])
        self.assertTrue(all(q['status']=='indeterminate' for q in r['order']))
        for q in p.values():q['acquisition_policy']['mode']='event'
        exact=actuator_relationships(p)
        self.assertTrue(all(q['status']=='ordered' for q in exact['order']))
        for name in before:
            np.testing.assert_array_equal(before[name]['values'],p[name]['values'])

    def test_initial_final_and_missing_support_are_censored(self):
        r=state_timeline([0,1,2,3,4,5,6],[1,1,0,1,1,1,1],
            valid=[1,1,1,0,1,1,1],acquisition_policy={'mode':'held'})
        first,last=r['events']
        self.assertTrue(first['left_censored']);self.assertFalse(first['right_censored'])
        self.assertTrue(last['left_censored']);self.assertTrue(last['right_censored'])
        self.assertEqual(r['summary']['rising_count'],0)
        self.assertEqual(r['summary']['observed_onset_count'],0)
        self.assertEqual(r['summary']['on_duration_s'],4)
        self.assertEqual(r['summary']['supported_duration_s'],4)
        self.assertEqual(r['summary']['duty_cycle'],1)
        self.assertEqual(r['supported_intervals'],[[0.,2.],[4.,6.]])

    def test_gap_does_not_create_new_activation(self):
        r=state_timeline([0,1,10,11,12],[0,1,1,1,0],
            acquisition_policy={'mode':'held','max_gap_seconds':2})
        self.assertEqual(r['summary']['observed_onset_count'],1)
        self.assertTrue(r['events'][0]['right_censored'])
        self.assertTrue(r['events'][1]['left_censored'])
        self.assertEqual(r['summary']['on_duration_s'],2)
        self.assertEqual(r['summary']['supported_duration_s'],3)

    def test_sample_only_counts_do_not_manufacture_seconds(self):
        r=state_timeline(None,[0,1,1,0,1],valid=[1,1,1,0,1])
        self.assertIsNone(r['summary']['on_duration_s'])
        self.assertIsNone(r['summary']['duty_cycle'])
        self.assertEqual(r['summary']['rising_count'],1)
        self.assertEqual(r['summary']['episode_count'],2)
        self.assertFalse(r['events'])
        self.assertTrue(all(row['duration_s'] is None for row in r['occupancy']))

    def test_duplicate_clock_requires_policy_and_backwards_is_unavailable(self):
        r=state_timeline([0,1,1,2],[0,1,0,0])
        self.assertFalse(r['intervals'])
        self.assertEqual(r['readiness'][0]['status'],'needs_review')
        first=state_timeline([0,1,1,2],[0,1,0,0],acquisition_policy={'mode':'held','duplicate_clock':'first'})
        last=state_timeline([0,1,1,2],[0,1,0,0],acquisition_policy={'mode':'held','duplicate_clock':'last'})
        self.assertEqual(first['summary']['on_duration_s'],1)
        self.assertEqual(last['summary']['on_duration_s'],0)
        reverse=state_timeline([0,2,1],[0,1,0])
        self.assertFalse(reverse['events'])
        self.assertEqual(reverse['readiness'][0]['status'],'invalid')

    def test_nonzero_codes_require_explicit_policy_and_on_values_normalise_numbers(self):
        self.assertFalse(state_timeline([0,1,2],[0,10,0])['events'])
        r=state_timeline([0,1,2],[0.,10.,0.],on_values=[10])
        self.assertEqual(r['summary']['on_duration_s'],1)
        r=state_timeline([0,1,2,3],[0,-5,6,0],parameters={'nonzero_is_on':True})
        self.assertEqual(r['summary']['on_duration_s'],2)
        self.assertEqual(r['summary']['rising_count'],1)

    def test_event_filter_retains_raw_occupancy_and_suppression_evidence(self):
        r=state_timeline([0,1,2,3,4,5],[0,1,0,1,1,0],parameters={'min_dwell_s':1.5})
        self.assertEqual(r['summary']['on_duration_s'],3)
        self.assertEqual(r['summary']['rising_count'],2)
        self.assertEqual(len(r['events']),1)
        self.assertEqual(len(r['suppressed_events']),1)
        self.assertEqual(r['events'][0]['confirmation_s'],4.5)
        self.assertEqual(r['events'][0]['onset_s'],3)

    def test_clock_uncertainty_does_not_claim_order(self):
        p={'a':projection([0,1,2,3],[0,1,0,0]),
           'b':projection([0,1.1,2,3],[0,1,0,0])}
        for row in p.values():row['acquisition_policy']={'mode':'event','timing_uncertainty_s':.1}
        r=actuator_relationships(p)
        self.assertEqual(r['order'][0]['status'],'indeterminate')
        self.assertAlmostEqual(r['order'][0]['delay_bounds_s'][0],-.1)
        self.assertEqual(r['timelines']['a']['events'][0]['onset_bracket_s'],[.9,1.1])

    def test_enum_occupancy_and_transitions_never_average_codes(self):
        r=state_timeline([0,1,3,4],[3,7,7,3],structure='enum',dictionary={'3':'alpha','7':'beta'},acquisition_policy='held')
        self.assertEqual(r['summary']['state_sequence'],[3,7,3])
        self.assertEqual({q['label']:q['duration_s'] for q in r['occupancy']},{'alpha':1,'beta':3})
        self.assertNotIn('mean',r['summary'])
        self.assertEqual(r['summary']['transition_count'],2)

    def test_relationships_require_review_and_use_shared_support(self):
        p={'a':projection([0,1,2,3],[0,1,1,0]),
           'b':projection([0,1,2,3],[0,0,1,0])}
        r=analyse_relationships(p,[{'operation':'state_mismatch','fields':['a','b']}])
        self.assertFalse(r['metrics'])
        r=analyse_relationships(p,[{'id':'command_feedback','operation':'state_mismatch','fields':['a','b'],'reviewed':True,'timing_compatible':True}])
        self.assertEqual(r['metrics'][0]['value'],1)
        self.assertEqual(r['metrics'][0]['supported_duration_s'],3)
        self.assertIn('cause is not established',r['metrics'][0]['observation'])

    def test_no_shared_support_is_not_zero_disagreement(self):
        p={'a':projection([0,1],[0,1]),'b':projection([2,3],[0,1])}
        r=analyse_relationships(p,[{'id':'mismatch','operation':'state_mismatch',
            'fields':['a','b'],'reviewed':True,'timing_compatible':True}])
        self.assertIsNone(r['metrics'][0]['value'])
        self.assertEqual(r['metrics'][0]['status'],'insufficient_data')

    def test_response_window_does_not_bridge_invalid_gap(self):
        p={'command':projection([0,1,2,3,4],[0,1,1,0,0]),
           'sensor':projection([0,1,2,3,4],[0,0,100,100,100])}
        p['sensor']['structure']='analog';p['sensor']['valid'][2]=False
        rule={'operation':'response_delay','fields':['command','sensor'],'reviewed':True,
              'timing_compatible':True,'units_compatible':True,'window_s':3,'threshold':20}
        r=analyse_relationships(p,[rule])
        self.assertIsNone(r['metrics'][0]['value'])
        self.assertEqual(r['metrics'][0]['status'],'partial')
        p['sensor']['valid'][2]=True
        r=analyse_relationships(p,[rule])
        self.assertEqual(r['metrics'][0]['value'],1)
        self.assertEqual(r['metrics'][0]['boundary_uncertainty']['response'],[1.,2.])

    def test_merged_event_keeps_component_brackets(self):
        r=state_timeline([0,1,2,3,4,5],[0,1,0,1,0,0],parameters={'merge_gap_s':1})
        self.assertEqual(len(r['events']),1)
        event=r['events'][0]
        self.assertEqual(event['duration_s'],3)
        self.assertEqual(event['active_duration_s'],2)
        self.assertEqual(event['components'][0]['brackets']['offset_s'],[1.,2.])
        self.assertEqual(event['brackets']['offset_s'],[3.,4.])

    def test_trusted_detector_registration_failure_isolation_and_restore(self):
        registry=event_registry().clone()
        saved=registry.snapshot()
        registry.register('custom.observed','1',lambda p,params:dict(events=[event('custom',1,2)],readiness=[]),trusted=True,structures=['binary'])
        p=projection([0,1,2],[0,1,0]);p['field_id']='customfield'
        r=registry.detect('custom.observed',p)
        self.assertEqual(r['events'][0]['detector_version'],'1')
        self.assertEqual(r['events'][0]['field_id'],'customfield')
        registry.register('broken','1',lambda *args:1/0,trusted=True)
        self.assertEqual(registry.detect('broken',p)['readiness'][0]['status'],'error')
        self.assertTrue(registry.detect('native_state_timeline',p)['events'])
        with self.assertRaises(ValueError):registry.register('source.function','1',lambda *a:None)
        registry.restore(saved)
        self.assertEqual(registry.detect('custom.observed',p)['readiness'][0]['status'],'unsupported')


class StageTests(unittest.TestCase):
    def test_documented_codes_repeated_instances_unknown_preserved_and_priority(self):
        p=projection([0,1,2,3,4,5,6],[0,1,1,2,1,1,0]);p['structure']='enum'
        r=resolve_stages({'codes':p},[
            {'id':'manual','kind':'manual','confirmed':True,'start_s':0,'end_s':6,'label':'User','type':'user'},
            {'id':'code','kind':'documented_codes','field_id':'codes','documented':True,'source':'recipe','version':'1','dictionary':{'1':'Process'}}],run_id='run')
        actual=[s for s in r['stages'] if s['label']=='Process']
        self.assertEqual([(s['start_s'],s['end_s']) for s in actual],[(1.,3.),(4.,6.)])
        self.assertNotEqual(actual[0]['id'],actual[1]['id'])
        self.assertTrue(any('Unmapped stage codes' in q['reason'] for q in r['readiness']))
        stages=r['stages']
        for a,b in zip(stages,stages[1:]):self.assertLessEqual(a['end_s'],b['start_s'])

    def test_undocumented_codes_never_guess_stage_meanings(self):
        p=projection([0,1,2],[3,3,3])
        r=resolve_stages({'a':p},[{'kind':'documented_codes','field_id':'a','dictionary':{'3':'Rinse'}}])
        self.assertFalse(r['stages'])
        self.assertTrue(any(q['status']=='needs_review' for q in r['readiness']))

    def test_empty_rule_does_not_become_entire_run_and_heuristics_are_neutral(self):
        p=projection([0,1,2,3],[0,0,1,0])
        r=resolve_stages({'a':p},[{'kind':'rule','reviewed':True,'conditions':[]}])
        self.assertFalse(r['stages'])
        r=resolve_stages({'a':p},[{'kind':'heuristic','explicit':True,'label':'Confirmed soak','conditions':[{'field_id':'a','op':'eq','value':0}]}])
        self.assertTrue(r['stages'])
        self.assertTrue(all(q['label'].startswith('Candidate segment') for q in r['stages']))
        self.assertTrue(all(q['type']=='candidate_segment' for q in r['stages']))

    def test_pulse_crossing_stage_counted_once_duration_split(self):
        original=[event('pulse',1,5,observed_onset=True)]
        stages=resolve_stages({},[
            {'id':'s1','kind':'manual','confirmed':True,'start_s':0,'end_s':3},
            {'id':'s2','kind':'manual','confirmed':True,'start_s':3,'end_s':7}])['stages']
        r=assign_events_to_stages(original,stages)
        self.assertEqual([a['onset_count'] for a in r[0]['stage_assignments']],[1,0])
        self.assertEqual([a['clipped_duration_s'] for a in r[0]['stage_assignments']],[2,2])
        self.assertNotIn('stage_assignments',original[0])
        r=assign_events_to_stages([event('initial',1,5,left_censored=True)],stages)
        self.assertEqual(sum(a['onset_count'] for a in r[0]['stage_assignments']),0)

    def test_activity_overlap_and_nested_steps_do_not_partition_parent(self):
        defs=[{'id':'parent','kind':'manual','confirmed':True,'start_s':0,'end_s':10},
              {'id':'child','kind':'manual','confirmed':True,'start_s':2,'end_s':4,'parent_id':'parent'},
              {'id':'activity','kind':'manual','confirmed':True,'start_s':1,'end_s':8,'exclusive':False}]
        r=resolve_stages({},defs)
        self.assertEqual(len(r['stages']),3)
        self.assertEqual(sorted(q['duration_s'] for q in r['stages']),[2,7,10])

    def test_rules_intersect_native_held_support_and_break_gaps(self):
        a=projection([0,1,2,5,6],[0,1,1,1,0]);a['acquisition_policy']['max_gap_seconds']=1
        b=projection([0,1.5,3,4,6],[0,1,1,0,0])
        defs=[{'kind':'rule','reviewed':True,'conditions':[{'field_id':'a','op':'eq','value':1},{'field_id':'b','op':'eq','value':1}]}]
        r=resolve_stages({'a':a,'b':b},defs)
        self.assertEqual([(q['start_s'],q['end_s']) for q in r['stages']],[(1.5,2.)])

    def test_analog_rule_uses_existing_linear_threshold_crossing(self):
        p=projection([0,2,4],[0,10,0]);p['structure']='analog'
        p['acquisition_policy']={'mode':'continuous','max_gap_seconds':3}
        definitions=[{'kind':'rule','reviewed':True,'conditions':[{'field_id':'speed','op':'gt','value':5}]}]
        r=resolve_stages({'speed':p},definitions)
        self.assertEqual([(q['start_s'],q['end_s']) for q in r['stages']],[(1.,3.)])
        self.assertTrue(any('Trace interpolation' in q['reason'] for q in r['readiness']))

    def test_registered_custom_resolver_without_builtin_changes(self):
        registry=StageResolverRegistry()
        registry.register('custom.recipe','1',lambda rows,d,r:([dict(start_s=0,end_s=2,label='Recipe step',type='custom',evidence_basis='documented recipe')],[]),trusted=True)
        r=resolve_stages({},[{'resolver':'custom.recipe'}],registry=registry)
        self.assertEqual(r['stages'][0]['label'],'Recipe step')
        with self.assertRaises(ValueError):registry.register('custom.recipe','2',lambda *args:None,trusted=True)


class SequenceTests(unittest.TestCase):
    def test_extra_pulse_not_ordinally_misaligned(self):
        a=[event('a1',0,1),event('a2',10,11),event('a3',20,21)]
        b=[event('b1',0,1),event('extra',5,6),event('b2',10,11),event('b3',20,21)]
        r=match_sequences(a,b,{'max_shift_s':1})
        self.assertEqual([(m['reference_id'],m['candidate_id']) for m in r['matches']],[('a1','b1'),('a2','b2'),('a3','b3')])
        self.assertEqual([e['id'] for e in r['added']],['extra'])
        self.assertFalse(r['missing'])

    def test_type_gates_missing_and_equal_repeated_events_are_ambiguous(self):
        a=[event('a',0,1,kind='fill')]
        b=[event('b1',0,1,kind='fill'),event('b2',0,1,kind='fill'),event('drain',0,1,kind='drain')]
        r=match_sequences(a,b,{'timing_weight':0})
        self.assertEqual(len(r['matches']),1)
        self.assertEqual(r['matches'][0]['status'],'ambiguous')
        self.assertTrue(r['ambiguous'])
        self.assertEqual(len(r['added']),2)
        self.assertNotEqual(r['matches'][0]['candidate_id'],'drain')

    def test_split_merge_suggestions_retain_original_events(self):
        a=[event('whole',0,4)]
        b=[event('part1',0,2),event('part2',2,4)]
        r=match_sequences(a,b)
        self.assertEqual(r['split_merge'][0]['type'],'split')
        self.assertEqual(r['split_merge'][0]['status'],'needs_review')
        self.assertEqual(r['split_merge'][0]['target_ids'],['part1','part2'])
        self.assertTrue(r['added'] or r['missing'])
        reverse=match_sequences(b,a)
        self.assertTrue(any(q['type']=='merge' for q in reverse['split_merge']))

    def test_budget_and_cancel_are_explicit(self):
        a=[event(str(i),i,i+1) for i in range(100)]
        r=match_sequences(a,a,{'max_cells':50})
        self.assertFalse(r['matches']);self.assertEqual(len(r['missing']),100)
        self.assertEqual(r['readiness'][0]['status'],'needs_review')
        with self.assertRaises(InterruptedError):
            match_sequences(a,a,{'cancelled':lambda:True})

    def test_permitted_costs_are_reported_and_order_is_preserved(self):
        a=[event('one',0,1),event('two',2,3)]
        b=[event('two',0,1),event('one',2,3)]
        r=match_sequences(a,b,{'timing_weight':0})
        self.assertEqual([m['candidate_index'] for m in r['matches']],sorted(m['candidate_index'] for m in r['matches']))
        self.assertEqual(r['parameters']['timing_weight'],0)
        with self.assertRaises(ValueError):match_sequences(a,b,{'insertion_penalty':-1})


if __name__=='__main__':unittest.main()

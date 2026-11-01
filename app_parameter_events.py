"""Native-clock state evidence, actuator occupancy and reviewed relationships.

Durations use half-open held intervals. Edge locations in a sampled state stream
are observations, with the previous/current observation bracket retained. No
implicit debounce or extrapolation is applied; unknown support is never OFF.
"""
from collections import defaultdict
from itertools import combinations
import copy
import math
import numpy as np

VERSION = '1.0'


def _cancel(parameters, i=0):
    callback = (parameters or {}).get('cancel')
    if i % 1024 == 0 and callable(callback) and callback():
        raise InterruptedError('Parameter analysis cancelled')


def _plain(value):
    return value.item() if isinstance(value, np.generic) else value


def _finite_value(value):
    if value is None:
        return False
    if isinstance(value, (complex, np.complexfloating)):
        return False
    if not isinstance(value, (str, bool, int, float, np.bool_, np.integer, np.floating)):
        return False
    return not isinstance(value, (float, np.floating)) or bool(np.isfinite(value))


def _state_key(value):
    value = _plain(value)
    if isinstance(value, (int, float)) and math.isfinite(value) and value == int(value):
        return str(int(value))
    return str(value)


def _ready(status, reason, **extra):
    return dict(status=status, reason=reason, **extra)


def _event(identity, index, kind, start, end, left, right, onset_bracket, offset_bracket, refs, parameters):
    uncertainty = parameters.get('timing_uncertainty_s')
    if uncertainty is not None:
        uncertainty = float(uncertainty)
        if not math.isfinite(uncertainty) or uncertainty < 0:
            raise ValueError('timing_uncertainty_s must be finite and nonnegative')
        onset_bracket = ([onset_bracket[0]-uncertainty, onset_bracket[1]+uncertainty]
                         if onset_bracket is not None else None)
        offset_bracket = ([offset_bracket[0]-uncertainty, offset_bracket[1]+uncertainty]
                          if offset_bracket is not None else None)
    return dict(id=f"{identity.get('run_id', '')}:{identity.get('field_id', '')}:{kind}:{index}",
                type=kind, field_id=identity.get('field_id', ''), run_id=identity.get('run_id', ''),
                instance=identity.get('instance', ''), role=identity.get('role', ''),
                onset_s=float(start), offset_s=float(end),
                onset_bracket_s=onset_bracket, offset_bracket_s=offset_bracket,
                brackets={'onset_s': onset_bracket, 'offset_s': offset_bracket},
                left_censored=bool(left), right_censored=bool(right),
                censoring={'left': bool(left), 'right': bool(right)},
                observed_onset=not left, observed_offset=not right,
                source_indices=list(refs), source_refs=[dict(field_id=identity.get('field_id', ''), sample_index=_plain(i)) for i in refs],
                detector='native_state_timeline', detector_version=VERSION,
                parameters={k: v for k, v in parameters.items() if k != 'cancel'}, stage_assignments=[])


def state_timeline(x_s, values, *, valid=None, structure='binary', acquisition_policy='sampled_hold',
                   max_gap_s=None, dictionary=None, on_values=None, parameters=None, identity=None):
    """Return held occupancy and censored native-clock episodes without mutation.

    ``max_gap_s=None`` declares no maximum gap; it does not estimate a sampling
    rate. Dict acquisition policies may declare a gap. ``event_log`` explicitly
    denotes state-change timestamps; every other accepted mode retains sampled
    edge brackets. Dictionary labels never change the underlying state codes.
    Optional min_dwell_s/debounce_s suppress *event eligibility*, retaining raw
    occupancy and a separate suppressed_events list. Hysteresis is explicit.
    """
    p = dict(parameters or {}); identity = dict(identity or {})
    _cancel(p)
    result = dict(intervals=[], events=[], transitions=[], suppressed_events=[], occupancy=[],
                  supported_intervals=[], summary={}, readiness=[], parameters={k:v for k,v in p.items() if k != 'cancel'})
    policy = dict(acquisition_policy) if isinstance(acquisition_policy, dict) else {}
    if policy:
        max_gap_s = max_gap_s if max_gap_s is not None else policy.get('max_gap_s', policy.get('max_gap_seconds'))
        acquisition_policy = policy.get('mode', policy.get('name', 'sampled_hold'))
        if policy.get('timing_uncertainty_s') is not None:
            p.setdefault('timing_uncertainty_s', policy['timing_uncertainty_s'])
    mode = str(acquisition_policy or 'sampled_hold').lower()
    result['parameters'] = {k:v for k,v in p.items() if k != 'cancel'}
    sample_only = x_s is None or mode == 'sample_only'
    if not sample_only and mode not in {'sampled_hold', 'hold', 'held', 'state_hold', 'event', 'event_log', 'exact_event_log'}:
        result['readiness'].append(_ready('unsupported', 'State occupancy requires a declared held-state or event-log acquisition policy.'))
        return result
    exact = mode in {'event', 'event_log', 'exact_event_log'}
    if max_gap_s is not None and (not math.isfinite(float(max_gap_s)) or float(max_gap_s) < 0):
        raise ValueError('max_gap_s must be finite and nonnegative')
    for key in ('min_dwell_s', 'minimum_dwell_s', 'debounce_s', 'merge_gap_s', 'refractory_s'):
        if key in p and (not math.isfinite(float(p[key])) or float(p[key]) < 0):
            raise ValueError(f'{key} must be finite and nonnegative')
    y = np.asarray(values, dtype=object).copy()
    if y.ndim != 1:
        raise ValueError('State values must be a one-dimensional scalar array')
    t = np.arange(len(y), dtype=float) if sample_only else np.asarray(x_s, dtype=float).copy()
    if t.ndim != 1:
        raise ValueError('Clock values must be one-dimensional')
    if len(t) != len(y):
        raise ValueError('Clock and state arrays must have equal lengths')
    ok = np.ones(len(y), bool) if valid is None else np.asarray(valid, bool).reshape(-1).copy()
    if len(ok) != len(y):
        raise ValueError('Validity and state arrays must have equal lengths')
    refs = np.asarray(identity.get('source_indices', np.arange(len(y)))).reshape(-1)
    if len(refs) != len(y):
        raise ValueError('source_indices and state arrays must have equal lengths')
    ok &= np.isfinite(t) & np.array([_finite_value(v) for v in y], bool)
    if len(t) > 1 and np.any(np.diff(t[np.isfinite(t)]) < 0):
        result['readiness'].append(_ready('invalid', 'Backward timestamps require clock-domain/reset review; source order was retained.'))
        return result
    duplicates = int(np.count_nonzero(np.diff(t) == 0)) if len(t) > 1 else 0
    if duplicates:
        duplicate_policy = policy.get('duplicate_clock', 'reject')
        if duplicate_policy not in {'first', 'last'}:
            result['readiness'].append(_ready('needs_review', 'Duplicate timestamps require an explicit first/last observation policy; original source order retained.'))
            return result
        keep = np.r_[True, np.diff(t) != 0] if duplicate_policy == 'first' else np.r_[np.diff(t) != 0, True]
        t, y, ok, refs = t[keep], y[keep], ok[keep], refs[keep]
        result['readiness'].append(_ready('partial', duplicate_policy.title() + ' observation at a duplicate timestamp is used under the declared policy; source references are retained.', duplicate_timestamps=duplicates))
    binary = structure in {'binary', 'binary_state'}
    if binary:
        hyst = p.get('hysteresis')
        if hyst:
            low, high = float(hyst['off']), float(hyst['on'])
            if low >= high:
                raise ValueError('Hysteresis off threshold must be below on threshold')
            state = None
            for i, value in enumerate(y):
                _cancel(p, i)
                if not ok[i]:
                    state = None
                    continue
                value = float(value)
                if value >= high: state = True
                elif value <= low: state = False
                elif state is None: ok[i] = False
                y[i] = bool(state) if state is not None else False
            active = np.asarray(y, bool)
        elif on_values is not None:
            selected = {_state_key(v) for v in on_values}
            active = np.array([_state_key(v) in selected for v in y], bool)
        elif all(v in (0, 1, False, True) for v in y[ok]):
            active = np.array([bool(v) if good else False for v, good in zip(y, ok)], bool)
        elif p.get('nonzero_is_on') is True:
            active = np.array([float(v) != 0 if good else False for v, good in zip(y, ok)], bool)
        elif 'noise_floor' in p:
            active = np.array([abs(float(v)) > float(p['noise_floor']) if good else False for v, good in zip(y, ok)], bool)
        else:
            result['readiness'].append(_ready('needs_mapping', 'Binary ON values or explicit thresholds are required for non-boolean codes.'))
            return result
        states = active.astype(object)
    else:
        active = np.zeros(len(y), bool); states = y
    if sample_only:
        # Observation order supports counts but never creates a fictitious time
        # coordinate. Missing samples break adjacency, including onset evidence.
        transitions = []
        sequence = []
        occupancy = {}
        episode_count = 0
        for i, state in enumerate(states):
            _cancel(p, i)
            if not ok[i]:
                continue
            key = _state_key(state)
            row = occupancy.setdefault(key, dict(state=_plain(state),
                label=(dictionary or {}).get(key, _plain(state)), sample_count=0,
                duration_s=None, fraction=None))
            row['sample_count'] += 1
            changed = i == 0 or not ok[i-1] or state != states[i-1]
            if changed:
                sequence.append(_plain(state))
                if not binary or active[i]:
                    episode_count += 1
            if i and ok[i-1] and state != states[i-1]:
                transitions.append((_state_key(states[i-1]), key))
        matrix = defaultdict(int)
        for pair in transitions:
            matrix[pair] += 1
        result['occupancy'] = list(occupancy.values())
        result['summary'] = dict(on_duration_s=None, off_duration_s=None,
            supported_duration_s=None, duty_cycle=None, duty_cycle_denominator_s=None,
            transition_count=len(transitions),
            rising_count=sum(b == '1' for a,b in transitions) if binary else None,
            falling_count=sum(b == '0' for a,b in transitions) if binary else None,
            episode_count=episode_count, state_sequence=sequence,
            transition_matrix=[dict(from_state=a,to_state=b,count=n) for (a,b),n in matrix.items()],
            initial_state=_plain(states[0]) if len(states) and ok[0] else None,
            final_state=_plain(states[-1]) if len(states) and ok[-1] else None,
            interval_policy='Sample-domain adjacency only; no time or duration inferred')
        result['readiness'].append(_ready('partial', 'Sample-domain state observations and adjacent changes only. A trustworthy clock and held-state policy are required for seconds, duty cycle, timed events and stage attribution.'))
        return result
    linked = np.zeros(max(0, len(t)-1), bool)
    if len(t)>1:
        delta = np.diff(t)
        linked = ok[:-1] & ok[1:] & (delta>0)
        if max_gap_s is not None: linked &= delta<=float(max_gap_s)
    # A transition is observed only across connected valid observations. No
    # boundary across missing support can be called a new activation.
    transitions = {}
    for i in range(1,len(t)):
        _cancel(p, i)
        if linked[i-1] and states[i] != states[i-1]:
            bracket = [float(t[i]), float(t[i])] if exact else [float(t[i-1]), float(t[i])]
            kind = ('rising' if active[i] else 'falling') if binary else 'state_transition'
            event = _event(identity, len(result['transitions']), kind, t[i], t[i], False, False, bracket, bracket, [refs[i-1], refs[i]], p)
            event.update(from_state=_plain(states[i-1]), to_state=_plain(states[i]), confirmation_s=float(t[i]))
            result['transitions'].append(event); transitions[i] = event
    # Iterate maximal runs of one state and one connected support component.
    i = 0
    state_runs = []
    zero_observations = []
    while i<len(t):
        _cancel(p, i)
        if not ok[i]: i+=1; continue
        start=i; end=i
        while end<len(t)-1 and linked[end] and states[end+1] == states[start]: end+=1
        # A changed state is supported up to the next observation, which is its
        # held-boundary estimate. A final isolated observation has zero duration.
        stop=end+1 if end<len(t)-1 and linked[end] else end
        left = start not in transitions
        right = stop not in transitions or stop==start
        onset = None if left else transitions[start]['onset_bracket_s']
        offset = None if right else transitions[stop]['onset_bracket_s']
        interval = dict(start_s=float(t[start]), end_s=float(t[stop]), state=_plain(states[start]),
                        label=(dictionary or {}).get(_plain(states[start]), (dictionary or {}).get(_state_key(states[start]), _plain(states[start]))),
                        active=bool(active[start]) if binary else None, source_indices=[_plain(v) for v in refs[start:stop+1]],
                        left_censored=left, right_censored=right, onset_bracket_s=onset, offset_bracket_s=offset,
                        support_component_start=bool(left), support_component_end=bool(right))
        state_runs.append(_plain(states[start]))
        if t[stop]>t[start]: result['intervals'].append(interval)
        else: zero_observations.append(interval)
        if not binary or active[start]:
            kind = 'active_episode' if binary else 'state_entry'
            # Transition brackets already contain declared clock uncertainty.
            event = _event(identity,len(result['events']),kind,t[start],t[stop],left,right,onset,offset,refs[start:stop+1],dict(p, timing_uncertainty_s=None))
            event['parameters'] = {k:v for k,v in p.items() if k != 'cancel'}
            event.update(state=_plain(states[start]), label=interval['label'], duration_s=float(t[stop]-t[start]),
                         active_duration_s=float(t[stop]-t[start]), confirmation_s=float(t[start]) if not left else None)
            result['events'].append(event)
        i = end+1
    occupied = {}; sequence=state_runs
    for interval in result['intervals'] + zero_observations:
        state=interval['state']; key=_state_key(state)
        if key not in occupied: occupied[key] = dict(state=state,label=interval['label'],duration_s=0.,episodes=0)
        occupied[key]['duration_s'] += interval['end_s']-interval['start_s']; occupied[key]['episodes'] += 1
        a,b=interval['start_s'],interval['end_s']
        if b <= a:
            continue
        if result['supported_intervals'] and result['supported_intervals'][-1][1] == a:
            result['supported_intervals'][-1][1]=b
        else: result['supported_intervals'].append([a,b])
    supported=sum(row['duration_s'] for row in occupied.values())
    for row in occupied.values(): row['fraction']=row['duration_s']/supported if supported else None
    result['occupancy']=list(occupied.values())
    counts=defaultdict(int)
    for edge in result['transitions']: counts[(_state_key(edge['from_state']),_state_key(edge['to_state']))]+=1
    matrix=[dict(from_state=a,to_state=b,count=n) for (a,b),n in counts.items()]
    raw_events=result['events']; kept=[]
    minimum=max(float(p.get('min_dwell_s',p.get('minimum_dwell_s',0))),float(p.get('debounce_s',0)))
    refractory=float(p.get('refractory_s',0)); last_onset=None
    for event in raw_events:
        reason=None
        if event['duration_s']<minimum: reason='Dwell shorter than explicit event confirmation duration'
        elif last_onset is not None and event['onset_s']-last_onset<refractory: reason='Explicit refractory interval'
        if reason:
            result['suppressed_events'].append(dict(event,suppressed=True,suppression_reason=reason))
        else:
            if event['observed_onset']: event['confirmation_s']=event['onset_s']+minimum
            kept.append(event);last_onset=event['onset_s']
    merge=float(p.get('merge_gap_s',0))
    merged=[]
    for event in kept:
        previous=merged[-1] if merged else None
        same_support=previous and any(a<=previous['offset_s']<=event['onset_s']<=b for a,b in result['supported_intervals'])
        if binary and merge and previous and not previous['right_censored'] and not event['left_censored'] and same_support and event['onset_s']-previous['offset_s']<=merge:
            components=copy.deepcopy(previous.get('components',[previous]))+[copy.deepcopy(event)]
            previous.update(offset_s=event['offset_s'],offset_bracket_s=event['offset_bracket_s'],right_censored=event['right_censored'],
                            observed_offset=event['observed_offset'],duration_s=event['offset_s']-previous['onset_s'],
                            active_duration_s=previous['active_duration_s']+event['active_duration_s'],components=components)
            previous['brackets']['offset_s']=event['offset_bracket_s']; previous['censoring']['right']=event['right_censored']
        else: merged.append(event)
    result['events']=merged
    durations = [event['duration_s'] for event in raw_events]
    complete_durations = [event['duration_s'] for event in raw_events if not event['left_censored'] and not event['right_censored']]
    off_gaps = [interval['end_s']-interval['start_s'] for interval in result['intervals']
                if binary and not interval['active'] and not interval['left_censored'] and not interval['right_censored']]
    def distribution(items):
        return dict(count=len(items), minimum_s=min(items) if items else None,
            maximum_s=max(items) if items else None, mean_s=sum(items)/len(items) if items else None,
            durations_s=items)
    span=float(t[-1]-t[0]) if len(t)>1 and np.all(np.isfinite(t[[0,-1]])) else None
    on=sum(row['duration_s'] for row in result['occupancy'] if row['state'] is True) if binary else None
    rising=sum(e['type']=='rising' for e in result['transitions']); falling=sum(e['type']=='falling' for e in result['transitions'])
    result['summary']=dict(recording_span_s=span,supported_duration_s=supported,on_duration_s=on,
                           off_duration_s=supported-on if binary else None,duty_cycle=on/supported if binary and supported else None,
                           duty_cycle_denominator_s=supported,transition_count=len(result['transitions']),
                           rising_count=rising,falling_count=falling,episode_count=len(raw_events),retained_event_count=len(merged),
                           observed_onset_count=sum(e['observed_onset'] for e in raw_events),state_sequence=sequence,transition_matrix=matrix,
                           complete_episode_durations=distribution(complete_durations),
                           observed_episode_support=distribution(durations), off_gap_durations=distribution(off_gaps),
                           first_observed_activation_s=next((e['onset_s'] for e in raw_events if e['observed_onset']),None),
                           last_observed_activation_s=next((e['onset_s'] for e in reversed(raw_events) if e['observed_onset']),None),
                           initial_state=_plain(states[0]) if len(t) and ok[0] else None,
                           final_state=_plain(states[-1]) if len(t) and ok[-1] else None,
                           interval_policy='Half-open native held support; no extrapolation',edge_timing='exact declared event log' if exact else 'sampled observation brackets',
                           event_filter_scope='Event eligibility only; occupancy and observed edge counts retain original evidence')
    if not len(t): result['readiness'].append(_ready('missing_input','No state observations.'))
    elif supported==0: result['readiness'].append(_ready('partial','No positive-duration supported state interval; sample-domain observations remain available.'))
    else: result['readiness'].append(_ready('partial' if span and supported<span else 'computed','State occupancy on valid native held support.'))
    return result


def _timeline(projection, field_id='', parameters=None):
    mapping=projection.get('mapping') or (projection.get('provenance') or {}).get('mapping') or {}
    encoding=mapping.get('encoding') or {}
    event_parameters = dict(mapping.get('parameters') or {})
    event_parameters.update(parameters or {})
    return state_timeline(projection.get('x_s'),projection.get('values',[]),valid=projection.get('valid'),
                          structure=projection.get('structure','binary'),acquisition_policy=projection.get('acquisition_policy','sampled_hold'),
                          max_gap_s=projection.get('max_gap_s',mapping.get('max_gap_s')),
                          dictionary=projection.get('state_dictionary',projection.get('dictionary',mapping.get('state_dictionary',mapping.get('dictionary',encoding.get('lookup'))))),
                          on_values=projection.get('on_values',mapping.get('on_values',event_parameters.get('on_values',encoding.get('on_values')))),parameters=event_parameters,
                          identity=dict(field_id=field_id,run_id=projection.get('run_id',''),instance=projection.get('instance',''),role=projection.get('role',''),
                                        source_indices=projection.get('source_indices',np.arange(len(projection.get('values',[]))))))


def actuator_relationships(projections, parameters=None):
    """Sweep observed combinations on shared valid support, without a powerset.

    Pair overlaps use each pair's own shared support; multi-actuator combinations
    use shared support of every supplied actuator. Commands describe commands.
    """
    p=dict(parameters or {}); _cancel(p)
    rows=dict(projections) if isinstance(projections,dict) else {str(q.get('field_id',i)):q for i,q in enumerate(projections)}
    timelines={name:_timeline(q,name,p) for name,q in rows.items()}
    timelines={k:v for k,v in timelines.items() if rows[k].get('structure','binary') in {'binary','binary_state'}}
    result=dict(metrics=[],overlaps=[],combinations=[],order=[],readiness=[],timelines=timelines)
    if not timelines:
        result['readiness'].append(_ready('missing_input','Mapped binary actuator projections are required.')); return result
    for name,line in timelines.items():
        if not line['intervals']:result['readiness'].append(_ready('missing_input','No supported actuator state.',field_id=name))
    # Endpoint sweep is linear in native interval count after sorting. It emits
    # only combinations actually observed and never constructs a powerset.
    def sweep(names):
        changes=defaultdict(list)
        for name in names:
            for it in timelines[name]['intervals']:
                changes[it['start_s']].append((name,it['active']))
                changes[it['end_s']].append((name,None))
        # At shared boundaries end removal precedes the new held state.
        current={}; segments=[];times=sorted(changes)
        for i,a in enumerate(times[:-1]):
            _cancel(p,i)
            for name,state in sorted(changes[a],key=lambda item:item[1] is not None):
                if state is None:current.pop(name,None)
                else:current[name]=state
            b=times[i+1]
            if len(current)==len(names) and b>a:
                active=tuple(name for name in names if current[name])
                if segments and segments[-1]['end_s']==a and segments[-1]['active']==active:segments[-1]['end_s']=b
                else:segments.append(dict(start_s=a,end_s=b,active=active))
        return segments
    names=list(timelines); all_segments=sweep(names); observed={}
    for segment in all_segments:
        active=segment['active'];d=segment['end_s']-segment['start_s']
        if active not in observed:observed[active]=dict(active=list(active),duration_s=0.,intervals=[])
        observed[active]['duration_s']+=d;observed[active]['intervals'].append([segment['start_s'],segment['end_s']])
    result['combinations']=list(observed.values())
    common=sum(s['end_s']-s['start_s'] for s in all_segments)
    union=sum(row['duration_s'] for key,row in observed.items() if key)
    all_on=observed.get(tuple(names),{}).get('duration_s',0.)
    all_off=observed.get((),{}).get('duration_s',0.)
    result.update(shared_supported_duration_s=common,union_duration_s=union,all_on_duration_s=all_on,all_off_duration_s=all_off)
    for a,b in combinations(names,2):
        _cancel(p)
        pair=sweep([a,b]); support=sum(s['end_s']-s['start_s'] for s in pair)
        overlap=[s for s in pair if len(s['active'])==2]
        result['overlaps'].append(dict(field_ids=[a,b],duration_s=sum(s['end_s']-s['start_s'] for s in overlap),
                                       supported_duration_s=support,intervals=[[s['start_s'],s['end_s']] for s in overlap],episode_count=len(overlap),
                                       observation='Simultaneous observed active states; command state does not establish physical actuation.'))
    onsets=sorted((dict(event,field_id=name) for name,line in timelines.items() for event in line['events'] if event['observed_onset']),key=lambda e:e['onset_s'])
    # Consecutive observed starts only. Overlapping brackets establish no order.
    for first,second in zip(onsets,onsets[1:]):
        if first['field_id'] == second['field_id']:
            continue
        a=first['onset_bracket_s']; b=second['onset_bracket_s']
        status='ordered' if a[1]<b[0] else ('simultaneous' if a[0]==a[1]==b[0]==b[1] else 'indeterminate')
        result['order'].append(dict(first_id=first['id'],second_id=second['id'],field_ids=[first['field_id'],second['field_id']],status=status,
                                    delay_s=second['onset_s']-first['onset_s'],delay_bounds_s=[b[0]-a[1],b[1]-a[0]],brackets=[a,b]))
    result['readiness'].append(_ready('computed' if common else 'partial','Relationships use shared valid held support; initial/censored activity does not establish start order.'))
    return result


def analyse_relationships(projections, rules, stages=None):
    """Evaluate explicit, reviewed association rules, never hardware diagnoses.

    Rules require reviewed=True, timing_compatible=True and two named fields.
    Supported operations are state_mismatch, response_delay, observed_change.
    A response rule requires an explicit window_s and threshold. No configured
    association is promoted to a root cause or engineering acceptance verdict.
    """
    rows=dict(projections) if isinstance(projections,dict) else {str(q.get('field_id',i)):q for i,q in enumerate(projections)}
    result=dict(metrics=[],events=[],readiness=[])
    for number,rule in enumerate(rules or []):
        rid=rule.get('id',f'relationship:{number}'); fields=rule.get('fields') or [rule.get('command_field'),rule.get('response_field')]
        def unavailable(status,reason):result['readiness'].append(_ready(status,reason,rule_id=rid))
        if not rule.get('reviewed') or not rule.get('timing_compatible'):
            unavailable('needs_mapping','Reviewed compatible inputs and synchronised timing are required.');continue
        if len(fields)!=2 or any(f not in rows for f in fields):
            unavailable('missing_input','Both configured relationship inputs are required.');continue
        a,b=(rows[f] for f in fields);operation=rule.get('operation')
        if operation=='state_mismatch':
            if any(q.get('structure') not in {'binary','binary_state'} for q in (a,b)):
                unavailable('not_comparable','State mismatch requires two mapped binary states.');continue
            pair=actuator_relationships({fields[0]:a,fields[1]:b})
            duration=sum(q['duration_s'] for q in pair['combinations'] if len(q['active'])==1)
            support=pair['shared_supported_duration_s']
            result['metrics'].append(dict(metric_id=rid,value=duration if support else None,unit='s',status='computed' if support else 'insufficient_data',
                                           supported_duration_s=pair['shared_supported_duration_s'],parameters=rule,evidence_basis='direct_measurement',
                                           reasons=[] if support else ['No positive-duration shared valid support'],
                                           observation='Observed command/feedback state disagreement on shared valid support; cause is not established.'))
        elif operation in {'response_delay','observed_change'}:
            if 'window_s' not in rule or 'threshold' not in rule or not rule.get('units_compatible'):
                unavailable('needs_mapping','Response associations require explicit window_s, threshold and compatible reviewed units.');continue
            window=float(rule['window_s']); threshold=float(rule['threshold']); direction=float(rule.get('direction',1))
            if window<=0 or not math.isfinite(window) or not math.isfinite(threshold) or direction not in (-1,1):
                unavailable('invalid','Response window must be positive and threshold finite.');continue
            trigger=_timeline(a,fields[0]); t=np.asarray(b.get('x_s',[]),float); y=np.asarray(b.get('values',[]),float)
            if t.ndim!=1 or y.ndim!=1 or len(t)!=len(y) or len(t)<2 or not np.isfinite(t).all() or np.any(np.diff(t)<=0):
                unavailable('invalid','Response input requires ordered native observations.');continue
            valid=np.asarray(b.get('valid',np.ones(len(t),bool)),bool)
            if valid.shape!=t.shape:
                unavailable('invalid','Response validity mask must match native observations.');continue
            good=valid&np.isfinite(t)&np.isfinite(y)
            for event in trigger['events']:
                if not event['observed_onset']:continue
                start=event['onset_s']; i=int(np.searchsorted(t,start,side='right')-1); stop=int(np.searchsorted(t,start+window,side='right'))
                if i<0 or not good[i]:continue
                candidates=np.arange(i+1,stop); candidates=candidates[good[candidates]]
                # Never bridge invalid samples or the declared gap limit.
                policy=b.get('acquisition_policy') or {}
                max_gap=b.get('max_gap_s',policy.get('max_gap_seconds') if isinstance(policy,dict) else None); stop_gap=None
                for k in range(i+1,stop):
                    if not good[k] or (max_gap is not None and t[k]-t[k-1]>max_gap):stop_gap=k;break
                if stop_gap is not None:candidates=candidates[candidates<stop_gap]
                reached=candidates[(y[candidates]-y[i])*direction>=threshold]
                hit=int(reached[0]) if len(reached) else None
                status='computed' if hit is not None else 'not_observed'
                complete=stop_gap is None and len(t) and t[-1]>=start+window
                if hit is None and not complete:status='partial'
                result['metrics'].append(dict(metric_id=rid,event_id=event['id'],value=float(t[hit]-start) if hit is not None else None,unit='s',
                                               status=status,parameters=rule,evidence_basis='documented_derived_quantity',
                                               boundary_uncertainty=dict(trigger=event['onset_bracket_s'],response=[float(t[hit-1]),float(t[hit])] if hit is not None else None),
                                               observation='Observed response threshold after configured activation; timing association does not establish cause.'))
        else:unavailable('unsupported','Unknown relationship operation; register a trusted implementation.')
    return result


class EventDetectorRegistry:
    """Versioned detectors supplied by trusted application or user plugins.

    Algorithms receive immutable native projections and explicit parameters.
    Registration never evaluates expressions/functions embedded in source data.
    A detector failure is a readiness record, leaving other capabilities usable.
    """
    def __init__(self):
        self._detectors = {}

    def register(self, detector_id, version, detector, *, trusted=False,
                 structures=(), evidence_requirements=(), coverage_policy='Declared native support only'):
        if not trusted or not isinstance(detector_id,str) or not detector_id or not isinstance(version,str) or not version or not callable(detector):
            raise ValueError('A trusted named, versioned callable event detector is required')
        if detector_id in self._detectors:
            raise ValueError('Event detector already registered: '+detector_id)
        if any(not isinstance(v,str) for v in (*structures,*evidence_requirements)) or not isinstance(coverage_policy,str):
            raise ValueError('Event detector evidence/structure metadata must be strings')
        self._detectors[detector_id] = dict(version=version,detector=detector,
            structures=tuple(structures),evidence_requirements=tuple(evidence_requirements),
            coverage_policy=coverage_policy)

    def definitions(self):
        return [dict(detector_id=key,version=entry['version'],structures=list(entry['structures']),
            evidence_requirements=list(entry['evidence_requirements']),coverage_policy=entry['coverage_policy'])
            for key,entry in self._detectors.items()]

    def snapshot(self):
        return {key:dict(value) for key,value in self._detectors.items()}

    def restore(self,snapshot):
        fresh=EventDetectorRegistry()
        for key,entry in snapshot.items():
            fresh.register(key,entry['version'],entry['detector'],trusted=True,
                structures=entry['structures'],evidence_requirements=entry['evidence_requirements'],
                coverage_policy=entry['coverage_policy'])
        self._detectors=fresh._detectors

    def clone(self):
        other=EventDetectorRegistry();other.restore(self.snapshot());return other

    def detect(self, detector_id, projection, *, parameters=None):
        if detector_id not in self._detectors:
            return dict(events=[],readiness=[_ready('unsupported','No trusted event detector is registered.',detector_id=detector_id)])
        entry=self._detectors[detector_id]
        if entry['structures'] and projection.get('structure') not in entry['structures']:
            return dict(events=[],readiness=[_ready('not_comparable','Detector does not support this reviewed signal structure.',detector_id=detector_id)])
        try:
            result=entry['detector'](projection,dict(parameters or {}))
            if not isinstance(result,dict) or not isinstance(result.get('events'),list) or not isinstance(result.get('readiness',[]),list):
                raise ValueError('A detector must return events and readiness arrays')
            result=copy.deepcopy(result)
            for event in result['events']:
                if not isinstance(event,dict) or not isinstance(event.get('type'),str):
                    raise ValueError('Each detected event requires a typed evidence record')
                event.setdefault('detector',detector_id);event.setdefault('detector_version',entry['version'])
                event.setdefault('field_id',projection.get('field_id',''));event.setdefault('run_id',projection.get('run_id',''))
                event.setdefault('stage_assignments',[])
            from app_parameter_contracts import strict_json
            return strict_json(result)
        except InterruptedError:
            raise
        except Exception as exc:
            return dict(events=[],readiness=[_ready('error',type(exc).__name__+': '+str(exc),detector_id=detector_id,
                remedy='Review detector parameters or the trusted plugin; source data was not modified.')])


_EVENT_REGISTRY=None


def event_registry():
    global _EVENT_REGISTRY
    if _EVENT_REGISTRY is None:
        _EVENT_REGISTRY=EventDetectorRegistry()
        _EVENT_REGISTRY.register('native_state_timeline',VERSION,
            lambda projection,parameters:_timeline(projection,projection.get('field_id',''),parameters),trusted=True,
            structures=('binary','enum','categorical','pulse'),
            evidence_requirements=('Reviewed state encoding','Trusted native clock for seconds'),
            coverage_policy='Half-open held support; no gap bridging or extrapolation; censored boundaries retained')
    return _EVENT_REGISTRY

"""Conservative reusable domain capabilities over native supported intervals.

No channel names select meaning. All thresholds, target bands, resets and
encoding policies below come from a reviewed mapping; missing prerequisites
produce availability records rather than guesses about the appliance.
"""
import math
import numpy as np
from app_engineering_units import UNITS, unit, convert


def _parameters(c):
    return c.mapping.get('parameters') or {}


def _finite(value, name, *, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + ' must be a finite number')
    if nonnegative and value < 0:
        raise ValueError(name + ' must be nonnegative')
    return float(value)


def _pieces(c):
    """Supported native interval arrays with the declared interpolation policy."""
    return c.segments()


def _band_intervals(a,b,left,right,low=None,high=None):
    """Exact within-band pieces of supported linear/held intervals."""
    if not len(a): return []
    lo, hi = np.zeros(len(a)), np.ones(len(a))
    change = right-left
    moving = change != 0
    if low is not None:
        crossing = np.divide(low-left, change, out=np.zeros(len(a)), where=moving)
        lo = np.where(moving & (change > 0), np.maximum(lo, crossing), lo)
        hi = np.where(moving & (change < 0), np.minimum(hi, crossing), hi)
        hi = np.where(~moving & (left < low), -1., hi)
    if high is not None:
        crossing = np.divide(high-left, change, out=np.zeros(len(a)), where=moving)
        hi = np.where(moving & (change > 0), np.minimum(hi, crossing), hi)
        lo = np.where(moving & (change < 0), np.maximum(lo, crossing), lo)
        hi = np.where(~moving & (left > high), -1., hi)
    lo,hi=np.maximum(0.,lo),np.minimum(1.,hi)
    selected=hi>lo
    starts=a[selected]+(b[selected]-a[selected])*lo[selected]
    stops=a[selected]+(b[selected]-a[selected])*hi[selected]
    output=[]
    for start,stop in zip(starts,stops):
        if output and abs(output[-1][1]-start)<=1e-10*max(1.,abs(start)):
            output[-1][1]=float(stop)
        else: output.append([float(start),float(stop)])
    return output


def _clip_duration(a, b, left, right, low=None, high=None):
    """Exact supported duration within a closed numeric band, no extrapolation."""
    return sum(stop-start for start,stop in _band_intervals(a,b,left,right,low,high))


def _band(c, definition, prefix='dwell'):
    if not isinstance(definition, dict) or not isinstance(definition.get('name'), str) or not definition['name']:
        raise ValueError('A dwell band requires an explicit name')
    low, high = definition.get('low'), definition.get('high')
    if low is None and high is None:
        raise ValueError('A dwell band needs at least one bound')
    if low is not None: low = _finite(low, 'Lower band bound')
    if high is not None: high = _finite(high, 'Upper band bound')
    if low is not None and high is not None and low > high:
        raise ValueError('Lower band bound exceeds upper band bound')
    a, b, left, right = _pieces(c)
    value = _clip_duration(a,b,left,right,low,high)
    name = prefix + ':' + definition['name']
    c.timed(name, value, 's', parameters=definition,
            weighting='supported time; declared piecewise linear/held band occupancy')
    c.timed(name + '.fraction', value/c.stats['known_s'] if c.stats.get('known_s') else None, '1',
            parameters=definition, weighting='band dwell / supported channel time')
    return value


def threshold_capabilities(c):
    """Generic numeric bands work for custom roles without UI/report changes."""
    p = _parameters(c)
    bands = p.get('bands', p.get('threshold_bands', []))
    if not isinstance(bands, list):
        raise ValueError('Threshold bands must be a list of named numeric bounds')
    for band in bands:
        c.check()
        _band(c, band)
    bins = p.get('distribution_bins')
    if bins is not None:
        if not isinstance(bins, list) or len(bins) < 2:
            raise ValueError('Distribution bins require at least two numeric boundaries')
        edges = [_finite(v, 'Distribution boundary') for v in bins]
        if any(a >= b for a,b in zip(edges,edges[1:])):
            raise ValueError('Distribution boundaries must strictly increase')
        a,b,left,right = _pieces(c)
        rows = [{'low': lo, 'high': hi, 'duration_s': _clip_duration(a,b,left,right,lo,hi)}
                for lo,hi in zip(edges,edges[1:])]
        # Finite-width linear segments have measure-zero shared boundaries;
        # held values at a boundary belong only to the interval on the right.
        held = left == right
        for i,row in enumerate(rows[:-1]):
            row['duration_s'] -= float(np.sum((b-a)[held & (left == row['high'])]))
        c.timed('supported_distribution', rows, '', parameters={'bins':edges, 'last_bin_closed':True},
                weighting='supported time; half-open bins except final closed bin')


def _native_pairs(c):
    """No interpolation of counters/budgets across resets or unknown support."""
    if c.x is None or len(c.values)<2 or c.time_reason:
        return np.array([],int)
    d = np.diff(c.x)
    usable = c.finite[:-1] & c.finite[1:] & (d>0)
    gap = c.policy.get('max_gap_seconds', c.policy.get('max_gap_s'))
    if gap is not None: usable &= d <= float(gap)
    if c.scope.get('start_s') is not None: usable &= c.x[:-1]>=c.scope['start_s']
    if c.scope.get('end_s') is not None: usable &= c.x[1:]<=c.scope['end_s']
    return np.flatnonzero(usable)


def _counter_event(c, index, kind, **details):
    return {'id': f'{c.run_id}:{c.field_id}:{kind}:{index}', 'type':kind,
        'run_id':c.run_id, 'field_id':c.field_id, 'role':c.projection.get('role',''),
        'instance':c.projection.get('instance',''), 'onset_s':float(c.x[index+1]),
        'onset_bracket_s':[float(c.x[index]),float(c.x[index+1])],
        'source_indices':[int(c.indices[index]),int(c.indices[index+1])],
        'detector':'native_numeric_changes', 'detector_version':'1',
        'evidence_basis':'observed numeric change', **details}


def counter_capability(projection, c):
    if not c.numeric:
        c.emit('counter.increment',status='unsupported',reason='Counters require scalar numeric values')
        return
    positions=np.flatnonzero(c.finite)
    for name,pos in (('initial',positions[0] if len(positions) else None),('final',positions[-1] if len(positions) else None)):
        c.emit('counter.'+name, (c.values[pos].item() if isinstance(c.values[pos],np.generic) else c.values[pos]) if pos is not None else None,
               weighting='first/last valid source observation')
    ids = _native_pairs(c)
    if not len(ids):
        for name in ('increment','reset_count','rollover_count'):
            c.emit('counter.'+name,status='insufficient_data',reason=c.time_reason or 'No adjacent supported counter observations')
        return
    policy=c.mapping.get('counter_policy') or {}
    reset=policy.get('reset','unresolved')
    modulus=policy.get('modulus')
    if reset not in ('unresolved','split','rollover'):
        raise ValueError('Unknown counter reset policy')
    if reset=='rollover':
        _finite(modulus,'Counter modulus',nonnegative=True)
        if modulus<=0 or not policy.get('source'):
            raise ValueError('Counter rollover requires a positive documented modulus')
    total, resets, rollovers = 0,0,0
    unresolved=False
    supported=float(np.sum(c.x[ids+1]-c.x[ids]))
    for i in ids:
        c.check()
        previous=c.values[i].item() if isinstance(c.values[i],np.generic) else c.values[i]
        current=c.values[i+1].item() if isinstance(c.values[i+1],np.generic) else c.values[i+1]
        delta=current-previous
        if delta<0:
            if reset=='rollover' and 0<=previous<modulus and 0<=current<modulus:
                delta=modulus-previous+current;rollovers+=1
                c.events.append(_counter_event(c,i,'counter_rollover',increment=delta,parameters=policy))
            else:
                resets+=1
                c.events.append(_counter_event(c,i,'counter_decrease',from_value=previous,to_value=current,parameters=policy))
                if reset=='unresolved': unresolved=True
                continue
        maximum=policy.get('maximum_increment')
        if maximum is not None and delta>_finite(maximum,'Maximum increment',nonnegative=True):
            unresolved=True
            c.events.append(_counter_event(c,i,'counter_excess_increment',increment=delta,parameters=policy))
            continue
        total+=delta
    reason='Unexplained counter decrease or out-of-policy increment prevents complete consumption' if unresolved else ''
    c.emit('counter.increment',total,status='partial' if unresolved or resets else 'computed',reason=reason,
           parameters=policy,weighting='sum of supported nonnegative increments; resets excluded',
           supported_duration_s=supported)
    c.emit('counter.reset_count',resets,'count',weighting='observed supported numeric decreases; not complete process episodes')
    c.emit('counter.rollover_count',rollovers,'count',weighting='documented modulus crossings')
    c.emit('counter.observation_rate',len(ids)/supported if supported else None,'1/s',
           weighting='supported adjacent increments / supported seconds')


def countdown_capability(projection,c):
    if not c.numeric:
        c.emit('countdown.availability',status='unsupported',reason='Countdown requires numeric values')
        return
    ids=_native_pairs(c); p=_parameters(c)
    for name,pos in (('initial',np.flatnonzero(c.finite)[:1]),('final',np.flatnonzero(c.finite)[-1:])):
        c.emit('countdown.'+name,float(c.y[pos[0]]) if len(pos) else None,weighting='source observations')
    if not len(ids):
        c.emit('countdown.progression',status='insufficient_data',reason=c.time_reason or 'No adjacent supported countdown observations')
        return
    delta=c.y[ids+1]-c.y[ids]
    c.emit('countdown.upward_revision_count',int(np.sum(delta>0)),'count',weighting='observed supported positive estimate changes')
    c.emit('countdown.downward_change_count',int(np.sum(delta<0)),'count',weighting='observed supported negative changes; includes normal countdown')
    for i in ids[delta>0]:
        c.events.append(_counter_event(c,i,'countdown_upward_revision',change=float(c.y[i+1]-c.y[i])))
    if 'pause_tolerance' in p:
        tol=_finite(p['pause_tolerance'],'Pause tolerance',nonnegative=True)
        c.emit('countdown.pause_duration',float(np.sum((c.x[ids+1]-c.x[ids])[np.abs(delta)<=tol])),'s',
               parameters={'pause_tolerance':tol},weighting='supported native intervals with absolute estimate change within tolerance')
    else:
        c.emit('countdown.pause_duration',unit='s',status='needs_mapping',reason='Explicit pause tolerance is required')
    if 'jump_threshold' in p:
        threshold=_finite(p['jump_threshold'],'Jump threshold',nonnegative=True)
        jumps=ids[np.abs(delta)>threshold]
        c.emit('countdown.jump_count',len(jumps),'count',parameters={'jump_threshold':threshold},weighting='supported numeric jumps above declared magnitude')
        for i in jumps: c.events.append(_counter_event(c,i,'countdown_jump',change=float(c.y[i+1]-c.y[i])))
    else:
        c.emit('countdown.jump_count',unit='count',status='needs_mapping',reason='Explicit jump threshold is required')
    completion=p.get('confirmed_completion_s')
    if completion is not None:
        completion=_finite(completion,'Confirmed completion')
        if UNITS.get(unit(c.unit),('unknown',))[0]!='time':
            c.emit('countdown.final_estimate_error',status='needs_mapping',reason='Remaining-time estimates require verified time units')
        elif len(ids):
            j=int(ids[-1]+1)
            c.emit('countdown.final_estimate_error',float(convert(c.y[j],c.unit,'s'))-(completion-float(c.x[j])),'s',
                parameters={'confirmed_completion_s':completion},weighting='last supported observation against explicitly confirmed completion')
    else:
        c.emit('countdown.final_estimate_error',unit='s',status='missing_input',reason='Actual completion time is not established; recording end is not assumed to be completion')


def _physical_ready(c,metric):
    authority=c.mapping.get('authority') or c.projection.get('provenance',{}).get('authority') or {}
    stored=(c.mapping.get('encoding') or {}).get('stored_values',c.projection.get('provenance',{}).get('stored_values','unresolved'))
    if not authority.get('reviewed') or stored=='unresolved' or c.projection.get('status') not in ('computed','partial'):
        c.emit(metric,status='needs_scaling',reason='Reviewed signal meaning and resolved raw/engineering encoding are required',
               remedy='Review authority, role, unit, stored-value encoding and transform provenance')
        return False
    return True


def _rotation(c):
    if UNITS.get(unit(c.unit),('unknown',))[0]!='rotation':
        c.emit('speed.rotation_duration',unit='s',status='needs_mapping',reason='Rotational-speed analysis requires verified RPM or rps units')
        return
    p=_parameters(c)
    if 'stationary_tolerance' not in p:
        c.emit('speed.stationary_duration',unit='s',status='needs_mapping',reason='Declare the stationary noise/tolerance band; no automatic zero-speed threshold is imposed')
        return
    tolerance=_finite(p['stationary_tolerance'],'Stationary tolerance',nonnegative=True)
    a,b,left,right=_pieces(c)
    stationary=_clip_duration(a,b,left,right,-tolerance,tolerance)
    total=c.stats.get('known_s',0)
    c.timed('speed.stationary_duration',stationary,'s',parameters={'stationary_tolerance':tolerance},weighting='supported time within declared stationary band')
    c.timed('speed.rotation_duration',max(0.,total-stationary),'s',parameters={'stationary_tolerance':tolerance},weighting='supported time outside declared stationary band; reported-speed activity')
    direction=c.mapping.get('direction') or {}
    if isinstance(direction,str): direction={'encoding':direction}
    if direction.get('confirmed') is True and direction.get('encoding') in ('signed','positive_negative'):
        for name,low,high in (('positive_duration',tolerance,None),('negative_duration',None,-tolerance)):
            c.timed('speed.'+name,_clip_duration(a,b,left,right,low,high),'s',parameters={'stationary_tolerance':tolerance,'direction':direction},weighting='supported time; documented signed mechanical direction')
        # Track direction through observed stationary dwell, but reset at every
        # unknown-support boundary. This avoids treating a gap as a reversal.
        reversals=0; sequence=[]; previous=None; previous_index=None
        ids=_native_pairs(c)
        for i in ids:
            if previous_index is None or i!=previous_index+1:
                previous=None
                sequence.append({'component_start_s':float(c.x[i]),'directions':[]})
            for j in (i,i+1):
                direction_value=1 if c.y[j]>tolerance else -1 if c.y[j]<-tolerance else 0
                if direction_value and direction_value!=previous:
                    if previous is not None: reversals+=1
                    sequence[-1]['directions'].append({'direction':direction_value,'observed_s':float(c.x[j]),'source_index':int(c.indices[j])})
                    previous=direction_value
            previous_index=i
        c.emit('speed.direction_reversal_count',reversals,'count',weighting='documented directional sequence through supported stationary dwell; no joining gaps')
        c.emit('speed.directional_sequence',sequence,'',weighting='native supported direction observations')
    else:
        c.emit('speed.directional_activity',status='needs_mapping',reason='Mechanical direction encoding is not confirmed; signed values remain numeric signs')
    from app_parameter_events import state_timeline
    activity=state_timeline(c.x,(np.abs(c.y)>tolerance).astype(int),valid=c.native_valid & np.isfinite(c.y),
        structure='binary',acquisition_policy=dict(c.policy,mode='held'),
        parameters={'stationary_tolerance':tolerance,'cancel':lambda:c.check() or False},
        identity={'run_id':c.run_id,'field_id':c.field_id,'instance':projection_instance(c),'role':c.projection.get('role',''), 'source_indices':c.indices.tolist()})
    for event in activity.get('events',[]):
        event=dict(event,type='reported_speed_active_bout',detector='reviewed_reported_speed_activity',
                   evidence_basis='sampled reported-speed threshold; physical motor state is not established')
        c.events.append(event)
    for name,key in (('observed_start_count','rising_count'),('observed_stop_count','falling_count')):
        c.emit('speed.'+name,activity.get('summary',{}).get(key),'count',parameters={'stationary_tolerance':tolerance},
            weighting='observed sampled reported-speed band transitions; initial activity is censored')
    slopes=(right-left)/(b-a) if len(a) else np.array([])
    for name,mask in (('ramp_up',slopes>0),('ramp_down',slopes<0)):
        c.timed('speed.'+name+'_duration',float(np.sum((b-a)[mask])),'s',weighting='strictly positive/negative supported reported-speed segment slope; not a confirmed controller attempt')
    plateau=p.get('plateau_slope_tolerance')
    if plateau is not None:
        plateau=_finite(plateau,'Plateau slope tolerance',nonnegative=True)
        mask=np.abs(slopes)<=plateau
        c.timed('speed.plateau_duration',float(np.sum((b-a)[mask])),'s',parameters={'slope_tolerance':plateau},weighting='supported segments within explicit absolute slope tolerance; may include stationary segments')
    else:
        c.emit('speed.plateau_duration',unit='s',status='needs_mapping',reason='Explicit plateau slope tolerance is required')
    for band in p.get('speed_bands',[]): _band(c,band,'speed.band')
    target=p.get('target_band')
    if target is not None:
        duration=_band(c,dict(target,name=target.get('name','target')),'speed.target')
        lo,hi=target.get('low'),target.get('high')
        c.timed('speed.target.attained',bool(duration>0),'',parameters=target,weighting='nonzero supported duration within declared target band')
        if hi is not None and np.any(c.finite):
            c.emit('speed.target.overshoot',max(0.,float(np.max(c.y[c.finite]))-float(hi)),statistic='difference',parameters=target,weighting='native extrema above target upper bound')
        intervals=_band_intervals(a,b,left,right,lo,hi)
        origin=float(c.scope.get('start_s',c.x[0])) if c.x is not None and len(c.x) else None
        c.timed('speed.target.time_to_reach',intervals[0][0]-origin if intervals and origin is not None else None,'s',
            parameters=target,weighting='first supported band-entry crossing relative to evaluation start')
        hold=target.get('hold_seconds'); settling_policy=target.get('settling_policy')
        if hold is not None and settling_policy in ('hold','through_end'):
            hold=_finite(hold,'Target hold duration',nonnegative=True)
            boundary=float(c.scope.get('end_s',c.x[-1])) if c.x is not None and len(c.x) else None
            eligible=[(start,stop) for start,stop in intervals if stop-start>=hold and
                (settling_policy=='hold' or boundary is not None and abs(stop-boundary)<=1e-9)]
            c.timed('speed.target.settling_time',eligible[0][0]-origin if eligible and origin is not None else None,'s',
                parameters=target,weighting='earliest supported continuous target-band hold under explicit exit policy')
        else:
            c.emit('speed.target.settling_time',unit='s',status='needs_mapping',reason='Settling requires explicit hold_seconds and settling_policy (hold or through_end)')
    for name in ('confirmed_retry_count','soak_duration','impact_count'):
        c.emit('speed.'+name,status='missing_input',reason='A documented process/event definition and supporting signals are required; reported speed alone does not establish this physical event')


def projection_instance(c):
    return str(c.projection.get('instance') or '')


def role_capabilities(projection,c):
    role=str(projection.get('role') or '')
    operations=_parameters(c).get('operations',[])
    if not isinstance(operations,list) or any(not isinstance(v,str) for v in operations):
        raise ValueError('Operations must be a list of registered operation identifiers')
    if role not in ('rotational_speed','speed','flow','measured_flow','power','active_power','vibration','acceleration') and not set(operations)&{'rotation','integrate_flow','integrate_active_power','waveform'}:
        return
    if not _physical_ready(c,'semantic.availability'): return
    if role in ('rotational_speed','speed') or 'rotation' in operations: _rotation(c)
    dimension=UNITS.get(unit(c.unit),('unknown',))[0]
    integrate_flow=role in ('flow','measured_flow') or 'integrate_flow' in operations
    integrate_power=role in ('power','active_power') or 'integrate_active_power' in operations
    if integrate_flow:
        if dimension!='flow' or projection.get('signal_kind') not in ('measurement','feedback'):
            c.emit('measured_flow.supported_volume',unit='L',status='needs_mapping',reason='Integrated volume requires measured flow/feedback with verified flow dimensions; actuator duration is not flow')
        else:
            factor=float(convert(1,c.unit,'L/s'))
            c.timed('measured_flow.supported_volume',c.stats.get('integral',float('nan'))*factor,'L',weighting='integrated supported measured flow; missing periods excluded')
    if integrate_power:
        if dimension!='power' or projection.get('signal_kind') not in ('measurement','feedback'):
            c.emit('active_power.supported_energy',unit='Wh',status='needs_mapping',reason='Energy requires measured active power with verified power units; commands and V×I alone do not establish active power')
        else:
            factor=float(convert(1,c.unit,'W'))/3600
            c.timed('active_power.supported_energy',c.stats.get('integral',float('nan'))*factor,'Wh',weighting='integrated supported measured active power; missing periods excluded')
    if role in ('vibration','acceleration') or 'waveform' in operations:
        finite=c.y[c.finite]
        rms=c.stats.get('rms')
        c.timed('waveform.crest_factor',float(np.max(np.abs(finite)))/rms if len(finite) and rms else None,'1',weighting='native absolute peak / supported-time RMS')
        c.emit('waveform.spectrum',status='missing_input',reason='Spectrum requires reviewed sample rate, bandwidth and waveform acquisition capability; telemetry rate is insufficient evidence')

"""Deterministic appliance KPIs, phases and quality-aware anomaly evaluation."""
import math
import operator
import numpy as np
from app_appliance_profiles import recognize,validate_profile,channel_key
from app_engineering_trace import Trace
from app_engineering_units import convert,convert_difference,seconds,UNITS,unit


def unavailable(definition,reason):
    return {'id':definition['id'],'name':definition.get('name',definition['id']),'group':definition.get('group','General'),'value':None,'unit':definition.get('unit',''),'status':'Not Available','reason':reason,'coverage':0.,'definition':dict(definition),'acceptance':'Not Evaluated'}


def resolved_channels(store,profile,mappings=None,dataset_id=None):
    rows=recognize(store,profile,mappings,dataset_id);groups={}
    for row in rows:
        if row['canonical_id']:groups.setdefault(row['canonical_id'],[]).append(row['channel_id'])
    # Multiple matches in one run are never resolved by first-channel accident.
    return {key:store.channels[ids[0]] for key,ids in groups.items() if len(ids)==1},rows


def make_trace(channel,key,profile,offset=0,source_unit=None):
    spec=next(c for c in profile['channels'] if c['id']==key)
    if channel.attributes.get('reference_calibration_verified') is False:raise ValueError('Reference calibration is not verified for engineering KPIs')
    if channel.source.lower().endswith(('.png','.jpg','.jpeg','.bmp','.tif','.tiff')) and not channel.attributes.get('reference_calibration_verified'):raise ValueError('Raster reference needs verified calibration before engineering calculation')
    calibration=profile.get('calibrations',{}).get(spec.get('calibration',''))
    if spec.get('calibration') and calibration is None:raise ValueError('Configured calibration is missing')
    trace=Trace(channel,spec['unit'],calibration,profile.get('extensions',{}).get('max_gap_seconds'),offset,source_unit)
    if spec['data_type'] in ('state','code','count'):trace.kind='discrete'
    if spec['data_type']=='state':
        trace.y=np.where(np.isfinite(trace.y)&(trace.y==np.floor(trace.y)),trace.y,np.nan)
        trace.raw_y=np.where(np.isfinite(trace.raw_y)&(trace.raw_y==np.floor(trace.raw_y)),trace.raw_y,np.nan)
    return trace


def conditions_mask(conditions,traces,grid):
    mask=np.ones(max(0,len(grid)-1),bool);known=mask.copy()
    operators={'eq':operator.eq,'ne':operator.ne,'gt':operator.gt,'ge':operator.ge,'lt':operator.lt,'le':operator.le}
    for rule in conditions:
        trace=traces.get(rule['channel'])
        if trace is None:return mask&False,known&False
        # Midpoints give held states their correct half-open interval semantics.
        values=trace.sample((grid[:-1]+grid[1:])/2);finite=np.isfinite(values);known&=finite
        op=rule['op']
        if op in ('on','off'):
            valid=finite&(values==np.floor(values));selected=values!=0 if op=='on' else values==0;known&=valid
        elif op=='in':selected=np.isin(values,rule.get('values',[]))
        else:selected=operators[op](values,rule['value'])
        if 'off_threshold' in rule and op in ('gt','ge','lt','le'):
            active=False;result=[]
            for value,is_finite in zip(values,finite):
                if not is_finite:active=False
                elif active:active=bool(value>rule['off_threshold'] if op in ('gt','ge') else value<rule['off_threshold'])
                else:active=bool(operators[op](value,rule['value']))
                result.append(active)
            selected=np.array(result)
        mask&=selected&known
    return mask,known


def intervals(grid,mask,minimum=0,debounce=0):
    result=[];start=None
    for i,active in enumerate(mask):
        if active and start is None:start=float(grid[i])
        if start is not None and (not active or i==len(mask)-1):
            end=float(grid[i] if not active else grid[i+1]);begin=start+debounce
            if end>begin and end-begin>=minimum:result.append((begin,end))
            start=None
    return result


def condition_grid(conditions,traces):
    knots=[]
    for rule in conditions:
        trace=traces[rule['channel']];knots.extend(trace.t)
        if trace.kind!='analog':continue
        thresholds=[rule[k] for k in ('value','off_threshold') if k in rule and isinstance(rule[k],(int,float))]
        for threshold in thresholds:
            left=trace.y[:-1]-threshold;right=trace.y[1:]-threshold;d=np.diff(trace.t)
            valid=np.isfinite(left)&np.isfinite(right)&(left*right<0)&(d<=trace.max_gap)
            roots=trace.t[:-1][valid]-left[valid]*d[valid]/(right[valid]-left[valid]);knots.extend(roots)
    return np.unique(knots)


def detect_phases(profile,traces):
    result=[]
    for definition in profile.get('phases',[]):
        rules=definition.get('conditions',[])
        if not rules or any(rule['channel'] not in traces for rule in rules):continue
        grid=condition_grid(rules,traces)
        mask,_=conditions_mask(rules,traces,grid)
        for a,b in intervals(grid,mask,definition.get('minimum_seconds',0),definition.get('debounce_seconds',0)):
            result.append({'name':definition['name'],'start_s':a,'end_s':b,'duration_s':b-a,'definition':definition})
    return sorted(result,key=lambda r:(r['start_s'],r['name']))


def evaluate_kpi(definition,traces,profile,phases,start=None,end=None,run_bounds=None):
    result=unavailable(definition,'Required channel is not mapped or has no verified unit');key=definition['channel'];op=definition['op'];trace=traces.get(key)
    if op=='duration' and definition.get('allow_any_time') and run_bounds is not None:
        windows=[(max(run_bounds[0],start) if start is not None else run_bounds[0],min(run_bounds[1],end) if end is not None else run_bounds[1])]
        if definition.get('phase'):windows=[(p['start_s'],p['end_s']) for p in phases if p['name']==definition['phase']]
        if not windows:result['reason']='Configured phase was not observed';return result
        duration=sum(max(0,b-a) for a,b in windows);value=float(convert(duration,'s',definition['unit']))
        result.update(value=value,status='Available',coverage=1.,reason='First-to-last recorded time, not an inferred firmware cycle boundary')
        limits=profile.get('acceptance',{}).get(definition['id'])
        if limits:
            tested=float(convert(value,definition['unit'],limits.get('unit',definition['unit'])));result['acceptance']='Pass' if limits.get('min',-math.inf)<=tested<=limits.get('max',math.inf) else 'Fail'
        return result
    if op=='duration' and definition.get('allow_any_time') and trace is None:trace=next(iter(traces.values()),None)
    if trace is None:return result
    if op in ('mean','rms','std'):
        try:trace=trace.to_unit(definition.get('unit',''))
        except ValueError as exc:result['reason']=str(exc);return result
    windows=[(start,end)]
    if definition.get('phase'):
        windows=[(p['start_s'],p['end_s']) for p in phases if p['name']==definition['phase']]
        if not windows:result['reason']='Configured phase was not observed';return result
    stats=[trace.stats(a,b) for a,b in windows];duration=sum(s['duration_s'] for s in stats);known=sum(s.get('known_s',0) for s in stats)
    coverage=known/duration if duration else 0
    supported=[s for s in stats if s.get('samples',0)]
    if not supported:result['reason']='No finite samples in the selected interval';return result
    target=definition.get('unit','');source=trace.unit
    try:
        if op=='duration':value=float(convert(duration,'s',target))
        elif op in ('integral','pulse_volume'):
            if not known:return result
            area=sum(s.get('integral',0) for s in stats if s.get('known_s',0))
            if op=='pulse_volume':
                cal=profile.get('calibrations',{}).get(definition.get('calibration',''),{})
                if not cal.get('verified') or not cal.get('id') or 'volume_per_pulse' not in cal:raise ValueError('Verified pulse calibration is required')
                counts=sum(s['last']-s['first'] for s in supported)
                resets=any(np.any(np.diff(trace.recorded_window(a,b))<0) for a,b in windows)
                if resets or counts<0:raise ValueError('Pulse counter reset requires an explicit reset policy')
                value=float(convert(counts*cal['volume_per_pulse'],cal['output_unit'],target))
            elif UNITS[unit(source)][0]=='power':value=float(convert(float(convert(area,source,'W')),'J',target))
            elif UNITS[unit(source)][0]=='flow':value=float(convert(float(convert(area,source,'L/s')),'L',target))
            else:raise ValueError('Integral output needs a compatible physical dimension')
        elif op=='on_duration':
            if not known:result['reason']='No supported actuator time intervals';return result
            if source!='state':raise ValueError('ON duration requires a mapped actuator state')
            value=0.
            for a,b in windows:
                t,y=trace.window(a,b);d=np.diff(t);valid=np.isfinite(y[:-1])&np.isfinite(y[1:])&(d<=trace.max_gap)&(y[:-1]==np.floor(y[:-1]))
                value+=float(d[valid&(y[:-1]!=0)].sum())
            value=float(convert(value,'s',target))
        elif op in ('mean','rms','std'):
            if not known:return result
            mean=sum(s.get('mean',0)*s.get('known_s',0) for s in stats if s.get('known_s',0))/known
            square=sum(s.get('rms',0)**2*s.get('known_s',0) for s in stats if s.get('known_s',0))/known
            variance=sum((s.get('std',0)**2+(s.get('mean',0)-mean)**2)*s.get('known_s',0) for s in stats if s.get('known_s',0))/known
            raw=mean if op=='mean' else math.sqrt(max(0,square if op=='rms' else variance))
            # Standard deviations are differences, so affine offsets must cancel.
            value=float(convert(raw,source,target)-(convert(0,source,target) if op=='std' else 0))
        elif op in ('min','max','absmax'):
            raw=(min if op=='min' else max)(s[op] for s in supported);value=float(convert(raw,source,target))
        elif op in ('first','last'):value=float(convert(supported[0 if op=='first' else -1][op],source,target))
        elif op=='counter':
            value=sum(s['last']-s['first'] for s in supported)
            resets=any(np.any(np.diff(trace.recorded_window(a,b))<0) for a,b in windows)
            if resets or value<0:raise ValueError('Counter reset: increase cannot be inferred')
            value=float(convert(value,source,target))
        elif op=='slope':
            if duration<=0 or not known:return result
            for a,b in windows:
                _,edge_values=trace.window(a,b)
                if not len(edge_values) or not np.isfinite(edge_values[[0,-1]]).all():raise ValueError('Slope requires supported start and end values')
            delta=sum(s['last']-s['first'] for s in supported)
            if UNITS[unit(source)][0]=='temperature' and target=='°C/min':value=delta*UNITS[unit(source)][1]/duration*60
            elif UNITS[unit(source)][0]=='rotation' and target=='RPM/s':value=float(convert(delta,source,'RPM'))/duration
            elif UNITS[unit(source)][0]=='volume' and target=='L/min':value=float(convert(delta,source,'L'))/duration*60
            elif UNITS[unit(source)][0]=='volume' and target=='L/s':value=float(convert(delta,source,'L'))/duration
            else:raise ValueError('Slope target unit does not match channel dimension')
        elif op in ('difference','ratio'):
            other=traces.get(definition.get('other_channel'))
            if other is None:raise ValueError('Second required channel is unavailable')
            right=other.stats(start,end).get('mean',np.nan);left=supported[0].get('mean',np.nan)
            right=float(convert(right,other.unit,source))
            if op=='difference':value=float(convert(left-right,source,target)-convert(0,source,target))
            else:
                if right==0:raise ValueError('Ratio denominator is zero')
                value=float(convert(left/right,'',target))
        else:raise ValueError('Unsupported KPI operation')
        value*=float(definition.get('scale',1))
        if not np.isfinite(value):raise ValueError('Insufficient finite data')
        result.update(value=value,status='Available' if coverage>=1-1e-9 else 'Partial coverage',reason='' if coverage>=1-1e-9 else 'Computed only over supported intervals',coverage=coverage)
        ambiguous=bool(trace.duplicates)
        if ambiguous:result.update(status='Duplicate timestamp timing',reason='Timing uses the last duplicate; peaks retain all recorded samples')
        estimated=trace.channel.attributes.get('values_estimated_from_pixels',False)
        if estimated:result.update(status='Estimated source',reason='Calibrated raster estimate; not a direct sensor measurement')
        limits=profile.get('acceptance',{}).get(definition['id'])
        if limits and coverage>=1-1e-9 and not estimated and not ambiguous:
            tested=float((convert_difference if op in ('std','difference') else convert)(value,target,limits.get('unit',target)))
            result['acceptance']='Pass' if limits.get('min',-math.inf)<=tested<=limits.get('max',math.inf) else 'Fail'
    except (ValueError,KeyError,TypeError,OverflowError) as exc:result['reason']=str(exc)
    return result


def anomalies(profile,traces):
    result=[]
    for rule in profile.get('anomalies',[]):
        name=rule.get('name','Configured anomaly');kind=rule.get('type','condition');trace=traces.get(rule.get('channel'))
        events=[];evaluated=False
        if trace is not None and len(trace.t)>1:
            if kind=='dropout':
                mask=(~np.isfinite(trace.y[:-1]))|(~np.isfinite(trace.y[1:]))|(np.diff(trace.t)>trace.max_gap)
                events=intervals(trace.t,mask,rule.get('minimum_seconds',0));evaluated=True
            elif kind=='sequence':
                steps=rule.get('sequence',[])
                if len(steps)>=2 and all(step['channel'] in traces for step in steps):
                    observations=[];known_all=True
                    for number,step in enumerate(steps):
                        grid=condition_grid([step],traces);mask,known=conditions_mask([step],traces,grid);known_all&=bool(len(known) and known.all())
                        for a,b in intervals(grid,mask):
                            if a>grid[0] or rule.get('include_initial_state',False):observations.append((a,number))
                    current=0;start=None;within=float(rule['within_seconds'])
                    for moment,number in sorted(observations):
                        if start is not None and moment-start>within:current=0;start=None
                        if number==0:current=1;start=moment
                        elif number==current:
                            current+=1
                            if current==len(steps):events.append((start,moment));current=0;start=None
                    evaluated=known_all
            elif kind in ('condition','fault','oob'):
                rules=rule.get('conditions',[])
                if kind=='fault':rules=[{'channel':rule['channel'],'op':'in','values':rule.get('fault_values',[])}]
                if kind=='oob':rules=[{'channel':rule['channel'],'op':'gt','value':rule.get('threshold',0)}]
                if rules and all(r['channel'] in traces for r in rules):
                    grid=condition_grid(rules,traces);mask,known=conditions_mask(rules,traces,grid);events=intervals(grid,mask,rule.get('minimum_seconds',0),rule.get('debounce_seconds',0));evaluated=bool(len(known) and known.all())
            elif kind=='stall':
                window=float(rule.get('window_seconds',0));threshold=rule.get('maximum_change')
                if window>0 and threshold is not None:
                    previous=trace.sample(trace.t-window);valid=np.isfinite(previous)&np.isfinite(trace.y)
                    valid&=(trace.coverage_at(trace.t)-trace.coverage_at(trace.t-window)>=window-1e-9)
                    mask=valid&(np.abs(trace.y-previous)<=float(threshold));events=intervals(trace.t,mask[:-1],rule.get('minimum_seconds',window));eligible=trace.t-window>=trace.t[0];evaluated=bool(eligible.any() and valid[eligible].all())
        if events:
            for a,b in events:result.append({'name':name,'type':kind,'status':'Detected','start_s':a,'end_s':b,'duration_s':b-a,'evidence':rule})
        else:result.append({'name':name,'type':kind,'status':'Not detected' if evaluated else 'Not evaluated','start_s':None,'end_s':None,'duration_s':None,'evidence':rule})
    return result


def analyze_run(store,profile,mappings=None,dataset_id=None,offset=0,cancel=None,source_units=None):
    profile=validate_profile(profile);channels,rows=resolved_channels(store,profile,mappings,dataset_id);traces={};warnings=[]
    for key,channel in channels.items():
        if cancel and cancel.is_set():raise InterruptedError('Engineering analysis cancelled')
        try:
            declared=(source_units or {}).get(channel.id,(source_units or {}).get(channel_key(channel)))
            traces[key]=make_trace(channel,key,profile,offset,declared)
            duplicates=len(channel.x)-len(traces[key].t)
            if duplicates:warnings.append(f'{channel.name}: {duplicates} duplicate timestamps retained in source; analysis uses the last sample at each timestamp')
        except ValueError as exc:warnings.append(f'{channel.name}: {exc}')
    clocks=[seconds(c)+offset for c in store.channels.values() if (dataset_id is None or c.dataset_id==dataset_id) and c.coordinate_kind=='time' and len(c.x) and not c.attributes.get('engineering_projection')]
    run_bounds=(min(float(t[0]) for t in clocks),max(float(t[-1]) for t in clocks)) if clocks else None
    phases=detect_phases(profile,traces)
    results=[evaluate_kpi(kpi,traces,profile,phases,run_bounds=run_bounds) for kpi in profile['kpis']]
    phase_rows=[]
    for phase in phases:
        if cancel and cancel.is_set():raise InterruptedError('Engineering analysis cancelled')
        metrics=[evaluate_kpi({k:v for k,v in kpi.items() if k!='phase'},traces,profile,[],phase['start_s'],phase['end_s'],run_bounds) for kpi in profile['kpis']]
        phase_rows.append({**phase,'metrics':metrics})
    return {'profile':profile,'mapping':rows,'kpis':results,'phases':phase_rows,'anomalies':anomalies(profile,traces),'warnings':warnings,'traces':traces,'dataset_id':dataset_id,'offset_s':offset,'quality_policy':'Last duplicate sample; no extrapolation; analog linear/discrete held; gaps > configured limit or 3× median sample interval excluded'}

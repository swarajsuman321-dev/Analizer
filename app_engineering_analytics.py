"""Deterministic appliance KPIs, phases and quality-aware anomaly evaluation."""
import math
import operator
import hashlib
import re
import numpy as np
from app_appliance_profiles import recognize,validate_profile,channel_key
from app_engineering_trace import Trace
from app_engineering_units import convert,convert_difference,seconds,UNITS,unit


def unavailable(definition,reason):
    return {'id':definition['id'],'name':definition.get('name',definition['id']),'group':definition.get('group','General'),'value':None,'unit':definition.get('unit',''),'status':'Not Available','reason':reason,'coverage':0.,'definition':dict(definition),'acceptance':'Not Evaluated'}


def reviewed_mapping_rows(store,profile,mappings=None,dataset_id=None,source_units=None):
    """Attach trust decisions without guessing ambiguous physical source roles.

    Legacy explicit mappings remain confirmations. Alias recognition is a proposal;
    ambiguous speed names and incompatible sensor dimensions require review.
    """
    rows=recognize(store,profile,mappings,dataset_id)
    definitions={c['id']:c for c in profile['channels']}
    for row in rows:
        channel=store.channels[row['channel_id']];key=row['canonical_id']
        declared=(source_units or {}).get(channel.id,(source_units or {}).get(channel_key(channel)))
        row['recorded_unit']=channel.unit;row['source_unit']=declared if declared is not None else channel.unit
        row['unit_review_status']='Confirmed' if declared is not None or channel.attributes.get('unit_detection')=='user confirmed' else ('Unverified inference' if channel.attributes.get('unit_detection') in ('signal name','inferred','name') or channel.attributes.get('engineering_unit_verified') is False else 'Recorded')
        row['mapping_confirmed']=row['method'] in ('user confirmed','confirmed template')
        row['review_status']='Confirmed' if row['mapping_confirmed'] else 'Recognized'
        row['review_reason']='';row['usable']=bool(key)
        row['canonical_role']=definitions[key]['name'] if key else ''
        row['calibration_id']=''
        words=set(re.findall(r'[a-z]+',str(row['source_name']).casefold()))
        if key=='speed' and row['review_status']!='Confirmed':
            row.update(usable=False,review_status='Review required',review_reason='Actual/feedback speed role is not confirmed; review the physical source before drawing an actual-speed conclusion')
        if key:
            spec=definitions[key];calibration=profile.get('calibrations',{}).get(spec.get('calibration',''))
            if calibration:row['calibration_id']=calibration.get('id','')
            try:
                convert([0.],row['source_unit'],calibration['input_unit'] if calibration else spec['unit'])
                if calibration and not calibration.get('verified'):raise ValueError('Configured calibration is not verified')
                if channel.attributes.get('engineering_unit_verified') is False and declared is None:
                    raise ValueError('Comparison display unit is unverified; confirm the original source unit before engineering calculation')
                if channel.attributes.get('unit_detection') in ('signal name','inferred','name') and declared is None:
                    raise ValueError('Source unit was inferred from its name and has not been confirmed')
            except (ValueError,KeyError) as exc:
                row.update(usable=False,review_status='Unit / calibration review required',review_reason=str(exc))
        elif words.intersection({'speed'}) and words.intersection({'feedback','actual','measured'}) and 'speed' in definitions:
            # A familiar-but-unrecognized name is a suggestion, never an automatic substitution.
            row.update(review_status='Review required',review_reason='Possible actual speed source; confirm its canonical role',candidates=list(dict.fromkeys([*row['candidates'],'speed'])))
    groups={}
    for row in rows:
        if row['canonical_id']:groups.setdefault(row['canonical_id'],[]).append(row)
    for key,matches in groups.items():
        confirmed=[row for row in matches if row['mapping_confirmed']]
        if len(confirmed)==1 and confirmed[0]['usable']:
            for row in matches:
                if row is not confirmed[0]:row.update(usable=False,review_reason='Another source was explicitly confirmed for this canonical role')
        elif len(matches)>1:
            for row in matches:row.update(usable=False,review_status='Ambiguous mapping',review_reason='; '.join(filter(None,[row.get('review_reason'),'Multiple sources claim this role; select one source or review its calibrated sensor meaning'])))
    return rows


def resolved_channels(store,profile,mappings=None,dataset_id=None,source_units=None):
    rows=reviewed_mapping_rows(store,profile,mappings,dataset_id,source_units)
    return {row['canonical_id']:store.channels[row['channel_id']] for row in rows if row['usable']},rows


def make_trace(channel,key,profile,offset=0,source_unit=None):
    spec=next(c for c in profile['channels'] if c['id']==key)
    if channel.attributes.get('reference_calibration_verified') is False and not (source_unit is not None and channel.attributes.get('reference_type')=='table' and channel.attributes.get('reference_time_verified')):raise ValueError('Reference calibration is not verified for engineering KPIs')
    if channel.source.lower().endswith(('.png','.jpg','.jpeg','.bmp','.tif','.tiff')) and not channel.attributes.get('reference_calibration_verified'):raise ValueError('Raster reference needs verified calibration before engineering calculation')
    calibration=profile.get('calibrations',{}).get(spec.get('calibration',''))
    if spec.get('calibration') and calibration is None:raise ValueError('Configured calibration is missing')
    trace=Trace(channel,spec['unit'],calibration,profile.get('extensions',{}).get('max_gap_seconds'),offset,source_unit,profile.get('extensions',{}).get('acquisition_policy'))
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
                if coverage<1-1e-9:raise ValueError('Pulse-counter volume needs continuous supported acquisition; counter changes across unknown gaps are not a supported-time total')
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
            if coverage<1-1e-9:raise ValueError('Counter increase needs continuous supported acquisition; resets or changes during unknown gaps cannot be excluded')
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
        if ambiguous:
            result['status']='Duplicate timestamp timing'
            result['reason']='; '.join(filter(None,[result['reason'],'Timing uses the last duplicate; peaks retain all recorded samples']))
        estimated=trace.channel.attributes.get('values_estimated_from_pixels',False)
        if estimated:result.update(status='Estimated source',reason='Calibrated raster estimate; not a direct sensor measurement')
        limits=profile.get('acceptance',{}).get(definition['id'])
        if limits and coverage>=1-1e-9 and not estimated and not ambiguous:
            tested=float((convert_difference if op in ('std','difference') else convert)(value,target,limits.get('unit',target)))
            result['acceptance']='Pass' if limits.get('min',-math.inf)<=tested<=limits.get('max',math.inf) else 'Fail'
    except (ValueError,KeyError,TypeError,OverflowError) as exc:result['reason']=str(exc)
    return result


def anomalies(profile,traces,quality_traces=None):
    result=[]
    for rule in profile.get('anomalies',[]):
        name=rule.get('name','Configured anomaly');kind=rule.get('type','condition');trace=(quality_traces or traces).get(rule.get('channel')) if kind=='dropout' else traces.get(rule.get('channel'))
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
    quality_sources={**traces,**(quality_traces or {})}
    policies={key:trace.quality()['acquisition_policy'] for key,trace in quality_sources.items()}
    trusted_ids={trace.channel.id for trace in traces.values()}
    for index,event in enumerate(result):
        event['category']='Data Quality' if event['type']=='dropout' else ('Rule Evaluation' if event['status']=='Not evaluated' else 'Appliance Event')
        signature=repr((event['name'],event['type'],event['evidence'].get('channel'),event['start_s'],event['end_s']))
        event['event_id']='EV-'+hashlib.sha256(signature.encode('utf-8')).hexdigest()[:16]
        trace=quality_sources.get(event['evidence'].get('channel'))
        if event['type']=='dropout':
            if trace is not None:
                event['source_channel_id']=trace.channel.id;event['source_name']=trace.channel.name
                event['source_role_review']=getattr(trace,'source_role_review','Recognized')
                if trace.channel.id not in trusted_ids:event['name']=trace.channel.name+' · acquisition gaps (physical role requires review)'

            event['interpretation']='Acquisition evidence only; a sampling gap does not establish an appliance fault'
            event['gap_threshold_s']=trace.max_gap if trace is not None else None
            event['acquisition_policy']=policies[event['evidence'].get('channel')] if trace is not None else 'Not evaluated: source missing'
    return result


def analyze_run(store,profile,mappings=None,dataset_id=None,offset=0,cancel=None,source_units=None):
    profile=validate_profile(profile)
    extensions=profile.get('extensions',{});policy=extensions.get('acquisition_policy',{})
    if not isinstance(policy,dict) or ('reviewed' in policy and not isinstance(policy['reviewed'],bool)):raise ValueError('Acquisition policy requires a name and an explicit reviewed flag')
    minimum_coverage=extensions.get('minimum_coverage',{})
    if not isinstance(minimum_coverage,dict) or any(isinstance(value,bool) or not isinstance(value,(int,float)) or not np.isfinite(value) or not 0<=value<=1 for value in minimum_coverage.values()):raise ValueError('Configured coverage requirements must be finite fractions from 0 to 1')
    channels,rows=resolved_channels(store,profile,mappings,dataset_id,source_units);traces={};warnings=[]
    for key,channel in channels.items():
        if cancel and cancel.is_set():raise InterruptedError('Engineering analysis cancelled')
        try:
            declared=(source_units or {}).get(channel.id,(source_units or {}).get(channel_key(channel)))
            traces[key]=make_trace(channel,key,profile,offset,declared)
            duplicates=len(channel.x)-len(traces[key].t)
            if duplicates:warnings.append(f'{channel.name}: {duplicates} duplicate timestamps retained in source; analysis uses the last sample at each timestamp')
        except ValueError as exc:
            warnings.append(f'{channel.name}: {exc}')
            for row in rows:
                if row['channel_id']==channel.id:row.update(usable=False,review_status='Unit / calibration review required',review_reason=str(exc))
    clocks=[seconds(c)+offset for c in store.channels.values() if (dataset_id is None or c.dataset_id==dataset_id) and c.coordinate_kind=='time' and len(c.x) and not c.attributes.get('engineering_projection')]
    run_bounds=(min(float(t[0]) for t in clocks),max(float(t[-1]) for t in clocks)) if clocks else None
    quality_traces=dict(traces)
    for row in rows:
        key=row.get('canonical_id')
        if key and key not in quality_traces and sum(item.get('canonical_id')==key for item in rows)==1:
            channel=store.channels[row['channel_id']]
            try:
                raw=Trace(channel,max_gap_seconds=extensions.get('max_gap_seconds'),offset=offset,acquisition_policy=policy)
                raw.source_role_review=row['review_status'];quality_traces[key]=raw
            except ValueError:pass  # A non-time coordinate cannot support timing evidence.
    phases=detect_phases(profile,traces)
    results=[evaluate_kpi(kpi,traces,profile,phases,*(run_bounds or (None,None)),run_bounds=run_bounds) for kpi in profile['kpis']]
    phase_rows=[]
    for phase in phases:
        if cancel and cancel.is_set():raise InterruptedError('Engineering analysis cancelled')
        metrics=[evaluate_kpi({k:v for k,v in kpi.items() if k!='phase'},traces,profile,[],phase['start_s'],phase['end_s'],run_bounds) for kpi in profile['kpis']]
        phase_rows.append({**phase,'metrics':metrics})
    run={'profile':profile,'mapping':rows,'kpis':results,'phases':phase_rows,'anomalies':anomalies(profile,traces,quality_traces),'warnings':warnings,'traces':traces,'quality_traces':quality_traces,'dataset_id':dataset_id,'offset_s':offset,'run_bounds':run_bounds,'report_scope':'whole_recording','quality_policy':'Last duplicate sample; no extrapolation; analog linear/discrete held; gaps > configured limit or 3× median sample interval excluded'}
    return enrich_readiness(run,*(run_bounds or (None,None)))


TIMING_OPS={'integral','pulse_volume','on_duration','mean','rms','std','slope','difference','ratio','counter'}


def enrich_readiness(run,start=None,end=None):
    """Explain results before presentation; retain independent quality warnings."""
    readiness=[];profile=run['profile'];traces=run['traces'];mapping=run['mapping']
    for result in run['kpis']:
        definition=result['definition'];key=definition['channel'];trace=traces.get(key)
        sources=[row for row in mapping if row.get('canonical_id') in (key,definition.get('other_channel')) and row.get('canonical_id') is not None or key in row.get('candidates',[])]
        result['source_details']=[{k:row.get(k) for k in ('channel_id','source_name','name','source_unit','canonical_id','canonical_role','method','review_status','unit_review_status','calibration_id','review_reason')} for row in sources]
        quality=trace.quality(start,end) if trace else {}
        result['quality']=quality;result['quality_flags']=list(quality.get('quality_flags',[]))
        blocker='';action='';reason=result.get('reason','')
        if result['value'] is None:
            if not sources:
                blocker='Missing source';reason='No source selected for canonical role '+key;action='Add the required recording or review its channel mapping in Engineering Setup'
            elif not trace:
                ambiguous=any(row.get('review_status')=='Ambiguous mapping' for row in sources)
                units=any('calibration' in row.get('review_status','').lower() for row in sources)
                blocker='Ambiguous mapping' if ambiguous else ('Unverified unit / calibration' if units else 'Unreviewed source role')
                reason='; '.join(dict.fromkeys(row.get('review_reason','') for row in sources if row.get('review_reason'))) or reason
                action='Select the intended source and explicitly confirm its role and source unit; configure a verified calibration if dimensions differ'
            elif definition.get('phase') and not any(p['name']==definition['phase'] for p in run['phases']):
                blocker='Unsupported phase';action='Configure verified phase-code meanings and boundary rules, then check timing coverage'
            elif 'calibration' in reason.lower() or 'conversion' in reason.lower():
                blocker='Unverified unit / calibration';action='Confirm the logger unit or configure a verified calibration with its reference identifier'
            else:
                blocker='Insufficient supported data';action='Review missing readings, masks, counter resets and acquisition coverage for the selected scope'
            result['reason']=reason
        elif quality and definition['op'] in TIMING_OPS and quality['coverage']<1-1e-9:
            blocker='Incomplete timing coverage';action='Review acquisition policy and the unsupported intervals before using a complete-run total'
        required=profile.get('extensions',{}).get('minimum_coverage',{}).get(definition['id'])
        if required is not None and quality and quality['coverage']<float(required):
            blocker='Insufficient configured coverage';action='Supply supported data meeting the reviewed test-plan coverage requirement'
            result['quality_flags'].append('Below configured coverage requirement');result['acceptance']='Not Evaluated'
        if not action and result['acceptance']=='Not Evaluated':action='Configure applicable acceptance limits and their plan revision to evaluate acceptance'
        result['blocker']=blocker;result['next_action']=action
        result['quantity_basis']='Supported-time total' if definition['op'] in ('integral','pulse_volume','on_duration') else ('Observed sample statistic' if definition['op'] in ('max','min','absmax','first','last') else 'Supported intervals')
        readiness.append({'result_id':result['id'],'name':result['name'],'state':blocker or ('Usable result' if result['value'] is not None else 'Not Available'),
                          'reason':result['reason'],'next_action':action,'usable':result['value'] is not None,'acceptance':result['acceptance']})
    # Phase and acceptance setup are independent of source/KPI calculations.
    if not any(phase.get('conditions') for phase in profile.get('phases',[])):
        readiness.append({'result_id':'phases','name':'Phase interpretation','state':'Unsupported phase','reason':'No reviewed phase interpretation configured','next_action':'Confirm phase-code meaning, conditions and timing policy','usable':False,'acceptance':'Not Evaluated'})
    if not profile.get('acceptance'):
        readiness.append({'result_id':'acceptance','name':'Acceptance evaluation','state':'Unconfigured acceptance','reason':'No applicable acceptance limits configured','next_action':'Enter the approved test-plan limits and record their revision/source','usable':False,'acceptance':'Not Evaluated'})
    blockers=[row for row in readiness if row['state']!='Usable result']
    run['readiness']=readiness
    run['readiness_summary']={'calculation':'Complete','usable_results':sum(k['value'] is not None for k in run['kpis']),
                              'total_results':len(run['kpis']),'data_adequacy':'Needs review' if blockers else 'Supported for calculated scope',
                              'acceptance':'Evaluated' if any(k['acceptance'] in ('Pass','Fail') for k in run['kpis']) else 'Not Evaluated',
                              'top_blockers':blockers[:3]}
    return run


def scoped_run(run,start_s,end_s):
    """Recalculate interval results, never scale a whole-run KPI by a time ratio."""
    import copy
    a,b=sorted((float(start_s),float(end_s)))
    if not np.isfinite([a,b]).all() or a==b:raise ValueError('Choose two distinct finite cursor positions for interval reporting')
    result={**run,'mapping':copy.deepcopy(run['mapping']),'report_scope':'cursor_interval','scope_start_s':a,'scope_end_s':b}
    result['traces']={key:trace.scoped(a,b) for key,trace in run['traces'].items()}
    result['quality_traces']={key:trace.scoped(a,b) for key,trace in run.get('quality_traces',run['traces']).items()}
    phases=[]
    for phase in run['phases']:
        start=max(a,phase['start_s']);end=min(b,phase['end_s'])
        if end>start:
            metrics=[evaluate_kpi({k:v for k,v in definition.items() if k!='phase'},result['traces'],run['profile'],[],start,end,run.get('run_bounds')) for definition in run['profile']['kpis']]
            phases.append({**phase,'start_s':start,'end_s':end,'duration_s':end-start,'metrics':metrics})
    result['phases']=phases
    result['kpis']=[evaluate_kpi(kpi,result['traces'],run['profile'],phases,a,b,run.get('run_bounds')) for kpi in run['profile']['kpis']]
    events=[]
    for event in run['anomalies']:
        if event['start_s'] is None:events.append(dict(event));continue
        if event['end_s']<a or event['start_s']>b:continue
        events.append({**event,'original_start_s':event['start_s'],'original_end_s':event['end_s'],
                       'start_s':max(a,event['start_s']),'end_s':min(b,event['end_s']),
                       'duration_s':max(0.,min(b,event['end_s'])-max(a,event['start_s']))})
    result['anomalies']=events
    return enrich_readiness(result,a,b)

"""General run roles, explicit t-zero anchors and uncertainty-aware envelopes."""
import numpy as np
from app_engineering_units import convert,convert_difference,seconds
from app_engineering_trace import Trace
from app_engineering_analytics import intervals


def deviation_color(percent):
    if percent is None or not np.isfinite(percent):return None
    value=abs(percent)
    return '#2e9f6b' if value<=5 else '#d99b24' if value<=10 else '#d45454'


def delta_kpis(reference,candidate):
    left={r['id']:r for r in reference['kpis']};right={r['id']:r for r in candidate['kpis']};rows=[]
    for key in dict.fromkeys([*left,*right]):
        a,b=left.get(key),right.get(key);row={'id':key,'name':(a or b)['name'],'unit':(a or b)['unit'],'reference':a['value'] if a else None,'candidate':b['value'] if b else None,'delta':None,'percent':None,'accent':None,'acceptance':'Not Evaluated'}
        if a and b and a['value'] is not None and b['value'] is not None:
            av=a['value'];bv=float((convert_difference if a.get('definition',{}).get('op') in ('std','difference') else convert)(b['value'],b['unit'],a['unit']));row['candidate']=bv;row['delta']=bv-av
            if av!=0:
                percent=(bv-av)/abs(av)*100
                row['percent']=percent if np.isfinite(percent) else None
            row['accent']=deviation_color(row['percent'])
        rows.append(row)
    return rows


def anchor_seconds(store,config,mapping=None,profile=None):
    """Return the selected source event, without altering native channel clocks."""
    mode=config.get('mode','recorded')
    if mode=='program':
        from app_program_alignment import program_start
        record=program_start(store,config.get('dataset_id'))
        channels=[c for c in store.channels.values() if c.dataset_id==config.get('dataset_id') and c.coordinate_kind=='time']
        shifts=[float(convert(c.shift,c.coordinate_unit,'s')) for c in channels]
        if not shifts or not np.allclose(shifts,shifts[0],rtol=0,atol=1e-9):
            raise ValueError('Reapply Align Program Starts so every channel in the run has one time offset.')
        return record['source_min']*60+shifts[0]
    if mode=='recorded':return 0.
    if mode in ('cursor','event','manual'):
        value=float(config['time_s'])
        if not np.isfinite(value):raise ValueError('Anchor must be finite')
        return value
    if mode=='phase':
        from app_engineering_analytics import analyze_run
        result=analyze_run(store,profile,mapping,config.get('dataset_id'))
        phase=next((p for p in result['phases'] if p['name']==config.get('phase')),None)
        if phase is None:raise ValueError('Selected phase was not observed')
        return phase['start_s']
    if mode=='actuator':
        channel=store.channels.get(config.get('channel_id'))
        if channel is None:raise ValueError('Select the actuator channel')
        if not channel.attributes.get('actuator_binary') and channel.unit!='state':raise ValueError('Activation anchor requires a confirmed actuator channel')
        t=seconds(channel);y=channel.values()[1];mask=np.isfinite(y)&(y==np.floor(y))&(y!=0)
        indices=np.flatnonzero(mask)
        if not len(indices):raise ValueError('No actuator activation was recorded')
        return float(t[indices[0]])
    raise ValueError('Unknown timeline alignment method')


def envelope(reference,candidate,rule):
    """Find exact linear crossings on valid intervals; held states stay held.

    Source samples and existing causal synchronization are never resampled in
    place. Duration counts only supported comparison time, not missing gaps.
    """
    if reference.unit!=candidate.unit:raise ValueError('Comparison traces must be normalized to the same unit first')
    zeros=[]
    if reference.kind=='analog':
        for i in np.flatnonzero(reference.y[:-1]*reference.y[1:]<0):
            if reference.t[i+1]-reference.t[i]<=reference.max_gap:zeros.append(reference.t[i]-reference.y[i]*(reference.t[i+1]-reference.t[i])/(reference.y[i+1]-reference.y[i]))
    grid=np.unique(np.r_[reference.t,candidate.t,rule.get('times_s',[]),zeros])
    if not len(grid):return {'breaches':[],'coverage_s':0.,'count':0,'duration_s':0.,'max_deviation':None,'max_percent':None,'grid':grid,'reference':grid,'candidate':grid,'lower':grid,'upper':grid}
    a=reference.sample(grid);b=candidate.sample(grid);absolute=float(rule.get('absolute',0));uncertainty=float(rule.get('uncertainty',0))
    if absolute<0 or uncertainty<0 or rule.get('relative_percent',0)<0:raise ValueError('Tolerance widths must be nonnegative')
    if rule.get('unit'):absolute=float(convert(absolute,rule['unit'],reference.unit)-convert(0,rule['unit'],reference.unit));uncertainty=float(convert(uncertainty,rule['unit'],reference.unit)-convert(0,rule['unit'],reference.unit))
    width=absolute+np.abs(a)*float(rule.get('relative_percent',0))/100+uncertainty;lower=a-width;upper=a+width
    if 'times_s' in rule:
        t=np.asarray(rule['times_s'],float);lo=np.asarray(rule['lower'],float);hi=np.asarray(rule['upper'],float)
        if len(t)<2 or len(t)!=len(lo) or len(t)!=len(hi) or not np.isfinite(t).all() or not np.isfinite(lo).all() or not np.isfinite(hi).all() or np.any(np.diff(t)<=0) or np.any(lo>hi):raise ValueError('Time-dependent limits need increasing times and finite ordered bounds')
        if rule.get('unit'):
            lo=convert(lo,rule['unit'],reference.unit);hi=convert(hi,rule['unit'],reference.unit)
        lower=np.interp(grid,t,lo,left=np.nan,right=np.nan)-uncertainty;upper=np.interp(grid,t,hi,left=np.nan,right=np.nan)+uncertainty
    delta_t=np.diff(grid);midpoint=(grid[:-1]+grid[1:])/2
    supported=np.isfinite(reference.sample(midpoint))&np.isfinite(candidate.sample(midpoint))
    supported&=np.isfinite(a[:-1])&np.isfinite(a[1:])&np.isfinite(b[:-1])&np.isfinite(b[1:])
    supported&=np.isfinite(lower[:-1])&np.isfinite(lower[1:])&np.isfinite(upper[:-1])&np.isfinite(upper[1:])&(delta_t>0)
    av0=a[:-1];av1=a[1:] if reference.kind=='analog' else av0
    bv0=b[:-1];bv1=b[1:] if candidate.kind=='analog' else bv0
    lv0=lower[:-1];lv1=lower[1:] if reference.kind=='analog' or 'times_s' in rule else lv0
    uv0=upper[:-1];uv1=upper[1:] if reference.kind=='analog' or 'times_s' in rule else uv0
    starts=[];ends=[]
    for r0,r1 in ((bv0-uv0,bv1-uv1),(lv0-bv0,lv1-bv1)):
        positive=supported&((r0>0)|(r1>0))
        crossing=np.divide(-r0,r1-r0,out=np.zeros_like(r0),where=(r1!=r0))
        begin=np.where(r0>0,0,np.clip(crossing,0,1));end=np.where(r1>0,1,np.clip(crossing,0,1))
        positive&=end>begin
        starts.append((grid[:-1]+begin*delta_t)[positive]);ends.append((grid[:-1]+end*delta_t)[positive])
    starts=np.concatenate(starts);ends=np.concatenate(ends);breached=[]
    if len(starts):
        order=np.argsort(starts,kind='stable');starts=starts[order];ends=ends[order];cumulative=np.maximum.accumulate(ends)
        breaks=np.r_[True,starts[1:]>cumulative[:-1]+1e-9];first=np.flatnonzero(breaks);last=np.r_[first[1:]-1,len(ends)-1]
        breached=[{'start_s':float(starts[i]),'end_s':float(cumulative[j]),'duration_s':float(cumulative[j]-starts[i])} for i,j in zip(first,last)]
    covered=float(delta_t[supported].sum());maximum=None;maxpercent=None
    if supported.any():
        difference=np.r_[np.abs(bv0-av0)[supported],np.abs(bv1-av1)[supported]]
        baseline=np.r_[av0[supported],av1[supported]];maximum=float(difference.max())
        nonzero=baseline!=0
        if nonzero.any() and not np.any((~nonzero)&(difference>0)):maxpercent=float((difference[nonzero]/np.abs(baseline[nonzero])*100).max())

    return {'breaches':breached,'coverage_s':covered,'count':len(breached),'duration_s':sum(r['duration_s'] for r in breached),'max_deviation':maximum,'max_percent':maxpercent,'first_s':breached[0]['start_s'] if breached else None,'last_s':breached[-1]['end_s'] if breached else None,'unit':reference.unit,'grid':grid,'reference':a,'candidate':b,'lower':lower,'upper':upper}


def compare_runs(reference,candidate,profile,golden=None,cancel=None):
    result={'kpis':delta_kpis(reference,candidate),'envelopes':{},'golden_kpis':delta_kpis(golden,candidate) if golden else [],'warnings':[]}
    for key,rule in profile.get('tolerances',{}).items():
        if cancel and cancel.is_set():raise InterruptedError('Comparison cancelled')
        a=reference['traces'].get(key);b=candidate['traces'].get(key)
        if a is None or b is None:result['warnings'].append(key+': tolerance not evaluated; required channel missing');continue
        result['envelopes'][key]=envelope(a,b,rule)
    return result


def recording_origin(store,dataset_id,timezone=None):
    """Read a recorded origin only; absent origins remain explicitly unknown."""
    import pandas as pd
    for c in store.channels.values():
        if c.dataset_id==dataset_id and c.attributes.get('time_origin'):
            value=pd.Timestamp(c.attributes['time_origin'])
            if pd.notna(value):
                if value.tz is None:
                    if not timezone:return None
                    value=value.tz_localize(timezone,ambiguous='raise',nonexistent='raise')
                return float(value.timestamp())
    return None

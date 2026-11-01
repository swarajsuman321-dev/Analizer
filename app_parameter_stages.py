"""Evidence-based stage instances and bounded order-preserving correspondence.

Resolvers never infer appliance semantics from stage numbers or zero speed.
Documented codes outrank confirmed boundaries, declared rules and labelled
heuristics. Activities may overlap; exclusive stages are clipped by precedence.
"""
from collections import defaultdict
import copy
import math
from types import SimpleNamespace

import numpy as np

from app_parameter_events import state_timeline

VERSION = '1.0'


def _rows(projections):
    return dict(projections) if isinstance(projections, dict) else {
        str(p.get('field_id', i)): p for i,p in enumerate(projections)}


def _reason(status, reason, **details):
    return dict(status=status, reason=reason, **details)


def _number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)) or not math.isfinite(float(value)):
        raise ValueError(name + ' must be finite')
    return float(value)


def _check(parameters, index=0):
    callback = (parameters or {}).get('cancelled', (parameters or {}).get('cancel'))
    if index % 512 == 0 and callable(callback) and callback():
        raise InterruptedError('Stage or sequence analysis cancelled')


def _key(value):
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, (int,float)) and not isinstance(value, bool) and math.isfinite(value) and value == int(value):
        return str(int(value))
    return str(value)


def _merge(intervals):
    result=[]
    for a,b in sorted(intervals):
        if b <= a:
            continue
        if result and a <= result[-1][1]:
            result[-1][1] = max(result[-1][1], b)
        else:
            result.append([float(a),float(b)])
    return result


def _intersection(left,right):
    i=j=0; result=[]
    while i<len(left) and j<len(right):
        a=max(left[i][0],right[j][0]); b=min(left[i][1],right[j][1])
        if b>a: result.append([a,b])
        if left[i][1]<right[j][1]: i+=1
        else: j+=1
    return result


def _subtract(interval, occupied):
    a,b=interval; result=[]
    for c,d in occupied:
        if d<=a: continue
        if c>=b: break
        if c>a: result.append([a,min(c,b)])
        a=max(a,d)
        if a>=b: break
    if b>a: result.append([a,b])
    return result


def _timeline(projection, structure='enum', values=None):
    mapping = projection.get('mapping') or (projection.get('provenance') or {}).get('mapping') or {}
    return state_timeline(projection.get('x_s'), projection.get('values',[]) if values is None else values,
        valid=projection.get('valid'), structure=structure,
        acquisition_policy=projection.get('acquisition_policy','sample_only'),
        dictionary=projection.get('state_dictionary', mapping.get('state_dictionary')),
        identity={'field_id':projection.get('field_id',''),'run_id':projection.get('run_id',''),
                  'source_indices':projection.get('source_indices',np.arange(len(projection.get('values',[]))))})


class StageResolverRegistry:
    """Trusted local resolvers return candidate stages plus readiness records."""
    def __init__(self):
        self._resolvers={}

    def register(self, resolver_id, version, resolver, *, trusted=False):
        if not trusted or not isinstance(resolver_id,str) or not resolver_id or not isinstance(version,str) or not version or not callable(resolver):
            raise ValueError('A trusted named, versioned callable stage resolver is required')
        if resolver_id in self._resolvers:
            raise ValueError('Stage resolver already registered: '+resolver_id)
        self._resolvers[resolver_id]=(version,resolver)

    def resolve(self, resolver_id, projections, definition, run_id):
        if resolver_id not in self._resolvers:
            return [],[_reason('unsupported','No trusted stage resolver is registered.',resolver_id=resolver_id)]
        version,resolver=self._resolvers[resolver_id]
        stages,readiness=resolver(projections,definition,run_id)
        for stage in stages:
            stage.setdefault('resolver',resolver_id);stage.setdefault('resolver_version',version)
        return stages,readiness

    def definitions(self):
        return [{'resolver_id':key,'version':value[0]} for key,value in self._resolvers.items()]

    def snapshot(self):
        return dict(self._resolvers)

    def restore(self,snapshot):
        fresh=StageResolverRegistry()
        for key,(version,resolver) in snapshot.items():
            fresh.register(key,version,resolver,trusted=True)
        self._resolvers=fresh._resolvers

    def clone(self):
        other=StageResolverRegistry();other.restore(self.snapshot());return other


def _codes(rows, definition, run_id):
    field_id=definition.get('field_id'); readiness=[]; stages=[]
    dictionary=definition.get('dictionary') or definition.get('state_dictionary')
    if not definition.get('documented') or not definition.get('source') or not definition.get('version'):
        return [],[_reason('needs_review','Controller stage meanings require a documented dictionary, source and version.',field_id=field_id)]
    if field_id not in rows:
        return [],[_reason('missing_input','The documented stage-code field is absent.',field_id=field_id)]
    if not isinstance(dictionary,dict) or not dictionary:
        return [],[_reason('needs_mapping','Supply a nonempty documented stage-code dictionary.',field_id=field_id)]
    line=_timeline(rows[field_id]); readiness.extend(line['readiness'])
    unknown=set()
    for interval in line['intervals']:
        code=_key(interval['state'])
        entry=dictionary.get(code,dictionary.get(interval['state']))
        if entry is None:
            unknown.add(code); continue
        item=entry if isinstance(entry,dict) else {'label':str(entry),'type':str(entry)}
        if not item.get('label'):
            unknown.add(code);continue
        stages.append(dict(start_s=interval['start_s'],end_s=interval['end_s'],
            type=str(item.get('type',item['label'])),label=str(item['label']),
            exclusive=item.get('exclusive',definition.get('exclusive',True)),
            parent_id=item.get('parent_id',definition.get('parent_id','')),
            left_censored=interval['left_censored'],right_censored=interval['right_censored'],
            onset_bracket_s=interval['onset_bracket_s'],offset_bracket_s=interval['offset_bracket_s'],
            source_field_ids=[field_id],source_indices=interval['source_indices'],
            evidence_basis='documented controller code',dictionary_code=code,
            source=definition['source'],definition_version=str(definition['version'])))
    if unknown:
        readiness.append(_reason('needs_mapping','Unmapped stage codes retain unknown meaning; no process names were inferred.',field_id=field_id,codes=sorted(unknown)))
    return stages,readiness


def _manual(rows, definition, run_id):
    if definition.get('confirmed') is not True:
        return [],[_reason('needs_review','User/recipe stage boundaries must be explicitly confirmed.')]
    a=_number(definition.get('start_s'),'start_s'); b=_number(definition.get('end_s'),'end_s')
    if b<=a: raise ValueError('Stage end must follow start')
    return [dict(start_s=a,end_s=b,type=str(definition.get('type','user_stage')),
        label=str(definition.get('label','User stage')),exclusive=definition.get('exclusive',True),
        parent_id=str(definition.get('parent_id','')),left_censored=False,right_censored=False,
        onset_bracket_s=definition.get('onset_bracket_s',[a,a]),offset_bracket_s=definition.get('offset_bracket_s',[b,b]),
        source_field_ids=list(definition.get('source_field_ids',[])),source_indices=[],
        evidence_basis='confirmed user/recipe boundary',source=str(definition.get('source','user review')),
        definition_version=str(definition.get('version','1')))],[]


def _rule(rows, definition, run_id):
    conditions=definition.get('conditions'); readiness=[]; intervals=[]; sources=[]
    if definition.get('reviewed') is not True:
        return [],[_reason('needs_review','Multi-signal stage rules require explicit review.')]
    if not isinstance(conditions,list) or not 1<=len(conditions)<=64:
        return [],[_reason('invalid','Stage rules require between 1 and 64 declared conditions; an empty rule does not detect a stage.')]
    combine=definition.get('combine','all')
    if combine not in {'all','any'}: raise ValueError('Stage condition combine must be all or any')
    for condition in conditions:
        field_id=condition.get('field_id'); operation=condition.get('op','eq')
        if field_id not in rows:
            return [],[_reason('missing_input','A stage-rule field is absent.',field_id=field_id)]
        projection=rows[field_id];values=np.asarray(projection.get('values',[]))
        if values.ndim!=1:
            return [],[_reason('unsupported','Stage predicates require scalar observations.',field_id=field_id)]
        current_unit=projection.get('unit','')
        if condition.get('unit'):
            from app_engineering_units import convert
            values=convert(values,current_unit,condition['unit']);current_unit=condition['unit']
        value=condition.get('value')
        if operation=='eq': match=values==value
        elif operation=='ne': match=values!=value
        elif operation in {'lt','le','gt','ge'}:
            value=_number(value,'condition value')
            match={'lt':np.less,'le':np.less_equal,'gt':np.greater,'ge':np.greater_equal}[operation](values.astype(float),value)
        elif operation=='in':
            if not isinstance(value,list) or len(value)>256: raise ValueError('Stage membership requires at most 256 explicit values')
            match=np.isin(values,value)
        elif operation=='between':
            if not isinstance(value,list) or len(value)!=2: raise ValueError('Stage range requires [minimum,maximum]')
            low=_number(value[0],'minimum');high=_number(value[1],'maximum')
            if high<low: raise ValueError('Stage range maximum precedes minimum')
            match=(values.astype(float)>=low)&(values.astype(float)<=high)
        else: raise ValueError('Unsupported bounded stage predicate: '+str(operation))
        policy=projection.get('acquisition_policy') or {}
        mode=policy.get('mode') if isinstance(policy,dict) else policy
        if mode=='continuous' and projection.get('x_s') is not None:
            # Reuse the established trace interpolation and phase-condition
            # machinery so a linear threshold crossing keeps its true native
            # time instead of becoming a sampled held-state boundary.
            from app_engineering_trace import Trace
            from app_engineering_analytics import condition_grid,conditions_mask,intervals as trace_intervals
            native=np.asarray(projection['x_s'],float)
            numeric=values.astype(float)
            valid=np.asarray(projection.get('valid',np.ones(len(values),bool)),bool)
            if native.shape!=numeric.shape or valid.shape!=numeric.shape or not np.isfinite(native).all() or np.any(np.diff(native)<=0):
                return [],[_reason('invalid','Analog stage predicates need ordered, valid native clock coordinates.',field_id=field_id)]
            numeric=np.where(valid,numeric,np.nan)
            channel=SimpleNamespace(kind='analog',unit=current_unit,coordinate_kind='time',coordinate_unit='s',values=lambda:(native,numeric))
            trace=Trace(channel,max_gap_seconds=policy.get('max_gap_seconds',policy.get('max_gap_s')),acquisition_policy=policy)
            if operation=='between':
                rules=[dict(channel='input',op='ge',value=value[0]),dict(channel='input',op='le',value=value[1])]
            elif operation=='in':
                # Membership still means equality/plateau, never an enum-code
                # interpolation. Add all target crossing roots to the grid.
                rules=[dict(channel='input',op='in',values=value)]
            else:
                rules=[dict(channel='input',op=operation,value=value)]
            grid=condition_grid(rules,{'input':trace})
            if operation=='in':
                extra=[condition_grid([dict(channel='input',op='eq',value=v)],{'input':trace}) for v in value]
                grid=np.unique(np.concatenate([grid]+extra)) if extra else grid
            mask,_=conditions_mask(rules,{'input':trace},grid)
            intervals.append(_merge(trace_intervals(grid,mask)))
            readiness.append(_reason('computed','Analog stage boundaries reuse declared Trace interpolation; '+trace.gap_policy+'.',field_id=field_id))
        else:
            line=_timeline(projection,structure='binary',values=match.astype(int))
            readiness.extend(line['readiness'])
            intervals.append(_merge([[it['start_s'],it['end_s']] for it in line['intervals'] if it['active']]))
        sources.append(field_id)
    active=intervals[0]
    for item in intervals[1:]:
        active=_intersection(active,item) if combine=='all' else _merge(active+item)
    stages=[dict(start_s=a,end_s=b,type=str(definition.get('type','rule_stage')),
        label=str(definition.get('label','Declared rule stage')),exclusive=definition.get('exclusive',True),
        parent_id=str(definition.get('parent_id','')),left_censored=True,right_censored=True,
        onset_bracket_s=None,offset_bracket_s=None,source_field_ids=sources,source_indices=[],
        evidence_basis='declared multi-signal rule',source=str(definition.get('source','reviewed rule')),
        definition_version=str(definition.get('version','1')),rule=copy.deepcopy(definition)) for a,b in active]
    return stages,readiness


def _heuristic(rows, definition, run_id):
    if definition.get('explicit') is not True:
        return [],[_reason('needs_review','Heuristic segmentation must be explicitly requested and remains a candidate.')]
    raw=dict(definition,reviewed=True,label='Candidate segment',type='candidate_segment')
    stages,readiness=_rule(rows,raw,run_id)
    for index,stage in enumerate(stages):
        stage.update(label='Candidate segment '+str(index+1),evidence_basis='explicitly labelled heuristic',heuristic=True)
    return stages,readiness


_DEFAULT=None


def stage_registry():
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT=StageResolverRegistry()
        for name,func in [('documented_codes',_codes),('manual',_manual),('rule',_rule),('heuristic',_heuristic)]:
            _DEFAULT.register(name,VERSION,func,trusted=True)
    return _DEFAULT


def resolve_stages(projections, definitions, *, run_id='', registry=None, cancelled=None):
    """Return stable stage instances, clipping exclusive lower-priority stages.

    ``definitions`` is a list or {stages:[...]}; custom resolver registrations
    must be trusted. A parent's exclusive intervals do not hide nested substeps;
    exclusivity applies within the same parent. Overlapping activities never
    participate in exclusive occupancy subtraction.
    """
    rows=_rows(projections);result=dict(stages=[],readiness=[])
    definitions=(definitions or {}).get('stages',[]) if isinstance(definitions,dict) else definitions or []
    priority={'documented_codes':0,'manual':1,'rule':2,'heuristic':3}
    ordered=sorted(enumerate(definitions),key=lambda pair:(priority.get(pair[1].get('resolver',pair[1].get('kind','manual')),2),pair[0]))
    occupied=defaultdict(list)
    for number,definition in ordered:
        _check({'cancelled':cancelled},number)
        resolver=definition.get('resolver',definition.get('kind','manual'))
        try:
            candidates,readiness=(registry or stage_registry()).resolve(resolver,rows,definition,run_id)
            result['readiness'].extend(dict(r,definition_id=definition.get('id',str(number))) for r in readiness)
            for index,stage in enumerate(candidates):
                a=_number(stage['start_s'],'stage start');b=_number(stage['end_s'],'stage end')
                if b<=a: continue
                parent=str(stage.get('parent_id',''));exclusive=bool(stage.get('exclusive',True))
                pieces=_subtract([a,b],occupied[parent]) if exclusive else [[a,b]]
                if len(pieces)!=1 or (pieces and pieces[0]!=[a,b]):
                    result['readiness'].append(_reason('partial','Lower-priority exclusive stage clipped to preserve documented/confirmed precedence.',definition_id=definition.get('id',str(number))))
                source_id=str(definition.get('id',f'{resolver}:{number}'))
                for fragment,(left,right) in enumerate(pieces):
                    item=copy.deepcopy(stage)
                    item.update(id=f'{run_id}:stage:{source_id}:{index}:{fragment}',run_id=run_id,
                        start_s=left,end_s=right,duration_s=right-left,definition_id=source_id,
                        fragment_index=fragment,original_interval_s=[a,b],exclusive=exclusive)
                    if left>a: item.update(left_censored=True,onset_bracket_s=None)
                    if right<b: item.update(right_censored=True,offset_bracket_s=None)
                    result['stages'].append(item)
                if exclusive: occupied[parent]=_merge(occupied[parent]+pieces)
        except InterruptedError:
            raise
        except (ValueError,TypeError,KeyError,OverflowError) as exc:
            result['readiness'].append(_reason('invalid','Stage definition rejected: '+str(exc),definition_id=definition.get('id',str(number))))
    result['stages'].sort(key=lambda s:(s['start_s'],s['end_s'],s['id']))
    if not result['stages']:
        result['readiness'].append(_reason('needs_mapping','No supported stage definition; report whole-run results or add documented codes/confirmed boundaries.'))
    return result


def assign_events_to_stages(events, stages):
    """Copy events, count an observed onset once and clip occupancy per stage."""
    result=[]
    for event in events:
        item=copy.deepcopy(event);assignments=[]
        onset=event.get('onset_s',event.get('start_s'));offset=event.get('offset_s',event.get('end_s',onset))
        if onset is not None and offset is not None:
            for stage in stages:
                if event.get('run_id') and stage.get('run_id') and event['run_id']!=stage['run_id']:continue
                a,b=stage['start_s'],stage['end_s'];left=max(a,onset);right=min(b,offset)
                counted=bool(event.get('observed_onset',not event.get('left_censored',False)) and a<=onset<b)
                if right>left or counted:
                    assignments.append(dict(stage_id=stage['id'],stage_label=stage.get('label',''),
                        clipped_start_s=left if right>=left else None,
                        clipped_end_s=right if right>=left else None,
                        clipped_duration_s=max(0.,right-left),onset_count=int(counted),
                        source_event_id=event.get('id',''),count_policy='observed onset in half-open stage'))
        item['stage_assignments']=assignments;result.append(item)
    return result


def _span(item):
    a=item.get('onset_s',item.get('start_s'));b=item.get('offset_s',item.get('end_s',a))
    return a,b


def _compatible(a,b,parameters):
    keys=parameters.get('context_keys',['type','role','instance','location','function','signal_kind','state'])
    for key in keys:
        if a.get(key) not in (None,'') and b.get(key) not in (None,'') and a[key]!=b[key]:return False
    return True


def _cost(a,b,p):
    if not _compatible(a,b,p):return math.inf
    aa,ab=_span(a);ba,bb=_span(b)
    if aa is None or ba is None:return math.inf
    delay=abs(float(ba)-float(aa)-p.get('alignment_offset_s',0.))
    if p.get('max_shift_s') is not None and delay>p['max_shift_s']:return math.inf
    duration=0.
    if ab is not None and bb is not None and not any(q.get('left_censored') or q.get('right_censored') for q in (a,b)):
        duration=abs((bb-ba)-(ab-aa))
    return p['timing_weight']*delay/p['timing_scale_s']+p['duration_weight']*duration/p['duration_scale_s']


def match_sequences(reference, candidate, parameters=None):
    """Banded edit-distance correspondence with explicit ambiguity and budgets.

    The algorithm is order preserving and gates type/context before costs.
    Bounded DP never allocates an uncontrolled dense Cartesian matrix. If a
    declared budget/band cannot cover an acquisition, unmatched evidence stays
    available with a remedy instead of guessing ordinal correspondence.
    """
    p=dict(parameters or {})
    _check(p)
    p.setdefault('insertion_penalty',1.);p.setdefault('deletion_penalty',1.)
    p.setdefault('timing_weight',.2);p.setdefault('duration_weight',1.)
    p.setdefault('timing_scale_s',1.);p.setdefault('duration_scale_s',1.)
    p.setdefault('ambiguity_tolerance',1e-9);p.setdefault('band',32);p.setdefault('max_cells',1_000_000)
    for key in ('insertion_penalty','deletion_penalty','timing_scale_s','duration_scale_s'):
        p[key]=_number(p[key],key)
        if p[key]<=0:raise ValueError(key+' must be positive')
    for key in ('timing_weight','duration_weight','ambiguity_tolerance'):
        p[key]=_number(p[key],key)
        if p[key]<0:raise ValueError(key+' must be nonnegative')
    for key in ('band','max_cells'):
        if isinstance(p[key],bool) or not isinstance(p[key],int) or p[key]<1:raise ValueError(key+' must be a positive integer')
    if p['max_cells']>4_000_000:raise ValueError('Sequence matching max_cells must not exceed 4000000')
    if p.get('max_shift_s') is not None:
        p['max_shift_s']=_number(p['max_shift_s'],'max_shift_s')
        if p['max_shift_s']<0:raise ValueError('max_shift_s must be nonnegative')
    if 'alignment_offset_s' in p:
        p['alignment_offset_s']=_number(p['alignment_offset_s'],'alignment_offset_s')
    if 'context_keys' in p and (not isinstance(p['context_keys'],list) or not 1<=len(p['context_keys'])<=32 or any(not isinstance(k,str) or not k for k in p['context_keys'])):
        raise ValueError('context_keys requires between 1 and 32 named context fields')
    reference=list(reference);candidate=list(candidate);n=len(reference);m=len(candidate)
    result=dict(matches=[],missing=[],added=[],ambiguous=[],split_merge=[],
        parameters={k:v for k,v in p.items() if k not in {'cancel','cancelled'}},readiness=[])
    if not n or not m:
        result['missing']=copy.deepcopy(reference);result['added']=copy.deepcopy(candidate)
        result['readiness'].append(_reason('partial','One sequence is empty; events remain unmatched, not zero-duration matches.'))
        return result
    band=max(p['band'],abs(n-m))
    estimate=sum(min(m,i+band)-max(0,i-band)+1 for i in range(n+1))
    if estimate>p['max_cells']:
        result['missing']=copy.deepcopy(reference);result['added']=copy.deepcopy(candidate)
        result['readiness'].append(_reason('needs_review','Sequence matching exceeds the declared cell budget; narrow the scope or review a tighter compatible sequence.',estimated_cells=estimate,max_cells=p['max_cells']))
        return result
    previous={j:j*p['insertion_penalty'] for j in range(min(m,band)+1)}
    links={(0,j):'insert' for j in range(1,min(m,band)+1)}
    for i in range(1,n+1):
        _check(p,i);current={}
        for j in range(max(0,i-band),min(m,i+band)+1):
            options=[]
            if j in previous:options.append((previous[j]+p['deletion_penalty'],'delete'))
            if j-1 in current:options.append((current[j-1]+p['insertion_penalty'],'insert'))
            if j and j-1 in previous:
                cost=_cost(reference[i-1],candidate[j-1],p)
                if math.isfinite(cost) and cost<p['insertion_penalty']+p['deletion_penalty']:
                    options.append((previous[j-1]+cost,'match'))
            if options:
                value,action=min(options,key=lambda item:(item[0],{'delete':0,'insert':1,'match':2}[item[1]]))
                current[j]=value;links[(i,j)]=action
        previous=current
    if m not in previous:
        result['missing']=copy.deepcopy(reference);result['added']=copy.deepcopy(candidate)
        result['readiness'].append(_reason('needs_review','No admissible path inside the declared sequence band; no ordinal matches were forced.'))
        return result
    i,j=n,m;matches=[];missing=[];added=[]
    while i or j:
        action=links.get((i,j))
        if action=='match':matches.append((i-1,j-1));i-=1;j-=1
        elif action=='delete':missing.append(i-1);i-=1
        elif action=='insert':added.append(j-1);j-=1
        else:raise RuntimeError('Broken bounded sequence path')
    for ri,ci in reversed(matches):
        a,b=reference[ri],candidate[ci];cost=_cost(a,b,p);aa,ab=_span(a);ba,bb=_span(b)
        alternatives=[]
        for cj in range(max(0,ci-band),min(m,ci+band+1)):
            if cj!=ci and abs(_cost(a,candidate[cj],p)-cost)<=p['ambiguity_tolerance']:
                alternatives.append(candidate[cj].get('id',str(cj)))
        row=dict(reference_id=a.get('id',str(ri)),candidate_id=b.get('id',str(ci)),
            reference_index=ri,candidate_index=ci,reference=copy.deepcopy(a),candidate=copy.deepcopy(b),
            cost=cost,status='ambiguous' if alternatives else 'matched',
            onset_delta_s=float(ba-aa),duration_delta_s=float((bb-ba)-(ab-aa)) if ab is not None and bb is not None else None,
            alternative_candidate_ids=alternatives,order_policy='order preserving',definition_version=VERSION)
        result['matches'].append(row)
        if alternatives:result['ambiguous'].append(copy.deepcopy(row))
    result['missing']=[copy.deepcopy(reference[k]) for k in reversed(missing)]
    result['added']=[copy.deepcopy(candidate[k]) for k in reversed(added)]
    # A split/merge is a review suggestion, never an automatic new event. Exact
    # span tiling is recognised without inventing a physical detector tolerance.
    tolerance=_number(p.get('split_merge_tolerance_s',1e-9),'split_merge_tolerance_s')
    if tolerance<0:raise ValueError('split_merge_tolerance_s must be nonnegative')
    for source,target,label in ((reference,candidate,'split'),(candidate,reference,'merge')):
        # Scan only neighbouring target events inside the same declared band.
        for index,item in enumerate(source):
            _check(p,index);a,b=_span(item)
            if a is None or b is None or b<=a:continue
            center=round(index*len(target)/max(1,len(source)))
            for k in range(max(0,center-band),min(len(target)-1,center+band)):
                left,right=target[k],target[k+1];la,lb=_span(left);ra,rb=_span(right)
                if any(v is None for v in (la,lb,ra,rb)):continue
                if _compatible(item,left,p) and _compatible(item,right,p) and abs(la-a)<=tolerance and abs(rb-b)<=tolerance and abs(lb-ra)<=tolerance:
                    result['split_merge'].append(dict(type=label,status='needs_review',
                        source_id=item.get('id',str(index)),target_ids=[left.get('id',str(k)),right.get('id',str(k+1))],
                        reason='Adjacent compatible intervals tile the original span; correspondence requires review.'))
    result['total_cost']=previous[m];result['evaluated_cells']=len(links)
    result['readiness'].append(_reason('partial' if missing or added or result['ambiguous'] else 'computed',
        'Ordered sequence comparison retains insertions, deletions and ambiguous correspondence; matching is descriptive, not acceptance.'))
    return result

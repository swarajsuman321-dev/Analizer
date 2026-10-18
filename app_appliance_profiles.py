"""Versioned appliance configuration and reviewable canonical-channel recognition."""
import copy
import json
import re
from pathlib import Path
from app_engineering_units import UNITS,unit

DOMAINS={'thermal','fluidic','electrical','kinematic','actuator_state','firmware_state'}
OPS={'duration','integral','mean','max','min','std','rms','first','last','slope','absmax','counter','on_duration','pulse_volume','difference','ratio'}
ROOT=Path(__file__).resolve().parent/'profiles'


def validate_profile(record):
    if not isinstance(record,dict) or record.get('schema_version')!=1:raise ValueError('Unsupported appliance profile schema; expected 1')
    allowed={'schema_version','id','category','metadata','domains','channels','phases','kpis','tolerances','acceptance','anomalies','calibrations','extensions'}
    if set(record)-allowed:raise ValueError('Unknown profile keys: '+', '.join(sorted(set(record)-allowed)))
    for key in ('id','category'):
        if not isinstance(record.get(key),str) or not record[key].strip():raise ValueError('Profile requires '+key)
    for key in ('channels','phases','kpis','anomalies'):
        if not isinstance(record.get(key,[]),list):raise ValueError(key+' must be a list')
    for key in ('metadata','tolerances','acceptance','calibrations','extensions'):
        if not isinstance(record.get(key,{}),dict):raise ValueError(key+' must be an object')
    ids=set()
    for channel in record.get('channels',[]):
        if not isinstance(channel,dict) or not re.fullmatch(r'[a-z][a-z0-9_]*',channel.get('id','')) or channel['id'] in ids:raise ValueError('Canonical identifiers must be unique lowercase names')
        ids.add(channel['id'])
        if channel.get('domain') not in DOMAINS or channel.get('data_type') not in ('analog','state','code','count'):raise ValueError('Invalid channel domain/data type')
        if unit(channel.get('unit','')) not in UNITS:raise ValueError('Unknown channel unit')
        if not isinstance(channel.get('aliases',[]),list) or any(not isinstance(a,str) for a in channel.get('aliases',[])):raise ValueError('Aliases must be strings')
        for pattern in channel.get('patterns',[]):
            # Patterns are deliberately a small anchored grammar, not arbitrary regex programs.
            if len(pattern)>120 or not pattern.startswith('^') or not pattern.endswith('$') or re.search(r'[^a-zA-Z0-9_ ^$.*?\[\]\\-]',pattern) or '**' in pattern or pattern.count('*')+pattern.count('?')>2:raise ValueError('Use short anchored literal/character-class patterns')
            try:re.compile(pattern)
            except re.error as exc:raise ValueError('Invalid profile recognition pattern') from exc
    names=set()
    for kpi in record.get('kpis',[]):
        if not isinstance(kpi,dict) or kpi.get('op') not in OPS or kpi.get('channel') not in ids:raise ValueError('Invalid KPI operation or channel')
        if not kpi.get('id') or kpi['id'] in names:raise ValueError('KPI identifiers must be unique')
        names.add(kpi['id'])
        if unit(kpi.get('unit','')) not in UNITS:raise ValueError('Unknown KPI result unit')
    for phase in record.get('phases',[]):
        if not isinstance(phase,dict) or not phase.get('name') or not isinstance(phase.get('conditions',[]),list):raise ValueError('Invalid phase definition')
        for key in ('minimum_seconds','debounce_seconds'):
            if not isinstance(phase.get(key,0),(float,int)) or phase.get(key,0)<0:raise ValueError('Phase intervals must be nonnegative')
        for condition in phase.get('conditions',[]):validate_condition(condition,ids)
    for name,rule in record.get('acceptance',{}).items():
        if name not in names or not isinstance(rule,dict) or not set(rule)<= {'min','max','unit'}:raise ValueError('Invalid acceptance rule')
        if not any(k in rule for k in ('min','max')):raise ValueError('Acceptance requires a limit')
    for key,rule in record.get('tolerances',{}).items():
        if key not in ids or not isinstance(rule,dict) or not set(rule)<={'relative_percent','absolute','unit','times_s','lower','upper','uncertainty'}:raise ValueError('Invalid tolerance definition')
        if rule.get('relative_percent',0)<0 or rule.get('absolute',0)<0 or rule.get('uncertainty',0)<0:raise ValueError('Tolerances must be nonnegative')
    validate_details(record)
    return copy.deepcopy(record)


def validate_condition(condition,ids):
    if not isinstance(condition,dict) or condition.get('channel') not in ids or condition.get('op') not in ('eq','ne','gt','ge','lt','le','in','on','off'):raise ValueError('Invalid phase/anomaly condition')
    if condition['op']=='in' and not isinstance(condition.get('values'),list):raise ValueError('Membership condition needs values')
    if condition['op'] in ('eq','ne','gt','ge','lt','le'):
        import math
        if not isinstance(condition.get('value'),(int,float)) or not math.isfinite(condition['value']):raise ValueError('Condition requires a finite value')


def load_profile(name='washing_machine'):
    path=Path(name)
    if not path.is_file():path=ROOT/(name+'.json')
    return validate_profile(json.loads(path.read_text(encoding='utf-8')))


def channel_key(channel):
    attrs=channel.attributes
    return attrs.get('tdms_template_key') or '|'.join((Path(channel.source).name,attrs.get('source_column',channel.name),channel.unit))


def token(value):return re.sub(r'[^a-z0-9]+',' ',str(value).casefold()).strip()


def recognize(store,profile,mappings=None,dataset_id=None):
    """Return reviewable results; never mutate channels or override confirmations."""
    definitions={c['id']:c for c in profile['channels']};rows=[];mapping=mappings or {}
    for channel in store.channels.values():
        if channel.attributes.get('engineering_projection'):continue
        if dataset_id is not None and channel.dataset_id!=dataset_id:continue
        attrs=channel.attributes;canonical=None;method='unmapped';candidates=[]
        # A reviewed source identity may be reused after a workspace/import identity changes.
        identity=attrs.get('tdms_template_key',attrs.get('source_column',channel.name))
        key=channel_key(channel);explicit=mapping.get(channel.id,mapping.get(key,mapping.get(identity)))
        if channel.id in mapping or key in mapping or identity in mapping:
            canonical=explicit or None;method='user confirmed'
        else:
            for field,label in [('canonical_id','confirmed template'),('source_canonical_id','source metadata')]:
                if attrs.get(field) in definitions:canonical=attrs[field];method=label;break
            if canonical is None:
                names={token(channel.name),token(identity),token(attrs.get('original_name',''))}
                for key,definition in definitions.items():
                    if names.intersection({token(key),token(definition['name']),*[token(a) for a in definition.get('aliases',[])]}):candidates.append(key)
                method='profile alias'
                if not candidates:
                    candidates=[key for key,definition in definitions.items() if any(len(token(channel.name))<=256 and re.fullmatch(p,token(channel.name)) for p in definition.get('patterns',[]))];method='profile pattern'
                if len(candidates)==1:canonical=candidates[0]
                elif len(candidates)>1:method='ambiguous; review required'
                else:method='unmapped'
        if canonical is not None and canonical not in definitions:raise ValueError('Confirmed mapping is not in this profile: '+str(canonical))
        rows.append({'channel_id':channel.id,'source_name':identity,'name':channel.name,'canonical_id':canonical,'method':method,'candidates':candidates,'source_unit':channel.unit,'domain':definitions[canonical]['domain'] if canonical else ''})
    return rows


def validate_details(record):
    """Validate nested numerical configuration before any worker or UI mutation."""
    import math
    def number(value,label,minimum=None):
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or (minimum is not None and value<minimum):raise ValueError(label+' must be finite'+(' and nonnegative' if minimum==0 else ''))
    channel_ids={c['id'] for c in record.get('channels',[])}
    for phase in record.get('phases',[]):
        for key in ('minimum_seconds','debounce_seconds'):number(phase.get(key,0),key,0)
    for kpi in record.get('kpis',[]):
        if kpi.get('op') in ('difference','ratio') and kpi.get('other_channel') not in channel_ids:raise ValueError('KPI requires a valid second channel')
    for rule in record.get('acceptance',{}).values():
        for key in ('min','max'):
            if key in rule:number(rule[key],'Acceptance '+key)
        if rule.get('min',-math.inf)>rule.get('max',math.inf):raise ValueError('Acceptance minimum exceeds maximum')
        if 'unit' in rule and unit(rule['unit']) not in UNITS:raise ValueError('Unknown acceptance unit')
    for rule in record.get('tolerances',{}).values():
        for key in ('absolute','relative_percent','uncertainty'):number(rule.get(key,0),key,0)
        if 'unit' in rule and unit(rule['unit']) not in UNITS:raise ValueError('Unknown tolerance unit')
        if any(key in rule for key in ('times_s','lower','upper')):
            if not all(isinstance(rule.get(key),list) for key in ('times_s','lower','upper')):raise ValueError('Time limits require times_s/lower/upper arrays')
            t,lo,hi=(rule[key] for key in ('times_s','lower','upper'))
            if len(t)<2 or len(t)!=len(lo) or len(t)!=len(hi):raise ValueError('Time limits require paired points')
            for value in [*t,*lo,*hi]:number(value,'Time limit')
            if any(a>=b for a,b in zip(t,t[1:])) or any(a>b for a,b in zip(lo,hi)):raise ValueError('Time limits must be ordered')
    for rule in record.get('anomalies',[]):
        if not isinstance(rule,dict) or not rule.get('name') or rule.get('channel') not in channel_ids or rule.get('type','condition') not in ('condition','fault','oob','sequence','dropout','stall'):raise ValueError('Invalid anomaly rule')
        for condition in rule.get('conditions',[]):validate_condition(condition,channel_ids)
        if rule.get('type')=='sequence':
            if not isinstance(rule.get('sequence'),list) or len(rule['sequence'])<2:raise ValueError('Sequence rules need at least two confirmed transitions')
            for step in rule['sequence']:validate_condition(step,channel_ids)
            number(rule.get('within_seconds'),'Sequence window',0)
        for key in ('minimum_seconds','debounce_seconds','window_seconds'):
            if key in rule:number(rule[key],key,0)
        if rule.get('type')=='fault' and not rule.get('fault_values'):raise ValueError('Fault rules need confirmed fault_values')
        if rule.get('type')=='stall':
            number(rule.get('maximum_change'),'Stall maximum_change',0)
            if rule.get('window_seconds',0)<=0:raise ValueError('Stall window must be positive')
    for name,cal in record.get('calibrations',{}).items():
        if not isinstance(cal,dict) or not isinstance(cal.get('verified'),bool) or not cal.get('id'):raise ValueError('Calibration needs identifier and explicit verified flag')
        if unit(cal.get('output_unit','')) not in UNITS:raise ValueError('Unknown calibration output unit')
        if 'volume_per_pulse' in cal:number(cal['volume_per_pulse'],'Volume per pulse',0)
        else:
            if unit(cal.get('input_unit','')) not in UNITS or len(cal.get('x',[]))<2 or len(cal.get('x',[]))!=len(cal.get('y',[])):raise ValueError('Calibration needs input unit and paired points')
            for v in cal['x']+cal['y']:number(v,'Calibration point')
            if any(a>=b for a,b in zip(cal['x'],cal['x'][1:])):raise ValueError('Calibration X must increase')
    for kpi in record.get('kpis',[]):
        if 'scale' in kpi:number(kpi['scale'],'KPI scale')
    gap=record.get('extensions',{}).get('max_gap_seconds')
    if gap is not None:number(gap,'Gap limit',0)

"""Serializable engineering-session configuration and cancellable analysis orchestration."""
import copy
from app_appliance_profiles import load_profile,validate_profile
from app_engineering_analytics import analyze_run,scoped_run
from app_engineering_compare import anchor_seconds,compare_runs,recording_origin


def default_session():
    warning=''
    try:profile=load_profile()
    except (OSError,ValueError,TypeError) as exc:
        warning='Default profile could not load: '+str(exc)
        try:profile=load_profile('generic_appliance')
        except (OSError,ValueError,TypeError):profile={'schema_version':1,'id':'generic_appliance','category':'Generic appliance — configure a valid profile','channels':[],'phases':[],'kpis':[],'anomalies':[],'metadata':{},'calibrations':{},'acceptance':{},'tolerances':{},'extensions':{}}
    return {'version':1,'profile':profile,'profile_warning':warning,'mappings':{},'source_units':{},'runs':{'analysis':None,'reference':None,'candidate':None,'golden':None},'anchors':{},'metadata':{'Report title':'Engineering report'},'show_tolerances':True,'show_phases':True}


def validate_session(record,store=None):
    if not isinstance(record,dict) or record.get('version')!=1:raise ValueError('Unsupported engineering session version')
    result=copy.deepcopy(record);result['profile']=validate_profile(result['profile'])
    for key in ('mappings','runs','anchors','metadata'):
        if not isinstance(result.get(key),dict):raise ValueError('Invalid session '+key)
    allowed={c['id'] for c in result['profile']['channels']}
    if any(value is not None and value not in allowed for value in result['mappings'].values()):raise ValueError('A mapped canonical channel is absent from this profile')
    if store:
        for key,value in result['runs'].items():
            if value is not None and value not in store.datasets:raise ValueError('Run no longer exists: '+key)
    from app_engineering_units import UNITS,unit
    if not isinstance(result.get('source_units',{}),dict) or any(unit(value) not in UNITS for value in result.get('source_units',{}).values()):raise ValueError('Invalid confirmed source units')
    return result


def analyze_session(store,session,comparison=False,cancel=None,report_scope="whole_recording",cursor_interval_s=None):
    session=validate_session(session,store)
    if report_scope not in ('whole_recording','cursor_interval','both'):raise ValueError('Unknown engineering report scope')
    if report_scope!='whole_recording' and (not cursor_interval_s or len(cursor_interval_s)!=2):raise ValueError('Cursor interval reporting requires two cursor positions')
    if not session['profile']['channels']:raise ValueError('Configure or import a valid appliance profile in Engineering Setup before analysis')
    roles=['reference','candidate'] if comparison else ['analysis']
    if comparison and session['runs'].get('golden') is not None:roles.append('golden')
    runs=[]
    origins={role:recording_origin(store,session['runs'].get(role),session['profile'].get('metadata',{}).get('recorded_timezone')) for role in roles}
    base=origins.get('reference') if comparison else None
    for role in roles:
        if cancel and cancel.is_set():raise InterruptedError('Engineering analysis cancelled')
        dataset=session['runs'].get(role)
        if dataset is None:
            candidates={c.dataset_id for c in store.channels.values() if not c.attributes.get('engineering_projection')}
            if len(candidates)==1:dataset=next(iter(candidates))
            else:raise ValueError('Select '+role+' dataset in Engineering Setup; files are never combined implicitly')
        anchor={**session['anchors'].get(role,{'mode':'program' if comparison else 'recorded'}),'dataset_id':dataset}
        offset=-anchor_seconds(store,anchor,session['mappings'],session['profile'])
        if comparison and anchor.get('mode')=='recorded' and base is not None and origins.get(role) is not None:offset=origins[role]-base
        result=analyze_run(store,session['profile'],session['mappings'],dataset,offset,cancel,session.get('source_units'))
        if comparison and anchor.get('mode')=='recorded' and (base is None or origins.get(role) is None):result['warnings'].append('Absolute recorded clock unavailable; existing numeric coordinates preserved without an additional shift')
        result['role']=role;runs.append(result)
        if anchor.get('mode')=='program':
            from app_program_alignment import program_start
            result['program_start']=program_start(store,dataset)
    comp=compare_runs(runs[0],runs[1],session['profile'],runs[2] if len(runs)>2 else None,cancel) if comparison else None
    interval_comp=None
    if report_scope!='whole_recording':
        scoped=[scoped_run(run,*cursor_interval_s) for run in runs]
        interval_comp=compare_runs(scoped[0],scoped[1],session['profile'],scoped[2] if len(scoped)>2 else None,cancel) if comparison else None
        runs=runs+scoped if report_scope=='both' else scoped
        if report_scope=='cursor_interval':comp=interval_comp
    return {'runs':runs,'comparison':comp,'interval_comparison':interval_comp,'session':session,'report_scope':report_scope}

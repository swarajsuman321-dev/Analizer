"""Traceable paginated engineering PDF and nine-sheet Excel reports."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from contextlib import contextmanager
import os
import re
import tempfile
from uuid import uuid4
import numpy as np
import pandas as pd
from app_version import VERSION

SHEETS=['Executive Summary','Test Metadata','KPI Results','Phase Breakdown','Comparison Results','Tolerance Breaches','Fault & Anomaly Log','Channel Mapping','Calculation Definitions']


def safe_record(value):
    if isinstance(value,dict):return {str(k):safe_record(v) for k,v in value.items() if k not in ('traces','quality_traces')}
    if isinstance(value,(list,tuple)):return [safe_record(v) for v in value]
    if isinstance(value,np.ndarray):return safe_record(value.tolist())
    if isinstance(value,(np.integer,np.floating,np.bool_)):value=value.item()
    if isinstance(value,Path):return str(value)
    if isinstance(value,float) and not np.isfinite(value):return None
    return value


def json_text(value):return json.dumps(safe_record(value),ensure_ascii=False,sort_keys=True)


def source_records(store,cancel=None,dataset_ids=None):
    rows=[];seen=set()
    for c in store.channels.values():
        if dataset_ids is not None and c.dataset_id not in dataset_ids:continue
        dataset=store.datasets.get(c.dataset_id)
        source=c.source or 'Workspace channel arrays · '+(dataset.name if dataset else 'Generated')
        identity=(source,c.dataset_id if not c.source else None)
        if identity in seen:continue
        seen.add(identity);path=Path(source);digest=hashlib.sha256()
        if c.source and path.is_file():
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):
                    if cancel and cancel.is_set():raise InterruptedError('Report cancelled')
                    digest.update(block)
            method='SHA-256 source file'
        else:
            for channel in store.channels.values():
                same_source=channel.source==c.source if c.source else not channel.source and channel.dataset_id==c.dataset_id
                if same_source and (dataset_ids is None or channel.dataset_id in dataset_ids):
                    if cancel and cancel.is_set():raise InterruptedError('Report cancelled')
                    digest.update(channel.name.encode());digest.update(channel.x.tobytes());digest.update(channel.y.tobytes())
            method='SHA-256 preserved channel arrays (source file unavailable)'
        rows.append({'source':source,'sha256':digest.hexdigest(),'method':method})
    return rows


def report_tables(store,runs,comparison,metadata=None,cancel=None,scope='whole_recording',view=None,selected_ids=None):
    from app_engineering_report_summary import event_identity,event_category,scope_label,required_result,GROUPING_POLICY
    metadata=metadata or {};profile=runs[0]['profile'];stamp=datetime.now(timezone.utc).isoformat()
    sources=source_records(store,cancel,{r['dataset_id'] for r in runs} if all(r.get('dataset_id') is not None for r in runs) else None);info={'Application version':VERSION,'Generated UTC':stamp,'Profile':profile['id'],'Profile schema':profile['schema_version'],**profile.get('metadata',{}),**metadata,'Report ID':metadata.get('Report ID') or uuid4().hex,'Report scope':scope,'Data policy':runs[0]['quality_policy'],'Profile configuration':profile,'Calibration definitions':profile.get('calibrations',{}),'Tolerance configuration':profile.get('tolerances',{}),'Acceptance limits':profile.get('acceptance',{}),'Sources':sources,'Run alignment':[{'role':r.get('role','analysis'),'dataset':r['dataset_id'],'offset_s':r['offset_s'],'scope':scope_label(r)} for r in runs],'Processing':[{'id':c.id,'name':c.name,'parents':c.parents,'recipe':c.recipe,'masks':c.masks,'shift':c.shift,'unit':c.unit,'source_unit':c.attributes.get('raw_unit',c.unit)} for c in store.channels.values()],'View':view or metadata.get('View',{}),'Event grouping policy':GROUPING_POLICY}
    positions=(view or {}).get('cursors',[])
    info['Source timing quality']=[{'Run':run.get('role','analysis'),'Scope':scope_label(run),'channel_id':trace.channel.id,'source':trace.channel.name,'canonical_role':key,**trace.quality(run.get('scope_start_s',(run.get('run_bounds') or (None,None))[0]),run.get('scope_end_s',(run.get('run_bounds') or (None,None))[1]))} for run in runs for key,trace in run.get('quality_traces',run['traces']).items()]
    if len(positions)==2:
        from app_engineering_report_pdf import cursor_trace_values
        from app_engineering_trace import Trace
        cursor_rows=[];a,b=sorted(float(value)*60 for value in positions)
        for run in runs:
            traces=dict(run['traces']);represented={trace.channel.id for trace in traces.values()}
            for id in selected_ids or []:
                channel=store.channels.get(id)
                if channel and channel.id not in represented and channel.dataset_id==run['dataset_id'] and channel.coordinate_kind=='time':traces['source_'+id]=Trace(channel,offset=run['offset_s'])
            for key,trace in traces.items():
                values=cursor_trace_values(trace,positions,(view or {}).get('cursor_locks'),(view or {}).get('snap',True))
                cursor_rows.append({'run':run.get('role','analysis'),'scope':scope_label(run),'channel_id':trace.channel.id,'source':trace.channel.name,'canonical_role':None if key.startswith('source_') else key,'unit':trace.unit,'A_min':positions[0],'B_min':positions[1],'A_value':values[0],'B_value':values[1],'absolute_delta_x_min':abs(b-a)/60,'absolute_delta_y':abs(values[1]-values[0]),'interval_statistics':trace.stats(a,b)})
        info['Cursor interval evidence']=cursor_rows
    kpis=[];phases=[];events=[];mapping=[]
    for number,run in enumerate(runs):
        role=run.get('role',('Reference' if comparison else 'Analysis','Candidate','Golden')[min(number,2)]).title()
        for row in run['kpis']:kpis.append({'Run':role,'Scope':scope_label(run),**{k:v for k,v in row.items() if k!='definition'},'report_required':required_result(row,run['profile'])})
        for phase in run['phases']:
            row={'Run':role,'Scope':scope_label(run),'Phase':phase['name'],'Start min':phase['start_s']/60,'End min':phase['end_s']/60,'Duration min':phase['duration_s']/60}
            for metric in phase['metrics']:row[metric['name']+' ['+metric['unit']+']']=metric['value'] if metric['value'] is not None else 'Not Available'
            phases.append(row)
        for index,row in enumerate(run['anomalies']):events.append({'Run':role,'Scope':scope_label(run),**row,'source_event_id':row.get('event_id'),'event_id':event_identity(row,run,index),'original_record_index':index,'source_dataset_id':run.get('dataset_id'),'category':event_category(row),'evidence':json_text(row.get('evidence',{}))})
        for row in run['mapping']:mapping.append({'Run':role,'Scope':scope_label(run),**row,'candidates':', '.join(row.get('candidates',[]))})
        for index,warning in enumerate(run['warnings']):
            row={'name':'Data quality limitation','status':'Not evaluated','category':'Data Quality','evidence':warning}
            events.append({'Run':role,'Scope':scope_label(run),**row,'event_id':event_identity(row,run,len(run['anomalies'])+index),'original_record_index':len(run['anomalies'])+index,'source_dataset_id':run.get('dataset_id')})
    breaches=[]
    comparisons=[(comparison,'Active cursor interval' if scope=='cursor_interval' else 'Whole recording')] if comparison else []
    if metadata.get('Interval comparison'):comparisons.append((metadata['Interval comparison'],'Active cursor interval'))
    comparison_rows=[]
    for current,comparison_scope in comparisons:
        comparison_rows.extend([{**row,'Comparison':'Reference vs Candidate','Scope':comparison_scope} for row in current['kpis']]+[{**row,'Comparison':'Golden vs Candidate','Scope':comparison_scope} for row in current['golden_kpis']])
        for channel,record in current['envelopes'].items():
            if record['breaches']:
                for event in record['breaches']:breaches.append({'Channel':channel,'Scope':comparison_scope,**event,'Maximum deviation':record['max_deviation'],'Unit':record['unit'],'Maximum %':record['max_percent'],'Compared seconds':record['coverage_s']})
            else:breaches.append({'Channel':channel,'Scope':comparison_scope,'Status':'No breach detected' if record['coverage_s'] else 'Not evaluated','Compared seconds':record['coverage_s']})
        for index,warning in enumerate(current['warnings']):
            row={'name':'Tolerance limitation','status':'Not evaluated','category':'Rule Evaluation','evidence':warning}
            events.append({'Run':'Comparison','Scope':comparison_scope,**row,'event_id':event_identity(row,{'dataset_id':'comparison','report_scope':comparison_scope},index),'original_record_index':index})
    if not phases:phases=[{'Status':'Not Available','Reason':'No configured phase with sufficient evidence was observed.'}]
    if not breaches:breaches=[{'Status':'Not evaluated','Reason':'No supported tolerance comparison was configured.'}]
    executive=[{'Metric':r['name'],'Run':r['Run'],'Scope':r['Scope'],'Value':r['value'] if r['value'] is not None else 'Not Available','Unit':r['unit'],'Quality':r['status'],'Coverage':r.get('coverage'),'Reason':r.get('reason',''),'Acceptance':r['acceptance']} for r in kpis]
    metadata_rows=[]
    for key,value in info.items():
        text=json_text(value) if isinstance(value,(dict,list)) else str(value)
        chunks=[text[i:i+30000] for i in range(0,max(1,len(text)),30000)]
        for part,chunk in enumerate(chunks):metadata_rows.append({'Field':key if len(chunks)==1 else f'{key} [part {part+1}/{len(chunks)}]','Value':chunk})
    metadata_rows.append({'Field':'Profile SHA-256','Value':hashlib.sha256(json_text(profile).encode()).hexdigest()})
    definitions=[{'KPI':k['id'],'Definition':json_text(k),'Required channel':k['channel'],'Result unit':k['unit'],'Acceptance limits':json_text(profile.get('acceptance',{}).get(k['id'],{}))} for k in profile['kpis']]
    tables=dict(zip(SHEETS,[pd.DataFrame(executive),pd.DataFrame(metadata_rows),pd.DataFrame(kpis),pd.DataFrame(phases),pd.DataFrame(comparison_rows if comparison else [{'Status':'Not evaluated: Analysis mode'}]),pd.DataFrame(breaches),pd.DataFrame(events),pd.DataFrame(mapping),pd.DataFrame(definitions)]))
    if not events:tables['Fault & Anomaly Log']=pd.DataFrame(columns=['event_id','Run','Scope','category','name','status','start_s','end_s','duration_s','evidence'])
    return tables,info


def report_preview(runs,scope='whole_recording',view=None,comparison=None,selected_ids=None,detailed_appendix=False):
    """Return the same exact page budget used by PDF export, without file I/O."""
    from app_engineering_report_summary import report_plan
    plan=report_plan(runs,scope=scope,detailed_appendix=detailed_appendix)
    extra=len((comparison or {}).get('warnings',[]))
    if extra:
        plan['event_records']+=extra
        if detailed_appendix:
            import math
            plan['appendix_pages']=math.ceil(plan['event_records']/20)
            plan['expected_pages']=plan['summary_pages']+plan['appendix_pages']
    plan['cursors_min']=list((view or {}).get('cursors',[]))
    present={run.get('report_scope','whole_recording') for run in runs}
    requested={'whole_recording','cursor_interval'} if scope=='both' else {scope}
    plan['event_count_exact']=bool(runs) and present==requested
    return plan


@contextmanager
def staged_report_bundle(destinations,cancel=None):
    """Publish a complete evidence set, restoring all previous files on error.

    Each writer uses a private file on the destination filesystem. Cancellation
    is checked before the commit. Commit then completes without cancellation
    checkpoints; an I/O error restores already-replaced members of the set.
    """
    staged={};backups={};published=[];retained_backups=set()
    def temporary(path):
        descriptor,name=tempfile.mkstemp(prefix='.signal-report-',suffix=path.suffix,dir=path.parent)
        os.close(descriptor);return Path(name)
    try:
        for destination in destinations:
            destination=Path(destination);staged[destination]=temporary(destination)
        yield staged
        if cancel and cancel.is_set():raise InterruptedError('Report cancelled')
        # Move existing files only after every new artifact has been written.
        for destination in staged:
            if destination.exists():
                backup=temporary(destination);os.replace(destination,backup);backups[destination]=backup
        for destination,source in reversed(tuple(staged.items())):
            os.replace(source,destination);published.append(destination)
        from app_operation_context import mark_committed
        mark_committed()
    except BaseException:
        rollback_errors=[]
        for destination in reversed(published):
            if destination not in backups:
                try:destination.unlink(missing_ok=True)
                except OSError as exc:rollback_errors.append(str(exc))
        for destination,backup in backups.items():
            try:os.replace(backup,destination)
            except OSError as exc:
                # A locked destination must never cause the only backup to be
                # deleted by cleanup. Surface its recoverable location.
                retained_backups.add(backup)
                rollback_errors.append(str(backup)+': '+str(exc))
        if rollback_errors:raise OSError('Report rollback needs recovery; retained backup paths: '+'; '.join(rollback_errors))
        raise
    finally:
        for path in [*staged.values(),*backups.values()]:
            if path not in retained_backups:path.unlink(missing_ok=True)


def _write_workbook(path,tables,cancel=None):
    from openpyxl.styles import PatternFill,Font
    with pd.ExcelWriter(path,engine='openpyxl') as writer:
        for name,frame in tables.items():
            if cancel and cancel.is_set():raise InterruptedError('Report cancelled')
            if len(frame)>1048575:raise ValueError(name+' exceeds the Excel worksheet row limit; use the complete JSON/CSV evidence')
            frame=frame.copy()
            for column in frame:
                frame[column]=frame[column].map(lambda v:json_text(v) if isinstance(v,(dict,list)) else v)
            frame.to_excel(writer,sheet_name=name,index=False,na_rep='Not Available')
            ws=writer.sheets[name];ws.freeze_panes='A2';ws.auto_filter.ref=ws.dimensions
            for cell in ws[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='243A53')
            if 'percent' in frame:
                percent_column=list(frame.columns).index('percent')+1
                for row in range(2,ws.max_row+1):ws.cell(row,percent_column).number_format='0.00"%"'
            for column in ws.columns:
                ws.column_dimensions[column[0].column_letter].width=min(60,max(14,max(len(str(c.value or '')) for c in list(column)[:80])+2))
            if 'accent' in frame:
                col=list(frame.columns).index('accent')+1
                from openpyxl.utils import get_column_letter
                ws.column_dimensions[get_column_letter(col)].hidden=True
                for row in range(2,ws.max_row+1):
                    color=ws.cell(row,col).value
                    if isinstance(color,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',color):
                        for cell in ws[row]:cell.fill=PatternFill('solid',fgColor=color.lstrip('#'))


def _scope_runs(runs,comparison,scope,view,cancel):
    """Direct exports get the same calculation scope as the engineering UI."""
    if scope not in ('whole_recording','cursor_interval','both'):
        raise ValueError('Unknown engineering report scope')
    expected={'whole_recording'} if scope=='whole_recording' else {'cursor_interval'} if scope=='cursor_interval' else {'whole_recording','cursor_interval'}
    present={run.get('report_scope','whole_recording') for run in runs}
    if present==expected:return runs,comparison
    positions=(view or {}).get('cursors',[])
    if scope!='whole_recording' and (len(positions)!=2 or not np.isfinite(positions).all()):
        raise ValueError('The active cursor interval requires two finite cursor times')
    from app_engineering_analytics import scoped_run
    whole=[run for run in runs if run.get('report_scope','whole_recording')=='whole_recording']
    if not whole:raise ValueError('Whole-recording analysis is required to change the report scope')
    scoped=list(whole) if scope in ('whole_recording','both') else []
    if scope!='whole_recording':
        for run in whole:
            if cancel and cancel.is_set():raise InterruptedError('Report cancelled')
            scoped.append(scoped_run(run,*sorted(float(x)*60 for x in positions)))
    if comparison:
        from app_engineering_compare import compare_runs
        group=[run for run in scoped if run.get('report_scope','whole_recording')==('cursor_interval' if scope=='cursor_interval' else 'whole_recording')]
        comparison=compare_runs(group[0],group[1],group[0]['profile'],group[2] if len(group)>2 else None,cancel)
    return scoped,comparison


def source_view_identity(store,view,selected_ids=None):
    """Resolve comparison projection locks to their preserved source sample.

    Engineering projections keep one original sample per displayed sample and
    record their parent ID. Derived/resampled channels without that invariant
    keep their own identity; they must never be guessed back onto a source.
    """
    def original_id(channel_id):
        channel=store.channels.get(channel_id)
        if channel and channel.attributes.get('engineering_projection') and len(channel.parents)==1:
            parent=store.channels.get(channel.parents[0])
            if parent and len(parent.x)==len(channel.x):return parent.id
        return channel_id
    result=dict(view or {});locks=[]
    for lock in result.get('cursor_locks',[]):
        if lock:
            resolved=original_id(lock.get('channel'));lock=dict(lock)
            if resolved!=lock.get('channel'):lock.update(projected_channel=lock['channel'],channel=resolved)
        locks.append(lock)
    if 'cursor_locks' in result:result['cursor_locks']=locks
    return result,list(dict.fromkeys(original_id(id) for id in selected_ids)) if selected_ids is not None else None


def export_engineering(path,store,runs,comparison=None,metadata=None,view=None,cancel=None,selected_ids=None,scope='whole_recording',detailed_appendix=False):
    """Write a bounded summary and complete, linked evidence atomically.

    A PDF always comes with a complete workbook, event CSV and JSON. All files
    are staged before replacing destinations; cancellation before completion
    leaves previous files untouched. No events are dropped to meet a page budget.
    """
    if cancel and cancel.is_set():raise InterruptedError('Report cancelled')
    path=Path(path)
    if path.suffix.lower() not in ('.pdf','.xlsx'):raise ValueError('Choose PDF or Excel for an engineering report')
    view,selected_ids=source_view_identity(store,view,selected_ids)
    runs,comparison=_scope_runs(runs,comparison,scope,view,cancel)
    if scope=='both' and comparison:
        from app_engineering_compare import compare_runs
        interval=[run for run in runs if run.get('report_scope')=='cursor_interval']
        if len(interval)>1:
            metadata={**(metadata or {}),'Interval comparison':compare_runs(interval[0],interval[1],interval[0]['profile'],interval[2] if len(interval)>2 else None,cancel)}
    tables,info=report_tables(store,runs,comparison,metadata,cancel,scope,view,selected_ids)
    from app_engineering_report_summary import summarize_events
    events=tables['Fault & Anomaly Log'].to_dict('records')
    groups=summarize_events(events)
    group_by_id={id:group['group_id'] for group in groups for id in group['event_ids']}
    if not tables['Fault & Anomaly Log'].empty:
        tables['Fault & Anomaly Log']['summary_group_id']=tables['Fault & Anomaly Log']['event_id'].map(group_by_id)
        tables['Fault & Anomaly Log']['report_id']=info['Report ID']
    plan=report_preview(runs,scope,view,comparison,selected_ids,detailed_appendix)
    if scope=='both' and (metadata or {}).get('Interval comparison'):
        plan['event_records']=len(events)
        if detailed_appendix:
            import math
            plan['appendix_pages']=math.ceil(len(events)/20);plan['expected_pages']=plan['summary_pages']+plan['appendix_pages']
    info['Report preview']=plan
    evidence={'report_id':info['Report ID'],'metadata':info,'runs':safe_record(runs),
              'comparison':safe_record(comparison),'tables':{name:frame.to_dict('records') for name,frame in tables.items()},
              'event_groups':groups,'page_plan':plan}
    companion=path.with_suffix('.evidence.xlsx') if path.suffix.lower()=='.pdf' else path
    json_path=path.with_suffix('.evidence.json');csv_path=path.with_suffix('.events.csv')
    # Publish the primary target last, with every companion already complete.
    with staged_report_bundle(list(dict.fromkeys([path,companion,json_path,csv_path])),cancel) as staged:
        primary=staged[path];workbook=staged[companion]
        json_output=staged[json_path];csv_output=staged[csv_path]
        _write_workbook(workbook,tables,cancel)
        if cancel and cancel.is_set():raise InterruptedError('Report cancelled')
        Path(json_output).write_text(json.dumps(safe_record(evidence),ensure_ascii=False,indent=2),encoding='utf-8')
        tables['Fault & Anomaly Log'].to_csv(csv_output,index=False,encoding='utf-8-sig')
        if path.suffix.lower()=='.pdf':write_pdf(primary,store,runs,comparison,tables,info,view,cancel,selected_ids,plan,groups)
        if cancel and cancel.is_set():raise InterruptedError('Report cancelled')
    return tables


def write_pdf(path,store,runs,comparison,tables,info,view,cancel,selected_ids,plan=None,groups=None):
    from app_engineering_report_pdf import render_summary
    return render_summary(path,store,runs,comparison,tables,info,view,cancel,selected_ids,plan,groups)

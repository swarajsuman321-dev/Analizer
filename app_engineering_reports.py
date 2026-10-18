"""Traceable paginated engineering PDF and nine-sheet Excel reports."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import textwrap
import numpy as np
import pandas as pd
from app_version import VERSION
from app_support import atomic_output

SHEETS=['Executive Summary','Test Metadata','KPI Results','Phase Breakdown','Comparison Results','Tolerance Breaches','Fault & Anomaly Log','Channel Mapping','Calculation Definitions']


def safe_record(value):
    if isinstance(value,dict):return {str(k):safe_record(v) for k,v in value.items() if k!='traces'}
    if isinstance(value,(list,tuple)):return [safe_record(v) for v in value]
    if isinstance(value,np.ndarray):return safe_record(value.tolist())
    if isinstance(value,(np.integer,np.floating)):value=value.item()
    if isinstance(value,float) and not np.isfinite(value):return None
    return value


def json_text(value):return json.dumps(safe_record(value),ensure_ascii=False,sort_keys=True)


def source_records(store,cancel=None):
    rows=[];seen=set()
    for c in store.channels.values():
        source=c.source or 'Workspace channel arrays'
        if source in seen:continue
        seen.add(source);path=Path(source);digest=hashlib.sha256()
        if path.is_file():
            with path.open('rb') as stream:
                for block in iter(lambda:stream.read(1024*1024),b''):
                    if cancel and cancel.is_set():raise InterruptedError('Report cancelled')
                    digest.update(block)
            method='SHA-256 source file'
        else:
            for channel in store.channels.values():
                if (channel.source or 'Workspace channel arrays')==source:
                    digest.update(channel.name.encode());digest.update(channel.x.tobytes());digest.update(channel.y.tobytes())
            method='SHA-256 preserved channel arrays (source file unavailable)'
        rows.append({'source':source,'sha256':digest.hexdigest(),'method':method})
    return rows


def report_tables(store,runs,comparison,metadata=None,cancel=None):
    metadata=metadata or {};profile=runs[0]['profile'];stamp=datetime.now(timezone.utc).isoformat()
    sources=source_records(store,cancel);info={'Application version':VERSION,'Generated UTC':stamp,'Profile':profile['id'],'Profile schema':profile['schema_version'],**profile.get('metadata',{}),**metadata,'Data policy':runs[0]['quality_policy'],'Profile configuration':profile,'Calibration definitions':profile.get('calibrations',{}),'Tolerance configuration':profile.get('tolerances',{}),'Acceptance limits':profile.get('acceptance',{}),'Sources':sources,'Run alignment':[{'role':r.get('role','analysis'),'dataset':r['dataset_id'],'offset_s':r['offset_s']} for r in runs],'Processing':[{'id':c.id,'name':c.name,'parents':c.parents,'recipe':c.recipe,'masks':c.masks,'shift':c.shift,'unit':c.unit,'source_unit':c.attributes.get('raw_unit',c.unit)} for c in store.channels.values()],'View':metadata.get('View',{})}
    kpis=[];phases=[];events=[];mapping=[]
    for role,run in zip(('Reference' if comparison else 'Analysis','Candidate','Golden'),runs):
        for row in run['kpis']:kpis.append({'Run':role,**{k:v for k,v in row.items() if k!='definition'}})
        for phase in run['phases']:
            row={'Run':role,'Phase':phase['name'],'Start min':phase['start_s']/60,'End min':phase['end_s']/60,'Duration min':phase['duration_s']/60}
            for metric in phase['metrics']:row[metric['name']+' ['+metric['unit']+']']=metric['value'] if metric['value'] is not None else 'Not Available'
            phases.append(row)
        for row in run['anomalies']:events.append({'Run':role,**row,'evidence':json_text(row['evidence'])})
        for row in run['mapping']:mapping.append({'Run':role,**row,'candidates':', '.join(row['candidates'])})
        for warning in run['warnings']:events.append({'Run':role,'name':'Data quality limitation','status':'Not evaluated','evidence':warning})
    breaches=[]
    if comparison:
        for channel,record in comparison['envelopes'].items():
            if record['breaches']:
                for event in record['breaches']:breaches.append({'Channel':channel,**event,'Maximum deviation':record['max_deviation'],'Unit':record['unit'],'Maximum %':record['max_percent'],'Compared seconds':record['coverage_s']})
            else:breaches.append({'Channel':channel,'Status':'No breach detected' if record['coverage_s'] else 'Not evaluated','Compared seconds':record['coverage_s']})
        for warning in comparison['warnings']:events.append({'Run':'Comparison','name':'Tolerance limitation','status':'Not evaluated','evidence':warning})
    if not events:events=[{'status':'Not evaluated','evidence':'No anomaly rules were configured; this is not proof of a fault-free run.'}]
    if not phases:phases=[{'Status':'Not Available','Reason':'No configured phase with sufficient evidence was observed.'}]
    if not breaches:breaches=[{'Status':'Not evaluated','Reason':'No supported tolerance comparison was configured.'}]
    executive=[{'Metric':r['name'],'Run':r['Run'],'Value':r['value'] if r['value'] is not None else 'Not Available','Unit':r['unit'],'Quality':r['status'],'Acceptance':r['acceptance']} for r in kpis]
    metadata_rows=[]
    for key,value in info.items():
        text=json_text(value) if isinstance(value,(dict,list)) else str(value)
        chunks=[text[i:i+30000] for i in range(0,max(1,len(text)),30000)]
        for part,chunk in enumerate(chunks):metadata_rows.append({'Field':key if len(chunks)==1 else f'{key} [part {part+1}/{len(chunks)}]','Value':chunk})
    metadata_rows.append({'Field':'Profile SHA-256','Value':hashlib.sha256(json_text(profile).encode()).hexdigest()})
    definitions=[{'KPI':k['id'],'Definition':json_text(k),'Required channel':k['channel'],'Result unit':k['unit'],'Acceptance limits':json_text(profile.get('acceptance',{}).get(k['id'],{}))} for k in profile['kpis']]
    tables=dict(zip(SHEETS,[pd.DataFrame(executive),pd.DataFrame(metadata_rows),pd.DataFrame(kpis),pd.DataFrame(phases),pd.DataFrame(([{**row,'Comparison':'Reference vs Candidate'} for row in comparison['kpis']]+[{**row,'Comparison':'Golden vs Candidate'} for row in comparison['golden_kpis']]) if comparison else [{'Status':'Not evaluated: Analysis mode'}]),pd.DataFrame(breaches),pd.DataFrame(events),pd.DataFrame(mapping),pd.DataFrame(definitions)]))
    return tables,info


def export_engineering(path,store,runs,comparison=None,metadata=None,view=None,cancel=None,selected_ids=None):
    if cancel and cancel.is_set():raise InterruptedError('Report cancelled')
    path=Path(path);tables,info=report_tables(store,runs,comparison,metadata,cancel)
    if path.suffix.lower() not in ('.pdf','.xlsx'):raise ValueError('Choose PDF or Excel for an engineering report')
    with atomic_output(path) as temporary:
        if path.suffix.lower()=='.xlsx':
            from openpyxl.styles import PatternFill,Font
            with pd.ExcelWriter(temporary,engine='openpyxl') as writer:
                for number,(name,frame) in enumerate(tables.items()):
                    if number and cancel and cancel.is_set():raise InterruptedError('Report cancelled')
                    # Excel row limit is checked explicitly rather than silently truncating.
                    if len(frame)>1048575:raise ValueError(name+' exceeds the Excel worksheet row limit')
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
                            if color:
                                for cell in ws[row]:cell.fill=PatternFill('solid',fgColor=color.lstrip('#'))
        else:write_pdf(temporary,store,runs,comparison,tables,info,view,cancel,selected_ids)
        if cancel and cancel.is_set():raise InterruptedError('Report cancelled')
    return tables


def write_pdf(path,store,runs,comparison,tables,info,view,cancel,selected_ids):
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_pdf import PdfPages
    from app_trace_colors import channel_colors
    from app_presentation import CURSOR_COLORS
    colors=channel_colors(store)
    runs=[{**run,'traces':dict(run['traces'])} for run in runs]
    if selected_ids:
        from app_engineering_trace import Trace
        represented={trace.channel.id for run in runs for trace in run['traces'].values()}
        for id in selected_ids:
            if id in represented or id not in store.channels:continue
            channel=store.channels[id]
            for run in runs:
                if channel.dataset_id==run['dataset_id'] and channel.coordinate_kind=='time':
                    run['traces']['source_'+id]=Trace(channel,offset=run['offset_s']);break
    def finish(pdf,fig):
        if cancel and cancel.is_set():raise InterruptedError('Report cancelled')
        fig.text(.04,.018,f'Appliance Signal Studio {VERSION} | {info["Generated UTC"]} | Profile {info["Profile"]}',fontsize=7,color='#526074')
        pdf.savefig(fig);fig.clear()
    def table_pages(pdf,title,frame,columns=None):
        if columns:frame=frame[[c for c in columns if c in frame]]
        # More than seven columns become vertical key/value records, retaining every metric.
        if len(frame.columns)>7:
            frame=pd.DataFrame([{'Record':i+1,'Field':str(k),'Value':json_text(v) if isinstance(v,(dict,list)) else v} for i,row in frame.iterrows() for k,v in row.items()])
        records=[]
        for _,row in frame.iterrows():
            values=[str(v) if pd.notna(v) else 'Not Available' for v in row]
            wrapped=[textwrap.wrap(v,30 if len(values)>3 else 80) or [''] for v in values]
            for index in range(max(map(len,wrapped))):records.append([parts[index] if index<len(parts) else '' for parts in wrapped])
        for start in range(0,max(1,len(records)),28):
            fig=Figure(figsize=(11.7,8.3));fig.suptitle(title,fontsize=16,x=.04,ha='left');axis=fig.add_axes([.04,.09,.92,.80]);axis.axis('off')
            data=records[start:start+28] or [['Not Available']*max(1,len(frame.columns))]
            table=axis.table(cellText=data,colLabels=list(frame.columns) or ['Result'],loc='upper left',cellLoc='left');table.auto_set_font_size(False);table.set_fontsize(8);table.scale(1,1.45)
            for (row,col),cell in table.get_celld().items():
                cell.set_edgecolor('#d6dee8')
                if row==0:cell.set_facecolor('#243a53');cell.get_text().set_color('white')
                elif row%2:cell.set_facecolor('#f1f5f9')
            finish(pdf,fig)
    with PdfPages(path,metadata={'Title':str(info.get('Report title','Engineering report')),'Author':'Appliance Signal Studio','Subject':json_text({'profile':info['Profile'],'sources':info['Sources']})}) as pdf:
        pdf.attach_note(json_text(info))
        cover=Figure(figsize=(11.7,8.3));cover.text(.05,.95,str(info.get('Report title','Engineering Report')),fontsize=20,weight='bold')
        header=[f"Appliance: {runs[0]['profile']['category']} | Manufacturer: {info.get('manufacturer') or 'Not provided'} | Model: {info.get('model') or 'Not provided'}",f"Scenario: {info.get('test_scenario') or 'Not provided'} | Generated: {info['Generated UTC']}",f"Profile: {info['Profile']} / schema {info['Profile schema']} | App: {VERSION}","Recordings: "+'; '.join(Path(source['source']).name for source in info['Sources']),"Boundary conditions: "+(json_text(info.get('boundary_conditions')) if info.get('boundary_conditions') else 'Not recorded'),"Acceptance: only explicit configured limits apply; deviation colors are not verdicts."]
        y=.90
        for line in header:
            for part in textwrap.wrap(line,135):cover.text(.05,y,part,fontsize=8);y-=.022
        axis=cover.add_axes([.04,.07,.92,max(.30,y-.11)]);axis.axis('off')
        primary={'cycle_duration','total_energy','total_water','peak_temperature','peak_speed','vibration_rms','oob_retries'}
        rows=[]
        for run in runs:
            for result in run['kpis']:
                if result['id'] in primary:rows.append([run.get('role','Analysis'),result['name'],f"{result['value']:.6g}" if result['value'] is not None else 'Not Available',result['unit'],result['acceptance']])
        if not rows:rows=[['Analysis','No configured primary KPIs','Not Available','','Not Evaluated']]
        table=axis.table(cellText=rows,colLabels=['Run','Primary KPI','Value','Unit','Acceptance'],loc='upper left',cellLoc='left');table.auto_set_font_size(False);table.set_fontsize(8);table.scale(1,1.35)
        for (row,col),cell in table.get_celld().items():
            cell.set_edgecolor('#d6dee8')
            if row==0:cell.set_facecolor('#243a53');cell.get_text().set_color('white')
        finish(pdf,cover)
        table_pages(pdf,'1. Executive Summary — all KPI results',tables['Executive Summary'])
        compact_metadata=tables['Test Metadata'][~tables['Test Metadata']['Field'].str.startswith(('Profile configuration','Processing','View'))]
        table_pages(pdf,'Test Metadata and Traceability — complete configuration in Excel',compact_metadata)
        table_pages(pdf,'2. Phase Breakdown',tables['Phase Breakdown'])
        keys=list(dict.fromkeys(key for run in runs for key in run['traces']))
        if selected_ids:
            keys=[key for key in keys if any(run['traces'].get(key) and run['traces'][key].channel.id in selected_ids for run in runs)]
        if not keys:table_pages(pdf,'3. Graphical Evidence',pd.DataFrame([{'Status':'Not Available','Reason':'No supported time-domain channels for the selected runs'}]))
        for start in range(0,len(keys),4):
            group=keys[start:start+4];fig=Figure(figsize=(11.7,8.3),layout='constrained');fig.suptitle('3. Graphical Evidence — time in minutes')
            for number,key in enumerate(group,1):
                axis=fig.add_subplot(len(group),1,number)
                for role,run in zip(('Reference' if comparison else 'Analysis','Candidate','Golden'),runs):
                    trace=run['traces'].get(key)
                    if trace is None:continue
                    from app_fast_plot import EnvelopeCache
                    x,y=EnvelopeCache(trace.raw_t/60,trace.raw_y).visible(float(trace.raw_t[0]/60),float(trace.raw_t[-1]/60),10000) if len(trace.raw_t) else ([],[])
                    axis.plot(x,y,label=role+' · '+trace.channel.name,color=colors.get(trace.channel.id),linewidth=.8,drawstyle='steps-post' if trace.kind!='analog' else 'default')
                    axis.set_ylabel(trace.unit)
                for phase in runs[0]['phases']:
                    axis.axvspan(phase['start_s']/60,phase['end_s']/60,alpha=.06,color='#5897ba');axis.text(phase['start_s']/60,.95,phase['name'],transform=axis.get_xaxis_transform(),fontsize=6,va='top')
                envelope=comparison['envelopes'].get(key) if comparison else None
                if envelope:
                    axis.fill_between(envelope['grid']/60,envelope['lower'],envelope['upper'],alpha=.16,color='#629d76',label='Tolerance envelope')
                    for breach in envelope['breaches']:axis.axvspan(breach['start_s']/60,breach['end_s']/60,color='#dd5555',alpha=.22)
                if view:
                    for name,position,color in zip(('A','B'),view.get('cursors',[]),CURSOR_COLORS):axis.axvline(position,color=color,linestyle='--',label='Cursor '+name)
                axis.legend(fontsize=7,loc='upper right',ncol=2);axis.set_xlabel('Time (min)');axis.grid(alpha=.15)
            finish(pdf,fig)
        if comparison:table_pages(pdf,'KPI Comparison — deviation colors are not acceptance',tables['Comparison Results'],['name','reference','candidate','delta','percent','unit'])
        table_pages(pdf,'4. Anomaly and Fault Analysis',tables['Fault & Anomaly Log'])
        table_pages(pdf,'Tolerance Breaches',tables['Tolerance Breaches'])
        table_pages(pdf,'Channel Mapping',tables['Channel Mapping'],['Run','name','canonical_id','source_unit','method'])
        table_pages(pdf,'Calculation Definitions',tables['Calculation Definitions'])

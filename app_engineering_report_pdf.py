"""Four-section engineering narrative with complete sidecar evidence.

The PDF is deliberately a summary. Its tables have explicit presentation budgets
and name the complete evidence package when more records exist. Full rule JSON,
recipes and raw event logs belong in the linked machine-readable evidence, never
in thousands of repeated PDF field/value pages.
"""
from pathlib import PureWindowsPath
import textwrap
import re
import numpy as np
from app_engineering_report_summary import finite_number,scope_label,SCOPE_LABELS

INK='#182c42'
MUTED='#526074'
PRINT_COLORS=('#075985','#b45309','#047857','#7e22ce','#be123c','#334155')


def value_text(value):
    if value is None:return 'Not Available'
    if isinstance(value,(float,np.floating)):
        return f'{value:.6g}' if np.isfinite(value) else 'Not Available'
    return str(value)


def short(value,width=50):
    text=value_text(value).replace('\n',' ')
    return text if len(text)<=width else text[:width-1]+'…'


def balanced_rows(records,limit,*,numeric_first=False):
    """Represent each run/scope before spending a summary's remaining space."""
    if limit<=0:return []
    groups={}
    for row in records:groups.setdefault((row.get('Run'),row.get('Scope')),[]).append(row)
    if numeric_first:
        groups={key:sorted(rows,key=lambda row:finite_number(row.get('value')) is None) for key,rows in groups.items()}
    selected=[]
    for index in range(max((len(rows) for rows in groups.values()),default=0)):
        for rows in groups.values():
            if index<len(rows):selected.append(rows[index])
            if len(selected)>=limit:return selected
    return selected


def plot_samples(trace,start_s=None,end_s=None,budget=6000):
    """Print a gap-aware min/max projection without connecting unknown spans."""
    t=np.asarray(trace.raw_t);y=np.asarray(trace.raw_y)
    if not len(t):return np.array([]),np.array([])
    a=t[0] if start_s is None else start_s;b=t[-1] if end_s is None else end_s
    left=max(0,np.searchsorted(t,a)-1);right=min(len(t),np.searchsorted(t,b,side='right')+1)
    t=t[left:right];y=y[left:right]
    if not len(t):return t,y
    gap=np.flatnonzero(np.diff(t)>trace.max_gap)+1
    if len(gap):
        # An inserted NaN separates both valid endpoint samples. Original
        # observations (including duplicate-time peaks) remain unchanged.
        y=np.insert(y,gap,np.nan);t=np.insert(t,gap,t[gap])
    if len(t)<=budget:return t/60,y
    # Keep finite extrema even when a reduction bucket contains a gap. Such
    # points remain isolated (rendered as tiny markers), rather than either
    # disappearing or being connected across unsupported time.
    step=max(1,int(np.ceil(len(t)*2/budget)));out_t=[];out_y=[]
    for start in range(0,len(t),step):
        chunk=y[start:start+step];finite=np.flatnonzero(np.isfinite(chunk))
        if not len(finite):out_t.append(t[start]);out_y.append(np.nan);continue
        indices=sorted(set((int(finite[np.argmin(chunk[finite])]),int(finite[np.argmax(chunk[finite])]))))
        missing=len(finite)!=len(chunk)
        if missing:out_t.append(t[start]);out_y.append(np.nan)
        for index in indices:
            out_t.append(t[start+index]);out_y.append(chunk[index])
            if missing:out_t.append(t[start+index]);out_y.append(np.nan)
    return np.asarray(out_t)/60,np.asarray(out_y)


def cursor_trace_values(trace,cursors_min,locks=None,snap=False):
    """Use the same channel/sample identity as the locked UI cursor marker."""
    values=trace.sample(np.asarray(cursors_min,float)*60)
    source=getattr(trace,'cursor_source',trace)
    if snap and len(source.raw_t):
        for index,point in enumerate(np.asarray(cursors_min,float)*60):
            if point<source.raw_t[0] or point>source.raw_t[-1]:continue
            sample=min(len(source.raw_t)-1,int(np.searchsorted(source.raw_t,point)))
            if sample and point-source.raw_t[sample-1]<source.raw_t[sample]-point:sample-=1
            sample=int(np.searchsorted(source.raw_t,source.raw_t[sample],side='right')-1)
            values[index]=source.raw_y[sample]
    for index,lock in enumerate((locks or [])[:len(values)]):
        if lock and lock.get('channel')==trace.channel.id:
            sample=lock.get('index')
            if isinstance(sample,(int,np.integer)):
                positions=np.flatnonzero(source.raw_indices==sample)
                if len(positions):values[index]=source.raw_y[positions[0]]
    return values


def render_summary(path,store,runs,comparison,tables,info,view,cancel,selected_ids,plan=None,groups=None):
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_pdf import PdfPages
    from app_engineering_reports import report_preview
    from app_engineering_report_summary import summarize_events
    from app_presentation import CURSOR_COLORS
    plan=plan or report_preview(runs,info.get('Report scope','whole_recording'),view,comparison)
    groups=groups if groups is not None else summarize_events(tables['Fault & Anomaly Log'].to_dict('records'))
    report_id=info['Report ID'];page=0;figures=[]
    scope=SCOPE_LABELS[info.get('Report scope','whole_recording')]
    sources=info['Sources'];profile=runs[0]['profile']
    whole=[run for run in runs if run.get('report_scope','whole_recording')=='whole_recording']
    visual_runs=[{**run,'traces':dict(run['traces'])} for run in (whole or runs)]
    if selected_ids:
        from app_engineering_trace import Trace
        represented={trace.channel.id for run in visual_runs for trace in run['traces'].values()}
        for id in selected_ids:
            channel=store.channels.get(id)
            if id in represented or channel is None or channel.coordinate_kind!='time':continue
            for run in visual_runs:
                if channel.dataset_id==run['dataset_id']:
                    run['traces']['source_'+id]=Trace(channel,offset=run['offset_s']);break
    # One source identity everywhere; basename is safe for a shareable PDF.
    from app_channel_identity import dataset_aliases
    aliases=dataset_aliases(store)

    def check():
        if cancel and cancel.is_set():raise InterruptedError('Report cancelled')

    def new(title,subtitle=None):
        check();fig=Figure(figsize=(11.7,8.3),facecolor='white')
        fig.text(.05,.95,title,fontsize=17,weight='bold',color=INK)
        fig.text(.05,.913,subtitle or scope,fontsize=8,color=MUTED)
        return fig

    def paragraph(fig,text,x=.05,y=.87,width=130,size=9,line=.025,color=INK):
        for segment in str(text).split('\n'):
            for part in textwrap.wrap(segment,width,break_long_words=True) or ['']:
                fig.text(x,y,part,fontsize=size,color=color,va='top');y-=line
        return y

    def table(fig,headers,rows,box=(.05,.14,.90,.67),widths=None,fontsize=8,max_lines=3):
        ax=fig.add_axes(box);ax.axis('off')
        if not rows:rows=[['Not Available']+['']*(len(headers)-1)]
        ratios=np.asarray(widths or [1/len(headers)]*len(headers),float);ratios=ratios/ratios.sum()
        wrapped=[]
        for row in rows:
            wrapped.append(['\n'.join(textwrap.wrap(value_text(v),max(8,int(150*ratios[i])))) for i,v in enumerate(row)])
        # Explicit summary budgets keep the body above the reserved footer.
        for i,row in enumerate(wrapped):
            for j,cell in enumerate(row):
                lines=cell.split('\n')
                if len(lines)>max_lines:wrapped[i][j]='\n'.join(lines[:max_lines-1]+[short(lines[max_lines-1],max(8,int(150*ratios[j]))-1)+'…'])
        wrapped_headers=['\n'.join(textwrap.wrap(header,max(8,int(150*ratios[i])))) for i,header in enumerate(headers)]
        grid=ax.table(cellText=wrapped,colLabels=wrapped_headers,colWidths=ratios,cellLoc='left',loc='upper left',bbox=[0,0,1,1])
        grid.auto_set_font_size(False);grid.set_fontsize(fontsize)
        for (r,c),cell in grid.get_celld().items():
            cell.set_edgecolor('#d6dee8');cell.set_linewidth(.4)
            if r==0:cell.set_facecolor('#243a53');cell.get_text().set_color('white');cell.get_text().set_weight('bold')
            elif r%2:cell.set_facecolor('#f1f5f9')
        return grid

    def done(fig):figures.append(fig)

    def scope_of(run):
        label=scope_label(run)
        if run.get('report_scope')=='cursor_interval':label+=f' [{run["scope_start_s"]/60:.6g}, {run["scope_end_s"]/60:.6g}] min'
        return run.get('role','analysis').title()+' · '+label

    def note_more(fig,shown,total,noun='records',y=.105):
        paragraph(fig,f'Summary shows {shown} of {total} {noun}; all {total} remain in the companion Excel / JSON evidence.',y=y,size=8,line=.02)

    # 1. Purpose/readiness: useful conclusions and next actions precede numbers.
    fig=new('1. Purpose and analysis readiness')
    y=paragraph(fig,str(info.get('Report title','Engineering Report')),y=.867,size=14,line=.035)
    identity=' | '.join(f'{label}: {info.get(label) or info.get(key) or "Not provided / not reviewed"}' for key,label in [('test_id','Test ID'),('manufacturer','Manufacturer'),('model','Model'),('operator','Operator'),('test_scenario','Program / Settings')])
    y=paragraph(fig,identity,y=y-.01,size=9)
    y=paragraph(fig,'Recordings: '+'; '.join(PureWindowsPath(s['source']).name for s in sources),y=y-.008,size=9)
    summaries=[run.get('readiness_summary',{}) for run in runs]
    incomplete=any(k['value'] is None for run in runs for k in run['kpis']) or any(s.get('data_adequacy')=='Needs review' for s in summaries)
    y=paragraph(fig,'Incomplete analysis — review source mapping, timing coverage and applicable acceptance setup.' if incomplete else 'Calculated results are available for the stated scope; acceptance depends on explicitly configured limits.',y=y-.015,size=11)
    overview=[]
    for run in runs[:4]:
        summary=run.get('readiness_summary',{})
        overview.append([scope_of(run),summary.get('calculation','Complete'),f'{sum(k["value"] is not None for k in run["kpis"])} / {len(run["kpis"])}',summary.get('data_adequacy','Review source quality'),summary.get('acceptance','Not Evaluated')])
    table(fig,['Run / scope','Calculation','Numeric KPIs','Data adequacy','Acceptance'],overview,box=(.05,.53,.90,.12),fontsize=8)
    usable=[f'{k["name"]}: {value_text(k["value"])} {k["unit"]}' for run in runs for k in run['kpis'] if k['value'] is not None]
    paragraph(fig,'Observed usable results: '+('; '.join(usable[:3]) if usable else 'No supported numeric result; review the blockers below.'),y=.49,size=9,line=.024)
    blockers=[]
    for run in runs:
        for item in run.get('readiness',run.get('readiness_summary',{}).get('top_blockers',[])):
            if item.get('state')=='Usable result':continue
            key=(item.get('name'),item.get('state'),item.get('next_action'))
            if not any(existing[1:]==key[1:] for existing in blockers):blockers.append(key)
    y=.43
    for name,state,action in blockers[:3]:y=paragraph(fig,f'{name} — {state}. Next: {action}',y=y,size=9,line=.022)-.01
    contents='Contents: '+'  |  '.join(f'{s["title"]} (pp. {s["first_page"]}–{s["first_page"]+s["pages"]-1})' for s in plan['section_pages'])
    paragraph(fig,contents,y=.18,size=8,line=.022,width=145)
    paragraph(fig,f'Report ID: {report_id}. Complete event log: {len(tables["Fault & Anomaly Log"]):,} records. Summary length: {plan["summary_pages"]} pages. Detailed evidence accompanies this PDF.',y=.11,size=8,line=.02,width=145)
    done(fig)

    # 2. Mapping and coverage with no silently inferred units.
    fig=new('1. Sources, mapping review and timing coverage')
    rows=[]
    for run in runs:
        for key,trace in {**run.get('quality_traces',{}),**run['traces']}.items():
            q=trace.quality(run.get('scope_start_s'),run.get('scope_end_s')) if hasattr(trace,'quality') else trace.stats()
            mapping=next((row for row in run['mapping'] if row.get('channel_id')==trace.channel.id),{})
            role=key+' ['+trace.unit+']'+(' · timing only' if key not in run['traces'] else '')
            rows.append([run.get('role','analysis').title(),short(trace.channel.name,30),role,mapping.get('review_status',mapping.get('method','Unreviewed')),f'{q.get("observed_span_s",q.get("duration_s",0))/60:.4g} / {q.get("supported_duration_s",q.get("known_s",0))/60:.4g} / {q.get("requested_span_s",q.get("duration_s",0))/60:.4g}',f'{100*q.get("coverage",0):.2f}%',str(q.get('duplicate_timestamps',trace.duplicates))+' / '+str(q.get('missing_readings',int((~np.isfinite(trace.raw_y)).sum()))),f'{trace.max_gap:.5g} s'])
    table(fig,['Run','Selected source','Canonical role / unit','Review','Observed / supported / scope min','Coverage','Duplicates / missing','Gap limit'],rows[:12],box=(.05,.38,.90,.47),widths=[.07,.17,.15,.15,.14,.08,.12,.12],fontsize=7)
    y=paragraph(fig,'Coverage is supported elapsed time divided by the requested recording or interval span; a shorter sensor span does not imply full coverage. Supported-time totals exclude unknown gaps; a peak is an observed-sample statistic. No universal adequacy or Pass/Fail threshold is assumed.',y=.33,size=9,line=.024)
    y=paragraph(fig,'Timing policy: '+runs[0]['quality_policy'],y=y-.01,size=9,line=.024)
    y=paragraph(fig,'Unmapped or blocked roles remain visible with specific actions in the KPI evidence. Physical units, pressure calibration, actual/command source roles and phase codes must be explicitly verified.',y=y-.01,size=9,line=.024)
    note_more(fig,min(12,len(rows)),len(rows),'mapped source/scope rows')
    done(fig)

    # 3. Timeline separates acquisition gaps from demonstrated appliance events.
    fig=new('2. Phase timeline and acquisition-event overview')
    ax=fig.add_axes([.20,.44,.73,.39]);lanes=[]
    for run in visual_runs[:3]:
        if run['phases']:
            for phase in run['phases'][:30]:ax.broken_barh([(phase['start_s']/60,phase['duration_s']/60)],(len(lanes)-.3,.6),facecolors=PRINT_COLORS[len(lanes)%len(PRINT_COLORS)],alpha=.7)
            lanes.append(run.get('role','analysis').title()+' · verified phases')
        for category in ('Data Quality','Appliance Event','Rule Evaluation'):
            matches=[event for event in tables['Fault & Anomaly Log'].to_dict('records') if event.get('category')==category and event.get('Run','').lower()==run.get('role','analysis').lower() and finite_number(event.get('start_s')) is not None]
            if not matches:continue
            starts=np.array([event['start_s']/60 for event in matches]);bounds=(float(starts.min()),float(max(event.get('end_s',event['start_s']) for event in matches)/60))
            if bounds[0]==bounds[1]:bounds=(bounds[0]-.01,bounds[1]+.01)
            counts,edges=np.histogram(starts,bins=200,range=bounds)
            ax.imshow(counts[np.newaxis,:],extent=(edges[0],edges[-1],len(lanes)-.3,len(lanes)+.3),aspect='auto',cmap='Blues',vmin=0,interpolation='nearest')
            lanes.append(run.get('role','analysis').title()+' · '+category)
    if lanes:ax.set_yticks(range(len(lanes)),lanes,fontsize=7);ax.set_ylim(-.6,len(lanes)-.4)
    else:ax.text(.5,.5,'No configured phase or timed event evidence',transform=ax.transAxes,ha='center');ax.set_yticks([])
    ax.set_xlabel('Time (min)',fontsize=9);ax.grid(axis='x',alpha=.2)
    paragraph(fig,'Blue density marks acquisition/rule event starts; it is not a motor-fault count. The complete log retains individual intervals and effective thresholds. Only explicitly configured and observed phases are shown.',y=.36,size=9,line=.025)
    phases=tables['Phase Breakdown'];rows=[[row.get('Run',''),row.get('Phase',row.get('Status','Not Available')),row.get('Start min',''),row.get('End min',''),row.get('Duration min','')] for row in phases.to_dict('records')]
    table(fig,['Run','Observed phase','Start min','End min','Duration min'],rows[:5],box=(.05,.14,.90,.14),fontsize=8)
    note_more(fig,min(5,len(rows)),len(rows),'phase rows',y=.10);done(fig)

    # 4–5. Four verified sources per page. Missing spans break the curves.
    keys=list(dict.fromkeys(key for run in visual_runs for key in run['traces']))
    if selected_ids:
        selected_keys=[key for key in keys if any(run['traces'].get(key) is not None and run['traces'][key].channel.id in selected_ids for run in visual_runs)]
        if selected_keys:keys=selected_keys
    # Stable engineering priority; no fabricated channels or phases.
    priority=('speed','target_speed','temperature','water_pressure','power','heater','drain','cold_valve')
    keys=sorted(keys,key=lambda k:priority.index(k) if k in priority else len(priority))

    def graphics(detail=False):
        fig=new('2. Selected source detail' if detail else '2. Whole-scope graphical evidence',scope+' · time in minutes; gaps are not connected')
        display=keys[:4]
        if not display:
            paragraph(fig,'No verified time-domain channels are available for this scope. Review mapping and units; unavailable signals are not fabricated.',y=.82,size=12);return fig
        for row,key in enumerate(display):
            ax=fig.add_axes([.10,.77-row*.17,.80,.12])
            for number,run in enumerate(visual_runs[:3]):
                trace=run['traces'].get(key)
                if trace is None:continue
                a,b=run.get('scope_start_s'),run.get('scope_end_s')
                if detail and len(trace.t):
                    # Observed peak neighborhood, explicitly not an inferred spin
                    # phase. No manufacturer phase-code meanings are invented.
                    finite=np.flatnonzero(np.isfinite(trace.y))
                    if len(finite):
                        center=float(trace.t[finite[np.argmax(np.abs(trace.y[finite]))]])
                        span=max(trace.max_gap*20,(trace.t[-1]-trace.t[0])*.08)
                        a=max(trace.t[0],center-span/2);b=min(trace.t[-1],center+span/2)
                x,y=plot_samples(trace,a,b)
                label=run.get('role','analysis').title()+' · '+short(aliases.get(trace.channel.dataset_id,''),28)+' · '+trace.channel.name
                ax.plot(x,y,color=PRINT_COLORS[number],lw=.7,marker='.',markersize=.6,label=label,drawstyle='steps-post' if trace.kind!='analog' else 'default')
                q=trace.stats(a,b)
                review=next((record.get('review_status','Unreviewed') for record in run['mapping'] if record['channel_id']==trace.channel.id),'Unreviewed')
                role_label=trace.channel.name+' · source role unreviewed' if key.startswith('source_') else key+' · '+review
                ax.text(.005,.86,f'{role_label} [{trace.unit}] · supported {100*q["coverage"]:.1f}%',transform=ax.transAxes,fontsize=7,bbox={'facecolor':'white','alpha':.8,'edgecolor':'none'})
                # Grey coverage strip shows unsupported intervals without 10,000
                # individual annotation artists or misleading filled curves.
                if len(trace.t)>1:
                    unsupported=(np.diff(trace.t)>trace.max_gap)|~np.isfinite(trace.y[:-1])|~np.isfinite(trace.y[1:])
                    ax.fill_between(trace.t/60,0,.035,where=np.r_[unsupported,False],step='post',transform=ax.get_xaxis_transform(),color='#64748b',alpha=.55,label='Unsupported time')
                for phase in run['phases'][:12]:ax.axvspan(phase['start_s']/60,phase['end_s']/60,alpha=.05,color='#0369a1')
                if a is not None and b is not None and a<b:ax.set_xlim(a/60,b/60)
            for name,position,color in zip(('A','B'),(view or {}).get('cursors',[]),CURSOR_COLORS):
                ax.axvline(position,color=color,lw=1.2,ls='--');ax.text(position,.98,f'{name} {position:.6g} min',transform=ax.get_xaxis_transform(),fontsize=6,ha='right',va='top',color=INK,bbox={'facecolor':'white','alpha':.85,'edgecolor':color,'linewidth':.5})
            ax.set_ylabel(next((run['traces'][key].unit for run in visual_runs if key in run['traces']),''),fontsize=8)
            ax.tick_params(labelsize=7);ax.grid(alpha=.15);ax.legend(fontsize=6,loc='lower right',framealpha=.75,ncol=2)
            if row==len(display)-1:ax.set_xlabel('Time (min)',fontsize=8,labelpad=2)
        paragraph(fig,'Detail: observed peak neighborhood; this is not an inferred appliance phase.' if detail else 'Grey strip: unsupported elapsed time. Exact source samples and gap policy remain in the evidence; envelope reduction preserves visible extrema and missing spans.',y=.155,size=8,line=.02)
        note_more(fig,len(display),len(keys),'selected source roles',y=.105)
        return fig
    done(graphics());done(graphics(True))

    # 6–7. A concise result table plus explicit limitations/actions, not raw JSON.
    fig=new('3. Engineering results — values and configured acceptance')
    kpis=tables['KPI Results'].to_dict('records')
    rows=[]
    required=[result for result in kpis if result.get('report_required')]
    selected=required[:18]
    for result in balanced_rows([row for row in kpis if not row.get('report_required')],18-len(selected),numeric_first=True):
        if len(selected)<18:selected.append(result)
    for result in selected:
        source=', '.join(str(s.get('source_name') or s.get('name') or s.get('canonical_id') or '') for s in result.get('source_details',[]))
        if result.get('report_required') and result['value'] is None:source=result.get('reason') or result.get('blocker') or 'Review source evidence'
        rows.append([result['Run'],short(result['Scope'],22),result['name'],value_text(result['value']),result['unit'],f'{100*result.get("coverage",0):.1f}%',result['acceptance'],short(source,35)])
    table(fig,['Run','Scope','Result','Value','Unit','Supported','Acceptance','Source / unavailable reason'],rows,box=(.05,.19,.90,.66),widths=[.07,.12,.22,.10,.07,.09,.10,.23],fontsize=7,max_lines=2)
    paragraph(fig,'Timing/integrated values are supported-time quantities, not unknown complete-cycle totals. Recorded span is a first-to-last timestamp span, not a firmware cycle boundary. Deviation colors do not establish acceptance.',y=.15,size=8,line=.021)
    note_more(fig,len(selected),len(kpis),'KPI rows'+(' (additional mandatory results continue below)' if len(required)>18 else ''),y=.085);done(fig)
    for start in range(18,len(required),8):
        fig=new('3. Primary and acceptance results — continued')
        rows=[]
        for result in required[start:start+8]:
            rows.append([result['Run']+' · '+result['Scope'],result['name'],value_text(result['value'])+' '+result['unit'],result.get('blocker') or result['status'],result.get('reason') or 'Supported for the stated scope',result.get('next_action') or 'Review configured acceptance and source evidence'])
        table(fig,['Run / scope','Required result','Value / unit','State','Reason','Next action'],rows,box=(.05,.19,.90,.66),widths=[.13,.18,.12,.15,.22,.20],fontsize=8,max_lines=4)
        paragraph(fig,'Primary / mandatory results and results with configured acceptance limits remain visible in the PDF. Complete numeric precision, mapping provenance and calculation definitions are retained in the evidence.',y=.14,size=8,line=.022)
        done(fig)
    fig=new('3. Result limitations, cursor interval and comparison')
    blocked=[row for row in kpis if row.get('blocker') or row['value'] is None]
    rows=[[row['Run']+' · '+('A–B' if row.get('Scope')=='Active cursor interval' else 'Whole'),row['name'],row.get('blocker') or row['status'],row.get('reason') or 'Review coverage and source evidence',row.get('next_action') or 'Review source mapping, units and applicable test-plan limits'] for row in balanced_rows(blocked,8)]
    table(fig,['Run / scope','Result','State','Reason','Next action'],rows,box=(.05,.46,.90,.39),widths=[.09,.18,.15,.27,.31],fontsize=7)
    cursors=(view or {}).get('cursors',[])
    y=.41
    if len(cursors)==2:
        a,b=sorted(cursors)
        y=paragraph(fig,f'Cursor A: {cursors[0]:.6g} min | Cursor B: {cursors[1]:.6g} min | absolute ΔX: {b-a:.6g} min. Cursor markers are context only in whole-recording reports; interval KPIs are explicitly labelled when selected.',y=y,size=9,line=.024)
        cursor_rows=[]
        for key in keys[:3]:
            source_run=next(run for run in visual_runs if key in run['traces']);trace=source_run['traces'][key];values=cursor_trace_values(trace,cursors,(view or {}).get('cursor_locks'),(view or {}).get('snap',True));stats=trace.stats(a*60,b*60)
            role=trace.channel.name if key.startswith('source_') else key
            if len(visual_runs)>1:role=source_run.get('role','analysis').title()+' · '+role
            cursor_rows.append([short(role,35),trace.unit,value_text(values[0]),value_text(values[1]),value_text(abs(values[1]-values[0])),value_text(stats.get('min')),value_text(stats.get('max')),value_text(stats.get('mean'))])
        table(fig,['Source role','Unit','A','B','|ΔY|','Min','Max','Mean'],cursor_rows,box=(.05,.24 if comparison else .18,.90,.10 if comparison else .12),fontsize=7)
    if comparison:
        compared=tables['Comparison Results'].to_dict('records')
        # Keep comparison evidence visible even when A/B context is present.
        # Prefer available numeric comparisons over a wall of unavailable KPIs.
        compared=sorted(compared,key=lambda row:finite_number(row.get('percent')) is None)
        limit=3 if len(cursors)==2 else 5
        visible=balanced_rows([{**row,'Run':row.get('Comparison','Reference vs Candidate')} for row in compared],limit)
        def comparison_label(row):
            return ('A–B' if row.get('Scope')=='Active cursor interval' else 'Whole')+' · '+('Golden' if str(row.get('Comparison','')).startswith('Golden') else 'Reference')
        rows=[[comparison_label(row),row.get('name'),row.get('reference'),row.get('candidate'),row.get('delta'),row.get('percent'),row.get('unit')] for row in visible]
        grid=table(fig,['Scope / baseline','KPI','Baseline','Candidate','Delta','Deviation %','Unit'],rows,box=(.05,.11 if len(cursors)==2 else .20,.90,.10 if len(cursors)==2 else .17),widths=[.16,.25,.10,.10,.10,.15,.14],fontsize=7,max_lines=2)
        for row,record in enumerate(visible,1):
            color=record.get('accent')
            if isinstance(color,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',color):grid[row,5].set_facecolor(color);grid[row,5].get_text().set_color(INK)
    elif len(cursors)!=2:paragraph(fig,'Comparison not evaluated: Analysis mode. No candidate/reference pairing or tolerance result is implied.',y=.30,size=10)
    if comparison:
        paragraph(fig,f'Summary: {min(8,len(blocked))} of {len(blocked)} blocked/qualified results; {len(visible)} of {len(compared)} comparison rows. All results and reasons remain in companion evidence.',y=.075 if len(cursors)==2 else .105,size=8,line=.02,width=145)
    else:note_more(fig,min(8,len(blocked)),len(blocked),'blocked/qualified results',y=.105)
    done(fig)

    # 8. Grouping does not change the complete event log.
    fig=new('4. Grouped events — acquisition quality and appliance evidence')
    rows=[]
    for group in groups[:10]:
        affected=group['affected_time_union_s'];longest=group['longest_interval_s'];first=group['first_s'];last=group['last_s']
        rows.append([group['category'],short(group['name'],43),group['count'],value_text(group.get('effective_gap_threshold_s')),value_text(affected/60 if affected is not None else None),value_text(longest),f'{first/60:.5g} / {last/60:.5g}' if first is not None else 'Not timed',group['status']])
    table(fig,['Class','Rule / selected source','Count','Gap limit s','Affected union min','Longest s','First / last min','Evaluation'],rows,box=(.05,.38,.90,.47),widths=[.11,.25,.06,.08,.13,.09,.14,.14],fontsize=7)
    y=paragraph(fig,f'Complete event log: {len(tables["Fault & Anomaly Log"]):,} records in {len(groups)} groups. This page shows {min(10,len(groups))} groups. All original records, IDs, grouping keys and rules are retained in the companion evidence.',y=.33,size=9,line=.024)
    paragraph(fig,'Affected time uses the union of overlapping intervals within a group; it does not add overlapping alerts twice. Longest / first / last refer to original timed observations. Sampling gaps are acquisition evidence and do not establish appliance faults.',y=y-.01,size=9,line=.024)
    paragraph(fig,'Full-event appendix: '+('explicitly requested; follows this summary.' if plan['detailed_appendix'] else 'not selected. Increasing event count does not expand this summary.'),y=.13,size=8,line=.022);done(fig)

    # 9. Representative events retain linkable IDs and meaningful next actions.
    fig=new('4. Representative evidence and engineering actions')
    all_events=tables['Fault & Anomaly Log'].to_dict('records');by_id={row['event_id']:row for row in all_events}
    representatives=[]
    for group in groups:
        for id in group['representative_ids'][:1]:
            if id in by_id:representatives.append(by_id[id])
    representatives=representatives[:5]
    rows=[]
    for event in representatives:
        start=finite_number(event.get('start_s'));end=finite_number(event.get('end_s'))
        rows.append([event['event_id'],event.get('category',''),event.get('name',''),f'{start/60:.6g}–{end/60:.6g}' if start is not None and end is not None else 'Not timed',event.get('gap_threshold_s',event.get('duration_s','')),event.get('status','')])
    table(fig,['Event ID','Class','Rule','Interval min','Gap threshold / duration s','Evaluation'],rows,box=(.05,.52,.90,.31),widths=[.20,.13,.25,.16,.14,.12],fontsize=7)
    y=paragraph(fig,f'Representative events: {len(representatives)} of {len(all_events):,} log records; {max(0,len(all_events)-len(representatives)):,} individual records are omitted from this PDF view and preserved completely in CSV / Excel / JSON.',y=.46,size=9,line=.024)
    actions=list(dict.fromkeys(item.get('next_action','') for run in runs for item in run.get('readiness',[]) if item.get('next_action')))
    y=paragraph(fig,'Next engineering actions',y=y-.02,size=12,line=.03)
    for action in actions[:4]:y=paragraph(fig,'• '+action,y=y,size=9,line=.023)-.01
    paragraph(fig,'Conclusion: use observed samples and supported-time results within their stated limitations. A missing source is Not Evaluated; a configurable rule without supporting evidence is not an automatic Pass.',y=.14,size=9,line=.023);done(fig)

    # 10. Readable methods, basenames/hashes and shared evidence identity.
    fig=new('4. Traceability and calculation methods')
    y=paragraph(fig,f'Report ID {report_id} | App {info["Application version"]} | Profile {info["Profile"]} / schema {info["Profile schema"]} | Generated {info["Generated UTC"]}',y=.86,size=9,line=.025)
    for source in sources[:4]:
        y=paragraph(fig,PureWindowsPath(source['source']).name+'\nSHA-256 '+source['sha256'],y=y-.01,size=8,line=.022,width=145)
    calibration_ids=[record.get('id',key) for key,record in profile.get('calibrations',{}).items()]
    references='Calibration references: '+(', '.join(str(value) for value in calibration_ids) or 'Not configured')+' | Acceptance plan: '+str(info.get('Acceptance plan revision') or info.get('acceptance_plan_revision') or 'Not provided / not reviewed')
    y=paragraph(fig,short(references,280),y=y-.012,size=8,line=.022,width=145)
    methods=[
        'Energy: integrate verified active power over supported intervals; convert joules to the requested unit. Unsupported gaps are excluded.',
        'Actuator ON time: sum supported held-state intervals with finite integer state ≠ 0; state 0 is OFF. This rule applies only to confirmed actuator-state channels.',
        'Mean/RMS: elapsed-time weighted over supported intervals; peaks retain all finite original samples, including duplicate timestamps.',
        'Coverage: supported duration / requested recording or interval span. Gaps use the configured acquisition policy or the disclosed conservative fallback.',
        'Recorded span: last timestamp − first timestamp; it is not an inferred firmware program-cycle boundary.',
        'Acceptance: only explicitly configured test-plan limits apply; missing calibration, missing evidence and unconfigured limits remain unevaluated.'
    ]
    y=paragraph(fig,'Calculation methods',y=y-.02,size=12,line=.032)
    for method in methods:y=paragraph(fig,'• '+method,y=y,size=8,line=.022,width=145)-.006
    paragraph(fig,'Companion evidence: .evidence.xlsx (all nine sheets), .events.csv (every original event), .evidence.json (full configuration, recipes, mappings, calibration/acceptance definitions, group provenance and source paths). All carry this report ID. PDF metadata uses source basenames; full local provenance stays in the evidence.',y=.17,size=8,line=.022,width=145)
    done(fig)

    if plan['detailed_appendix']:
        for start in range(0,len(all_events),20):
            fig=new('Detailed event appendix — explicitly requested')
            rows=[]
            for event in all_events[start:start+20]:
                rows.append([event['event_id'],event.get('category',''),event.get('name',''),value_text((finite_number(event.get('start_s')) or 0)/60) if finite_number(event.get('start_s')) is not None else 'Not timed',event.get('duration_s',''),event.get('status','')])
            table(fig,['Event ID','Class','Rule','Start min','Duration s','Evaluation'],rows,box=(.05,.13,.90,.72),widths=[.22,.14,.29,.12,.11,.12],fontsize=7)
            done(fig)

    if len(figures)!=plan['expected_pages']:raise RuntimeError('Report page preview differs from generated pages')
    public_sources=[{'name':PureWindowsPath(s['source']).name,'sha256':s['sha256']} for s in sources]
    import json
    with PdfPages(path,metadata={'Title':str(info.get('Report title','Engineering report')),'Author':'Appliance Signal Studio','Subject':json.dumps({'report_id':report_id,'profile':info['Profile'],'sources':public_sources,'scope':scope})}) as pdf:
        for page,fig in enumerate(figures,1):
            check()
            # Footer sits below every axis/table, including dense evidence plots.
            fig.text(.05,.035,f'Appliance Signal Studio {info["Application version"]} | Report {report_id[:16]} | {scope}',fontsize=7,color=MUTED)
            fig.text(.95,.035,f'{page} / {len(figures)}',ha='right',fontsize=7,color=MUTED)
            pdf.savefig(fig);fig.clear()
    return plan

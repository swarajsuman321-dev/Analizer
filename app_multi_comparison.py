"""One explicit reference, multiple candidates, and confirmed actuator overlaps."""
from itertools import combinations
import json
from pathlib import Path
import numpy as np
import pandas as pd
from app_channel_identity import channel_label
from app_program_alignment import program_start,source_offset_minutes
from app_time_units import minute_factor
from app_operation_context import checkpoint


def compare_many(store,reference_id,candidate_ids,max_gap_seconds=None):
    from app_signal_comparison import compare_signals,_clean
    from app_engineering_trace import Trace
    from app_event_metrics import simultaneous_on
    ids=list(dict.fromkeys([reference_id,*candidate_ids]))
    if len(ids)<2:raise ValueError('Choose a reference and at least one other signal.')
    if len(ids)>32:raise ValueError('Compare up to 32 signals per report.')
    channels=[];origins={}
    for id in ids:
        c=store.channels.get(id)
        if c is None or c.coordinate_kind!='time':raise ValueError('Select available time-based signals.')
        origins[c.dataset_id]=program_start(store,c.dataset_id)
        channels.append(c)
    pairs=[]
    for id in ids[1:]:
        checkpoint('Comparing '+channel_label(store,id))
        pairs.append(compare_signals(store,reference_id,id,alignment='program',max_gap_seconds=max_gap_seconds,allow_same_recording=True))
    binary=[];overlaps=[];sources=[]
    for c in channels:
        origin=origins[c.dataset_id]['source_min']+source_offset_minutes(store,c)
        factor=minute_factor(c.coordinate_unit)
        trace=Trace(c,offset=-origin*60-c.shift*factor*60,max_gap_seconds=max_gap_seconds)
        sources.append({'channel_id':c.id,'name':channel_label(store,c),'dataset_id':c.dataset_id,
            'unit':c.unit,'coordinate_unit':c.coordinate_unit,'program_start':origins[c.dataset_id],
            'source_x':c.x,'source_y':c.y,'original_y':c.raw_y,'shift':c.shift,'masks':c.masks,
            'program_time_min':c.x*factor-origin,'kind':c.kind,
            'actuator_binary':bool(c.attributes.get('actuator_binary')),'max_gap_s':trace.max_gap})
        if c.attributes.get('actuator_binary'):
            if trace.max_gap<=0:continue
            states=[None if not np.isfinite(v) else int(v!=0) for v in trace.y]
            binary.append((c,trace,states))
    for (a,ta,sa),(b,tb,sb) in combinations(binary,2):
        checkpoint('Calculating confirmed actuator overlap')
        result=simultaneous_on(ta.t,sa,tb.t,sb,max_gap_s=ta.max_gap,max_gap_b_s=tb.max_gap)
        overlaps.append({'first_id':a.id,'second_id':b.id,'first':channel_label(store,a),'second':channel_label(store,b),
            **result,'first_gap_s':ta.max_gap,'second_gap_s':tb.max_gap,
            'meaning':'Simultaneous ON on program-aligned supported time; separate runs describe timing similarity, not physical simultaneous operation.'})
    return _clean({'schema':1,'reference_id':reference_id,'selected_ids':ids,'alignment':'confirmed program start',
        'pairs':pairs,'overlaps':overlaps,'sources':sources,
        'limitations':['Unknown/unconfirmed actuator meanings are excluded from overlap calculations.',
            'Every candidate is compared with the chosen reference; incompatible units remain explicitly blocked.',
            'No program start, acceptance limit, calibration or appliance phase is inferred.']})


def summary_rows(result):
    return [{'Candidate':pair.get('candidate',{}).get('name') or result['selected_ids'][index+1],
        'Status':pair['status'],'Reason':pair.get('reason',''),
        'RMSE':pair.get('metrics',{}).get('rmse'),'Unit':pair.get('metrics',{}).get('unit',''),
        'Compared min':pair.get('metrics',{}).get('compared_duration_min'),
        'Mean difference':pair.get('metrics',{}).get('mean_bias')} for index,pair in enumerate(result['pairs'])]


def export_multi_bundle(path,result,metadata=None):
    """Atomically publish PDF summary, full workbook and the same JSON result."""
    from app_engineering_reports import staged_report_bundle
    from app_reporting import literal_workbook_text
    from app_support import write_excel_frame
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_pdf import PdfPages
    from textwrap import fill
    path=Path(path);workbook=path.with_suffix('.xlsx');evidence=path.with_suffix('.evidence.json')
    rows=summary_rows(result);metadata=metadata or {}
    with staged_report_bundle([path,workbook,evidence]) as staged:
        with pd.ExcelWriter(staged[workbook],engine='openpyxl') as writer:
            write_excel_frame(writer,pd.DataFrame(rows),'Comparison summary')
            write_excel_frame(writer,pd.DataFrame(result['overlaps']),'Actuator overlap')
            for index,pair in enumerate(result['pairs'],1):
                checkpoint('Writing full comparison intervals')
                write_excel_frame(writer,pd.DataFrame(pair['differences']),f'Differences {index}')
                write_excel_frame(writer,pd.DataFrame(pair['events']),f'Events {index}')
            for index,source in enumerate(result['sources'],1):
                values={'source_coordinate':source['source_x'],'program_time_min':source['program_time_min'],'value':source['source_y']}
                if source['original_y'] is not None:values['original_value']=source['original_y']
                write_excel_frame(writer,pd.DataFrame(values),f'Source {index}')
            literal_workbook_text(writer.book)
        with PdfPages(staged[path]) as pdf:
            for offset in range(0,len(rows),14):
                fig=Figure(figsize=(11.7,8.3));fig.suptitle(str(metadata.get('Report title') or 'Program-aligned signal comparison'),wrap=True)
                ax=fig.add_axes([.06,.2,.88,.66]);ax.axis('off')
                columns=['Candidate','Status','RMSE','Unit','Compared min']
                cells=[[fill(str(row.get(key) if row.get(key) is not None else 'Not Available'),35) for key in columns] for row in rows[offset:offset+14]]
                table=ax.table(cellText=cells,colLabels=columns,loc='center',cellLoc='left');table.auto_set_font_size(False);table.set_fontsize(8);table.scale(1,2)
                fig.text(.06,.1,'Time zero: confirmed program start for each recording. Original samples, complete difference intervals, events and overlap evidence are in the companion workbook and JSON.',wrap=True,fontsize=9)
                pdf.savefig(fig)
            for offset in range(0,len(result['overlaps']),14):
                fig=Figure(figsize=(11.7,8.3));fig.suptitle('Confirmed actuator overlap')
                ax=fig.add_axes([.06,.2,.88,.66]);ax.axis('off')
                cells=[[fill(row['first'],28),fill(row['second'],28),f"{row['common_known_s']:.6g}",f"{row['simultaneous_on_s']:.6g}"] for row in result['overlaps'][offset:offset+14]]
                table=ax.table(cellText=cells,colLabels=['First signal','Second signal','Common known s','Both ON s'],loc='center',cellLoc='left');table.auto_set_font_size(False);table.set_fontsize(8);table.scale(1,2)
                fig.text(.06,.1,'Overlap excludes unknown states and unsupported gaps. Across different runs this measures timing similarity on program time, not physical simultaneous operation.',wrap=True,fontsize=9)
                pdf.savefig(fig)
            # Plot each chosen signal on its own units; never invent a common Y scale.
            for source in result['sources']:
                checkpoint('Rendering selected signal')
                fig=Figure(figsize=(11.7,8.3));ax=fig.subplots()
                x=np.asarray(source['program_time_min']);y=np.asarray(source['source_y'],dtype=float).copy()
                shifted=np.asarray(source['source_x'])+source['shift']
                for a,b in source['masks']:y[(shifted>=min(a,b))&(shifted<=max(a,b))]=np.nan
                gaps=np.flatnonzero(np.diff(x)*60>source['max_gap_s'])+1
                from app_fast_plot import EnvelopeCache
                # Render independent supported blocks, never a line across gaps.
                parts=np.split(np.arange(len(x)),gaps)
                for part in parts:
                    if not len(part):continue
                    px,py=EnvelopeCache(x[part],y[part]).visible(float(x[part[0]]),float(x[part[-1]]),max(100,6000//max(1,len(parts))))
                    ax.plot(px,py,linewidth=.8,drawstyle='steps-post' if source['actuator_binary'] else 'default')
                ax.set_title(fill(source['name'],90));ax.set_xlabel('Time from confirmed program start (min)');ax.set_ylabel(source['unit'] or 'Recorded value');ax.grid(alpha=.2)
                fig.text(.1,.02,fill(f"Program start: {source['program_start']['source_min']:.9g} source min. Evidence: {source['program_start']['evidence']}",140),fontsize=8)
                pdf.savefig(fig)
            details=[key+': '+str(metadata[key]) for key in ('Prepared by','Reviewed by','Test conditions','Observations','Conclusions','Recommended actions') if metadata.get(key)]
            reasons=[f"Candidate {index+1}: {pair['reason']}" for index,pair in enumerate(result['pairs']) if pair.get('reason')]
            lines=[]
            for text in [*result['limitations'],*reasons,*details]:lines.extend(fill(text,105).splitlines()+[''])
            for offset in range(0,len(lines),38):
                fig=Figure(figsize=(11.7,8.3));fig.suptitle('Evidence and limitations')
                fig.text(.06,.9,'\n'.join(lines[offset:offset+38]),va='top',fontsize=10);pdf.savefig(fig)
        from app_comparison_report import clean
        staged[evidence].write_text(json.dumps(clean({'result':result,'metadata':metadata}),indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8')
    return {'pdf':str(path),'workbook':str(workbook),'evidence':str(evidence)}

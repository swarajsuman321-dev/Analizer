"""Render completed parameter results without rerunning measurement algorithms.

The version-2 bundle is shared with the review UI. PDF is a readable narrative;
the streaming workbook and strict JSON retain every record, including unavailable
results, unmatched fields, native references and nested numerical evidence.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from app_comparison_report import _Pages, _flatten, clean, write_workbook
from app_operation_context import checkpoint
from app_parameter_contracts import strict_json
from app_report_appearance import include_cursor_lines
from app_version import VERSION, BUILD_DATE


TABLES = (('Runs', 'runs'), ('Parameter inventory', 'inventory'),
          ('Metrics', 'metrics'), ('Comparisons', 'comparisons'),
          ('Events', 'events'), ('Stages', 'stages'), ('Pairings', 'pairings'),
          ('Readiness', 'readiness'), ('Quality', 'quality'),
          ('Plot series', 'plot_series'))


def _display(value):
    """Show the computed value without introducing a second rounding policy."""
    value=clean(value)
    if value is None:return 'Not Available'
    if isinstance(value,(dict,list)):
        return json.dumps(value,ensure_ascii=False,sort_keys=True)
    return str(value)


def _first(record,*keys,default=None):
    return next((record[key] for key in keys if record.get(key) is not None),default)


def _frame(records):
    return pd.DataFrame(records) if records else pd.DataFrame(columns=['No records'])


def build_parameter_evidence(result_bundle, metadata=None):
    """Copy the computed bundle once; exports never change caller-owned records."""
    if not isinstance(result_bundle,dict) or result_bundle.get('schema_version')!=2:
        raise ValueError('Parameter reports require a version-2 result bundle')
    if result_bundle.get('kind') not in ('analysis','comparison'):
        raise ValueError('Parameter result kind must be analysis or comparison')
    for _,key in TABLES:
        if not isinstance(result_bundle.get(key,[]),list):
            raise ValueError('Parameter result '+key+' must be a list')
        if any(not isinstance(row,dict) for row in result_bundle.get(key,[])):
            raise ValueError('Parameter result '+key+' must contain records')
    # The analysis contract already makes unavailable values explicit. Reject a
    # broken producer instead of quietly converting NaN into an unexplained
    # null during export; otherwise the UI and delivered evidence would differ.
    evidence=strict_json(result_bundle)
    notes=clean(deepcopy(metadata or {}))
    report={'Report ID':notes.get('Report ID') or uuid4().hex,
            'Report title':notes.get('Report title') or 'Parameter '+evidence['kind']+' report',
            'Generated UTC':datetime.now(timezone.utc).isoformat(),
            'Application version':VERSION,'Build date':BUILD_DATE,
            'Result schema':2,'Metadata':notes,
            'Calculation policy':'Values, statuses and reasons are rendered from the completed result bundle; export does not recompute measurements.',
            'Plot policy':'Bounded display projections; measurements retain their full-resolution source evidence. Cursor overlays are an explicit export-only choice.'}
    evidence['report']=report
    tables={name:_frame(evidence.get(key,[])) for name,key in TABLES}
    tables['Report details']=pd.DataFrame(_flatten(report))
    tables['Provenance']=pd.DataFrame(_flatten(evidence.get('provenance',{})))
    # Keep extension records too. A newly registered analyser can add evidence
    # without requiring a report-specific table implementation.
    known={key for _,key in TABLES}|{'report','provenance'}
    tables['Result extensions']=pd.DataFrame(_flatten({key:value for key,value in evidence.items() if key not in known}))
    return evidence,tables


def _identity(record):
    return _display(_first(record,'label','name','source_name','original_name',
                           'field_name','metric_id','field_id','channel_id',
                           'instance','type','id',default='Record'))


def _reason(record):
    """Join supplied explanations; never infer a physical cause from a delta."""
    values=record.get('reasons') or []
    if not isinstance(values,list):values=[values]
    if record.get('reason'):values=[*values,record['reason']]
    return '; '.join(dict.fromkeys(map(str,values)))


def _status(record):
    return str(record.get('status') or 'Not specified').replace('_',' ')


def _acceptance(record):
    decision=record.get('acceptance') or record.get('acceptance_status') or {}
    return str(decision.get('status','not_evaluated') if isinstance(decision,dict) else decision).replace('_',' ')


def _remedy(record):
    """Actionable documentation guidance, never fabricated calibration values."""
    supplied=_first(record,'remedy','action','next_step')
    if supplied:return _display(supplied)
    return {
        'needs_mapping':'Review the field structure, semantic role and any required state dictionary.',
        'needs_scaling':'Confirm whether values are raw or engineering units and review the documented transform.',
        'needs_review':'Review the stated mapping, clock and evidence authority before using a physical interpretation.',
        'missing_input':'Map the required source input or leave this result explicitly unavailable.',
        'invalid':'Inspect the recorded source-quality and clock diagnostics; missing data must not be replaced with zero.',
        'unsupported':'Select a compatible registered capability or supply the documented acquisition/decoder information.',
        'not_comparable':'Review the explicit pairing, source meanings, units, scope and shared support.',
        'insufficient_data':'Choose a supported interval or provide sufficient native observations for this capability.',
        'error':'Inspect the analyser error and its input requirements, then retry after correcting the cause.',
        'cancelled':'Run the analysis again to complete the cancelled calculation.'
    }.get(record.get('status'),'Review the supplied reason and its linked source evidence.')


def _names(evidence):
    fields={_first(row,'id','field_id'):row for row in evidence.get('inventory',[])}
    runs={_first(row,'id','run_id','dataset_id'):row for row in evidence.get('runs',[])}
    def source(record):
        field=fields.get(record.get('field_id'),{})
        run=runs.get(record.get('run_id') or field.get('run_id'),{})
        return (_identity(run)+' / ' if run else '')+(_identity(field) if field else
                   str(record.get('field_id') or record.get('run_id') or 'Not specified'))
    return fields,runs,source


def _exact_table(pages,records,columns,widths):
    """Use the result's full number representation, including on PDF tables."""
    def value(item):
        rendered=_display(item)
        # Long structured algorithm outputs (for example a spectrum) belong in
        # the complete evidence rather than shrinking the narrative font or
        # expanding one table cell across hundreds of pages.
        if isinstance(item,(dict,list)) and len(rendered)>1200:
            return f'Structured result ({len(item)} entries); retained without truncation in workbook/JSON.'
        return rendered
    pages.table([{key:value(row.get(key)) for key in columns} for row in records],columns,widths)


def _details(pages,record,keys,*,label=None):
    values=[key.replace('_',' ')+': '+_display(record[key]) for key in keys if key in record]
    if values:pages.paragraph('; '.join(values),size=8,label=label)


def _record_list(pages,records,keys,*,empty):
    if not records:
        pages.paragraph(empty,size=8)
        return
    for row in records:
        checkpoint('Paginating parameter evidence')
        pages.ensure(.08)
        pages.paragraph(_identity(row),size=9)
        _details(pages,row,keys)


def _plot_modes(series):
    """Choose only coordinate arrays explicitly supplied in the result."""
    modes=[]
    if 'original_x' in series:modes.append(('Original acquisition coordinates',series['original_x']))
    if 'aligned_x' in series:modes.append(('Declared aligned coordinates',series['aligned_x']))
    if not modes and 'x' in series:
        modes.append((str(series.get('coordinate_label') or series.get('alignment_label') or
                          series.get('view') or 'Original coordinates'),series['x']))
    return modes


def _numeric_array(values):
    try:
        array=np.asarray(values,dtype=float)
    except (TypeError,ValueError):return None
    return array if array.ndim==1 else None


def _series_plots(pages,series,metadata,pairings=None):
    """Place comparable display projections together without joining samples.

    Grouping is presentation only: an explicit pairing and identical supplied
    units are required to overlay different fields. No names, interpolation or
    row positions are used to invent a pairing here.
    """
    from matplotlib.colors import is_color_like
    from app_presentation import CURSOR_COLORS
    pair_keys={}
    for index,pair in enumerate(pairings or []):
        if pair.get('confirmed') is True or pair.get('status')=='confirmed':
            for key in ('reference_field_id','candidate_field_id'):
                if pair.get(key):pair_keys[pair[key]]='pair-'+str(index)
    groups={}
    for index,record in enumerate(series):
        y=_numeric_array(_first(record,'y','value','values',default=[]))
        for mode,coordinates in _plot_modes(record):
            x=_numeric_array(coordinates)
            if x is None or y is None or not len(x) or len(x)!=len(y):continue
            identity=record.get('pairing_id') or pair_keys.get(record.get('field_id')) or record.get('field_id') or 'series-'+str(index)
            key=(identity,mode,record.get('unit'),_first(record,'x_unit','coordinate_unit'))
            groups.setdefault(key,[]).append((record,x,y))
    for number,((_,mode,unit,x_unit),records) in enumerate(groups.items()):
        checkpoint('Rendering parameter display projection')
        if number%2==0:
            pages.page('2. Graphs','Original and aligned evidence')
            pages.figure.text(.07,.075,
                'Display projections only; complete native measurements, indices, gaps and alignment remain in the evidence files.',
                fontsize=7,parse_math=False,wrap=True)
        axis=pages.figure.add_axes([.13,.55 if number%2==0 else .18,.77,.27])
        axis.set_title(mode,fontsize=9,loc='left',parse_math=False)
        palette=('#075985','#b45309','#7e22ce','#047857')
        for index,(record,x,y) in enumerate(records):
            state=record.get('structure') in ('binary','binary_state','enum','multistate','categorical')
            color=record.get('color')
            if not color or not is_color_like(color):color=palette[index%len(palette)]
            axis.plot(x,y,label=_identity(record),color=color,linewidth=.9,
                      drawstyle='steps-post' if state else 'default')
            if include_cursor_lines(metadata) and record.get('cursor_mode','dual')!='off':
                count=1 if record.get('cursor_mode')=='point' else 2
                for cursor_index,position in enumerate(record.get('cursors',[])[:count]):
                    if not isinstance(position,(float,int)) or not np.isfinite(position):continue
                    axis.axvline(position,color=CURSOR_COLORS[cursor_index],linestyle='--',linewidth=1.2)
                    axis.text(position,.98,('A','B')[cursor_index]+' '+_display(position),
                              color=CURSOR_COLORS[cursor_index],transform=axis.get_xaxis_transform(),
                              va='top',fontsize=8,parse_math=False)
                for marker in record.get('cursor_markers',[]):
                    cursor_index=marker.get('cursor_index')
                    if cursor_index not in range(count):continue
                    if marker.get('x') is not None and marker.get('y') is not None:
                        axis.scatter([marker['x']],[marker['y']],c=[CURSOR_COLORS[cursor_index]],s=35,zorder=6)
        axis.set_xlabel('Coordinate'+(' ('+str(x_unit)+')' if x_unit else ''),parse_math=False)
        axis.set_ylabel(str(unit or 'Source value'),parse_math=False)
        axis.grid(True,alpha=.18)
        axis.tick_params(labelsize=8)
        legend=axis.legend(fontsize=7,framealpha=.45)
        for item in legend.get_texts():item.set_parse_math(False)
    return len(groups)


def _span(record):
    for start,end,unit in (('start_s','end_s','s'),('onset_s','offset_s','s'),
                           ('start_min','end_min','min'),('onset','offset',None),
                           ('start','end',None)):
        if start in record and end in record:
            values=_numeric_array([record[start],record[end]])
            if values is not None and np.isfinite(values).all() and values[1]>=values[0]:
                return float(values[0]),float(values[1]),record.get('coordinate_unit') or unit or 'source coordinates'
    return None


def _timeline(pages,records,*,stages=False,inventory=None):
    import textwrap
    groups={};limit=2000
    field_names={_first(row,'id','field_id'):_identity(row) for row in inventory or []}
    for record in records:
        span=_span(record)
        if span is not None:groups.setdefault(span[2],[]).append((record,span))
    for unit,items in groups.items():
        # Raster lanes retain the field identity. Large event sets are a
        # declared bounded display projection, never a filter on evidence.
        lanes={}
        for record,span in items[:limit]:
            key=str(record.get('field_id') or record.get('run_id') or _identity(record))
            if stages:key=str(record.get('instance_id') or record.get('stage_id') or record.get('id') or key)
            lanes.setdefault(key,[]).append((record,span))
        lane_items=list(lanes.values())
        for offset in range(0,len(lane_items),18):
            pages.page('2. Graphs','Declared stage timeline' if stages else 'Observed event raster')
            axis=pages.figure.add_axes([.31,.19,.61,.64])
            batch=lane_items[offset:offset+18]
            for index,lane in enumerate(batch):
                spans=[(start,end-start) for _,(start,end,_) in lane]
                color=('#0e7490','#b45309','#7e22ce','#047857','#be123c')[index%5]
                axis.broken_barh(spans,(index-.3,.6),facecolors=color,alpha=.75)
                for record,(start,end,_) in lane:
                    if start==end:axis.plot([start],[index],'|',color=color)
                    censoring=record.get('censoring') or {}
                    if record.get('left_censored') or censoring.get('left'):
                        axis.plot([start],[index],'<',color=color,markersize=5)
                    if record.get('right_censored') or censoring.get('right'):
                        axis.plot([end],[index],'>',color=color,markersize=5)
            labels=['\n'.join(textwrap.wrap(field_names.get(lane[0][0].get('field_id'),_identity(lane[0][0])),28)) for lane in batch]
            axis.set_yticks(range(len(batch)),labels,fontsize=7)
            axis.set_xlabel('Coordinate ('+str(unit)+')',parse_math=False)
            for label in axis.get_yticklabels():label.set_parse_math(False)
            axis.grid(True,axis='x',alpha=.18)
            pages.figure.text(.07,.11,'Bars show supplied event/stage intervals; unshaded time does not imply OFF. Arrowheads mark censored boundaries. Unknown support and observation brackets remain explicit in the evidence.',
                              fontsize=7,parse_math=False,wrap=True)
            if len(items)>limit:
                pages.figure.text(.07,.075,f'Display shows the first {limit} of {len(items)} intervals; complete intervals remain in workbook/JSON.',
                                  fontsize=7,parse_math=False)


def _comparison_rows(evidence):
    """Render source values and declared delta semantics together for review."""
    rows=[];fields,runs,_=_names(evidence)
    def source_name(field_id):
        field=fields.get(field_id,{})
        run=runs.get(field.get('run_id'),{})
        return (_identity(run)+' / ' if run else '')+(_identity(field) if field else str(field_id or 'Not specified'))
    def measurement(value,unit):
        return _display(value)+(' '+str(unit) if unit and value is not None else '')
    for row in evidence.get('comparisons',[]):
        reference=row.get('reference_metric') or row.get('reference') or {}
        candidate=row.get('candidate_metric') or row.get('candidate') or {}
        if not isinstance(reference,dict):reference={}
        if not isinstance(candidate,dict):candidate={}
        delta=_first(row,'delta','signed_delta')
        relative=_first(row,'relative_delta_percent','relative_percent','percentage_point_delta')
        suffix=' pp' if row.get('percentage_point_delta') is not None else ' %'
        notes=_reason(row)
        if row.get('delta_semantics'):notes=(str(row['delta_semantics'])+'; '+notes).rstrip('; ')
        if row.get('comparison_type'):notes=(str(row['comparison_type']).replace('_',' ')+'; '+notes).rstrip('; ')
        if row.get('reference_field_id') or row.get('candidate_field_id'):
            notes+='; '+source_name(row.get('reference_field_id'))+' → '+source_name(row.get('candidate_field_id'))
        conversion=row.get('conversion') or {}
        if conversion.get('source_unit')!=conversion.get('target_unit') and 'candidate_in_reference_unit' in row:
            notes+='; Run B original '+_display(candidate.get('value'))+' '+str(candidate.get('unit') or '')+'; displayed after declared unit conversion'
        if row.get('relative_reason'):notes+='; '+str(row['relative_reason'])
        comparison_type=row.get('comparison_type')
        common_keys={
            'common_window_analog':(('mean_bias','Mean signed difference',row.get('unit')),
                ('mae','Mean absolute difference',row.get('unit')),
                ('rmse','Root mean square difference',row.get('unit')),
                ('max_absolute_difference','Largest absolute difference',row.get('unit')),
                ('max_difference_time_s','Time of largest difference','s'),
                ('absolute_difference_area','Absolute difference area',row.get('area_unit')),
                ('supported_duration_s','Shared supported duration','s'),
                ('coverage_fraction','Shared supported coverage','fraction')),
            'common_window_state':(('agreement_duration_s','State agreement duration','s'),
                ('mismatch_duration_s','State mismatch duration','s'),
                ('supported_duration_s','Shared supported duration','s'),
                ('agreement_fraction','State agreement','fraction'))}
        if comparison_type in common_keys:
            for key,label,unit in common_keys[comparison_type]:
                if key not in row:continue
                rows.append({'Measure':label,'Run A':'Shared window','Run B':'Shared window',
                    'Delta / error':row.get(key),'Unit':unit or '', 'Relative':'Not applicable',
                    'Evidence / comparability':_status(row)+'; '+notes,'Acceptance':_acceptance(row)})
            if any(key in row for key,_,_ in common_keys[comparison_type]):continue
        rows.append({'Measure':_first(row,'metric_id','comparison_id','type',default='Comparison'),
            'Run A':measurement(_first(row,'reference_value','baseline_value',default=reference.get('value',row.get('reference'))),reference.get('unit') or row.get('unit')),
            'Run B':measurement(_first(row,'candidate_in_reference_unit','candidate_value',default=candidate.get('value',row.get('candidate'))),
                                 row.get('unit') if row.get('candidate_in_reference_unit') is not None else candidate.get('unit') or row.get('unit')),
            'Delta / error':delta,'Unit':row.get('delta_unit') or row.get('unit') or reference.get('unit') or candidate.get('unit') or '',
            'Relative':_display(relative)+suffix if relative is not None else 'Not applicable',
            'Evidence / comparability':_status(row)+('; '+notes if notes else ''),
            'Acceptance':_acceptance(row),'_signed_change':delta})
    return rows


def _metric_rows(evidence):
    _,_,source=_names(evidence)
    def scope(row):
        value=row.get('scope') or {}
        return '; scope '+_display(value) if value.get('kind','run')!='run' else ''
    def sources(row):
        fields=(row.get('provenance') or {}).get('field_ids', (row.get('provenance') or {}).get('fields', []))
        if fields:
            return ' + '.join(source({'field_id':field_id,'run_id':row.get('run_id')}) for field_id in fields)
        return source(row)
    return [{'Source':sources(row),'Measure':str(row.get('label') or row.get('metric_id'))+scope(row),'Value':row.get('value'),
             'Unit':row.get('unit'),'Evidence / availability':_status(row)+'; '+str(row.get('evidence_basis') or '')+
               ('; '+_reason(row) if _reason(row) else '')+
               ('; supported '+_display(row['supported_duration_s'])+' s' if row.get('supported_duration_s') is not None else '')+
               (' / '+_display(row['coverage_denominator_s'])+' s scope' if row.get('coverage_denominator_s') is not None else ''),
             'Acceptance':_acceptance(row)}
            for row in evidence.get('metrics',[])]


def _event_summary(pages,records,label):
    """Show activity and uncertainty concisely; keep all native rows separately."""
    grouped={}
    for record in records:
        key=(record.get('run_id',''),record.get('field_id',''),record.get('type') or record.get('stage_type') or _identity(record))
        group=grouped.setdefault(key,{'Run':key[0],'Field':key[1],'Type':key[2],
                                  'Records':0,'Left censored':0,'Right censored':0})
        group['Records']+=1
        group['Left censored']+=bool(record.get('left_censored') or record.get('censoring',{}).get('left'))
        group['Right censored']+=bool(record.get('right_censored') or record.get('censoring',{}).get('right'))
    if grouped:
        _exact_table(pages,list(grouped.values()),
                     ['Run','Field','Type','Records','Left censored','Right censored'],[.15,.21,.28,.12,.12,.12])
        pages.paragraph('Record totals describe supplied evidence rows. They are not a replacement for a detector’s proven onset count. '
                        'Observation brackets, source indices, matched/unmatched decisions, suppressed candidates and stage assignments remain in the complete '+label+' table.',size=8)
        # Boundary evidence is useful in the main report, while a long pulse
        # sequence should not expand it into thousands of pages.
        detail=records[:12]
        for row in detail:
            pages.paragraph(_identity(row),size=8)
            _details(pages,row,('event_id','id','stage_id','instance_id','run_id','field_id','type','start_s','end_s',
                    'onset_s','offset_s','onset_bracket_s','offset_bracket_s','left_censored','right_censored',
                    'stage_assignments','match_status','rule','status','reasons'))
        if len(records)>len(detail):
            pages.paragraph(f'Boundary examples shown: {len(detail)} of {len(records)} records. The complete {label} table and JSON retain every record without truncation.',size=8)
    else:pages.paragraph('No '+label+' were supplied.',size=8)


def render_parameter_pdf(path,evidence,companion_names=None):
    """Paginate completed records, plots and availability without inferring roles."""
    from matplotlib.backends.backend_pdf import PdfPages
    report=evidence['report'];metadata=report['Metadata']
    with PdfPages(path,metadata={'Title':str(report['Report title']),
                                'Subject':'Version-2 parameter evidence',
                                'Keywords':'Report ID '+report['Report ID']}) as pdf:
        pages=_Pages(pdf,report)
        pages.page('1. Overview and review')
        pages.paragraph(report['Calculation policy'],size=8)
        pages.paragraph(f"{len(evidence.get('runs',[]))} runs; {len(evidence.get('inventory',[]))} inventoried source fields; "
                        f"{len(evidence.get('metrics',[]))} metric records; {len(evidence.get('comparisons',[]))} comparisons. "
                        'Unavailable results and unpaired fields remain in this report and its complete companions.',size=9)
        comparisons=_comparison_rows(evidence)
        changed=[row for row in comparisons if row.get('_signed_change') is not None and row['_signed_change']!=0]
        pages.paragraph('Differences are descriptive measurements, not automatic Pass/Fail conclusions. '
                        'Run A is the declared reference and signed changes are Run B minus Run A. '
                        'Relative changes are shown only when supplied by the comparison engine.',size=8,label='How to read this report')
        if changed:
            pages.paragraph('The following supplied differences are a concise starting point for your report. '
                            'The complete comparison table follows in section 3.',size=8,label='Observed changes')
            for row in changed[:6]:
                pages.paragraph(str(row['Measure'])+': Run A '+_display(row['Run A'])+', Run B '+_display(row['Run B'])+
                    '; signed change '+_display(row['Delta / error'])+' '+str(row['Unit'])+'. '+str(row['Evidence / comparability']),size=8)
            if len(changed)>6:pages.paragraph(f'{len(changed)} supplied comparisons have non-zero differences; six are outlined above in result order.',size=8)
        elif any('_signed_change' in row for row in comparisons):
            pages.paragraph('No supplied scalar comparison has a non-zero signed difference. Check comparability and common support before interpreting agreement.',size=8,label='Comparison review')
        _record_list(pages,evidence.get('runs',[]),
                     ('id','run_id','dataset_id','role','source','context','metadata','alignment','clock','warnings'),
                     empty='No run records were supplied.')
        pages.paragraph('Explicit pairings',label='Pairing review')
        _record_list(pages,evidence.get('pairings',[]),
                     ('pairing_id','reference','candidate','reference_field_id','candidate_field_id',
                      'status','reason','role','instance','unit','context_compatibility'),
                     empty='No pairings were supplied. Independent per-run results retain their source identities.')
        for key in ('Prepared by','Reviewed by','Test conditions'):
            pages.paragraph(metadata.get(key) or 'Not provided',size=8,label=key)

        if not _series_plots(pages,evidence.get('plot_series',[]),metadata,evidence.get('pairings')):
            pages.page('2. Graphs','Original and aligned evidence')
            pages.paragraph(report['Plot policy'],size=8)
            pages.paragraph('No usable display projection was supplied. This does not change the computed results or availability reasons.',size=8)
        _timeline(pages,evidence.get('events',[]),inventory=evidence.get('inventory'))
        _timeline(pages,evidence.get('stages',[]),stages=True,inventory=evidence.get('inventory'))

        pages.page('3. Measurements and comparisons','Computed metric records')
        metrics=_metric_rows(evidence)
        if metrics:
            _exact_table(pages,metrics[:120],['Source','Measure','Value','Unit','Evidence / availability','Acceptance'],[.2,.18,.14,.08,.27,.13])
            if len(metrics)>120:
                pages.paragraph(f'This overview shows 120 of {len(metrics)} completed metric records in result order. '
                                'Every metric, native extremum, scope, coverage denominator, provenance and uncertainty remains in the Metrics workbook/JSON table. '
                                'All unavailable results remain in the readiness appendix below.',size=8)
        else:pages.paragraph('No metric records were supplied. See readiness for required inputs and remedies.',size=8)
        pages.page('3. Measurements and comparisons','Signed differences and comparability')
        if comparisons:
            _exact_table(pages,comparisons,['Measure','Run A','Run B','Delta / error','Unit','Relative','Evidence / comparability','Acceptance'],[.17,.11,.11,.11,.06,.1,.22,.12])
            pages.paragraph('Full-run scalar differences and common-window pointwise errors are distinct result records. '
                            'Source metric definitions, matching decisions, conversions, shared support and unavailable reasons remain attached to each comparison in the complete evidence.',size=8)
        else:pages.paragraph('No comparison records were supplied. No pairing or baseline was inferred.',size=8)
        for label,key in (('Event evidence','events'),('Stage evidence','stages')):
            pages.page('3. Measurements and comparisons',label)
            _event_summary(pages,evidence.get(key,[]),key)

        pages.page('4. Quality, inventory and readiness','Complete source-field inventory')
        paired={pair[key] for pair in evidence.get('pairings',[]) for key in ('reference_field_id','candidate_field_id')
                if pair.get(key) and (pair.get('confirmed') is True or pair.get('status')=='confirmed')}
        inventory=[{'Parameter':_identity(row),'Run':row.get('run_id') or row.get('dataset_id'),
            'Group / source':str(row.get('group') or '')+' / '+str(row.get('source_key') or row.get('path') or ''),
            'Type / unit':str(row.get('dtype') or row.get('structure') or '')+' / '+str(row.get('unit') or 'Not supplied')+
              ('; mapped '+str(row['mapping'].get('structure') or 'unknown')+' / '+str(row['mapping'].get('role') or 'role unreviewed') if isinstance(row.get('mapping'),dict) else ''),
            'Samples':_first(row,'native_samples','sample_count'),'Disposition':str(row.get('disposition') or row.get('status') or 'Not specified')+
              ('; '+('paired' if _first(row,'id','field_id') in paired else 'unpaired') if evidence['kind']=='comparison' else '')}
            for row in evidence.get('inventory',[])]
        if inventory:_exact_table(pages,inventory,['Parameter','Run','Group / source','Type / unit','Samples','Disposition'],[.25,.13,.2,.18,.09,.15])
        else:pages.paragraph('No inventory records were supplied.',size=8)
        pages.paragraph('Every supplied field is inventoried, including metadata, categorical, empty, invalid and unsupported structures. '
                        'Original identity, reviewed mapping/encoding, source properties and quality remain in the complete Parameter inventory table.',size=8)
        pages.page('4. Quality, inventory and readiness','Unavailable results and practical remedies')
        for row in evidence.get('readiness',[]):
            pages.paragraph('; '.join(str(k).replace('_',' ')+': '+_display(v) for k,v in row.items()),size=8)
            pages.paragraph(_remedy(row),size=8,label='Practical next step')
        if not evidence.get('readiness'):pages.paragraph('No readiness records were supplied. This is not an acceptance statement.',size=8)
        unavailable={}
        for row in evidence.get('metrics',[]):
            if row.get('status') in ('computed','partial'):continue
            key=(row.get('run_id'),row.get('field_id'),_status(row),_reason(row))
            unavailable.setdefault(key,[]).append(str(row.get('metric_id')))
        for (run,field,status,reason),metric_ids in unavailable.items():
            pages.paragraph('Run '+str(run or 'unspecified')+' / field '+str(field or 'unspecified')+
                '; '+status+': '+reason+'; affected metrics: '+', '.join(metric_ids),size=8)
            pages.paragraph(_remedy({'status':status.replace(' ','_')}),size=8,label='Practical next step')
        pages.paragraph('Result availability, evidence basis and engineering acceptance are separate decisions. No acceptance limit is inferred by this report.',size=8)
        pages.page('4. Quality, inventory and readiness','Quality and provenance')
        for row in evidence.get('quality',[]):
            pages.paragraph('; '.join(str(k).replace('_',' ')+': '+_display(v) for k,v in row.items()),size=8)
        for row in _flatten(evidence.get('provenance',{})):
            pages.paragraph(str(row['Field'])+': '+_display(row['Value']),size=8)
        for key in ('Observations','Conclusions','Recommended actions'):
            pages.paragraph(metadata.get(key) or 'Not provided',label='User-provided '+key.lower())
        for name in companion_names or []:pages.paragraph(name,label='Complete evidence file')
        pages.save()
        return pages.page_number


def export_parameter_report(path,result_bundle,*,metadata=None):
    """Atomically deliver readable PDF and complete workbook/JSON evidence."""
    from app_engineering_reports import staged_report_bundle
    path=Path(path)
    if path.suffix.lower() not in ('.pdf','.xlsx','.json'):
        raise ValueError('Choose PDF, Excel or JSON for parameter results')
    if not path.parent.is_dir():raise ValueError('Choose an existing writable output folder')
    evidence,tables=build_parameter_evidence(result_bundle,metadata)
    pdf=path if path.suffix.lower()=='.pdf' else None
    workbook=path if path.suffix.lower()=='.xlsx' else path.with_suffix('.xlsx') if pdf else None
    json_path=path if path.suffix.lower()=='.json' else path.with_suffix('.evidence.json')
    destinations=[item for item in (pdf,workbook,json_path) if item is not None]
    with staged_report_bundle(destinations) as staged:
        if workbook is not None:
            checkpoint('Writing complete parameter workbook')
            write_workbook(staged[workbook],None,None,evidence,tables,base_frames={})
        if pdf is not None:
            evidence['pdf_pages']=render_parameter_pdf(staged[pdf],evidence,
                                                      [workbook.name,json_path.name])
        evidence['companions']=[item.name for item in destinations]
        checkpoint('Writing complete parameter JSON evidence')
        staged[json_path].write_text(json.dumps(clean(evidence),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        checkpoint('Committing parameter report evidence')
    return {'pdf':str(pdf) if pdf else None,'workbook':str(workbook) if workbook else None,
            'evidence':str(json_path),'report_id':evidence['report']['Report ID']}

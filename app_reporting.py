"""Direct exports of the visible workspace and its active cursor intervals."""
from pathlib import Path
import numpy as np
import pandas as pd
from app_presentation import match_color,cursor_sample
from app_signal_processing import IntervalSummary
from app_time_units import presentation_statistics


def match_scorecard(score):
    """Express verified relative differences as a bounded similarity percentage.

    Match = max(0, 100 - abs(relative difference percent)). Missing, unverified
    and zero-denominator metrics retain no percentage and receive no accent.
    The engineering engine's signed differences and original values are retained.
    """
    result=score.drop(columns=['status'],errors='ignore').copy()
    difference=pd.to_numeric(score.get('percent',pd.Series(index=score.index,dtype=float)).astype(str).str.replace('%','',regex=False),errors='coerce')
    verified=score.get('status',pd.Series('',index=score.index)).isin(['GREEN','YELLOW','RED'])
    result['match_percent']=(100-difference.abs()).clip(lower=0,upper=100).where(verified & np.isfinite(difference))
    return result


def interval_tables(store,workspace):
    from app_plot_workspace import LAYOUTS
    rows,cols=LAYOUTS[workspace['layout']];frames=[];summary=[]
    for pane_number,view in enumerate(workspace['panes'][:rows*cols],1):
        a,b=view.get('cursors',[0,0]);low,high=sorted((a,b))
        for channel_id in view['ids']:
            c=store.channels[channel_id];x,y=c.values();mask=(x>=low)&(x<=high)
            va=cursor_sample(c,a,view.get('snap',True));vb=cursor_sample(c,b,view.get('snap',True))
            metadata={'pane':pane_number,'channel_id':c.id,'channel':c.name,'unit':c.unit,'coordinate_unit':c.coordinate_unit,
                      'cursor_A_X':a,'cursor_B_X':b,'A':va,'B':vb,**presentation_statistics(c,IntervalSummary(c).query(a,b))}
            if workspace.get('statistics_scope')=='Whole recording' and len(x):
                whole=IntervalSummary(c).query(float(x[0]),float(x[-1]))
                metadata.update({key:whole[key] for key in ('Min','Max','Mean')});metadata['min_max_mean_scope']='Whole recording'
            for index,lock in enumerate(view.get('cursor_locks',[])):
                if lock and lock.get('channel') in store.channels:metadata[f'cursor_{("A","B")[index]}_locked_channel']=store.channels[lock['channel']].name
            metadata['ΔY']=vb-va
            metadata['match_percent']=c.attributes.get('match_percent',np.nan) if match_color(c.attributes.get('match_percent')) else np.nan
            if c.attributes.get('actuator_binary'):
                from app_actuators import state_text
                metadata.update(value_interpretation='actuator',A_state=state_text(va),B_state=state_text(vb))
                scope=IntervalSummary(c).query(float(x[0]),float(x[-1])) if workspace.get('statistics_scope')=='Whole recording' and len(x) else IntervalSummary(c).query(a,b)
                metadata['ON_time']=scope['Mean']*scope['Coverage']*scope['ΔX'];metadata['ON_fraction']=scope['Mean'];metadata['known_time']=scope['Coverage']*scope['ΔX']
            summary.append(metadata)
            frames.append(pd.DataFrame({'pane':pane_number,'channel_id':c.id,'channel':c.name,'coordinate':x[mask],
                                        'value':y[mask],'unit':c.unit,'coordinate_unit':c.coordinate_unit,
                                        'cursor_A_X':a,'cursor_B_X':b,'match_percent':metadata['match_percent'],**({'original_value':c.raw_y[mask]} if c.raw_y is not None else {})}))
    if not summary:raise ValueError('Check at least one channel before exporting')
    return pd.concat(frames,ignore_index=True),pd.DataFrame(summary)


def export_report(path,store,workspace,scorecard=None,*,title='Signal analysis report'):
    """One save dialog, no configuration wizard; never interpolate exported samples."""
    from app_workspace_io import render_report
    path=Path(path);data,summary=interval_tables(store,workspace)
    if path.suffix.lower()=='.csv':data.to_csv(path,index=False)
    elif path.suffix.lower()=='.xlsx':
        from openpyxl.styles import PatternFill
        with pd.ExcelWriter(path,engine='openpyxl') as writer:
            data.to_excel(writer,sheet_name='Active interval',index=False)
            summary.to_excel(writer,sheet_name='Cursor summary',index=False)
            if scorecard is not None:scorecard.to_excel(writer,sheet_name='Comparison',index=False)
            for sheet in writer.book:
                sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
                headers=[cell.value for cell in sheet[1]]
                if 'match_percent' in headers:
                    column=headers.index('match_percent')+1
                    for row in range(2,sheet.max_row+1):
                        cell=sheet.cell(row,column);color=match_color(cell.value)
                        if color:cell.fill=PatternFill('solid',fgColor=color.lstrip('#'));cell.number_format='0.0"%"'
    elif path.suffix.lower() in ('.pdf','.png'):
        render_report(path,store,workspace,title=title,scorecard=scorecard)
    else:raise ValueError('Choose PDF, Excel, CSV or PNG')
    return data,summary

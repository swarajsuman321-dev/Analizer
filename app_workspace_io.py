"""Portable JSON/NPZ workspaces and independent presentation rendering."""
from dataclasses import asdict
from pathlib import Path
import json
import math
import os
import tempfile
import numpy as np
import pandas as pd
from app_channel_store import ChannelStore,Channel,Dataset
from app_fast_plot import EnvelopeCache
from app_signal_processing import IntervalSummary


def encode_cell(value):
    if value is None or value is pd.NA or value is pd.NaT:return {'type':'null'}
    if isinstance(value,(float,np.floating)):return {'type':'float','value':float(value).hex()}
    if isinstance(value,(bool,np.bool_)):return {'type':'bool','value':bool(value)}
    if isinstance(value,(int,np.integer)):return {'type':'int','value':int(value)}
    if isinstance(value,pd.Timestamp):return {'type':'timestamp','value':value.isoformat()}
    return {'type':'string','value':str(value)}


def decode_cell(value):
    kind=value['type'];v=value.get('value')
    return {'null':lambda:None,'float':lambda:float.fromhex(v),'bool':lambda:v,'int':lambda:v,
            'timestamp':lambda:pd.Timestamp(v),'string':lambda:v}[kind]()


def save_workspace(path,store,views,ui=None):
    path=Path(path).with_suffix('.json');arrays={};channels=[];datasets=[]
    for c in store.channels.values():
        metadata=asdict(c);metadata.pop('x');metadata.pop('y');metadata.pop('raw_y');channels.append(metadata)
        arrays[c.id+'_x']=c.x;arrays[c.id+'_y']=c.y
        if c.raw_y is not None:arrays[c.id+'_raw_y']=c.raw_y
    for ds in store.datasets.values():
        frame=ds.frame
        datasets.append({'id':ds.id,'name':ds.name,'source':ds.source,'columns':[str(c) for c in frame.columns],
                         'dtypes':[str(t) for t in frame.dtypes],
                         'index':[encode_cell(v) for v in frame.index], 'index_name':frame.index.name,
                         'attributes':frame.attrs,
                         'cells':[[encode_cell(v) for v in row] for row in frame.itertuples(index=False,name=None)]})
    # A generation-named companion keeps an interrupted save from corrupting the previous snapshot.
    from uuid import uuid4
    companion=path.with_name(path.stem+'.'+uuid4().hex[:12]+'.npz')
    np.savez_compressed(companion,**arrays)
    record={'version':1,'arrays':companion.name,'channels':channels,'datasets':datasets,'views':views,'ui':ui or {}}
    fd,temp=tempfile.mkstemp(dir=path.parent,prefix=path.name,suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:json.dump(record,stream,ensure_ascii=False,allow_nan=False)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return path


def load_workspace(path):
    path=Path(path)
    from app_config_migration import read_configuration
    record=read_configuration(path)
    if record.get('version')!=1:raise ValueError('Unsupported workspace version')
    companion=Path(record['arrays'])
    if companion.name!=str(companion):raise ValueError('Workspace arrays must be an adjacent NPZ file')
    store=ChannelStore()
    with np.load(path.parent/companion,allow_pickle=False) as arrays:
        for metadata in record['channels']:
            c=Channel(x=arrays[metadata['id']+'_x'],y=arrays[metadata['id']+'_y'],raw_y=arrays[metadata['id']+'_raw_y'] if metadata['id']+'_raw_y' in arrays else None,**metadata)
            store.add(c)
    for d in record['datasets']:
        frame=pd.DataFrame([[decode_cell(v) for v in row] for row in d['cells']],columns=d['columns'])
        for column,dtype in zip(frame.columns,d['dtypes']):
            frame[column]=frame[column].astype(dtype)
        frame.index=[decode_cell(v) for v in d['index']]
        frame.index.name=d.get('index_name');frame.attrs=d.get('attributes',{})
        store.datasets[d['id']]=Dataset(d['name'],frame,d['source'],d['id'])
    for c in store.channels.values():
        if c.dataset_id and c.dataset_id not in store.datasets:raise ValueError('Channel references a missing dataset')
    views=record['views'];ui=record.get('ui',{})
    if not isinstance(views,list) or not isinstance(ui,dict):raise ValueError('Invalid workspace layout/settings')
    from app_plot_workspace import LAYOUTS
    for view in views:
        if not isinstance(view,dict) or view.get('layout') not in LAYOUTS or not isinstance(view.get('panes'),list):raise ValueError('Unsupported workspace layout')
        for pane in view['panes']:
            if not isinstance(pane,dict) or not isinstance(pane.get('ids',[]),list) or any(id not in store.channels for id in pane.get('ids',[])):raise ValueError('Layout references an unknown channel')
            if not isinstance(pane.get('bindings',{}),dict):raise ValueError('Invalid axis bindings')
            for key,shape in [('range',(2,2)),('cursors',(2,))]:
                if key in pane:
                    values=np.asarray(pane[key],dtype=float)
                    if values.shape!=shape or not np.isfinite(values).all():raise ValueError('Invalid saved '+key)
            locks=pane.get('cursor_locks',[None,None])
            if not isinstance(locks,list) or len(locks)!=2 or any(lock is not None and (not isinstance(lock,dict) or lock.get('channel') not in store.channels or not isinstance(lock.get('index'),int)) for lock in locks):raise ValueError('Invalid saved cursor locks')
    return store,views,ui


def export_processed(path,channels):
    frames=[]
    for c in channels:
        x,y=c.values()
        frame=pd.DataFrame({'channel_id':c.id,'channel':c.name,'coordinate':x,'value':y,'unit':c.unit,
                            'coordinate_unit':c.coordinate_unit,'coordinate_kind':c.coordinate_kind})
        if 'metric_labels' in c.attributes:
            frame['metric']=c.attributes['metric_labels'];frame['unit']=c.attributes['metric_units']
        frames.append(frame)
    if not frames:raise ValueError('Select channels to export')
    data=pd.concat(frames,ignore_index=True)
    path=Path(path)
    if path.suffix.lower()=='.xlsx':data.to_excel(path,index=False)
    else:data.to_csv(path,index=False)
    return data


def render_report(path,store,workspace,title='Signal analysis report',scorecard=None):
    """Render the visible axes, cursor positions and interval summary from view state."""
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from app_plot_workspace import LAYOUTS
    from app_trace_colors import channel_colors
    colors=channel_colors(store)
    from app_presentation import CURSOR_COLORS,match_color
    from app_reporting import interval_tables
    path=Path(path);rows,cols=LAYOUTS[workspace['layout']]
    _,summary=interval_tables(store,workspace)
    statistics=summary.to_dict('records')
    table_height=max(1.5,.27*(len(summary)+2))
    score_height=max(1.2,.27*(len(scorecard)+2)) if scorecard is not None and len(scorecard) else 0
    fig=Figure(figsize=(14,max(5,rows*3)+table_height+score_height),layout='constrained');FigureCanvasAgg(fig)
    grid=fig.add_gridspec(rows+1+bool(score_height),cols,height_ratios=[3]*rows+[table_height]+([score_height] if score_height else []))
    fig.suptitle(title+('\nMin / Max / Average: whole recording · A / B and Δ: cursor interval' if workspace.get('statistics_scope')=='Whole recording' else ''));fig.set_facecolor('white')
    for index,view in enumerate(workspace['panes'][:rows*cols]):
        axis=fig.add_subplot(grid[index//cols,index%cols]);axes={};ranges=view.get('range')
        units=list(dict.fromkeys(view.get('bindings',{}).get(id,store.channels[id].unit) for id in view['ids']))
        for id in view['ids']:
            c=store.channels[id];key=view.get('bindings',{}).get(id,c.unit);style=c.attributes.get('plot_style',{});color=colors[id]
            if key not in axes:
                current=axis if not axes else axis.twinx()
                if style.get('side')=='left' and axes:
                    current.spines['right'].set_visible(False);current.spines['left'].set_visible(True);current.spines['left'].set_position(('outward',48*len(axes)))
                    current.yaxis.tick_left();current.yaxis.set_label_position('left')
                elif style.get('side')=='right' and current is axis:
                    current.yaxis.tick_right();current.yaxis.set_label_position('right');current.spines['left'].set_visible(False)
                elif axes:current.spines['right'].set_position(('outward',48*(len(axes)-1)))
                if key=='Actuators':current.set_yticks([0,1],['OFF','ON'])
                current.set_ylabel(key or 'Value',color=color);current.tick_params(axis='y',colors=color);axes[key]=current
                bounds=view.get('axes',{}).get(key)
                if bounds:current.set_ylim(*bounds)
                elif current is axis and ranges:current.set_ylim(*ranges[1])
            x,y=c.values();left,right=ranges[0] if ranges else ((x[0],x[-1]) if len(x) else (0,1))
            dx,dy=EnvelopeCache(x,y).visible(left,right,8000)
            if view.get('normalized'):
                finite=y[np.isfinite(y)];low,high=(float(finite.min()),float(finite.max())) if len(finite) else (0.,1.)
                dy=np.where(np.isfinite(dy),(dy-low)/(high-low) if high>low else .5,np.nan)+view['ids'].index(id)
            axes[key].plot(dx,dy,label=c.name,color=color,drawstyle='steps-post' if c.attributes.get('actuator_binary') else 'default',linewidth=float(style.get('width',.8)),linestyle={'solid':'-','dash':'--','dot':':','dashdot':'-.'}.get(style.get('style'),'-'))
            for cursor_index,lock in enumerate(view.get('cursor_locks',[])):
                if not lock or lock.get('channel')!=id or not len(x) or view.get('cursor_mode')=='off':continue
                if cursor_index==1 and view.get('cursor_mode','dual')!='dual':continue
                sample=int(np.clip(lock['index'],0,len(x)-1));value=y[sample]
                if not np.isfinite(value):continue
                if view.get('normalized'):value=((value-low)/(high-low) if high>low else .5)+view['ids'].index(id)
                axes[key].scatter([x[sample]],[value],s=45,c=[CURSOR_COLORS[cursor_index]],edgecolors='#182033',zorder=6)
            axis.set_xlabel(f'{c.coordinate_kind} ({c.coordinate_unit})');axis.set_xlim(left,right)
        if not view['ids']:axis.text(.5,.5,'No channels selected',ha='center',va='center',transform=axis.transAxes)
        for name,position,color in zip(('A','B'),view.get('cursors',[]),CURSOR_COLORS):
            axis.axvline(position,color=color,linestyle='--',linewidth=1.4)
            axis.text(position,.98,f'{name} {position:.6g}',color=color,backgroundcolor='#182033',transform=axis.get_xaxis_transform(),va='top',fontsize=8)
        for annotation in view.get('annotations',[]):
            if annotation['kind']=='ROI':axis.axvspan(annotation['start'],annotation['end'],alpha=.15)
            elif annotation['kind']=='Threshold':axes.get(annotation.get('axis'),axis).axhline(annotation['start'],color='purple',linestyle=':')
            else:
                axis.axvline(annotation['start'],color='purple',linestyle=':')
                if annotation.get('text'):axis.text(annotation['start'],.88,annotation['text'],transform=axis.get_xaxis_transform(),color='purple',fontsize=8,va='top',bbox={'facecolor':'white','edgecolor':'none','alpha':.85})
        handles=[];labels=[]
        for current in axes.values():
            h,l=current.get_legend_handles_labels();handles.extend(h);labels.extend(l)
        if handles and view.get('show_legends',True):axis.legend(handles,labels,fontsize=7,loc='upper left')
        if view.get('show_grid',True):axis.grid(True,alpha=.15)
        else:axis.grid(False)
    def draw_table(target,frame,columns):
        target.axis('off')
        def display(value):
            if isinstance(value,(float,np.floating)):return f'{value:.5g}' if np.isfinite(value) else '—'
            return str(value)
        from app_actuators import state_text
        def cell_text(row,column):
            if row.get('value_interpretation')=='actuator':
                if column in ('A','B','Min','Max'):return state_text(row[column])
                if column=='Mean':return f"{100*row[column]:.4g}% ON" if np.isfinite(row[column]) else 'Unknown'
                if column=='ΔY':return state_text(row['A'])+' → '+state_text(row['B'])
            return display(row[column])
        values=[[cell_text(row,c) for c in columns] for _,row in frame.iterrows()]
        table=target.table(cellText=values,colLabels=[c.replace('_',' ') for c in columns],loc='center',cellLoc='left')
        table.auto_set_font_size(False);table.set_fontsize(7);table.scale(1,1.3)
        for (row,col),cell in table.get_celld().items():
            cell.set_edgecolor('#dde3eb')
            if row==0:cell.set_facecolor('#edf1f7')
            if columns[col] in ('A','B'):
                cell.set_facecolor('#182033');cell.get_text().set_color(CURSOR_COLORS[columns[col]=='B'])
            if row and columns[col]=='match_percent':
                color=match_color(frame.iloc[row-1]['match_percent'])
                if color:cell.set_facecolor(color)
    draw_table(fig.add_subplot(grid[rows,:]),summary,['channel','unit','A','B','ΔX','ΔY','Min','Max','Mean','match_percent'])
    if score_height:
        columns=[c for c in ('parameter','sim_val','raw_val','delta','percent','match_percent') if c in scorecard]
        draw_table(fig.add_subplot(grid[rows+1,:]),scorecard,columns)
    if path.suffix.lower() in ('.html','.md'):
        image=path.with_suffix('.png');fig.savefig(image,dpi=160)
        if path.suffix.lower()=='.html':
            import html
            content=f'<meta charset="utf-8"><h1>{html.escape(title)}</h1><img src="{html.escape(image.name)}" alt="Signal plots">'+summary.to_html(index=False)
        else:content=f'# {title}\n\n![Signal plots]({image.name})\n\n'+summary.to_csv(index=False)
        path.write_text(content,encoding='utf-8')
    else:fig.savefig(path,dpi=300)
    fig.clear()
    return statistics

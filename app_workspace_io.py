"""Portable JSON/NPZ workspaces and independent presentation rendering."""
from pathlib import Path
import json
import math
import os
import tempfile
import base64
from copy import deepcopy
from dataclasses import fields
import numpy as np
import pandas as pd
from app_channel_store import ChannelStore,Channel,Dataset
from app_fast_plot import EnvelopeCache
from app_signal_processing import IntervalSummary


def encode_cell(value):
    if value is None or value is pd.NA or value is pd.NaT:return {'type':'null'}
    if isinstance(value,(float,np.floating)):return {'type':'float','value':float(value).hex()}
    if isinstance(value,(bool,np.bool_)):return {'type':'bool','value':bool(value)}
    if isinstance(value,(pd.Timedelta,np.timedelta64)):
        return {'type':'timedelta','value':int(pd.Timedelta(value).value)}
    if isinstance(value,(int,np.integer)):return {'type':'int','value':int(value)}
    if isinstance(value,pd.Timestamp):return {'type':'timestamp','value':value.isoformat()}
    if isinstance(value,np.datetime64):return {'type':'datetime64','value':str(value),'dtype':value.dtype.str}
    if isinstance(value,(complex,np.complexfloating)):
        return {'type':'complex','real':float(value.real).hex(),'imag':float(value.imag).hex()}
    if isinstance(value,(bytes,bytearray,memoryview)):return {'type':'bytes','value':base64.b64encode(bytes(value)).decode('ascii')}
    if isinstance(value,np.void):return encode_cell(np.asarray(value))
    if isinstance(value,np.ndarray):
        if value.dtype.hasobject:
            return {'type':'object_array','shape':list(value.shape),'value':[encode_cell(v) for v in value.flat]}
        return {'type':'array','dtype':np.lib.format.dtype_to_descr(value.dtype),'shape':list(value.shape),
                'value':base64.b64encode(np.ascontiguousarray(value).tobytes()).decode('ascii')}
    if isinstance(value,dict):return {'type':'mapping','value':[[encode_cell(k),encode_cell(v)] for k,v in value.items()]}
    if isinstance(value,(list,tuple)):
        return {'type':'tuple' if isinstance(value,tuple) else 'list','value':[encode_cell(v) for v in value]}
    return {'type':'string','value':str(value)}


def decode_cell(value):
    kind=value['type'];v=value.get('value')
    if kind=='array':
        dtype=value['dtype']
        def descriptor(entries):
            if not isinstance(entries,list):return entries
            return [tuple([tuple(entry[0]) if isinstance(entry[0],list) else entry[0],descriptor(entry[1])]+
                          ([tuple(entry[2])] if len(entry)>2 else [])) for entry in entries]
        dtype=descriptor(dtype)
        dtype=np.dtype(dtype)
        if dtype.hasobject:raise ValueError('Object bytes are not permitted in a workspace')
        return np.frombuffer(base64.b64decode(v,validate=True),dtype=dtype).copy().reshape(value['shape'])
    if kind=='object_array':
        out=np.empty(len(v),dtype=object)
        for index,cell in enumerate(v):out[index]=decode_cell(cell)
        return out.reshape(value['shape'])
    if kind=='complex':return complex(float.fromhex(value['real']),float.fromhex(value['imag']))
    if kind=='datetime64':return np.datetime64(v).astype(value['dtype'])
    if kind=='timedelta':return pd.Timedelta(v,unit='ns')
    if kind=='bytes':return base64.b64decode(v,validate=True)
    if kind=='mapping':return {decode_cell(k):decode_cell(cell) for k,cell in v}
    if kind in ('list','tuple'):
        decoded=[decode_cell(cell) for cell in v]
        return tuple(decoded) if kind=='tuple' else decoded
    return {'null':lambda:None,'float':lambda:float.fromhex(v),'bool':lambda:v,'int':lambda:v,
            'timestamp':lambda:pd.Timestamp(v),'string':lambda:v}[kind]()


def _encode_metadata(value,arrays,prefix):
    """Keep large numeric reader arrays in the safe NPZ companion."""
    if isinstance(value,np.ndarray) and not value.dtype.hasobject:
        key=prefix+'_'+str(len(arrays));arrays[key]=value
        return {'type':'npz_reference','value':key}
    if isinstance(value,dict):
        return {'type':'mapping','value':[[encode_cell(k),_encode_metadata(v,arrays,prefix)] for k,v in value.items()]}
    if isinstance(value,(list,tuple)):
        return {'type':'tuple' if isinstance(value,tuple) else 'list','value':[_encode_metadata(v,arrays,prefix) for v in value]}
    return encode_cell(value)


def _decode_metadata(value,arrays):
    kind=value['type']
    if kind=='npz_reference':return np.array(arrays[value['value']],copy=True)
    if kind=='mapping':return {decode_cell(k):_decode_metadata(v,arrays) for k,v in value['value']}
    if kind in ('list','tuple'):
        decoded=[_decode_metadata(v,arrays) for v in value['value']]
        return tuple(decoded) if kind=='tuple' else decoded
    return decode_cell(value)


def save_workspace(path,store,views,ui=None):
    from app_operation_context import checkpoint,mark_committed
    path=Path(path).with_suffix('.json');arrays={};channels=[];datasets=[]
    checkpoint('Preparing workspace channels')
    for c in store.channels.values():
        metadata={f.name:deepcopy(getattr(c,f.name)) for f in fields(c) if f.name not in ('x','y','raw_y')};channels.append(metadata)
        metadata['attributes']=_encode_metadata(metadata['attributes'],arrays,c.id+'_attributes')
        arrays[c.id+'_x']=c.x;arrays[c.id+'_y']=c.y
        if c.raw_y is not None:arrays[c.id+'_raw_y']=c.raw_y
    for number,ds in enumerate(store.datasets.values(),1):
        frame=ds.frame
        cells=[]
        for row_number,row in enumerate(frame.itertuples(index=False,name=None)):
            if row_number%4096==0:checkpoint(f'Saving {ds.name} ({number}/{len(store.datasets)})',row_number,len(frame))
            cells.append([encode_cell(v) for v in row])
        datasets.append({'id':ds.id,'name':ds.name,'source':ds.source,'columns':[str(c) for c in frame.columns],
                         'dtypes':[str(t) for t in frame.dtypes],
                         'index':[encode_cell(v) for v in frame.index], 'index_name':frame.index.name,
                         'attributes':_encode_metadata(frame.attrs,arrays,ds.id+'_attributes'),
                         'column_labels':[encode_cell(c) for c in frame.columns],
                         'categorical_columns':{str(i):{'categories':[encode_cell(v) for v in frame.iloc[:,i].cat.categories],
                                                        'ordered':bool(frame.iloc[:,i].cat.ordered)}
                                                for i in range(len(frame.columns)) if isinstance(frame.iloc[:,i].dtype,pd.CategoricalDtype)},
                         'cells':cells})
    # A generation-named companion keeps an interrupted save from corrupting the previous snapshot.
    from uuid import uuid4
    companion=path.with_name(path.stem+'.'+uuid4().hex[:12]+'.npz')
    temp=None;committed=False
    try:
        checkpoint('Compressing waveform arrays');np.savez_compressed(companion,**arrays)
        checkpoint('Writing source-preserving workspace')
        record={'version':1,'source_encoding':'typed-v1','arrays':companion.name,'channels':channels,'datasets':datasets,'views':views,'ui':ui or {}}
        fd,temp=tempfile.mkstemp(dir=path.parent,prefix=path.name,suffix='.tmp')
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            for index,chunk in enumerate(json.JSONEncoder(ensure_ascii=False,allow_nan=False).iterencode(record)):
                if index%16384==0:checkpoint()
                stream.write(chunk)
        checkpoint('Committing workspace');os.replace(temp,path);committed=True;mark_committed()
    finally:
        if temp and os.path.exists(temp):os.unlink(temp)
        if not committed:companion.unlink(missing_ok=True)
    return path


def load_workspace(path):
    from app_operation_context import checkpoint
    path=Path(path)
    from app_config_migration import read_configuration
    checkpoint('Reading workspace metadata');record=read_configuration(path);checkpoint('Restoring waveform arrays')
    if record.get('version')!=1:raise ValueError('Unsupported workspace version')
    companion=Path(record['arrays'])
    if companion.name!=str(companion):raise ValueError('Workspace arrays must be an adjacent NPZ file')
    store=ChannelStore()
    with np.load(path.parent/companion,allow_pickle=False) as arrays:
        for metadata in record['channels']:
            checkpoint()
            if record.get('source_encoding')=='typed-v1':metadata={**metadata,'attributes':_decode_metadata(metadata['attributes'],arrays)}
            c=Channel(x=arrays[metadata['id']+'_x'],y=arrays[metadata['id']+'_y'],raw_y=arrays[metadata['id']+'_raw_y'] if metadata['id']+'_raw_y' in arrays else None,**metadata)
            store.add(c)
        # Reader raw arrays can live in the companion independently of plot
        # arrays. Restore them before closing the no-pickle NPZ context.
        for d in record['datasets']:
            if record.get('source_encoding')=='typed-v1':d['attributes']=_decode_metadata(d.get('attributes',{'type':'mapping','value':[]}),arrays)
    for d in record['datasets']:
        cells=[]
        for number,row in enumerate(d['cells']):
            if number%4096==0:checkpoint('Restoring '+d['name'],number,len(d['cells']))
            cells.append([decode_cell(v) for v in row])
        labels=[decode_cell(c) for c in d['column_labels']] if 'column_labels' in d else d['columns']
        frame=pd.DataFrame(cells,columns=labels)
        for position,dtype in enumerate(d['dtypes']):
            # Assign by position so duplicate source names remain distinct.
            categorical=d.get('categorical_columns',{}).get(str(position))
            if categorical:
                series=frame.iloc[:,position].astype(pd.CategoricalDtype([decode_cell(v) for v in categorical['categories']],ordered=categorical['ordered']))
            else:series=frame.iloc[:,position].astype(dtype)
            frame.isetitem(position,series)
        frame.index=[decode_cell(v) for v in d['index']]
        frame.index.name=d.get('index_name');frame.attrs=d.get('attributes',{})
        store.datasets[d['id']]=Dataset(d['name'],frame,d['source'],d['id'])
    for c in store.channels.values():
        checkpoint()
        if c.dataset_id and c.dataset_id not in store.datasets:raise ValueError('Channel references a missing dataset')
    views=record['views'];ui=record.get('ui',{})
    if not isinstance(views,list) or not isinstance(ui,dict):raise ValueError('Invalid workspace layout/settings')
    from app_plot_workspace import LAYOUTS,graph_positions
    for view in views:
        if not isinstance(view,dict) or view.get('layout') not in LAYOUTS or not isinstance(view.get('panes'),list):raise ValueError('Unsupported workspace layout')
        positions=graph_positions(view)
        if view.get('layout')=='Custom' and len(view['panes'])<len(positions):raise ValueError('Workspace is missing a visible graph')
        for pane in view['panes']:
            if not isinstance(pane,dict) or not isinstance(pane.get('ids',[]),list) or any(id not in store.channels for id in pane.get('ids',[])):raise ValueError('Layout references an unknown channel')
            if not isinstance(pane.get('bindings',{}),dict):raise ValueError('Invalid axis bindings')
            for key,shape in [('range',(2,2)),('cursors',(2,))]:
                if key in pane:
                    values=np.asarray(pane[key],dtype=float)
                    if values.shape!=shape or not np.isfinite(values).all():raise ValueError('Invalid saved '+key)
            locks=pane.get('cursor_locks',[None,None])
            if not isinstance(locks,list) or len(locks)!=2 or any(lock is not None and (not isinstance(lock,dict) or lock.get('channel') not in store.channels or not isinstance(lock.get('index'),int)) for lock in locks):raise ValueError('Invalid saved cursor locks')
    checkpoint('Workspace validated');return store,views,ui


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


def render_report(path,store,workspace,title='Signal analysis report',scorecard=None,metadata=None):
    """Render workspace plots and unchanged cursor statistics with optional overlays."""
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from app_plot_workspace import layout_shape,workspace_panes
    from app_trace_colors import channel_colors
    from app_channel_identity import channel_label
    from app_operation_context import checkpoint
    from app_report_appearance import include_cursor_lines
    show_cursors=include_cursor_lines(metadata)
    colors=channel_colors(store)
    from app_presentation import CURSOR_COLORS,match_color
    from app_reporting import interval_tables
    path=Path(path);rows,cols=layout_shape(workspace)
    _,summary=interval_tables(store,workspace)
    statistics=summary.to_dict('records')
    table_height=max(1.5,.27*(len(summary)+2))
    score_height=max(1.2,.27*(len(scorecard)+2)) if scorecard is not None and len(scorecard) else 0
    fig=Figure(figsize=(14,max(5,rows*3)+table_height+score_height),layout='constrained');FigureCanvasAgg(fig)
    grid=fig.add_gridspec(rows+1+bool(score_height),cols,height_ratios=[3]*rows+[table_height]+([score_height] if score_height else []))
    fig.suptitle(title+('\nMin / Max / Average: whole recording · A / B and Δ: cursor interval' if workspace.get('statistics_scope')=='Whole recording' else ''));fig.set_facecolor('white')
    shown=workspace_panes(workspace)
    for index,((row,column),view) in enumerate(shown):
        checkpoint('Rendering graph '+str(index+1),index,len(shown))
        axis=fig.add_subplot(grid[row,column]);axes={};ranges=view.get('range')
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
            axes[key].plot(dx,dy,label=channel_label(store,c),color=color,drawstyle='steps-post' if c.attributes.get('actuator_binary') else 'default',linewidth=float(style.get('width',.8)),linestyle={'solid':'-','dash':'--','dot':':','dashdot':'-.'}.get(style.get('style'),'-'))
            for cursor_index,lock in enumerate(view.get('cursor_locks',[])):
                if not show_cursors or not lock or lock.get('channel')!=id or not len(x) or view.get('cursor_mode')=='off':continue
                if cursor_index==1 and view.get('cursor_mode','dual')!='dual':continue
                sample=int(np.clip(lock['index'],0,len(x)-1));value=y[sample]
                if not np.isfinite(value):continue
                if view.get('normalized'):value=((value-low)/(high-low) if high>low else .5)+view['ids'].index(id)
                axes[key].scatter([x[sample]],[value],s=45,c=[CURSOR_COLORS[cursor_index]],edgecolors='#182033',zorder=6)
            axis.set_xlabel(f'{c.coordinate_kind} ({c.coordinate_unit})');axis.set_xlim(left,right)
        if not view['ids']:axis.text(.5,.5,'No channels selected',ha='center',va='center',transform=axis.transAxes)
        cursor_count=0 if not show_cursors or view.get('cursor_mode')=='off' else (1 if view.get('cursor_mode')=='point' else 2)
        for name,position,color in zip(('A','B'),view.get('cursors',[])[:cursor_count],CURSOR_COLORS):
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

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
        metadata=asdict(c);metadata.pop('x');metadata.pop('y');channels.append(metadata)
        arrays[c.id+'_x']=c.x;arrays[c.id+'_y']=c.y
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
    record=json.loads(path.read_text(encoding='utf-8'))
    if record.get('version')!=1:raise ValueError('Unsupported workspace version')
    companion=Path(record['arrays'])
    if companion.name!=str(companion):raise ValueError('Workspace arrays must be an adjacent NPZ file')
    store=ChannelStore()
    with np.load(path.parent/companion,allow_pickle=False) as arrays:
        for metadata in record['channels']:
            c=Channel(x=arrays[metadata['id']+'_x'],y=arrays[metadata['id']+'_y'],**metadata)
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
    return store,record['views'],record.get('ui',{})


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


def render_report(path,store,workspace,title='Signal workbench'):
    """Render plots from domain/view state rather than screenshotting widgets."""
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from app_plot_workspace import COLORS,LAYOUTS
    path=Path(path);rows,cols=LAYOUTS[workspace['layout']]
    fig=Figure(figsize=(12, max(5,rows*3)),layout='constrained');FigureCanvasAgg(fig)
    fig.suptitle(title);statistics=[]
    for index,view in enumerate(workspace['panes'][:rows*cols]):
        axis=fig.add_subplot(rows,cols,index+1);axes={};ranges=view.get('range')
        for number,id in enumerate(view['ids']):
            c=store.channels[id];key=view.get('bindings',{}).get(id,c.unit)
            if key not in axes:
                current=axis if not axes else axis.twinx()
                if axes:current.spines['right'].set_position(('outward',40*(len(axes)-1)))
                current.set_ylabel(key or 'Value');axes[key]=current
                bounds=view.get('axes',{}).get(key)
                if bounds:current.set_ylim(*bounds)
                elif current is axis and ranges:current.set_ylim(*ranges[1])
            x,y=c.values();left,right=ranges[0] if ranges else (x[0],x[-1])
            dx,dy=EnvelopeCache(x,y).visible(left,right,4000)
            axes[key].plot(dx,dy,label=c.name,color=COLORS[number%len(COLORS)],linewidth=.8)
            axis.set_xlabel(f'{c.coordinate_kind} ({c.coordinate_unit})');axis.set_xlim(left,right)
            if len(view.get('cursors',[]))==2:
                a,b=view['cursors'];stats=IntervalSummary(c).query(a,b)
                statistics.append({'channel':c.name,'unit':c.unit,'coordinate_unit':c.coordinate_unit,**stats})
        for position in view.get('cursors',[]):axis.axvline(position,color='gray',linestyle='--',linewidth=.7)
        for annotation in view.get('annotations',[]):
            if annotation['kind']=='ROI':axis.axvspan(annotation['start'],annotation['end'],alpha=.15)
            elif annotation['kind']=='Threshold':axes.get(annotation.get('axis'),axis).axhline(annotation['start'],color='purple',linestyle=':')
            else:axis.axvline(annotation['start'],color='purple',linestyle=':')
        for current in axes.values():current.legend(fontsize=6,loc='upper left')
        axis.grid(alpha=.2)
    if path.suffix.lower() in ('.html','.md'):
        image=path.with_suffix('.png');fig.savefig(image,dpi=140)
        table=pd.DataFrame(statistics)
        if path.suffix.lower()=='.html':
            import html
            content=f'<meta charset="utf-8"><h1>{html.escape(title)}</h1><img src="{html.escape(image.name)}" alt="Signal plots">'+table.to_html(index=False)
        else:
            content=f'# {title}\n\n![Signal plots]({image.name})\n\n'+table.to_csv(index=False)
        path.write_text(content,encoding='utf-8')
    else:fig.savefig(path,dpi=160)
    return statistics

"""Normalize time projections to minutes while preserving original source tables."""
from dataclasses import replace
import numpy as np

MINUTE_FACTORS={'ns':1/60e9,'us':1/60e6,'µs':1/60e6,'ms':1/60000,'s':1/60,'sec':1/60,'second':1/60,'seconds':1/60,
                'min':1.,'minute':1.,'minutes':1.,'h':60.,'hr':60.,'hour':60.,'hours':60.}


def minute_factor(unit):
    key=str(unit).strip().lower()
    if key not in MINUTE_FACTORS:raise ValueError(f'Unknown time unit: {unit}; choose seconds, minutes or hours when importing')
    return MINUTE_FACTORS[key]


def normalize_minutes(store,views=None):
    """Convert channel projections and optional old view state; never edit datasets."""
    factors={};value_factors={}
    for id,c in list(store.channels.items()):
        factor=minute_factor(c.coordinate_unit) if c.coordinate_kind=='time' else 1.
        value_factor=MINUTE_FACTORS.get(c.unit.strip().lower(),1.)
        is_time_value=c.unit.strip().lower() in MINUTE_FACTORS
        factors[id]=factor;value_factors[id]=value_factor
        if (c.coordinate_kind!='time' or c.coordinate_unit=='min') and (not is_time_value or c.unit=='min'):continue
        attrs=dict(c.attributes)
        if c.coordinate_kind=='time':attrs.setdefault('original_coordinate_unit',c.coordinate_unit)
        if is_time_value:
            attrs.setdefault('original_value_unit',c.unit)
            for name in ('warning_min','warning_max','fault_min','fault_max'):
                if name in attrs:attrs[name]=float(attrs[name])*value_factor
            if 'plot_style' in attrs:
                style=dict(attrs['plot_style'])
                for name in ('ymin','ymax'):
                    if style.get(name) not in ('',None):style[name]=float(style[name])*value_factor
                attrs['plot_style']=style
        store.channels[id]=replace(c,x=c.x*factor,y=c.y*value_factor,shift=c.shift*factor,
                                   masks=[(a*factor,b*factor) for a,b in c.masks],coordinate_unit='min' if c.coordinate_kind=='time' else c.coordinate_unit,
                                   unit='min' if is_time_value else c.unit,attributes=attrs,revision=c.revision+1)
    for workspace in views or []:
        for pane in workspace.get('panes',[]):
            ids=pane.get('ids',[]);factor=next((factors[id] for id in ids if id in factors),1.)
            primary=next((value_factors[id] for id in ids if id in value_factors),1.)
            if 'range' in pane:pane['range']=[[v*factor for v in pane['range'][0]],[v*primary for v in pane['range'][1]]]
            if 'cursors' in pane:pane['cursors']=[v*factor for v in pane['cursors']]
            for annotation in pane.get('annotations',[]):
                axis=annotation.get('axis')
                scale=MINUTE_FACTORS.get(str(axis).strip().lower(),primary) if annotation.get('kind')=='Threshold' else factor
                if str(axis).strip().lower() in MINUTE_FACTORS:annotation['axis']='min'
                for name in ('start','end'):
                    if name in annotation:annotation[name]*=scale
            for field in ('bindings','normalization_bindings'):
                if field in pane:pane[field]={id:('min' if unit.strip().lower() in MINUTE_FACTORS else unit) for id,unit in pane[field].items()}
            pane['axes']={('min' if unit.strip().lower() in MINUTE_FACTORS else unit):[v*MINUTE_FACTORS.get(unit.strip().lower(),1.) for v in bounds] for unit,bounds in pane.get('axes',{}).items()}
    return store


def presentation_statistics(channel,stats):
    """The numerical engine integrates in SI; the minute-based UI labels its units."""
    result=dict(stats)
    if channel.coordinate_kind=='time' and channel.coordinate_unit=='min':
        result['Slope']*=60
        result['Integral']/=60
    return result

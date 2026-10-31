"""Explicit, source-wide program origins; recording start is never a fallback."""
from copy import deepcopy
import math

from app_time_units import minute_factor


def source_span(store, dataset_id):
    channels=[c for c in store.channels.values() if c.dataset_id==dataset_id
              and c.coordinate_kind=='time' and len(c.x) and not c.attributes.get('engineering_projection')]
    originals=[c for c in channels if not c.parents and not c.recipe]
    channels=originals or channels
    if not channels:raise ValueError('This recording has no time-based samples.')
    return (min(float(c.x[0])*minute_factor(c.coordinate_unit) for c in channels),
            max(float(c.x[-1])*minute_factor(c.coordinate_unit) for c in channels))


def program_start(store, dataset_id):
    dataset=store.datasets.get(dataset_id)
    record=dataset.frame.attrs.get('program_start') if dataset is not None else None
    if not isinstance(record,dict) or record.get('confirmed') is not True:
        raise ValueError('Confirm program start for each recording using Align Program Starts; recording start is not assumed.')
    point=record.get('source_min')
    if isinstance(point,bool) or not isinstance(point,(int,float)) or not math.isfinite(point):
        raise ValueError('Saved program start must be a finite source-time coordinate.')
    if not isinstance(record.get('evidence'),str) or not record['evidence'].strip():
        raise ValueError('Program start needs a recorded signal/rule or a user confirmation note.')
    low,high=source_span(store,dataset_id)
    if not low<=point<=high:raise ValueError('Saved program start is outside this recording.')
    return deepcopy(record)


def source_offset_minutes(store,channel):
    """Undo an engineering projection's existing origin before rebasing a run."""
    if not channel.attributes.get('engineering_projection'):return 0.
    import numpy as np
    if len(channel.parents)!=1 or channel.parents[0] not in store.channels:
        raise ValueError('Regenerate the engineering projection from its source before program alignment.')
    parent=store.channels[channel.parents[0]]
    if len(channel.x)!=len(parent.x) or not len(channel.x):
        raise ValueError('Engineering projection has no exact source-clock mapping; regenerate it before alignment.')
    offsets=channel.x*minute_factor(channel.coordinate_unit)-parent.x*minute_factor(parent.coordinate_unit)
    if not np.allclose(offsets,offsets[0],rtol=0,atol=1e-8):
        raise ValueError('Engineering projection clock is not a source-wide offset; regenerate it before alignment.')
    return float(offsets[0])


def align_program_start(store, dataset_id, source_min, evidence):
    """Apply one origin to every time channel without changing original arrays."""
    if dataset_id not in store.datasets:raise ValueError('Choose a loaded recording.')
    if isinstance(source_min,bool):raise ValueError('Program start must be a finite time coordinate.')
    source_min=float(source_min)
    low,high=source_span(store,dataset_id)
    if not math.isfinite(source_min) or not low<=source_min<=high:
        raise ValueError('Program start must lie within the recording source-time span.')
    if not isinstance(evidence,str) or not evidence.strip():
        raise ValueError('Describe the signal/rule or observation confirming program start.')
    record={'source_min':source_min,'confirmed':True,'method':'user_confirmed',
            'evidence':evidence.strip(),'coordinate':'original source time in minutes'}
    # Validate every unit and prepare the entire update before changing state.
    changes=[]
    for channel in store.channels.values():
        if channel.dataset_id!=dataset_id or channel.coordinate_kind!='time':continue
        shift=(-source_min-source_offset_minutes(store,channel))/minute_factor(channel.coordinate_unit)
        delta=shift-channel.shift
        attributes={**channel.attributes,'program_start':deepcopy(record)}
        changes.append((channel.id,shift,[(a+delta,b+delta) for a,b in channel.masks],attributes))
    store.datasets[dataset_id].frame.attrs['program_start']=deepcopy(record)
    with store.batch():
        for id,shift,masks,attributes in changes:
            store.update(id,shift=shift,masks=masks,attributes=attributes)
    return record

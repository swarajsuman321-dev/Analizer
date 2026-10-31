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
        shift=-source_min/minute_factor(channel.coordinate_unit)
        delta=shift-channel.shift
        attributes={**channel.attributes,'program_start':deepcopy(record)}
        changes.append((channel.id,shift,[(a+delta,b+delta) for a,b in channel.masks],attributes))
    store.datasets[dataset_id].frame.attrs['program_start']=deepcopy(record)
    with store.batch():
        for id,shift,masks,attributes in changes:
            store.update(id,shift=shift,masks=masks,attributes=attributes)
    return record

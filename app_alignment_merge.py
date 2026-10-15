"""Refresh an alignment by source/column identity without duplicating channels."""
from dataclasses import replace
from pathlib import Path
import os
import numpy as np


def merge_alignment(target,incoming):
    key=next((c.attributes.get('alignment_key') for c in incoming.channels.values()),None)
    if not key:raise ValueError('Alignment result has no source identity')
    datasets={};remap={};added=[];updated=0
    source=next((d.source for d in incoming.datasets.values() if d.frame.attrs.get('studio_sheet')=='Synchronized_Series'),'')
    def identity_of(c):return (os.path.normcase(str(Path(c.source).resolve())) if c.source else '',c.attributes.get('data_column',c.name))
    matching={d.id:d for d in target.datasets.values() if d.frame.attrs.get('alignment_key')==key or (not d.frame.attrs.get('alignment_key') and d.source==source and d.frame.attrs.get('studio_sheet')=='Synchronized_Series')}
    with target.batch():
        for ds in incoming.datasets.values():
            sheet=ds.frame.attrs.get('studio_sheet')
            old=next((d for d in target.datasets.values() if d.frame.attrs.get('alignment_key')==key and d.frame.attrs.get('studio_sheet')==sheet),None)
            if old is None and sheet=='Synchronized_Series':old=next(iter(matching.values()),None)
            id=old.id if old else ds.id;datasets[ds.id]=id;target.datasets[id]=replace(ds,id=id)
        index={}
        for c in list(target.channels.values()):
            if not c.parents and (c.attributes.get('alignment_key')==key or (c.dataset_id in matching and c.group=='Aligned')):
                identity=identity_of(c)
                if identity in index:
                    remap[c.id]=index[identity].id;target.delete([c.id])
                else:index[identity]=c
        for c in incoming.channels.values():
            identity=identity_of(c);old=index.get(identity)
            if old:
                attrs={**old.attributes,**c.attributes}
                if not (np.array_equal(old.x,c.x,equal_nan=True) and np.array_equal(old.y,c.y,equal_nan=True) and old.attributes==attrs and old.dataset_id==datasets[c.dataset_id]):
                    target.update(old.id,x=c.x,y=c.y,kind=c.kind,coordinate_kind=c.coordinate_kind,coordinate_unit=c.coordinate_unit,dataset_id=datasets[c.dataset_id],attributes=attrs,unit=old.unit or c.unit);updated+=1
            else:
                target.add(replace(c,dataset_id=datasets[c.dataset_id]));added.append(c.id)
        # Tables and KPIs can change even if sampled curves do not.
        if incoming.channels and not added and not updated and index:target.changed(next(iter(index.values())).id)
    return added,updated,remap

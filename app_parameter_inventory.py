"""Complete source inventories independent of immutable numeric plot projections.

Coordinates returned by :func:`source_field` are seconds only for a usable
declared/candidate timebase. Sample-domain fields keep sample coordinates.
Original order, invalid timestamps, quality companions and reader raw values
are retained even when a plotting channel has sorted/filtered its projection.
"""
from copy import deepcopy
from collections.abc import Mapping
import hashlib
import json
import re
import numpy as np
import pandas as pd


def _immutable(values):
    out=np.array(values,copy=True)
    if out.dtype.kind=='O':
        # Object cells can themselves contain mutable vectors or dictionaries.
        out=np.empty(len(values),dtype=object)
        for i,value in enumerate(values):out[i]=_freeze(value)
    out.setflags(write=False)
    return out


def _freeze(value):
    if isinstance(value,np.ndarray):return _immutable(value)
    if isinstance(value,(list,tuple)):return tuple(_freeze(v) for v in value)
    if isinstance(value,Mapping):
        from types import MappingProxyType
        return MappingProxyType({k:_freeze(v) for k,v in value.items()})
    if isinstance(value,np.void):return value.copy()
    if isinstance(value,bytearray):return bytes(value)
    return value


def field_id(run_id,source_key):
    return 'field-'+hashlib.sha256((str(run_id)+'\0'+str(source_key)).encode()).hexdigest()[:24]


def _numeric(values):
    if np.asarray(values).dtype.kind=='c':return np.full(len(values),np.nan)
    try:return pd.to_numeric(pd.Series(values),errors='coerce').to_numpy(dtype=float)
    except (TypeError,ValueError):return np.full(len(values),np.nan)


def clock_quality(coordinates,policy='unknown'):
    x=np.asarray(coordinates,dtype=float);finite=np.isfinite(x);d=np.diff(x)
    adjacent=finite[:-1]&finite[1:];positive=d[adjacent&(d>0)]
    median=float(np.median(positive)) if len(positive) else None
    # A gap is an acquisition-policy observation, never a physical fault.
    gaps=int(np.sum(positive>median*5)) if median and policy in ('sampled','held_state') else 0
    return {'invalid_timestamps':int((~finite).sum()),'duplicates':int(np.sum(adjacent&(d==0))),
            'backwards':int(np.sum(adjacent&(d<0))),'resets':int(np.sum(adjacent&(d<0))),
            'reset_interpretation':'candidate backward jumps; no automatic unwrap',
            'gaps':gaps,'gap_policy':'interval > 5 × median positive interval' if policy in ('sampled','held_state') else 'not inferred for event/unknown acquisition',
            'median_interval':median,'jitter':float(np.std(positive)) if len(positive)>1 else None}


def _source_positions(frame,spec):
    if spec.get('source_type')=='metadata':return np.arange(1,dtype=np.int64)
    positions=spec.get('source_row_positions')
    if positions is not None:return np.asarray(positions,dtype=np.int64)
    return np.arange(min(int(spec.get('length',len(frame))),len(frame)),dtype=np.int64)


def _clock(frame,spec,positions):
    n=len(positions);clock=deepcopy(spec.get('clock_description',{}));key=spec.get('clock')
    policy=clock.get('acquisition_policy',frame.attrs.get('reader_options',{}).get('acquisition_policy','unknown'))
    if not key or key not in frame.columns or clock.get('kind')=='sample':
        x=np.arange(n,dtype=float)
        clock={**clock,'kind':'sample','domain':'sample','unit':'sample','origin':None,
               'trust':'unavailable','source_key':None,'acquisition_policy':policy}
    else:
        source=frame[key].iloc[positions];unit=spec.get('coordinate_unit','s')
        components=spec.get('clock_components',[])
        if len(components)==2 and all(k in frame for k in components):
            from app_data import timestamp_text
            source=timestamp_text(frame[components[0]].iloc[positions]).str.cat(timestamp_text(frame[components[1]].iloc[positions]),sep=' ')
        if unit=='datetime' or pd.api.types.is_datetime64_any_dtype(source):
            from app_data import _parse_timestamp_column
            parsed=_parse_timestamp_column(source,key)
            parsed=pd.to_datetime(parsed,errors='coerce',utc=True)
            origin=frame.attrs.get('time_origin') or clock.get('origin')
            if origin is None:
                valid=parsed.dropna();origin=valid.iloc[0].isoformat() if len(valid) else None
            if origin:
                instant=pd.Timestamp(origin)
                instant=instant.tz_localize('UTC') if instant.tz is None else instant.tz_convert('UTC')
                x=(parsed-instant).dt.total_seconds().to_numpy()
            else:x=np.full(n,np.nan)
            clock.update(domain=clock.get('domain','absolute'),origin=str(origin) if origin else None)
        else:
            from app_data import timestamp_text
            x=_numeric(timestamp_text(source))
            from app_time_units import minute_factor
            try:x=x*minute_factor(unit)*60
            except ValueError:
                x=np.arange(n,dtype=float);clock.update(kind='sample',domain='sample',trust='unavailable')
            clock.setdefault('domain','relative');clock.setdefault('origin',None)
        clock={'kind':'time','domain':'relative','origin':None,'trust':'heuristic',**clock,
               'unit':'s' if clock.get('kind','time')=='time' else 'sample','source_key':str(key),'acquisition_policy':policy}
    clock.setdefault('candidates',[])
    clock['quality']=clock_quality(x,policy) if clock['kind']=='time' else {}
    return x,clock


def _default_specs(frame):
    specs={};counts={}
    for position,column in enumerate(frame.columns):
        key=str(column);counts[key]=counts.get(key,0)+1
        if list(map(str,frame.columns)).count(key)>1:key=f'{key} [column {position}]'
        specs[key]={'column_position':position,'original_name':str(column),'length':len(frame)}
    return specs


def source_field(store,field):
    """Retrieve native evidence, never the sorted/masked display projection."""
    from app_operation_context import checkpoint
    checkpoint()
    ds=store.datasets[field['run_id']];frame=ds.frame
    specs=frame.attrs.get('inventory_fields') or _default_specs(frame)
    spec=specs[field['source_key']];positions=_source_positions(frame,spec)
    column=spec.get('column_position')
    if spec.get('source_type')=='metadata':
        values=np.empty(1,dtype=object);values[0]=deepcopy(spec.get('metadata_value'))
        x=np.arange(1,dtype=float);clock={'kind':'sample','domain':'sample','unit':'sample','origin':None,
          'trust':'unavailable','source_key':None,'acquisition_policy':'unknown','candidates':[],'quality':{}}
        return {'values':_immutable(values),'raw_values':_immutable(values),'coordinates':_immutable(x),'x':_immutable(x),
                'source_indices':_immutable(positions),'quality_valid':_immutable([True]),'metadata':deepcopy(field.get('metadata',{})),'clock':clock}
    values=frame.attrs.get('source_native_arrays',{}).get(field['source_key'])
    if values is None:
        values=frame.iloc[positions,column].to_numpy() if column is not None else frame[field['source_key']].iloc[positions].to_numpy()
        # Restore native integer/bool/complex dtype after DataFrame padding;
        # values with an exact source array above bypass this projection entirely.
        if spec.get('dtype'):
            try:values=values.astype(spec['dtype'])
            except (ValueError,TypeError):pass
    raw=frame.attrs.get('source_raw_arrays',{}).get(field['source_key'],values)
    same_raw=raw is values
    raw=np.asarray(raw)[:len(values)]
    x,clock=_clock(frame,spec,positions)
    quality=np.ones(len(values),dtype=bool);status=spec.get('status')
    if status and status in frame.columns:
        flags=frame[status].iloc[positions].astype('string').str.strip().str.upper()
        valid_values=spec.get('quality_valid_values',['OK'])
        quality=flags.isin([str(v).upper() for v in valid_values]).fillna(False).to_numpy(dtype=bool)
    immutable_values=_immutable(values)
    out={'values':immutable_values,'raw_values':immutable_values if same_raw else _immutable(raw),'coordinates':_immutable(x),
         'source_indices':_immutable(positions),'quality_valid':_immutable(quality),
         'metadata':deepcopy(field.get('metadata',{})),'clock':clock}
    out['x']=out['coordinates']
    return out


def inventory_runs(store,dataset_ids=None):
    from app_operation_context import checkpoint
    selected=set(dataset_ids) if dataset_ids is not None else None;runs=[]
    for ds in store.datasets.values():
        checkpoint('Inventorying '+ds.name)
        if selected is not None and ds.id not in selected:continue
        frame=ds.frame;specs=frame.attrs.get('inventory_fields') or _default_specs(frame);fields=[]
        for key,spec in specs.items():
            checkpoint()
            position=spec.get('column_position')
            series=pd.Series([spec.get('metadata_value')],dtype=object) if spec.get('source_type')=='metadata' else frame.iloc[:,position] if position is not None else frame[key]
            channels=[c for c in store.channels.values() if c.dataset_id==ds.id and not c.parents and c.attributes.get('source_column')==key]
            channel=channels[0] if channels else None
            unit=frame.attrs.get('column_units',{}).get(key,'')
            metadata={'source_properties':deepcopy(frame.attrs.get('tdms_channel_properties',{}).get(key,{})),
                      'group_properties':deepcopy(frame.attrs.get('tdms_groups',{}).get(spec.get('tdms_group',''),{}).get('properties',{})),
                      'file_properties':deepcopy(frame.attrs.get('tdms_file_properties',{})),
                      'reader_operations':deepcopy(spec.get('reader_operations',[])),
                      'scaling_authority':spec.get('scaling_authority','unreviewed'),
                      'quality_source':spec.get('status'),'acquisition_policy':spec.get('clock_description',{}).get('acquisition_policy','unknown')}
            metadata.update(deepcopy(spec.get('metadata',{})))
            field={'id':field_id(ds.id,key),'run_id':ds.id,'source_key':key,'original_name':spec.get('original_name',str(series.name)),
                   'group':spec.get('tdms_group',spec.get('group','Columns')),'path':spec.get('path',key),
                   'dtype':spec.get('dtype',str(series.dtype)),'unit':str(unit or ''),'disposition':'needs review',
                   'native_samples':len(_source_positions(frame,spec)),'metadata':metadata}
            if channel:field['channel_id']=channel.id
            evidence=source_field(store,field);values=evidence['values'];field['clock']=evidence['clock']
            numeric=_numeric(values);finite=np.isfinite(numeric)
            if np.asarray(values).ndim==1 and np.asarray(values).dtype.kind in 'biuf':numeric_scalar=True
            elif np.asarray(values).dtype.kind in 'cV' or np.asarray(values).ndim!=1:numeric_scalar=False
            else:
                scalar_cells=[v for v in values if not isinstance(v,(tuple,list,np.ndarray,Mapping))]
                nonmissing=[v for v in scalar_cells if not (v is None or v is pd.NA or v is pd.NaT or isinstance(v,(float,np.floating)) and np.isnan(v))]
                try:
                    converted=pd.to_numeric(pd.Series(nonmissing),errors='coerce')
                    numeric_scalar=bool(nonmissing) and len(scalar_cells)==len(values) and not pd.isna(converted).any() and converted.dtype.kind!='c'
                except (TypeError,ValueError):numeric_scalar=False
            metadata['numeric_scalar']=numeric_scalar
            metadata['native_dtype']=field['dtype']
            quality={'samples':len(values),'valid_quality_samples':int(evidence['quality_valid'].sum()),
                     'invalid_quality_samples':int((~evidence['quality_valid']).sum()),'clock':field['clock']['quality']}
            native_dtype=np.asarray(values).dtype
            numeric_dtype=pd.api.types.is_numeric_dtype(native_dtype) or numeric_scalar
            if numeric_dtype and native_dtype.kind!='c':
                quality.update(invalid_values=int((~finite).sum()),finite_samples=int(finite.sum()),
                               constant=bool(finite.any() and np.all(numeric[finite]==numeric[finite][0])))
            else:
                quality['missing_values']=sum(v is None or v is pd.NA or v is pd.NaT or isinstance(v,(float,np.floating)) and np.isnan(v) for v in values)
            field['quality']=quality
            explicit=spec.get('disposition')
            unsupported=native_dtype.kind in 'Vc' or np.asarray(values).ndim>1 or any(isinstance(v,(tuple,list,np.ndarray,Mapping)) for v in values[:min(len(values),32)])
            if explicit:field['disposition']=explicit
            elif not len(values):field['disposition']='invalid';metadata['reason']='Empty source field.'
            elif unsupported:field['disposition']='unsupported';metadata['reason']='Complex, vector or structured values require a registered analysis capability.'
            elif numeric_dtype and not finite.any():field['disposition']='invalid';metadata['reason']='No finite source values.'
            elif numeric_dtype or any(isinstance(v,(str,bool,np.bool_)) for v in values):field['disposition']='analysed'
            else:field['disposition']='needs review';metadata['reason']='Source structure needs review.'
            fields.append(field)
        signature=[{k:f[k] for k in ('source_key','dtype','unit','group')} for f in fields]
        schema=hashlib.sha256(json.dumps(sorted(signature,key=lambda f:f['source_key']),ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        runs.append({'id':ds.id,'name':ds.name,'source':ds.source,'schema_signature':schema,'fields':fields,
                     'metadata':{'format':frame.attrs.get('format',frame.attrs.get('reader_id','table')),
                                 'reader_id':frame.attrs.get('reader_id'),'reader_version':frame.attrs.get('reader_version'),
                                 'source_identity':deepcopy(frame.attrs.get('source_identity',{'method':'unavailable','reason':'No import-time source hash was captured.'})),
                                 'reader_options':deepcopy(frame.attrs.get('reader_options',{})),
                                 'source_metadata':deepcopy(frame.attrs.get('tdms_file_properties',{})),
                                 'group_metadata':deepcopy(frame.attrs.get('tdms_groups',{}))},
                     'quality':{'fields':len(fields),'measurements':sum(f['disposition'] not in ('supporting clock','quality/status source','metadata') for f in fields),
                                'clocks':sum(f['disposition']=='supporting clock' for f in fields),'quality_sources':sum(f['disposition']=='quality/status source' for f in fields)}})
    return runs

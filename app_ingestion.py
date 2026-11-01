"""Generic file readers; source tables are kept separate from projections."""
from pathlib import Path
from copy import deepcopy
import re
import zipfile
import numpy as np
import pandas as pd
from app_channel_store import Channel, Dataset, ChannelStore


def _read_builtin(path,options):
    path = Path(path)
    # An unsupported suffix is parsed as text only after an explicit user choice.
    suffix = '.csv' if options.get('reader_id')=='tabular' else path.suffix.lower()
    if suffix == '.tdms':
        from app_tdms import read_tdms_tables
        return read_tdms_tables(path)
    if suffix == '.zip':
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if Path(n).suffix.lower() in ('.csv','.txt','.tsv','.tab') and not n.endswith('/')]
            if not names:
                raise ValueError('ZIP contains no CSV data')
            return [(n, _read_tabular(archive.open(n),options)) for n in names]
    if suffix in ('.xlsx', '.xls'):
        return list(pd.read_excel(path, sheet_name=None,header=options.get('header',0),decimal=options.get('decimal','.')).items())
    if suffix == '.parquet':
        return [(path.name, pd.read_parquet(path))]
    if suffix == '.json':
        return [(path.name, pd.read_json(path))]
    try:
        frame=_read_tabular(path,options)
    except (pd.errors.ParserError,UnicodeDecodeError):
        # Bench instruments such as WT500 prepend a variable-width settings
        # block. Reuse the lossless engineering header/unit reader for these.
        from app_data import smart_read_file
        if any(k in options for k in ('delimiter','header','decimal','encoding')):raise
        frame=smart_read_file(path)
    return [(path.name,frame)]


def _read_tabular(path,options):
    delimiter=options.get('delimiter');delimiter=None if delimiter in (None,'auto') else delimiter
    try:return pd.read_csv(path,sep=delimiter,engine='python',header=options.get('header',0),decimal=options.get('decimal','.'),encoding=options.get('encoding','utf-8-sig'))
    except pd.errors.EmptyDataError:return pd.DataFrame()


_BUILTINS_REGISTERED=False


def _register_builtin_readers():
    global _BUILTINS_REGISTERED
    from app_reader_registry import ReaderSpec,register_reader,TABULAR_OPTIONS,_READERS
    for id,suffixes in [('tabular',('.csv','.txt','.tsv','.tab','.dat','.log','.asc')),
                        ('excel',('.xlsx','.xls')),('tdms',('.tdms',)),('archive',('.zip',)),
                        ('json',('.json',)),('parquet',('.parquet',))]:
        if id in _READERS:
            if _READERS[id].read is not _read_builtin:raise ValueError('Reserved builtin reader identity: '+id)
            continue
        register_reader(ReaderSpec(id,'1.0',suffixes,_read_builtin,dict(TABULAR_OPTIONS)))
    _BUILTINS_REGISTERED=True


def read_tables(path,reader_options=None):
    from app_reader_registry import reader_for,validate_options
    from app_operation_context import checkpoint
    import hashlib
    reader=reader_for(path,(reader_options or {}).get('reader_id'))
    options=validate_options(reader_options,reader)
    tables=reader.read(Path(path),options)
    if not isinstance(tables,(tuple,list)) or any(not isinstance(t,(tuple,list)) or len(t)!=2 or not isinstance(t[1],pd.DataFrame) for t in tables):
        raise ValueError('Reader must return named pandas source tables')
    digest=hashlib.sha256()
    # Captured while importing; later reports never relabel a re-read file hash
    # as the identity of a potentially older in-memory recording.
    with Path(path).open('rb') as stream:
        while True:
            chunk=stream.read(1024*1024)
            if not chunk:break
            checkpoint();digest.update(chunk)
    for name,frame in tables:
        frame.attrs={**frame.attrs,'reader_id':reader.id,'reader_version':reader.version,
                     'reader_options':options,'source_identity':{'method':'sha256-file-at-import','sha256':digest.hexdigest()}}
        if options.get('column_units'):frame.attrs['column_units']={**frame.attrs.get('column_units',{}),**options['column_units']}
    return tables


def ingest(store, path, time_column=None, coordinate_unit=None,force_sample=False,reader_options=None):
    from app_operation_context import checkpoint
    checkpoint('Reading '+Path(path).name)
    from app_reader_registry import validate_options,reader_for
    reader_options=validate_options(reader_options,reader_for(path,(reader_options or {}).get('reader_id')))
    time_column=time_column if time_column is not None else reader_options.get('time_column')
    coordinate_unit=coordinate_unit or reader_options.get('unit')
    if reader_for(path,reader_options.get('reader_id')).id=='tdms':
        from app_tdms import ingest_tdms
        return ingest_tdms(store,path,time_column,coordinate_unit,force_sample,reader_options=reader_options)
    # Parse every sheet/field in an isolated store. A malformed late sheet or
    # cancellation must leave existing datasets and channel selections intact.
    target_store=store;store=ChannelStore()
    ids = []
    with store.batch():
        for name, frame in read_tables(path,reader_options):
            checkpoint('Preparing '+name)
            ds = Dataset(name, frame.copy(deep=True), str(path))
            store.datasets[ds.id] = ds
            from app_unit_detection import detect_unit,projection_frame
            frame = projection_frame(frame)
            # Unit-row consumption changes only the analysis projection. Keep
            # original row positions for every native field in the source table.
            source_positions=list(range(len(ds.frame)-len(frame),len(ds.frame)))
            candidates = [c for c in frame.columns if re.match(r'^(?:timestamp|datetime|date[ _]time|time|elapsed|relative[ _](?:time|minutes|seconds)|date)(?:$|[ _\[(])',str(c),re.I) and not re.search(r'remain|left|countdown',str(c),re.I)]
            time_origin=None
            clock = None if force_sample else time_column or (candidates[0] if candidates else None)
            clock_columns={clock};clock_components=[]
            unit = coordinate_unit or ('s' if clock else 'sample')
            kind = 'time' if clock and unit!='sample' else 'sample'
            if clock:
                from app_data import timestamp_text
                numeric = pd.to_numeric(timestamp_text(frame[clock]), errors='coerce')
                if pd.api.types.is_numeric_dtype(frame[clock].dtype) or numeric.notna().sum() >= max(1, len(frame)*.8):
                    x = numeric.to_numpy(dtype=float)
                    if not coordinate_unit:
                        declared=frame.attrs.get('column_units',{}).get(clock)
                        label=str(clock).lower()
                        if re.search(r'min',label):unit='min'
                        elif re.search(r'millisecond|(?:^|[^a-z])ms(?:$|[^a-z])',label):unit='ms'
                        elif re.search(r'microsecond|(?:^|[^a-z])(?:us|µs)(?:$|[^a-z])',label):unit='us'
                        elif re.search(r'hour|(?:^|[^a-z])(?:h|hr)(?:$|[^a-z])',label):unit='h'
                        elif str(clock).lower()=='time':
                            from app_simulation import is_simulation_frame
                            if is_simulation_frame(frame):unit='min'
                            if len(frame):
                                from app_time_units import MINUTE_FACTORS
                                first=str(frame[clock].iloc[0]).strip().lower()
                                if first in MINUTE_FACTORS:unit=first
                        if declared:unit=declared
                else:
                    names={str(c).strip().lower():c for c in frame.columns}
                    if not time_column and 'date' in names and 'time' in names:
                        from app_data import extract_datetime_series
                        parsed=extract_datetime_series(frame,fallback=False);clock_columns.update([names['date'],names['time']]);clock_components=[str(names['date']),str(names['time'])]
                    else:
                        from app_data import _parse_timestamp_column
                        parsed = _parse_timestamp_column(frame[clock], clock,
                            frame.attrs.get('column_units',{}).get(clock,''),
                            excel=frame.attrs.get('source_format')=='excel')
                    valid = parsed.dropna()
                    if valid.empty:
                        raise ValueError(f'Cannot interpret coordinate column {clock}')
                    time_origin=valid.iloc[0].isoformat()
                    x = (parsed-valid.iloc[0]).dt.total_seconds().to_numpy();unit='s'
            else:
                x = np.arange(len(frame), dtype=float)
            source_unit=unit
            # Trusted adapters may describe native per-field clocks, original
            # lengths, categorical/quality fields and metadata. Generic plotting
            # must not erase that common source contract.
            provided_inventory=deepcopy(ds.frame.attrs.get('inventory_fields',{}))
            inventory=deepcopy(provided_inventory)
            for column_number,col in enumerate(frame.columns):
                key=str(col)
                if list(map(str,frame.columns)).count(key)>1:key=f'{key} [column {column_number}]'
                default_spec={'column_position':column_number,'original_name':str(col),'length':len(frame),
                                'source_row_positions':source_positions,'clock':str(clock) if clock is not None else None,
                                'clock_components':clock_components,'dtype':str(frame.iloc[:,column_number].dtype),
                                'coordinate_unit':'datetime' if time_origin else source_unit,
                                'clock_description':{'kind':kind,'domain':reader_options.get('clock_domain','absolute' if time_origin else ('relative' if clock is not None else 'sample')),
                                    'origin':time_origin,'trust':'declared' if time_column is not None else 'heuristic' if clock is not None else 'unavailable',
                                    'candidates':[str(c) for c in candidates], 'acquisition_policy':reader_options.get('acquisition_policy','unknown')}}
                if col in clock_columns:default_spec['disposition']='supporting clock'
                inventory[key]={**default_spec,**inventory.get(key,{})}
            ds.frame.attrs={**ds.frame.attrs,'inventory_fields':inventory,'time_origin':time_origin,
                            'column_units':{**ds.frame.attrs.get('column_units',{}),**frame.attrs.get('column_units',{})}}
            if kind=='time':
                from app_time_units import minute_factor
                x=x*minute_factor(unit);unit='min'
            for column_number,col in enumerate(frame.columns):
                checkpoint('Loading '+name+' · '+str(col),column_number,len(frame.columns))
                if col in clock_columns:
                    continue
                from app_actuators import interpret_channel
                source_key=str(col)
                if list(map(str,frame.columns)).count(source_key)>1:source_key=f'{source_key} [column {column_number}]'
                if inventory[source_key].get('disposition') in ('supporting clock','quality/status source','metadata'):continue
                native=None
                if source_key in provided_inventory:
                    from app_parameter_inventory import source_field
                    native=source_field(store,{'run_id':ds.id,'source_key':source_key})
                source_values=native['values'] if native is not None else frame.iloc[:,column_number].to_numpy()
                channel_x=native['x'] if native is not None else x
                channel_kind=native['clock']['kind'] if native is not None else kind
                channel_unit='min' if channel_kind=='time' else 'sample'
                if native is not None and channel_kind=='time':channel_x=channel_x/60
                channel_order=np.flatnonzero(np.isfinite(channel_x));channel_order=channel_order[np.argsort(channel_x[channel_order],kind='stable')]
                # Preserve complex/vector/categorical source values in the
                # inventory even when the numeric plotting model cannot use them.
                if np.asarray(source_values).dtype.kind in 'cV' or np.asarray(source_values).ndim!=1:continue
                try:y = pd.to_numeric(pd.Series(source_values), errors='coerce').to_numpy(dtype=float)
                except (TypeError,ValueError):continue
                detected_unit,unit_source=detect_unit(frame,col)
                from app_data import classify_signal_kind
                state = bool(re.search(r'valve|state|code|stage|switch|bool', str(col), re.I)) or classify_signal_kind(col) in ('control','door_lock','stage')
                if detected_unit and detected_unit.lower() not in ('state','bool','boolean','code','1'):state=False
                channel = Channel(str(col), channel_x[channel_order], y[channel_order], unit=detected_unit,
                                  kind='discrete' if state else 'analog', coordinate_unit=channel_unit if native is not None else unit,
                                  coordinate_kind=channel_kind, dataset_id=ds.id, source=str(path),
                                  attributes={'time_origin':time_origin,'unit_detection':unit_source,'original_coordinate_unit':source_unit,'source_column':source_key, 'source_rows':len(source_values), 'projection_rows':len(channel_order)})
                channel=interpret_channel(channel,raw_series=np.asarray(source_values)[channel_order])
                if native is not None and not native['quality_valid'].all():
                    from dataclasses import replace
                    projected=channel.y.copy();projected[~native['quality_valid'][channel_order]]=np.nan
                    channel=replace(channel,y=projected,attributes={**channel.attributes,'invalid_quality_samples':int((~native['quality_valid']).sum())})
                if not np.isfinite(channel.y).any() and not channel.attributes.get('actuator_binary'):continue
                ids.append(store.add(channel).id)
    checkpoint('Adding imported datasets')
    with target_store.batch():
        target_store.datasets.update(store.datasets)
        for channel in store.channels.values():target_store.add(channel)
    return ids

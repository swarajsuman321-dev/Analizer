"""Generic file readers; source tables are kept separate from projections."""
from pathlib import Path
import re
import zipfile
import numpy as np
import pandas as pd
from app_channel_store import Channel, Dataset


def read_tables(path):
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == '.tdms':
        from app_tdms import read_tdms_tables
        return read_tdms_tables(path)
    if suffix == '.zip':
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith('.csv')]
            if not names:
                raise ValueError('ZIP contains no CSV data')
            return [(n, pd.read_csv(archive.open(n), sep=None, engine='python')) for n in names]
    if suffix in ('.xlsx', '.xls'):
        return list(pd.read_excel(path, sheet_name=None).items())
    if suffix == '.parquet':
        return [(path.name, pd.read_parquet(path))]
    if suffix == '.json':
        return [(path.name, pd.read_json(path))]
    try:
        frame=pd.read_csv(path,sep=None,engine='python')
    except (pd.errors.ParserError,UnicodeDecodeError):
        # Bench instruments such as WT500 prepend a variable-width settings
        # block. Reuse the lossless engineering header/unit reader for these.
        from app_data import smart_read_file
        frame=smart_read_file(path)
    return [(path.name,frame)]


def ingest(store, path, time_column=None, coordinate_unit=None,force_sample=False):
    from app_operation_context import checkpoint
    checkpoint('Reading '+Path(path).name)
    if Path(path).suffix.lower()=='.tdms':
        from app_tdms import ingest_tdms
        return ingest_tdms(store,path,time_column,coordinate_unit,force_sample)
    ids = []
    with store.batch():
        for name, frame in read_tables(path):
            checkpoint('Preparing '+name)
            ds = Dataset(name, frame.copy(deep=True), str(path))
            store.datasets[ds.id] = ds
            from app_unit_detection import detect_unit,projection_frame
            frame = projection_frame(frame)
            from app_data import timestamp_candidates
            candidates = timestamp_candidates(frame) if not force_sample and not time_column else []
            time_origin=None
            clock = None if force_sample else time_column or (candidates[0] if candidates else None)
            clock_columns={clock}
            unit = coordinate_unit or ('s' if clock else 'sample')
            kind = 'time' if clock and unit!='sample' else 'sample'
            if clock:
                from app_data import timestamp_text, _parse_timestamp_column
                numeric = pd.to_numeric(timestamp_text(frame[clock]), errors='coerce')
                if numeric.notna().sum() >= max(1, len(frame)*.8):
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
                        parsed=extract_datetime_series(frame,fallback=False);clock_columns.update([names['date'],names['time']])
                    else:parsed = _parse_timestamp_column(frame[clock],clock,
                        frame.attrs.get('column_units',{}).get(clock,''),
                        excel=Path(path).suffix.lower() in ('.xls','.xlsx'))
                    valid = parsed.dropna()
                    if valid.empty:
                        raise ValueError(f'Cannot interpret coordinate column {clock}')
                    time_origin=valid.iloc[0].isoformat()
                    x = (parsed-valid.iloc[0]).dt.total_seconds().to_numpy();unit='s'
            else:
                x = np.arange(len(frame), dtype=float)
            source_unit=unit
            if kind=='time':
                from app_time_units import minute_factor
                x=x*minute_factor(unit);unit='min'
            good = np.isfinite(x)
            order = np.flatnonzero(good)[np.argsort(x[good], kind='stable')]
            for column_number,col in enumerate(frame.columns):
                checkpoint('Loading '+name+' · '+str(col),column_number,len(frame.columns))
                if col in clock_columns:
                    continue
                from app_actuators import interpret_channel
                y = pd.to_numeric(frame[col], errors='coerce').to_numpy(dtype=float)
                detected_unit,unit_source=detect_unit(frame,col)
                from app_data import classify_signal_kind
                state = bool(re.search(r'valve|state|code|stage|switch|bool', str(col), re.I)) or classify_signal_kind(col) in ('control','door_lock','stage')
                if detected_unit and detected_unit.lower() not in ('state','bool','boolean','code','1'):state=False
                channel = Channel(str(col), x[order], y[order], unit=detected_unit,
                                  kind='discrete' if state else 'analog', coordinate_unit=unit,
                                  coordinate_kind=kind, dataset_id=ds.id, source=str(path),
                                  attributes={'time_origin':time_origin,'unit_detection':unit_source,'original_coordinate_unit':source_unit,'source_column':str(col), 'source_rows':len(frame), 'projection_rows':len(order)})
                channel=interpret_channel(channel,raw_series=frame[col].iloc[order].to_numpy())
                if not np.isfinite(channel.y).any() and not channel.attributes.get('actuator_binary'):continue
                ids.append(store.add(channel).id)
    return ids

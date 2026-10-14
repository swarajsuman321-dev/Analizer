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
    return [(path.name, pd.read_csv(path, sep=None, engine='python'))]


def ingest(store, path, time_column=None, coordinate_unit=None):
    ids = []
    with store.batch():
        for name, frame in read_tables(path):
            ds = Dataset(name, frame.copy(deep=True), str(path))
            store.datasets[ds.id] = ds
            candidates = [c for c in frame.columns if re.search(r'time|timestamp|elapsed|date', str(c), re.I)]
            clock = time_column or (candidates[0] if candidates else None)
            unit = coordinate_unit or ('s' if clock else 'sample')
            kind = 'time' if clock else 'sample'
            if clock:
                numeric = pd.to_numeric(frame[clock], errors='coerce')
                if numeric.notna().sum() >= max(1, len(frame)*.8):
                    x = numeric.to_numpy(dtype=float)
                    if not coordinate_unit and re.search(r'min', str(clock), re.I):
                        unit = 'min'
                else:
                    parsed = pd.to_datetime(frame[clock], errors='coerce')
                    valid = parsed.dropna()
                    if valid.empty:
                        raise ValueError(f'Cannot interpret coordinate column {clock}')
                    x = (parsed-valid.iloc[0]).dt.total_seconds().to_numpy()
            else:
                x = np.arange(len(frame), dtype=float)
            good = np.isfinite(x)
            order = np.flatnonzero(good)[np.argsort(x[good], kind='stable')]
            for col in frame.columns:
                if col == clock:
                    continue
                y = pd.to_numeric(frame[col], errors='coerce').to_numpy(dtype=float)
                if not np.isfinite(y).any():
                    continue
                match = re.search(r'[\[(]([^\])]+)[\])]', str(col))
                state = bool(re.search(r'valve|state|code|stage|switch|bool', str(col), re.I))
                channel = Channel(str(col), x[order], y[order], unit=match.group(1) if match else '',
                                  kind='discrete' if state else 'analog', coordinate_unit=unit,
                                  coordinate_kind=kind, dataset_id=ds.id, source=str(path),
                                  attributes={'source_column':str(col), 'source_rows':len(frame), 'projection_rows':len(order)})
                ids.append(store.add(channel).id)
    return ids

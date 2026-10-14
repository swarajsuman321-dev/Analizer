"""Adapters for the established engineering pipeline, preserving source tables."""
import numpy as np
from app_channel_store import ChannelStore,Channel,Dataset
from app_ingestion import ingest


def compare_recordings(machine,simulation):
    from app_data import smart_read_file,extract_datetime_series
    import pandas as pd
    from app_simulation import load_simulation_reference,specs_for_curves
    from app_comparator import ComparisonEngine
    from app_inspection import comparison_traces
    original=smart_read_file(machine)
    raw=original.copy(deep=True)
    if 'time_min' in raw:
        raw['time_min']=pd.to_numeric(raw['time_min'],errors='coerce')
        invalid=int(raw['time_min'].isna().sum());raw=raw.dropna(subset=['time_min']).sort_values('time_min',kind='stable')
    else:
        timestamps=extract_datetime_series(raw,fallback=False)
        invalid=int(timestamps.isna().sum())
        raw['dt']=timestamps;raw=raw.dropna(subset=['dt']).sort_values('dt',kind='stable').reset_index(drop=True)
        if raw.empty:raise ValueError('Bench comparison requires a recognizable clock; choose a mapped time column')
        raw['time_min']=(raw['dt']-raw['dt'].min()).dt.total_seconds()/60.
    raw.attrs['comparison_data_quality']={'invalid_timestamp_rows_excluded':invalid,'duplicate_timestamps':int(raw['time_min'].duplicated().sum()),'duplicate_policy':'Every source sample retained; cursor selects the last duplicate'}
    ComparisonEngine.apply_pressure_default(raw,'Pa')
    adapter=load_simulation_reference(simulation,pressure_display_unit='Pa',preserve_pressure_numbers=True)
    try:
        curves=adapter.extract_curves();specs=specs_for_curves(curves)
        columns=ComparisonEngine.find_bench_columns(raw,specs)
        traces=comparison_traces(raw,curves,columns,specs)
        score=ComparisonEngine.generate_scorecard(raw,curves)
        store=ChannelStore()
        bench=Dataset('Original bench comparison',original,source=machine);store.datasets[bench.id]=bench
        reference=Dataset('Original simulation comparison',adapter.frame.copy(),source=simulation);store.datasets[reference.id]=reference
        for spec in specs:
            entries=traces[spec['key']]
            for source in ('sim','bench'):
                trace=entries[source]
                if trace is None:continue
                x,y,kind=trace
                unit=spec['unit']
                if spec['key']=='heater_power' and source=='bench' and entries['bench_kind']=='digital':unit='state'
                store.add(Channel(f'{spec["label"]} · {source}',x,y,unit=unit,kind='analog' if kind=='analog' else 'discrete',
                                  coordinate_unit='min',dataset_id=reference.id if source=='sim' else bench.id,group='Comparison',
                                  attributes={'parameter':spec['key'],'comparison_source':source}))
        return store,score
    finally:
        close=getattr(adapter,'close',None)
        if close:close()

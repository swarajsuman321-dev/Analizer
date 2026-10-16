"""Shared engineering workflows and retained diagnostic tables for the Qt studio."""
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
from app_channel_store import ChannelStore,Channel,Dataset
from app_unit_detection import detect_unit
from app_data import (DataEngine,smart_read_file,extract_datetime_series,get_column_unit,
                      classify_signal_kind,normalize_control_series)


def quality_frame(frame):
    rows=[]
    for column in frame:
        series=frame[column];numeric=pd.to_numeric(series,errors='coerce')
        values=numeric.to_numpy(dtype=float,na_value=np.nan)
        rows.append({'Signal':str(column),'Rows':len(series),'Missing readings':int(series.isna().sum()),
                     'Non-finite numeric readings':int(np.isinf(values).sum()),'Unit':get_column_unit(frame,column) or 'Not stated'})
    return pd.DataFrame(rows)


def metadata_frame(values):
    import json
    return pd.DataFrame([{'Setting':str(k),'Value':json.dumps(v,default=str,ensure_ascii=False) if isinstance(v,(dict,list,tuple)) else str(v)} for k,v in values.items()])


def add_table(store,name,frame,source='',sheet=None):
    frame=frame.copy(deep=True)
    if sheet:frame.attrs['studio_sheet']=sheet
    dataset=Dataset(name,frame,source);store.datasets[dataset.id]=dataset
    return dataset


def align_recordings(power,machine,strategy,offset_seconds=0,plugins=None):
    from app_inspection import engineering_metrics
    from app_data import BUILTIN_SYNC_STRATEGIES
    if not power and not machine:raise ValueError('Choose at least one recording')
    hook=plugins.custom_sync_hooks.get(strategy) if plugins else None
    if strategy not in BUILTIN_SYNC_STRATEGIES and hook is None:raise ValueError('The selected synchronization plugin is unavailable')
    engine=DataEngine(power,machine,'Raw Timestamps (No Shift)' if hook else strategy,float(offset_seconds)/60.)
    frame=engine.get_data().copy(deep=True)
    if frame.empty:raise ValueError('The selected recordings contain no usable data')
    if hook:
        inherited=dict(frame.attrs);frame=hook(frame.copy(deep=True))
        if not isinstance(frame,pd.DataFrame) or frame.empty or 'relative_minutes' not in frame:raise ValueError('Sync plugins must return a nonempty DataFrame with relative_minutes')
        frame.attrs={**inherited,**frame.attrs};frame.attrs['sync_report']={**frame.attrs.get('sync_report',{}),'selected_plugin':strategy}
    x=pd.to_numeric(frame['relative_minutes'],errors='coerce').to_numpy(float)
    if not np.isfinite(x).all():raise ValueError('Synchronized coordinates must be finite')
    order=np.argsort(x,kind='stable');frame=frame.iloc[order].reset_index(drop=True);x=x[order]
    store=ChannelStore()
    for name,path in (('Original power',power),('Original machine',machine)):
        if path:
            if Path(path).suffix.lower()=='.tdms':
                from app_tdms import read_tdms_tables
                original=read_tdms_tables(path)[0][1]
            else:original=smart_read_file(path)
            add_table(store,name,original,path,name.replace(' ','_'))
    aligned=add_table(store,'Aligned engineering data',frame,'; '.join(filter(None,(power,machine))),'Synchronized_Series')
    power_columns=set(next((d.frame.columns for d in store.datasets.values() if d.name=='Original power'),[]))
    machine_columns=set(next((d.frame.columns for d in store.datasets.values() if d.name=='Original machine'),[]))
    for column in frame:
        if column in ('relative_minutes','datetime','dt') or str(column).endswith(('_BIN','_BIN_ops')):continue
        kind=classify_signal_kind(column)
        values=pd.to_numeric(frame[column],errors='coerce')
        from app_data import is_actuator_column
        if is_actuator_column(column,detect_unit(frame,column)[0]):values=normalize_control_series(frame[column],column)
        state=kind in ('control','door_lock','state','code','stage')
        detected=detect_unit(frame,column)[0]
        if detected and detected.lower() not in ('state','bool','boolean','code','1'):state=False
        source_column=str(column)[:-4] if str(column).endswith('_ops') and str(column)[:-4] in machine_columns else str(column)
        source_path=machine if str(column).endswith('_ops') or column not in power_columns else power
        store.add(Channel(str(column),x,values.to_numpy(float),source=source_path or '',unit=detect_unit(frame,column)[0] or ('state' if state else ''),
                          kind='discrete' if state else 'analog',coordinate_unit='min',dataset_id=aligned.id,group='Aligned',
                          attributes={'source_column':source_column,'data_column':str(column),'signal_kind':kind}))
    rows=engineering_metrics(frame)
    if plugins:
        for hook in plugins.custom_kpi_hooks:
            extra=hook(frame.copy(deep=True))
            if not isinstance(extra,list):raise ValueError('KPI plugins must return a list of (name, value) pairs')
            rows.extend(extra)
    add_table(store,'Engineering KPIs',pd.DataFrame(rows,columns=['Parameter','Value']),sheet='Summary_KPIs')
    add_table(store,'Data quality',quality_frame(frame),sheet='Data_Quality')
    add_table(store,'Synchronization details',metadata_frame({'Sources':[power,machine],'Offset seconds':offset_seconds,'Warnings':engine.warnings,'Assumed time':engine.used_synthetic_time,'Synchronization':frame.attrs.get('sync_report',{})}),sheet='Report_Info')
    import os
    alignment_key='|'.join(os.path.normcase(str(Path(path).resolve())) if path else '' for path in (power,machine))
    for channel in store.channels.values():channel.attributes['alignment_key']=alignment_key
    for dataset in store.datasets.values():dataset.frame.attrs['alignment_key']=alignment_key
    from app_actuators import interpret_channel
    for id,channel in list(store.channels.items()):
        interpreted=interpret_channel(channel,raw_series=frame[channel.attributes['data_column']])
        if not np.isfinite(interpreted.y).any() and not interpreted.attributes.get('actuator_binary'):del store.channels[id]
        else:store.channels[id]=interpreted
    return store,frame


@dataclass
class ComparisonResult:
    store: ChannelStore
    score: pd.DataFrame
    raw: pd.DataFrame
    curves: dict
    columns: dict


def compare_recordings(machine,simulation,*,reference_settings=None,calibration=None,bench_columns=None,tolerances=None,detailed=False):
    from app_simulation import load_simulation_reference,specs_for_curves
    from app_comparator import ComparisonEngine
    from app_inspection import comparison_traces
    original=smart_read_file(machine);raw=original.copy(deep=True)
    if 'time_min' in raw:
        raw['time_min']=pd.to_numeric(raw['time_min'],errors='coerce');invalid=int((~np.isfinite(raw['time_min'])).sum())
        raw=raw.loc[np.isfinite(raw['time_min'])].sort_values('time_min',kind='stable')
    else:
        timestamps=extract_datetime_series(raw,fallback=False);invalid=int(timestamps.isna().sum())
        raw['dt']=timestamps;raw=raw.dropna(subset=['dt']).sort_values('dt',kind='stable').reset_index(drop=True)
        if raw.empty:raise ValueError('Bench comparison requires a recognizable clock')
        raw['time_min']=(raw['dt']-raw['dt'].min()).dt.total_seconds()/60.
    if raw.empty:raise ValueError('No valid bench timestamps were found')
    raw.attrs['comparison_data_quality']={'invalid_timestamp_rows_excluded':invalid,'duplicate_timestamps':int(raw['time_min'].duplicated().sum()),'duplicate_policy':'Every source sample retained; cursor selects last duplicate'}
    ComparisonEngine.apply_pressure_default(raw,'Pa')
    image=Path(simulation).suffix.lower() in ('.png','.jpg','.jpeg','.bmp','.tif','.tiff')
    if image:
        from app_reference_image import SimulationImageAnalyzer
        adapter=SimulationImageAnalyzer(simulation,calibration=calibration)
    else:
        settings={'pressure_display_unit':'Pa','preserve_pressure_numbers':True,**(reference_settings or {})}
        adapter=load_simulation_reference(simulation,**settings)
    try:
        curves=adapter.extract_curves();specs=specs_for_curves(curves)
        overrides=bench_columns or {}
        for key,column in overrides.items():
            if key not in {spec['key'] for spec in specs}:raise ValueError(f'Unknown comparison signal: {key}')
            if column is not None and column not in raw:raise ValueError(f'Mapped bench column is missing: {column}')
        raw.attrs['bench_column_overrides']=overrides
        columns=ComparisonEngine.find_bench_columns(raw,specs);traces=comparison_traces(raw,curves,columns,specs)
        score=ComparisonEngine.generate_scorecard(raw,curves,tolerances=tolerances)
        store=ChannelStore();bench=add_table(store,'Original bench comparison',original,machine,'Original_Bench')
        add_table(store,'Prepared bench comparison',raw,machine,'Raw_Test_Log')
        reference=add_table(store,'Simulation reference',pd.DataFrame() if image else adapter.frame,simulation,'Simulation_CSV' if not image else 'Reference_Image')
        for spec in specs:
            entries=traces[spec['key']]
            for source in ('sim','bench'):
                trace=entries[source]
                if trace is None:continue
                x,y,kind=trace;unit=spec['unit']
                if spec['key']=='heater_power' and source=='bench' and entries['bench_kind']=='digital':unit='state'
                store.add(Channel(f'{spec["label"]} · {source}',x,y,unit=unit,kind='analog' if kind=='analog' else 'discrete',coordinate_unit='min',
                                  dataset_id=reference.id if source=='sim' else bench.id,group='Comparison',
                                  attributes={'parameter':spec['key'],'comparison_source':source,'signal_kind':kind,'actuator_command':spec['key']=='heater_power' and source=='bench' and entries['bench_kind']=='digital'}))
            if spec['key'] in curves:add_table(store,spec['label']+' reference',curves[spec['key']],simulation,'Sim_'+spec['key'])
        from app_reporting import match_scorecard
        add_table(store,'Comparison scorecard',match_scorecard(score),sheet='Scorecard_Summary')
        for name,table in [('Bench_Data_Quality',quality_frame(raw)),('Heater_State_Comparison',ComparisonEngine.heater_state_report(raw,curves)),
                           ('Image_Trace_Quality' if image else 'CSV_Trace_Quality',adapter.report_dataframe()),
                           ('Image_Calibration' if image else 'CSV_Units',metadata_frame(adapter.analysis_info()))]:
            add_table(store,name,table,sheet=name)
        if hasattr(adapter,'file_report'):
            add_table(store,'Package files',adapter.file_report(),sheet='Package_Files')
            add_table(store,'Package metadata',metadata_frame(adapter.package_metadata),sheet='Package_Metadata')
        add_table(store,'Comparison settings',metadata_frame({'Bench':machine,'Reference':simulation,'Mappings':columns,'Quality':raw.attrs['comparison_data_quality'],'Notes':score.attrs}),sheet='Comparison_Info')
        result=ComparisonResult(store,score,raw,curves,columns)
        return result if detailed else (store,score)
    finally:
        close=getattr(adapter,'close',None)
        if close:close()


def load_reference(path,settings=None,calibration=None):
    """Open a simulation CSV/ZIP/image without requiring a bench recording."""
    from app_simulation import load_simulation_reference,specs_for_curves
    image=Path(path).suffix.lower() in ('.png','.jpg','.jpeg','.bmp','.tif','.tiff')
    if image:
        from app_reference_image import SimulationImageAnalyzer
        adapter=SimulationImageAnalyzer(path,calibration=calibration)
    else:adapter=load_simulation_reference(path,**(settings or {}))
    try:
        curves=adapter.extract_curves();store=ChannelStore()
        source=add_table(store,'Simulation reference',pd.DataFrame() if image else adapter.frame,str(path),'Reference_Image' if image else 'Simulation_CSV')
        for spec in specs_for_curves(curves):
            curve=curves.get(spec['key'])
            if curve is None or curve.empty:continue
            store.add(Channel(spec['label'],curve['time_min'].to_numpy(float),curve['value'].to_numpy(float),unit=spec['unit'],
                              kind='analog' if spec['kind']=='analog' and not spec.get('step') else 'discrete',coordinate_unit='min',dataset_id=source.id,source=str(path),
                              attributes={'parameter':spec['key'],'signal_kind':spec['kind'],'reference_type':'image' if image else 'table'}))
        add_table(store,'Reference quality',adapter.report_dataframe(),sheet='Image_Trace_Quality' if image else 'CSV_Trace_Quality')
        add_table(store,'Reference details',metadata_frame(adapter.analysis_info()),sheet='Image_Calibration' if image else 'CSV_Units')
        if hasattr(adapter,'file_report'):
            add_table(store,'Package files',adapter.file_report(),sheet='Package_Files')
            add_table(store,'Package metadata',metadata_frame(adapter.package_metadata),sheet='Package_Metadata')
        return store
    finally:
        close=getattr(adapter,'close',None)
        if close:close()

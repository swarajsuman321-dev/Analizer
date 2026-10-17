"""TDMS import with per-channel clocks and inert, portable source metadata."""
from pathlib import Path
import re
import numpy as np
import pandas as pd
from app_channel_store import Channel,Dataset,ChannelStore
from app_time_units import minute_factor


def portable(value):
    if isinstance(value,dict):return {str(k):portable(v) for k,v in value.items()}
    if isinstance(value,(list,tuple,np.ndarray)):return [portable(v) for v in value]
    if isinstance(value,(np.datetime64,pd.Timestamp)):return str(value)
    if isinstance(value,np.generic):return portable(value.item())
    if isinstance(value,float) and not np.isfinite(value):return str(value)
    if isinstance(value,(str,int,float,bool)) or value is None:return value
    return str(value)


def is_clock(name):
    return bool(re.search(r'^(?:dtime|time|timestamp|elapsed(?:[ _](?:time|seconds|minutes))?|relative[ _](?:time|seconds|minutes))(?:$|[ \[(])|_dtime$',name,re.I))


def read_tdms_tables(path):
    from nptdms import TdmsFile
    path=Path(path)
    try:file=TdmsFile.read(path)
    except Exception as exc:raise ValueError(f'Cannot read TDMS recording: {exc}') from exc
    columns={};properties={};specs={};groups={};units={};lengths={};absolute=[]
    for group in file.groups():
        groups[group.name]={'properties':portable(group.properties),'channels':{c.name:portable(c.properties) for c in group.channels()}}
        for channel in group.channels():
            if not len(channel):continue
            data=channel[:]
            if data.dtype.kind in 'Vc':continue
            columns[channel.path]=pd.Series(data);lengths[channel.path]=len(data)
            properties[channel.path]=portable(channel.properties)
            unit=channel.properties.get('unit_string') or group.properties.get('Unit') or (group.properties.get('LabSys_Scaling_OutputUnit','') if group.properties.get('LabSys_Scaling_Active') else '')
            units[channel.path]=str(channel.properties.get('unit_string') or 's') if is_clock(channel.name) else str(unit)
            if is_clock(channel.name) and data.dtype.kind=='M':absolute.append(data[~np.isnat(data)].min() if np.any(~np.isnat(data)) else np.datetime64('NaT'))
            start=channel.properties.get('wf_start_time')
            if start is not None:
                try:absolute.append(np.datetime64(start,'ns'))
                except (ValueError,TypeError):pass
    absolute=[v for v in absolute if not np.isnat(v)]
    origin=min(absolute) if absolute else None
    for group in file.groups():
        clocks=[c for c in group.channels() if c.path in columns and is_clock(c.name)]
        for channel in group.channels():
            if channel.path not in columns or is_clock(channel.name):continue
            # LabSys stores one measurement, its clock and quality status in each group.
            labsys=channel.name.endswith('_Value') and channel.name[:-6]+'_dTime' in group
            if channel.name.endswith('_Status') and channel.name[:-7]+'_Value' in group:continue
            if columns[channel.path].dtype.kind not in 'biuf':
                words=columns[channel.path].dropna().astype(str).str.upper()
                if not len(words) or not words.isin(['ON','OFF','TRUE','FALSE']).all():continue
            clock=group[channel.name[:-6]+'_dTime'] if labsys else (clocks[0] if len(clocks)==1 and 'wf_increment' not in channel.properties else None)
            time_col=None;unit='sample';kind='sample'
            if clock is not None:
                time_col=clock.path;unit=units[clock.path] or 's';kind='time'
                if columns[time_col].dtype.kind=='M':unit='datetime'
            elif 'wf_increment' in channel.properties:
                increment=float(channel.properties['wf_increment']);offset=float(channel.properties.get('wf_start_offset',0))
                if not np.isfinite(increment) or increment<=0 or not np.isfinite(offset):raise ValueError(f'Invalid TDMS waveform timing for {channel.name}')
                start=channel.properties.get('wf_start_time')
                if start is not None and origin is not None:offset+=float((np.datetime64(start,'ns')-origin)/np.timedelta64(1,'s'))
                time_col=channel.path+' / waveform time (s)';columns[time_col]=pd.Series(offset+np.arange(len(channel))*increment);unit='s';kind='time'
            status=channel.name[:-6]+'_Status' if labsys else None
            status_path=group[status].path if status in group else None
            specs[channel.path]={'name':group.name if labsys else channel.name,'group':'Measurements' if labsys else group.name,'tdms_group':group.name,'length':len(channel),'clock':time_col,'coordinate_unit':unit,'coordinate_kind':kind,'status':status_path}
    if not columns:raise ValueError('Cannot read TDMS recording: no channel data (empty or incomplete file)')
    frame=pd.DataFrame(columns)
    frame.attrs={'format':'TDMS','column_units':units,'tdms_file_properties':portable(file.properties),'tdms_groups':groups,
                 'tdms_channel_properties':properties,'tdms_lengths':lengths,'tdms_projections':specs,'time_origin':str(origin) if origin is not None else None}
    return [(path.name,frame)]


def ingest_tdms(store,path,time_column=None,coordinate_unit=None,force_sample=False):
    from app_actuators import interpret_channel
    from app_unit_detection import detect_unit
    pending=[]
    for name,frame in read_tdms_tables(path):
        ds=Dataset(name,frame,str(path));channels=[]
        for column,spec in frame.attrs['tdms_projections'].items():
            n=spec['length'];source=frame[column].iloc[:n];clock=None if force_sample else time_column or spec['clock']
            unit=coordinate_unit or (frame.attrs['column_units'].get(clock) or spec['coordinate_unit'] if clock else 'sample');kind='time' if clock and unit!='sample' else 'sample'
            if clock:
                if clock not in frame:raise ValueError(f'Coordinate column not found: {clock}')
                if spec['coordinate_unit']=='datetime' and not coordinate_unit:
                    parsed=pd.to_datetime(frame[clock].iloc[:n],errors='coerce');origin=pd.Timestamp(frame.attrs['time_origin'])
                    x=(parsed-origin).dt.total_seconds().to_numpy()/60;unit='min'
                else:x=pd.to_numeric(frame[clock].iloc[:n],errors='coerce').to_numpy(float)*minute_factor(unit) if kind=='time' else pd.to_numeric(frame[clock].iloc[:n],errors='coerce').to_numpy(float)
            else:x=np.arange(n,dtype=float);unit='sample';kind='sample'
            order=np.flatnonzero(np.isfinite(x));order=order[np.argsort(x[order],kind='stable')]
            y=pd.to_numeric(source,errors='coerce').to_numpy(float)
            detected,unit_source=detect_unit(frame,column)
            attrs={'format':'TDMS','source_column':column,'tdms_group':spec['tdms_group'],'tdms_channel_properties':frame.attrs['tdms_channel_properties'][column],
                   'original_coordinate_unit':spec['coordinate_unit'],'unit_detection':unit_source,'source_rows':n,'projection_rows':len(order),'time_origin':frame.attrs['time_origin']}
            # Explicit LabSys appliance-command schema; do not coerce arbitrary codes.
            if re.fullmatch(r'PDH_AAS_B_(?:HEATER_ON|PU|V\d+)_\d+_R',spec['name']) and not detected:attrs['actuator_command']=True
            channel=Channel(spec['name'],x[order],y[order],unit=detected,kind='discrete' if re.search(r'state|code|stage|error|position',spec['name'],re.I) else 'analog',
                            coordinate_kind=kind,coordinate_unit='min' if kind=='time' else 'sample',dataset_id=ds.id,group=spec['group'],source=str(path),attributes=attrs)
            channel=interpret_channel(channel,raw_series=source.iloc[order].to_numpy())
            if spec['status']:
                quality=frame[spec['status']].iloc[:n].astype('string').str.strip().str.upper().eq('OK').fillna(False).to_numpy(bool)[order]
                from dataclasses import replace
                projected=channel.y.copy();projected[~quality]=np.nan
                bad=np.flatnonzero(~quality);runs=np.split(bad,np.flatnonzero(np.diff(bad)>1)+1) if len(bad) else []
                channel=replace(channel,y=projected,masks=[(float(channel.x[run[0]]),float(channel.x[run[-1]])) for run in runs],attributes={**channel.attributes,'quality_column':spec['status'],'invalid_quality_samples':int((~quality).sum())})
            channels.append(channel)
        if channels:pending.append((ds,channels))
    if not pending:raise ValueError('TDMS contains no supported measurement channels')
    ids=[]
    with store.batch():
        for ds,channels in pending:
            store.datasets[ds.id]=ds
            for channel in channels:ids.append(store.add(channel).id)
    return ids


def engineering_frame(path):
    """Causal, explicitly derived table for the existing synchronization engine.

    Direct plotting keeps native clocks. This adapter uses their union and holds
    earlier readings for at most five seconds, matching the engine's tolerance.
    """
    store=ChannelStore();ingest_tdms(store,path)
    # The UI has reviewed unknown parameters before this worker is started.
    # Apply known units/interpretation before analysis while retaining stable
    # engine column names (custom display names belong to the channel tree).
    from app_tdms_templates import ParameterTemplates
    ParameterTemplates().apply(store)
    channels=[c for c in store.channels.values() if c.coordinate_kind=='time' and len(c.x)]
    if not channels:raise ValueError('TDMS has no recorded timing; use Open to inspect its sample-indexed channels')
    timeline=np.unique(np.concatenate([c.x for c in channels]));source=next(iter(store.datasets.values())).frame
    origin=source.attrs.get('time_origin')
    if not origin:
        origin=source.attrs['tdms_groups'].get('FileMetaData',{}).get('properties',{}).get('Test Execution Start Time') or '2000-01-01'
    origin=pd.Timestamp(origin)
    if origin.tz is not None:origin=origin.tz_convert('UTC').tz_localize(None)
    frame=pd.DataFrame({'datetime':origin+pd.to_timedelta(timeline*60,unit='s')});units={}
    for channel in channels:
        x,effective=channel.values();raw=channel.raw_y if channel.raw_y is not None else channel.y
        raw=np.where(np.isfinite(effective),raw,np.nan)
        index=np.searchsorted(x,timeline,side='right')-1;safe=np.clip(index,0,len(x)-1)
        valid=(index>=0)&(timeline-x[safe]<=5/60);values=np.full(len(timeline),np.nan);values[valid]=raw[safe[valid]]
        original_name=channel.attributes.get('original_name',channel.name)
        name=original_name if channel.group=='Measurements' else channel.group+' / '+original_name
        frame[name]=values;units[name]='boolean' if channel.attributes.get('actuator_binary') else channel.unit
    frame.attrs={**source.attrs,'column_units':units,'source_path':str(Path(path).resolve()),'source_format':'tdms',
                 'tdms_projection_policy':'Union of recorded clocks; previous reading held for at most 5 seconds. Native samples remain in the original TDMS source table.'}
    return frame

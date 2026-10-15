"""Per-channel actuator interpretation, with reversible source values."""
from dataclasses import replace
import numpy as np
import pandas as pd
from app_data import is_actuator_column,normalize_control_series


def interpret_channel(channel,mode=None,raw_series=None):
    attrs=dict(channel.attributes);mode=mode or attrs.get('value_interpretation','auto')
    if mode not in ('auto','numeric','actuator'):raise ValueError('Choose Auto, Numeric or Actuator interpretation')
    if raw_series is None and channel.parents and mode=='auto':return channel
    original=channel.raw_y if channel.raw_y is not None else channel.y
    source=pd.Series(raw_series if raw_series is not None else original)
    name=attrs.get('source_column',channel.name)
    raw_unit=attrs.get('raw_unit',channel.unit);raw_kind=attrs.get('raw_kind',channel.kind)
    words=source.dropna().astype(str).str.strip().str.upper()
    boolean_words=len(words)>0 and words.isin({'ON','OFF','TRUE','FALSE'}).all()
    binary=mode=='actuator' or (mode=='auto' and (attrs.get('actuator_command',False) or is_actuator_column(name,raw_unit) or str(raw_unit).lower() in ('bool','boolean') or (boolean_words and raw_unit in ('','state'))))
    binary=bool(binary)
    if not binary and channel.raw_y is None and mode=='auto':return channel
    attrs.update(value_interpretation=mode,actuator_binary=binary,raw_unit=raw_unit,raw_kind=raw_kind)
    numeric=pd.to_numeric(source,errors='coerce')
    if binary:
        states=normalize_control_series(source,name,nonzero_integers=True)
        raw=numeric.fillna(states).to_numpy(float)
        return replace(channel,y=states.to_numpy(float),raw_y=raw,unit='state',kind='discrete',attributes=attrs)
    return replace(channel,y=numeric.to_numpy(float),raw_y=channel.raw_y,unit=raw_unit,kind=raw_kind,attributes=attrs)


def state_text(value):
    return 'ON' if value==1 else 'OFF' if value==0 else 'Unknown'

"""Conservative channel unit detection shared by ordinary and engineering imports."""
import re
from app_data import get_column_unit


def detect_unit(frame, column):
    explicit=get_column_unit(frame,column)
    if explicit:return explicit,'declared'
    name=str(column).strip();key=re.sub(r'[^a-z0-9]+','_',name.lower()).strip('_')
    # Unbracketed suffixes are common in logger exports.
    suffix=re.search(r'(?:_|\s)(kWh|Wh|kW|W|mbar|kPa|Pa|bar|RPM|rpm|Hz|mV|V|mA|A|degC|°C|°F|ms|min|sec|kg|mL|L)$',name)
    if suffix:
        proxy=frame.copy(deep=False);proxy.attrs={**frame.attrs,'column_units':{column:suffix.group(1)}}
        return get_column_unit(proxy,column),'suffix'
    known={'water_temp':'°C','water_pressure':'Pa','heater_power':'W','drum_speed':'RPM','water_volume':'L','water_amount':'L','remaining_time':'min','relative_minutes':'min'}
    if key in known:return known[key],'signal name'
    if re.search(r'valve|state|switch|bool',key):return 'state','signal name'
    if re.search(r'(?:^|_)(?:rpm|speed)(?:_|$)',key) and 'drum' in key:return 'RPM','signal name'
    return '','unknown'


def projection_frame(frame):
    """Consume bracketed or plain engineering unit rows without changing source tables."""
    from app_data import _remove_unit_row
    cleaned=_remove_unit_row(frame.copy(deep=True))
    if len(cleaned)!=len(frame) or frame.empty:return cleaned
    known={'s','sec','ms','us','µs','min','h','°C','degC','°F','W','kW','Wh','kWh','V','mV','A','mA','Pa','kPa','bar','mbar','RPM','rpm','L','mL','Hz','kg','g','%','state'}
    cells={col:str(value).strip() for col,value in frame.iloc[0].items() if str(value).strip() in known}
    if cells and len(cells)>=len(frame.columns)*.4 and all(str(value).strip() in known or str(value).strip() in ('','nan') for value in frame.iloc[0]):
        cleaned=frame.iloc[1:].copy(deep=True).reset_index(drop=True);cleaned.attrs={**frame.attrs,'column_units':cells}
    return cleaned

import os
import re
import csv
import pandas as pd
import numpy as np

class DataReadError(ValueError):
    """Raised when a selected data file cannot be decoded or parsed."""


DRUM_SYNC_STRATEGY = 'First Drum Start to First Power Rise'
BUILTIN_SYNC_STRATEGIES = (
    'Intelligent (Heater ON to >1.5kW Spike)',
    DRUM_SYNC_STRATEGY,
    'Raw Timestamps (No Shift)',
    'Manual Time Offset (Minutes)',
)


def get_column_unit(df, column):
    """Read an explicit unit from the export's unit row or column label."""
    hint = df.attrs.get('column_units', {}).get(column)
    if not hint:
        matches = [unit for unit in re.findall(r'[\[(]([^\])]+)[\])]', str(column))
                   if not unit.strip().isdigit()]
        hint = matches[-1] if matches else None
    if hint is None:
        return None
    token = str(hint).strip().lower().replace(' ', '').replace('μ', 'µ')
    return {
        'w': 'W', 'watt': 'W', 'watts': 'W', 'kw': 'kW', 'kilowatt': 'kW', 'kilowatts': 'kW', 'wh': 'Wh', 'kwh': 'kWh',
        'bar': 'bar', 'mbar': 'mbar', 'pa': 'Pa', 'kpa': 'kPa', 'us': 'µs', 'µs': 'µs',
        'c': '°C', '°c': '°C', 'degc': '°C', 'celsius': '°C',
        'f': '°F', '°f': '°F', 'degf': '°F', 'fahrenheit': '°F', 'k': 'K', 'kelvin': 'K',
        'a': 'A', 'v': 'V', 'hz': 'Hz', 'g': 'g', 'kg': 'kg', 'ms': 'ms',
        'rpm': 'RPM', 'r/min': 'RPM', 'rps': 'rps',
        'l': 'L', 'liter': 'L', 'litre': 'L', 'ml': 'mL',
        's': 's', 'sec': 's', 'second': 's', 'seconds': 's',
        'min': 'min', 'minute': 'min', 'minutes': 'min',
        'h': 'h', 'hr': 'h', 'hour': 'h', 'hours': 'h',
    }.get(token, str(hint).strip())


def convert_signal_units(series, source_unit, target_unit):
    """Convert explicit engineering units; never convert a sensor pulse to pressure."""
    numeric = pd.to_numeric(series, errors='coerce').astype(float).replace([np.inf, -np.inf], np.nan)
    if source_unit is None or source_unit == target_unit:
        return numeric
    factors = {
        ('kW', 'W'): 1000, ('W', 'kW'): 0.001,
        ('kWh', 'Wh'): 1000, ('Wh', 'kWh'): 0.001,
        ('bar', 'mbar'): 1000, ('mbar', 'bar'): 0.001,
        ('Pa', 'mbar'): 0.01, ('mbar', 'Pa'): 100,
        ('kPa', 'mbar'): 10, ('mbar', 'kPa'): 0.1,
        ('bar', 'Pa'): 100000, ('Pa', 'bar'): 0.00001,
        ('kPa', 'Pa'): 1000, ('Pa', 'kPa'): 0.001,
        ('kPa', 'bar'): 0.01, ('bar', 'kPa'): 100,
        ('rps', 'RPM'): 60, ('RPM', 'rps'): 1 / 60,
        ('mL', 'L'): 0.001, ('L', 'mL'): 1000,
        ('g', 'kg'): 0.001, ('kg', 'g'): 1000,
        ('s', 'min'): 1 / 60, ('h', 'min'): 60, ('ms', 'min'): 1 / 60000,
    }
    if (source_unit, target_unit) in factors:
        return numeric * factors[(source_unit, target_unit)]
    if target_unit == '°C' and source_unit == '°F':
        return (numeric - 32) * (5 / 9)
    if target_unit == '°C' and source_unit == 'K':
        return numeric - 273.15
    raise DataReadError(f'Cannot compare {source_unit} with {target_unit} without an explicit conversion.')

def smart_read_file(filepath):
    if not filepath:
        return pd.DataFrame()
    if not os.path.exists(filepath):
        raise DataReadError(f"The selected file no longer exists: {filepath}")

    ext = os.path.splitext(filepath)[1].lower()
    if ext=='.tdms':
        from app_tdms import engineering_frame
        return engineering_frame(filepath)
    if ext in ['.xlsx', '.xls', '.xlsm']:
        try:
            df = pd.read_excel(filepath)
            df.attrs['source_path'] = os.path.abspath(filepath)
            df.attrs['source_format'] = 'excel'
            if sum(1 for c in df.columns if 'unnamed' in str(c).lower()) >= len(df.columns) * 0.5:
                for skip in range(1, 50):
                    try:
                        trial = pd.read_excel(filepath, skiprows=skip)
                        if sum(1 for c in trial.columns if 'unnamed' in str(c).lower()) < len(trial.columns) * 0.4:
                            df = trial
                            break
                    except Exception:
                        continue
            df.attrs['source_path'] = os.path.abspath(filepath)
            df.attrs['source_format'] = 'excel'
            return _clean_dataframe_types(_remove_unit_row(df))
        except Exception as exc:
            raise DataReadError(f"Could not read Excel file '{os.path.basename(filepath)}': {exc}") from exc

    encodings = ['utf-8-sig', 'cp1252', 'latin1']
    last_error = None
    for enc in encodings:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                sample_lines = [f.readline() for _ in range(160)]

            if not sample_lines:
                continue

            best_sep = ','
            best_skip = 0
            max_valid_cols = 0

            for idx, line in enumerate(sample_lines):
                line_str = line.strip()
                if not line_str or line_str.startswith('#') or line_str.startswith('//'):
                    continue

                for sep in [',', ';', '\t', '|']:
                    parts = [p.strip() for p in next(csv.reader([line_str], delimiter=sep))]
                    if len(parts) >= 2 and len(parts) > max_valid_cols:
                        text_tokens = sum(1 for p in parts if any(c.isalpha() for c in p))
                        if text_tokens >= max(1, int(len(parts) * 0.35)):
                            max_valid_cols = len(parts)
                            best_sep = sep
                            best_skip = idx

            df = pd.read_csv(
                filepath,
                skiprows=best_skip,
                sep=best_sep,
                encoding=enc,
                on_bad_lines='error',
                low_memory=False
            )

            df.columns = [str(c).strip().strip('"').strip() for c in df.columns]
            df = df.loc[:, ~df.columns.str.contains('^Unnamed:.*_level')]
            df.attrs['source_path'] = os.path.abspath(filepath)
            df.attrs['delimiter'] = best_sep

            if not df.empty:
                return _clean_dataframe_types(_remove_unit_row(df))
        except (UnicodeDecodeError, UnicodeError) as exc:
            last_error = exc
            continue
        except pd.errors.ParserError as exc:
            raise DataReadError(
                f"Could not parse '{os.path.basename(filepath)}' without losing rows: {exc}"
            ) from exc
        except Exception as exc:
            last_error = exc
            continue

    try:
        df = pd.read_csv(filepath, sep=None, engine='python', on_bad_lines='error')
        df.attrs['source_path'] = os.path.abspath(filepath)
        return _clean_dataframe_types(_remove_unit_row(df))
    except Exception as exc:
        last_error = exc
    if last_error:
        raise DataReadError(f"Could not read data file '{os.path.basename(filepath)}': {last_error}") from last_error
    return pd.DataFrame()


def _remove_unit_row(df):
    """Retain a dedicated bracketed unit row as metadata rather than samples."""
    if df.empty:
        return df
    first_row = df.iloc[0].astype(str)
    unit_cells = {
        column: str(value).strip().strip('[]()').strip()
        for column, value in first_row.items()
        if re.match(r'^[\[\(].+[\]\)]$', str(value).strip())
    }
    if len(unit_cells) >= len(df.columns) * 0.4:
        df.attrs['column_units'] = unit_cells
        return df.iloc[1:].reset_index(drop=True)
    return df


def _clean_dataframe_types(df):
    if df.empty:
        return df

    original_columns = list(df.columns)
    columns, seen = [], set()
    for original in original_columns:
        name = str(original).strip()
        unique = name
        suffix = 2
        while unique in seen:
            unique = f'{name} [{suffix}]'
            suffix += 1
        seen.add(unique)
        columns.append(unique)
    df.columns = columns
    if original_columns != columns:
        units = df.attrs.get('column_units', {})
        df.attrs['column_units'] = {
            renamed: units[original]
            for original, renamed in zip(original_columns, columns) if original in units
        }

    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col]):
            cleaned = df[col].astype('string').str.strip().replace('', pd.NA)
            if cleaned.dropna().empty:
                continue
            numeric_text = cleaned
            if df.attrs.get('delimiter') in (';', '\t', '|'):
                decimal_comma = cleaned.str.fullmatch(r'[+-]?\d+,\d+(?:[eE][+-]?\d+)?').fillna(False)
                numeric_text = cleaned.where(~decimal_comma, cleaned.str.replace(',', '.', regex=False))
            converted = pd.to_numeric(numeric_text, errors='coerce')
            # Mixed control columns can contain numbers and words such as OFF.
            # Keep those words instead of silently coercing them to missing.
            if converted.notna().sum() == cleaned.notna().sum():
                df[col] = converted
            else:
                df[col] = numeric_text

    return df


def classify_signal_kind(column_name):
    """Classify states without mistaking heater power or pump speed for ON/OFF."""
    name = re.sub(r'[^a-z0-9]+', ' ', str(column_name).lower()).strip()
    if any(token in name for token in (
        'wash stage', 'cycle state', 'program stage', 'program phase',
        'machine state', 'state machine', 'stwf number', 'phase nr', 'step nr', 'schritt',
    )):
        return 'stage'
    if any(token in name for token in (
        'temperature', 'temperatur', 'temprature', 'temperatuer', 'temp',
        'pressure', 'druck', 'speed', 'rpm', 'drehzahl', 'voltage', 'ampere', 'amps',
        'power', 'energy', 'volume', 'weight', 'count', 'retry', 'left time',
        'remaining time', 'remain time', 'frequency', 'hz', 'ntc',
    )):
        return 'analog'
    if re.search(r'[\[(]\s*(?:a|v|w|kw|wh|kwh|hz|°c|°f|k|rpm)\s*[\])]', str(column_name).lower()):
        return 'analog'
    if 'current' in name and not any(word in name for word in ('state', 'status', 'relay', 'lock', 'ctrl', 'control')):
        return 'analog'
    if any(token in name for token in ('door', 'interlock', 'lid switch', 'lock')):
        return 'door_lock'
    if any(token in name for token in (
        'valve', 'vavle', 'ventil', 'pump', 'pumpe', 'relay', 'relais',
        'ctrl', 'control', 'state', 'status', 'start pause', 'start/pause',
        'heater on', 'heat on', 'running',
    )):
        return 'control'
    return 'analog'


def is_actuator_column(column_name, unit=None):
    """Identify actuator commands, excluding physical measurements and program codes."""
    name=re.sub(r'[^a-z0-9]+',' ',str(column_name).lower())
    if unit and str(unit).strip().lower() not in ('state','bool','boolean','1'):return False
    if re.search(r'\b(power|energy|current|voltage|temper\w*|temp|pressure|speed|rpm|flow|frequency|duration|count|retry|stage|phase|code|duty|pwm|position|error|fault|alarm|diagnostic|status|detected)\b',name):return False
    return bool(re.search(r'\b(valv\w*|vavle|ventil\w*|door|interlock|lid|lock|heater|heating|heat|pump|pumpe|relay|relais|solenoid|actuator|contactor|fan|motor|compressor)\b',name))


def normalize_control_series(series, column_name="", *, nonzero_integers=None):
    """Actuator integers map nonzero to ON; missing/fractional readings stay unknown."""
    numeric = pd.to_numeric(series, errors='coerce')
    finite = numeric.notna() & np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan))
    result = pd.Series(np.nan, index=series.index, name=series.name, dtype=float)
    if nonzero_integers is None:nonzero_integers=is_actuator_column(column_name)
    valid_integer = finite & numeric.eq(np.floor(numeric))
    if not nonzero_integers:valid_integer &= numeric.ge(0)
    result.loc[valid_integer] = numeric.loc[valid_integer].ne(0).astype(float)
    text = series.astype('string').str.strip().str.upper()

    is_door_lock = any(k in str(column_name).lower() for k in ('door', 'lock', 'interlock', 'lid'))
    if is_door_lock:
        active_words = {'ON', 'TRUE', 'ACTIVE', 'LOCK', 'LOCKED', 'ENGAGED', '1'}
        inactive_words = {'OFF', 'FALSE', 'INACTIVE', 'UNLOCK', 'UNLOCKED', 'OPEN', 'RELEASED', '0'}
    else:
        active_words = {'ON', 'TRUE', 'ACTIVE', 'START', 'RUN', 'RUNNING', 'OPEN', '1'}
        inactive_words = {'OFF', 'FALSE', 'INACTIVE', 'PAUSE', 'PAUSED', 'STOP', 'STOPPED', 'CLOSED', '0'}

    result.loc[text.isin(active_words)] = 1.0
    result.loc[text.isin(inactive_words)] = 0.0
    return result


def infer_pressure_units(df):
    """Infer units for appliance pressure channels, including paired mbar/pulse exports.

    Some logger exports use two nearly identical ``water pressure`` headers: the
    engineering pressure in mbar and a raw sensor pulse period in microseconds.
    Explicit units always win. For an unlabelled pair, the high-period channel
    (>1200 median) is treated as pulse time and the lower-range channel as mbar.
    """
    if df is None or df.empty:
        return {}

    units = {}
    candidates = []
    for column in df.columns:
        name = str(column).strip().lower()
        unit_hint = str(df.attrs.get('column_units', {}).get(column, '')).lower()
        labelled_name = f'{name} {unit_hint}'
        if not any(token in name for token in ('pressure', 'pressur', 'druck')):
            continue

        if re.search(r'\b(?:pulse|usec|microseconds?|u\s*sec|µ\s*sec|μ\s*sec|µs|μs|us)\b', labelled_name):
            units[column] = 'µs'
            continue
        if re.search(r'\b(?:mbar|millibars?)\b', labelled_name):
            units[column] = 'mbar'
            continue
        if re.search(r'\bkpa\b', labelled_name):
            units[column] = 'kPa'
            continue
        if re.search(r'\bpa\b', labelled_name):
            units[column] = 'Pa'
            continue
        if re.search(r'\bbar\b', labelled_name):
            units[column] = 'bar'
            continue

        values = df[column]
        if isinstance(values, pd.DataFrame):
            values = values.iloc[:, 0]
        numeric = pd.to_numeric(values, errors='coerce')
        median = float(numeric.dropna().abs().median()) if numeric.notna().any() else np.nan
        base_name = re.sub(r'(?:\.\d+|\s*\[\d+\])$', '', name)
        base_name = re.sub(r'\b(?:dst|dest|target|set|setpoint)\b', '', base_name)
        base_name = re.sub(r'[^a-z0-9]+', '', base_name)
        is_target = bool(re.search(r'\b(?:dst|dest|target|set|setpoint)\b', name))
        candidates.append((column, median, base_name, is_target))

    # Infer duplicated unlabelled sensor channels as a pair. This distinguishes
    # the provided logger's ~1600 µs raw signal from its 0–1000 mbar channel.
    groups = {}
    for item in candidates:
        if not item[3]:
            groups.setdefault(item[2], []).append(item)
    for group in groups.values():
        valid = [item for item in group if np.isfinite(item[1])]
        if len(valid) > 1 and max(item[1] for item in valid) >= 1200 > min(item[1] for item in valid):
            low = min(valid, key=lambda item: item[1])
            high = max(valid, key=lambda item: item[1])
            units[low[0]] = 'mbar'
            units[high[0]] = 'µs'

    for column, median, _base, is_target in candidates:
        if column in units:
            continue
        # A magnitude alone cannot establish physical units. Only the paired
        # logger schema above or explicit metadata can provide a match.
        units[column] = 'unknown'
    inferred = [column for column in units if column in {item[0] for item in candidates} and units[column] != 'unknown']
    if inferred:
        warnings = df.attrs.setdefault('data_warnings', [])
        message = 'Pressure units inferred from paired channel ranges; confirm the logger export units.'
        if message not in warnings:
            warnings.append(message)
    unconfirmed = [column for column, _median, _base, target in candidates
                   if not target and units.get(column) == 'unknown']
    if unconfirmed:
        warnings = df.attrs.setdefault('data_warnings', [])
        message = 'Pressure units unconfirmed for: ' + ', '.join(map(str, unconfirmed)) + '. These channels are excluded from mbar comparisons.'
        if message not in warnings:
            warnings.append(message)
    return units


def normalize_program_stage_series(series):
    """Return wash/rinse/spin stage IDs (1/2/3), accepting scaled image values."""
    values = pd.Series(series, index=getattr(series, 'index', None))
    numeric = pd.to_numeric(values, errors='coerce')
    # Work with plain NumPy masks throughout. Nullable pandas BooleanArrays can
    # contain pd.NA, whose truth value raises ``boolean value of NA is ambiguous``
    # when any downstream operation coerces the mask to bool.
    numeric_values = numeric.to_numpy(dtype=float, na_value=np.nan, copy=True)
    finite = np.isfinite(numeric_values)
    result = np.full(len(values), np.nan, dtype=float)

    direct = finite & (numeric_values >= 0) & (numeric_values <= 3.5)
    direct_values = np.rint(numeric_values[direct]).copy()
    direct_values[direct_values < 1] = np.nan
    direct_values[direct_values > 3] = np.nan
    result[direct] = direct_values

    encoded = finite & ~direct
    encoded_values = numeric_values[encoded]
    encoded_stages = np.select(
        [encoded_values < 500, encoded_values < 1500, encoded_values < 2500, encoded_values <= 3500],
        [np.nan, 1.0, 2.0, 3.0], default=np.nan
    )
    result[encoded] = encoded_stages

    labels = values.astype('string').str.strip().str.lower()
    label_map = {
        'wash': 1.0, 'main wash': 1.0, 'washing': 1.0,
        'rinse': 2.0, 'rinsing': 2.0,
        'spin': 3.0, 'spinning': 3.0,
    }
    for label, stage in label_map.items():
        label_mask = labels.eq(label).fillna(False).to_numpy(dtype=bool)
        result[~finite & label_mask] = stage
    return pd.Series(result, index=values.index, name=values.name, dtype=float)

def _parse_timestamp_column(target, column_name, unit_hint='', excel=False):
    """Parse absolute timestamps, elapsed units and clock rollover consistently."""
    if pd.api.types.is_datetime64_any_dtype(target):
        return pd.to_datetime(target, errors='coerce', utc=True).dt.tz_localize(None)
    text = target.astype('string').str.strip()
    numeric = pd.to_numeric(text, errors='coerce')
    present = text.notna() & text.ne('')
    if present.any() and numeric.notna().sum() >= present.sum() * 0.8:
        name = re.sub(r'[_\[\]()]', ' ', f'{column_name} {unit_hint}'.lower())
        if any(token in name for token in ('date', 'datum')) and text.dropna().str.fullmatch(r'\d{8}').all():
            return pd.to_datetime(text, format='%Y%m%d', errors='coerce')
        explicit_unit = next((unit for pattern, unit in (
            (r'\b(?:ns|nanoseconds?)\b', 'ns'),
            (r'\b(?:us|µs|μs|usec|microseconds?)\b', 'us'),
            (r'\b(?:ms|msec|milliseconds?)\b', 'ms'),
            (r'\b(?:min|minutes?)\b', 'm'),
            (r'\b(?:h|hr|hours?)\b', 'h'),
            (r'\b(?:s|sec|seconds?|sekunden)\b', 's'),
        ) if re.search(pattern, name)), None)
        magnitude = numeric.dropna().abs().median()
        if excel and explicit_unit is None:
            if any(token in name for token in ('date', 'datum')) and 20000 < magnitude < 100000:
                return pd.to_datetime(numeric, unit='D', origin='1899-12-30', errors='coerce')
            if name.strip() in ('time', 'clock', 'zeit', 'uhrzeit') and numeric.dropna().between(0, 1).all():
                days = numeric + numeric.ffill().diff().lt(-0.5).fillna(False).cumsum()
                return pd.Timestamp('2000-01-01') + pd.to_timedelta(days, unit='D', errors='coerce')
        if ('timestamp' in name or 'epoch' in name or 'unix' in name) and magnitude > 1e8:
            epoch_unit = explicit_unit or ('ns' if magnitude > 1e17 else 'us' if magnitude > 1e14 else 'ms' if magnitude > 1e11 else 's')
            return pd.to_datetime(numeric, unit=epoch_unit, errors='coerce')
        if explicit_unit is None:
            explicit_unit = 's'
        seconds_per_unit = {'ns': 1e-9, 'us': 1e-6, 'ms': 1e-3, 's': 1, 'm': 60, 'h': 3600}
        return pd.Timestamp('2000-01-01') + pd.to_timedelta(numeric * seconds_per_unit[explicit_unit], unit='s', errors='coerce')

    clock_mask = text.str.fullmatch(r'\d{1,3}:\d{2}(?::\d{2}(?:\.\d+)?)?').fillna(False)
    if clock_mask.sum() > len(target) * 0.4:
        clocks = text.where(clock_mask)
        short_clock = clocks.str.count(':').eq(1).fillna(False)
        clocks = clocks.where(~short_clock, clocks + ':00')
        offsets = pd.to_timedelta(clocks, errors='coerce')
        # Large backward jumps in a clock-only log denote midnight. Small
        # out-of-order samples stay sortable without adding an entire day.
        rollovers = offsets.ffill().diff().lt(pd.Timedelta(hours=-12)).fillna(False).cumsum()
        return pd.Timestamp('2000-01-01') + offsets + pd.to_timedelta(rollovers, unit='D')
    return pd.to_datetime(text, format='mixed', errors='coerce', utc=True).dt.tz_localize(None)


def extract_datetime_series(df, fallback=True):
    """Return indexed timestamps without treating remaining-time signals as clocks."""
    if df.empty:
        return pd.Series(pd.NaT, index=df.index, dtype='datetime64[ns]')
    names = {column: re.sub(r'[_-]+', ' ', str(column).strip().lower()) for column in df.columns}
    date_col = next((c for c, name in names.items() if name in ('date', 'datum', 'day', 'tag')), None)
    time_col = next((c for c, name in names.items() if name in ('time', 'zeit', 'uhrzeit')), None)
    if date_col is not None and time_col is not None:
        clocks = df[time_col].astype('string').str.strip()
        clock_numbers = pd.to_numeric(df[time_col], errors='coerce')
        is_excel = df.attrs.get('source_format') == 'excel'
        parsed_dates = _parse_timestamp_column(df[date_col], date_col, excel=is_excel).dt.normalize()
        if is_excel and clock_numbers.notna().any() and clock_numbers.dropna().between(0, 1).all():
            clock_offsets = pd.to_timedelta(clock_numbers, unit='D', errors='coerce')
        else:
            short_clock = clocks.str.fullmatch(r'\d{1,2}:\d{2}').fillna(False)
            clock_text = clocks.where(~short_clock, clocks + ':00')
            clock_offsets = pd.to_timedelta(clock_text, errors='coerce')
        parsed = parsed_dates + clock_offsets
        if parsed.notna().sum() > len(df) * 0.4:
            return parsed

    priorities = ('timestamp', 'datetime', 'date time', 'time stamp', 'elapsed', 'relative time', 'rel time', 'seconds', 'sekunden', 'time', 'zeit', 'clock', 'dauer')
    candidates = []
    for token in priorities:
        for column, name in names.items():
            if any(excluded in name for excluded in ('left', 'remain', 'countdown', 'target', 'dest')):
                continue
            if (name == token or name.startswith(token + ' ') or name.startswith(token + '(') or name.startswith(token + '[')) and column not in candidates:
                candidates.append(column)
    for column in candidates:
        parsed = _parse_timestamp_column(df[column], column, df.attrs.get('column_units', {}).get(column, ''), excel=df.attrs.get('source_format') == 'excel')
        if parsed.notna().sum() > len(df) * 0.4:
            return parsed
    for column in df.columns[:4]:
        sample = df[column].dropna().astype(str).str.strip().head(20)
        if not sample.empty and sample.str.contains(r'[-/:]').sum() >= len(sample) * 0.6:
            parsed = _parse_timestamp_column(df[column], column)
            if parsed.notna().sum() > len(df) * 0.4:
                return parsed
    if fallback:
        return pd.Series(pd.date_range(start='2000-01-01', periods=len(df), freq='1s'), index=df.index)
    return pd.Series(pd.NaT, index=df.index, dtype='datetime64[ns]')

def find_power_column(columns):
    for c in columns:
        cl = re.sub(r'[^a-z0-9]', ' ', str(c).lower()).strip()
        tokens = cl.split()
        if any(ign in cl for ign in ['wp', 'wh', 'kwh', 'consumed', 'pressure', 'druck', 'pump', 'pumpe', 'factor', 'apparent', 'reactive']):
            continue
        if tokens and tokens[0] == 'p' and (len(tokens) == 1 or tokens[1] in ['e1', 'e2', 'e3', 'tot', 'total', 'sum', 'w', 'kw', 'watt', 'watts']):
            return c
        elif cl in ['p', 'p e1', 'p e2', 'p e3', 'p total', 'ptot', 'psum', 'p1', 'p2', 'p3', 'pac', 'pact', 'p meas', 'p w', 'p kw']:
            return c
        elif any(phrase in cl for phrase in ['real power', 'active power', 'activepower', 'realpower', 'wirkleistung', 'active p', 'p active']):
            return c
        elif any(tok in ['power', 'leistung'] for tok in tokens):
            return c
    return None

def find_energy_column(columns):
    for c in columns:
        cl = re.sub(r'[^a-z0-9]', ' ', str(c).lower()).strip()
        tokens = cl.split()
        if any(ign in cl for ign in ['factor', 'set', 'dst', 'target', 'dest', 'limit']):
            continue
        if any(tok in ['wp', 'wh', 'kwh', 'mwh'] for tok in tokens) or any(tok.startswith('wp') for tok in tokens) or 'wp e1' in cl:
            return c
        elif any(phrase in cl for phrase in ['power consumed', 'energy consumed', 'active energy', 'consumed power', 'consumed energy', 'total energy', 'wirkenergie', 'energie verbrauch', 'verbrauch']):
            return c
        elif 'energy' in tokens and not any(ign in cl for ign in ['meter', 'ratio']):
            return c
        elif cl == 'e' or any(u in str(c).lower() for u in ['[wh]', '(wh)', '[kwh]', '(kwh)']):
            return c
    return None

def find_column_by_keywords(columns, keywords):
    for c in columns:
        c_clean = str(c).lower().replace('_', ' ').replace('-', ' ').strip()
        if any(kw in c_clean for kw in keywords):
            return c
    return None

class DataEngine:
    def __init__(self, pd_path, rd_path, sync_strategy="Intelligent", manual_offset=0.0):
        self.pd_path = pd_path
        self.rd_path = rd_path
        self.sync_strategy = sync_strategy
        self.manual_offset = manual_offset
        self.aligned_df = None
        self.used_synthetic_time = False
        self.warnings = []
        self.sync_report = {}
        self._process()

    def _process(self):
        power_df = smart_read_file(self.pd_path)
        ops_df = smart_read_file(self.rd_path)
        for frame in (power_df, ops_df):
            infer_pressure_units(frame)
            self.warnings.extend(frame.attrs.get('data_warnings', []))

        if power_df.empty and ops_df.empty:
            self.aligned_df = pd.DataFrame()
            return
        elif power_df.empty:
            self.aligned_df = self._single_frame_prep(ops_df)
            return
        elif ops_df.empty:
            self.aligned_df = self._single_frame_prep(power_df)
            return

        power_df['datetime'] = extract_datetime_series(power_df, fallback=False)
        ops_df['datetime'] = extract_datetime_series(ops_df, fallback=False)
        if power_df['datetime'].notna().sum() == 0 or ops_df['datetime'].notna().sum() == 0:
            raise DataReadError(
                "Both input files need a recognizable date/time column to synchronize them. "
                "Load one file at a time if its rows should be plotted using an assumed 1-second sample interval."
            )

        power_df = self._prepare_timestamps(power_df, 'Power')
        ops_df = self._prepare_timestamps(ops_df, 'Machine')

        if power_df.empty and ops_df.empty:
            self.aligned_df = pd.DataFrame()
            return
        elif power_df.empty:
            self.aligned_df = self._single_frame_prep(ops_df)
            return
        elif ops_df.empty:
            self.aligned_df = self._single_frame_prep(power_df)
            return

        power_df = self._binarize_controls(power_df)
        ops_df = self._binarize_controls(ops_df)

        power_col = find_power_column(power_df.columns)
        heat_col = next((column for column in ops_df.columns
                         if classify_signal_kind(column) == 'control'
                         and any(word in str(column).lower() for word in ('heat', 'heiz'))
                         and not str(column).endswith('_BIN')), None)
        shift = pd.Timedelta(0)
        event_details = {}

        if self.sync_strategy == DRUM_SYNC_STRATEGY:
            shift, event_details = self._first_drum_power_shift(power_df, ops_df, power_col)
            power_df['datetime'] += shift

        elif "Intelligent" in self.sync_strategy and heat_col and power_col:
            h_target = f"{heat_col}_BIN" if f"{heat_col}_BIN" in ops_df.columns else heat_col
            h_active = ops_df[ops_df[h_target] == 1]
            if not h_active.empty:
                t_heat = h_active.iloc[0]['datetime']
                power_watts = convert_signal_units(power_df[power_col], get_column_unit(power_df, power_col), 'W')
                t_spike = power_df[power_watts > 1500]
                if not t_spike.empty:
                    shift = t_heat - t_spike.iloc[0]['datetime']
                    power_df['datetime'] += shift
                else:
                    self.warnings.append('Heater synchronization could not find a power spike; original timestamps were used.')
            else:
                self.warnings.append('Heater synchronization could not find a heater ON sample; original timestamps were used.')

        elif "Intelligent" in self.sync_strategy:
            self.warnings.append('Heater synchronization channels were unavailable; original timestamps were used.')

        elif "Manual" in self.sync_strategy:
            shift = pd.Timedelta(minutes=self.manual_offset)
            power_df['datetime'] += shift

        tolerance = pd.Timedelta('5s')
        if (power_df['datetime'].max() + tolerance < ops_df['datetime'].min()
                or ops_df['datetime'].max() + tolerance < power_df['datetime'].min()):
            raise DataReadError(
                'The two recordings do not overlap after synchronization. '
                'Check their dates/time zones, choose drum-start or heater synchronization, or set a manual offset.'
            )

        # Keep samples from both devices. A nearest match can show an actuator
        # ON before its recorded transition; backward matching is causal.
        timeline = pd.DataFrame({'datetime': pd.concat(
            [power_df['datetime'], ops_df['datetime']], ignore_index=True
        ).drop_duplicates().sort_values().reset_index(drop=True)})
        merged = pd.merge_asof(
            timeline, power_df.sort_values('datetime'), on='datetime',
            direction='backward', tolerance=tolerance
        )
        merged = pd.merge_asof(
            merged,
            ops_df.sort_values('datetime'),
            on='datetime',
            direction='backward',
            tolerance=tolerance,
            suffixes=('', '_ops')
        )
        merged['relative_minutes'] = (merged['datetime'] - merged['datetime'].min()).dt.total_seconds() / 60.0
        self.sync_report = {
            'strategy': self.sync_strategy, 'power_shift_seconds': shift.total_seconds(),
            'power_rows': len(power_df), 'machine_rows': len(ops_df),
            'aligned_rows': len(merged), 'match_tolerance_seconds': 5,
            **event_details,
        }
        power_units = power_df.attrs.get('column_units', {})
        ops_units = ops_df.attrs.get('column_units', {})
        merged.attrs['column_units'] = dict(power_units)
        merged.attrs['column_units'].update({
            f'{column}_ops' if column in power_df.columns else column: unit
            for column, unit in ops_units.items()
        })
        merged.attrs['data_warnings'] = list(dict.fromkeys(self.warnings))
        merged.attrs['sync_report'] = self.sync_report
        self.aligned_df = merged.reset_index(drop=True)

    @staticmethod
    def _drum_speed_column(columns):
        """Prefer drum feedback, exclude motor speed, label command fallback."""
        candidates = []
        for column in columns:
            name = re.sub(r'[^a-z0-9]+', ' ', str(column).lower()).replace('drump', 'drum').strip()
            words = name.split()
            if ('drum' not in words or not any(word in words for word in ('speed', 'rpm'))
                    or any(word in words for word in ('motor', 'target', 'destination', 'dst', 'dest', 'setpoint', 'bin'))):
                continue
            candidates.append((column, 'feedback' in words, words[:3] == ['drum', 'speed', 'feedback']))
        if not candidates:
            return None, False
        column, feedback, _ = sorted(candidates, key=lambda item: (not item[1], not item[2]))[0]
        return column, feedback

    @staticmethod
    def _first_sustained_rise(times, values, threshold, minimum_seconds=0.5):
        """Return the first known inactive-to-active edge, rejecting spikes/gaps."""
        times = pd.Series(times).reset_index(drop=True)
        values = pd.to_numeric(pd.Series(values), errors='coerce').to_numpy(dtype=float, na_value=np.nan)
        elapsed = (times - times.iloc[0]).dt.total_seconds().to_numpy(dtype=float)
        steps = np.diff(elapsed)
        positive = steps[np.isfinite(steps) & (steps > 0)]
        if not len(positive):
            return None
        cadence = np.quantile(positive, .9) if len(positive) >= 20 else np.median(positive)
        gap_limit = max(float(cadence) * 5, minimum_seconds)
        inactive_samples = 0
        armed = False
        start = None
        for index, value in enumerate(values):
            if not np.isfinite(value) or not np.isfinite(elapsed[index]):
                inactive_samples, armed, start = 0, False, None
                continue
            if index and (steps[index - 1] <= 0 or steps[index - 1] > gap_limit):
                inactive_samples, armed, start = 0, False, None
            if value <= threshold:
                inactive_samples += 1
                armed = armed or inactive_samples >= 2
                start = None
            elif armed:
                inactive_samples = 0
                if start is None:
                    start = index
                if index > start and elapsed[index] - elapsed[start] >= minimum_seconds:
                    return start
            else:
                inactive_samples = 0
        return None

    def _first_drum_power_shift(self, power_df, ops_df, power_col):
        speed_col, is_feedback = self._drum_speed_column(ops_df.columns)
        if speed_col is None or power_col is None:
            raise DataReadError('Drum-start synchronization needs a drum speed/feedback channel in RD and an active power channel in PD.')
        speed = convert_signal_units(ops_df[speed_col], get_column_unit(ops_df, speed_col), 'RPM').abs()
        drum_index = self._first_sustained_rise(ops_df['datetime'], speed, 10.0)
        if drum_index is None:
            raise DataReadError('No reliable first drum start was found: record standstill before rotation above 10 RPM for at least 0.5 seconds. Unknown feedback samples are not replaced with command speed.')
        watts = convert_signal_units(power_df[power_col], get_column_unit(power_df, power_col), 'W')
        baseline_samples = watts.iloc[:3]
        if len(baseline_samples) < 3 or not baseline_samples.notna().all():
            raise DataReadError('Drum-start synchronization needs at least three initial known standby power samples before the first rise.')
        baseline = float(baseline_samples.median())
        mad = float((baseline_samples - baseline).abs().median())
        rise_margin = max(20.0, 6 * 1.4826 * mad)
        if baseline_samples.max() - baseline_samples.min() > rise_margin:
            raise DataReadError('Initial power samples already contain a large rise; a reliable standby baseline is unavailable. Use a manual time offset.')
        threshold = baseline + rise_margin
        power_index = self._first_sustained_rise(power_df['datetime'], watts, threshold)
        if power_index is None:
            raise DataReadError(f'No reliable first power rise was found above {threshold:.2f} W for at least 0.5 seconds. Use a manual time offset.')
        drum_event = ops_df['datetime'].iloc[drum_index]
        power_event = power_df['datetime'].iloc[power_index]
        shift = drum_event - power_event
        if not is_feedback:
            self.warnings.append(f'Drum-start sync uses commanded speed ({speed_col}); no drum feedback channel was exported.')
        self.warnings.append('Drum-start sync assumes the first power rise corresponds to the first drum movement. Review the selected events if another load starts first or feedback is delayed.')
        return shift, {
            'event_alignment': 'First drum rotation matched to first sustained power rise',
            'drum_speed_column': str(speed_col), 'drum_uses_feedback': is_feedback,
            'power_column': str(power_col), 'drum_threshold_RPM': 10.0,
            'power_baseline_W': baseline, 'power_rise_margin_W': rise_margin,
            'power_threshold_W': threshold, 'minimum_event_duration_seconds': 0.5,
            'drum_event_RPM': float(speed.iloc[drum_index]), 'power_event_W': float(watts.iloc[power_index]),
            'drum_event_timestamp': drum_event.isoformat(),
            'power_event_timestamp_original': power_event.isoformat(),
            'power_event_timestamp_aligned': (power_event + shift).isoformat(),
            'drum_event_elapsed_seconds': (drum_event - ops_df['datetime'].iloc[0]).total_seconds(),
            'power_event_elapsed_seconds': (power_event - power_df['datetime'].iloc[0]).total_seconds(),
            'power_start_relative_to_machine_seconds': (power_df['datetime'].iloc[0] + shift - ops_df['datetime'].iloc[0]).total_seconds(),
            'source_clock_policy': 'Align by selected events; preserve each recording\'s measured intervals, without rescaling values or time.',
        }

    def _prepare_timestamps(self, df, source):
        invalid = int(df['datetime'].isna().sum())
        duplicates = int(df['datetime'].dropna().duplicated().sum())
        if invalid:
            self.warnings.append(f'{source}: {invalid} rows without usable timestamps were excluded.')
        if duplicates:
            self.warnings.append(f'{source}: {duplicates} duplicate timestamps retained their last recorded sample.')
        return df.dropna(subset=['datetime']).sort_values('datetime', kind='stable').drop_duplicates(
            'datetime', keep='last'
        ).reset_index(drop=True)

    def _single_frame_prep(self, df):
        timestamps = extract_datetime_series(df, fallback=False)
        if timestamps.notna().sum() == 0:
            self.used_synthetic_time = True
            self.warnings.append('No usable timestamps were exported; this single file uses an assumed 1-second sample interval.')
            timestamps = pd.Series(
                pd.date_range(start='2000-01-01', periods=len(df), freq='1s'), index=df.index
            )
        df['datetime'] = timestamps
        df = self._prepare_timestamps(df, 'Data')
        if not df.empty:
            df['relative_minutes'] = (df['datetime'] - df['datetime'].min()).dt.total_seconds() / 60.0
        df.attrs['data_warnings'] = list(dict.fromkeys(self.warnings))
        df.attrs['used_synthetic_time'] = self.used_synthetic_time
        return self._binarize_controls(df)

    def _binarize_controls(self, df):
        """
        Normalize actuator values consistently: positive integers are ON/LOCKED;
        zero and inactive text values are OFF/UNLOCKED. Negative, fractional,
        missing and
        unrecognized values remain unknown, producing visible gaps in plots.
        """
        for c in df.columns:
            if not str(c).endswith('_BIN') and classify_signal_kind(c) in ('control', 'door_lock'):
                df[f"{c}_BIN"] = normalize_control_series(df[c], c)

        return df

    def get_data(self):
        return self.aligned_df

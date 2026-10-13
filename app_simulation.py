"""Simulation CSV references, independent of Tkinter and image digitization.

The supported exporter uses minutes, RPM, degC and litres by default.
The user's confirmed pressure unit for this exporter is Pa by default.
Source units are recorded separately from the requested pressure display policy.
Original-pressure mode keeps both sources numeric and uses the requested Pa label.
All samples, including equal timestamps, are kept for analysis and export.
"""
from dataclasses import dataclass
import os

import numpy as np
import pandas as pd

from app_data import DataReadError, smart_read_file, get_column_unit, convert_signal_units, normalize_control_series
from app_image_analysis import SIMULATION_LEGEND_SPECS


# Exactly the ten signals requested in the reference legend. Simulation-specific
# definitions are independent of the image digitizer's stage/relay conversions.
CSV_LEGEND_SPECS = [dict(spec) for spec in SIMULATION_LEGEND_SPECS]
for spec in CSV_LEGEND_SPECS:
    key = spec['key']
    if key == 'stwf_number':
        spec.update(label='STWF Code', unit='code', kind='code', block='Software Code',
                    bench_aliases=('stwf_number', 'stwf code'))
    elif key == 'pressure':
        spec['unit'] = 'Pa'
    elif key == 'water':
        spec.update(label='Cumulative Water', block='Cumulative Inlet Water',
                    bench_aliases=('water_amount', 'accumulated water inlet', 'cumulative water',
                                   'total water consumption', 'cumulative inlet water'))
    elif key == 'temperature':
        spec['bench_aliases'] += ('water_temp',)
    elif key == 'drain_open':
        spec['bench_aliases'] += ('drain_open',)
    elif key == 'calculated_remain_time':
        spec.update(key='actual_remaining_time', label='Actual Remaining Time',
                    bench_aliases=(), block='Remaining Time')
    elif key == 'heater_power':
        spec.update(label='Heater Power', unit='W', kind='analog', block='Heater Power',
                    bench_aliases=('heat valve', 'heater relay', 'heater state', 'heater status',
                                   'heater on', 'heater control', 'heater command', 'heating status', 'heater_power', 'heater power', 'heater watts'),
                    step=True, heater_on_reference_watts=2000.0)

CSV_COLUMNS = {
    'temperature': ('water_temp', '°C'), 'pressure': ('water_pressure', 'unknown'),
    'pre_wash_valve_open': ('pre_wash_valve_open', 'state'),
    'wash_valve_open': ('main_wash_valve_open', 'state'),
    'water': ('water_amount', 'L'), 'stwf_number': ('stwf_number', 'code'),
    'drain_open': ('drain_open', 'state'), 'drum_speed': ('drum_speed', 'RPM'),
    'heater_power': ('heater_power', 'W'),
}


def is_csv_reference(curves):
    return any(isinstance(c, pd.DataFrame) and c.attrs.get('source_type') == 'csv'
               for c in (curves or {}).values())


def actual_remaining_values(frame):
    """Countdown to this recording's end, never to an estimated program end."""
    time = pd.to_numeric(frame['time_min'], errors='coerce').replace([np.inf, -np.inf], np.nan)
    return time.max() - time


def is_simulation_frame(frame):
    signatures = {'drum_speed', 'water_volume', 'process_state', 'pre_wash_valve_open', 'vt_line'}
    return 'time' in frame and len(signatures.intersection(frame.columns)) >= 3


def specs_for_curves(curves):
    if is_csv_reference(curves):
        pressure = (curves or {}).get('pressure')
        unit = pressure.attrs.get('unit', 'unknown') if isinstance(pressure, pd.DataFrame) else 'unknown'
        specs = [dict(spec) for spec in CSV_LEGEND_SPECS]
        for spec in specs:
            if spec['key'] == 'pressure':
                spec['unit'] = unit
                spec['preserve_pressure_numbers'] = pressure.attrs.get('preserve_pressure_numbers', False) if isinstance(pressure, pd.DataFrame) else False
                if unit == 'unknown':
                    spec['label'] = 'Water Pressure (raw; unit unconfirmed)'
        return specs
    return SIMULATION_LEGEND_SPECS


@dataclass
class SimulationCsvAdapter:
    path: str
    time_unit: str = 'min'
    pressure_unit: str = 'Pa'
    remaining_time_unit: str = 'min'
    pressure_display_unit: str = 'Pa'
    preserve_pressure_numbers: bool = False
    high_resolution_time_column: str | None = None

    def __post_init__(self):
        self.frame = smart_read_file(self.path)
        if not is_simulation_frame(self.frame):
            raise DataReadError('Expected a simulation CSV with time and at least three simulator signal columns.')
        if self.frame.empty:
            raise DataReadError('The simulation CSV contains no samples.')
        unit = get_column_unit(self.frame, 'time') or self.time_unit
        times = convert_signal_units(self.frame['time'], unit, 'min')
        if not times.notna().all():
            raise DataReadError('Simulation time contains missing or non-finite values; correct the file before comparing.')
        if times.diff().lt(0).any():
            raise DataReadError('Simulation time goes backwards; split restarted runs before comparing.')
        self.time_source = 'time'
        self.time_source_note = 'Numeric time column used.'
        if self.high_resolution_time_column and self.high_resolution_time_column in self.frame:
            precise = convert_signal_units(self.frame[self.high_resolution_time_column], 's', 'min')
            valid = precise.notna().all() and not precise.diff().lt(0).any()
            consistent = valid and (precise - times).abs().le(0.0051).all()
            if consistent:
                times = precise
                self.time_source = self.high_resolution_time_column
                self.time_source_note = 'Documented seconds counter agrees with rounded minutes; precise timestamps used.'
            else:
                self.time_source_note = 'Precise counter inconsistent or invalid; original time column retained.'
        self.frame['time_min'] = times - times.iloc[0]
        self.duration_min = float(self.frame['time_min'].iloc[-1])
        if self.duration_min <= 0:
            raise DataReadError('Simulation CSV must span a positive duration.')
        self.curves = {}
        source_units = {}
        for spec in CSV_LEGEND_SPECS:
            key = spec['key']
            if key == 'actual_remaining_time':
                values = actual_remaining_values(self.frame)
                source, source_unit = 'calculated from cycle end', 'min'
            else:
                source, source_unit = CSV_COLUMNS[key]
                if source not in self.frame:
                    continue
                if key == 'pressure':
                    source_unit = self.pressure_unit
                source_unit = get_column_unit(self.frame, source) or source_unit
                source_units[source] = source_unit
                target_unit = ('unknown' if source_unit == 'unknown' else self.pressure_display_unit) if key == 'pressure' else spec['unit']
                if key == 'pressure' and self.preserve_pressure_numbers:
                    target_unit = 'Pa'
                    values = pd.to_numeric(self.frame[source], errors='coerce').replace([np.inf, -np.inf], np.nan)
                elif spec['kind'] == 'digital':
                    values = normalize_control_series(self.frame[source], source)
                elif target_unit == 'unknown':
                    values = pd.to_numeric(self.frame[source], errors='coerce').replace([np.inf, -np.inf], np.nan)
                else:
                    values = convert_signal_units(self.frame[source], source_unit, target_unit)
            if key == 'actual_remaining_time':
                target_unit = 'min'
            curve = pd.DataFrame({'time_min': self.frame['time_min'], 'value': values})
            curve.attrs.update(source_type='csv', source_column=source, source_unit=source_unit,
                               unit=target_unit, x_calibration_verified=True,
                               y_calibration_verified=target_unit != 'unknown')
            if key == 'pressure':
                curve.attrs['preserve_pressure_numbers'] = self.preserve_pressure_numbers
            self.curves[key] = curve
        self.frame.attrs['column_units'] = {**self.frame.attrs.get('column_units', {}), **source_units}
        self.frame.attrs['simulation_csv'] = True
        self.frame.attrs['comparison_data_quality'] = {'duplicate_policy': 'Every sample retained in metrics and export.'}

    def extract_curves(self):
        return self.curves

    def analysis_info(self):
        return {'source_type': 'csv', 'source_path': os.path.abspath(self.path),
                'rows': len(self.frame), 'duration_min': self.duration_min,
                'duplicate_time_rows': int(self.frame['time_min'].duplicated().sum()),
                'time_unit': get_column_unit(self.frame, 'time') or self.time_unit,
                'time_source': self.time_source, 'time_source_note': self.time_source_note,
                'pressure_unit': self.frame.attrs['column_units'].get('water_pressure'),
                'remaining_time_source': 'Recording end minus elapsed time; estimated/display countdowns unused',
                'pressure_display_unit': self.curves.get('pressure', pd.DataFrame()).attrs.get('unit'),
                'preserve_pressure_numbers': self.preserve_pressure_numbers,
                'cursor_duplicate_policy': 'Last sample at equal timestamp; all transitions retained in charts/counts.',
                'unit_policy': ('Pressure numbers unchanged for both sources; Pa is the requested display label. Source units are recorded separately.'
                                if self.preserve_pressure_numbers else
                                'ZIP definitions and explicit CSV units are recorded; declared units determine conversion.')}

    def report_dataframe(self):
        return pd.DataFrame([{'signal': spec['label'], 'source_column': self.curves[spec['key']].attrs['source_column'],
                              'unit': self.curves[spec['key']].attrs['unit'], 'rows': len(self.curves[spec['key']]),
                              'known_fraction': float(self.curves[spec['key']]['value'].notna().mean())}
                             for spec in specs_for_curves(self.curves) if spec['key'] in self.curves])


def display_samples(times, values, kind, target=10000):
    """Reduce plotting only: retain every state edge and analog bin extrema."""
    times, values = np.asarray(times, dtype=float), np.asarray(values, dtype=float)
    if len(times) <= 2:
        return times, values
    if kind in ('digital', 'stage', 'code', 'step'):
        changes = (values[1:] != values[:-1]) & ~(np.isnan(values[1:]) & np.isnan(values[:-1]))
        indices = np.unique(np.r_[0, np.flatnonzero(changes), np.flatnonzero(changes) + 1, len(times) - 1])
    elif len(times) > target:
        indices = [0, len(times) - 1]
        # Gaps and isolated observations must remain visible.
        gap_edges = np.flatnonzero(np.isfinite(values[1:]) != np.isfinite(values[:-1]))
        indices.extend(gap_edges)
        indices.extend(gap_edges + 1)
        for chunk in np.array_split(np.arange(len(times)), max(1, target // 4)):
            finite = chunk[np.isfinite(values[chunk])]
            indices.extend((chunk[0], chunk[-1]))
            if len(finite):
                indices.extend((finite[np.argmin(values[finite])], finite[np.argmax(values[finite])]))
        indices = np.unique(indices)
    else:
        return times, values
    return times[indices], values[indices]


def load_simulation_reference(path, **settings):
    """Use run-specific package definitions when a ZIP is selected."""
    if str(path).lower().endswith('.zip'):
        from app_simulation_package import SimulationPackageAdapter
        settings.setdefault('pressure_unit', 'unknown')
        return SimulationPackageAdapter(path, **settings)
    return SimulationCsvAdapter(path, **settings)

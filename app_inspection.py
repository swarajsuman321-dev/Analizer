"""Cursor sampling that respects step states and missing observations."""

import numpy as np
import pandas as pd

from app_data import (normalize_control_series, normalize_program_stage_series, infer_pressure_units,
                      get_column_unit, convert_signal_units, find_power_column, find_energy_column,
                      find_column_by_keywords)


def prepare_trace(times, values, kind='analog'):
    times = pd.to_numeric(pd.Series(times), errors='coerce').to_numpy(dtype=float, na_value=np.nan)
    values = pd.to_numeric(pd.Series(values), errors='coerce').to_numpy(dtype=float, na_value=np.nan)
    if len(times) != len(values):
        raise ValueError('Cursor time and value arrays must have the same length.')
    valid_time = np.isfinite(times)
    times, values = times[valid_time], values[valid_time]
    order = np.argsort(times, kind='stable')
    times, values = times[order], values[order]
    if times.size:
        keep = np.r_[times[1:] != times[:-1], True]
        times, values = times[keep], values[keep]
    return times, values, kind


def sample_trace(trace, when):
    if trace is None or when is None or not np.isfinite(when):
        return np.nan
    times, values, kind = trace
    if not len(times) or when < times[0] or when > times[-1]:
        return np.nan
    left = int(np.searchsorted(times, when, side='right') - 1)
    if kind in ('digital', 'lock', 'stage', 'code', 'step') or times[left] == when or left == len(times) - 1:
        return float(values[left])
    right = left + 1
    if not np.isfinite(values[left]) or not np.isfinite(values[right]):
        return np.nan
    fraction = (when - times[left]) / (times[right] - times[left])
    return float(values[left] + fraction * (values[right] - values[left]))


def format_sample(value, kind='analog', unit=''):
    if not np.isfinite(value):
        return '—'
    if kind == 'lock':
        return 'LOCKED' if value > 0 else 'UNLOCKED'
    if kind == 'digital':
        return 'ON' if value > 0 else 'OFF'
    if kind == 'code':
        return f'{value:g}'
    if kind == 'stage':
        return {1: '1 · Wash', 2: '2 · Rinse', 3: '3 · Spin'}.get(int(value), '—')
    return f'{value:.2f}' + (f' {unit}' if unit else '')


def comparison_traces(raw_df, sim_curves, bench_columns, specs):
    traces = {}
    from app_comparator import ComparisonEngine
    for spec in specs:
        kind = spec['kind']
        sim = sim_curves.get(spec['key'])
        sim_kind = 'step' if spec.get('step') else kind
        sim_trace = (prepare_trace(sim['time_min'], sim['value'], sim_kind)
                     if isinstance(sim, pd.DataFrame) and not sim.empty else None)
        column = bench_columns.get(spec['key'])
        bench_trace = None
        bench_kind = 'digital' if spec['key'] == 'heater_power' and ComparisonEngine.heater_bench_is_state(raw_df,column) else kind
        if column in raw_df.columns:
            values = ComparisonEngine._bench_values(raw_df, spec['key'], column, specs)
            bench_trace = prepare_trace(raw_df['time_min'], values, bench_kind)
        traces[spec['key']] = {'sim': sim_trace, 'bench': bench_trace, 'bench_kind': bench_kind}
    return traces


def format_comparison_samples(spec, sim, bench, bench_kind=None):
    kind = spec['kind']
    unit = spec['unit'] if spec['unit'] not in ('state','stage','code') else ''
    if spec['key'] == 'heater_power' and spec['unit'] == 'W' and bench_kind == 'digital':
        sim_text = (format_sample(sim, unit='W') + (' · ON' if sim > 0 else ' · OFF')) if np.isfinite(sim) else '—'
        bench_text = format_sample(bench, 'digital')
        difference = ('MATCH' if (sim > 0) == (bench > 0) else 'DIFFERENT') if np.isfinite(sim) and np.isfinite(bench) else '—'
        return sim_text, bench_text, difference
    difference = '—'
    if np.isfinite(sim) and np.isfinite(bench):
        difference = ('MATCH' if sim == bench else 'DIFFERENT') if kind in ('digital','stage','code') else f'{bench - sim:+.2f} {unit}'.strip()
    return format_sample(sim,kind,unit), format_sample(bench,kind,unit), difference


def engineering_metrics(frame):
    """Compute metrics without substituting zero for unrecorded samples."""
    time = pd.to_numeric(frame['relative_minutes'], errors='coerce')
    valid_time = time[np.isfinite(time)]
    if valid_time.empty:
        return [('Total Cycle Duration', 'Unavailable')]
    duration = float(valid_time.max() - valid_time.min())
    rows = [('Total Cycle Duration', f'{duration:.2f} Minutes')]
    power_col = find_power_column(frame.columns)
    energy_col = find_energy_column(frame.columns)
    integrated_wh = None
    if power_col is not None:
        power = convert_signal_units(frame[power_col], get_column_unit(frame, power_col), 'W')
        times, values, _kind = prepare_trace(time, power)
        finite = np.isfinite(values)
        if finite.any():
            rows.append(('Peak Real Power', f'{values[finite].max():.1f} W'))
            intervals = np.diff(times)
            usable = finite[:-1] & finite[1:] & (intervals > 0)
            covered_min = float(intervals[usable].sum())
            if covered_min > 0:
                integral = float(np.sum((values[:-1][usable] + values[1:][usable]) * 0.5 * intervals[usable]))
                integrated_wh = integral / 60.0
                rows.append(('Average Real Power (time weighted)', f'{integral / covered_min:.1f} W'))
                rows.append(('Power Integration Coverage', f'{100 * covered_min / duration:.1f}%' if duration > 0 else 'Single sample'))
            else:
                rows.append(('Average Real Power', 'Insufficient timed samples'))
    if energy_col is not None:
        energy = convert_signal_units(frame[energy_col], get_column_unit(frame, energy_col), 'Wh')
        _times, values, _kind = prepare_trace(time, energy)
        values = values[np.isfinite(values)]
        if len(values) > 1:
            differences = np.diff(values)
            resets = differences < 0
            increments = np.where(resets, np.maximum(values[1:], 0), differences)
            consumed = float(increments.sum())
            rows.append(('Energy Counter Increase', f'{consumed:.2f} Wh ({consumed / 1000:.3f} kWh)'))
            if resets.any():
                rows.append(('Energy Counter Resets', f'{resets.sum()} · increase assumes each reset starts at zero'))
        else:
            rows.append(('Energy Counter Increase', 'Insufficient counter readings'))
    elif integrated_wh is not None:
        rows.append(('Energy over Valid Power Intervals', f'{integrated_wh:.2f} Wh ({integrated_wh / 1000:.3f} kWh)'))
    for keywords, label, unit in (
        (['current temp', 'current temperature', 'water temp'], 'Maximum Temperature', '°C'),
        (['drum speed', 'rpm', 'drehzahl', 'drump'], 'Maximum Drum Speed', 'RPM'),
    ):
        column = find_column_by_keywords(frame.columns, keywords)
        if column is not None:
            values = convert_signal_units(frame[column], get_column_unit(frame, column), unit).dropna()
            if not values.empty:
                rows.append((label, f'{values.max():.1f} {unit}'))
    return rows

import os
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from app_data import (
    normalize_control_series, normalize_program_stage_series, infer_pressure_units,
    classify_signal_kind, get_column_unit, convert_signal_units,
)
from app_layout import SignalFigureLayout, set_signal_time_bounds
from app_figure_interaction import enable_draggable_legend
from app_signal_specs import SIMULATION_LEGEND_SPECS

from app_simulation import CSV_LEGEND_SPECS, specs_for_curves, display_samples, is_csv_reference, actual_remaining_values



class ComparisonEngine:
    """
    Evaluates physical test logs against CSV or image reference curves,
    calculating variances, percentage deviations, and pass/fail scorecards.
    """
    @staticmethod
    def _recording_gap_limit(time_values):
        """Allow normal variable cadence while retaining a guard for outages."""
        times = np.asarray(time_values, dtype=float)
        positive = np.diff(times)
        positive = positive[np.isfinite(positive) & (positive > 0)]
        if not len(positive):
            return np.inf
        # A global median underestimated the slower portion of this logger.
        # With short recordings, use the median so one outage cannot dominate.
        cadence = np.quantile(positive, 0.9) if len(positive) >= 20 else np.median(positive)
        return float(cadence * 5)

    @staticmethod
    def _last_sustained_threshold_entry(time_values, value_values, threshold, min_duration=0.5):
        """Find the start of the final sustained segment above a threshold."""
        times = pd.to_numeric(pd.Series(time_values), errors='coerce').to_numpy(dtype=float, na_value=np.nan)
        values = pd.to_numeric(pd.Series(value_values), errors='coerce').to_numpy(dtype=float, na_value=np.nan)
        valid = np.isfinite(times)
        if not np.any(valid):
            return np.nan

        order = np.argsort(times[valid], kind='stable')
        times = times[valid][order]
        ordered_values = values[valid][order]
        active = np.isfinite(ordered_values) & (ordered_values > threshold)
        gaps = np.diff(times)
        breaks = np.r_[True, gaps > ComparisonEngine._recording_gap_limit(times)]
        starts = np.flatnonzero(active & (breaks | ~np.r_[False, active[:-1]]))
        ends = np.flatnonzero(active & (np.r_[breaks[1:], True] | ~np.r_[active[1:], False]))
        if not len(starts):
            return np.nan

        durations = times[ends] - times[starts]
        sustained = np.flatnonzero(durations >= min_duration)
        if not len(sustained):
            return np.nan
        return float(times[starts[sustained[-1]]])

    @staticmethod
    def _active_duration_minutes(time_values, active_values):
        """Integrate a sampled on/off signal using each sample's time interval."""
        times = pd.to_numeric(pd.Series(time_values), errors='coerce').to_numpy(dtype=float, na_value=np.nan)
        active = pd.to_numeric(pd.Series(active_values), errors='coerce').to_numpy(dtype=float, na_value=np.nan)
        if len(times) != len(active):
            return np.nan
        valid = np.isfinite(times)
        times, active = times[valid], active[valid]
        if not len(times):
            return np.nan
        order = np.argsort(times, kind='stable')
        times, active = times[order], active[order]
        intervals = np.diff(times)
        positive = intervals[intervals > 0]
        if not np.isfinite(active).all():
            return np.nan
        if len(positive) and np.any(intervals > ComparisonEngine._recording_gap_limit(times)):
            return np.nan
        # The final timestamp closes the observed range; do not invent an
        # additional interval after the recording ended.
        return float(intervals[(active[:-1] > 0) & (intervals > 0)].sum())

    @staticmethod
    def apply_pressure_default(raw_df, unit='mbar'):
        """Attach fallback unit metadata only where no unit was declared."""
        inferred = infer_pressure_units(raw_df)
        units = dict(raw_df.attrs.get('column_units', {}))
        for column, detected in inferred.items():
            declared = get_column_unit(raw_df,column)
            if declared in (None,'unknown'):
                # Persist the paired raw channel too: declaring the physical
                # channel must not make its pulse-period partner look unknown.
                units[column] = 'µs' if detected == 'µs' else unit
        raw_df.attrs['column_units'] = units

    @staticmethod
    def heater_bench_is_state(raw_df, column):
        """A bench relay state is not a measurement of heater watts."""
        if column is None or column not in raw_df:
            return False
        if get_column_unit(raw_df, column) in ('W', 'kW'):
            return False
        name = str(column).lower()
        if any(word in name for word in ('relay', 'valve', 'state', 'status', 'on/off', 'on off', 'heater on')):
            return True
        values = raw_df[column].dropna()
        if values.empty:
            return False
        words = values.astype(str).str.strip().str.lower()
        if words.isin(('on','off','true','false','active','inactive','1','0','1.0','0.0')).all():
            return True
        return False

    @staticmethod
    def heater_state_report(raw_df, sim_curves):
        specs = specs_for_curves(sim_curves)
        column = ComparisonEngine.find_bench_columns(raw_df, specs).get('heater_power')
        frames = []
        sim = sim_curves.get('heater_power')
        if isinstance(sim, pd.DataFrame) and not sim.empty:
            power = pd.to_numeric(sim['value'], errors='coerce')
            frames.append(pd.DataFrame({'source':'Simulation','time_min':sim['time_min'],
                                         'heater_on':np.where(power.notna(),power.gt(0),np.nan),
                                         'recorded_power_W':power if sim.attrs.get('unit') == 'W' else np.nan}))
        if column is not None:
            values = ComparisonEngine._bench_values(raw_df,'heater_power',column,specs)
            state = ComparisonEngine.heater_bench_is_state(raw_df,column)
            frames.append(pd.DataFrame({'source':'Bench','time_min':raw_df['time_min'],
                                         'heater_on':np.where(values.notna(),values.gt(0),np.nan),
                                         'recorded_power_W':np.nan if state else values}))
        return pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()

    @staticmethod
    def _bench_values(raw_df, key, column, specs=None):
        if key == 'actual_remaining_time':
            return actual_remaining_values(raw_df)
        source = raw_df[column]
        spec = next(spec for spec in (specs or CSV_LEGEND_SPECS) if spec['key'] == key)
        if key == 'heater_power' and ComparisonEngine.heater_bench_is_state(raw_df, column):
            return normalize_control_series(source, column)
        if spec['kind'] == 'digital':
            return normalize_control_series(source, column)
        if spec['kind'] == 'stage':
            return normalize_program_stage_series(source)
        if key == 'pressure' and spec.get('preserve_pressure_numbers'):
            return pd.to_numeric(source, errors='coerce').replace([np.inf, -np.inf], np.nan)
        unit = get_column_unit(raw_df, column)
        if key == 'pressure':
            unit = infer_pressure_units(raw_df).get(column)
        return convert_signal_units(source, unit, spec['unit'])

    @staticmethod
    def _activation_count(values):
        numeric = pd.to_numeric(pd.Series(values), errors='coerce').to_numpy(dtype=float, na_value=np.nan)
        if not len(numeric) or not np.isfinite(numeric).any():
            return np.nan, False
        active = numeric > 0
        known = np.isfinite(numeric)
        previous_off = np.r_[True, known[:-1] & ~active[:-1]]
        return int(np.count_nonzero(active & known & previous_off)), bool(known.all())

    @staticmethod
    def _combined_controls(frames):
        """Combine valve states using three-valued OR; hidden pixels stay unknown."""
        if not frames:
            return pd.Series(dtype=float)
        shared_index = frames[0].index
        for frame in frames[1:]:
            shared_index = shared_index.union(frame.index)
        shared_index = shared_index.sort_values()
        aligned = []
        for frame in frames:
            aligned_frame = frame.reindex(shared_index, method='ffill')
            if not frame.empty:
                aligned_frame.loc[(shared_index < frame.index.min()) | (shared_index > frame.index.max())] = np.nan
            aligned.append(aligned_frame)
        states = pd.concat(aligned, axis=1)
        combined = pd.Series(np.nan, index=states.index, dtype=float)
        combined.loc[states.eq(0).all(axis=1)] = 0.0
        combined.loc[states.eq(1).any(axis=1)] = 1.0
        return combined

    @staticmethod
    def _calibration_flags(curve):
        """Missing confirmation metadata is unverified, even for a known profile."""
        if not isinstance(curve, pd.DataFrame):
            return {'x_calibration_verified': False, 'y_calibration_verified': False,
                    'calibration_verified': False}
        metadata = curve.attrs.get('analysis_metadata', {})
        metadata = metadata if isinstance(metadata, dict) else {}
        flags = {}
        for key in ('x_calibration_verified', 'y_calibration_verified'):
            value = curve.attrs.get(key, metadata.get(key, False))
            flags[key] = isinstance(value, (bool, np.bool_)) and bool(value)
        flags['calibration_verified'] = all(flags.values())
        return flags

    @staticmethod
    def difference_band(percent):
        """Display bands describe absolute difference, never acceptance."""
        if not np.isfinite(percent):
            return 'VALUE'
        magnitude = abs(float(percent))
        return 'GREEN' if magnitude < 10 else 'YELLOW' if magnitude <= 20 else 'RED'

    @staticmethod
    def generate_scorecard(raw_df, sim_curves, tolerances=None):
        """Report values, signed differences and the user's fixed colour bands.

        The legacy tolerances argument remains accepted for saved projects;
        it does not define acceptance or override the difference colours.
        """
        if raw_df is None or raw_df.empty or 'time_min' not in raw_df.columns:
            raise ValueError('Raw test data must contain rows and a time_min column.')
        if not isinstance(sim_curves, dict):
            raise ValueError('Simulation reference curves must be provided by signal name.')
        specs = specs_for_curves(sim_curves)
        csv_reference = is_csv_reference(sim_curves)
        sim_curves = {key: curve for key, curve in sim_curves.items() if isinstance(curve, pd.DataFrame)}
        raw_df = raw_df.copy()
        raw_df['time_min'] = pd.to_numeric(raw_df['time_min'], errors='coerce').astype(float)
        excluded = int((~np.isfinite(raw_df['time_min'])).sum())
        duplicates = int(raw_df['time_min'].dropna().duplicated().sum())
        raw_df = raw_df.loc[np.isfinite(raw_df['time_min'])].sort_values('time_min', kind='stable').reset_index(drop=True)
        times = raw_df['time_min']
        if times.empty:
            raise ValueError('The raw test file does not contain usable time values.')
        columns = ComparisonEngine.find_bench_columns(raw_df, specs)
        rows = []

        def curve_values(key):
            curve = sim_curves.get(key, pd.DataFrame())
            values = pd.to_numeric(curve.get('value', pd.Series(dtype=float)), errors='coerce').astype(float)
            return values.replace([np.inf, -np.inf], np.nan)

        def bench_values(key):
            column = columns.get(key)
            return (ComparisonEngine._bench_values(raw_df, key, column, specs).replace([np.inf, -np.inf], np.nan)
                    if column is not None else pd.Series(dtype=float))

        def complete(values):
            return not values.empty and values.notna().all()

        def percent_text(value):
            if not np.isfinite(value):
                return '—'
            # Avoid displaying 10.00% in green, or 20.00% in red, when rounding
            # would conceal which side of the requested boundary a value lies.
            for precision in (2, 4, 8):
                rounded = round(float(value), precision)
                if ComparisonEngine.difference_band(rounded) == ComparisonEngine.difference_band(value):
                    return f'{value:+.{precision}f}%'
            return f'{value:+.12g}%'

        def add_value(label, sim, bench, unit, note='', verified=True):
            difference = bench - sim if np.isfinite(sim) and np.isfinite(bench) else np.nan
            percent = difference / abs(sim) * 100 if np.isfinite(difference) and sim != 0 else np.nan
            status = ('MISSING' if not np.isfinite(difference) else 'REVIEW' if not verified
                      else ComparisonEngine.difference_band(percent))
            if np.isfinite(difference) and sim == 0:
                note = (note + '; ' if note else '') + 'Percentage undefined: simulation value is zero'
            rows.append({'parameter':label,
                         'sim_val':f'{sim:.2f} {unit}'.strip() if np.isfinite(sim) else 'Unavailable',
                         'raw_val':f'{bench:.2f} {unit}'.strip() if np.isfinite(bench) else 'Unavailable',
                         'delta':f'{difference:+.2f} {unit}'.strip() if np.isfinite(difference) else '—',
                         'percent':percent_text(percent), 'notes':note, 'status':status})

        def add_count(label, sim_states, bench_states, note='', sources_complete=True):
            sim_count, sim_complete = ComparisonEngine._activation_count(sim_states)
            bench_count, bench_complete = ComparisonEngine._activation_count(bench_states)
            known = sim_complete and bench_complete and sources_complete
            def text(count, covered):
                return (f'{count:g} activations' if covered else f'≥{count:g} observed') if np.isfinite(count) else 'Unavailable'
            rows.append({'parameter':label, 'sim_val':text(sim_count, sim_complete and sources_complete),
                         'raw_val':text(bench_count, bench_complete and sources_complete),
                         'delta':f'{bench_count - sim_count:+g}' if known else '—', 'percent':'—',
                         'notes':note if known else (note + '; ' if note else '') + 'Incomplete actuator coverage',
                         'status':'VALUE' if known else 'REVIEW'})

        time_curves = [curve for curve in sim_curves.values() if not curve.empty and 'time_min' in curve]
        sim_times = pd.concat([pd.to_numeric(curve['time_min'], errors='coerce') for curve in time_curves], ignore_index=True) if time_curves else pd.Series(dtype=float)
        sim_times = sim_times.loc[np.isfinite(sim_times)]
        sim_duration = float(sim_times.max() - sim_times.min()) if not sim_times.empty else np.nan
        bench_duration = float(times.max() - times.min())
        reference_time_verified = bool(time_curves) and all(ComparisonEngine._calibration_flags(curve)['x_calibration_verified'] for curve in time_curves)
        quality = raw_df.attrs.get('comparison_data_quality', {})
        bench_time_verified = (len(times) >= 2 and not raw_df.attrs.get('used_synthetic_time', False)
                               and excluded == 0 and quality.get('invalid_timestamp_rows_excluded', 0) == 0)
        add_value('Total Cycle Duration', sim_duration, bench_duration, 'min', 'First to last recorded sample', reference_time_verified and bench_time_verified)

        sim_speed, bench_speed = curve_values('drum_speed').abs(), bench_values('drum_speed').abs()
        speed_flags = ComparisonEngine._calibration_flags(sim_curves.get('drum_speed'))
        sim_peak = float(sim_speed.max()) if not sim_speed.empty else np.nan
        bench_peak = float(bench_speed.max()) if not bench_speed.empty else np.nan
        speed_note = f'Bench: {columns.get("drum_speed") or "speed channel absent"}'
        add_value('Peak Spin Extraction Speed', sim_peak, bench_peak, 'RPM', speed_note,
                  complete(sim_speed) and complete(bench_speed) and speed_flags['y_calibration_verified'])
        sim_curve = sim_curves.get('drum_speed', pd.DataFrame())
        sim_spin = ComparisonEngine._last_sustained_threshold_entry(sim_curve['time_min'], sim_speed, 600) if 'time_min' in sim_curve else np.nan
        bench_spin = ComparisonEngine._last_sustained_threshold_entry(times, bench_speed, 600) if not bench_speed.empty else np.nan
        add_value('Final Sustained >600 RPM Start', sim_spin, bench_spin, 'min', 'Last period >600 RPM lasting at least 30 s',
                  complete(sim_speed) and complete(bench_speed) and speed_flags['calibration_verified'] and bench_time_verified)

        for key, label in [('temperature','Peak Water Temperature'), ('pressure','Peak Water Pressure')]:
            sim_values, raw_values = curve_values(key), bench_values(key)
            spec = next(spec for spec in specs if spec['key'] == key)
            flags = ComparisonEngine._calibration_flags(sim_curves.get(key))
            note = f'Bench: {columns.get(key) or "channel absent"}'
            if key == 'pressure' and spec.get('preserve_pressure_numbers'):
                note += '; original numbers, Pa display label'
            add_value(label, float(sim_values.max()) if not sim_values.empty else np.nan,
                      float(raw_values.max()) if not raw_values.empty else np.nan, spec['unit'],
                      note, complete(sim_values) and complete(raw_values) and flags['y_calibration_verified'])

        raw_heat = bench_values('heater_power')
        # Relay states (including raw 128) are normalized before integration;
        # measured watt channels remain numeric and are active above 0 W.
        raw_heat_mask = np.where(raw_heat.notna(), raw_heat.gt(0), np.nan)
        raw_heat_duration = ComparisonEngine._active_duration_minutes(times, raw_heat_mask) if not raw_heat.empty else np.nan
        sim_heat = sim_curves.get('heater_power', pd.DataFrame())
        sim_heat_values = curve_values('heater_power')
        sim_heat_duration = ComparisonEngine._active_duration_minutes(sim_heat['time_min'], np.where(sim_heat_values.notna(), sim_heat_values.gt(0), np.nan)) if 'time_min' in sim_heat else np.nan
        add_value('Total Heating Active Duration', sim_heat_duration, raw_heat_duration, 'min',
                  'Sum of ON sample intervals; bench positive integer states include 128',
                  reference_time_verified and bench_time_verified)

        for key, label in [('pre_wash_valve_open','Pre-wash Valve Activations'), ('wash_valve_open','Main-wash Valve Activations')]:
            add_count(label, curve_values(key), bench_values(key), f'Bench: {columns.get(key) or "channel absent"}')

        intake_keys = ('pre_wash_valve_open','wash_valve_open')
        bench_intake = [bench_values(key) for key in intake_keys if columns.get(key) is not None]
        sim_intake = []
        intake_curves = [sim_curves.get(key, pd.DataFrame()) for key in intake_keys]
        shared = all({'time_min','value'}.issubset(curve.columns) for curve in intake_curves)
        shared = shared and all(curve['time_min'].reset_index(drop=True).equals(intake_curves[0]['time_min'].reset_index(drop=True)) for curve in intake_curves[1:])
        for curve in intake_curves:
            if not curve.empty and {'time_min','value'}.issubset(curve.columns):
                frame = curve[['time_min','value']].apply(pd.to_numeric, errors='coerce')
                if shared:
                    values = frame['value'].reset_index(drop=True)
                else:
                    frame = frame.loc[np.isfinite(frame['time_min'])].sort_values('time_min', kind='stable').drop_duplicates('time_min', keep='last')
                    values = pd.Series(frame['value'].to_numpy(dtype=float), index=frame['time_min'])
                sim_intake.append(values)
        add_count('Water Intake Bursts', ComparisonEngine._combined_controls(sim_intake), ComparisonEngine._combined_controls(bench_intake),
                  'Either inlet valve ON; simultaneous valve operation counts once', len(sim_intake) == 2 and len(bench_intake) == 2)
        add_count('Drain Pump Evacuations', curve_values('drain_open'), bench_values('drain_open'), f'Bench: {columns.get("drain_open") or "channel absent"}')

        if csv_reference:
            sim_water, bench_water = curve_values('water'), bench_values('water')
            add_value('Cumulative Inlet Water', float(sim_water.iloc[-1]) if not sim_water.empty else np.nan,
                      float(bench_water.iloc[-1]) if not bench_water.empty else np.nan, 'L',
                      f'Bench: {columns.get("water") or "cumulative water not recorded"}', complete(sim_water) and complete(bench_water))

        result = pd.DataFrame(rows)
        result.attrs.update(benchmark_duration=bench_duration, reference_duration=sim_duration,
                            benchmark_peak_rpm=bench_peak, reference_peak_rpm=sim_peak,
                            benchmark_peak_text=f'{bench_peak:.0f} RPM' if np.isfinite(bench_peak) else 'Unavailable',
                            reference_peak_text=(f'{sim_peak:.0f} RPM' + (' (CSV)' if csv_reference else ' (image estimate)')) if np.isfinite(sim_peak) else 'Unavailable',
                            difference_policy='Signed percentage = (bench - simulation) / abs(simulation) * 100; zero simulation leaves percentage unavailable',
                            colour_bands={'GREEN':'abs difference <10%', 'YELLOW':'10% <= abs difference <=20%', 'RED':'abs difference >20%'},
                            calibration={'reference_time_verified':reference_time_verified, 'benchmark_time_verified':bench_time_verified,
                                         'sim':{key:ComparisonEngine._calibration_flags(curve) for key,curve in sim_curves.items()}},
                            bench_gap_limit_seconds=ComparisonEngine._recording_gap_limit(times) * 60,
                            assumptions=[('Simulation values use full-resolution CSV samples and declared exporter units.' if csv_reference else 'Simulation values are estimates digitized from image pixels.'),
                                         'Colour bands describe percentage difference; no acceptance limits or pass/fail verdicts.',
                                         'Positive integer actuator states are ON; zero is OFF. Raw heater state 128 is ON.',
                                         'Final sustained speed entry uses absolute speed >600 RPM for at least 0.5 minutes.',
                                         'Cadence guard uses five times the 90th percentile positive interval for 20 or more intervals, otherwise five times the median.',
                                         'Missing actuator states remain unknown; incomplete counts are lower bounds.',
                                         'Heating duration is unavailable when unknown states or a true recording gap prevents complete integration.'] + list(raw_df.attrs.get('data_warnings', [])))
        if excluded:
            result.attrs['assumptions'].append(f'{excluded} rows with invalid elapsed time excluded.')
        if duplicates:
            result.attrs['assumptions'].append(f'{duplicates} duplicate elapsed timestamps retained; zero-duration intervals add no ON time.')
        result.attrs['coverage'] = {'bench':{}, 'sim':{}}
        for spec in specs:
            key = spec['key']
            if columns.get(key) is not None:
                values = bench_values(key)
                result.attrs['coverage']['bench'][key] = float(values.notna().mean())
            values = curve_values(key)
            if not values.empty:
                result.attrs['coverage']['sim'][key] = float(values.notna().mean())
        return result

    @staticmethod
    def find_bench_columns(raw_df, specs=None):
        """Match simulation traces to semantically and dimensionally compatible bench columns."""
        def normalize(value):
            return re.sub(r'[^a-z0-9]+', '', str(value).lower())

        specs = specs or SIMULATION_LEGEND_SPECS
        columns = list(raw_df.columns)
        normalized = {column: normalize(column) for column in columns}
        pressure_units = infer_pressure_units(raw_df)
        result = {}
        for spec in specs:
            if spec['key'] == 'drum_speed':
                feedback = [column for column in columns
                            if 'feedback' in normalized[column]
                            and ('drum' in normalized[column] or normalized[column] in ('speedfeedback','rpmfeedback'))
                            and not str(column).endswith('_BIN')]
                if feedback:
                    feedback.sort(key=lambda column: normalized[column] not in ('drumpspeedfeedback','drumspeedfeedback'))
                    result[spec['key']] = next((column for column in feedback
                                               if pd.to_numeric(raw_df[column], errors='coerce').notna().any()), feedback[0])
                    continue
            if spec['key'] == 'actual_remaining_time':
                result[spec['key']] = ('time_min' if 'time_min' in raw_df
                                       and np.isfinite(pd.to_numeric(raw_df['time_min'], errors='coerce')).any() else None)
                continue
            aliases = [normalize(alias) for alias in spec['bench_aliases']]
            if spec['key'] == 'pressure':
                if spec['unit'] == 'unknown':
                    result[spec['key']] = None
                    continue
                candidates = []
                for column in columns:
                    name = str(column).strip().lower()
                    words = set(re.findall(r'[a-z0-9]+', name))
                    if words.intersection({'dst', 'dest', 'target', 'set', 'setpoint'}):
                        continue
                    if pressure_units.get(column) not in ('mbar', 'bar', 'Pa', 'kPa'):
                        continue
                    if not any(alias and (normalized[column] == alias or alias in normalized[column]) for alias in aliases):
                        continue
                    raw_values = raw_df[column]
                    if isinstance(raw_values, pd.DataFrame):
                        raw_values = raw_values.iloc[:, 0]
                    numeric = pd.to_numeric(raw_values, errors='coerce')
                    median = float(numeric.dropna().abs().median()) if numeric.notna().any() else np.inf
                    explicit_mbar = bool(re.search(r'\b(?:mbar|millibars?)\b', name))
                    candidates.append((column, explicit_mbar, median))
                if candidates:
                    candidates.sort(key=lambda item: (not item[1], item[2]))
                    result[spec['key']] = candidates[0][0]
                else:
                    # A pulse-period column is not a valid mbar reference and
                    # should remain unmatched instead of being compared silently.
                    result[spec['key']] = None
                continue

            eligible = []
            for column in columns:
                name = str(column).lower()
                words = set(re.findall(r'[a-z0-9]+', name))
                if not any(alias and alias in normalized[column] for alias in aliases):
                    continue
                if str(column).endswith('_BIN') or words.intersection({'dst', 'dest', 'destination', 'target', 'setpoint'}):
                    continue
                if spec['key'] == 'calculated_remain_time' and 'display' in normalized[column]:
                    continue
                if spec['key'] == 'temperature' and words.intersection({'motor', 'ambient', 'cabinet', 'evap'}):
                    continue
                if (spec['kind'] == 'digital' and classify_signal_kind(column) not in ('control', 'door_lock')
                        and normalized[column] not in aliases):
                    continue
                if spec['unit'] == 'unknown' and get_column_unit(raw_df, column) not in (None, 'unknown'):
                    continue
                try:
                    values = ComparisonEngine._bench_values(raw_df, spec['key'], column, specs)
                except (ValueError, TypeError):
                    continue
                if values.notna().any():
                    eligible.append(column)
            exact = next(
                (column for alias in aliases for column in eligible if normalized[column] == alias),
                None
            )
            if exact is None:
                exact = next(
                    (column for alias in aliases for column in eligible if alias and alias in normalized[column]),
                    None
                )
            result[spec['key']] = exact
        for key,column in raw_df.attrs.get('bench_column_overrides',{}).items():
            if key not in result:raise ValueError(f'Unknown bench mapping: {key}')
            if column is not None and column not in raw_df:raise ValueError(f'Mapped bench column is missing: {column}')
            result[key]=column
        return result

    @staticmethod
    def render_comparison_figure(
        raw_df, sim_curves, visibility=None, bench_columns=None, actuator_analysis=None
    ):
        """Render visible image-legend signals against their matched bench traces."""
        specs = specs_for_curves(sim_curves)
        visibility = visibility or {}
        bench_columns = bench_columns or ComparisonEngine.find_bench_columns(raw_df, specs)
        actuator_analysis = actuator_analysis or {}
        pressure_units = infer_pressure_units(raw_df)

        panels = {}
        for spec in specs:
            state = visibility.get(spec['key'], {})
            sim_df = sim_curves.get(spec['key'], pd.DataFrame())
            bench_col = bench_columns.get(spec['key'])
            sim_on = bool(state.get('sim', True)) and isinstance(sim_df, pd.DataFrame) and not sim_df.empty and {'time_min', 'value'}.issubset(sim_df.columns)
            bench_on = bool(state.get('bench', True)) and bench_col in raw_df.columns
            if not sim_on and not bench_on:
                continue
            # Keep each parameter on its own axis. Same-unit signals often
            # have very different ranges (for example temperature and motor
            # temperature), so combining them makes one trace unreadable.
            panel = panels.setdefault(spec['key'], {
                'signals': [], 'unit': spec['unit'],
                'title': spec['label'],
                'digital': spec['kind'] == 'digital', 'stage': spec['kind'] == 'stage', 'code': spec['kind'] == 'code'
            })
            panel['signals'].append((spec, sim_df if sim_on else None, bench_col if bench_on else None))

        if not panels:
            return None, [], [], "Enable at least one available Simulation or Bench signal."

        panel_items = list(panels.items())
        fig_height = max(6.5, 1.65 * len(panel_items) + 0.75)
        fig, axes_raw = plt.subplots(
            nrows=len(panel_items), ncols=1, figsize=(14, fig_height),
            dpi=100, sharex=True, squeeze=False
        )
        axes = list(axes_raw[:, 0])
        twin_axes = []
        layout_rows = []
        fig.suptitle(
            'Simulation vs. Test Bench Signal Comparison',
            fontsize=14, fontweight='bold', color='#17324D', y=0.995
        )

        # Only visible curves define the domain; hiding all bench curves must
        # not leave an empty tail out to the longer bench cycle's end.
        time_extents = []

        drain_intervals = []
        drain_curve = sim_curves.get('drain_open', pd.DataFrame())
        if isinstance(drain_curve, pd.DataFrame) and {'time_min', 'value'}.issubset(drain_curve.columns):
            drain_t = pd.to_numeric(drain_curve['time_min'], errors='coerce').to_numpy(dtype=float, na_value=np.nan)
            drain_v = pd.to_numeric(drain_curve['value'], errors='coerce').to_numpy(dtype=float, na_value=np.nan)
            drain_on = np.isfinite(drain_t) & np.isfinite(drain_v) & (drain_v > 0.5)
            drain_indices = np.flatnonzero(drain_on)
            if drain_indices.size:
                drain_runs = np.split(drain_indices, np.flatnonzero(np.diff(drain_indices) > 1) + 1)
                positive_steps = np.diff(drain_t[np.isfinite(drain_t)])
                positive_steps = positive_steps[positive_steps > 0]
                tail_step = float(np.median(positive_steps)) if positive_steps.size else 0.0
                drain_intervals = [
                    (float(drain_t[run[0]]), float(drain_t[run[-1]] + tail_step))
                    for run in drain_runs if run.size
                ]

        for panel_index, (_signal_key, panel) in enumerate(panel_items):
            axis = axes[panel_index]
            axis.grid(True, linestyle=':', color='#D8DEE6', alpha=0.75)
            axis.tick_params(axis='x', labelsize=8, colors='#344054')
            axis.tick_params(axis='y', labelsize=9, colors='#344054')
            panel_notes = []
            heater_state_axis = None
            title = panel['title']
            if panel['unit'] not in ('state', 'stage', 'code'):
                title = f"{title} ({panel['unit']})"
            has_visible_sim = any(sim_df is not None for _, sim_df, _ in panel['signals'])
            if (_signal_key in ('pre_wash_valve_open', 'wash_valve_open') and has_visible_sim
                    and specs is SIMULATION_LEGEND_SPECS):
                for start, end in drain_intervals:
                    axis.axvspan(start, end, color='#647D16', alpha=0.12,
                                 linewidth=0, zorder=0)
                if drain_intervals:
                    panel_notes.append('Shaded intervals: drain fill can hide simulation valve pixels.')
            handoff = actuator_analysis.get('first_rinse_handoff')
            if handoff and has_visible_sim and _signal_key in ('drain_open', 'wash_valve_open'):
                handoff_time = float(handoff['main_wash_on_min'])
                axis.axvline(
                    handoff_time, color='#344054', linestyle=':', linewidth=0.9,
                    zorder=3
                )
                if _signal_key == 'wash_valve_open':
                    panel_notes.append(f"First-rinse handoff: {handoff_time:.1f} min.")
            first_drain = actuator_analysis.get('first_drain_pressure_response')
            if first_drain and has_visible_sim and _signal_key in ('drain_open', 'pressure'):
                drain_start = float(first_drain['drain_on_min'])
                broad_fill_start = first_drain.get('broad_fill_on_min')
                axis.axvline(
                    drain_start, color='#475467', linestyle=':', linewidth=0.9,
                    zorder=3
                )
                if broad_fill_start is not None and float(broad_fill_start) != drain_start:
                    axis.axvline(
                        float(broad_fill_start), color='#647D16', linestyle='-.',
                        linewidth=0.9, zorder=3
                    )
                pressure_decline_start = first_drain.get('pressure_decline_start_min')
                if pressure_decline_start is not None:
                    axis.axvline(
                        float(pressure_decline_start), color='#D97706',
                        linestyle='--', linewidth=0.9, alpha=0.9, zorder=3
                    )
                pressure_drop = first_drain.get('pressure_drop_mbar')
                if _signal_key == 'pressure' and pressure_drop is not None:
                    broad_fill_note = (
                        f"broad fill ~{float(broad_fill_start):.1f} min; "
                        if broad_fill_start is not None else ""
                    )
                    onset_note = (
                        f"Pressure starts falling ~{pressure_decline_start:.1f} min; "
                        f"first pump pulse ~{drain_start:.1f} min; {broad_fill_note}"
                        if pressure_decline_start is not None else
                        f"First pump pulse ~{drain_start:.1f} min; {broad_fill_note}"
                    )
                    panel_notes.append(onset_note + f"pressure drop ~{pressure_drop:.0f} mbar.")
            visible_values = []
            legend_handles = []
            legend_labels = []
            for spec, sim_df, bench_col in panel['signals']:
                color = spec['color']
                bench_name = re.sub(r'\s+', ' ', str(bench_col)).strip() if bench_col is not None else ''
                if spec['key'] == 'actual_remaining_time' and bench_col is not None:
                    bench_name = 'Actual Remaining Time'
                if spec['key'] == 'pressure' and bench_col is not None:
                    bench_name = f'Water Pressure ({spec["unit"]})'
                if sim_df is not None:
                    tx = pd.to_numeric(sim_df['time_min'], errors='coerce').to_numpy(dtype=float, na_value=np.nan)
                    sy = pd.to_numeric(sim_df['value'], errors='coerce').to_numpy(dtype=float, na_value=np.nan)
                    sy = np.where(np.isfinite(sy), sy, np.nan)
                    valid_time = np.isfinite(tx)
                    tx, sy = tx[valid_time], sy[valid_time]
                    tx, sy = display_samples(tx, sy, 'step' if spec.get('step') else spec['kind'])
                    if spec.get('step'):
                        line, = axis.step(tx, sy, where='post', color=color, lw=1.15, label=f"Sim · {spec['label']} (W)")
                    elif spec['kind'] == 'code':
                        line, = axis.step(tx, sy, where='post', color=color, lw=1.0, label=f"Sim · {spec['label']}")
                    elif spec['kind'] == 'digital':
                        # Preserve NaNs as gaps. The image analyzer uses them
                        # when a filled actuator trace hides the valve pixels.
                        sy = np.where(np.isfinite(sy), np.where(sy > 0.5, 1.0, 0.0), np.nan)
                        line, = axis.step(
                            tx, sy, where='post', color=color, lw=1.0, alpha=0.86,
                            label=f"Sim · {spec['label']}"
                        )
                    elif spec['kind'] == 'stage':
                        source_values = pd.to_numeric(sim_df['value'], errors='coerce')
                        stage_values = normalize_program_stage_series(source_values).to_numpy(dtype=float)
                        valid_stage = np.isfinite(pd.to_numeric(sim_df['time_min'], errors='coerce').to_numpy(dtype=float, na_value=np.nan))
                        tx = pd.to_numeric(sim_df['time_min'], errors='coerce').to_numpy(dtype=float, na_value=np.nan)[valid_stage]
                        sy = stage_values[valid_stage]
                        line, = axis.step(
                            tx, sy, where='post', color=color, lw=1.0, alpha=0.86,
                            label=f"Sim · {spec['label']}"
                        )
                    else:
                        line, = axis.plot(
                            tx, sy, color=color, lw=1.15, alpha=0.9,
                            label=f"Sim · {spec['label']}"
                        )
                        # A single observed pixel between unknown columns has
                        # no connecting line segment. Show the evidence as a
                        # small point instead of making that peak disappear.
                        known = np.isfinite(sy)
                        isolated = known & ~np.r_[False, known[:-1]] & ~np.r_[known[1:], False]
                        if np.any(isolated):
                            axis.scatter(tx[isolated], sy[isolated], color=color,
                                         s=8, linewidths=0, alpha=0.9, zorder=4)
                    if sy.size:
                        visible_values.extend(sy[np.isfinite(sy)].tolist())
                    valid_samples = np.isfinite(tx) & np.isfinite(sy)
                    if np.any(valid_samples):
                        sample_times = tx[valid_samples]
                        time_extents.append((float(sample_times.min()), float(sample_times.max())))
                    legend_handles.append(line)
                    legend_labels.append(line.get_label())

                if bench_col is not None:
                    bx = pd.to_numeric(raw_df['time_min'], errors='coerce').to_numpy(dtype=float, na_value=np.nan)
                    source = raw_df[bench_col]
                    bench_heater_state = spec['key'] == 'heater_power' and spec['unit'] == 'W' and ComparisonEngine.heater_bench_is_state(raw_df, bench_col)
                    if bench_heater_state:
                        by = ComparisonEngine._bench_values(raw_df, spec['key'], bench_col, specs).to_numpy(dtype=float)
                        bx, by = display_samples(bx, by, 'digital')
                        heater_state_axis = axis.twinx()
                        twin_axes.append(heater_state_axis)
                        heater_state_axis.set_ylim(-0.04, 1.04)
                        heater_state_axis.set_yticks([0, 1], labels=['OFF', 'ON'])
                        heater_state_axis.tick_params(axis='y', colors=spec['bench_color'], labelsize=9)
                        line, = heater_state_axis.step(bx, by, where='post', color=spec['bench_color'], lw=1.15,
                                                      linestyle='--', label='Bench · Heater ON/OFF')
                        panel_notes.append('Simulation: watts. Bench: ON/OFF. Simulation power > 0 W means ON.')
                    elif spec['kind'] == 'code':
                        by = pd.to_numeric(source, errors='coerce').to_numpy(dtype=float, na_value=np.nan)
                        bx, by = display_samples(bx, by, 'code')
                        line, = axis.step(bx, by, where='post', color=spec['bench_color'], lw=1.0, label=f"Bench · {bench_name}")
                    elif spec['kind'] == 'digital':
                        by = normalize_control_series(source, bench_col).to_numpy(dtype=float)
                        bx, by = display_samples(bx, by, 'digital')
                        line, = axis.step(
                            bx, by, where='post', color=spec['bench_color'], lw=1.0, alpha=0.86,
                            label=f"Bench · {bench_name}"
                        )
                    elif spec['kind'] == 'stage':
                        by = normalize_program_stage_series(source).to_numpy(dtype=float)
                        line, = axis.step(
                            bx, by, where='post', color=spec['bench_color'], lw=1.0, alpha=0.86,
                            label=f"Bench · {bench_name}"
                        )
                    else:
                        by = ComparisonEngine._bench_values(raw_df, spec['key'], bench_col, specs).to_numpy(dtype=float, na_value=np.nan)
                        by = np.where(np.isfinite(by), by, np.nan)
                        # Retain unknown samples as gaps instead of drawing a
                        # continuous bridge across a missing-data interval.
                        valid = np.isfinite(bx)
                        bx, by = bx[valid], by[valid]
                        bx, by = display_samples(bx, by, spec['kind'])
                        line, = axis.plot(
                            bx, by, color=spec['bench_color'], lw=1.1, alpha=0.9,
                            label=f"Bench · {bench_name}"
                        )
                    if by.size and not bench_heater_state:
                        visible_values.extend(by[np.isfinite(by)].tolist())
                    valid_samples = np.isfinite(bx) & np.isfinite(by)
                    if np.any(valid_samples):
                        sample_times = bx[valid_samples]
                        time_extents.append((float(sample_times.min()), float(sample_times.max())))
                    legend_handles.append(line)
                    legend_labels.append(line.get_label())

            if panel['digital']:
                # A small inset keeps the OFF/ON strokes visible at the border.
                axis.set_ylim(-0.04, 1.04)
                axis.set_yticks([0, 1])
                axis.set_yticklabels(['OFF', 'ON'], fontweight='bold', color='#344054')
                # The horizontal block heading already names this state signal;
                # OFF/ON ticks carry its value meaning without another label.
                axis.set_ylabel('')
            elif panel['stage']:
                axis.set_ylim(0.8, 3.2)
                axis.set_yticks([1, 2, 3])
                axis.set_yticklabels(['1 · Wash', '2 · Rinse', '3 · Spin'], fontweight='bold', color='#344054')
                axis.set_ylabel('')
            else:
                if visible_values:
                    finite_values = np.asarray(visible_values, dtype=float)
                    finite_values = finite_values[np.isfinite(finite_values)]
                    if finite_values.size:
                        low, high = float(finite_values.min()), float(finite_values.max())
                        span = high - low
                        padding = max(span * 0.06, abs(high) * 0.015, 0.5)
                        auto_low = low - padding
                        if low >= 0 and auto_low < 0:
                            auto_low = 0.0
                        if _signal_key == 'pressure' and any(spec.get('preserve_pressure_numbers') for spec, _, _ in panel['signals']):
                            # A common 0–3000 range keeps original traces comparable;
                            # expand it rather than hiding samples outside that range.
                            axis.set_ylim(0.0 if low >= 0 else auto_low, max(3000.0, high + padding))
                        else:
                            axis.set_ylim(auto_low, high + padding)
                unit = panel['unit']
                axis.set_ylabel(unit, fontsize=9, fontweight='bold', color='#344054', labelpad=4)
            if heater_state_axis is not None and has_visible_sim:
                curve = sim_curves.get('heater_power', pd.DataFrame())
                reference = curve.attrs.get('heater_on_reference_watts', 2000.0)
                if np.isfinite(reference) and reference > 0:
                    upper = max(reference, max(visible_values,default=reference)) * 1.04
                    axis.set_ylim(-.04 * reference, upper)
                    heater_state_axis.set_ylim(-.04, upper / reference)
            if heater_state_axis is not None and not has_visible_sim:
                axis.set_yticks([])
                axis.set_ylabel('')
                title = 'Heater · Bench ON/OFF'
            row_axes = [axis] + ([heater_state_axis] if heater_state_axis is not None else [])
            scales = [{'axis': axis, 'side': 'left'}]
            if heater_state_axis is not None:
                scales.append({'axis': heater_state_axis, 'side': 'right'})
            layout_rows.append({
                'axis': axis, 'axes': row_axes,
                'scales': scales,
                'title': title,
                'legend_entries': list(zip(legend_handles, legend_labels)),
                'note': ' '.join(panel_notes),
            })

        x_min = min((bounds[0] for bounds in time_extents), default=0.0)
        x_max = max((bounds[1] for bounds in time_extents), default=1.0)
        axes[0].set_xlim(set_signal_time_bounds(fig, x_min, x_max))
        SignalFigureLayout(fig, layout_rows, font_size=9, show_legends=True,
                           legend_dragger=enable_draggable_legend)
        fig._signal_initial_ylims = {axis: axis.get_ylim() for axis in axes + twin_axes}
        return fig, axes, twin_axes, None

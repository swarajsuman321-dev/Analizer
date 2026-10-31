"""Explicit two-recording comparison on supported elapsed-time intervals.

Original channels are never aligned or resampled in place. The timing projection
uses the established last-duplicate policy and conservative gap-aware Trace
rules. Linear differences are integrated analytically, so acquiring one logger
more frequently does not give that logger more statistical weight.
"""
from dataclasses import replace
import hashlib
import json
import math

import numpy as np

from app_engineering_trace import Trace
from app_engineering_units import UNITS, convert, unit
from app_operation_context import checkpoint


def _clean(value):
    """Return strict JSON data, including missing numeric evidence as null."""
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, np.ndarray):
        return _clean(value.tolist())
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    if isinstance(value, (float, np.floating)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    # Provenance can contain a path/date or an extension's metadata object.
    # Represent it as text; numerical results above are explicitly typed.
    return str(value)


def _origin(store, channel):
    starts, derived = [], []
    for current in store.channels.values():
        if current.dataset_id != channel.dataset_id or current.coordinate_kind != 'time' or not len(current.x):
            continue
        if current.attributes.get('engineering_projection'):
            continue
        try:
            # Recording start belongs to acquired source timestamps, not a
            # derived channel's synthetic clock or a user's graph time shift.
            target = derived if current.parents or current.recipe else starts
            target.append(float(convert(current.x[0], current.coordinate_unit, 's')))
        except ValueError:
            continue
    if not starts and not derived:
        raise ValueError('The recording has no supported time coordinate.')
    return min(starts or derived), bool(starts)


def _trace(channel, target, offset, max_gap_seconds):
    if channel.attributes.get('actuator_binary'):
        # A confirmed binary interpretation is explicit metadata, never a
        # threshold guessed from a parameter name or a numerical range.
        values = channel.values()[1]
        binary = np.where(np.isfinite(values), (values != 0).astype(float), np.nan)
        channel = replace(channel, y=binary, unit='state', kind='discrete')
    return Trace(channel, target=target if channel.unit != target else None,
                 offset=offset, max_gap_seconds=max_gap_seconds)


def _segments(trace, starts, ends):
    """One-sided endpoint values of each fully supported union-knot segment."""
    count = len(starts)
    left = np.full(count, np.nan)
    right = np.full(count, np.nan)
    valid = np.zeros(count, dtype=bool)
    if len(trace.t) < 2:
        return left, right, valid
    index = np.searchsorted(trace.t, starts, side='right')-1
    safe = np.clip(index, 0, len(trace.t)-2)
    width = trace.t[safe+1]-trace.t[safe]
    valid = ((index >= 0) & (index < len(trace.t)-1) &
             (ends <= trace.t[safe+1]) & (width > 0) &
             (width <= trace.max_gap) & np.isfinite(trace.y[safe]) &
             np.isfinite(trace.y[safe+1]))
    if trace.kind == 'analog':
        slope = (trace.y[safe+1]-trace.y[safe])/width
        left[valid] = (trace.y[safe]+slope*(starts-trace.t[safe]))[valid]
        right[valid] = (trace.y[safe]+slope*(ends-trace.t[safe]))[valid]
    else:
        left[valid] = trace.y[safe[valid]]
        right[valid] = left[valid]
    return left, right, valid


def _within_fraction(first, last, threshold):
    """Exact fraction of a linear segment lying in [-threshold, threshold]."""
    threshold = np.broadcast_to(np.asarray(threshold, dtype=float), first.shape)
    same = first == last
    result = np.where(same & (np.abs(first) <= threshold), 1., 0.)
    moving = ~same
    if moving.any():
        delta = last[moving]-first[moving]
        low = (-threshold[moving]-first[moving])/delta
        high = (threshold[moving]-first[moving])/delta
        result[moving] = np.maximum(0., np.minimum(1., np.maximum(low, high))-
                                   np.maximum(0., np.minimum(low, high)))
    return result


def _numerical_resolution(trace, starts, original_unit):
    """Bound floating-point calculation noise, never physical measurement error.

    Linear interpolation uses the two bracketing samples. Their magnitudes set
    the floating-point resolution even when their interpolation cancels near
    zero. An affine unit conversion additionally includes its intermediate
    offsets; Celsius/Fahrenheit cancellation must not turn roundoff into a
    full-duration difference. No absolute epsilon floor or test-plan limit is
    introduced, so genuinely tiny recorded values remain distinguishable.
    """
    index = np.clip(np.searchsorted(trace.t, starts, side='right')-1,
                    0, max(0, len(trace.t)-2))
    left = np.abs(trace.y[index])
    right = np.abs(trace.y[np.minimum(index+1, len(trace.y)-1)])
    magnitude = np.maximum(left, right)
    resolution = 8*np.spacing(magnitude)
    source, target = unit(original_unit), unit(trace.unit)
    if source != target and source in UNITS and target in UNITS:
        source_offset = UNITS[source][2]
        target_multiplier, target_offset = UNITS[target][1:]
        # A conservative error bound for the multiply/add/subtract/divide
        # conversion, expressed in the comparison unit. The input term is
        # reconstructed from either converted endpoint without changing data.
        conversion_magnitude = np.maximum(
            np.abs(trace.y[index]*target_multiplier+target_offset-source_offset),
            np.abs(trace.y[np.minimum(index+1, len(trace.y)-1)]*target_multiplier+target_offset-source_offset))
        conversion_magnitude = (conversion_magnitude+abs(source_offset)+abs(target_offset))/abs(target_multiplier)
        epsilon = np.finfo(float).eps
        resolution = resolution + (4*epsilon/(1-4*epsilon))*conversion_magnitude
    return resolution


def _plot(trace, start, end, budget=6000):
    """Bounded visual projection; full interval evidence remains separate."""
    left = np.searchsorted(trace.raw_t, start, side='left')
    right = np.searchsorted(trace.raw_t, end, side='right')
    t, y = trace.raw_t[left:right], trace.raw_y[left:right]
    for boundary, first in ((start, True), (end, False)):
        if len(trace.t) and trace.t[0] <= boundary <= trace.t[-1] and not np.any(t == boundary):
            value = trace.sample(np.asarray([boundary]))[0]
            t = np.r_[boundary, t] if first else np.r_[t, boundary]
            y = np.r_[value, y] if first else np.r_[y, value]
    if len(t) > 1:
        gaps = np.flatnonzero(np.diff(t) > trace.max_gap)+1
        if len(gaps):
            y = np.insert(y, gaps, np.nan)
            t = np.insert(t, gaps, t[gaps])
    if len(t) > budget:
        step = int(np.ceil(len(t)/max(1, budget//6)))
        out_t, out_y = [], []
        for offset in range(0, len(t), step):
            if offset % 8192 < step:
                checkpoint()
            chunk = y[offset:offset+step]
            finite = np.flatnonzero(np.isfinite(chunk))
            if not len(finite):
                out_t.append(t[offset]); out_y.append(np.nan)
                continue
            selected = sorted({int(finite[np.argmin(chunk[finite])]),
                               int(finite[np.argmax(chunk[finite])])})
            missing = len(finite) != len(chunk)
            for index in selected:
                if missing:
                    out_t.append(t[offset+index]); out_y.append(np.nan)
                out_t.append(t[offset+index]); out_y.append(chunk[index])
                if missing:
                    out_t.append(t[offset+index]); out_y.append(np.nan)
        t, y = np.asarray(out_t), np.asarray(out_y)
    return {'time_min': t/60, 'value': y,
            'interpolation': 'linear' if trace.kind == 'analog' else 'held',
            'projection': 'Bounded min/max illustration; calculations use complete supported intervals'}


def _activity(trace, role, start, end, binary, rotation):
    if not binary and not rotation:
        return {'available': False, 'reason': 'Activity requires a confirmed actuator or declared rotation unit.'}, []
    points = np.unique(np.r_[start, trace.t[(trace.t >= start) & (trace.t <= end)], end])
    starts, ends = points[:-1], points[1:]
    first, last, valid = _segments(trace, starts, ends)
    durations = ends-starts
    active = valid & ((first != 0) | (last != 0))
    forward = np.zeros(len(starts))
    reverse = np.zeros(len(starts))
    for sign, target in ((1, forward), (-1, reverse)):
        a, b = first*sign, last*sign
        same_side = valid & (a >= 0) & (b >= 0) & ((a > 0) | (b > 0))
        target[same_side] = durations[same_side]
        crossing = valid & (a*b < 0)
        if crossing.any():
            fraction = np.abs(a[crossing])/(np.abs(a[crossing])+np.abs(b[crossing]))
            target[crossing] = durations[crossing]*np.where(a[crossing] > 0, fraction, 1-fraction)
    interpretation = ('Confirmed actuator: finite zero is OFF; finite nonzero is ON' if binary else
                      'Declared rotation-unit signal: exact zero/nonzero readings and numerical sign changes only. Source role and negative-value protocol meaning may be unconfirmed; commands, feedback and sentinels are not distinguished here.')
    events = []
    # Events require a finite, gap-supported source interval. Initial ON data
    # is not called a start; activity after a gap is not a proven transition.
    last_direction = 0
    for index in range(max(0, len(trace.t)-1)):
        if index % 8192 == 0:
            checkpoint()
        a, b = trace.t[index:index+2]
        va, vb = trace.y[index:index+2]
        if b < start or a > end:
            continue
        if b <= a or b-a > trace.max_gap or not np.isfinite([va, vb]).all():
            last_direction = 0
            continue
        if rotation and va != 0:
            last_direction = int(np.sign(va))
        event, at = None, b
        if va == 0 and vb != 0:
            event = 'Became nonzero' if rotation else 'ON'
            at = a if trace.kind == 'analog' else b
        elif va != 0 and vb == 0:
            event = 'Became zero' if rotation else 'OFF'
        elif rotation and va*vb < 0:
            event = 'Numeric sign change'
            if trace.kind == 'analog':
                at = a+(b-a)*abs(va)/(abs(va)+abs(vb))
        if event and start <= at <= end:
            events.append({'role': role, 'event': event, 'time_min': float(at/60),
                           'from_value': float(va), 'to_value': float(vb),
                           'interpretation': interpretation})
        # A continuously observed stop may separate the two directions; the
        # restart still establishes a reversal. Missing support resets this
        # memory, so separate logging blocks do not invent a reversal.
        if (rotation and va == 0 and vb != 0 and last_direction and
                int(np.sign(vb)) != last_direction and start <= at <= end):
            events.append({'role': role, 'event': 'Numeric sign change', 'time_min': float(at/60),
                           'from_value': 0., 'to_value': float(vb),
                           'interpretation': interpretation})
        if rotation and vb != 0:
            last_direction = int(np.sign(vb))
    supported = float(durations[valid].sum())
    total_active = float(durations[active].sum())
    return {'available': True, 'interpretation': interpretation,
            'active_duration_min': total_active/60,
            'active_fraction': total_active/supported if supported else None,
            'supported_duration_min': supported/60,
            'starts': sum(row['event'] in ('Became nonzero', 'ON') for row in events),
            'stops': sum(row['event'] in ('Became zero', 'OFF') for row in events),
            'sign_changes': sum(row['event'] == 'Numeric sign change' for row in events),
            'reversals': sum(row['event'] == 'Numeric sign change' for row in events),
            'transition_meaning': 'starts/stops count zero/nonzero signal transitions; reversals is an alias for numerical sign changes, not a confirmed mechanical reversal',
            'positive_duration_min': float(forward.sum()/60) if rotation else None,
            'negative_duration_min': float(reverse.sum()/60) if rotation else None}, events


def _record(store, original, trace, role, start, end, origin):
    dataset = store.datasets.get(original.dataset_id)
    stats = trace.stats(start, end)
    quality = trace.quality(start, end)
    binary = bool(original.attributes.get('actuator_binary'))
    rotation = UNITS.get(unit(trace.unit), (None,))[0] == 'rotation'
    activity, events = _activity(trace, role, start, end, binary, rotation)
    raw = trace.raw_y[(trace.raw_t >= start) & (trace.raw_t <= end)]
    fingerprint = hashlib.sha256()
    for values in (original.x, original.y, original.raw_y):
        if values is not None:
            fingerprint.update(memoryview(np.ascontiguousarray(values, dtype='<f8')).cast('B'))
    fingerprint.update(json.dumps(_clean({'unit': original.unit, 'coordinate_unit': original.coordinate_unit,
                                         'kind': original.kind, 'shift': original.shift, 'masks': original.masks,
                                         'actuator_binary': binary}), sort_keys=True).encode('utf-8'))
    record = {'channel_id': original.id, 'name': original.name,
              'dataset_id': original.dataset_id,
              'dataset': dataset.name if dataset else original.dataset_id,
              'source': original.source or (dataset.source if dataset else ''),
              'original_unit': original.unit, 'unit': trace.unit,
              'coordinate_unit': original.coordinate_unit,
              'loaded_snapshot_sha256': fingerprint.hexdigest(),
              'fingerprint_method': 'SHA-256 of loaded coordinate/value arrays, original values when retained, units, kind, shift and masks; not a source-file digest',
              'processing': {'parents': original.parents, 'recipe': original.recipe,
                             'shift': original.shift, 'masks': original.masks},
              'recording_origin_min': origin/60,
              'kind': 'actuator' if binary else original.kind,
              'statistics': {**{name: stats.get(name) for name in ('min', 'max', 'mean', 'rms', 'std', 'first', 'last')},
                             'samples': int(np.isfinite(raw).sum()),
                             'observed_span_min': quality['observed_span_s']/60,
                             'supported_duration_min': stats.get('known_s', 0)/60,
                             'coverage_fraction': stats.get('coverage', 0),
                             'requested_span_min': max(0., end-start)/60},
              'quality': quality, 'activity': activity, 'plot': _plot(trace, start, end)}
    return record, events


def compare_signals(store, reference_id, candidate_id, alignment='elapsed', offset_min=0,
                    interval=None, tolerance=None, max_gap_seconds=None,allow_same_recording=False):
    """Compare an explicit pair; user-data blockers are returned, never guessed.

    ``offset_min`` shifts only the candidate's comparison projection. ``interval``
    is an optional [start, end] in aligned minutes. No tolerance means exact
    numerical differences, not an acceptance test or an inferred pass limit.
    """
    result = {'schema': 1, 'status': 'blocked', 'reason': '', 'reference': {},
              'candidate': {}, 'alignment': {}, 'scope': {}, 'metrics': {},
              'differences': [], 'events': [], 'summary': [], 'limitations': []}
    try:
        checkpoint('Validating selected signals')
        reference, candidate = store.channels.get(reference_id), store.channels.get(candidate_id)
        if reference is None or candidate is None:
            raise ValueError('Select two available channels from different recordings.')
        if reference_id == candidate_id or (reference.dataset_id == candidate.dataset_id and not allow_same_recording):
            raise ValueError('Select one parameter from each of two different recordings.')
        if reference.coordinate_kind != 'time' or candidate.coordinate_kind != 'time':
            raise ValueError('Two-signal activity comparison requires time-based recordings; frequency and sample-index plots retain their own units.')
        if not len(reference.x) or not len(candidate.x):
            raise ValueError('Both selected channels need recorded samples.')
        if alignment not in ('program', 'elapsed', 'recorded', 'manual'):
            raise ValueError('Choose program, elapsed, recorded or manual timeline alignment.')
        offset_min = float(offset_min)
        if not math.isfinite(offset_min):
            raise ValueError('The candidate offset must be finite minutes.')
        if tolerance is not None:
            tolerance = float(tolerance)
            if not math.isfinite(tolerance) or tolerance < 0:
                raise ValueError('An explicit absolute tolerance must be finite and nonnegative.')
        left_binary = bool(reference.attributes.get('actuator_binary'))
        right_binary = bool(candidate.attributes.get('actuator_binary'))
        if left_binary != right_binary:
            raise ValueError('The selected channels have different value interpretations. Confirm both as numeric signals or both as actuators before comparing.')
        target = 'state' if left_binary else unit(reference.unit)
        source = 'state' if right_binary else unit(candidate.unit)
        if target != source:
            if not target or not source:
                raise ValueError('Confirm both source units before comparing differently labelled units.')
            convert([0., 1.], source, target)  # Verification precedes any calculation.
        if not target:
            result['limitations'].append('Source units are not declared; differences compare recorded numbers without a physical-unit interpretation.')
        elif not left_binary and target not in UNITS:
            result['limitations'].append('Both signals declare the same custom unit; no external calibration or physical-unit validation is implied.')
        origin_records = [_origin(store, channel) if alignment == 'elapsed' else (0., True)
                          for channel in (reference, candidate)]
        origins = [record[0] for record in origin_records]
        program_records=[]
        if alignment=='program':
            from app_program_alignment import program_start,source_offset_minutes
            program_records=[program_start(store,c.dataset_id) for c in (reference,candidate)]
            origins=[record['source_min']*60 for record in program_records]
        if alignment == 'elapsed' and not all(record[1] for record in origin_records):
            result['limitations'].append('An original source clock is unavailable in at least one dataset; its elapsed origin uses the earliest remaining temporal projection.')
        shifts=[float(convert(c.shift,c.coordinate_unit,'s'))+source_offset_minutes(store,c)*60 if alignment=='program' else 0 for c in (reference,candidate)]
        left = _trace(reference, target, -origins[0]-shifts[0], max_gap_seconds)
        right = _trace(candidate, target, -origins[1]-shifts[1]+offset_min*60, max_gap_seconds)
        start, end = min(left.t[0], right.t[0]), max(left.t[-1], right.t[-1])
        if interval is not None:
            if len(interval) != 2:
                raise ValueError('The comparison interval needs two minute coordinates.')
            start, end = sorted(float(value)*60 for value in interval)
            if not np.isfinite([start, end]).all():
                raise ValueError('Comparison interval coordinates must be finite.')
        if end <= start:
            raise ValueError('The recordings have no elapsed-time span to compare.')
        result['alignment'] = {'mode': alignment, 'reference_origin_min': origins[0]/60,
                               'candidate_origin_min': origins[1]/60, 'candidate_offset_min': offset_min,
                               'reference_original_clock': origin_records[0][1],
                               'candidate_original_clock': origin_records[1][1],
                               'description': ('Elapsed time from each recording’s earliest original source timestamp; late-starting parameters and applied graph shifts retain their offset. Derived clocks do not rebase original recordings.' if alignment == 'elapsed' else
                                               'Recorded numeric time coordinates are preserved; no calendar origin is inferred.')}
        if alignment=='program':
            result['alignment'].update(program_starts=program_records,
                description='Time zero is the confirmed program start of each recording. One source-wide offset preserves all channel timing; pre-program samples retain negative elapsed time.')
        overlap_start, overlap_end = max(start, left.t[0], right.t[0]), min(end, left.t[-1], right.t[-1])
        result['scope'] = {'start_min': start/60, 'end_min': end/60, 'span_min': (end-start)/60,
                           'overlap_start_min': overlap_start/60 if overlap_end >= overlap_start else None,
                           'overlap_end_min': overlap_end/60 if overlap_end >= overlap_start else None,
                           'overlap_span_min': max(0., overlap_end-overlap_start)/60}
        checkpoint('Measuring reference signal')
        result['reference'], left_events = _record(store, reference, left, 'Reference', start, end, origins[0])
        checkpoint('Measuring candidate signal')
        result['candidate'], right_events = _record(store, candidate, right, 'Candidate', start, end, origins[1])
        if alignment=='program':
            for record,channel,origin in zip((result['reference'],result['candidate']),(reference,candidate),origins):
                record['program_origin_min']=origin/60
                record['recording_origin_min']=_origin(store,channel)[0]/60
        result['events'] = sorted(left_events+right_events, key=lambda row: (row['time_min'], row['role']))
        grid = np.unique(np.r_[start, left.t[(left.t > start) & (left.t < end)],
                               right.t[(right.t > start) & (right.t < end)], end])
        starts, ends = grid[:-1], grid[1:]
        av0, av1, valid_left = _segments(left, starts, ends)
        bv0, bv1, valid_right = _segments(right, starts, ends)
        supported = valid_left & valid_right
        durations = ends-starts
        d0, d1 = bv0-av0, bv1-av1
        numerical_resolution = (_numerical_resolution(left, starts, reference.unit) +
                                _numerical_resolution(right, starts, candidate.unit))
        h, first, last = durations[supported], d0[supported], d1[supported]
        known = float(h.sum())
        metrics = {'unit': target, 'compared_duration_min': known/60,
                   'coverage_fraction': known/(end-start), 'mean_bias': None,
                   'mean_absolute_difference': None, 'rmse': None,
                   'max_absolute_difference': None, 'max_difference_time_min': None,
                   'different_duration_min': None, 'tolerance': tolerance,
                   'within_tolerance_duration_min': None,
                   'numerical_resolution_max': None,
                   'numerical_resolution_policy': 'Floating-point operation resolution only: interpolation operand ULPs and affine conversion error bound. This is not measurement accuracy or an acceptance tolerance. Raw differences and summary error metrics are retained.',
                   'difference_direction': 'Candidate minus Reference',
                   'weighting': 'Elapsed-time weighted over joint supported intervals only'}
        if known:
            area = h*(first+last)/2
            square = h*(first*first+first*last+last*last)/3
            absolute = h*(np.abs(first)+np.abs(last))/2
            crossing = first*last < 0
            absolute[crossing] = h[crossing]*(first[crossing]**2+last[crossing]**2)/(2*(np.abs(first[crossing])+np.abs(last[crossing])))
            endpoints = np.column_stack((np.abs(first), np.abs(last)))
            index, side = np.unravel_index(np.argmax(endpoints), endpoints.shape)
            times = starts[supported] if side == 0 else ends[supported]
            resolution = numerical_resolution[supported]
            numerically_same = _within_fraction(first, last, resolution)
            metrics.update(mean_bias=float(area.sum()/known),
                           mean_absolute_difference=float(absolute.sum()/known),
                           rmse=float(np.sqrt(max(0., square.sum()/known))),
                           max_absolute_difference=float(endpoints[index, side]),
                           max_difference_time_min=float(times[index]/60),
                           max_difference_time_policy='Supported interval endpoint; held values use the value before any boundary jump',
                           numerical_resolution_max=float(resolution.max()),
                           different_duration_min=float(np.sum(h*(1-numerically_same))/60))
            if tolerance is not None:
                metrics['within_tolerance_duration_min'] = float(np.sum(h*_within_fraction(first, last, np.maximum(tolerance, resolution)))/60)
        result['metrics'] = metrics
        checkpoint('Collecting complete difference intervals', 0, len(starts))
        for index in range(len(starts)):
            if index % 8192 == 0:
                checkpoint('Collecting complete difference intervals', index, len(starts))
            valid = bool(supported[index])
            reason = '' if valid else ('Reference and candidate unsupported' if not valid_left[index] and not valid_right[index] else
                                       'Reference unsupported' if not valid_left[index] else 'Candidate unsupported')
            result['differences'].append({'start_min': starts[index]/60, 'end_min': ends[index]/60,
                                          'duration_min': durations[index]/60, 'supported': valid,
                                          'reference_start': av0[index], 'reference_end': av1[index],
                                          'candidate_start': bv0[index], 'candidate_end': bv1[index],
                                          'delta_start': d0[index] if valid else None,
                                          'delta_end': d1[index] if valid else None,
                                          'numerical_resolution': numerical_resolution[index] if valid else None,
                                          'reason': reason})
        result['limitations'].extend([
            'Missing readings, masks, unsupported gaps and time outside either recording are excluded from difference totals.',
            'Last duplicate sample defines timing; all original observations remain available and source extrema retain duplicate peaks.',
            'The default gap policy is three times each signal’s median positive sample interval unless explicitly configured.',
            'Differences are descriptive measurements, not a Pass/Fail decision or appliance fault diagnosis.'])
        if tolerance is None:
            result['limitations'].append('No acceptance tolerance configured; different duration counts numerically distinguishable inequality, excluding floating-point interpolation/conversion roundoff only.')
        if known:
            result['status'] = 'compared'
            result['summary'] = [f'Compared {known/60:.6g} min of supported data ({known/(end-start):.1%} of the requested elapsed span).',
                                 f'Mean candidate-minus-reference difference: {metrics["mean_bias"]:.6g} {target or "recorded units"}.',
                                 f'Largest supported difference: {metrics["max_absolute_difference"]:.6g} {target or "recorded units"} at {metrics["max_difference_time_min"]:.6g} min.']
            if result['reference']['activity']['available']:
                a, b = result['reference']['activity'], result['candidate']['activity']
                description = 'Supported ON-signal time' if left_binary else 'Supported nonzero-signal time'
                result['summary'].append(f'{description}: Reference {a["active_duration_min"]:.6g} min; Candidate {b["active_duration_min"]:.6g} min. Each total uses that signal’s own supported time.')
        else:
            result['reason'] = 'No joint gap-supported interval is available. Point samples alone cannot establish duration or time-weighted differences.'
        return _clean(result)
    except (ValueError, TypeError, OverflowError) as error:
        result['reason'] = str(error)
        return _clean(result)

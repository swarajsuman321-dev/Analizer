"""Evidence-first recording analysis and typed comparison orchestration.

This service owns no widgets and changes neither loaded data nor plot state.
Measurements use native observations before alignment; aligned/decimated arrays
are illustrations only. Pairing suggestions are never accepted implicitly.
"""
from copy import deepcopy
from itertools import combinations
import hashlib
import json
import math

import numpy as np

from app_channel_store import Channel, ChannelStore, Dataset
from app_engineering_units import UNITS, convert, convert_difference, unit
from app_operation_context import checkpoint
from app_parameter_contracts import RESULT_STATUSES, metric_record, result_bundle, strict_json
from app_parameter_capabilities import CapabilityDefinition, CapabilityRegistry
from app_parameter_inventory import inventory_runs, source_field
from app_parameter_semantics import project_field, resolve_mapping


_NUMERIC = {'analog', 'quantized_analog', 'setpoint', 'unknown'}
_STATES = {'binary', 'enum', 'categorical', 'pulse'}
_ALIGNMENTS = {'elapsed', 'native', 'anchor', 'manual', 'stage_relative'}
_COMPARATORS = None


def comparator_registry():
    """Versioned trusted comparators, extensible without changing report/UI code.

    A comparator receives ``(left, right, context)`` and returns one JSON record
    or a list. Context holds field identities, options and native run origins.
    Extensions register on a clone; input filenames never load executable code.
    """
    global _COMPARATORS
    if _COMPARATORS is None:
        registry = CapabilityRegistry()
        registry.register(CapabilityDefinition('comparison.analog', structures=tuple(sorted(_NUMERIC)),
            scopes=('pair',), prerequisites=('compatible explicit field pairing', 'native time support'),
            output_units=('source', 's'), coverage_policy='Exact piecewise integration on common physical support'),
            lambda left, right, c: _analog(left, right, c['left_field'], c['right_field'], c['options'], c['origins']), trusted=True)
        registry.register(CapabilityDefinition('comparison.state', structures=tuple(sorted(_STATES)),
            scopes=('pair',), prerequisites=('compatible explicit state pairing', 'native held support'),
            output_units=('s', '1'), coverage_policy='Half-open joint held-state agreement; no enum numeric distance'),
            lambda left, right, c: _state_compare(left, right, c['left_field'], c['right_field'], c['options'], c['origins']), trusted=True)
        _COMPARATORS = registry
    return _COMPARATORS


def _check(cancelled=None):
    checkpoint()
    stopped = cancelled() if callable(cancelled) else bool(
        cancelled is not None and getattr(cancelled, 'is_set', lambda: False)())
    if stopped:
        raise InterruptedError('Recording analysis cancelled')


def _finite(value):
    return isinstance(value, (int, float, np.number)) and not isinstance(value, (bool, np.bool_)) and math.isfinite(float(value))


def _json(value):
    """Qualify missing numerical plot coordinates without emitting JSON NaN."""
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_json(v) for v in value]
    if isinstance(value, np.generic):
        return _json(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _notice(status, reason, *, field_id='', run_id='', remedy='', **details):
    return {'status': status, 'reason': str(reason), 'field_id': field_id,
            'run_id': run_id, 'remedy': remedy or 'Review the mapping and available source evidence', **details}


def _fingerprint(projection):
    digest = hashlib.sha256()
    for key in ('values', 'x_s', 'source_indices', 'valid'):
        values = projection.get(key)
        if values is None:
            digest.update(b'none')
        else:
            values = np.asarray(values)
            digest.update(str(values.dtype).encode())
            digest.update(str(values.shape).encode())
            if values.dtype.kind == 'O':
                digest.update(repr(values.tolist()).encode('utf-8'))
            else:
                digest.update(values.tobytes())
    return digest.hexdigest()


def _origins(store, runs, mappings=None, profile=None, cancelled=None):
    """Run origins include all original fields, including late unselected ones."""
    origins = {}
    for run in runs:
        starts = []
        for field in run['fields']:
            _check(cancelled)
            source = source_field(store, field)
            clock = source['clock']
            try:
                mapping = resolve_mapping(field, mappings=mappings, profile=profile)
            except (ValueError, TypeError):
                continue  # The field loop records this mapping error separately.
            if clock.get('kind') != 'time' or not (clock.get('trust') == 'declared' or mapping['acquisition_policy'].get('clock_reviewed') is True):
                continue
            x = np.asarray(source['coordinates'], float)
            finite = x[np.isfinite(x)]
            if len(finite) and not np.any(np.diff(finite) < 0):
                starts.append(float(finite[0]))
        origins[run['id']] = min(starts) if starts else None
    return origins


def _native_offsets(runs):
    """Restore declared calendar origins before comparing acquisition time."""
    import pandas as pd
    offsets = {}
    for run in runs:
        origins = {field.get('clock', {}).get('origin') for field in run['fields']
                   if field.get('clock', {}).get('domain') == 'absolute' and field.get('clock', {}).get('origin')}
        if len(origins) == 1:
            try:
                origin = pd.Timestamp(next(iter(origins)))
                if origin.tzinfo is None:
                    origin = origin.tz_localize('UTC')
                offsets[run['id']] = float(origin.timestamp())
            except (ValueError, TypeError, OverflowError):
                offsets[run['id']] = None
        elif len(origins) > 1:
            offsets[run['id']] = None
    return offsets


def _mapping_view(field):
    mapping = field.get('mapping') or field.get('provenance', {}).get('mapping') or {}
    return {key: mapping.get(key, field.get(key, '')) for key in (
        'structure', 'role', 'instance', 'location', 'function', 'signal_kind', 'dimension')}


def _compatibility(left, right, *, suggestions=False):
    """Names alone never establish semantic or encoding equivalence."""
    a, b = _mapping_view(left), _mapping_view(right)
    reasons = []
    for key in ('role', 'instance', 'location', 'function', 'signal_kind'):
        av, bv = a.get(key) or '', b.get(key) or ''
        if av != bv and (av or bv):
            reasons.append(key.replace('_', ' ') + ' differs or is missing')
    sa, sb = a.get('structure') or 'unknown', b.get('structure') or 'unknown'
    if sa != sb and not ({sa, sb} <= _NUMERIC):
        reasons.append('Signal structures differ')
    ma, mb = left.get('mapping') or {}, right.get('mapping') or {}
    ea, eb = ma.get('encoding') or {}, mb.get('encoding') or {}
    if ea.get('stored_values') == 'raw' and eb.get('stored_values') == 'raw':
        if ea.get('signature') and eb.get('signature') and ea['signature'] != eb['signature']:
            reasons.append('Raw encoding signatures differ')
    if sa in {'enum', 'categorical', 'bitfield'}:
        da, db = ma.get('state_dictionary') or {}, mb.get('state_dictionary') or {}
        if da != db:
            reasons.append('State dictionaries differ; review a common decoder before comparing codes')
    ua, ub = unit(left.get('unit', ma.get('unit', ''))), unit(right.get('unit', mb.get('unit', '')))
    if ua != ub:
        try:
            convert([0., 1.], ub, ua)
        except (ValueError, TypeError):
            reasons.append('Source units are incompatible or unresolved')
    if suggestions and (not a.get('role') or not ma.get('authority', {}).get('reviewed') or not mb.get('authority', {}).get('reviewed')):
        reasons.append('Pairing requires reviewed roles and meaning')
    return reasons


def suggest_pairings(inventory_or_bundle, *, baseline_run_id=None):
    """Return gated review candidates, including ambiguity; never confirm them."""
    if isinstance(inventory_or_bundle, dict):
        fields = inventory_or_bundle.get('inventory', [])
    else:
        entries = list(inventory_or_bundle or [])
        fields = [field for entry in entries for field in entry['fields']] if entries and 'fields' in entries[0] else entries
    runs = list(dict.fromkeys(field['run_id'] for field in fields))
    if not runs:
        return []
    baseline_run_id = baseline_run_id or runs[0]
    suggestions = []
    for left in fields:
        if left['run_id'] != baseline_run_id:
            continue
        candidates = [right for right in fields if right['run_id'] != baseline_run_id and not _compatibility(left, right, suggestions=True)]
        counts = {run_id: sum(r['run_id'] == run_id for r in candidates) for run_id in runs}
        for right in candidates:
            suggestions.append({'reference_field_id': left['id'], 'candidate_field_id': right['id'],
                'reference_run_id': left['run_id'], 'candidate_run_id': right['run_id'],
                'confirmed': False, 'status': 'needs_review',
                'ambiguous': counts[right['run_id']] != 1,
                'reason': 'Compatible reviewed meaning; user confirmation required' if counts[right['run_id']] == 1 else 'Multiple compatible fields; select the correct instance'})
    return suggestions


def _offset(run_id, options, origins):
    mode = options['alignment']
    if mode == 'native':
        offset = options.get('_native_offsets_s', {}).get(run_id, 0.)
        return (offset, '') if offset is not None else (None, 'Declared absolute clock origins are incompatible or invalid; review the run clock domain')
    if mode in ('elapsed', 'manual'):
        origin = origins.get(run_id)
        if origin is None:
            return None, 'Recording origin is unavailable'
        extra = options.get('offsets_s', {}).get(run_id, 0.) if mode == 'manual' else 0.
        if not _finite(extra):
            return None, 'Manual offset must be finite seconds'
        return -origin + float(extra), ''
    if mode == 'anchor':
        anchor = options.get('anchors_s', {}).get(run_id)
        if isinstance(anchor, dict):
            anchor = anchor.get('time_s') if anchor.get('confirmed') is True else None
        if not _finite(anchor):
            return None, 'A confirmed finite time anchor is required for every compared run'
        return -float(anchor), ''
    return 0., ''


def _aligned_records(records, run_id, options, origins):
    """Align sequence-cost coordinates and retain every native boundary."""
    mode = dict(options)
    if mode['alignment'] == 'stage_relative':
        mode['alignment'] = 'elapsed'  # Never compare physical delays in progress units.
    offset, reason = _offset(run_id, mode, origins)
    if offset is None:
        return [], reason
    result = []
    for original in records:
        item = deepcopy(original)
        for key in ('start_s', 'end_s', 'onset_s', 'offset_s', 'confirmation_s'):
            if _finite(item.get(key)):
                item['native_'+key] = item[key]
                item[key] += offset
        for key in ('onset_bracket_s', 'offset_bracket_s'):
            if isinstance(item.get(key), list):
                item['native_'+key] = item[key][:]
                item[key] = [value+offset for value in item[key]]
        item['alignment'] = {'mode': mode['alignment'], 'offset_s': offset, 'comparison_view_only': True}
        result.append(item)
    return result, ''


def _stage_display(plots, stages, options, readiness):
    """A selected stage-progress overlay never changes physical measurements."""
    if options['alignment'] != 'stage_relative':
        return
    selected = options.get('stage_view') or {}
    for picture in plots:
        stage_id = selected.get(picture['run_id'])
        stage = next((item for item in stages if item.get('run_id') == picture['run_id'] and item.get('id') == stage_id), None)
        if not stage or stage['end_s'] <= stage['start_s']:
            readiness.append(_notice('needs_review', 'Select an established stage instance in each run for stage-relative display', field_id=picture['field_id'], run_id=picture['run_id'], remedy='Supply options.stage_view as run ID → reviewed stage ID; native plots and measurements remain available'))
            continue
        x = np.asarray(picture['original_x'], float)
        # Keep original and aligned arrays the same length. Out-of-stage values
        # are explicitly absent rather than compressed into a false full run.
        selected_mask = (x >= stage['start_s']) & (x <= stage['end_s'])
        normalized = (x-stage['start_s'])/(stage['end_s']-stage['start_s'])
        picture['aligned_x'] = [float(value) if good else None for value, good in zip(normalized, selected_mask)]
        picture['aligned_coordinate_unit'] = 'stage progress (0–1)'
        picture['alignment'] = {'mode': 'stage_relative', 'stage_id': stage_id, 'start_s': stage['start_s'], 'end_s': stage['end_s'], 'display_only': True,
            'policy': 'Native duration/rates and acceptance retain physical seconds'}


def _display(projection, field, options, origins):
    values = np.asarray(projection['values'])
    if values.ndim != 1 or values.dtype.kind not in 'biuf':
        return None
    numeric = values.astype(float)
    numeric[~np.asarray(projection['valid'], bool)] = np.nan
    x = projection.get('x_s')
    timed = x is not None
    x = np.asarray(x if timed else projection['source_indices'], float)
    budget = int(options.get('plot_budget', 2000))
    if budget < 8:
        raise ValueError('Plot budget must be at least 8 observations')
    # Every bucket contributes endpoints/extrema and missing-data separators;
    # reducing this budget never changes native metric/event computation.
    selected = []
    if len(x) <= budget:
        selected = list(range(len(x)))
    else:
        step = max(1, math.ceil(len(x) / max(1, budget // 6)))
        for start in range(0, len(x), step):
            _check(options.get('cancelled'))
            end = min(len(x), start + step)
            finite = np.flatnonzero(np.isfinite(numeric[start:end])) + start
            indices = {start, end-1}
            if len(finite):
                indices.update((int(finite[np.argmin(numeric[finite])]), int(finite[np.argmax(numeric[finite])])))
            missing = np.flatnonzero(~np.isfinite(numeric[start:end])) + start
            if len(missing):
                indices.add(int(missing[0]))
                indices.add(int(missing[-1]))
            selected.extend(sorted(indices))
    x, numeric = x[selected], numeric[selected]
    result = {'field_id': field['id'], 'run_id': field['run_id'], 'channel_id': field.get('channel_id'),
        'label': field.get('run_name', field['run_id'])+' · '+(field.get('display_name') or field['original_name']), 'unit': projection['unit'],
        'structure': projection['structure'], 'original_x': x.tolist(), 'y': _json(numeric),
        'source_indices': np.asarray(projection['source_indices'])[selected].tolist(),
        'coordinate_unit': 's' if timed else 'sample', 'coordinate_kind': 'Time' if timed else 'Sample',
        'projection': 'Bounded source-index/minimum/maximum illustration; all measurements use original observations'}
    if field.get('trace_color'):
        result['color'] = field['trace_color']
    if timed:
        offset, reason = _offset(field['run_id'], options, origins)
        if offset is not None and options['alignment'] != 'stage_relative':
            result['aligned_x'] = (x + offset).tolist()
            result['alignment'] = {'mode': options['alignment'], 'offset_s': offset, 'recording_origin_s': origins.get(field['run_id'])}
        elif reason:
            result['alignment_unavailable'] = reason
    return result


def _comparator_values(projection, offset):
    """Adapt per-source gap policies to the existing exact pair integrator.

    Its public API accepts one gap bound. Inserting an invalid midpoint into
    each unsupported native gap retains both observed endpoints and prevents
    either gap half contributing to joint support, without resampling sources.
    """
    x = np.asarray(projection['x_s'], float) + offset
    y = np.asarray(projection['values'], float).copy()
    y[~np.asarray(projection['valid'], bool)] = np.nan
    policy = projection['acquisition_policy']
    gap = policy.get('max_gap_seconds')
    positive = np.diff(x)
    positive = positive[positive > 0]
    if gap is None:
        gap = 3 * float(np.median(positive)) if len(positive) else 0.
    indices = np.flatnonzero(np.diff(x) > gap) + 1
    if len(indices):
        inserted = (x[indices-1] + x[indices]) / 2
        x, y = np.insert(x, indices, inserted), np.insert(y, indices, np.nan)
    return x, y, float(gap)


def _analog(left, right, left_field, right_field, options, origins):
    from app_signal_comparison import compare_signals
    common = {'comparison_type': 'common_window_analog', 'reference_field_id': left_field['id'],
        'candidate_field_id': right_field['id'], 'reference_run_id': left_field['run_id'],
        'candidate_run_id': right_field['run_id'], 'definition_version': '1',
        'acceptance': {'status': 'not_evaluated', 'reasons': ['No engineering acceptance rule supplied']}}
    offsets = [_offset(field['run_id'], options, origins) for field in (left_field, right_field)]
    if options['alignment'] == 'stage_relative':
        return dict(common, status='not_comparable', reasons=['Normalized stage progress is a display view and cannot replace physical duration or pointwise time error'])
    if left.get('x_s') is None or right.get('x_s') is None or any(offset is None for offset, _ in offsets):
        return dict(common, status='not_comparable', reasons=['Trustworthy clocks and explicit alignment are required for common-window errors'] + [reason for _, reason in offsets if reason])
    temp = ChannelStore()
    channels, gaps = [], []
    import pandas as pd
    for projection, field, (offset, _) in zip((left, right), (left_field, right_field), offsets):
        x, y, gap = _comparator_values(projection, offset)
        dataset = Dataset(field['run_id'], pd.DataFrame(), id=field['run_id'])
        temp.datasets[dataset.id] = dataset
        channel = Channel(field['original_name'], x, y, unit=projection['unit'],
            coordinate_unit='s', dataset_id=dataset.id, kind='discrete' if projection['acquisition_policy'].get('mode') in ('held', 'event') else 'analog')
        temp.channels[channel.id] = channel
        channels.append(channel)
        gaps.append(gap)
    if any(not len(channel.x) for channel in channels):
        return dict(common, status='insufficient_data', reasons=['Both sources require native observations'])
    span = max(channel.x[-1] for channel in channels)-min(channel.x[0] for channel in channels)
    evidence = compare_signals(temp, channels[0].id, channels[1].id, alignment='recorded',
        max_gap_seconds=max(1., float(span)), tolerance=options.get('tolerance'))
    metrics = evidence.get('metrics', {})
    duration = metrics.get('compared_duration_min', 0.) * 60
    return dict(common, status='computed' if evidence.get('status') == 'compared' else 'not_comparable',
        reasons=[evidence['reason']] if evidence.get('reason') else [],
        unit=left['unit'], alignment={'mode': options['alignment'], 'offsets_s': dict(zip((left_field['run_id'], right_field['run_id']), [item[0] for item in offsets]))},
        supported_duration_s=duration, coverage_fraction=metrics.get('coverage_fraction'),
        mean_bias=metrics.get('mean_bias'), mae=metrics.get('mean_absolute_difference'),
        rmse=metrics.get('rmse'), max_absolute_difference=metrics.get('max_absolute_difference'),
        max_difference_time_s=metrics['max_difference_time_min']*60 if metrics.get('max_difference_time_min') is not None else None,
        absolute_difference_area=(metrics['mean_absolute_difference']*duration) if metrics.get('mean_absolute_difference') is not None else None,
        area_unit=(left['unit'] or 'raw-unit')+'·s', difference_direction='Candidate minus Reference',
        weighting='Supported physical time; exact existing piecewise integration',
        source_gap_limits_s=gaps, intervals=evidence.get('differences', []),
        interval_coordinate_unit='min', tolerance=options.get('tolerance'),
        limitations=evidence.get('limitations', []))


def _state_compare(left, right, left_field, right_field, options, origins):
    from app_parameter_events import state_timeline
    common = {'comparison_type': 'common_window_state', 'definition_version': '1',
        'reference_field_id': left_field['id'], 'candidate_field_id': right_field['id'],
        'reference_run_id': left_field['run_id'], 'candidate_run_id': right_field['run_id'],
        'acceptance': {'status': 'not_evaluated', 'reasons': ['No engineering acceptance rule supplied']}}
    if options['alignment'] == 'stage_relative':
        return dict(common, status='not_comparable', reasons=['Normalized progress is display-only; state agreement uses physical time'])
    timelines = []
    for projection, field in ((left, left_field), (right, right_field)):
        offset, reason = _offset(field['run_id'], options, origins)
        if projection.get('x_s') is None or offset is None:
            return dict(common, status='not_comparable', reasons=[reason or 'Trustworthy native time is required for state agreement'])
        mapping = field['mapping']
        timelines.append(state_timeline(np.asarray(projection['x_s'])+offset, projection['values'], valid=projection['valid'],
            structure=projection['structure'], acquisition_policy=projection['acquisition_policy'],
            dictionary=mapping.get('state_dictionary'), on_values=mapping.get('parameters', {}).get('on_values'),
            parameters=mapping.get('parameters'), identity={'field_id': field['id'], 'run_id': field['run_id']}))
    a, b = timelines[0]['intervals'], timelines[1]['intervals']
    i = j = 0
    agree = mismatch = 0.
    intervals = []
    while i < len(a) and j < len(b):
        _check(options.get('cancelled'))
        start, end = max(a[i]['start_s'], b[j]['start_s']), min(a[i]['end_s'], b[j]['end_s'])
        if end > start:
            same = a[i]['state'] == b[j]['state']
            agree += end-start if same else 0.
            mismatch += end-start if not same else 0.
            intervals.append({'start_s': start, 'end_s': end, 'agreement': bool(same), 'reference_state': a[i]['state'], 'candidate_state': b[j]['state']})
        if a[i]['end_s'] <= b[j]['end_s']:
            i += 1
        else:
            j += 1
    known = agree+mismatch
    return dict(common, status='computed' if known else 'not_comparable', reasons=[] if known else ['No joint supported held-state intervals'],
        agreement_duration_s=agree, mismatch_duration_s=mismatch, supported_duration_s=known,
        agreement_fraction=agree/known if known else None, intervals=intervals,
        source_readiness=timelines[0]['readiness']+timelines[1]['readiness'],
        weighting='Joint supported physical time; no enum-code numeric error')


def _conversion(value, source, target, metric):
    if source == target:
        return float(value)
    statistic = metric.get('statistic', 'absolute')
    if source.endswith('/s') and target.endswith('/s'):
        return float(convert_difference(value, source[:-2], target[:-2]))
    operation = convert_difference if statistic in ('difference', 'rate') or metric['metric_id'] in ('range', 'time_std') else convert
    return float(operation(value, source, target))


def compare_metric_records(reference, candidate, *, comparable=True, reasons=None, physical=True,
                           scope_correspondence=False):
    """Typed Candidate-minus-Reference delta retaining both source records.

    Public to extensions/tests: unavailable comparisons retain full input
    records and a practical reason instead of erasing a requested measurement.
    """
    blockers = list(reasons or [])
    for key in ('metric_id', 'definition_version', 'role', 'instance', 'weighting'):
        if reference.get(key) != candidate.get(key):
            blockers.append(key.replace('_', ' ')+' does not match')
    if reference.get('scope', {}).get('kind') != candidate.get('scope', {}).get('kind'):
        blockers.append('Metric scopes differ')
    elif reference.get('scope') != candidate.get('scope') and not scope_correspondence:
        blockers.append('Metric scopes need an explicit stage/event correspondence')
    if reference.get('status') not in ('computed', 'partial') or candidate.get('status') not in ('computed', 'partial'):
        blockers.append('Both source measurements must be available')
    record = {'comparison_type': 'full_scope_metric', 'metric_id': reference['metric_id'],
        'definition_version': reference.get('definition_version', '1'),
        'reference_run_id': reference.get('run_id'), 'candidate_run_id': candidate.get('run_id'),
        'reference_field_id': reference.get('field_id'), 'candidate_field_id': candidate.get('field_id'),
        'reference_metric': deepcopy(reference), 'candidate_metric': deepcopy(candidate),
        'reference': reference.get('value'), 'candidate': candidate.get('value'),
        'unit': reference.get('unit', ''), 'delta': None, 'relative_percent': None,
        'difference_direction': 'Candidate minus Reference', 'scope': deepcopy(reference.get('scope', {})),
        'acceptance': {'status': 'not_evaluated', 'reasons': ['Descriptive difference; no acceptance rule supplied']}}
    if not comparable and not blockers:
        blockers.append('Source meanings are not comparable')
    av, bv = reference.get('value'), candidate.get('value')
    if blockers:
        return strict_json(dict(record, status='not_comparable', reasons=blockers))
    if not _finite(av) or not _finite(bv):
        return strict_json(dict(record, status='computed', equal=av == bv, delta_semantics='categorical equality only',
            reasons=[], relative_reason='Relative change is not defined for categorical or structured results'))
    try:
        converted = _conversion(bv, candidate.get('unit', ''), reference.get('unit', ''), reference)
    except (ValueError, TypeError) as exc:
        return strict_json(dict(record, status='not_comparable', reasons=['Unit conversion unavailable: '+str(exc)]))
    delta = converted-float(av)
    if not math.isfinite(delta):
        return strict_json(dict(record, status='not_comparable', reasons=['Signed difference exceeds finite numerical range']))
    record['candidate_in_reference_unit'] = converted
    record['conversion'] = {'source_unit': candidate.get('unit', ''), 'target_unit': reference.get('unit', ''), 'statistic': reference.get('statistic', 'absolute')}
    duty = reference['metric_id'] in ('state.duty_cycle', 'duty_cycle', 'duty_fraction')
    dimension = UNITS.get(unit(reference.get('unit', '')), ('unknown',))[0]
    if duty:
        record.update(delta=delta*100, delta_unit='percentage points', delta_semantics='Candidate minus Reference duty fraction × 100', relative_reason='Duty-cycle change is expressed in percentage points')
    else:
        record.update(delta=delta, delta_unit=record['unit'], delta_semantics='Signed absolute difference')
        if dimension == 'temperature':
            record['relative_reason'] = 'Relative change of absolute temperature is not reported'
        elif not physical:
            record['relative_reason'] = 'Raw observation comparison has no confirmed ratio-scale meaning'
        elif dimension in ('state', 'code', 'unknown'):
            record['relative_reason'] = 'This quantity has no established ratio-scale interpretation'
        elif abs(float(av)) <= 8 * np.spacing(abs(float(av))):
            record['relative_reason'] = 'Reference is zero at numerical resolution; relative change is undefined'
        else:
            relative = delta/abs(float(av))*100
            if math.isfinite(relative):
                record['relative_percent'] = relative
            else:
                record['relative_reason'] = 'Relative change exceeds finite numerical range'
    return strict_json(dict(record, status='partial' if 'partial' in (reference['status'], candidate['status']) else 'computed', reasons=[]))


def _scalar_pairs(metrics, left, right, stage_correspondence=None):
    """Keep unavailable metrics and match scopes by declared correspondence."""
    def key(metric):
        scope = metric.get('scope') or {}
        kind = scope.get('kind', 'run')
        interval = '' if kind in ('run', 'stage', 'event') else json.dumps(scope, sort_keys=True)
        return metric['metric_id'], kind, scope.get('stage_id'), scope.get('event_id'), interval
    right_by_key = {key(metric): metric for metric in metrics if metric.get('field_id') == right['id']}
    for metric in metrics:
        if metric.get('field_id') != left['id']:
            continue
        match_key = key(metric)
        if match_key[1] == 'stage' and stage_correspondence:
            match_key = match_key[:2]+(stage_correspondence.get(match_key[2]), match_key[3], match_key[4])
        candidate = right_by_key.get(match_key)
        if candidate is not None:
            yield metric, candidate


def _aggregate(metrics):
    """Descriptive equal-run means; no pooling samples or significance claim."""
    groups = {}
    for metric in metrics:
        if metric.get('scope', {}).get('kind') != 'run' or metric.get('status') not in ('computed', 'partial') or not _finite(metric.get('value')):
            continue
        # Unreviewed/missing instance identity cannot establish cross-run peers.
        if not metric.get('role'):
            continue
        key = tuple(metric.get(k, '') for k in ('metric_id', 'definition_version', 'role', 'instance', 'unit', 'weighting'))
        groups.setdefault(key, []).append(metric)
    output = []
    for key, entries in groups.items():
        runs = [entry['run_id'] for entry in entries]
        if len(set(runs)) < 3 or len(set(runs)) != len(runs):
            continue
        output.append({'metric_id': key[0], 'definition_version': key[1], 'role': key[2], 'instance': key[3],
            'unit': key[4], 'value': float(np.mean([entry['value'] for entry in entries])),
            'weighting': 'Equal weight per run; no sample pooling', 'run_ids': runs,
            'weights': [1/len(runs)]*len(runs), 'source_metrics': entries,
            'status': 'computed', 'acceptance': {'status': 'not_evaluated', 'reasons': ['Descriptive aggregate; no statistical significance or better/worse claim']}})
    return output


def analyse_recordings(store, dataset_ids=None, *, mappings=None, pairings=None,
                       profile=None, options=None, registry=None, comparators=None):
    """Inventory all selected recordings and compute one shared evidence bundle.

    ``pairings`` must contain explicit ``confirmed: True`` field-ID pairs.
    ``options`` may specify baseline/pairwise comparisons, physical alignment,
    scopes, stages, relationship rules, cancellation and a progress callback.
    An interrupted run returns completed evidence with status ``cancelled``;
    no partial report is labelled complete.
    """
    options = dict(options or {})
    options.setdefault('alignment', 'elapsed')
    if options['alignment'] not in _ALIGNMENTS:
        raise ValueError('Choose elapsed, native, anchor, manual or stage_relative alignment')
    if options.get('comparison_mode', 'baseline') not in ('baseline', 'pairwise'):
        raise ValueError('Comparison mode must be baseline or pairwise')
    runs = inventory_runs(store, dataset_ids)
    if not runs:
        raise ValueError('Load at least one available recording')
    run_ids = [run['id'] for run in runs]
    baseline = options.get('baseline_run_id') or run_ids[0]
    if baseline not in run_ids:
        raise ValueError('The baseline must be one of the selected recordings')
    fields = [deepcopy(field) for run in runs for field in run['fields']]
    run_names = {run['id']: run['name'] for run in runs}
    for field in fields:
        field['run_name'] = run_names[field['run_id']]
        channel = store.channels.get(field.get('channel_id'))
        if channel is not None:
            field['trace_color'] = channel.attributes.get('plot_style', {}).get('color') or channel.attributes.get('trace_color')
    field_by_id = {field['id']: field for field in fields}
    options['_native_offsets_s'] = _native_offsets(runs)
    origins = {run_id: None for run_id in run_ids}
    projections, metrics, events, readiness, quality, plots, stages, comparisons = {}, [], [], [], [], [], [], []
    completed = 0
    status = 'completed'
    accepted_pairs = []
    cancelled = options.get('cancelled')
    progress = options.get('progress')
    from app_parameter_analytics import analyse_field
    try:
        origins = _origins(store, runs, mappings=mappings, profile=profile, cancelled=cancelled)
        for field in fields:
            _check(cancelled)
            if callable(progress):
                progress({'phase': 'analysis', 'completed': completed, 'total': len(fields), 'field_id': field['id'], 'label': field['original_name']})
            try:
                mapping = resolve_mapping(field, mappings=mappings, profile=profile)
                field['mapping'] = mapping
                field['display_name'] = mapping.get('display_name') or field['original_name']
                projection = project_field(store, field, mapping)
                projection.update(run_id=field['run_id'], field_id=field['id'], mapping=mapping)
                projections[field['id']] = projection
                field['mapping_status'] = projection['status']
                field['loaded_projection_sha256'] = _fingerprint(projection)
                quality.append({'run_id': field['run_id'], 'field_id': field['id'], **projection.get('quality', {})})
                if projection['status'] not in ('computed', 'partial'):
                    readiness.append(_notice(projection['status'], '; '.join(projection.get('reasons', [])), field_id=field['id'], run_id=field['run_id'], remedy='Review structure, meaning, encoding, units and acquisition policy; generic source observations remain available'))
                if field['disposition'] in ('unsupported', 'invalid'):
                    reason = field.get('metadata', {}).get('reason') or field['disposition']
                    metrics.append(metric_record('field.availability', status='unsupported' if field['disposition'] == 'unsupported' else 'insufficient_data',
                        field_id=field['id'], run_id=field['run_id'], reasons=[reason]))
                    readiness.append(_notice('unsupported' if field['disposition'] == 'unsupported' else 'insufficient_data', reason, field_id=field['id'], run_id=field['run_id']))
                else:
                    output = analyse_field(projection, run_id=field['run_id'], field_id=field['id'], mapping=mapping,
                        scopes=options.get('scopes'), registry=registry, cancelled=lambda: _cancelled(cancelled))
                    metrics.extend(output['metrics']); events.extend(output['events'])
                    readiness.extend(output['readiness']); quality.extend(output['quality'])
                picture = _display(projection, field, options, origins)
                if picture:
                    plots.append(picture)
            except InterruptedError:
                raise
            except Exception as exc:
                status = 'partial'
                field['analysis_status'] = 'error'
                readiness.append(_notice('error', f'{type(exc).__name__}: {exc}', field_id=field['id'], run_id=field['run_id'], remedy='Review this field or its trusted reader/analyser; other fields remain available'))
            completed += 1
        # Stage/relationship services consume the same reviewed projections.
        from app_parameter_stages import resolve_stages, assign_events_to_stages, match_sequences
        from app_parameter_events import analyse_relationships
        for run_id in run_ids:
            _check(cancelled)
            run_projections = {key: value for key, value in projections.items() if value['run_id'] == run_id}
            definitions = options.get('stage_definitions', [])
            definitions = definitions.get('stages', []) if isinstance(definitions, dict) else definitions
            definitions = [definition for definition in definitions if definition.get('run_id', run_id) == run_id]
            stage_result = resolve_stages(run_projections, definitions, run_id=run_id,
                cancelled=lambda: _cancelled(cancelled))
            stages.extend(stage_result['stages']); readiness.extend(stage_result['readiness'])
            if options.get('relationship_rules'):
                relations = analyse_relationships(run_projections, options['relationship_rules'], stages=stage_result['stages'])
                metrics.extend(relations.get('metrics', [])); events.extend(relations.get('events', [])); readiness.extend(relations.get('readiness', []))
        events = assign_events_to_stages(events, stages)
        _stage_display(plots, stages, options, readiness)
        # Add per-stage field measurements using unchanged physical clocks.
        for stage in stages:
            if not _finite(stage.get('start_s')) or not _finite(stage.get('end_s')):
                continue
            stage_id = stage.get('id', stage.get('stage_id'))
            scope = {'kind': 'stage', 'stage_id': stage_id, 'start_s': stage['start_s'], 'end_s': stage['end_s']}
            for field_id, projection in projections.items():
                if projection['run_id'] != stage.get('run_id') or field_by_id[field_id]['disposition'] in ('unsupported', 'invalid'):
                    continue
                output = analyse_field(projection, run_id=projection['run_id'], field_id=field_id,
                    mapping=field_by_id[field_id]['mapping'], scopes=[scope], registry=registry, cancelled=lambda: _cancelled(cancelled))
                metrics.extend(output['metrics']); readiness.extend(output['readiness']); quality.extend(output['quality'])
                # The episode catalogue is native whole-run evidence. Stage
                # attribution clips occupancy; it never duplicates episodes.
        run_pairs = list(combinations(run_ids, 2)) if options.get('comparison_mode') == 'pairwise' else [(baseline, run_id) for run_id in run_ids if run_id != baseline]
        stage_matches = {}
        for a, b in run_pairs:
            left_stages = [stage for stage in stages if stage.get('run_id') == a]
            right_stages = [stage for stage in stages if stage.get('run_id') == b]
            if left_stages or right_stages:
                left_aligned, left_reason = _aligned_records(left_stages, a, options, origins)
                right_aligned, right_reason = _aligned_records(right_stages, b, options, origins)
                matching_parameters = {**options.get('matching_parameters', {}), 'cancelled': lambda: _cancelled(cancelled)}
                match = match_sequences(left_aligned, right_aligned, parameters=matching_parameters)
                if left_reason or right_reason:
                    match['readiness'].append(_notice('not_comparable', '; '.join(filter(None, (left_reason, right_reason)))))
                comparisons.append({'comparison_type': 'stage_sequence', 'reference_run_id': a, 'candidate_run_id': b, **match})
                stage_matches[(a, b)] = {row.get('reference_id'): row.get('candidate_id') for row in match.get('matches', [])}
        for pair in pairings or []:
            _check(cancelled)
            pair = deepcopy(pair)
            left = field_by_id.get(pair.get('reference_field_id'))
            right = field_by_id.get(pair.get('candidate_field_id'))
            reason = []
            if not left or not right:
                reason.append('A selected field is unavailable')
            elif left['run_id'] == right['run_id']:
                reason.append('Choose fields from different recordings')
            elif (left['run_id'], right['run_id']) not in run_pairs:
                reason.append('Pair orientation is outside the selected baseline/pairwise scope')
            if pair.get('confirmed') is not True:
                reason.append('Pairing has not been confirmed')
            if not reason:
                reason.extend(_compatibility(left, right))
            pair.update(status='not_comparable' if reason else 'confirmed', reasons=reason)
            accepted_pairs.append(pair)
            if reason:
                readiness.append(_notice('not_comparable', '; '.join(reason), field_id=pair.get('reference_field_id', ''), remedy='Select and confirm compatible field roles, instances, units and encodings'))
                comparisons.append({'comparison_type': 'field_pair', **pair})
                continue
            lp, rp = projections.get(left['id']), projections.get(right['id'])
            if lp is None or rp is None:
                readiness.append(_notice('unavailable', 'One field did not produce a usable projection', field_id=left['id']))
                continue
            physically_reviewed = all(projection['status'] in ('computed', 'partial') for projection in (lp, rp))
            for a, b in _scalar_pairs(metrics, left, right, stage_matches.get((left['run_id'], right['run_id']))):
                comparisons.append(compare_metric_records(a, b, physical=physically_reviewed,
                    scope_correspondence=a.get('scope', {}).get('kind') == 'stage' and bool(stage_matches.get((left['run_id'], right['run_id'])))))
            comparator_set = comparators or comparator_registry()
            right_ids = {definition.capability_id for definition, _ in comparator_set.applicable(rp)}
            for definition, comparer in comparator_set.applicable(lp):
                if definition.capability_id not in right_ids:
                    continue
                _check(cancelled)
                try:
                    records = comparer(lp, rp, {'left_field': left, 'right_field': right, 'options': options,
                        'origins': origins, 'cancelled': lambda: _cancelled(cancelled)})
                    records = records if isinstance(records, list) else [records]
                    for record in records:
                        if not isinstance(record, dict):
                            raise ValueError('Trusted comparators must return JSON comparison records')
                        if record.get('status') not in RESULT_STATUSES:
                            raise ValueError('Trusted comparators must declare a supported result status')
                        for key, expected in (('reference_field_id', left['id']), ('candidate_field_id', right['id'])):
                            if record.get(key, expected) != expected:
                                raise ValueError('Comparator source identities must match the confirmed field pair')
                        comparisons.append(strict_json({**record, 'reference_field_id': left['id'], 'candidate_field_id': right['id'],
                            'comparator_id': definition.capability_id, 'comparator_version': definition.definition_version}))
                except InterruptedError:
                    raise
                except Exception as exc:
                    status = 'partial'
                    comparisons.append({'comparison_type': 'capability_availability', 'status': 'error',
                        'reference_field_id': left['id'], 'candidate_field_id': right['id'],
                        'comparator_id': definition.capability_id, 'comparator_version': definition.definition_version,
                        'reasons': [f'{type(exc).__name__}: {exc}']})
            selected_events = [[event for event in events if event.get('field_id') == field['id']] for field in (left, right)]
            if any(selected_events):
                left_aligned, left_reason = _aligned_records(selected_events[0], left['run_id'], options, origins)
                right_aligned, right_reason = _aligned_records(selected_events[1], right['run_id'], options, origins)
                matching_parameters = {**options.get('matching_parameters', {}), 'cancelled': lambda: _cancelled(cancelled)}
                comparisons.append({'comparison_type': 'event_sequence', 'reference_field_id': left['id'], 'candidate_field_id': right['id'],
                    **match_sequences(left_aligned, right_aligned, parameters=matching_parameters),
                    'alignment_reasons': list(filter(None, (left_reason, right_reason)))})
    except InterruptedError:
        status = 'cancelled'
        readiness.append(_notice('cancelled', 'Analysis cancelled; only completed evidence is retained', remedy='Run analysis again to complete the remaining fields and comparisons'))
    for field in fields:
        if field['id'] not in projections:
            field.setdefault('analysis_status', 'not_processed')
    paired = {pair.get(key) for pair in accepted_pairs if pair.get('status') == 'confirmed' for key in ('reference_field_id', 'candidate_field_id')}
    if len(runs) > 1:
        for field in fields:
            if field['id'] not in paired:
                readiness.append(_notice('needs_review', 'No confirmed comparison pairing; original measurements retained', field_id=field['id'], run_id=field['run_id'], remedy='Confirm a compatible field pair or leave this field explicitly unpaired'))
    public_options = {key: value for key, value in options.items() if key not in ('cancelled', 'progress') and not key.startswith('_')}
    run_summaries = [{key: value for key, value in run.items() if key != 'fields'} for run in runs]
    provenance = {'engine': 'app_parameter_comparison', 'definition_version': '1', 'options': public_options,
        'baseline_run_id': baseline, 'recording_origins_s': origins,
        'native_calendar_offsets_s': options['_native_offsets_s'],
        'alignment_policy': 'Native measurements precede alignment; late channels retain the common run origin',
        'acceptance_policy': 'No limits, physical causes, better/worse direction or significance inferred',
        'source_policy': 'Original observations and loaded source order retained; no display decimation used in measurements',
        'context_policy': 'Descriptive single-run differences; controlled-equivalence of recipe/load/supply/environment/calibration is not assumed'}
    bundle = result_bundle('comparison' if len(runs) > 1 else 'analysis', run_summaries, fields, metrics,
        comparisons=comparisons, events=events, stages=stages, pairings=accepted_pairs,
        readiness=readiness, quality=_json(quality), provenance=_json(provenance), plot_series=plots,
        status=status, completed_field_count=completed, requested_field_count=len(fields),
        aggregates=_aggregate(metrics), pairing_suggestions=suggest_pairings(fields, baseline_run_id=baseline))
    if callable(progress):
        progress({'phase': status, 'completed': completed, 'total': len(fields)})
    return bundle


def _cancelled(value):
    return bool(value() if callable(value) else value is not None and getattr(value, 'is_set', lambda: False)())


def compare_selected_fields(store, reference_channel_id, candidate_channel_id, *, mappings=None,
                            profile=None, options=None, registry=None, comparators=None):
    """Use an explicitly chosen plot-channel pair without guessing peer fields."""
    left, right = store.channels.get(reference_channel_id), store.channels.get(candidate_channel_id)
    if left is None or right is None or left.dataset_id == right.dataset_id:
        raise ValueError('Choose one source channel from each of two different recordings')
    selected = inventory_runs(store, [left.dataset_id, right.dataset_id])
    fields = [field for run in selected for field in run['fields']]
    by_channel = {field.get('channel_id'): field for field in fields if field.get('channel_id')}
    if reference_channel_id not in by_channel or candidate_channel_id not in by_channel:
        raise ValueError('This comparison requires original source fields; keep derived-channel comparison available through Compare Two Signals')
    opts = dict(options or {})
    opts['baseline_run_id'] = left.dataset_id
    return analyse_recordings(store, [left.dataset_id, right.dataset_id], mappings=mappings, profile=profile,
        pairings=[{'reference_field_id': by_channel[reference_channel_id]['id'],
                   'candidate_field_id': by_channel[candidate_channel_id]['id'], 'confirmed': True,
                   'authority': 'Explicit user-selected source channels'}], options=opts, registry=registry,
        comparators=comparators)

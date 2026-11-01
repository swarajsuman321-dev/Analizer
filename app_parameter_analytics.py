"""Capability-driven, original-resolution field measurements.

Trace remains the numerical authority for moments and acquisition support. The
small adapter here supplies native arrays, never display-decimated channels.
Semantic analysers add measurements only after reviewed meaning/scaling exists.
"""
from types import SimpleNamespace
import copy
import math

import numpy as np

from app_engineering_trace import Trace
from app_operation_context import checkpoint
from app_parameter_capabilities import CapabilityDefinition, CapabilityRegistry
from app_parameter_contracts import metric_record, strict_json


NUMERIC_STRUCTURES = ('analog', 'quantized_analog', 'setpoint', 'unknown')


class AnalysisContext:
    """Public trusted-analyser context; emit creates the common evidence record."""
    def __init__(self, projection, *, run_id='', field_id='', mapping=None, scope=None, cancelled=None):
        self.projection = projection
        self.mapping = copy.deepcopy(mapping or {})
        self.scope = dict(scope or {'kind': 'run'})
        self.run_id, self.field_id = run_id, field_id
        self.cancelled = cancelled
        self.metrics, self.events, self.readiness, self.quality = [], [], [], []
        self.unit = str(projection.get('unit') or '')
        self.values = np.asarray(projection.get('values', []))
        if self.values.ndim != 1:
            raise ValueError('Field analysis requires a one-dimensional scalar array')
        self.indices = np.asarray(projection.get('source_indices', np.arange(len(self.values))))
        self.valid = np.array(projection.get('valid', np.ones(len(self.values), bool)), bool, copy=True)
        if len(self.valid) != len(self.values) or len(self.indices) != len(self.values):
            raise ValueError('Values, validity and source references must have equal lengths')
        self.x = None if projection.get('x_s') is None else np.asarray(projection['x_s'], float)
        if self.x is not None and (self.x.ndim != 1 or len(self.x) != len(self.values)):
            raise ValueError('Native coordinates must match the original values')
        self.native_valid = self.valid.copy()
        self.scope_selection = np.ones(len(self.values), bool)
        if self.x is not None and 'start_s' in self.scope and 'end_s' in self.scope:
            # Samples are included at both boundaries for numerical measurement;
            # event count attribution remains half-open in the event service.
            self.scope_selection = (self.x >= self.scope['start_s']) & (self.x <= self.scope['end_s'])
            self.valid &= self.scope_selection
        self.numeric = self.values.dtype.kind in 'biuf'
        self.y = np.asarray(self.values, float) if self.numeric else None
        self.finite = self.valid & np.isfinite(self.y) if self.numeric else self.valid.copy()
        self.trace = None
        self.active_definition = None
        self.time_reason = ''
        policy = projection.get('acquisition_policy') or {}
        self.policy = dict(policy) if isinstance(policy, dict) else {'mode': policy}
        if self.x is None or self.policy.get('mode') == 'sample_only':
            self.time_reason = 'No trustworthy time coordinate; only sample-domain evidence is available'
        elif not np.isfinite(self.x).all():
            self.time_reason = 'Nonfinite clock coordinates prevent trustworthy interval support'
        elif np.any(np.diff(self.x) < 0):
            self.time_reason = 'Backward timestamps/clock reset require a reviewed clock-domain repair policy'
        elif np.any(np.diff(self.x) == 0) and self.policy.get('duplicate_clock', 'reject') == 'reject':
            self.time_reason = 'Duplicate timestamps require an explicit first/last acquisition policy'
        elif (self.values.dtype.kind in 'iu' and any(abs(int(v))>2**53 for v in self.values[self.native_valid])
              and projection.get('structure','unknown') in NUMERIC_STRUCTURES):
            self.time_reason = 'Integer magnitude exceeds exact float64 representation; native extrema are retained but numerical timing moments require a reviewed scaling projection'
        elif self.numeric and projection.get('structure', 'unknown') in NUMERIC_STRUCTURES:
            channel = SimpleNamespace(kind='analog', unit=self.unit, coordinate_kind='time', coordinate_unit='s')
            y = np.where(self.native_valid & np.isfinite(self.y), self.y, np.nan)
            timing_keep = np.ones(len(self.x), bool)
            if self.policy.get('duplicate_clock') == 'first' and len(self.x):
                timing_keep = np.r_[True, np.diff(self.x) > 0]
            channel.values = lambda: (self.x[timing_keep], y[timing_keep])
            gap = self.policy.get('max_gap_s', self.policy.get('max_gap_seconds'))
            self.trace = Trace(channel, max_gap_seconds=gap, acquisition_policy=self.policy)
            mode = str(self.policy.get('interpolation', self.policy.get('mode', 'linear')))
            if mode in ('hold', 'held', 'sampled_hold', 'event', 'event_log', 'exact_event_log'):
                self.trace.kind = 'discrete'
        self.stats = self.trace.stats(self.scope.get('start_s'), self.scope.get('end_s')) if self.trace else {}
        if self.trace:
            self.quality.append(self.trace.quality(self.scope.get('start_s'), self.scope.get('end_s')))
        if self.time_reason:
            self.quality.append({'field_id': field_id, 'reason': self.time_reason, 'time_support': 'unavailable'})

    def check(self):
        checkpoint()
        if self.cancelled is not None and (self.cancelled() if callable(self.cancelled) else self.cancelled.is_set()):
            raise InterruptedError('Parameter analysis cancelled')

    def emit(self, metric_id, value=None, unit=None, *, status='computed', reason='', remedy='', **details):
        if isinstance(value, (float, np.floating)) and not np.isfinite(value):
            value, status = None, 'insufficient_data'
            reason = reason or 'No supported observations for this measurement'
        if value is None and status == 'computed':
            status = 'insufficient_data'
            reason = reason or 'No supported observations for this measurement'
        defaults = {'provenance': self.projection.get('provenance', {}),
            'supported_duration_s': self.stats.get('known_s'),
            'coverage_denominator_s': self.stats.get('duration_s'),
            'sample_count': int(self.finite.sum()), 'reasons': [reason] if reason else []}
        if self.active_definition is not None:
            defaults.update(capability_id=self.active_definition.capability_id,
                definition_version=self.active_definition.definition_version)
        defaults.update(details)
        record = metric_record(metric_id, value, self.unit if unit is None else unit,
            status=status, run_id=self.run_id, field_id=self.field_id,
            role=str(self.projection.get('role') or ''), instance=str(self.projection.get('instance') or ''),
            scope=self.scope, **defaults)
        self.metrics.append(record)
        if status not in ('computed', 'partial', 'not_observed'):
            self.readiness.append({'metric_id': metric_id, 'field_id': self.field_id, 'scope': self.scope,
                'status': status, 'reason': reason or record['reasons'][0], 'remedy': remedy or 'Review the required mapping, acquisition policy or source observations'})
        return record

    def timed(self, metric_id, value=None, unit=None, **details):
        if self.trace is None or not self.stats.get('known_s', 0):
            return self.emit(metric_id, unit=unit, status='insufficient_data',
                reason=self.time_reason or 'At least two valid observations on a supported interval are required',
                remedy='Declare a trustworthy timebase and acquisition policy; inspect invalid samples and gaps', **details)
        return self.emit(metric_id, value, unit, status='partial' if self.stats.get('coverage', 0) < 1-1e-12 else 'computed', **details)

    def segments(self):
        """Reuse Trace's union-knot segment support and interpolation semantics."""
        if self.trace is None:
            return (np.array([]),)*4
        from app_signal_comparison import _segments
        t, _ = self.trace.window(self.scope.get('start_s'), self.scope.get('end_s'))
        if len(t) < 2:
            return (np.array([]),)*4
        left, right, supported = _segments(self.trace, t[:-1], t[1:])
        return t[:-1][supported], t[1:][supported], left[supported], right[supported]


def _generic(projection, context):
    c = context
    c.emit('sample_count', int(c.scope_selection.sum()), 'count', weighting='original observations within scope')
    c.emit('valid_sample_count', int(c.finite.sum()), 'count', weighting='original observations with validity mask')
    positions = np.flatnonzero(c.finite)
    if not len(positions):
        for name in ('minimum', 'maximum', 'peak_absolute', 'first', 'last', 'range'):
            c.emit(name, status='insufficient_data', reason='No valid finite numeric observations')
    else:
        native = c.values[positions]
        native_values = [v.item() if isinstance(v,np.generic) else v for v in native]
        selected = {'minimum': int(positions[min(range(len(native_values)),key=lambda i:native_values[i])]),
                    'maximum': int(positions[max(range(len(native_values)),key=lambda i:native_values[i])]),
                    'peak_absolute': int(positions[max(range(len(native_values)),key=lambda i:abs(native_values[i]))]),
                    'first': int(positions[0]), 'last': int(positions[-1])}
        for name, position in selected.items():
            value = c.values[position].item() if isinstance(c.values[position],np.generic) else c.values[position]
            if name == 'peak_absolute': value=abs(value)
            details = {'source_sample_indices': [int(c.indices[position])], 'weighting': 'original observations'}
            if c.x is not None and np.isfinite(c.x[position]):
                details['time_s'] = float(c.x[position])
            c.emit(name, value, **details)
        c.emit('range', max(native_values)-min(native_values), statistic='difference', weighting='original observations')
        y = c.y[positions]
        percentiles = c.mapping.get('parameters', {}).get('percentiles', [5, 50, 95])
        for q in percentiles:
            if not isinstance(q, (float, int)) or isinstance(q, bool) or not 0 <= q <= 100:
                raise ValueError('Percentiles must be explicit numbers between 0 and 100')
            c.emit('sample_percentile_p' + format(q, 'g'), float(np.percentile(y, q, method='linear')),
                   parameters={'percentile': q, 'method': 'linear'}, weighting='unweighted original valid observations; sampling-density dependent')
    for name, key in (('time_mean', 'mean'), ('time_rms', 'rms'), ('time_std', 'std')):
        c.timed(name, c.stats.get(key), weighting='supported time; ' + ('held' if c.trace and c.trace.kind != 'analog' else 'piecewise linear'), statistic='difference' if name == 'time_std' else 'absolute')
    c.timed('supported_duration', c.stats.get('known_s'), 's', weighting='supported intervals only')
    c.timed('coverage_fraction', c.stats.get('coverage'), '1', weighting='supported duration / evaluated interval')
    start, end, left, right = c.segments()
    slopes = (right-left)/(end-start)
    for metric, operation in (('minimum_slope', np.min), ('maximum_slope', np.max)):
        c.timed(metric, float(operation(slopes)) if len(slopes) else None,
                (c.unit + '/s') if c.unit else 'raw-unit/s', statistic='difference', weighting='supported segment slopes')
    from app_parameter_domains import threshold_capabilities
    threshold_capabilities(c)


def _states(projection, context):
    from app_parameter_events import state_timeline
    c = context
    params = dict(c.mapping.get('parameters') or {})
    if params.get('nonzero_is_on') and not (c.mapping.get('authority') or {}).get('reviewed'):
        c.emit('state.encoding', status='needs_mapping', reason='The nonzero-is-ON interpretation requires reviewed authority')
        return
    if c.cancelled is not None:
        params['cancel'] = lambda: c.cancelled() if callable(c.cancelled) else c.cancelled.is_set()
    timeline = state_timeline(c.x, c.values, valid=c.native_valid, structure=projection['structure'],
        acquisition_policy=c.policy, dictionary=c.mapping.get('state_dictionary', projection.get('state_dictionary')),
        on_values=params.get('on_values'), parameters=params,
        identity={'run_id': c.run_id, 'field_id': c.field_id, 'role': projection.get('role', ''),
                  'instance': projection.get('instance', ''), 'source_indices': c.indices.tolist()})
    summary = dict(timeline.get('summary', {}))
    occupancy = timeline.get('occupancy', [])
    events = timeline.get('events', []) + timeline.get('transitions', []) + timeline.get('suppressed_events', [])
    if c.x is not None and 'start_s' in c.scope and 'end_s' in c.scope:
        start, end = float(c.scope['start_s']), float(c.scope['end_s'])
        clipped = []
        by_state = {}
        for interval in timeline.get('intervals', []):
            a, b = max(start,interval['start_s']), min(end,interval['end_s'])
            if b <= a: continue
            row = dict(interval,start_s=a,end_s=b)
            clipped.append(row)
            key = str(interval['state'])
            target = by_state.setdefault(key,{'state':interval['state'],'label':interval.get('label',interval['state']),'duration_s':0.,'episodes':0})
            target['duration_s'] += b-a; target['episodes'] += 1
        supported = sum(v['duration_s'] for v in by_state.values())
        occupancy = list(by_state.values())
        for row in occupancy: row['fraction'] = row['duration_s']/supported if supported else None
        selected = []
        for event in events:
            a,b = max(start,event.get('onset_s',start)),min(end,event.get('offset_s',end))
            onset = event.get('observed_onset') and start <= event.get('onset_s',start-1) < end
            if b>a or onset:
                selected.append(dict(event,scope=c.scope,scoped_duration_s=max(0.,b-a),scoped_onset_count=int(bool(onset))))
        events=selected
        transitions=[e for e in timeline.get('transitions',[]) if start<=e['onset_s']<end]
        summary = dict(supported_duration_s=supported,
            on_duration_s=sum(r['end_s']-r['start_s'] for r in clipped if r.get('active') is True),
            off_duration_s=sum(r['end_s']-r['start_s'] for r in clipped if r.get('active') is False),
            transition_count=len(transitions),rising_count=sum(e['type']=='rising' for e in transitions),
            falling_count=sum(e['type']=='falling' for e in transitions),
            episode_count=sum(e.get('scoped_onset_count',0) for e in selected if e.get('type') in ('active_episode','state_entry') and not e.get('suppressed')),
            state_sequence=[r['state'] for r in clipped])
        summary['duty_cycle']=summary['on_duration_s']/supported if supported else None
        summary['observed_episode_support']={'durations_s':[e['scoped_duration_s'] for e in selected if e.get('type') in ('active_episode','state_entry') and not e.get('suppressed')], 'clipped_to_scope':True}
        summary['initial_state']=next((r['state'] for r in clipped if r['start_s']==start),None)
        summary['final_state']=next((r['state'] for r in reversed(clipped) if r['end_s']==end),None)
    c.events.extend(events)
    c.readiness.extend(timeline.get('readiness', []))
    support = summary.get('supported_duration_s')
    sample_only = c.x is None or c.policy.get('mode') == 'sample_only'
    weighting = 'source-adjacent observations' if sample_only else 'half-open supported held-state intervals'
    for key, value in summary.items():
        if key not in ('interval_policy','edge_timing','event_filter_scope'):
            c.emit('state.' + key, value, 's' if key.endswith('_s') else ('1' if key == 'duty_cycle' else 'count' if key.endswith('_count') else ''),
                   weighting=weighting, evidence_basis='observed state timeline', supported_duration_s=support,
                   coverage_denominator_s=(c.scope['end_s']-c.scope['start_s']) if 'start_s' in c.scope and 'end_s' in c.scope else support)
    c.emit('state.occupancy', occupancy, '', weighting=weighting, supported_duration_s=support)


def _bitfield(projection, context):
    c = context
    masks = (c.mapping.get('parameters') or {}).get('bit_masks', [])
    if not masks or not (c.mapping.get('authority') or {}).get('reviewed', False):
        c.emit('bitfield.decoded_flags', status='needs_mapping', reason='Documented reviewed bit masks are required',
               remedy='Review each bit mask, name and active encoding; opaque packed values remain preserved')
        return
    combined = 0
    y = np.zeros(len(c.values), np.uint64)
    usable = np.zeros(len(c.values), bool)
    for i, value in enumerate(c.values):
        if not c.finite[i]: continue
        scalar=value.item() if isinstance(value,np.generic) else value
        if isinstance(scalar,(int,bool)):
            integer=int(scalar)
        elif isinstance(scalar,float) and np.isfinite(scalar) and scalar.is_integer():
            integer=int(scalar)
        else: continue
        if 0<=integer<2**64:
            y[i]=integer; usable[i]=True
    for mask in masks:
        name, bits = mask.get('name'), mask.get('mask')
        if not isinstance(name, str) or not name or not isinstance(bits, int) or isinstance(bits, bool) or bits <= 0 or bits >= 2**64 or combined & bits or mask.get('documented') is not True or not mask.get('source'):
            c.emit('bitfield.decoded_flags', status='invalid', reason='Bit masks require names, positive integers and nonoverlapping documented definitions')
            return
        combined |= bits
    for mask in masks:
        child = dict(projection, values=((y & np.uint64(mask['mask'])) != 0).astype(int), valid=usable,
                     structure='binary', instance=str(projection.get('instance', '')) + '/' + mask['name'])
        nested = AnalysisContext(child, run_id=c.run_id, field_id=c.field_id,
            mapping={'parameters': {'on_values': [1]}}, scope=c.scope, cancelled=c.cancelled)
        nested.active_definition=c.active_definition
        _states(child, nested)
        c.metrics.extend(nested.metrics); c.events.extend(nested.events); c.readiness.extend(nested.readiness)
    c.emit('bitfield.undecoded_values', sorted({int(v) & ~combined for v in y[usable]}), '', weighting='original valid observations')


def _metadata(projection, context):
    context.emit('metadata.observation_count', len(context.values), 'count')
    context.emit('metadata.values', [str(v) for v in context.values[:100]], '',
                 warnings=['Preview limited to first 100 source values'] if len(context.values) > 100 else [])


_DEFAULT = None


def capability_registry():
    """Return application built-ins; use clone() before adding local plugins."""
    global _DEFAULT
    if _DEFAULT is None:
        from app_parameter_domains import counter_capability, countdown_capability, role_capabilities
        registry = CapabilityRegistry()
        definitions = [
            (CapabilityDefinition('generic.numeric', structures=NUMERIC_STRUCTURES,
                scopes=('run', 'stage', 'interval'),
                parameters={'percentiles': {'default': [5, 50, 95], 'weighting': 'sample', 'method': 'linear'}},
                prerequisites=('scalar numeric observations',), coverage_policy='Trace-supported piecewise linear/held intervals; raw extrema retained'), _generic),
            (CapabilityDefinition('generic.states', structures=('binary', 'enum', 'categorical', 'pulse'),
                scopes=('run', 'stage', 'interval'),
                required_inputs=('values',), output_units=('s', 'count', '1'),
                coverage_policy='half-open supported held-state occupancy; censored boundaries retained'), _states),
            (CapabilityDefinition('generic.bitfield', structures=('bitfield',),
                scopes=('run', 'stage', 'interval'),
                prerequisites=('reviewed nonoverlapping masks',), output_units=('s', 'count'),
                coverage_policy='documented masks only; undecoded bits retained'), _bitfield),
            (CapabilityDefinition('generic.counter', structures=('counter',),
                scopes=('run', 'stage', 'interval'),
                prerequisites=('declared counter structure', 'reviewed reset/rollover policy'),
                coverage_policy='adjacent supported observations; never interpolate across resets'), counter_capability),
            (CapabilityDefinition('generic.countdown', structures=('countdown',),
                scopes=('run', 'stage', 'interval'),
                parameters={'pause_tolerance': {'required': True}, 'jump_threshold': {'required': True}},
                coverage_policy='adjacent supported observations; revisions are observed numeric changes'), countdown_capability),
            (CapabilityDefinition('generic.metadata', structures=('metadata',),
                scopes=('run', 'stage', 'interval'),
                coverage_policy='original observations; bounded preview'), _metadata),
            (CapabilityDefinition('semantic.roles', structures=NUMERIC_STRUCTURES,
                scopes=('run', 'stage', 'interval'),
                roles=(),
                prerequisites=('reviewed role and verified units/scaling',), output_units=('source', 's', 'L', 'Wh'),
                coverage_policy='Trace-supported intervals; role-specific thresholds must be explicit'), role_capabilities),
        ]
        for definition, analyser in definitions:
            registry.register(definition, analyser, trusted=True)
        _DEFAULT = registry
    return _DEFAULT


def analyse_field(projection, *, run_id='', field_id='', mapping=None, scopes=None, registry=None, cancelled=None):
    """Analyse one original field; independent capability failures remain auditable."""
    output = {'metrics': [], 'events': [], 'readiness': [], 'quality': []}
    if np.asarray(projection.get('values', [])).ndim != 1:
        reason = 'Vector or higher-dimensional observations require a registered structure-specific analyser; the source field remains preserved'
        output['metrics'].append(metric_record('field.availability', status='unsupported', run_id=run_id, field_id=field_id, reasons=[reason]))
        output['readiness'].append({'field_id':field_id,'status':'unsupported','reason':reason,'remedy':'Register a trusted vector analyser or review a scalar component projection'})
        return output
    for scope in (scopes if scopes is not None else [None]):
        checkpoint()
        c = AnalysisContext(projection, run_id=run_id, field_id=field_id, mapping=mapping, scope=scope, cancelled=cancelled)
        c.check()
        selected = list((registry or capability_registry()).applicable(projection))
        if not selected:
            c.emit('field.availability', status='unsupported', reason='No registered capability supports this structure',
                   remedy='Review the field structure or install a trusted analyser supporting it')
        for definition, analyser in selected:
            c.check()
            if definition.capability_id == 'generic.numeric' and not c.numeric:
                c.emit('numeric.availability', status='unsupported', reason='The original field is not scalar numeric data',
                       remedy='Map categorical/text structure or add an analyser for the preserved datatype')
                continue
            c.active_definition = definition
            if c.scope.get('kind', 'run') not in definition.scopes:
                c.emit(definition.capability_id + '.availability', status='unsupported', reason='Capability does not support this scope kind')
                continue
            if any(projection.get(key) is None for key in definition.required_inputs):
                c.emit(definition.capability_id + '.availability', status='missing_input', reason='Missing required capability input')
                continue
            before = (len(c.metrics), len(c.events), len(c.readiness), len(c.quality))
            try:
                analyser(projection, c)
                c.check()
                # A plugin may alternatively return records; the supported API
                # uses context.emit so metadata/provenance cannot be forgotten.
            except InterruptedError:
                raise
            except Exception as exc:
                del c.metrics[before[0]:]; del c.events[before[1]:]; del c.readiness[before[2]:]; del c.quality[before[3]:]
                c.emit(definition.capability_id + '.availability', status='error',
                       reason=f'{type(exc).__name__}: {exc}', remedy='Review capability parameters or the trusted analyser implementation',
                       definition_version=definition.definition_version)
        for key in output:
            output[key].extend(getattr(c, key))
    return strict_json(output)

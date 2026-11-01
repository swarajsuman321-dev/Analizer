"""Fast analysis of the signals a user selected, independent of their file count.

The familiar plotting interpretation is the starting point: numeric values stay
numeric and an actuator already displayed as ON/OFF receives held-state event
analysis. No appliance meaning, calibration, acceptance limit or manual review is
invented here. Advanced semantic review remains available separately.
"""
from copy import deepcopy
from datetime import datetime, timezone
import math
from pathlib import Path
from uuid import uuid4

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from app_adaptive_ui import ContentDialog
from app_channel_identity import channel_label
from app_compact_forms import ElidedComboBox, add_help
from app_dialog_history import remember_path, start_directory
from app_operation_context import checkpoint, cancellation_requested
from app_output import output_path
from app_parameter_contracts import metric_record, result_bundle


def _cancelled(cancelled):
    return bool(cancelled() if callable(cancelled) else cancelled is not None and cancelled.is_set())


def _check(cancelled):
    checkpoint()
    if _cancelled(cancelled):
        raise InterruptedError('Selected-signal analysis cancelled')


def _projection(channel, gap_factor, max_gap_seconds):
    """Read the complete displayed arrays once, preserving masks and shifts."""
    from app_time_units import minute_factor
    x, y = channel.values()
    valid = np.isfinite(y)
    timed = channel.coordinate_kind == 'time'
    try:
        seconds = np.asarray(x, float)*minute_factor(channel.coordinate_unit)*60 if timed else None
    except ValueError:
        seconds = None
    differences = np.diff(seconds) if seconds is not None else np.array([])
    positive = differences[differences > 0]
    gap = float(max_gap_seconds) if max_gap_seconds is not None else (
        gap_factor*float(np.median(positive)) if len(positive) else 0.)
    binary = bool(channel.attributes.get('actuator_binary'))
    values = y
    if binary:
        valid = valid & (y == np.floor(y))
        values = np.where(valid, (y != 0).astype(float), np.nan)
    structure = 'binary' if binary else ('enum' if channel.kind == 'discrete' and channel.unit.lower() in ('state', 'code', 'bool', 'boolean') else 'unknown')
    policy = {'mode': ('held' if channel.kind == 'discrete' or binary else 'continuous') if seconds is not None else 'sample_only',
              'max_gap_seconds': gap, 'duplicate_clock': 'last',
              'clock_domain': channel.attributes.get('clock_domain', '')}
    provenance = {'source_channel_id': channel.id, 'source_dataset_id': channel.dataset_id,
                  'source_name': channel.name, 'source': channel.source,
                  'value_interpretation': channel.attributes.get('value_interpretation', 'numeric'),
                  'actuator_interpretation': 'Existing plotted ON/OFF interpretation; finite zero OFF and finite nonzero integer ON' if binary else 'None applied',
                  'meaning_review': 'Physical role, calibration and device encoding have not been independently confirmed by quick analysis',
                  'gap_policy': 'User-specified maximum supported gap' if max_gap_seconds is not None else f'Existing conservative plot policy: {gap_factor:g} × median positive native sample interval',
                  'gap_limit_seconds': gap if seconds is not None else None,
                  'shift_coordinate_units': channel.shift, 'masks': deepcopy(channel.masks),
                  'original_samples_unchanged': True}
    mapping = {'state_dictionary': {}, 'parameters': {},
               'authority': {'kind': 'compatible_metadata', 'reviewed': False,
                             'source': 'Existing plotted interpretation'}, 'encoding': {}}
    return {'values': values, 'x_s': seconds, 'valid': valid,
            'source_indices': np.arange(len(y), dtype=np.int64), 'unit': channel.unit,
            'structure': structure, 'role': '', 'instance': '', 'signal_kind': 'unknown',
            'status': 'computed', 'acquisition_policy': policy, 'mapping': mapping,
            'provenance': provenance, 'run_id': channel.dataset_id,
            'field_id': channel.id, 'state_dictionary': {}}


def _clipped(projection, interval_s):
    """Use existing Trace interpolation only to add supported scope boundaries."""
    if interval_s is None or projection.get('x_s') is None:
        return projection
    from types import SimpleNamespace
    from app_engineering_trace import Trace
    x = projection['x_s']
    values = np.where(projection['valid'], projection['values'], np.nan)
    channel = SimpleNamespace(kind='discrete' if projection['structure'] in ('binary', 'enum') else 'analog',
        unit=projection['unit'], coordinate_kind='time', coordinate_unit='s', values=lambda: (x, values))
    trace = Trace(channel, max_gap_seconds=projection['acquisition_policy']['max_gap_seconds'])
    start, end = interval_s
    t, y = trace.window(start, end)
    indices = np.maximum(0, np.searchsorted(x, t, side='right')-1)
    return {**projection, 'x_s': t, 'values': y, 'valid': np.isfinite(y),
            'source_indices': projection['source_indices'][indices] if len(x) else np.array([], dtype=int),
            'provenance': {**projection['provenance'], 'scope_boundary_projection':
                'Supported native interpolation at scope boundaries; native observations remain unchanged'}}


def _origins(store, channels):
    from app_signal_comparison import _origin
    origins = {}
    for channel in channels:
        if channel.dataset_id not in origins:
            try:
                origins[channel.dataset_id] = _origin(store, channel)[0]
            except ValueError:
                origins[channel.dataset_id] = None
    return origins


def _pair(left, right, lf, rf, options, origins):
    """Reuse existing typed common-support comparison, including same-file pairs.

    Its analog adapter requires distinct temporary dataset identities. These
    identities are calculation-local; both still use their original run origin,
    and the returned record retains the true run/field identities.
    """
    from app_parameter_comparison import _analog, _state_compare
    states = {'binary', 'enum'}
    if (left['structure'] in states) != (right['structure'] in states):
        return {'comparison_type': 'field_pair', 'reference_field_id': lf['id'],
            'candidate_field_id': rf['id'], 'status': 'not_comparable',
            'reasons': ['Choose two numeric signals or two compatible state signals.'],
            'acceptance': {'status': 'not_evaluated', 'reasons': ['No engineering acceptance rule supplied']}}
    if left['structure'] in states and left['structure'] != right['structure']:
        return {'comparison_type': 'field_pair', 'reference_field_id': lf['id'],
            'candidate_field_id': rf['id'], 'status': 'not_comparable',
            'reasons': ['Binary actuator states and opaque enum codes have different meanings.'],
            'acceptance': {'status': 'not_evaluated', 'reasons': ['No engineering acceptance rule supplied']}}
    reference = {**lf, 'run_id': 'quick-reference:'+lf['id']}
    candidate = {**rf, 'run_id': 'quick-candidate:'+rf['id']}
    temporary_origins = {reference['run_id']: origins.get(lf['run_id']), candidate['run_id']: origins.get(rf['run_id'])}
    operation = _state_compare if left['structure'] in states else _analog
    result = operation(left, right, reference, candidate, options, temporary_origins)
    result.update(reference_run_id=lf['run_id'], candidate_run_id=rf['run_id'])
    if isinstance(result.get('alignment'), dict):
        result['alignment']['source_run_origins_s'] = {k: origins[k] for k in {lf['run_id'], rf['run_id']}}
    result['evidence_basis'] = 'Explicit user-selected signals and existing plotted numeric/state interpretations'
    result['physical_comparability'] = 'Descriptive signal difference; physical roles and controlled test equivalence are not established'
    return result


def analyse_selected_signals(store, channel_ids, reference_id=None, *, alignment='elapsed',
                             interval_s=None, gap_factor=3., max_gap_seconds=None,
                             registry=None, cancelled=None, mode='comparison'):
    """Analyse one or compare any number of explicitly selected plot signals."""
    from app_parameter_analytics import analyse_field
    from app_parameter_comparison import _display, compare_metric_records
    from app_parameter_events import actuator_relationships
    if alignment not in ('elapsed', 'native'):
        raise ValueError('Choose elapsed recording time or original time coordinates.')
    if mode not in ('analysis', 'comparison'):
        raise ValueError('Choose analysis or comparison mode.')
    if not math.isfinite(float(gap_factor)) or gap_factor <= 0:
        raise ValueError('The supported-gap factor must be positive and finite.')
    if max_gap_seconds is not None and (not math.isfinite(float(max_gap_seconds)) or max_gap_seconds < 0):
        raise ValueError('Maximum supported gap must be nonnegative and finite.')
    ids = list(dict.fromkeys(channel_ids))
    if not ids or any(id not in store.channels for id in ids):
        raise ValueError('Select at least one available signal to analyse.')
    if reference_id is not None and reference_id not in ids:
        raise ValueError('The reference must be one of the selected signals.')
    reference_id = reference_id or ids[0]
    channels = [store.channels[id] for id in ids]
    if interval_s is not None:
        if len(interval_s) != 2 or not np.isfinite(interval_s).all():
            raise ValueError('The cursor interval needs two finite second coordinates.')
        interval_s = sorted(float(v) for v in interval_s)
    scopes = [{'kind': 'interval', 'start_s': interval_s[0], 'end_s': interval_s[1]}] if interval_s is not None else None
    origins = _origins(store, channels)
    runs, inventory, metrics, events, quality, readiness, pictures = [], [], [], [], [], [], []
    run_ids = set()
    projections = {}
    options = {'alignment': alignment, 'plot_budget': 2000}
    for channel in channels:
        _check(cancelled)
        checkpoint('Analysing '+channel.name, len(inventory), len(channels))
        if channel.dataset_id not in run_ids:
            dataset = store.datasets.get(channel.dataset_id)
            runs.append({'id': channel.dataset_id, 'name': dataset.name if dataset else 'Unassigned signals',
                'source': dataset.source if dataset else channel.source,
                'metadata': {'scope': 'Selected signals only', 'recording_origin_s': origins.get(channel.dataset_id)}})
            run_ids.add(channel.dataset_id)
        projection = _projection(channel, gap_factor, max_gap_seconds)
        projections[channel.id] = projection
        field = {'id': channel.id, 'channel_id': channel.id, 'run_id': channel.dataset_id,
            'run_name': next(run['name'] for run in runs if run['id'] == channel.dataset_id),
            'original_name': channel.name, 'display_name': channel.name, 'unit': channel.unit,
            'structure': projection['structure'], 'native_samples': len(channel.x),
            'source_key': str(channel.attributes.get('source_column', channel.name)),
            'disposition': 'analysed', 'mapping': projection['mapping'],
            'metadata': projection['provenance']}
        inventory.append(field)
        output = analyse_field(projection, run_id=channel.dataset_id, field_id=channel.id,
            mapping=projection['mapping'], scopes=scopes, registry=registry, cancelled=cancelled)
        metrics.extend(output['metrics']); events.extend(output['events'])
        quality.extend(output['quality']); readiness.extend(output['readiness'])
        if projection['x_s'] is None:
            readiness.append({'field_id': channel.id, 'status': 'needs_review',
                'reason': 'No usable time coordinate; sample-domain results only.',
                'remedy': 'Review the time column and coordinate unit during import.'})
        picture = _display(projection, field, options, origins)
        if picture:
            pictures.append(picture)
    by_id = {field['id']: field for field in inventory}
    comparisons, pairings = [], []
    reference_metrics = {m['metric_id']: m for m in metrics if m['field_id'] == reference_id}
    for candidate_id in ids if mode == 'comparison' else []:
        _check(cancelled)
        if candidate_id == reference_id:
            continue
        pairings.append({'reference_field_id': reference_id, 'candidate_field_id': candidate_id,
                         'confirmed': True, 'status': 'confirmed',
                         'authority': 'Explicitly selected signals; first selected signal is reference unless changed'})
        left, right = projections[reference_id], projections[candidate_id]
        for candidate in (m for m in metrics if m['field_id'] == candidate_id):
            reference = reference_metrics.get(candidate['metric_id'])
            if reference is not None:
                comparable = (left['structure'] in ('binary', 'enum')) == (right['structure'] in ('binary', 'enum'))
                comparisons.append(compare_metric_records(reference, candidate, comparable=comparable,
                    reasons=[] if comparable else ['Numeric and state interpretations differ'], physical=False))
        comparisons.append(_pair(_clipped(left, interval_s), _clipped(right, interval_s),
            by_id[reference_id], by_id[candidate_id], options, origins))
    # Overlap is a within-recording timing relationship. Independently elapsed
    # recordings may be compared, but their valve states are not simultaneous.
    overlap_groups = []
    for run_id in run_ids:
        actuators = {id: _clipped(q, interval_s) for id, q in projections.items()
                     if q['run_id'] == run_id and q['structure'] == 'binary'}
        if len(actuators) < 2:
            continue
        _check(cancelled)
        overlap = actuator_relationships(actuators, {'cancel': lambda: _cancelled(cancelled)})
        if not overlap.get('shared_supported_duration_s'):
            for key in ('union_duration_s', 'all_on_duration_s', 'all_off_duration_s'):
                overlap[key] = None
            overlap['status'] = 'insufficient_data'
            overlap['reason'] = 'No shared known state interval; unknown support is not zero.'
        for pair in overlap.get('overlaps', []):
            if not pair['supported_duration_s']:
                pair.update(duration_s=None, episode_count=None, status='insufficient_data',
                            reason='No pair-specific shared known state interval.')
        overlap_groups.append({'run_id': run_id, **overlap})
        common = overlap.get('shared_supported_duration_s', 0.)
        for name, key in [('Any selected actuator ON', 'union_duration_s'),
                          ('All selected actuators ON together', 'all_on_duration_s'),
                          ('All selected actuators OFF', 'all_off_duration_s')]:
            value = overlap.get(key) if common else None
            metrics.append(metric_record('actuator.'+key, value, 's', run_id=run_id,
                status='computed' if common else 'insufficient_data', scope=scopes[0] if scopes else None,
                evidence_basis='Observed shared held-state support', label=name,
                supported_duration_s=common, coverage_denominator_s=common,
                reasons=[] if common else ['No shared known state interval; unknown support is not zero.'],
                provenance={'fields': list(actuators), 'command_is_not_physical_flow': True}))
        for row in overlap.get('overlaps', []):
            support = row['supported_duration_s']
            names = [by_id[id]['original_name'] for id in row['field_ids']]
            metrics.append(metric_record('actuator.pair_overlap', row['duration_s'] if support else None, 's',
                run_id=run_id, status='computed' if support else 'insufficient_data',
                scope=scopes[0] if scopes else None, label=' + '.join(names)+' ON together',
                evidence_basis='Observed pair-specific shared held-state support',
                supported_duration_s=support, coverage_denominator_s=support,
                event_count=row['episode_count'] if support else None,
                reasons=[] if support else ['No pair-specific shared known state interval.'],
                provenance={'field_ids': row['field_ids'], 'intervals_s': row['intervals']}))
        readiness.extend(overlap.get('readiness', []))
    kind = 'comparison' if mode == 'comparison' and len(ids) > 1 else 'analysis'
    return result_bundle(kind, runs, inventory, metrics,
        comparisons=comparisons, events=events, pairings=pairings, quality=quality,
        readiness=readiness, plot_series=pictures, status='completed',
        actuator_overlaps=overlap_groups,
        provenance={'engine': 'app_quick_signal_analysis', 'definition_version': '1',
            'selection_policy': 'Selected signals only; no limit on selected signal count',
            'reference_field_id': reference_id,
            'comparison_policy': 'Reference versus every other selected signal' if kind == 'comparison' else 'Independent measurements and within-recording actuator relationships; no baseline comparison',
            'recording_origins_s': origins, 'alignment': alignment,
            'scope': scopes[0] if scopes else {'kind': 'run'},
            'interpretation_policy': 'Existing plotted values and ON/OFF interpretation; no inferred physical roles, scaling or acceptance',
            'gap_policy': {'factor': gap_factor, 'max_gap_seconds': max_gap_seconds},
            'overlap_policy': 'Within each original recording only; common known support, never elapsed-aligned different recordings'})


def _number(value, suffix=''):
    if value is None:
        return 'Unknown'
    return f'{float(value):.6g}{suffix}' if isinstance(value, (int, float)) else str(value)


class QuickSignalResults:
    """Construct a familiar result dialog with a concise first page."""
    @staticmethod
    def create(window, result, bundle):
        from app_parameter_controls import ParameterResultsDialog
        dialog = ParameterResultsDialog(window, result, bundle)
        dialog.setWindowTitle('Selected Signal Analysis & Comparison')
        fields = {field['id']: field for field in result['inventory']}
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        reference = fields.get(result['provenance']['reference_field_id'], {})
        label = QtWidgets.QLabel(('Reference: '+str(reference.get('run_name', ''))+' · '+str(reference.get('original_name', ''))+
            '. Each additional selected signal is compared with this reference. Differences are descriptive; no Pass/Fail rule is assumed.')
            if result['kind'] == 'comparison' else 'Analysis of each selected signal, with within-recording actuator overlaps. No reference/candidate comparison or Pass/Fail rule is assumed.')
        label.setWordWrap(True)
        layout.addWidget(label)
        scope = result.get('provenance', {}).get('scope', {})
        scope_text = (f"Native cursor interval: {scope['start_s']/60:.6g}–{scope['end_s']/60:.6g} min. "
                      'The same original clock coordinates are applied before display alignment.'
                      if scope.get('kind') == 'interval' else 'Measurement scope: whole recording for each selected signal.')
        scope_label = QtWidgets.QLabel(scope_text)
        scope_label.setWordWrap(True)
        layout.addWidget(scope_label)
        rows = []
        for field in result['inventory']:
            records = {m['metric_id']: m for m in result['metrics'] if m.get('field_id') == field['id']}
            get = lambda key: records.get(key, {}).get('value')
            rows.append([field['run_name']+' · '+field['original_name'], field['unit'] or 'Raw / unknown',
                _number(get('minimum')), _number(get('maximum')), _number(get('time_mean')),
                _number(get('state.on_duration_s')/60 if get('state.on_duration_s') is not None else None, ' min'),
                _number(get('state.duty_cycle')*100 if get('state.duty_cycle') is not None else None, '%')])
        table = QtWidgets.QTableWidget(len(rows), 7)
        table.setHorizontalHeaderLabels(['Signal / Recording', 'Unit', 'Minimum', 'Maximum', 'Time Average', 'ON Time', 'Duty'])
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for row, values in enumerate(rows):
            for column, value in enumerate(values):
                table.setItem(row, column, QtWidgets.QTableWidgetItem(value))
        layout.addWidget(table)
        pair_rows = [row for row in result.get('comparisons', []) if row.get('comparison_type') in ('common_window_analog', 'common_window_state')]
        if pair_rows:
            paired = QtWidgets.QTableWidget(len(pair_rows), 6)
            paired.setHorizontalHeaderLabels(['Compared with Reference', 'Mean Difference', 'Mean Absolute Difference', 'Largest Difference', 'State Agreement', 'Compared Known Time'])
            paired.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            paired.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
            for row, record in enumerate(pair_rows):
                candidate = fields[record['candidate_field_id']]
                available = record['status'] == 'computed'
                unit = (' '+record['unit']) if record.get('unit') else ' recorded units'
                values = [candidate['run_name']+' · '+candidate['original_name'],
                    _number(record.get('mean_bias'), unit), _number(record.get('mae'), unit),
                    _number(record.get('max_absolute_difference'), unit),
                    _number(record['agreement_fraction']*100 if record.get('agreement_fraction') is not None else None, '%'),
                    _number(record.get('supported_duration_s', 0)/60 if available else None, ' min')]
                for column, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(value)
                    item.setToolTip('\n'.join(record.get('reasons', [])))
                    paired.setItem(row, column, item)
            layout.addWidget(paired)
        overlap_metrics = [m for m in result['metrics'] if m['metric_id'].startswith('actuator.')]
        if overlap_metrics:
            overlaps = QtWidgets.QTableWidget(len(overlap_metrics), 3)
            overlaps.setHorizontalHeaderLabels(['Observed Actuator Relationship', 'ON Together / Duration', 'Known Shared Support'])
            overlaps.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            overlaps.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
            for row, record in enumerate(overlap_metrics):
                for col, text in enumerate([record.get('label', record['metric_id']),
                    _number(record['value']/60 if record['value'] is not None else None, ' min'),
                    _number(record.get('supported_duration_s', 0)/60, ' min')]):
                    item = QtWidgets.QTableWidgetItem(text)
                    item.setToolTip('\n'.join(record.get('reasons', [])))
                    overlaps.setItem(row, col, item)
            layout.addWidget(overlaps)
        dialog.tabs.insertTab(0, page, 'Summary')
        dialog.tabs.setCurrentIndex(0)
        return dialog


class QuickSignalDialog(ContentDialog):
    """A compact optional chooser; ordinary selected-signal use is one action."""
    def __init__(self, controls, selected=()):
        super().__init__(controls.window)
        self.controls = controls
        self.setWindowTitle('Choose Signals to Compare')
        self.setObjectName('quickSignalComparisonOptions')
        layout = QtWidgets.QVBoxLayout(self)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(['Recording / Signal', 'Unit'])
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        roots = {}
        self.items = {}
        for channel in controls.window.store.channels.values():
            dataset = controls.window.store.datasets.get(channel.dataset_id)
            root = roots.get(channel.dataset_id)
            if root is None:
                root = QtWidgets.QTreeWidgetItem(self.tree, [dataset.name if dataset else 'Unassigned'])
                root.setFlags(root.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable |
                              QtCore.Qt.ItemFlag.ItemIsAutoTristate)
                root.setCheckState(0, QtCore.Qt.CheckState.Unchecked)
                root.setToolTip(0, 'Select or deselect signals in this recording only.')
                roots[channel.dataset_id] = root
            item = QtWidgets.QTreeWidgetItem(root, [channel.name, channel.unit or 'Unknown'])
            item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, QtCore.Qt.CheckState.Checked if channel.id in selected else QtCore.Qt.CheckState.Unchecked)
            self.items[channel.id] = item
        self.tree.expandAll()
        layout.addWidget(self.tree)
        form = QtWidgets.QFormLayout()
        self.reference = ElidedComboBox()
        form.addRow('Reference signal', self.reference)
        self.alignment = ElidedComboBox()
        self.alignment.addItem('Elapsed time from each recording start', 'elapsed')
        self.alignment.addItem('Original time coordinates', 'native')
        form.addRow('Time alignment', self.alignment)
        self.scope = ElidedComboBox()
        self.scope.addItem('Whole recording', 'run')
        self.scope.addItem('Current shared A–B interval (native clock)', 'interval')
        form.addRow('Measurement scope', self.scope)
        self.max_gap = QtWidgets.QDoubleSpinBox()
        self.max_gap.setRange(0, 86400000)
        self.max_gap.setSpecialValueText('Automatic: 3 × median sample interval')
        self.max_gap.setSuffix(' s')
        form.addRow('Maximum supported time gap', self.max_gap)
        layout.addLayout(form)
        add_help(layout, 'Select any number of signals, including signals from one recording. '
                 'The reference is compared with each other selected signal. '
                 'Known actuator states use held ON/OFF timing; unknown gaps never become OFF. '
                 'Overlap is calculated within each recording, not between unrelated recordings. '
                 'Quick analysis describes loaded plot values; use reviewed semantic mapping for calibrated physical conclusions.')
        self.error = QtWidgets.QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setText('Compare & Prepare Report')
        buttons.accepted.connect(self._start)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.tree.itemChanged.connect(self._refresh_reference)
        self._refresh_reference()

    def selected(self):
        return [id for id, item in self.items.items() if item.checkState(0) == QtCore.Qt.CheckState.Checked]

    def _refresh_reference(self, *_):
        current = self.reference.currentData()
        self.reference.clear()
        for id in self.selected():
            self.reference.addItem(channel_label(self.controls.window.store, id, include_source=True), id)
        self.reference.setCurrentIndex(max(0, self.reference.findData(current)))

    def _start(self):
        try:
            self.controls.start(self.selected(), self.reference.currentData(), alignment=self.alignment.currentData(),
                max_gap_seconds=self.max_gap.value() or None,
                interval_s=self.controls.current_interval() if self.scope.currentData() == 'interval' else None)
        except (ValueError, OSError) as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class QuickSignalAnalysisControls(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.last_result = self.last_bundle = None
        self.dialog = self.result_dialog = None
        self.action = QtGui.QAction('Compare Selected Signals', self)
        self.action.setObjectName('compareSelectedSignals')
        self.action.setToolTip('Compare two, three or more selected signals; the first selected signal is the reference. No fixed pair limit.')
        self.action.triggered.connect(lambda: window.guard(self.compare_selected))
        self.analyse_action = QtGui.QAction('Analyse Selected Signals', self)
        self.analyse_action.setObjectName('analyseSelectedSignals')
        self.analyse_action.setToolTip('Measurements, events and overlap for the selected or visible signals')
        self.analyse_action.triggered.connect(lambda: window.guard(self.analyse_selected))
        self.setup_action = QtGui.QAction('Choose Comparison Signals & Timing…', self)
        self.setup_action.triggered.connect(lambda: window.guard(self.show_dialog))

    def selected(self):
        ids = list(dict.fromkeys(id for id in self.window.portal.selected() if id in self.window.store.channels))
        if not ids:
            ids = list(dict.fromkeys(id for pane in self.window.active_workspace.visible_panes()
                                    for id in pane.ids if id in self.window.store.channels))
        return ids

    def compare_selected(self):
        ids = self.selected()
        return self.start(ids) if len(ids) > 1 else self.show_dialog(ids)

    def analyse_selected(self):
        ids = self.selected()
        if not ids:
            raise ValueError('Select or plot at least one signal to analyse.')
        pane = self.window.active_workspace.active
        use_interval = (self.window.stats_scope.currentText() == 'Cursor interval' and
                        pane is not None and pane.coordinate and pane.coordinate[0] == 'time')
        interval = self.current_interval() if use_interval else None
        return self.start(ids, mode='analysis', interval_s=interval)

    def current_interval(self):
        from app_time_units import minute_factor
        pane = self.window.active_workspace.active
        if pane is None or not pane.coordinate or pane.coordinate[0] != 'time':
            raise ValueError('Choose a time-based graph to analyse the shared A–B interval, or select Whole recording.')
        return sorted(float(line.value())*minute_factor(pane.coordinate[1])*60 for line in pane.cursor_lines)

    def show_dialog(self, selected=None):
        self.window.mutate()
        if not self.window.store.channels:
            raise ValueError('Open a recording first, then choose signals to compare.')
        if self.dialog is not None:
            self.dialog.show(); self.dialog.raise_()
            return self.dialog
        dialog = QuickSignalDialog(self, self.selected() if selected is None else selected)
        self.dialog = dialog
        dialog.finished.connect(lambda code: setattr(self, 'dialog', None))
        dialog.show()
        return dialog

    def start(self, ids, reference_id=None, *, alignment='elapsed', interval_s=None, max_gap_seconds=None, mode='comparison'):
        self.window.mutate()
        ids = list(dict.fromkeys(ids))
        if not ids or any(id not in self.window.store.channels for id in ids):
            raise ValueError('Choose at least one available signal.')
        if mode == 'comparison' and len(ids) > 1:
            self.window.data_comparison.add_channels(ids)
        store = self.window.store
        metadata = deepcopy(self.window.report_metadata())
        registry = self.window.studio.plugins.parameter_registry.clone()
        fallback = output_path('Selected signal analysis.pdf', 'reports').parent
        directory = Path(start_directory('QuickSignalReport', fallback))
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S%fZ')
        destination = directory/('Selected signals-'+timestamp+'-'+uuid4().hex[:8]+'.pdf')
        for action in (self.action, self.analyse_action, self.setup_action):
            action.setEnabled(False)

        def work():
            from app_parameter_report import export_parameter_report
            result = analyse_selected_signals(store, ids, reference_id, alignment=alignment,
                interval_s=interval_s, max_gap_seconds=max_gap_seconds,
                registry=registry, cancelled=cancellation_requested, mode=mode)
            checkpoint('Preparing selected-signal report and complete evidence')
            bundle = export_parameter_report(destination, result, metadata=metadata)
            return result, bundle

        def complete(value):
            self.last_result, self.last_bundle = value
            if self.result_dialog is not None:
                self.result_dialog.close()
            dialog = QuickSignalResults.create(self.window, self.last_result, self.last_bundle)
            self.result_dialog = dialog
            dialog.finished.connect(lambda code: self._closed(dialog))
            dialog.show()
            remember_path('QuickSignalReport', destination)
            self.window.last_export = Path(self.last_bundle['pdf'])
            self.window.open_export_button.show(); self.window.open_export_folder_button.show()
            self.window.statusBar().showMessage('Selected-signal analysis and report saved: '+str(destination))

        def finished(error):
            for action in (self.action, self.analyse_action, self.setup_action):
                action.setEnabled(True)
        try:
            self.window.background(work, complete, title='Analysing selected signals', on_finished=finished)
        except Exception:
            finished(None)
            raise
        return True

    def _closed(self, dialog):
        if self.result_dialog is dialog:
            self.result_dialog = None

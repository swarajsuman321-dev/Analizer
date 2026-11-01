"""Inventory, review and typed analysis without changing the live plot sources.

Qt objects stay on the GUI thread. Workers receive immutable source arrays and
plain reviewed settings; the same completed bundle feeds the result tables and
all report formats. Unknown fields need no wizard before generic analysis.
"""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from app_adaptive_ui import ContentDialog
from app_compact_forms import ElidedComboBox
from app_dialog_history import remember_path, start_directory
from app_operation_context import checkpoint, cancellation_requested
from app_output import output_path
from app_parameter_contracts import STRUCTURES
from app_parameter_inventory import inventory_runs
from app_parameter_semantics import (ParameterTemplates2, resolve_mapping,
                                     validate_mapping, template_scope)


def _text(value):
    if value is None:
        return 'Not Available'
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    return str(value)


def _label(field, runs):
    run = next((r for r in runs if r['id'] == field['run_id']), {})
    return str(run.get('name', 'Recording'))+' · '+field['original_name']+' ['+str(field.get('unit') or 'raw / unknown unit')+']'


class ParameterReviewDialog(ContentDialog):
    """Common review for any reader; advanced contracts remain explicit JSON."""
    def __init__(self, field, mapping, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Review Parameter Meaning and Timing')
        self.setObjectName('parameterMeaningReview')
        self.field, self.original = field, deepcopy(mapping)
        layout = QtWidgets.QVBoxLayout(self)
        title = QtWidgets.QLabel(field['original_name']+' · source '+field['source_key'])
        title.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        layout.addWidget(title)
        tabs = QtWidgets.QTabWidget()
        layout.addWidget(tabs)
        basic = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(basic)
        self.fields = {}
        choices = {'structure': sorted(STRUCTURES),
                   'signal_kind': ['unknown', 'measurement', 'command', 'feedback', 'reference', 'context', 'status'],
                   'stored_values': ['unresolved', 'raw', 'engineering'],
                   'mode': ['sample_only', 'continuous', 'held', 'event']}
        values = {**mapping, 'stored_values': mapping['encoding'].get('stored_values', 'unresolved'),
                  'mode': mapping['acquisition_policy'].get('mode', 'sample_only')}
        names = [('display_name', 'Display name'), ('structure', 'Signal structure'),
                 ('role', 'Role (leave blank if unknown)'), ('instance', 'Instance / sensor identity'),
                 ('location', 'Location'), ('function', 'Function'),
                 ('signal_kind', 'Measurement / command / feedback'), ('unit', 'Output unit'),
                 ('stored_values', 'Stored value encoding'), ('mode', 'Acquisition policy')]
        for key, label in names:
            widget = ElidedComboBox() if key in choices else QtWidgets.QLineEdit()
            if key in choices:
                widget.addItems(choices[key])
                widget.setCurrentText(str(values.get(key, '')))
            else:
                widget.setText(str(values.get(key, '')))
            widget.setAccessibleName(label)
            form.addRow(label, widget)
            self.fields[key] = widget
        self.max_gap = QtWidgets.QLineEdit('' if mapping['acquisition_policy'].get('max_gap_seconds') is None else str(mapping['acquisition_policy']['max_gap_seconds']))
        self.max_gap.setPlaceholderText('Required for continuous / held timing; seconds')
        form.addRow('Maximum supported gap (s)', self.max_gap)
        self.clock_reviewed = QtWidgets.QCheckBox('I confirm the native clock and acquisition policy')
        self.clock_reviewed.setChecked(mapping['acquisition_policy'].get('clock_reviewed') is True)
        form.addRow(self.clock_reviewed)
        self.confirm = QtWidgets.QCheckBox('I confirm this meaning and encoding from source documentation or review')
        self.confirm.setChecked(mapping['authority'].get('reviewed') is True)
        form.addRow(self.confirm)
        self.authority = QtWidgets.QLineEdit(str(mapping['authority'].get('source', '')))
        self.authority.setPlaceholderText('Document, recipe, device specification, or reviewed observation')
        form.addRow('Evidence / authority', self.authority)
        tabs.addTab(basic, 'Meaning & Timing')
        family = QtWidgets.QWidget()
        family_form = QtWidgets.QFormLayout(family)
        family_note = QtWidgets.QLabel('Optional documented source family for safe template reuse. Future files must declare this family or you must explicitly choose it; matching channel names alone never reuse scaling or state dictionaries.')
        family_note.setWordWrap(True)
        family_form.addRow(family_note)
        scope = template_scope(field)
        self.family_fields = {}
        for key, label in [('source_schema', 'Source schema / protocol version'), ('device_family', 'Device family'), ('firmware_family', 'Firmware family')]:
            editor = QtWidgets.QLineEdit(scope.get(key, ''))
            self.family_fields[key] = editor
            family_form.addRow(label, editor)
        family_form.addRow('Encoding signature', QtWidgets.QLabel(scope['encoding_signature']))
        tabs.addTab(family, 'Template Compatibility')
        self.advanced = {}
        for key, label in [('transforms', 'Transforms'), ('state_dictionary', 'State Dictionary'),
                           ('parameters', 'Analysis Parameters'), ('decoder', 'Decoder')]:
            editor = QtWidgets.QPlainTextEdit(json.dumps(mapping.get(key, [] if key == 'transforms' else {}), ensure_ascii=False, indent=2))
            editor.setAccessibleName(label+' JSON')
            self.advanced[key] = editor
            tabs.addTab(editor, label)
        source = QtWidgets.QPlainTextEdit(_text(field))
        source.setReadOnly(True)
        tabs.addTab(source, 'Original Source Evidence')
        self.save_template = QtWidgets.QCheckBox('Save this review as a reusable template when schema/device/firmware are compatible')
        self.save_template.setChecked(True)
        layout.addWidget(self.save_template)
        self.error = QtWidgets.QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept_review)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        mapping = deepcopy(self.original)
        for key, widget in self.fields.items():
            value = widget.currentText() if isinstance(widget, QtWidgets.QComboBox) else widget.text().strip()
            if key == 'stored_values':
                mapping['encoding'][key] = value
            elif key == 'mode':
                mapping['acquisition_policy'][key] = value
            else:
                mapping[key] = value
        mapping['acquisition_policy'].update(
            clock_reviewed=self.clock_reviewed.isChecked(),
            max_gap_seconds=float(self.max_gap.text()) if self.max_gap.text().strip() else None)
        mapping['authority'] = {'kind': 'user_confirmed' if self.confirm.isChecked() else 'unresolved',
                                'source': self.authority.text().strip(), 'version': '1',
                                'reviewed': self.confirm.isChecked()}
        for key, editor in self.advanced.items():
            mapping[key] = json.loads(editor.toPlainText())
        return validate_mapping(mapping, self.field)

    def _accept_review(self):
        try:
            self.values()
        except (ValueError, TypeError) as exc:
            self.error.setText(str(exc))
            return
        self.accept()

    def reviewed_field(self):
        field = deepcopy(self.field)
        scope = {key: editor.text().strip() for key, editor in self.family_fields.items()}
        field.setdefault('metadata', {})['template_scope'] = scope
        return field


class ParameterResultsDialog(ContentDialog):
    """Read-only render of the exact computation delivered to the report writer."""
    def __init__(self, window, result, bundle=None):
        super().__init__(window)
        self.setWindowTitle('Recording Analysis & Comparison Results')
        self.setObjectName('parameterResults')
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.result, self.bundle = result, bundle
        layout = QtWidgets.QVBoxLayout(self)
        status = QtWidgets.QLabel('Results: '+str(result.get('status', 'completed'))+
            ' · '+str(len(result.get('inventory', [])))+' source fields · '+
            str(len(result.get('metrics', [])))+' measurements. Acceptance is evaluated only where a rule is supplied.')
        status.setWordWrap(True)
        layout.addWidget(status)
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.details = QtWidgets.QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(140)
        self.details.setAccessibleName('Selected result evidence, reasons and provenance')
        self.tables = {}
        definitions = [
            ('Comparisons', 'comparisons', ['metric_id', 'reference', 'candidate', 'delta', 'delta_unit', 'relative_percent', 'status', 'reasons']),
            ('Measurements', 'metrics', ['field_id', 'metric_id', 'value', 'unit', 'status', 'reasons']),
            ('Inventory', 'inventory', ['original_name', 'run_id', 'structure', 'disposition', 'native_samples', 'unit']),
            ('Readiness & Quality', 'readiness', ['field_id', 'status', 'reasons']),
            ('Events', 'events', ['field_id', 'type', 'start_s', 'end_s', 'left_censored', 'right_censored']),
            ('Stages', 'stages', ['run_id', 'type', 'label', 'start_s', 'end_s', 'evidence_basis']),
            ('Field Pairing', 'pairings', ['reference_field_id', 'candidate_field_id', 'status', 'reasons']),
            ('Source Quality', 'quality', ['run_id', 'field_id', 'status', 'reasons'])]
        for title, key, columns in definitions:
            records = result.get(key, [])
            table = QtWidgets.QTableWidget(len(records), len(columns))
            table.setHorizontalHeaderLabels([c.replace('_', ' ').title() for c in columns])
            table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
            table.setWordWrap(False)
            table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Interactive)
            table.horizontalHeader().setStretchLastSection(True)
            for row, record in enumerate(records):
                for col, name in enumerate(columns):
                    value = record.get(name)
                    if value is None and name == 'type':
                        value = record.get('event_type', record.get('kind'))
                    item = QtWidgets.QTableWidgetItem(_text(value))
                    item.setToolTip(_text(record))
                    table.setItem(row, col, item)
            table.currentCellChanged.connect(lambda row, col, oldrow, oldcol, records=records:
                self.details.setPlainText(_text(records[row]) if 0 <= row < len(records) else ''))
            self.tables[key] = table
            self.tabs.addTab(table, title+' ('+str(len(records))+')')
        self._plots(result.get('plot_series', []))
        layout.addWidget(self.details)
        buttons = QtWidgets.QHBoxLayout()
        if bundle:
            for title, key in [('Open PDF Report', 'pdf'), ('Open Excel Evidence', 'workbook'), ('Open JSON Evidence', 'evidence')]:
                button = QtWidgets.QPushButton(title)
                button.clicked.connect(lambda checked=False, key=key: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(Path(bundle[key]).resolve()))))
                buttons.addWidget(button)
        source_plot = QtWidgets.QPushButton('Plot Selected Source Field')
        source_plot.setToolTip('Add the field selected in Inventory or Measurements to the Comparison workspace using the existing plot tools')
        source_plot.clicked.connect(lambda: window.guard(lambda: self.plot_source(window)))
        buttons.addWidget(source_plot)
        buttons.addStretch()
        close = QtWidgets.QPushButton('Close')
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def plot_source(self, window):
        page = self.tabs.currentWidget()
        selected = next(((key, table.currentRow()) for key, table in self.tables.items() if table is page), None)
        if selected is None or selected[1] < 0:
            self.details.setPlainText('Choose a source field in Inventory or a measurement row first.')
            return
        record = self.result.get(selected[0], [])[selected[1]]
        field_id = record.get('field_id', record.get('id'))
        field = next((f for f in self.result.get('inventory', []) if f.get('id') == field_id), {})
        channel_id = field.get('channel_id')
        if channel_id not in window.store.channels:
            self.details.setPlainText('This field has no numeric plot projection, or its recording was closed. Its source evidence remains in the inventory and report.')
            return
        window.data_comparison.add_channels([channel_id])

    def _plots(self, series):
        import pyqtgraph as pg
        if not series:
            return
        tabs = QtWidgets.QTabWidget()
        colors = ('#00D2FF', '#FF9F1C', '#A78BFA', '#4ADE80', '#F472B6', '#FACC15')
        for title, xkey in [('Original Native Coordinates', 'original_x'), ('Comparison Alignment', 'aligned_x')]:
            page = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(page)
            # Unit groups retain independent axes and never overlay pressure,
            # temperature and encoded states on one misleading physical scale.
            groups = {}
            for item in series:
                key = (item.get('coordinate_unit', 'sample'), item.get('unit', ''))
                groups.setdefault(key, []).append(item)
            for (xunit, yunit), items in groups.items():
                graph = pg.PlotWidget()
                graph.addLegend(offset=(8, 8))
                graph.setLabel('left', yunit or 'Raw values')
                graph.setLabel('bottom', 'Time' if xunit in ('s', 'min') else 'Coordinate', units='min' if xunit == 's' else xunit)
                for index, item in enumerate(items):
                    x = np.asarray(item.get(xkey, item.get('x', [])), float)
                    y = np.asarray(item.get('y', []), float)
                    if len(x) != len(y):
                        continue
                    if xunit == 's':
                        x = x / 60
                    graph.plot(x, y, pen=pg.mkPen(colors[index % len(colors)], width=1.2),
                               name=str(item.get('label', item.get('field_id', 'Parameter'))), connect='finite')
                layout.addWidget(graph)
            tabs.addTab(page, title)
        self.tabs.addTab(tabs, 'Plots')


class ParameterAnalysisDialog(ContentDialog):
    def __init__(self, controls):
        super().__init__(controls.window)
        self.setWindowTitle('Analyse & Compare Recordings')
        self.setObjectName('parameterAnalysisDialog')
        self.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        self.controls = controls
        self.runs = inventory_runs(controls.window.store)
        self.fields = [field for run in self.runs for field in run['fields']]
        self.mappings = controls.reviewed_mappings(self.fields)
        layout = QtWidgets.QVBoxLayout(self)
        explanation = QtWidgets.QLabel('Every source field is accounted for. Run generic analysis immediately, or review meaning, encoding and timing to enable physical results. Comparisons use only explicitly confirmed field pairs.')
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel('Reference recording'))
        self.baseline = ElidedComboBox()
        for run in self.runs:
            self.baseline.addItem(run['name'], run['id'])
        row.addWidget(self.baseline, 1)
        self.alignment = ElidedComboBox()
        for title, value in [('Elapsed time from each recording start', 'elapsed'), ('Original native coordinates', 'native'),
                             ('Confirmed time anchors', 'anchor'), ('Manual time offsets', 'manual'), ('Confirmed stage-relative display', 'stage_relative')]:
            self.alignment.addItem(title, value)
        row.addWidget(self.alignment, 1)
        layout.addLayout(row)
        scope_row = QtWidgets.QHBoxLayout()
        scope_row.addWidget(QtWidgets.QLabel('Measurement scope'))
        self.scope = ElidedComboBox()
        self.scope.addItem('Whole recording (each native clock)', 'run')
        self.scope.addItem('Selected graph A–B interval (native clock)', 'interval')
        self.scope.setToolTip('Per-run measurements use original native seconds before alignment. A–B applies those same original clock coordinates to every selected run.')
        scope_row.addWidget(self.scope, 1)
        load_profile = QtWidgets.QPushButton('Load Analysis Profile…')
        load_profile.clicked.connect(self.load_profile)
        scope_row.addWidget(load_profile)
        family = QtWidgets.QPushButton('Use Saved Source Family…')
        family.setToolTip('Explicitly identify the reference recording’s documented family and reuse only encoding-compatible saved reviews')
        family.clicked.connect(self.use_saved_family)
        scope_row.addWidget(family)
        layout.addLayout(scope_row)
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs, 1)
        self.inventory = QtWidgets.QTableWidget(len(self.fields), 7)
        self.inventory.setHorizontalHeaderLabels(['Recording / Field', 'Unit', 'Samples', 'Disposition', 'Structure', 'Review', 'Timing'])
        self.inventory.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.inventory.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.inventory.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.inventory.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.inventory.cellDoubleClicked.connect(lambda row, col: self.review(row))
        self.tabs.addTab(self.inventory, 'All Source Fields')
        pairs = QtWidgets.QWidget()
        pairs_layout = QtWidgets.QVBoxLayout(pairs)
        self.pair_table = QtWidgets.QTableWidget(0, 3)
        self.pair_table.setHorizontalHeaderLabels(['Reference field', 'Candidate field', 'Confirmed pair'])
        self.pair_table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        pairs_layout.addWidget(self.pair_table)
        buttons = QtWidgets.QHBoxLayout()
        add = QtWidgets.QPushButton('Add Field Pair')
        add.clicked.connect(self.add_pair)
        remove = QtWidgets.QPushButton('Remove Selected Pair')
        remove.clicked.connect(lambda: self.pair_table.removeRow(self.pair_table.currentRow()) if self.pair_table.currentRow() >= 0 else None)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch()
        pairs_layout.addLayout(buttons)
        self.tabs.addTab(pairs, 'Reviewed Field Pairing')
        advanced = QtWidgets.QWidget()
        advanced_layout = QtWidgets.QVBoxLayout(advanced)
        advanced_help = QtWidgets.QLabel('Optional advanced settings: comparison_mode (baseline or pairwise), anchors_s, offsets_s, scopes, stage_definitions and relationship_rules. Times use seconds; elapsed is the default. No physical limits are supplied automatically.')
        advanced_help.setWordWrap(True)
        advanced_layout.addWidget(advanced_help)
        self.options = QtWidgets.QPlainTextEdit(json.dumps(controls.state().get('options', {}), ensure_ascii=False, indent=2))
        advanced_layout.addWidget(self.options)
        self.tabs.addTab(advanced, 'Advanced Analysis Settings')
        self.error = QtWidgets.QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        actions = QtWidgets.QHBoxLayout()
        review = QtWidgets.QPushButton('Review Selected Field…')
        review.clicked.connect(lambda: self.review(self.inventory.currentRow()))
        actions.addWidget(review)
        notes = QtWidgets.QPushButton('Report Details…')
        notes.clicked.connect(lambda: controls.window.guard(controls.window.edit_report_details))
        actions.addWidget(notes)
        actions.addStretch()
        self.run_button = QtWidgets.QPushButton('Analyse & Prepare Report')
        self.run_button.setDefault(True)
        self.run_button.clicked.connect(self.start)
        actions.addWidget(self.run_button)
        cancel = QtWidgets.QPushButton('Close')
        cancel.clicked.connect(self.reject)
        actions.addWidget(cancel)
        layout.addLayout(actions)
        self.refresh()
        state = controls.state()
        self.baseline.setCurrentIndex(max(0, self.baseline.findData(state.get('baseline_run_id'))))
        self.alignment.setCurrentIndex(max(0, self.alignment.findData(state.get('alignment', 'elapsed'))))
        for pair in state.get('pairings', []):
            self.add_pair(pair)

    def refresh(self):
        for row, field in enumerate(self.fields):
            mapping = self.mappings[field['id']]
            values = [_label(field, self.runs), field.get('unit', ''), field['native_samples'], field['disposition'],
                      mapping['structure'], 'Reviewed' if mapping['authority'].get('reviewed') else 'Raw observation / needs review',
                      mapping['acquisition_policy'].get('mode', 'sample_only')]
            for col, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(str(value))
                item.setToolTip(_text(field))
                self.inventory.setItem(row, col, item)

    def review(self, row):
        if not 0 <= row < len(self.fields):
            self.error.setText('Choose a source field to review.')
            return
        field = self.fields[row]
        dialog = ParameterReviewDialog(field, self.mappings[field['id']], self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        mapping = dialog.values()
        reviewed_field = dialog.reviewed_field()
        self.controls.save_field_scope(reviewed_field)
        field['metadata'] = reviewed_field['metadata']
        self.mappings[field['id']] = mapping
        if dialog.save_template.isChecked() and mapping['authority'].get('reviewed'):
            try:
                templates = ParameterTemplates2()
                templates.save(templates.review(field, mapping))
            except (OSError, ValueError) as exc:
                self.error.setText('Review is active for this workspace; reusable template could not be saved: '+str(exc))
        self.controls.save_state(mappings=self.mappings)
        self.refresh()

    def add_pair(self, pair=None):
        pair = pair if isinstance(pair, dict) else {}
        row = self.pair_table.rowCount()
        self.pair_table.insertRow(row)
        for column, key in enumerate(('reference_field_id', 'candidate_field_id')):
            combo = ElidedComboBox()
            combo.addItem('Choose a source field', None)
            for field in self.fields:
                combo.addItem(_label(field, self.runs), field['id'])
            combo.setCurrentIndex(max(0, combo.findData(pair.get(key))))
            self.pair_table.setCellWidget(row, column, combo)
        confirm = QtWidgets.QCheckBox('Confirmed')
        confirm.setToolTip('I confirm these represent compatible parameters and instances; the engine still checks units, meaning and timing.')
        confirm.setChecked(pair.get('confirmed') is True)
        self.pair_table.setCellWidget(row, 2, confirm)

    def load_profile(self):
        from app_dialog_history import open_file
        path, _ = open_file(self, 'Load versioned analysis profile', filter='Analysis profile (*.json)', purpose='ParameterProfile')
        if not path:
            return
        try:
            from app_parameter_profiles import profile_v2
            profile = profile_v2(json.loads(Path(path).read_text(encoding='utf-8')))
            self.controls.save_state(profile=profile)
            for field in self.fields:
                if not self.mappings[field['id']]['authority'].get('reviewed'):
                    self.mappings[field['id']] = resolve_mapping(field, profile=profile)
            self.refresh()
            self.error.setText('Profile loaded. Alias matches are suggestions; review meaning, encoding and timing before physical interpretation.')
        except (OSError, ValueError, TypeError) as exc:
            self.error.setText(str(exc))

    def use_saved_family(self):
        templates = ParameterTemplates2()
        scopes = {}
        for entry in templates.entries.values():
            scope = entry['scope']
            if scope.get('reusable'):
                key = (scope['source_schema'], scope['device_family'], scope['firmware_family'])
                scopes[key] = scope
        if not scopes:
            self.error.setText('No complete source-family template is saved yet. Review a parameter and enter its documented schema, device family and firmware family under Template Compatibility.')
            return
        from app_compact_forms import choose_item
        keys = list(scopes)
        labels = [' · '.join(key) for key in keys]
        choice, accepted = choose_item(self, 'Confirm Source Family', 'Apply to the reference recording only. Confirm the documented family:', labels)
        if not accepted:
            return
        selected = scopes[keys[labels.index(choice)]]
        matched = 0
        for field in self.fields:
            if field['run_id'] != self.baseline.currentData():
                continue
            field.setdefault('metadata', {})['template_scope'] = {
                key: selected[key] for key in ('source_schema', 'device_family', 'firmware_family')}
            self.controls.save_field_scope(field)
            resolved = templates.resolve(field)
            if resolved['mapping'] is not None:
                self.mappings[field['id']] = resolved['mapping']
                matched += 1
        self.controls.save_state(mappings=self.mappings)
        self.refresh()
        self.error.setText(str(matched)+' compatible saved reviews applied. New fields and incompatible encodings still require review. Choose another reference recording to identify its family separately.')

    def settings(self):
        options = json.loads(self.options.toPlainText())
        if not isinstance(options, dict):
            raise ValueError('Advanced analysis settings must be a JSON object.')
        pairings = []
        for row in range(self.pair_table.rowCount()):
            reference = self.pair_table.cellWidget(row, 0).currentData()
            candidate = self.pair_table.cellWidget(row, 1).currentData()
            if reference is None or candidate is None or reference == candidate:
                raise ValueError('Each field pair needs two different source fields.')
            if next(f for f in self.fields if f['id'] == reference)['run_id'] == next(f for f in self.fields if f['id'] == candidate)['run_id']:
                raise ValueError('Compare fields belonging to different recordings.')
            pairings.append({'reference_field_id': reference, 'candidate_field_id': candidate,
                             'confirmed': self.pair_table.cellWidget(row, 2).isChecked()})
        options.update(alignment=self.alignment.currentData(), baseline_run_id=self.baseline.currentData())
        if self.scope.currentData() == 'interval':
            pane = self.controls.window.active_workspace.active
            if pane is None or pane.coordinate[0] != 'time':
                raise ValueError('Choose a time-based graph for the native A–B interval scope.')
            from app_time_units import minute_factor
            a, b = sorted(float(cursor.value())*minute_factor(pane.coordinate[1])*60 for cursor in pane.cursor_lines)
            options['scopes'] = [{'kind': 'interval', 'start_s': a, 'end_s': b}]
        return options, pairings

    def start(self):
        try:
            options, pairings = self.settings()
            self.controls.save_state(mappings=self.mappings, pairings=pairings,
                                     baseline_run_id=self.baseline.currentData(),
                                     alignment=self.alignment.currentData(), options=options)
            self.controls.start([run['id'] for run in self.runs], self.mappings, pairings, options)
        except (ValueError, TypeError, OSError) as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class ParameterAnalysisControls(QtCore.QObject):
    """One entry point for inventory, single-run analysis and reviewed comparison."""
    def __init__(self, window):
        super().__init__(window)
        self.window, self.dialog, self.result_dialog = window, None, None
        self.last_result = self.last_bundle = None
        self.action = QtGui.QAction('Analyse & Compare Recordings…', self)
        self.action.setObjectName('analyseCompareRecordings')
        self.action.setToolTip('Inventory every source field, review meaning and compare explicitly paired parameters; prepare PDF, Excel and JSON evidence')
        self.action.triggered.connect(lambda: window.guard(self.show_dialog))

    def state(self):
        state = self.window.engineering.session.get('parameter_analysis', {})
        return deepcopy(state) if isinstance(state, dict) else {}

    def save_state(self, **values):
        self.window.engineering.session['parameter_analysis'] = {**self.state(), **deepcopy(values)}

    def save_field_scope(self, field):
        """Persist reviewed annotations separately from original source arrays."""
        dataset = self.window.store.datasets.get(field['run_id'])
        if dataset is None:
            raise ValueError('This source recording was closed.')
        if not dataset.frame.attrs.get('inventory_fields'):
            from app_parameter_inventory import _default_specs
            dataset.frame.attrs['inventory_fields'] = _default_specs(dataset.frame)
        specs = dataset.frame.attrs['inventory_fields']
        if field['source_key'] not in specs:
            position = list(map(str, dataset.frame.columns)).index(field['source_key'])
            specs[field['source_key']] = {'column_position': position, 'original_name': field['original_name']}
        specs[field['source_key']].setdefault('metadata', {})['template_scope'] = deepcopy(field.get('metadata', {}).get('template_scope', {}))

    def reviewed_mappings(self, fields):
        previous = self.state().get('mappings', {})
        templates = ParameterTemplates2()
        mappings = {}
        for field in fields:
            saved = templates.resolve(field)
            explicit = previous.get(field['id']) or saved.get('mapping')
            mappings[field['id']] = resolve_mapping(field, explicit, profile=self.state().get('profile'))
        return mappings

    def show_dialog(self):
        self.window.mutate()
        if not self.window.store.datasets:
            raise ValueError('Open a recording first. Numeric, categorical and metadata-only datasets are supported in the inventory.')
        if self.dialog is not None:
            self.dialog.show()
            self.dialog.raise_()
            return self.dialog
        self.dialog = ParameterAnalysisDialog(self)
        self.dialog.finished.connect(lambda code: setattr(self, 'dialog', None))
        self.dialog.show()
        return self.dialog

    def start(self, dataset_ids, mappings, pairings, options):
        self.window.mutate()
        if not dataset_ids or any(id not in self.window.store.datasets for id in dataset_ids):
            raise ValueError('A selected recording was closed. Reopen the analysis dialog to refresh the inventory.')
        store = self.window.store
        mappings, pairings, options = deepcopy(mappings), deepcopy(pairings), deepcopy(options)
        metadata = self.window.report_metadata()
        profile = self.state().get('profile')
        fallback = output_path('Parameter analysis.pdf', 'reports').parent
        folder = Path(start_directory('ParameterAnalysisReport', fallback))
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S%fZ')
        path = folder/('Parameter analysis-'+timestamp+'-'+uuid4().hex[:8]+'.pdf')
        registry = self.window.studio.plugins.parameter_registry.clone()
        comparators = self.window.studio.plugins.comparator_registry.clone()
        self.action.setEnabled(False)

        def work():
            from app_parameter_comparison import analyse_recordings
            from app_parameter_report import export_parameter_report
            def progress(stage, *args):
                if isinstance(stage, dict):
                    checkpoint('Analysing '+str(stage.get('label') or stage.get('phase', 'parameters')),
                               stage.get('completed'), stage.get('total'))
                else:
                    checkpoint(str(stage))
            options.update(cancelled=cancellation_requested, progress=progress)
            result = analyse_recordings(store, dataset_ids, mappings=mappings, pairings=pairings,
                                        profile=profile, options=options, registry=registry, comparators=comparators)
            checkpoint('Preparing readable parameter report and full evidence')
            bundle = export_parameter_report(path, result, metadata=metadata)
            return {'result': result, 'bundle': bundle}

        def complete(value):
            self.last_result, self.last_bundle = value['result'], value['bundle']
            if self.result_dialog is not None:
                self.result_dialog.close()
            self.result_dialog = ParameterResultsDialog(self.window, self.last_result, self.last_bundle)
            current = self.result_dialog
            current.finished.connect(lambda code: self._result_closed(current))
            self.result_dialog.show()
            remember_path('ParameterAnalysisReport', path)
            self.window.last_export = Path(self.last_bundle['pdf'])
            self.window.open_export_button.show()
            self.window.open_export_folder_button.show()
            self.window.statusBar().showMessage('Parameter report and complete evidence saved: '+str(path))

        try:
            self.window.background(work, complete, title='Analysing recordings',
                                   on_finished=lambda error: self.action.setEnabled(True))
        except Exception:
            self.action.setEnabled(True)
            raise

    def _result_closed(self, dialog):
        if self.result_dialog is dialog:
            self.result_dialog = None

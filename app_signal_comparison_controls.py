"""One-action, explicit two-recording comparisons using immutable source data.

The controller only chooses source identities and captures GUI state. Numerical
comparison and the complete report transaction run in the existing worker; the
main Analysis/Comparison plots are never rebound or shifted by this workflow.
"""
from copy import deepcopy
from datetime import datetime, timezone
import math
from pathlib import Path
from uuid import uuid4

import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from app_adaptive_ui import ContentDialog
from app_channel_identity import channel_details, channel_label
from app_compact_forms import ElidedComboBox
from app_dialog_history import remember_path, start_directory
from app_operation_context import checkpoint
from app_output import output_path


def _number(value, suffix=''):
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return 'Not Available'
    return f'{number:.6g}{suffix}' if math.isfinite(number) else 'Not Available'


class SignalComparisonDialog(ContentDialog):
    """Compact source-qualified fallback when the current selection is unclear."""
    def __init__(self, controls, selected=()):
        super().__init__(controls.window)
        self.controls = controls
        self.setWindowTitle('Compare Two Signals')
        self.setObjectName('compareTwoSignalsDialog')
        self.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QtWidgets.QVBoxLayout(self)
        explanation = QtWidgets.QLabel(
            'Choose one parameter from each recording. Comparison uses confirmed '
            'program starts as time zero and retains later channel starts. '
            'The original measurements and plotted views stay unchanged.')
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        form = QtWidgets.QFormLayout()
        layout.addLayout(form)
        self.reference = ElidedComboBox()
        self.candidate = ElidedComboBox()
        self.reference.setAccessibleName('Reference parameter and recording')
        self.candidate.setAccessibleName('Candidate parameter and recording')
        form.addRow('Reference parameter', self.reference)
        form.addRow('Candidate parameter', self.candidate)
        self.reference.addItem('Choose a parameter', None)
        for channel in controls.window.store.channels.values():
            if channel.dataset_id in controls.window.store.datasets:
                self._add_channel(self.reference, channel)
        self.error = QtWidgets.QLabel()
        self.error.setWordWrap(True)
        self.error.setAccessibleName('Comparison selection error')
        layout.addWidget(self.error)
        buttons = QtWidgets.QHBoxLayout()
        notes = QtWidgets.QPushButton('Report Details & Conclusions…')
        notes.setToolTip('Optional notes shared by comparison and engineering reports')
        notes.clicked.connect(lambda: controls.window.guard(controls.window.edit_report_details))
        notes.setVisible(callable(getattr(controls.window, 'edit_report_details', None)))
        buttons.addWidget(notes)
        buttons.addStretch()
        self.compare_button = QtWidgets.QPushButton('Compare and Prepare Report')
        self.compare_button.setDefault(True)
        buttons.addWidget(self.compare_button)
        cancel = QtWidgets.QPushButton('Cancel')
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        layout.addLayout(buttons)
        self.reference.currentIndexChanged.connect(self._reference_changed)
        self.candidate.currentIndexChanged.connect(self._validate)
        self.compare_button.clicked.connect(self._compare)
        # More than two choices must never become an arbitrary automatic pair.
        initial = list(dict.fromkeys(selected))
        if len(initial) == 2:
            self.reference.setCurrentIndex(max(0, self.reference.findData(initial[0])))
        self._reference_changed()
        if len(initial) == 2:
            self.candidate.setCurrentIndex(max(0, self.candidate.findData(initial[1])))
        self._validate()

    def _add_channel(self, combo, channel):
        text = channel_label(self.controls.window.store, channel, include_source=True)
        combo.addItem(text+' ['+(channel.unit or 'Unknown unit')+']', channel.id)
        combo.setItemData(combo.count()-1, channel_details(self.controls.window.store, channel),
                          QtCore.Qt.ItemDataRole.ToolTipRole)

    def _reference_changed(self, *_):
        store = self.controls.window.store
        selected = self.candidate.currentData()
        reference = store.channels.get(self.reference.currentData())
        blocker = QtCore.QSignalBlocker(self.candidate)
        self.candidate.clear()
        self.candidate.addItem('Choose a parameter from another recording', None)
        for channel in store.channels.values():
            if (channel.dataset_id in store.datasets and reference is not None
                    and channel.dataset_id != reference.dataset_id):
                self._add_channel(self.candidate, channel)
        self.candidate.setCurrentIndex(max(0, self.candidate.findData(selected)))
        del blocker
        self._validate()

    def _validate(self, *_):
        try:
            self.controls.validate_pair(self.reference.currentData(), self.candidate.currentData())
        except ValueError as exc:
            self.error.setText(str(exc))
            self.compare_button.setEnabled(False)
            return
        self.error.setText('Reference and Candidate are shown in this order in the report. '
                           'Differences are Candidate − Reference. No appliance profile is required.')
        self.compare_button.setEnabled(True)

    def _compare(self):
        try:
            self.controls.start(self.reference.currentData(), self.candidate.currentData())
        except Exception as exc:
            self.error.setText(str(exc))
            return
        self.accept()


class SignalComparisonResults(ContentDialog):
    """A short factual result, with one-click access to the complete evidence."""
    def __init__(self, window, result, bundle=None):
        super().__init__(window)
        self.result = result
        self.bundle = bundle
        self.setWindowTitle('Two-Signal Comparison Results')
        self.setObjectName('twoSignalComparisonResults')
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QtWidgets.QVBoxLayout(self)
        labels = []
        for role in ('reference', 'candidate'):
            source = result.get(role, {})
            labels.append(role.title()+': '+str(source.get('dataset') or source.get('source') or 'Recording')+
                          ' · '+str(source.get('name') or source.get('channel_id') or 'Parameter'))
        self.sources = QtWidgets.QLabel('\n'.join(labels))
        self.sources.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.sources.setWordWrap(True)
        layout.addWidget(self.sources)
        alignment = result.get('alignment', {}).get('description') or 'Elapsed time from each recording’s start'
        self.scope = QtWidgets.QLabel(str(alignment))
        self.scope.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.scope.setWordWrap(True)
        layout.addWidget(self.scope)
        if result.get('status') != 'compared':
            reason = QtWidgets.QLabel(str(result.get('reason') or 'The selected signals could not be compared.'))
            reason.setTextFormat(QtCore.Qt.TextFormat.PlainText)
            reason.setWordWrap(True)
            layout.addWidget(reason)
        else:
            metrics = result.get('metrics', {})
            unit = str(metrics.get('unit') or '')
            value_suffix = (' '+unit) if unit else ''
            coverage = metrics.get('coverage_fraction')
            rows = [
                ('Mean difference (Candidate − Reference)', _number(metrics.get('mean_bias'), value_suffix)),
                ('Mean absolute difference', _number(metrics.get('mean_absolute_difference'), value_suffix)),
                ('Root mean square difference', _number(metrics.get('rmse'), value_suffix)),
                ('Largest absolute difference', _number(metrics.get('max_absolute_difference'), value_suffix)),
                ('Compared supported time', _number(metrics.get('compared_duration_min'), ' min')),
                ('Supported comparison coverage', _number(coverage*100 if isinstance(coverage, (int, float)) else None, '%')),
            ]
            self.metrics = QtWidgets.QTableWidget(len(rows), 2)
            self.metrics.setHorizontalHeaderLabels(['Result', 'Value'])
            self.metrics.verticalHeader().hide()
            self.metrics.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
            self.metrics.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
            self.metrics.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            for row, (name, value) in enumerate(rows):
                self.metrics.setItem(row, 0, QtWidgets.QTableWidgetItem(name))
                self.metrics.setItem(row, 1, QtWidgets.QTableWidgetItem(value))
            layout.addWidget(self.metrics)
            facts = [str(value) for value in result.get('summary', [])]
            limitations = [str(value) for value in result.get('limitations', [])]
            self.notes = QtWidgets.QPlainTextEdit('\n'.join(facts+limitations))
            self.notes.setReadOnly(True)
            self.notes.setAccessibleName('Comparison findings and data limitations')
            self.notes.setMaximumHeight(180)
            layout.addWidget(self.notes)
        buttons = QtWidgets.QHBoxLayout()
        if bundle:
            for label, key in (('Open Report', 'pdf'), ('Open Workbook', 'workbook')):
                button = QtWidgets.QPushButton(label)
                button.clicked.connect(lambda checked=False, key=key: self.open_path(bundle[key]))
                buttons.addWidget(button)
            folder = QtWidgets.QPushButton('Open Folder')
            folder.clicked.connect(lambda: self.open_path(Path(bundle['pdf']).parent))
            buttons.addWidget(folder)
        buttons.addStretch()
        close = QtWidgets.QPushButton('Close')
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    @staticmethod
    def open_path(path):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(Path(path).resolve())))


class SignalComparisonControls(QtCore.QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.dialog = None
        self.result_dialog = None
        self.last_result = None
        self.last_bundle = None
        self.action = QtGui.QAction('Compare Two Signals', self)
        self.action.setObjectName('compareTwoSignals')
        self.action.setToolTip('Select parameters with confirmed program starts and prepare PDF, Excel and JSON evidence')
        self.action.triggered.connect(lambda: window.guard(self.compare_selected))

    def validate_pair(self, reference, candidate):
        store = self.window.store
        a, b = store.channels.get(reference), store.channels.get(candidate)
        if a is None or b is None:
            raise ValueError('Choose one reference parameter and one candidate parameter.')
        if a.id == b.id:
            raise ValueError('Choose two different parameters from different recordings.')
        if not a.dataset_id or not b.dataset_id or a.dataset_id not in store.datasets or b.dataset_id not in store.datasets:
            raise ValueError('Choose parameters belonging to two loaded recordings.')
        if a.dataset_id == b.dataset_id:
            raise ValueError('Choose one parameter from each of two different recordings.')
        return a, b

    def compare_selected(self):
        self.window.mutate()
        selected = list(dict.fromkeys(id for id in self.window.portal.selected() if id in self.window.store.channels))
        pair = selected if len(selected) == 2 else []
        if len(selected) < 2:
            visible = list(dict.fromkeys(id for pane in self.window.active_workspace.visible_panes()
                                        for id in pane.ids if id in self.window.store.channels))
            if len(visible) == 2:
                pair = visible
        if len(pair) == 2:
            try:
                self.validate_pair(*pair)
            except ValueError:
                pass
            else:
                return self.start(*pair)
        return self.show_dialog(selected)

    def show_dialog(self, selected=()):
        self.window.mutate()
        if self.dialog is not None:
            self.dialog.show()
            self.dialog.raise_()
            return self.dialog
        dialog = SignalComparisonDialog(self, selected)
        self.dialog = dialog
        dialog.finished.connect(lambda _result, current=dialog: self._dialog_finished(current))
        dialog.show()
        return dialog

    def _dialog_finished(self, current):
        if self.dialog is current:
            self.dialog = None

    def _report_snapshot(self, pair):
        """Each source plot retains its own original clock and complete span."""
        panes = []
        for channel in pair:
            x, y = channel.values()
            low, high = (float(x[0]), float(x[-1])) if len(x) else (0., 0.)
            finite = y[np.isfinite(y)]
            bottom, top = (float(finite.min()), float(finite.max())) if len(finite) else (0., 1.)
            if top == bottom:
                top = bottom+1
            panes.append({'ids': [channel.id], 'bindings': {channel.id: channel.unit or 'Value'},
                          'range': [[low, high], [bottom, top]], 'axes': {},
                          'cursors': [low, high], 'cursor_mode': 'dual', 'cursor_locks': [None, None],
                          'snap': True, 'annotations': [], 'show_grid': True, 'show_legends': True,
                          'normalized': False})
        return {'layout': 'Horizontal split', 'panes': panes, 'active': 0,
                'report_kind': 'comparison', 'workspace_name': 'Two-signal comparison',
                'statistics_scope': 'Whole recording', 'time_axes_locked': False}

    def start(self, reference_id, candidate_id):
        self.window.mutate()
        pair = self.validate_pair(reference_id, candidate_id)
        from app_program_alignment import program_start
        for channel in pair:program_start(self.window.store,channel.dataset_id)
        store = self.window.store
        snapshot = self._report_snapshot(pair)
        metadata = deepcopy(self.window.report_metadata() if callable(getattr(self.window, 'report_metadata', None)) else {})
        fallback = output_path('Signal comparison.pdf', 'reports').parent
        directory = Path(start_directory('SignalComparisonReport', fallback))
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S%fZ')
        destination = directory/('Signal comparison-'+timestamp+'-'+uuid4().hex[:8]+'.pdf')
        self.action.setEnabled(False)

        def work():
            from app_signal_comparison import compare_signals
            from app_comparison_report import export_comparison_bundle
            checkpoint('Comparing the selected parameters')
            result = compare_signals(store, reference_id, candidate_id, alignment='program')
            if result.get('status') != 'compared':
                return {'result': result, 'bundle': None}
            report_metadata = {**metadata, 'Signal comparison': result}
            checkpoint('Preparing comparison report and complete evidence')
            bundle = export_comparison_bundle(destination, store, snapshot, metadata=report_metadata)
            for key in ('pdf', 'workbook', 'evidence'):
                if not isinstance(bundle.get(key), (str, Path)) or not Path(bundle[key]).is_file():
                    raise ValueError('The comparison report did not produce its complete '+key+' output.')
            return {'result': result, 'bundle': bundle}

        def finished(_error):
            self.action.setEnabled(True)

        try:
            self.window.background(work, self._complete, title='Comparing two signals', on_finished=finished)
        except Exception:
            self.action.setEnabled(True)
            raise
        return True

    def _complete(self, value):
        self.last_result = value['result']
        self.last_bundle = value['bundle']
        if self.result_dialog is not None:
            self.result_dialog.close()
        self.result_dialog = SignalComparisonResults(self.window, self.last_result, self.last_bundle)
        self.result_dialog.finished.connect(lambda _result, current=self.result_dialog: self._results_finished(current))
        self.result_dialog.show()
        if self.last_bundle:
            path = Path(self.last_bundle['pdf'])
            remember_path('SignalComparisonReport', path)
            self.window.last_export = path
            self.window.open_export_button.show()
            self.window.open_export_folder_button.show()
            self.window.statusBar().showMessage('Comparison report and complete evidence saved: '+str(path))
        else:
            self.window.statusBar().showMessage(str(self.last_result.get('reason') or 'These signals could not be compared.'))

    def _results_finished(self, current):
        if self.result_dialog is current:
            self.result_dialog = None

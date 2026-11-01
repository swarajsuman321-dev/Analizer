"""Explicit tabular import options; unsupported bytes are never guessed as data."""
from PySide6 import QtWidgets
from app_adaptive_ui import ContentDialog
from app_reader_registry import validate_options


class ImportOptionsDialog(ContentDialog):
    def __init__(self, path, parent=None, *, unsupported=False):
        super().__init__(parent)
        self.setWindowTitle('Import as Text' if unsupported else 'Review Import Options')
        self.setObjectName('sourceImportOptions')
        self.unsupported = unsupported
        layout = QtWidgets.QVBoxLayout(self)
        label = QtWidgets.QLabel(('No reader recognises this extension. Choose Import as Text only for a tabular text file. ' if unsupported else '')+str(path))
        label.setWordWrap(True)
        layout.addWidget(label)
        form = QtWidgets.QFormLayout()
        layout.addLayout(form)
        self.delimiter = QtWidgets.QLineEdit()
        self.delimiter.setPlaceholderText('Automatic; enter \\t for a tab')
        form.addRow('Column separator', self.delimiter)
        self.header = QtWidgets.QSpinBox()
        self.header.setRange(-1, 100000)
        self.header.setSpecialValueText('No header row')
        self.header.setValue(0)
        form.addRow('Header row (first row = 0)', self.header)
        self.decimal = QtWidgets.QComboBox()
        self.decimal.addItems(['.', ','])
        form.addRow('Decimal separator', self.decimal)
        self.encoding = QtWidgets.QLineEdit('utf-8-sig')
        form.addRow('Text encoding', self.encoding)
        self.time_column = QtWidgets.QLineEdit()
        self.time_column.setPlaceholderText('Automatic; enter the original column name')
        form.addRow('Time column', self.time_column)
        self.unit = QtWidgets.QComboBox()
        self.unit.addItems(['Automatic', 's', 'min', 'ms', 'h', 'sample'])
        form.addRow('Coordinate unit', self.unit)
        self.policy = QtWidgets.QComboBox()
        for title, value in [('Unknown / review later', 'unknown'), ('Sampled continuous waveform', 'sampled'),
                             ('Sampled held state', 'held_state'), ('Exact event log', 'event_log')]:
            self.policy.addItem(title, value)
        form.addRow('Acquisition policy', self.policy)
        self.domain = QtWidgets.QLineEdit()
        self.domain.setPlaceholderText('Optional documented shared clock domain')
        form.addRow('Clock domain', self.domain)
        self.error = QtWidgets.QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Open | QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Open).setText('Import as Text' if unsupported else 'Import')
        buttons.accepted.connect(self._validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def options(self):
        options = {'reader_id': 'tabular', 'header': self.header.value() if self.header.value() >= 0 else None,
                   'decimal': self.decimal.currentText(), 'encoding': self.encoding.text().strip(),
                   'acquisition_policy': self.policy.currentData()}
        delimiter = self.delimiter.text()
        if delimiter:
            options['delimiter'] = '\t' if delimiter == '\\t' else delimiter
        if self.time_column.text().strip():
            options['time_column'] = self.time_column.text().strip()
        if self.unit.currentText() != 'Automatic':
            options['unit'] = self.unit.currentText()
        if self.domain.text().strip():
            options['clock_domain'] = self.domain.text().strip()
        return validate_options(options)

    def _validate(self):
        try:
            self.options()
        except (ValueError, TypeError) as exc:
            self.error.setText(str(exc))
            return
        self.accept()

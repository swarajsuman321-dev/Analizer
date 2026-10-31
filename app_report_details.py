"""Optional, plain-language report notes shared by both report workflows.

The session metadata remains the single persistent source. Editing this dialog
does not calculate results, change engineering limits, or accept a test.
"""
from PySide6 import QtWidgets


REPORT_FIELDS = ('Report title', 'Prepared by', 'Reviewed by', 'Test conditions',
                 'Observations', 'Conclusions', 'Recommended actions')


class ReportDetailsDialog(QtWidgets.QDialog):
    def __init__(self, metadata, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Report Details & Conclusions')
        self.setObjectName('reportDetailsDialog')
        self.resize(680, 540)
        self.fields = {}
        layout = QtWidgets.QVBoxLayout(self)
        help_text = QtWidgets.QLabel(
            'Optional details for comparison and engineering reports. '
            'Notes are saved with your workspace. They do not change measured '
            'results, configured limits or Pass/Fail decisions.')
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        from app_report_appearance import show_cursor_guides
        self.cursor_guides = QtWidgets.QCheckBox('Include cursor lines and markers in exported plots')
        self.cursor_guides.setChecked(show_cursor_guides(metadata))
        self.cursor_guides.setToolTip('Cursor times and statistics are always retained. On-screen cursors stay unchanged.')
        layout.addWidget(self.cursor_guides)
        identity = QtWidgets.QFormLayout()
        layout.addLayout(identity)
        for name in REPORT_FIELDS[:3]:
            value = metadata.get(name, '')
            if name == 'Report title' and value == 'Engineering report':
                value = ''  # This is the old session's automatic title.
            field = QtWidgets.QLineEdit(value if isinstance(value, str) else '')
            field.setObjectName('report'+name.replace(' ', ''))
            field.setPlaceholderText('Use the report default' if name == 'Report title' else 'Not provided')
            identity.addRow(name, field)
            self.fields[name] = field
        tabs = QtWidgets.QTabWidget()
        layout.addWidget(tabs, 1)
        for name in REPORT_FIELDS[3:]:
            value = metadata.get(name, '')
            field = QtWidgets.QPlainTextEdit(value if isinstance(value, str) else '')
            field.setObjectName('report'+name.replace(' ', ''))
            field.setAccessibleName(name)
            field.setPlaceholderText('Optional user-provided '+name.lower())
            tabs.addTab(field, name)
            self.fields[name] = field
        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save |
            QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        return {'show_cursor_guides': self.cursor_guides.isChecked(), **{name: (field.text() if isinstance(field, QtWidgets.QLineEdit)
                       else field.toPlainText()).strip()
                for name, field in self.fields.items()}}


def update_report_details(metadata, values):
    """Apply an accepted edit, retaining unrelated legacy/custom metadata."""
    result = dict(metadata)
    if 'show_cursor_guides' in values:
        if not isinstance(values['show_cursor_guides'], bool):
            raise ValueError('Cursor guide preference must be a boolean')
        result['show_cursor_guides'] = values['show_cursor_guides']
    for name in REPORT_FIELDS:
        value = values.get(name, '')
        if not isinstance(value, str):
            raise ValueError(name+' must be text')
        if value.strip():
            result[name] = value.strip()
        else:
            result.pop(name, None)
    return result

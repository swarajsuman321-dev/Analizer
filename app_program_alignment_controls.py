"""Review a source-time program origin for each recording, with explicit evidence."""
from PySide6 import QtWidgets
from app_program_alignment import align_program_start, program_start, source_span,source_offset_minutes
from app_time_units import minute_factor


class ProgramAlignmentDialog(QtWidgets.QDialog):
    def __init__(self,window):
        super().__init__(window);self.window=window
        self.setWindowTitle('Align Program Starts');self.resize(620,300)
        layout=QtWidgets.QVBoxLayout(self)
        help=QtWidgets.QLabel('Set the actual program start for each run. That point becomes time zero for every channel in the recording; earlier samples stay visible at negative time. Use a recorded start signal or a reviewed observation. Recording start is never assumed.')
        help.setWordWrap(True);layout.addWidget(help)
        form=QtWidgets.QFormLayout();layout.addLayout(form)
        self.recording=QtWidgets.QComboBox()
        for dataset in window.store.datasets.values():
            try:source_span(window.store,dataset.id)
            except ValueError:continue
            self.recording.addItem(dataset.name,dataset.id)
        form.addRow('Recording',self.recording)
        self.point=QtWidgets.QDoubleSpinBox();self.point.setDecimals(9);self.point.setSuffix(' min')
        form.addRow('Program start in original source time',self.point)
        self.evidence=QtWidgets.QLineEdit();self.evidence.setPlaceholderText('For example: controller program-start transition reviewed')
        form.addRow('Evidence / confirmation',self.evidence)
        self.from_cursor=QtWidgets.QPushButton('Use Cursor A from this recording')
        self.from_cursor.clicked.connect(self.use_cursor);layout.addWidget(self.from_cursor)
        self.status=QtWidgets.QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        buttons=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Apply|QtWidgets.QDialogButtonBox.StandardButton.Close)
        self.apply_button=buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Apply)
        self.apply_button.clicked.connect(self.apply);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        self.recording.currentIndexChanged.connect(self.load);self.load()

    def load(self,*_):
        id=self.recording.currentData();self.apply_button.setEnabled(id is not None)
        if id is None:self.status.setText('Load a time-based recording first.');return
        low,high=source_span(self.window.store,id);self.point.setRange(low,high)
        try:record=program_start(self.window.store,id)
        except ValueError:
            self.point.setValue(low);self.evidence.clear();self.status.setText('Program start is not confirmed. The displayed value is only the source-span boundary; review it before applying.')
        else:
            self.point.setValue(record['source_min']);self.evidence.setText(record['evidence']);self.status.setText('Confirmed program start is saved with this recording.')

    def use_cursor(self):
        pane=self.window.active_workspace.active;id=self.recording.currentData()
        channel=next((self.window.store.channels[c] for c in pane.ids if self.window.store.channels[c].dataset_id==id and self.window.store.channels[c].coordinate_kind=='time'),None)
        if channel is None:self.status.setText('Activate a time graph containing this recording first.');return
        self.point.setValue((pane.cursor_lines[0].value()-channel.shift)*minute_factor(channel.coordinate_unit)-source_offset_minutes(self.window.store,channel))
        self.status.setText('Cursor A selected. Describe why this point establishes program start, then Apply.')

    def apply(self):
        try:
            self.window.mutate()
            align_program_start(self.window.store,self.recording.currentData(),self.point.value(),self.evidence.text())
        except ValueError as exc:self.status.setText(str(exc));return
        for workspace in self.window.workspaces:
            workspace.refresh()
            for pane in workspace.visible_panes():
                if pane.ids:pane.fit()
            workspace.link()
        self.window._readouts()
        self.status.setText('Aligned all time channels in this recording to program start. Save the workspace to retain the confirmed origin.')

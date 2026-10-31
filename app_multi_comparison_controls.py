"""Choose an explicit reference and any reviewed set of candidate signals."""
from PySide6 import QtCore,QtWidgets
from app_channel_identity import channel_label
from app_program_alignment import program_start
from app_signal_comparison_controls import SignalComparisonResults


class MultiComparisonDialog(QtWidgets.QDialog):
    def __init__(self,controls,selected=()):
        super().__init__(controls.window);self.controls=controls
        self.setWindowTitle('Compare Signals');self.resize(720,550)
        layout=QtWidgets.QVBoxLayout(self)
        label=QtWidgets.QLabel('Choose one reference and check the signals to compare against it. All runs use their confirmed program starts. Confirmed actuator channels also receive pairwise ON-overlap analysis. Different units remain explicitly unavailable for numerical differences.')
        label.setWordWrap(True);layout.addWidget(label)
        self.reference=QtWidgets.QComboBox();layout.addWidget(self.reference)
        self.candidates=QtWidgets.QListWidget();layout.addWidget(self.candidates,1)
        self.error=QtWidgets.QLabel();self.error.setWordWrap(True);layout.addWidget(self.error)
        buttons=QtWidgets.QHBoxLayout()
        align=QtWidgets.QPushButton('Align Program Starts…');align.clicked.connect(self.align);buttons.addWidget(align)
        self.compare_button=QtWidgets.QPushButton('Compare and Prepare Report');buttons.addWidget(self.compare_button)
        cancel=QtWidgets.QPushButton('Cancel');cancel.clicked.connect(self.reject);buttons.addWidget(cancel);layout.addLayout(buttons)
        self.initial=list(dict.fromkeys(selected))
        channels=[c for c in controls.window.store.channels.values() if c.coordinate_kind=='time' and c.dataset_id in controls.window.store.datasets]
        for c in channels:self.reference.addItem(channel_label(controls.window.store,c,include_source=True),c.id)
        if self.initial:self.reference.setCurrentIndex(max(0,self.reference.findData(self.initial[0])))
        self.reference.currentIndexChanged.connect(self.populate)
        self.candidates.itemChanged.connect(self.validate)
        self.compare_button.clicked.connect(self.compare)
        self.populate()

    def selected(self):
        return [self.candidates.item(i).data(QtCore.Qt.ItemDataRole.UserRole) for i in range(self.candidates.count())
            if self.candidates.item(i).checkState()==QtCore.Qt.CheckState.Checked]

    def populate(self,*_):
        selected=set(self.selected()) or set(self.initial)
        self.candidates.blockSignals(True);self.candidates.clear()
        for c in self.controls.window.store.channels.values():
            if c.id==self.reference.currentData() or c.coordinate_kind!='time' or c.dataset_id not in self.controls.window.store.datasets:continue
            item=QtWidgets.QListWidgetItem(channel_label(self.controls.window.store,c,include_source=True)+' ['+(c.unit or 'Unknown unit')+']')
            item.setData(QtCore.Qt.ItemDataRole.UserRole,c.id)
            item.setFlags(item.flags()|QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.CheckState.Checked if c.id in selected else QtCore.Qt.CheckState.Unchecked)
            self.candidates.addItem(item)
        self.candidates.blockSignals(False);self.validate()

    def validate(self,*_):
        try:
            selected=self.selected()
            if not selected:raise ValueError('Check at least one candidate signal.')
            if len(selected)>31:raise ValueError('Choose up to 31 candidates per report.')
            for id in [self.reference.currentData(),*selected]:
                channel=self.controls.window.store.channels.get(id)
                if channel is None:raise ValueError('Choose a reference signal.')
                program_start(self.controls.window.store,channel.dataset_id)
        except ValueError as exc:self.error.setText(str(exc));self.compare_button.setEnabled(False)
        else:self.error.setText('Differences are Candidate − Reference. Missing values and unsupported gaps remain unknown.');self.compare_button.setEnabled(True)

    def align(self):
        self.controls.window.align_programs();self.validate()

    def compare(self):
        try:self.controls.start_multi(self.reference.currentData(),self.selected())
        except ValueError as exc:self.error.setText(str(exc));return
        self.accept()


class MultiComparisonResults(QtWidgets.QDialog):
    def __init__(self,window,result,bundle):
        super().__init__(window);self.setWindowTitle('Signal Comparison Results');self.resize(850,550)
        from app_multi_comparison import summary_rows
        layout=QtWidgets.QVBoxLayout(self)
        message=QtWidgets.QLabel('All results use confirmed program time. Unavailable pairs keep their reasons; no acceptance limits are inferred.')
        message.setWordWrap(True);layout.addWidget(message)
        rows=summary_rows(result);columns=['Candidate','Status','Reason','RMSE','Unit','Compared min']
        self.results=QtWidgets.QTableWidget(len(rows),len(columns));self.results.setHorizontalHeaderLabels(columns)
        self.results.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        for r,row in enumerate(rows):
            for c,key in enumerate(columns):self.results.setItem(r,c,QtWidgets.QTableWidgetItem(str(row[key] if row[key] is not None else 'Not Available')))
        self.results.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.results)
        overlap=result['overlaps'];self.overlaps=QtWidgets.QTableWidget(len(overlap),4)
        self.overlaps.setHorizontalHeaderLabels(['First actuator','Second actuator','Common known s','Both ON s'])
        self.overlaps.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        for r,row in enumerate(overlap):
            for c,key in enumerate(('first','second','common_known_s','simultaneous_on_s')):self.overlaps.setItem(r,c,QtWidgets.QTableWidgetItem(str(row[key])))
        layout.addWidget(self.overlaps)
        note=QtWidgets.QLabel('Across separate runs, ON overlap describes timing similarity on program time, not physical simultaneous operation. Only confirmed actuator interpretations are included.')
        note.setWordWrap(True);layout.addWidget(note)
        buttons=QtWidgets.QHBoxLayout()
        for label,key in [('Open Report','pdf'),('Open Workbook','workbook'),('Open JSON Evidence','evidence')]:
            button=QtWidgets.QPushButton(label);button.clicked.connect(lambda checked=False,key=key:SignalComparisonResults.open_path(bundle[key]));buttons.addWidget(button)
        close=QtWidgets.QPushButton('Close');close.clicked.connect(self.accept);buttons.addWidget(close);layout.addLayout(buttons)

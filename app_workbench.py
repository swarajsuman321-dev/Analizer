"""Qt data workbench: shared state, commands, asynchronous processing, and views."""
import base64
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from PySide6 import QtCore,QtGui,QtWidgets
from app_channel_store import ChannelStore,Channel,Dataset
from app_channel_portal import ChannelPortal
from app_ingestion import ingest
from app_plot_workspace import PlotWorkspace,LAYOUTS
from app_signal_processing import formula,transform,UNIT_DEFINITIONS
from app_workspace_io import save_workspace,load_workspace,export_processed,render_report
from app_qt_style import ThemeController

OPERATIONS=['Moving average','Savitzky–Golay','Butterworth low-pass','Offset and scale','Time shift','Resampling',
            'Differentiation','Cumulative integration','Descriptive statistics','Histogram','FFT','Welch PSD','Peak and valley detection']


class WorkerSignals(QtCore.QObject):
    finished=QtCore.Signal(object,object)


class Worker(QtCore.QRunnable):
    def __init__(self,fn):
        super().__init__();self.fn=fn;self.signals=WorkerSignals()
    def run(self):
        try:self.signals.finished.emit(self.fn(),None)
        except Exception as exc:self.signals.finished.emit(None,str(exc))


class FrameModel(QtCore.QAbstractTableModel):
    def __init__(self,frame=None):
        super().__init__();self.frame=frame if frame is not None else pd.DataFrame()
    def rowCount(self,parent=QtCore.QModelIndex()):return 0 if parent.isValid() else len(self.frame)
    def columnCount(self,parent=QtCore.QModelIndex()):return 0 if parent.isValid() else len(self.frame.columns)
    def data(self,index,role=QtCore.Qt.ItemDataRole.DisplayRole):
        if role==QtCore.Qt.ItemDataRole.DisplayRole:return str(self.frame.iat[index.row(),index.column()])
        if role==QtCore.Qt.ItemDataRole.BackgroundRole and 'status' in self.frame:
            colors={'GREEN':'#c2e6ca','YELLOW':'#fff0ad','RED':'#f8c0c0','MISSING':'#e3e5e8','REVIEW':'#e3e5e8'}
            color=colors.get(self.frame.iloc[index.row()]['status'])
            if color:return QtGui.QColor(color)
        if role==QtCore.Qt.ItemDataRole.ForegroundRole and 'status' in self.frame:return QtGui.QColor('#182033')
    def headerData(self,section,orientation,role=QtCore.Qt.ItemDataRole.DisplayRole):
        if role!=QtCore.Qt.ItemDataRole.DisplayRole:return None
        return str(self.frame.columns[section]) if orientation==QtCore.Qt.Orientation.Horizontal else str(section+1)


class AdvancedStudioWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('Appliance Signal Studio · Data Workbench');self.setMinimumSize(1024,680)
        self.store=ChannelStore();self.generation=0;self.busy=False;self.preview=None;self.workers=set();self._reading=False
        self.pool=QtCore.QThreadPool.globalInstance();self.pool.setMaxThreadCount(2)
        self.theme=ThemeController(QtWidgets.QApplication.instance())
        self.tabs=QtWidgets.QTabWidget();self.setCentralWidget(self.tabs)
        self.dashboard=PlotWorkspace(self.store);self.comparison=PlotWorkspace(self.store);self.telemetry=PlotWorkspace(self.store)
        self.tabs.addTab(self.dashboard,'Engineering Dashboard');self.tabs.addTab(self.comparison,'Comparison');self.tabs.addTab(self.telemetry,'Telemetry')
        for workspace in self.workspaces:
            workspace.measurementsChanged.connect(self.readouts)
            workspace.activeChanged.connect(lambda _:self.readouts())
            workspace.setAcceptDrops(True);workspace.installEventFilter(self)
        self.tabs.currentChanged.connect(lambda _:self.readouts())
        self.docks={};self._build_portal();self._build_properties();self._build_readouts();self._build_math();self._build_table();self._build_engineering();self._build_toolbar()
        self.store.observe(self.store_changed)
        self.statusBar().showMessage('Open a recording or choose Preview sample. Source data is retained unchanged.')
        self.readout_timer=QtCore.QTimer(self);self.readout_timer.setSingleShot(True);self.readout_timer.timeout.connect(self._readouts)
        self.resizeDocks([self.docks['Data Portal'],self.docks['Properties']],[260,280],QtCore.Qt.Orientation.Horizontal)
        self.resizeDocks([self.docks['Readout']],[180],QtCore.Qt.Orientation.Vertical)
        self._readouts();self.theme.themeChanged.connect(self.plot_theme);self.theme.apply(self.theme.mode)

    def plot_theme(self,dark):
        color='#e3eaf5' if dark else '#182033';background='#151b26' if dark else '#ffffff'
        for workspace in self.workspaces:
            for pane in workspace.panes:
                pane.dark=dark;pane.setBackground(background)
                for name in ('bottom','left'):pane.getAxis(name).setTextPen(color)
                pane.cursor_lines[0].setPen(color)
        self.preview_plot.setBackground(background)

    @property
    def workspaces(self):return [self.dashboard,self.comparison,self.telemetry]
    @property
    def active_workspace(self):return self.workspaces[self.tabs.currentIndex()]

    def eventFilter(self,obj,event):
        if obj in self.workspaces:
            if event.type()==QtCore.QEvent.Type.DragEnter and event.mimeData().hasFormat('application/x-analizer-channels'):
                event.acceptProposedAction();return True
            if event.type()==QtCore.QEvent.Type.Drop:
                ids=bytes(event.mimeData().data('application/x-analizer-channels')).decode().splitlines()
                self.guard(lambda:obj.assign(ids));event.acceptProposedAction();return True
        return super().eventFilter(obj,event)

    def dock(self,name,widget,area):
        dock=QtWidgets.QDockWidget(name,self);dock.setObjectName(name);dock.setWidget(widget);self.addDockWidget(area,dock);self.docks[name]=dock
        if name in ('Properties','Channel Math','Engineering Controls'):
            scroll=QtWidgets.QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(widget);scroll.setMinimumWidth(220);dock.setWidget(scroll)
        return dock

    def _build_portal(self):
        self.portal=ChannelPortal(self.store);self.portal.plotRequested.connect(lambda ids:self.guard(lambda:self.active_workspace.assign(ids)))
        self.portal.selectionChanged.connect(self.selection);self.portal.organizeRequested.connect(self.organize)
        self.dock('Data Portal',self.portal,QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)

    def _build_properties(self):
        self.properties=QtWidgets.QWidget();form=QtWidgets.QFormLayout(self.properties);form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapAllRows)
        self.prop_name=QtWidgets.QLineEdit();self.prop_unit=QtWidgets.QLineEdit();self.prop_group=QtWidgets.QLineEdit()
        self.prop_kind=QtWidgets.QComboBox();self.prop_kind.addItems(['analog','discrete'])
        self.prop_attrs=QtWidgets.QPlainTextEdit();self.prop_attrs.setMaximumHeight(100)
        self.warning_min=QtWidgets.QLineEdit();self.warning_max=QtWidgets.QLineEdit();self.fault_min=QtWidgets.QLineEdit();self.fault_max=QtWidgets.QLineEdit()
        for label,widget in [('Name',self.prop_name),('Unit',self.prop_unit),('Group',self.prop_group),('Kind',self.prop_kind),('Custom properties (JSON)',self.prop_attrs),('Warning minimum',self.warning_min),('Warning maximum',self.warning_max),('Fault minimum',self.fault_min),('Fault maximum',self.fault_max)]:form.addRow(label,widget)
        button=QtWidgets.QPushButton('Apply properties and limits');button.clicked.connect(lambda:self.guard(self.apply_properties));form.addRow(button)
        self.dock('Properties',self.properties,QtCore.Qt.DockWidgetArea.RightDockWidgetArea)

    def _build_readouts(self):
        self.readout=QtWidgets.QTableWidget(0,5);self.readout.setHorizontalHeaderLabels(['Channel','Unit','Cursor A','Cursor B','Status'])
        self.intervals=QtWidgets.QTableWidget(0,11);self.intervals.setHorizontalHeaderLabels(['Channel','ΔX','ΔY','Mean','RMS','Min','Max','Peak-to-Peak','Slope','Integral','Coverage'])
        self.dock('Readout',self.readout,QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)
        self.dock('Interval Measurements',self.intervals,QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)
        self.tabifyDockWidget(self.docks['Readout'],self.docks['Interval Measurements']);self.docks['Readout'].raise_()

    def _build_math(self):
        widget=QtWidgets.QWidget();form=QtWidgets.QFormLayout(widget);form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapAllRows)
        self.expression=QtWidgets.QLineEdit('Ch("Power") * 0.001');self.formula_name=QtWidgets.QLineEdit('Formula')
        form.addRow('Formula',self.expression);form.addRow('Result name',self.formula_name)
        button=QtWidgets.QPushButton('Create formula channel');button.clicked.connect(lambda:self.guard(self.apply_formula));form.addRow(button)
        self.operation=QtWidgets.QComboBox();self.operation.addItems(OPERATIONS);form.addRow('Operation',self.operation)
        self.parameter_widget=QtWidgets.QWidget();self.parameter_form=QtWidgets.QFormLayout(self.parameter_widget);self.parameter_fields={}
        defaults={'window':11,'order':2,'cutoff':1,'scale':1,'offset':0,'shift':0,'step':1,'bins':30,'prominence':0}
        labels={'window':'Window (samples)','order':'Polynomial / filter order','cutoff':'Cutoff (Hz)','scale':'Scale','offset':'Offset','shift':'Shift (coordinate units)','step':'Resampling step','bins':'Histogram bins','prominence':'Peak prominence'}
        for key,value in defaults.items():
            spin=QtWidgets.QDoubleSpinBox();spin.setDecimals(6);spin.setRange(-1e9,1e9);spin.setValue(value)
            if key in ('window','order','bins'):spin.setDecimals(0);spin.setMinimum(1)
            if key in ('cutoff','step'):spin.setMinimum(.000001)
            self.parameter_fields[key]=spin;self.parameter_form.addRow(labels[key],spin)
        form.addRow(self.parameter_widget);self.operation.currentTextChanged.connect(self.show_parameters);self.show_parameters()

        self.parameter_help=QtWidgets.QLabel('window/order · cutoff (Hz) · scale/offset · shift/step (coordinate units) · bins · prominence');self.parameter_help.setWordWrap(True);form.addRow(self.parameter_help)
        row=QtWidgets.QHBoxLayout();preview=QtWidgets.QPushButton('Preview');self.apply_button=QtWidgets.QPushButton('Apply');self.apply_button.setEnabled(False)
        preview.clicked.connect(lambda:self.guard(self.preview_transform));self.apply_button.clicked.connect(lambda:self.guard(self.apply_preview));row.addWidget(preview);row.addWidget(self.apply_button);form.addRow(row)
        self.preview_plot=__import__('pyqtgraph').PlotWidget();self.preview_plot.setMinimumHeight(120);form.addRow(self.preview_plot)
        self.preview_message=QtWidgets.QLabel('Select one channel, preview an operation, then Apply.');self.preview_message.setWordWrap(True);form.addRow(self.preview_message)
        define=QtWidgets.QPushButton('Define local unit');define.clicked.connect(lambda:self.guard(self.define_unit));form.addRow(define)
        self.dock('Channel Math',widget,QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
        self.tabifyDockWidget(self.docks['Properties'],self.docks['Channel Math']);self.docks['Properties'].raise_()

    def _build_table(self):
        widget=QtWidgets.QWidget();layout=QtWidgets.QVBoxLayout(widget);self.source_selector=QtWidgets.QComboBox();layout.addWidget(self.source_selector)
        self.table=QtWidgets.QTableView();self.table.setAlternatingRowColors(True);layout.addWidget(self.table)
        self.table_model=FrameModel();self.table.setModel(self.table_model)
        self.source_selector.currentIndexChanged.connect(self.show_source)
        self.dock('Channel Table',widget,QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)
        self.tabifyDockWidget(self.docks['Readout'],self.docks['Channel Table']);self.docks['Readout'].raise_()

    def _build_engineering(self):
        widget=QtWidgets.QWidget();form=QtWidgets.QFormLayout(widget);form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapAllRows)
        self.power_path=QtWidgets.QLineEdit();self.machine_path=QtWidgets.QLineEdit();self.simulation_path=QtWidgets.QLineEdit()
        for label,field in [('Power recording',self.power_path),('Machine recording',self.machine_path),('Simulation CSV / ZIP',self.simulation_path)]:
            row=QtWidgets.QHBoxLayout();row.addWidget(field);button=QtWidgets.QPushButton('…');button.setMaximumWidth(32);row.addWidget(button)
            button.clicked.connect(lambda checked=False,f=field:self.pick_file(f));form.addRow(label,row)
        from app_data import BUILTIN_SYNC_STRATEGIES
        self.sync=QtWidgets.QComboBox();self.sync.addItems(BUILTIN_SYNC_STRATEGIES);form.addRow('Sync strategy',self.sync)
        self.offset=QtWidgets.QDoubleSpinBox();self.offset.setRange(-1e9,1e9);self.offset.setDecimals(3);form.addRow('Manual offset (s)',self.offset)
        button=QtWidgets.QPushButton('Align recordings');button.clicked.connect(lambda:self.guard(self.align));form.addRow(button)
        button=QtWidgets.QPushButton('Compare original recordings');button.clicked.connect(lambda:self.guard(self.compare));form.addRow(button)
        self.engineering_notes=QtWidgets.QPlainTextEdit();self.engineering_notes.setReadOnly(True);self.engineering_notes.setMaximumHeight(110);form.addRow(self.engineering_notes)
        self.scorecard=QtWidgets.QTableView();self.scorecard.setMinimumHeight(100);form.addRow(self.scorecard)
        button=QtWidgets.QPushButton('Open legacy calibration / plugins');button.clicked.connect(self.open_legacy);form.addRow(button)
        self.dock('Engineering Controls',widget,QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        self.tabifyDockWidget(self.docks['Data Portal'],self.docks['Engineering Controls']);self.docks['Data Portal'].raise_()

    def _build_toolbar(self):
        toolbar=self.addToolBar('Workbench');toolbar.setObjectName('Workbench');self.commands={}
        def action(text,fn,shortcut=None,tip=None):
            item=QtGui.QAction(text,self);item.triggered.connect(lambda:self.guard(fn));item.setToolTip(tip or text)
            if shortcut:item.setShortcut(shortcut)
            toolbar.addAction(item);self.commands[text]=item;return item
        action('Open',self.open_data,'Ctrl+O','Import CSV, Excel, ZIP, Parquet or JSON recording')
        action('Preview sample',self.demo)
        action('Save workspace',self.save,'Ctrl+S');action('Restore',self.restore)
        action('Export data',self.export_data);action('Presentation',self.report,'Ctrl+P')
        action('Math',lambda:self.docks['Channel Math'].raise_(),'Ctrl+M')
        action('Commands',self.command_palette,'Ctrl+K')
        self.layout_combo=QtWidgets.QComboBox();self.layout_combo.addItems(LAYOUTS);toolbar.addWidget(self.layout_combo)
        self.layout_combo.currentTextChanged.connect(lambda text:self.guard(lambda:self.active_workspace.set_layout(text)))
        self.cursor_combo=QtWidgets.QComboBox();self.cursor_combo.addItems(['dual','point','off']);toolbar.addWidget(self.cursor_combo)
        self.cursor_combo.currentTextChanged.connect(lambda mode:[p.set_cursor_mode(mode) for p in self.active_workspace.visible_panes()])
        snap=QtWidgets.QCheckBox('Snap');snap.setChecked(True);toolbar.addWidget(snap);snap.toggled.connect(lambda value:[setattr(p,'snap',value) for p in self.active_workspace.visible_panes()])
        view=self.menuBar().addMenu('View')
        for dock in self.docks.values():view.addAction(dock.toggleViewAction())
        channel=self.menuBar().addMenu('Channel')
        for text in ['Plot','Hide','Show all','Hide all','Rename','Duplicate','Delete','Move / group','Move to dataset','Merge groups','Move up','Move down','Assign axis','Mask interval','Clear masks','Marker','Threshold','ROI']:
            item=channel.addAction(text);item.triggered.connect(lambda checked=False,t=text:self.organize(t.lower()))
        theme=QtWidgets.QComboBox();theme.addItems(['System','Dark','Light']);toolbar.addWidget(theme);theme.currentTextChanged.connect(self.theme.apply)
        kind=view.addAction('Show channel kind');kind.setCheckable(True);kind.toggled.connect(lambda show:self.portal.tree.setColumnHidden(2,not show))

    def guard(self,fn):
        try:return fn()
        except Exception as exc:
            self.statusBar().showMessage(str(exc));QtWidgets.QMessageBox.warning(self,'Action could not complete',str(exc))

    def mutate(self):
        if self.busy:raise ValueError('Wait for the current operation before modifying channels')

    def background(self,fn,callback):
        self.mutate();self.busy=True;self.apply_button.setEnabled(False)
        generation=self.generation;store=self.store
        self.statusBar().showMessage('Working…');worker=Worker(fn);self.workers.add(worker)
        def complete(result,error):
            self.workers.discard(worker)
            if generation!=self.generation or store is not self.store:return
            self.busy=False
            if error:self.guard(lambda:(_ for _ in ()).throw(ValueError(error)))
            else:self.guard(lambda:callback(result))
            self.statusBar().showMessage('Ready' if not error else error)
        worker.signals.finished.connect(complete);self.pool.start(worker)

    def pick_file(self,field):
        path,_=QtWidgets.QFileDialog.getOpenFileName(self,'Choose recording')
        if path:field.setText(path)

    def open_data(self):
        self.mutate();paths,_=QtWidgets.QFileDialog.getOpenFileNames(self,'Open recordings','','Data (*.csv *.txt *.xlsx *.xls *.zip *.parquet *.json)')
        if not paths:return
        clock,ok=QtWidgets.QInputDialog.getText(self,'Coordinates','Time column (blank = detect or sample index):')
        if not ok:return
        unit,ok=QtWidgets.QInputDialog.getItem(self,'Coordinates','Numeric coordinate unit',['Auto','s','min','h','sample'],0,False)
        if not ok:return
        def load():
            store=ChannelStore()
            for path in paths:ingest(store,path,clock or None,None if unit=='Auto' else unit)
            return store
        self.background(load,self.merge_store)

    def merge_store(self,other):
        with self.store.batch():
            self.store.datasets.update(other.datasets)
            for c in other.channels.values():self.store.add(c)
        ids=list(other.channels)
        if ids:self.telemetry.assign(ids[:8]);self.tabs.setCurrentIndex(2)

    def store_changed(self,ids):
        self.portal.rebuild()
        for workspace in self.workspaces:workspace.refresh()
        current=self.source_selector.currentData();self.source_selector.blockSignals(True);self.source_selector.clear();self.source_selector.addItem('Selected channel projection',None)
        for ds in self.store.datasets.values():self.source_selector.addItem(ds.name,ds.id)
        if current:self.source_selector.setCurrentIndex(max(0,self.source_selector.findData(current)))
        self.source_selector.blockSignals(False);self.show_source();self.readouts()

    def selection(self,ids):
        self.preview=None;self.apply_button.setEnabled(False)
        if ids:
            c=self.store.channels[ids[0]];self.prop_name.setText(c.name);self.prop_unit.setText(c.unit);self.prop_group.setText(c.group);self.prop_kind.setCurrentText(c.kind)
            self.prop_attrs.setPlainText(json.dumps(c.attributes,indent=2))
            for key,field in [('warning_min',self.warning_min),('warning_max',self.warning_max),('fault_min',self.fault_min),('fault_max',self.fault_max)]:field.setText(str(c.attributes.get(key,'')))
        self.show_source()

    def apply_properties(self):
        self.mutate();ids=self.portal.selected()
        if len(ids)!=1:raise ValueError('Select one channel to edit properties')
        attrs=json.loads(self.prop_attrs.toPlainText() or '{}')
        if not isinstance(attrs,dict):raise ValueError('Properties must be a JSON object')
        for key,field in [('warning_min',self.warning_min),('warning_max',self.warning_max),('fault_min',self.fault_min),('fault_max',self.fault_max)]:
            if field.text():attrs[key]=float(field.text())
            else:attrs.pop(key,None)
        self.store.update(ids[0],name=self.prop_name.text(),unit=self.prop_unit.text(),group=self.prop_group.text(),kind=self.prop_kind.currentText(),attributes=attrs)

    def show_source(self,*args):
        ds=self.store.datasets.get(self.source_selector.currentData())
        if ds:frame=ds.frame
        elif self.portal.selected():
            c=self.store.channels[self.portal.selected()[0]];x,y=c.values();frame=pd.DataFrame({'coordinate':x,'value':y})
            if 'metric_labels' in c.attributes:frame['metric']=c.attributes['metric_labels'];frame['unit']=c.attributes['metric_units']
        else:frame=pd.DataFrame()
        self.table_model=FrameModel(frame);self.table.setModel(self.table_model)

    def organize(self,command):
        def perform():
            self.mutate();ids=self.portal.selected();workspace=self.active_workspace;pane=workspace.active
            if command in ('plot','show all'):
                workspace.assign(ids if command=='plot' else list(self.store.channels));return
            if command in ('hide','hide all'):
                for target in workspace.visible_panes():target.bind([] if command=='hide all' else [id for id in target.ids if id not in ids],target.bindings,fit=False)
                workspace.link();self.readouts();return
            if command=='organize':
                command2,ok=QtWidgets.QInputDialog.getItem(self,'Organize','Action',['Rename','Duplicate','Delete','Move / group','Move to dataset','Merge groups','Move up','Move down','Assign axis','Mask interval','Clear masks','Marker','Threshold','ROI'])
                if ok:self.organize(command2.lower())
                return
            if command in ('marker','threshold','roi'):
                a,b=[l.value() for l in pane.cursor_lines]
                text,ok=QtWidgets.QInputDialog.getText(self,'Annotation','Label:')
                if not ok:return
                if command=='threshold':
                    a,ok=QtWidgets.QInputDialog.getDouble(self,'Threshold','Y value:',0,-1e12,1e12,6)
                    if not ok:return
                axis=pane.bindings.get(ids[0]) if ids and ids[0] in pane.bindings else None
                pane.annotate({'marker':'Marker','threshold':'Threshold','roi':'ROI'}[command],a,b,text,axis);return
            if not ids:raise ValueError('Select channels in the Data Portal')
            if command=='delete':self.store.delete(ids)
            elif command=='duplicate':
                with self.store.batch():
                    for id in ids:self.store.duplicate(id)
            elif command=='move to dataset':
                datasets=list(self.store.datasets.values())
                if not datasets:raise ValueError('Import a dataset first')
                choice,ok=QtWidgets.QInputDialog.getItem(self,'Move channels','Destination dataset',[f'{ds.name} [{ds.id[:8]}]' for ds in datasets],0,False)
                if ok:
                    ds=datasets[[f'{ds.name} [{ds.id[:8]}]' for ds in datasets].index(choice)]
                    with self.store.batch():
                        for id in ids:self.store.update(id,dataset_id=ds.id)
            elif command in ('rename','move / group','merge groups','assign axis'):
                value,ok=QtWidgets.QInputDialog.getText(self,'Channel organization','Name / group / axis label:')
                if not ok or not value:return
                if command=='assign axis':
                    bindings=dict(pane.bindings);bindings.update({id:value for id in ids if id in pane.ids});pane.bind(pane.ids,bindings,fit=False)
                else:
                    target=list(ids)
                    if command=='merge groups':
                        keys={(self.store.channels[id].dataset_id,self.store.channels[id].group) for id in ids}
                        target=[id for id,c in self.store.channels.items() if (c.dataset_id,c.group) in keys]
                    with self.store.batch():
                        for id in target:self.store.update(id,**({'name':value} if command=='rename' else {'group':value}))
            elif command in ('mask interval','clear masks'):
                a,b=[l.value() for l in pane.cursor_lines]
                with self.store.batch():
                    for id in ids:
                        c=self.store.channels[id]
                        if command=='mask interval' and (c.coordinate_kind,c.coordinate_unit)!=pane.coordinate:raise ValueError('Select channels with the active viewport coordinate system')
                        self.store.update(id,masks=[] if command=='clear masks' else c.masks+[(a,b)])
            elif command in ('move up','move down'):
                keys=list(self.store.channels);direction=-1 if command=='move up' else 1
                for id in (ids if direction<0 else ids[::-1]):
                    i=keys.index(id);j=i+direction
                    if 0<=j<len(keys):keys[i],keys[j]=keys[j],keys[i]
                self.store.channels={id:self.store.channels[id] for id in keys};self.store.changed(*ids)
        self.guard(perform)

    def apply_formula(self):
        self.mutate();c=formula(self.store,self.expression.text(),self.formula_name.text());self.store.add(c);self.active_workspace.assign([c.id])

    def show_parameters(self,*args):
        relevant={'Moving average':['window'],'Savitzky–Golay':['window','order'],'Butterworth low-pass':['cutoff','order'],
                  'Offset and scale':['scale','offset'],'Time shift':['shift'],'Resampling':['step'],'Histogram':['bins'],
                  'Peak and valley detection':['prominence']}.get(self.operation.currentText(),[])
        for key,field in self.parameter_fields.items():
            field.setVisible(key in relevant);self.parameter_form.labelForField(field).setVisible(key in relevant)

    def preview_transform(self):
        ids=self.portal.selected()
        if len(ids)!=1:raise ValueError('Select one source channel')
        c=self.store.channels[ids[0]];operation=self.operation.currentText();params={key:field.value() for key,field in self.parameter_fields.items()}
        if not isinstance(params,dict):raise ValueError('Parameters must be a JSON object')
        self.preview=None
        def complete(result):
            if self.store.channels.get(c.id) is not c:return
            self.preview=(c.id,c.revision,result);self.apply_button.setEnabled(True);self.preview_plot.clear()
            self.preview_plot.setLabel('bottom',result.coordinate_kind,units=result.coordinate_unit);self.preview_plot.setLabel('left',result.unit)
            from app_fast_plot import EnvelopeCache
            if len(result.x):
                x,y=EnvelopeCache(result.x,result.y).visible(result.x[0],result.x[-1],2000);self.preview_plot.plot(x,y,pen='#58b6ff',connect='finite')
            self.preview_message.setText(f'{result.name}: {len(result.x):,} points. Apply creates a derived channel.')
        self.background(lambda:transform(c,operation,**params),complete)

    def apply_preview(self):
        self.mutate()
        if self.preview is None:raise ValueError('Preview an operation first')
        id,revision,c=self.preview
        if id not in self.store.channels or self.store.channels[id].revision!=revision:raise ValueError('Source changed; preview again')
        self.store.add(c);self.active_workspace.assign([c.id]);self.preview=None;self.apply_button.setEnabled(False)

    def define_unit(self):
        text,ok=QtWidgets.QInputDialog.getText(self,'Unit definition','symbol, existing reference unit, scale (for example mW,W,0.001)')
        if not ok:return
        symbol,reference,scale=[s.strip() for s in text.split(',')];dimension,factor=UNIT_DEFINITIONS[reference]
        scale=float(scale)
        if scale<=0:raise ValueError('Scale must be positive')
        UNIT_DEFINITIONS[symbol]=(dimension,factor*scale)

    def readouts(self):
        if hasattr(self,'readout_timer') and not self.readout_timer.isActive():self.readout_timer.start(16)

    def _readouts(self):
        if not self.active_workspace.active:return
        pane=self.active_workspace.active
        try:measurements=pane.measurements()
        except KeyError:return
        self.readout.setRowCount(len(measurements));self.intervals.setRowCount(len(measurements))
        def display(value):return f'{value:.6g}' if np.isfinite(value) else 'Unknown'
        for row,(id,stats) in enumerate(measurements.items()):
            c=self.store.channels[id];value=stats['A'];status='Unconfigured';attrs=c.attributes
            if not np.isfinite(value):status='Unknown'
            elif any(k in attrs for k in ('warning_min','warning_max','fault_min','fault_max')):
                status='Nominal'
                if value<attrs.get('warning_min',-np.inf) or value>attrs.get('warning_max',np.inf):status='Warning'
                if value<attrs.get('fault_min',-np.inf) or value>attrs.get('fault_max',np.inf):status='Fault'
            for col,text in enumerate([c.name,c.unit,display(stats['A']),display(stats['B']),status]):
                item=QtWidgets.QTableWidgetItem(text);item.setToolTip(f'{c.name}: {text}')
                if col==4 and status in ('Warning','Fault'):item.setForeground(QtGui.QColor('#ffb454' if status=='Warning' else '#ff8096'))
                self.readout.setItem(row,col,item)
            labels=['ΔX','ΔY','Mean','RMS','Min','Max','Peak-to-Peak','Slope','Integral','Coverage']
            measure_unit='s' if c.coordinate_kind=='time' else c.coordinate_unit
            units=[c.coordinate_unit,c.unit,c.unit,c.unit,c.unit,c.unit,c.unit,c.unit+'/'+measure_unit,c.unit+'·'+measure_unit,'fraction']
            self.intervals.setItem(row,0,QtWidgets.QTableWidgetItem(c.name))
            for col,(label,unit) in enumerate(zip(labels,units),1):self.intervals.setItem(row,col,QtWidgets.QTableWidgetItem(display(stats[label])+' '+unit))

    def demo(self):
        self.mutate();ds=Dataset('Illustrative sample',pd.DataFrame(),source='synthetic');self.store.datasets[ds.id]=ds
        x=np.linspace(0,600,10001)
        with self.store.batch():
            for i in range(6):self.store.add(Channel(f'Sample {i+1}',x,20+i*5+np.sin(x/(15+i*3))*5,unit='°C' if i<3 else 'W',dataset_id=ds.id,attributes={'illustrative':True}))
        self.telemetry.assign([id for id,c in self.store.channels.items() if c.dataset_id==ds.id]);self.tabs.setCurrentIndex(2)

    def align(self):
        power,machine,strategy,offset=self.power_path.text(),self.machine_path.text(),self.sync.currentText(),self.offset.value()
        if not power or not machine:raise ValueError('Choose power and machine recordings')
        def calculate():
            from app_data import DataEngine
            return DataEngine(power,machine,strategy,offset)
        def complete(engine):
            frame=engine.get_data();self.aligned_frame=frame;self.engineering_notes.setPlainText(json.dumps(engine.sync_report,default=str,indent=2))
            other=ChannelStore()
            for path in (power,machine):ingest(other,path)
            ds=Dataset('Aligned engineering data',frame.copy(),source=f'{power}; {machine}');other.datasets[ds.id]=ds
            coordinate=next((col for col in frame if str(col).lower() in ('time_min','relative_minutes')),None)
            x=frame[coordinate].to_numpy(float) if coordinate else np.arange(len(frame),dtype=float)
            for col in frame.select_dtypes(include='number'):
                if col==coordinate:continue
                from app_data import get_column_unit,classify_signal_kind
                other.add(Channel(str(col),x,frame[col].to_numpy(float),unit=get_column_unit(frame,col) or '',kind='discrete' if classify_signal_kind(col) in ('control','door_lock','state','code','stage') else 'analog',coordinate_unit='min' if coordinate else 'sample',coordinate_kind='time' if coordinate else 'sample',dataset_id=ds.id,group='Aligned'))
            self.merge_store(other);self.dashboard.assign([c.id for c in other.channels.values() if c.dataset_id==ds.id][:10]);self.tabs.setCurrentIndex(0)
        self.background(calculate,complete)

    def compare(self):
        machine,simulation=self.machine_path.text(),self.simulation_path.text()
        if not machine or not simulation:raise ValueError('Choose machine and simulation recordings')
        def calculate():
            from app_analysis_service import compare_recordings
            return compare_recordings(machine,simulation)
        def complete(result):
            other,score=result;self.scorecard.setModel(FrameModel(score));self.scorecard_data=score
            self.merge_store(other);self.comparison.assign(list(other.channels));self.tabs.setCurrentIndex(1)
        self.background(calculate,complete)

    def open_legacy(self):
        entry=Path(__file__).with_name('main.py')
        if getattr(sys,'frozen',False):subprocess.Popen([sys.executable,'--legacy'])
        else:subprocess.Popen([sys.executable,str(entry),'--legacy'],cwd=entry.parent)

    def ui_state(self):
        return {'geometry':bytes(self.saveGeometry().toBase64()).decode(),'docks':bytes(self.saveState().toBase64()).decode(),
                'tab':self.tabs.currentIndex(),'selection':self.portal.selected(),'source':self.source_selector.currentData(),
                'units':UNIT_DEFINITIONS,'engineering':{'power':self.power_path.text(),'machine':self.machine_path.text(),'simulation':self.simulation_path.text(),'strategy':self.sync.currentText(),'offset':self.offset.value()}}

    def save(self):
        self.mutate();path,_=QtWidgets.QFileDialog.getSaveFileName(self,'Save portable workspace','','Workspace (*.json)')
        if path:save_workspace(path,self.store,[w.state() for w in self.workspaces],self.ui_state());self.statusBar().showMessage('Saved JSON and adjacent NPZ; keep both files together.')

    def restore(self):
        path,_=QtWidgets.QFileDialog.getOpenFileName(self,'Restore workspace','','Workspace (*.json)')
        if path:self.restore_path(path)

    def restore_path(self,path):
        store,views,ui=load_workspace(path)
        self.generation+=1;self.busy=False;self.preview=None;self.apply_button.setEnabled(False);self.store=store;self.portal.store=store
        for workspace,state in zip(self.workspaces,views):workspace.store=store;workspace.restore(state)
        self.store.observe(self.store_changed);self.store_changed(set())
        for encoded,method in [(ui.get('geometry'),self.restoreGeometry),(ui.get('docks'),self.restoreState)]:
            if encoded:method(QtCore.QByteArray.fromBase64(encoded.encode()))
        self.tabs.setCurrentIndex(ui.get('tab',0));self.source_selector.setCurrentIndex(max(0,self.source_selector.findData(ui.get('source'))))
        selected=set(ui.get('selection',[]))
        iterator=QtWidgets.QTreeWidgetItemIterator(self.portal.tree)
        while iterator.value():
            item=iterator.value();item.setSelected(item.data(0,QtCore.Qt.ItemDataRole.UserRole) in selected);iterator+=1
        UNIT_DEFINITIONS.update(ui.get('units',{}))
        engineering=ui.get('engineering',{})
        for key,field in [('power',self.power_path),('machine',self.machine_path),('simulation',self.simulation_path)]:field.setText(engineering.get(key,''))
        self.sync.setCurrentText(engineering.get('strategy',self.sync.currentText()));self.offset.setValue(engineering.get('offset',0));self.readouts()

    def export_data(self):
        ids=self.portal.selected()
        if not ids:raise ValueError('Select channels to export')
        path,_=QtWidgets.QFileDialog.getSaveFileName(self,'Export processed channels','','CSV (*.csv);;Excel (*.xlsx)')
        if path:export_processed(path,[self.store.channels[id] for id in ids])

    def report(self):
        path,_=QtWidgets.QFileDialog.getSaveFileName(self,'Presentation export','','PNG (*.png);;SVG (*.svg);;PDF (*.pdf);;HTML (*.html);;Markdown (*.md)')
        if path:render_report(path,self.store,self.active_workspace.state())

    def command_palette(self):
        command,ok=QtWidgets.QInputDialog.getItem(self,'Command palette','Command',list(self.commands),0,False)
        if ok:self.commands[command].trigger()

    def closeEvent(self,event):
        self.generation+=1
        if self.busy:
            self.statusBar().showMessage('Waiting for current processing to finish…');self.pool.waitForDone()
        event.accept()


def run_workbench():
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion');window=AdvancedStudioWindow();window.showMaximized()
    return app.exec()

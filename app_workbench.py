"""Qt data workbench: shared state, commands, asynchronous processing, and views."""
import json
import sys
import threading
from copy import deepcopy
from pathlib import Path
import numpy as np
import pandas as pd
from PySide6 import QtCore,QtGui,QtWidgets
from app_channel_store import ChannelStore,Channel,Dataset
from app_channel_portal import ChannelPortal
from app_ingestion import ingest
from app_plot_workspace import PlotWorkspace,LAYOUTS,PRESET_LAYOUTS
from app_signal_processing import formula,transform,UNIT_DEFINITIONS
from app_workspace_io import save_workspace,load_workspace
from app_qt_style import ThemeController
from app_presentation import CURSOR_COLORS,match_color
from app_version import VERSION
from app_output import output_directory,output_path

OPERATIONS=['Moving average','Savitzky–Golay','Butterworth low-pass','Offset and scale','Time shift','Resampling',
            'Differentiation','Cumulative integration','Descriptive statistics','Histogram','FFT','Welch PSD','Peak and valley detection']


class WorkerSignals(QtCore.QObject):
    finished=QtCore.Signal(object,object)
    progress=QtCore.Signal(str,int)


class Worker(QtCore.QRunnable):
    def __init__(self,fn):
        super().__init__();self.fn=fn;self.signals=WorkerSignals();self.cancel=threading.Event();self.output_committed=False
    def run(self):
        from app_operation_context import operation_context,checkpoint
        try:
            with operation_context(self.cancel,self.signals.progress.emit) as context:
                checkpoint();result=self.fn()
                self.output_committed=context['committed']
            self.signals.finished.emit(result,None)
        except Exception as exc:self.signals.finished.emit(None,exc)


class FrameModel(QtCore.QAbstractTableModel):
    def __init__(self,frame=None):
        super().__init__();self.frame=frame if frame is not None else pd.DataFrame()
    def rowCount(self,parent=QtCore.QModelIndex()):return 0 if parent.isValid() else len(self.frame)
    def columnCount(self,parent=QtCore.QModelIndex()):return 0 if parent.isValid() else len(self.frame.columns)
    def data(self,index,role=QtCore.Qt.ItemDataRole.DisplayRole):
        if role==QtCore.Qt.ItemDataRole.DisplayRole:
            value=self.frame.iat[index.row(),index.column()]
            if 'accent' in self.frame and self.frame.columns[index.column()]=='percent':return f'{value:+.4g}%' if pd.notna(value) else '—'
            if self.frame.columns[index.column()]=='match_percent':return f'{value:.1f}%' if pd.notna(value) else '—'
            return str(value)
        if role==QtCore.Qt.ItemDataRole.BackgroundRole and 'accent' in self.frame and self.frame.columns[index.column()] in ('delta','percent'):
            color=self.frame.iloc[index.row()]['accent']
            if isinstance(color,str) and color.startswith('#'):return QtGui.QColor(color)
        if role==QtCore.Qt.ItemDataRole.BackgroundRole and 'match_percent' in self.frame:
            color=match_color(self.frame.iloc[index.row()]['match_percent'])
            if color:return QtGui.QColor(color)
        if role==QtCore.Qt.ItemDataRole.ForegroundRole and 'match_percent' in self.frame:return QtGui.QColor('#101828')
    def headerData(self,section,orientation,role=QtCore.Qt.ItemDataRole.DisplayRole):
        if role!=QtCore.Qt.ItemDataRole.DisplayRole:return None
        return str(self.frame.columns[section]).replace('_',' ').title() if orientation==QtCore.Qt.Orientation.Horizontal else str(section+1)


class AdvancedStudioWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__();self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose);self.setWindowTitle(f'Appliance Signal Studio · {VERSION}');self.setMinimumSize(1024,680)
        from app_identity import apply_identity
        apply_identity(self)
        self.store=ChannelStore();self.generation=0;self.busy=False;self.workers=set();self.removal_undo=None
        self.output_root=output_directory()
        self.pool=QtCore.QThreadPool.globalInstance();self.pool.setMaxThreadCount(2)
        self.theme=ThemeController(QtWidgets.QApplication.instance(),self)
        self.tabs=QtWidgets.QTabWidget();self.setCentralWidget(self.tabs)
        self.dashboard=PlotWorkspace(self.store);self.comparison=PlotWorkspace(self.store)
        self.tabs.addTab(self.dashboard,'Analysis');self.tabs.addTab(self.comparison,'Comparison')
        for workspace in self.workspaces:
            workspace.measurementsChanged.connect(self.readouts)
            workspace.activeChanged.connect(self.workspace_changed)
            workspace.setAcceptDrops(True);workspace.installEventFilter(self)
        self.tabs.currentChanged.connect(self.workspace_changed)
        self.docks={};self._build_portal();self._build_properties();self._build_readouts();self._build_math();self._build_table();self._build_engineering();self._build_toolbar();self._build_operation_status()
        from app_studio_tools import StudioTools
        self.studio=StudioTools(self)
        from app_compact_controls import CompactControls
        self.compact=CompactControls(self)
        from app_engineering_ui import EngineeringTools
        self.engineering=EngineeringTools(self)
        self.about_menu=self.menuBar().addMenu('About')
        self.about_menu.addAction(self.help_action);self.about_menu.addAction(self.info_action)
        from app_adaptive_ui import ContentDialog
        from app_info import InfoTab
        self.info_dialog=ContentDialog(self);self.info_dialog.setWindowTitle(f'About Appliance Signal Studio · {VERSION}');self.info_dialog.setModal(True);self.info_dialog.resize(1050,760)
        info_layout=QtWidgets.QVBoxLayout(self.info_dialog);self.info=InfoTab(self);info_layout.addWidget(self.info)
        self.help_dialog=ContentDialog(self);self.help_dialog.setWindowTitle('User Manual');self.help_dialog.resize(1050,760)
        help_layout=QtWidgets.QVBoxLayout(self.help_dialog);self.help=self.info.help;help_layout.addWidget(self.help)
        self.store.observe(self.store_changed)
        self.statusBar().showMessage('Open a recording to begin. Check channels to show them; drag A and B to inspect an interval.')
        self.readout_timer=QtCore.QTimer(self);self.readout_timer.setSingleShot(True);self.readout_timer.timeout.connect(self._readouts)
        from app_adaptive_ui import DialogBounds
        self.dialog_bounds=DialogBounds(self);QtWidgets.QApplication.instance().installEventFilter(self.dialog_bounds)
        self.resizeDocks([self.docks['Data Portal'],self.docks['Properties']],[260,280],QtCore.Qt.Orientation.Horizontal)
        self.resizeDocks([self.docks['Readout']],[180],QtCore.Qt.Orientation.Vertical)
        self.enable_all_panels()
        self._readouts();self.theme.themeChanged.connect(self.plot_theme);self.theme.apply(self.theme.mode)
        self._build_quick_analysis_controls()

    def _build_quick_analysis_controls(self):
        """Expose common graph tasks without changing the advanced tools."""
        from app_trace_controls import TraceColorControls
        from app_data_comparison import DataComparisonControls
        from app_graph_fullscreen import GraphFullscreenController
        from app_workspace_fullscreen import WorkspaceFullscreenController
        from app_panel_folding import PanelFoldingControls
        self.trace_colors=TraceColorControls(self)
        self.data_comparison=DataComparisonControls(self)
        self.graph_fullscreen=GraphFullscreenController(self)
        self.graph_fullscreen.action.setShortcut('Shift+F11')
        self.graph_fullscreen.action.setToolTip('Expand only the selected graph. Shift+F11 or Esc returns.')
        self.graph_fullscreen.exit_action.setToolTip('Return this graph to its original position (Esc or Shift+F11).')
        self.workspace_fullscreen=WorkspaceFullscreenController(self)
        self.panel_folding=PanelFoldingControls(self)
        color=self.channel_menu.addAction('Change Trace Color…')
        color.setToolTip('Choose a color for the selected channel without resetting the graph')
        color.triggered.connect(lambda:self.guard(self.trace_colors.choose))
        self.trace_color_action=color
        button=QtWidgets.QPushButton('Change Trace Color…',self.properties)
        button.clicked.connect(lambda:self.guard(self.trace_colors.choose))
        self.properties.layout().insertRow(0,button)
        self.portal.traceColorRequested.connect(lambda ids:self.guard(lambda:self.trace_colors.choose(ids)))
        self.portal.comparisonRequested.connect(lambda ids:self.guard(lambda:self.data_comparison.add_channels(ids)))
        self.view_menu.addSeparator();self.view_menu.addAction(self.workspace_fullscreen.action);self.view_menu.addAction(self.graph_fullscreen.action)
        self.report_details_action=QtGui.QAction('Report Details & Conclusions…',self)
        self.report_details_action.setToolTip('Optional title, authors, test conditions, observations, conclusions and actions for both report workflows')
        self.report_details_action.triggered.connect(lambda:self.guard(self.edit_report_details))
        self.studio.submenus['Export'].addAction(self.report_details_action)
        self.studio.submenus['Engineering'].addAction(self.report_details_action)
        from app_signal_comparison_controls import SignalComparisonControls
        self.signal_comparison=SignalComparisonControls(self)
        self.main_toolbar.insertAction(self.compare_data_action,self.signal_comparison.action)
        self.studio.submenus['Engineering'].addAction(self.signal_comparison.action)
        before=next((action for action in self.main_toolbar.actions() if action.text()=='Calculate Channel'),None)
        self.main_toolbar.insertWidget(before,self.panel_folding.button)
        def fullscreen_icon(dark=None):
            from app_adaptive_ui import navigation_icon
            if dark is None:dark=self.palette().color(QtGui.QPalette.ColorRole.Window).lightness()<128
            self.graph_fullscreen.action.setIcon(navigation_icon('fullscreen',dark))
            self.workspace_fullscreen.action.setIcon(navigation_icon('fullscreen',dark))
        fullscreen_icon();self.theme.themeChanged.connect(fullscreen_icon)
        self.fullscreen_menus=[]
        for workspace in self.workspaces:
            bar=workspace.navigation_bar
            # Keep the compact expansion control with the zoom icons, before
            # longer lock/setup labels. Native Windows fonts need more width
            # than offscreen Linux, and common graph actions should stay in
            # view while the existing toolbar handles narrow-window overflow.
            bar.insertAction(workspace.time_lock_action,self.workspace_fullscreen.action)
            button=bar.widgetForAction(self.workspace_fullscreen.action)
            button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setAccessibleName('Fullscreen Workspace')
            menu=QtWidgets.QMenu(button);menu.addAction(self.workspace_fullscreen.action);menu.addAction(self.graph_fullscreen.action)
            button.setMenu(menu);button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup)
            self.fullscreen_menus.append(menu)
        self.panel_folding.apply_defaults(['Properties','Channel Math','Channel Table','Interval Measurements','Engineering Controls'])
        self.docks['Data Portal'].raise_()
        self.tabs.setTabToolTip(0,'Analysis: plot and inspect selected channels using their preserved source timing.')
        self.tabs.setTabToolTip(1,'Comparison: overlay runs on confirmed program time; use Compare Signals for numerical differences and actuator overlap.')

    def exit_graph_fullscreen(self):
        if hasattr(self,'workspace_fullscreen'):self.workspace_fullscreen.exit()
        if hasattr(self,'graph_fullscreen'):self.graph_fullscreen.exit()

    def report_metadata(self,engineering=False):
        """Capture user notes independently of live widgets for export workers."""
        metadata=deepcopy(self.engineering.session.get('metadata',{}))
        if not engineering and metadata.get('Report title')=='Engineering report':
            metadata.pop('Report title')
        return metadata

    def edit_report_details(self):
        self.mutate()
        from app_report_details import ReportDetailsDialog,update_report_details
        parent=self
        for name in ('workspace_fullscreen','graph_fullscreen'):
            controller=getattr(self,name,None)
            if controller is not None and controller.is_active:parent=controller.fullscreen_window
        dialog=ReportDetailsDialog(self.engineering.session.get('metadata',{}),parent)
        if dialog.exec()!=QtWidgets.QDialog.DialogCode.Accepted:return False
        self.engineering.session['metadata']=update_report_details(self.engineering.session.get('metadata',{}),dialog.values())
        self.statusBar().showMessage('Report details updated. Save the workspace to retain them for later sessions.')
        return True

    def plot_theme(self,dark):
        color='#e3eaf5' if dark else '#182033';background='#151b26' if dark else '#ffffff'
        for workspace in self.workspaces:
            for pane in workspace.panes:
                pane.dark=dark;pane.setBackground(background)
                pane.getAxis('bottom').setTextPen(color)
                pane.bind(pane.ids,pane.bindings,fit=False)

    @property
    def workspaces(self):return [self.dashboard,self.comparison]
    @property
    def active_workspace(self):return self.workspaces[getattr(self,'_plot_tab_index',0)]

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
        self.portal.visibilityRequested.connect(lambda ids,visible:self.guard(lambda:self.set_channel_visibility(ids,visible)))
        self.portal.selectionChanged.connect(self.selection);self.portal.organizeRequested.connect(self.organize)
        self.portal.removeRequested.connect(lambda:self.guard(self.remove_recording));self.portal.clearRequested.connect(lambda:self.guard(self.clear_recordings))
        self.portal.datasetRemovalRequested.connect(lambda id:self.guard(lambda:self.request_drop_recordings([id])))
        self.dock('Data Portal',self.portal,QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)

    def _build_properties(self):
        self.properties=QtWidgets.QWidget();form=QtWidgets.QFormLayout(self.properties);form.setRowWrapPolicy(QtWidgets.QFormLayout.RowWrapPolicy.WrapAllRows)
        self.prop_name=QtWidgets.QLineEdit();self.prop_unit=QtWidgets.QLineEdit();self.prop_group=QtWidgets.QLineEdit()
        self.prop_kind=QtWidgets.QComboBox();self.prop_kind.addItems(['analog','discrete'])
        self.prop_interpretation=QtWidgets.QComboBox();self.prop_interpretation.addItem('Auto (identify actuator commands)','auto');self.prop_interpretation.addItem('Numeric / original readings','numeric');self.prop_interpretation.addItem('Actuator ON / OFF','actuator')
        self.prop_attrs=QtWidgets.QPlainTextEdit();self.prop_attrs.setMaximumHeight(100)
        self.warning_min=QtWidgets.QLineEdit();self.warning_max=QtWidgets.QLineEdit();self.fault_min=QtWidgets.QLineEdit();self.fault_max=QtWidgets.QLineEdit()
        for label,widget in [('Name',self.prop_name),('Unit',self.prop_unit),('Group',self.prop_group),('Kind',self.prop_kind),('Value interpretation',self.prop_interpretation),('Warning minimum',self.warning_min),('Warning maximum',self.warning_max),('Fault minimum',self.fault_min),('Fault maximum',self.fault_max)]:form.addRow(label,widget)
        self.prop_metadata=QtWidgets.QTableWidget(0,2);self.prop_metadata.setHorizontalHeaderLabels(['Property','Value (JSON value or text)']);self.prop_metadata.setMaximumHeight(140)
        self.prop_metadata.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        form.addRow('Custom properties',self.prop_metadata)
        metadata_row=QtWidgets.QHBoxLayout();add_property=QtWidgets.QPushButton('Add property');remove_property=QtWidgets.QPushButton('Remove property');metadata_row.addWidget(add_property);metadata_row.addWidget(remove_property);form.addRow(metadata_row)
        add_property.clicked.connect(lambda:self.prop_metadata.insertRow(self.prop_metadata.rowCount()))
        remove_property.clicked.connect(lambda:self.prop_metadata.removeRow(self.prop_metadata.currentRow()) if self.prop_metadata.currentRow()>=0 else None)
        self.metadata_advanced=QtWidgets.QToolButton();self.metadata_advanced.setText('Advanced JSON editor');self.metadata_advanced.setCheckable(True);self.metadata_advanced.setToolTip('Edit the complete metadata object. Structured editing remains available when collapsed.')
        self.prop_attrs.hide();form.addRow(self.metadata_advanced);form.addRow(self.prop_attrs)
        self.metadata_advanced.toggled.connect(self.toggle_metadata_editor)
        button=QtWidgets.QPushButton('Apply properties and limits');button.clicked.connect(lambda:self.guard(self.apply_properties));form.addRow(button)
        self.dock('Properties',self.properties,QtCore.Qt.DockWidgetArea.RightDockWidgetArea)

    def _build_readouts(self):
        widget=QtWidgets.QWidget();layout=QtWidgets.QVBoxLayout(widget)
        self.cursor_caption=QtWidgets.QLabel();top=QtWidgets.QHBoxLayout();layout.addLayout(top);top.addWidget(self.cursor_caption,1)
        self.stats_scope=QtWidgets.QComboBox();self.stats_scope.addItems(['Cursor interval','Whole recording']);self.stats_scope.setToolTip('Scope for Min, Max and Average; A, B and Δ value always follow the cursors');top.addWidget(self.stats_scope);self.stats_scope.currentIndexChanged.connect(self.readouts)
        body=QtWidgets.QHBoxLayout();layout.addLayout(body)
        self.readout=QtWidgets.QTableWidget(0,9);self.readout.setHorizontalHeaderLabels(['Channel','Unit','A','B','Match','Δ value','Min','Max','Average'])
        header=self.readout.horizontalHeader();header.setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch);header.setMinimumSectionSize(65)
        header.setSectionResizeMode(0,QtWidgets.QHeaderView.ResizeMode.Interactive);self.readout.setColumnWidth(0,260)
        header.setSectionResizeMode(1,QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.readout.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.readout.verticalHeader().hide();self.readout.verticalHeader().setDefaultSectionSize(26)
        self.readout.setMinimumHeight(110)
        body.addWidget(self.readout,1)
        from app_readout_details import ReadoutDetailsLabel
        self.interval_card=ReadoutDetailsLabel('Select a plotted channel to inspect its interval.')
        self.interval_card.setStyleSheet('padding:10px; border:1px solid #8293a9; border-radius:6px;');self.interval_card.setMinimumHeight(110);self.interval_card.setMaximumWidth(340)
        self.interval_scroll=QtWidgets.QScrollArea();self.interval_scroll.setWidgetResizable(True);self.interval_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.interval_scroll.setMinimumWidth(210);self.interval_scroll.setMaximumWidth(340);self.interval_scroll.setMinimumHeight(110)
        self.interval_scroll.setAccessibleName('Complete interval details');self.interval_scroll.setToolTip('Scroll to read longer interval details')
        self.interval_scroll.setWidget(self.interval_card);body.addWidget(self.interval_scroll)
        self.readout.itemSelectionChanged.connect(self.update_interval_card)
        self.intervals=QtWidgets.QTableWidget(0,11);self.intervals.setHorizontalHeaderLabels(['Channel','ΔX','ΔY','Mean','RMS','Min','Max','Peak-to-Peak','Slope','Integral','Coverage'])
        self.intervals.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.dock('Readout',widget,QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)
        self.dock('Interval Measurements',self.intervals,QtCore.Qt.DockWidgetArea.BottomDockWidgetArea)
        self.tabifyDockWidget(self.docks['Readout'],self.docks['Interval Measurements'])

    def update_interval_card(self):
        import html
        pane=self.active_workspace.active
        measurements=self.active_workspace.measurement_rows()
        keys=list(measurements);row=self.readout.currentRow()
        if not keys:
            self.interval_card.setText('No channels selected');self.interval_card.setToolTip('');return
        channel_id=keys[row if 0<=row<len(keys) else 0];pane,measurement=measurements[channel_id]
        c=self.store.channels[channel_id];stats=self.statistics_for_display(pane,channel_id,measurement)
        def number(key):return f"{abs(stats[key]) if key in ('ΔX','ΔY') else stats[key]:.5g}" if np.isfinite(stats[key]) else '—'
        anchors=self.locked_cursor_texts(pane)
        from app_channel_identity import channel_label,channel_details
        title=self.interval_card.fontMetrics().elidedText(channel_label(self.store,c),QtCore.Qt.TextElideMode.ElideMiddle,max(80,self.interval_card.width()-24))
        name=html.escape(title);unit=html.escape(c.unit or 'Unknown unit')
        details=[channel_details(self.store,c)]
        for cursor,lock in enumerate(pane.cursor_locks):
            if lock and lock['channel'] in self.store.channels:
                details.append(('A','B')[cursor]+' locked sample '+str(lock['index'])+'\n'+channel_details(self.store,lock['channel']))
        self.interval_card.setToolTip('\n\n'.join(details))
        summary=f"<b>{name}</b> · {self.stats_scope.currentText()}<br>ΔX {number('ΔX')} {html.escape(c.coordinate_unit)} &nbsp; |ΔY| {number('ΔY')} {unit}<br>Min {number('Min')} &nbsp; Max {number('Max')} &nbsp; Mean {number('Mean')} {unit}"
        if not c.attributes.get('actuator_binary'):
            summary+=f"<br>Interval RMS {number('RMS')} · Slope {number('Slope')} {unit}/{html.escape(c.coordinate_unit)}<br>Integral {number('Integral')} {unit}·{html.escape(c.coordinate_unit)} · Coverage {stats['Coverage']:.1%}"
            if c.unit in ('W','kW') and c.coordinate_kind=='time':
                factor={'s':1/3600,'min':1/60,'h':1}.get(c.coordinate_unit)
                if factor is not None:summary+=f"<br>Interval energy {stats['Integral']*factor*(1000 if c.unit=='kW' else 1):.5g} Wh"
        if c.attributes.get('actuator_binary'):
            from app_actuators import state_text
            a,b=[line.value() for line in pane.cursor_lines]
            if self.stats_scope.currentIndex()==1 and len(c.x):a,b=float(c.x[0]+c.shift),float(c.x[-1]+c.shift)
            binary=pane.summaries[c.id][1].query(a,b);known=binary['Coverage']*binary['ΔX'];on=binary['Mean']*known
            duty=f"{100*binary['Mean']:.4g}%" if np.isfinite(binary['Mean']) else 'Unknown'
            duration=f'{on:.5g}' if np.isfinite(on) else 'Unknown'
            summary=f"<b>{name}</b> · {self.stats_scope.currentText()}<br>A {state_text(stats['A'])} &nbsp; B {state_text(stats['B'])}<br>{'ON time' if c.coordinate_kind=='time' else 'ON span'} {duration} {html.escape(c.coordinate_unit)} · Duty {duty}<br>Known time {known:.5g} {html.escape(c.coordinate_unit)}"
        self.interval_card.setText(('<br>'.join(anchors)+'<br><br>' if anchors else '')+summary)

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

        self.parameter_help=QtWidgets.QLabel();self.parameter_help.setWordWrap(True);form.addRow(self.parameter_help)
        self.apply_button=QtWidgets.QPushButton('Apply to workspace');self.apply_button.clicked.connect(lambda:self.guard(self.apply_transform));form.addRow(self.apply_button)
        self.parameter_fields['cutoff'].valueChanged.connect(self.update_processing_preflight)
        self.update_processing_preflight()
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
        for label,field in [('Power recording',self.power_path),('Machine recording',self.machine_path),('Simulation CSV / ZIP / Image',self.simulation_path)]:
            row=QtWidgets.QHBoxLayout();row.addWidget(field);button=QtWidgets.QPushButton('Choose File…');row.addWidget(button)
            button.clicked.connect(lambda checked=False,f=field:self.pick_file(f));form.addRow(label,row)
        from app_data import BUILTIN_SYNC_STRATEGIES
        self.sync=QtWidgets.QComboBox();self.sync.addItems(BUILTIN_SYNC_STRATEGIES);form.addRow('Recording Alignment Method',self.sync)
        self.offset=QtWidgets.QDoubleSpinBox();self.offset.setRange(-1e9,1e9);self.offset.setDecimals(3);self.offset.setSuffix(' s');form.addRow('Manual offset (seconds)',self.offset)
        button=QtWidgets.QPushButton('Align recordings');button.clicked.connect(lambda:self.guard(self.align));form.addRow(button)
        button=QtWidgets.QPushButton('Compare original recordings');button.clicked.connect(lambda:self.guard(self.compare));form.addRow(button)
        self.engineering_notes=QtWidgets.QPlainTextEdit();self.engineering_notes.setReadOnly(True);self.engineering_notes.setMaximumHeight(110);form.addRow(self.engineering_notes)
        self.scorecard=QtWidgets.QTableView();self.scorecard.setMinimumHeight(100);form.addRow(self.scorecard)
        self.dock('Engineering Controls',widget,QtCore.Qt.DockWidgetArea.LeftDockWidgetArea)
        self.tabifyDockWidget(self.docks['Data Portal'],self.docks['Engineering Controls'])

    def _build_toolbar(self):
        toolbar=self.addToolBar('Workbench');toolbar.setObjectName('Workbench');toolbar.setMovable(False)
        self.main_toolbar=toolbar
        def action(text,fn,shortcut=None,tip=None):
            item=QtGui.QAction(text,self);item.triggered.connect(lambda:self.guard(fn));item.setToolTip(tip or text)
            if shortcut:item.setShortcut(shortcut)
            toolbar.addAction(item);return item
        action('Open Data Files',self.open_data,'Ctrl+O','Import TDMS, CSV, Excel, ZIP, Parquet or JSON recording')
        self.compare_data_action=action('Compare Data…',lambda:self.data_comparison.show_dialog(),tip='Choose channels from any loaded recordings to overlay in Comparison')
        action('Save workspace',self.save,'Ctrl+S');action('Restore Workspace',self.restore)
        self.export_button=QtWidgets.QPushButton('Export Report');self.export_button.setObjectName('exportReport')
        self.export_button.setStyleSheet('QPushButton {background:#216eb5; color:white; font-weight:600; padding:7px 16px; border-radius:5px;}')
        self.export_button.clicked.connect(lambda:self.guard(self.report));toolbar.addWidget(self.export_button)
        self.export_button.setToolTip('Save a PDF summary, interval CSV/Excel, or high-resolution PNG')
        report_action=QtGui.QAction(self);report_action.setShortcut('Ctrl+P');report_action.triggered.connect(lambda:self.guard(self.report));self.addAction(report_action)
        action('Calculate Channel',lambda:self.show_dock('Channel Math'),'Ctrl+M')
        self.layout_combo=QtWidgets.QComboBox();self.layout_combo.setToolTip('Choose a preset layout, or use Add Graph to build your own');self.layout_combo.addItems(PRESET_LAYOUTS);toolbar.addWidget(self.layout_combo)
        self.layout_combo.currentTextChanged.connect(lambda text:self.guard(lambda:self.set_graph_layout(text)))
        self.add_graph_action=toolbar.addAction('Add Graph',lambda:self.guard(self.add_graph))
        self.add_graph_action.setToolTip('Add a blank graph, then choose its channels in Data Portal. Right-click a graph to move, resize or remove it.')
        self.cursor_combo=QtWidgets.QComboBox();self.cursor_combo.setToolTip('Show two cursors, one cursor or hide cursors');[self.cursor_combo.addItem(label,mode) for label,mode in [('Two Cursors','dual'),('One Cursor','point'),('Hide Cursors','off')]];toolbar.addWidget(self.cursor_combo)
        self.cursor_combo.currentIndexChanged.connect(lambda index:[p.set_cursor_mode(self.cursor_combo.currentData()) for p in self.active_workspace.visible_panes()])
        self.snap_checkbox=QtWidgets.QCheckBox('Snap to Samples');self.snap_checkbox.setChecked(True);self.snap_checkbox.setToolTip('Snap cursors to recorded sample timestamps');toolbar.addWidget(self.snap_checkbox);self.snap_checkbox.toggled.connect(self.set_snap)
        view=self.menuBar().addMenu('View');self.view_menu=view
        view.addAction('Show all panels',self.enable_all_panels);view.addSeparator()
        for dock in self.docks.values():view.addAction(dock.toggleViewAction())
        channel=self.menuBar().addMenu('Channel');self.channel_menu=channel
        for text,command in [('Rename Channel','rename'),('Duplicate Channel','duplicate'),('Delete Selected Channels','delete'),('Assign Value Axis','assign axis'),('Mask Interval','mask interval'),('Clear Masks','clear masks'),('Add Marker','marker'),('Mark Interval','roi')]:
            item=channel.addAction(text);item.triggered.connect(lambda checked=False,c=command:self.organize(c))
        theme=QtWidgets.QComboBox();theme.addItems(['System','Dark','Light']);toolbar.addWidget(theme);theme.currentTextChanged.connect(self.theme.apply)
        self.help_action=QtGui.QAction('User Manual',self);self.help_action.setShortcut('F1');self.help_action.triggered.connect(self.show_help)
        self.info_action=QtGui.QAction('About / Updates',self);self.info_action.triggered.connect(self.show_info)
        channel.addSeparator();channel.addAction('Review TDMS parameters…',lambda:self.guard(self.review_loaded_tdms))
        self.program_alignment_action=channel.addAction('Align Program Starts…',lambda:self.guard(self.align_programs))
        toolbar.addAction(self.program_alignment_action)
        channel.addAction('Remove recording…',lambda:self.guard(self.remove_recording));channel.addAction('Clear workspace',lambda:self.guard(self.clear_recordings))
        self.undo_removal_action=QtGui.QAction('Undo Dataset Removal',self);channel.addAction(self.undo_removal_action)
        self.undo_removal_action.triggered.connect(lambda:self.guard(self.undo_recording_removal));self.undo_removal_action.setShortcut('Ctrl+Alt+Z');self.undo_removal_action.setEnabled(False)

        # One navigation presentation inside the graph header. Menus and
        # shortcuts continue using these workspace actions and selected mode.
        for index,workspace in enumerate(self.workspaces):
            workspace.mutation_guard=self.mutate
            bar=workspace.navigation_bar;bar.setObjectName(('Analysis','Comparison')[index]+'Navigation')
            bar.addSeparator();lock=bar.addAction('Lock Cursors…');lock.setToolTip('Lock Cursor A or B to a chosen channel sample (Ctrl+L)')
            lock.triggered.connect(lambda:self.guard(self.studio.cursor_lock_dialog))
            workspace.contextRequested.connect(lambda command,pane:self.guard(lambda:self.plot_context(command,pane)))
            workspace.graphStructureChanging.connect(self.exit_graph_fullscreen)
        from app_plot_workspace import install_graph_navigation
        install_graph_navigation(self.tabs,self.workspaces)

    def _build_operation_status(self):
        self.operation_progress=QtWidgets.QProgressBar();self.operation_progress.setMaximumWidth(150);self.operation_progress.hide()
        self.cancel_operation_button=QtWidgets.QPushButton('Cancel operation');self.cancel_operation_button.setToolTip('Request cancellation at the next safe step; an active file writer may need to finish its current step.');self.cancel_operation_button.hide()
        self.cancel_operation_button.clicked.connect(self.cancel_operation)
        self.open_export_button=QtWidgets.QPushButton('Open File');self.open_export_folder_button=QtWidgets.QPushButton('Open Folder')
        self.open_export_button.hide();self.open_export_folder_button.hide();self.last_export=None
        self.open_export_button.clicked.connect(lambda:self.open_export(False));self.open_export_folder_button.clicked.connect(lambda:self.open_export(True))
        for widget in (self.open_export_button,self.open_export_folder_button,self.operation_progress,self.cancel_operation_button):self.statusBar().addPermanentWidget(widget)

    def cancel_operation(self):
        for worker in self.workers:worker.cancel.set()
        if hasattr(self,'engineering') and self.busy:self.engineering.cancel_token.set()
        self.cancel_operation_button.setEnabled(False);self.statusBar().showMessage('Cancelling at the next safe step…')

    def open_export(self,folder=False):
        if self.last_export:
            path=self.last_export.parent if folder else self.last_export
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path.resolve())))

    def plot_context(self,command,pane):
        workspace=next((w for w in self.workspaces if pane in w.panes),None)
        if workspace is None:return
        self.tabs.setCurrentIndex(self.workspaces.index(workspace));workspace.active=pane;workspace.activeChanged.emit(pane)
        if command=='cursor':self.studio.cursor_lock_dialog()
        elif command=='export':self.report()
        elif command=='fullscreen':self.graph_fullscreen.enter(pane)
        elif command=='fullscreen-workspace':self.workspace_fullscreen.enter(workspace)
        elif command.startswith('trace-color:'):self.trace_colors.choose([command.partition(':')[2]])
        elif command=='compare':self.data_comparison.add_channels(pane.ids)
        elif command=='fft':
            self.show_dock('Channel Math');self.operation.setCurrentText('FFT')
            self.statusBar().showMessage('Select one source channel in the Data Portal, review its clock, then Apply to workspace.')

    def set_graph_layout(self,name):
        self.exit_graph_fullscreen()
        self.active_workspace.set_layout(name)

    def add_graph(self):
        self.mutate();self.exit_graph_fullscreen()
        pane=self.active_workspace.add_graph()
        self.show_dock('Data Portal')
        return pane

    def align_programs(self):
        from app_program_alignment_controls import ProgramAlignmentDialog
        self.mutate()
        dialog=ProgramAlignmentDialog(self)
        dialog.exec()

    def enable_all_panels(self):
        for dock in self.docks.values():dock.show()
        self.docks['Data Portal'].raise_();self.docks['Properties'].raise_();self.docks['Engineering Controls'].show();self.docks['Engineering Controls'].raise_();self.docks['Readout'].raise_()
        if hasattr(self,'panel_folding'):self.panel_folding.sync()

    def show_info(self):
        self.info_dialog.open()

    def show_help(self):
        self.help_dialog.show();self.help_dialog.raise_();self.help_dialog.activateWindow()

    def guard(self,fn):
        try:return fn()
        except Exception as exc:
            self.statusBar().showMessage(str(exc));QtWidgets.QMessageBox.warning(self,'Action could not complete',str(exc))

    def mutate(self):
        if self.busy:raise ValueError('Wait for the current operation before modifying channels')

    def background(self,fn,callback,*,title='Processing data',on_finished=None,managed_cancel=False):
        self.mutate();self.busy=True;self.apply_button.setEnabled(False)
        generation=self.generation;store=self.store
        self.statusBar().showMessage(title+'…');worker=Worker(fn);self.workers.add(worker)
        self.operation_progress.setRange(0,0);self.operation_progress.show();self.cancel_operation_button.setEnabled(True);self.cancel_operation_button.show()
        def progress(stage,value):
            if generation!=self.generation or worker not in self.workers:return
            self.statusBar().showMessage(stage)
            self.operation_progress.setRange(0,0 if value<0 else 100)
            if value>=0:self.operation_progress.setValue(value)
        worker.signals.progress.connect(progress)
        def complete(result,error):
            self.workers.discard(worker)
            if generation!=self.generation or store is not self.store:
                if not self.busy and not self.workers:self.operation_progress.hide();self.cancel_operation_button.hide()
                return
            self.busy=False;self.operation_progress.hide();self.cancel_operation_button.hide();self.update_processing_preflight()
            cancelled=worker.cancel.is_set() and not worker.output_committed and not managed_cancel
            final_error=error or (InterruptedError('Operation cancelled; prior results retained.') if cancelled else None)
            if on_finished is not None:self.guard(lambda:on_finished(final_error))
            if isinstance(final_error,InterruptedError):self.statusBar().showMessage(str(final_error));return
            if error:self.guard(lambda:(_ for _ in ()).throw(ValueError(str(error))))
            else:self.guard(lambda:callback(result))
            if error:self.statusBar().showMessage(str(error))
            elif not self.busy and self.statusBar().currentMessage()==title+'…':self.statusBar().showMessage('Ready')
        worker.signals.finished.connect(complete);self.pool.start(worker)

    def pick_file(self,field):
        from app_dialog_history import open_file
        purpose=next((key for key,widget in [('EngineeringPower',self.power_path),('EngineeringMachine',self.machine_path),('EngineeringSimulation',self.simulation_path)] if field is widget),'EngineeringRecording')
        path,_=open_file(self,'Choose recording',purpose=purpose)
        if path:field.setText(path)

    def open_data(self,*,plot_import=True):
        from app_dialog_history import open_files
        self.mutate();paths,_=open_files(self,'Open recordings','','Data (*.tdms *.csv *.txt *.xlsx *.xls *.zip *.parquet *.json)',purpose='OpenData')
        if not paths:return False
        def load():
            from app_operation_context import checkpoint
            store=ChannelStore()
            for index,path in enumerate(paths):
                checkpoint(f'Loading {Path(path).name} ({index+1}/{len(paths)})',index,len(paths));ingest(store,path);checkpoint()
            return store
        workspace=self.active_workspace
        self.background(load,lambda other:self.finish_import(other,workspace,plot_import=plot_import),title='Opening recordings')
        return True

    def finish_import(self,other,workspace=None,*,plot_import=True):
        if not other.channels:raise ValueError('No numeric measurement channels were found. Check the file format, coordinate column and unit settings.')
        if self.review_tdms_import(other):self.merge_store(other,workspace,plot_import=plot_import)

    def review_tdms_import(self,other):
        """Use one template contract for Open and Engineering Controls."""
        from app_tdms_templates import ParameterTemplates,ParameterReview
        templates=ParameterTemplates();unknown=templates.unknown(other)
        if unknown:
            dialog=ParameterReview(unknown,self,templates.warning)
            try:
                if dialog.exec()!=QtWidgets.QDialog.DialogCode.Accepted:return False
                templates.save(dialog.entries())
            finally:
                dialog.deleteLater()
        templates.apply(other)
        return True

    def review_loaded_tdms(self):
        self.mutate()
        from app_tdms_templates import ParameterTemplates,ParameterReview,identity
        channels=[c for c in self.store.channels.values() if c.attributes.get('format')=='TDMS']
        if not channels:raise ValueError('Open a TDMS recording first')
        templates=ParameterTemplates();dialog=ParameterReview(channels,self,templates.warning)
        for row,c in enumerate(dialog.channels):
            entry=templates.entries.get(identity(c))
            if entry:
                dialog.table.item(row,1).setText(entry['name']);dialog.table.item(row,2).setText(entry['unit'])
                dialog.table.cellWidget(row,3).setCurrentIndex(dialog.table.cellWidget(row,3).findData(entry['interpretation']))
        if dialog.exec()==QtWidgets.QDialog.DialogCode.Accepted:
            templates.save(dialog.entries());templates.apply(self.store);self.store.changed(*[c.id for c in channels])

    def remove_recording(self):
        self.mutate();datasets=list(self.store.datasets.values())
        if not datasets:return
        labels=[f'{ds.name} [{ds.id[:8]}]' for ds in datasets]
        from app_compact_forms import choose_item
        choice,ok=choose_item(self,'Remove recording','Unload recording (original file is kept):',labels)
        if ok:self.request_drop_recordings([datasets[labels.index(choice)].id])

    def request_drop_recordings(self,dataset_ids):
        """Confirm cross-channel consequences on user actions, not service calls."""
        self.mutate();plan=self.store.removal_plan(dataset_ids)
        if plan['dependent_ids']:
            text=f"Close {len(plan['dataset_ids'])} recording(s) and unload {len(plan['channel_ids'])} channels, including {len(plan['dependent_ids'])} dependent derived channels? Original files are kept. Undo Dataset Removal can restore this workspace work."
            dialog=QtWidgets.QMessageBox(QtWidgets.QMessageBox.Icon.Question,'Review dataset removal',text,QtWidgets.QMessageBox.StandardButton.Yes|QtWidgets.QMessageBox.StandardButton.No,self)
            from app_channel_identity import channel_label
            dialog.setDetailedText('Dependent channels:\n'+'\n'.join(channel_label(self.store,id,include_source=True) for id in plan['dependent_ids']))
            dialog.setDefaultButton(QtWidgets.QMessageBox.StandardButton.No)
            if dialog.exec()!=QtWidgets.QMessageBox.StandardButton.Yes:return
        self.drop_recordings(dataset_ids)

    def clear_recordings(self):
        self.mutate()
        if not self.store.datasets and not self.store.channels:return
        answer=QtWidgets.QMessageBox.question(self,'Clear workspace','Unload all recordings and generated channels from Analysis and Comparison? Original files and saved outputs are kept.')
        if answer==QtWidgets.QMessageBox.StandardButton.Yes:self.drop_recordings(list(self.store.datasets),clear_all=True)

    def drop_recordings(self,dataset_ids,clear_all=False):
        self.mutate()
        self.exit_graph_fullscreen()
        snapshot=self.store.removal_snapshot(dataset_ids,clear_all=clear_all)
        self.removal_undo=(snapshot,deepcopy([workspace.state() for workspace in self.workspaces]),deepcopy(self.ui_state()))
        with self.store.batch():
            self.store.remove_datasets(dataset_ids)
            if clear_all:self.store.delete(list(self.store.channels))
        self.scorecard_data=None;self.scorecard.setModel(FrameModel())
        if not self.store.channels:
            self.prop_name.clear();self.prop_unit.clear();self.prop_group.clear();self.prop_attrs.clear();self.apply_button.setEnabled(False)
            self.prop_metadata.setRowCount(0)
            for field in (self.warning_min,self.warning_max,self.fault_min,self.fault_max):field.clear()
        if clear_all:
            for field in (self.power_path,self.machine_path,self.simulation_path):field.clear()
        self.undo_removal_action.setEnabled(bool(snapshot.channel_ids or snapshot.datasets))
        self.sync_visibility();self._readouts();self.statusBar().showMessage('Recording removed. Original files kept. Use Channel → Undo Dataset Removal to restore unloaded work.')

    def undo_recording_removal(self):
        self.mutate()
        if self.removal_undo is None:return
        snapshot,saved_views,ui=self.removal_undo;views=deepcopy(saved_views)
        # Preserve traces added since removal while reinstating the original
        # bindings and exact cursor/sample identities in their former panes.
        for workspace,state in zip(self.workspaces,views):
            current=workspace.state();panes=state.setdefault('panes',[]);additional=[]
            all_channels={**snapshot.channels,**self.store.channels}
            for index,now in enumerate(current['panes']):
                if index>=len(panes):panes.append(deepcopy(now));continue
                saved=panes[index];extras=[id for id in now['ids'] if id not in saved.get('ids',[])]
                if not extras:continue
                if not saved.get('ids'):
                    panes[index]=deepcopy(now);continue
                old_coordinates={(all_channels[id].coordinate_kind,all_channels[id].coordinate_unit) for id in saved.get('ids',[]) if id in all_channels}
                new_coordinates={(all_channels[id].coordinate_kind,all_channels[id].coordinate_unit) for id in extras if id in all_channels}
                if old_coordinates and new_coordinates!=old_coordinates:
                    # Time and frequency cannot share a viewport. Preserve the
                    # user's later work in another pane instead of dropping it.
                    extra=deepcopy(now);extra['ids']=extras;extra['bindings']={id:now.get('bindings',{}).get(id,'') for id in extras};additional.append(extra)
                else:
                    saved.setdefault('ids',[]).extend(extras)
                    saved.setdefault('bindings',{}).update({id:now['bindings'][id] for id in extras if id in now.get('bindings',{})})
                    saved_locks=saved.setdefault('cursor_locks',[None,None])
                    for cursor,lock in enumerate(now.get('cursor_locks',[None,None])):
                        if saved_locks[cursor] is None and lock and lock.get('channel') in self.store.channels:
                            saved_locks[cursor]=deepcopy(lock)
                            saved.setdefault('cursors',[0,0])[cursor]=now.get('cursors',[0,0])[cursor]
            old_count=np.prod(LAYOUTS[state['layout']]);current_count=np.prod(LAYOUTS[current['layout']])
            if current_count>=old_count:
                state['layout']=current['layout'];state['active']=current.get('active',0);state['layout_proportions']=current.get('layout_proportions',{})
            if additional:
                for extra in additional:
                    empty=next((index for index,pane in enumerate(panes) if not pane.get('ids')),None)
                    if empty is None:panes.append(extra)
                    else:panes[empty]=extra
                required=max(index+1 for index,pane in enumerate(panes) if pane.get('ids'))
                choices=[(rows*cols,name) for name,(rows,cols) in LAYOUTS.items() if rows*cols>=required]
                if not choices:raise ValueError('Undo needs another viewport for a different coordinate domain. Save your current work or close an unused pane before retrying.')
                state['layout']=min(choices)[1]
        current_ui=self.ui_state()
        current_ui['selection']=list(dict.fromkeys(current_ui.get('selection',[])+ui.get('selection',[])))
        if current_ui.get('source') is None:current_ui['source']=ui.get('source')
        for key,value in ui.get('engineering',{}).items():
            if key in ('power','machine','simulation') and not current_ui['engineering'].get(key):current_ui['engineering'][key]=value
        self.store.restore_removal(snapshot)
        self.restore_loaded(self.store,views,current_ui)
        self.removal_undo=None;self.undo_removal_action.setEnabled(False)
        self.statusBar().showMessage('Dataset removal undone; channels, dependencies, plot bindings and cursor locks restored.')

    def merge_store(self,other,workspace=None,deduplicate_alignment=False,*,plot_import=True):
        from app_actuators import interpret_channel
        for id,channel in list(other.channels.items()):other.channels[id]=interpret_channel(channel)
        from app_time_units import normalize_minutes
        normalize_minutes(other)
        if deduplicate_alignment:
            from app_alignment_merge import merge_alignment
            before=[(pane,pane.state()) for workspace_item in self.workspaces for pane in workspace_item.panes]
            ids,updated,remap=merge_alignment(self.store,other)
            for pane,state in before:
                if any(id in remap for id in state['ids']):
                    state['ids']=list(dict.fromkeys(remap.get(id,id) for id in state['ids']))
                    state['bindings']={remap.get(id,id):unit for id,unit in state['bindings'].items()}
                    for lock in state.get('cursor_locks',[]):
                        if lock:lock['channel']=remap.get(lock['channel'],lock['channel'])
                    pane.bind(state['ids'],state['bindings'],fit=False);pane.restore_ranges(state)
            self.statusBar().showMessage(f'Alignment refreshed: {len(ids)} new channels, {updated} updated; existing samples are not duplicated.')
        else:
            with self.store.batch():
                self.store.datasets.update(other.datasets)
                for c in other.channels.values():self.store.add(c)
            ids=list(other.channels)
        if ids and plot_import:
            target=workspace or self.active_workspace;was_empty=not any(p.ids for p in target.panes)
            previous=[(p,p.state()) for p in target.visible_panes() if p.ids] if deduplicate_alignment else []
            target.assign(ids)
            for pane,state in previous:pane.restore_ranges(state)
            if was_empty and not self.studio.pending_preset:target.arrange_readable()
        self.sync_visibility()
        if plot_import and hasattr(self,'studio') and self.studio.pending_preset:self.studio.apply_preset(self.studio.pending_preset)

    def store_changed(self,ids):
        self.portal.rebuild()
        for workspace in self.workspaces:workspace.refresh()
        current=self.source_selector.currentData();self.source_selector.blockSignals(True);self.source_selector.clear();self.source_selector.addItem('Selected channel projection',None)
        for ds in self.store.datasets.values():self.source_selector.addItem(ds.name,ds.id)
        if current:self.source_selector.setCurrentIndex(max(0,self.source_selector.findData(current)))
        self.source_selector.blockSignals(False);self.show_source();self.readouts()

    def selection(self,ids):
        if ids:
            c=self.store.channels[ids[0]];self._property_channel_id=c.id;self._property_metadata_base=deepcopy(c.attributes);self.prop_name.setText(c.name);self.prop_unit.setText(c.unit);self.prop_group.setText(c.group);self.prop_kind.setCurrentText(c.kind)
            self.prop_interpretation.setCurrentIndex(max(0,self.prop_interpretation.findData(c.attributes.get('value_interpretation','auto'))))
            self.prop_attrs.setPlainText(json.dumps(c.attributes,indent=2))
            self._metadata_snapshot=self.prop_attrs.toPlainText();self.populate_metadata(c.attributes)
            for key,field in [('warning_min',self.warning_min),('warning_max',self.warning_max),('fault_min',self.fault_min),('fault_max',self.fault_max)]:field.setText(str(c.attributes.get(key,'')))
        self.show_source();self.update_processing_preflight(reset_default=True)

    def populate_metadata(self,attributes):
        self.prop_metadata.setRowCount(len(attributes))
        for row,(key,value) in enumerate(attributes.items()):
            self.prop_metadata.setItem(row,0,QtWidgets.QTableWidgetItem(str(key)))
            self.prop_metadata.setItem(row,1,QtWidgets.QTableWidgetItem(json.dumps(value,ensure_ascii=False)))

    def structured_metadata(self):
        result={}
        for row in range(self.prop_metadata.rowCount()):
            key=self.prop_metadata.item(row,0);value=self.prop_metadata.item(row,1)
            name=key.text().strip() if key else ''
            if not name and (value is None or not value.text().strip()):continue
            if not name:raise ValueError('Each custom property needs a name')
            if name in result:raise ValueError('Custom property names must be unique: '+name)
            text=value.text() if value else ''
            try:result[name]=json.loads(text)
            except json.JSONDecodeError:result[name]=text
        return result

    def toggle_metadata_editor(self,advanced):
        try:
            if advanced:
                self.prop_attrs.setPlainText(json.dumps(self.structured_metadata(),indent=2,ensure_ascii=False))
                self._metadata_snapshot=self.prop_attrs.toPlainText()
            else:
                value=json.loads(self.prop_attrs.toPlainText() or '{}')
                if not isinstance(value,dict):raise ValueError('Properties must be a JSON object')
                self.populate_metadata(value);self._metadata_snapshot=self.prop_attrs.toPlainText()
        except (ValueError,TypeError) as exc:
            blocker=QtCore.QSignalBlocker(self.metadata_advanced);self.metadata_advanced.setChecked(not advanced);del blocker
            self.statusBar().showMessage(str(exc));return
        self.prop_attrs.setVisible(advanced);self.prop_metadata.setVisible(not advanced)

    def apply_properties(self):
        self.mutate();ids=self.portal.selected()
        if len(ids)!=1:raise ValueError('Select one channel to edit properties')
        raw=self.prop_attrs.toPlainText()
        attrs=json.loads(raw or '{}') if self.metadata_advanced.isChecked() or raw!=getattr(self,'_metadata_snapshot',raw) else self.structured_metadata()
        if not isinstance(attrs,dict):raise ValueError('Properties must be a JSON object')
        c=self.store.channels[ids[0]]
        from app_metadata_merge import merge_metadata_edits
        base=getattr(self,'_property_metadata_base',c.attributes) if getattr(self,'_property_channel_id',None)==c.id else c.attributes
        attrs=merge_metadata_edits(base,attrs,c.attributes)
        for key,field in [('warning_min',self.warning_min),('warning_max',self.warning_max),('fault_min',self.fault_min),('fault_max',self.fault_max)]:
            if field.text():attrs[key]=float(field.text())
            else:attrs.pop(key,None)
        from app_actuators import interpret_channel
        from dataclasses import replace
        if self.prop_unit.text()!=c.unit:attrs['raw_unit']=self.prop_unit.text()
        if self.prop_kind.currentText()!=c.kind:attrs['raw_kind']=self.prop_kind.currentText()
        candidate=replace(c,name=self.prop_name.text(),unit=self.prop_unit.text(),group=self.prop_group.text(),kind=self.prop_kind.currentText(),attributes=attrs)
        updated=interpret_channel(candidate,self.prop_interpretation.currentData())
        self.store.update(c.id,name=updated.name,unit=updated.unit,group=updated.group,kind=updated.kind,y=updated.y,raw_y=updated.raw_y,attributes=updated.attributes)
        if bool(c.attributes.get('actuator_binary'))!=bool(updated.attributes.get('actuator_binary')):
            for workspace in self.workspaces:
                for pane in workspace.panes:
                    if c.id not in pane.curves or pane.normalized:continue
                    view=pane.curves[c.id][0];bounds=[]
                    for id,(axis,curve) in pane.curves.items():
                        if axis is view:
                            values=self.store.channels[id].values()[1];finite=values[np.isfinite(values)]
                            if len(finite):bounds.extend([float(finite.min()),float(finite.max())])
                    if bounds:view.setYRange(min(bounds),max(bounds) if max(bounds)>min(bounds) else min(bounds)+1,padding=.08)
        # Refresh the baseline only after a successful Apply; opening an editor
        # or switching its representation must not turn draft edits into saved
        # metadata or discard a color changed by another control.
        self.selection([c.id])

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
                command2,ok=QtWidgets.QInputDialog.getItem(self,'Organize','Action',['Rename','Duplicate','Delete','Move / group','Move to dataset','Merge groups','Move up','Move down','Assign axis','Mask interval','Clear masks','Marker','Threshold','Mark Interval'])
                if ok:self.organize('roi' if command2=='Mark Interval' else command2.lower())
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
                from app_compact_forms import choose_item
                choice,ok=choose_item(self,'Move channels','Destination dataset',[f'{ds.name} [{ds.id[:8]}]' for ds in datasets])
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
        self.mutate();store=self.store;workspace=self.active_workspace;expression=self.expression.text();name=self.formula_name.text()
        def complete(channel):self.store.add(channel);workspace.assign([channel.id]);self.sync_visibility()
        self.background(lambda:formula(store,expression,name),complete,title='Calculating formula channel')

    def show_parameters(self,*args):
        relevant={'Moving average':['window'],'Savitzky–Golay':['window','order'],'Butterworth low-pass':['cutoff','order'],
                  'Offset and scale':['scale','offset'],'Time shift':['shift'],'Resampling':['step'],'Histogram':['bins'],
                  'Peak and valley detection':['prominence']}.get(self.operation.currentText(),[])
        for key,field in self.parameter_fields.items():
            field.setVisible(key in relevant);self.parameter_form.labelForField(field).setVisible(key in relevant)
        if hasattr(self,'apply_button'):self.update_processing_preflight()

    def update_processing_preflight(self,*args,reset_default=False):
        if not hasattr(self,'apply_button'):return
        from app_processing_preflight import processing_preflight
        ids=self.portal.selected();channel=self.store.channels.get(ids[0]) if len(ids)==1 else None
        if reset_default and channel is not None and getattr(self,'_cutoff_channel',None)!=channel.id:
            self._cutoff_channel=channel.id
            info=processing_preflight(channel,'Butterworth low-pass')
            if info['nyquist']:
                spin=self.parameter_fields['cutoff'];blocker=QtCore.QSignalBlocker(spin)
                spin.setValue(min(1,info['nyquist']*.5));del blocker
        check=processing_preflight(channel,self.operation.currentText(),self.parameter_fields['cutoff'].value())
        self.parameter_help.setText(check['message']);self.parameter_help.setAccessibleName('Processing requirements: '+check['message'])
        self.apply_button.setEnabled(check['valid'] and not self.busy)
        self.apply_button.setToolTip('Create a derived channel; original samples are preserved.' if check['valid'] else check['message'])

    def apply_transform(self):
        ids=self.portal.selected()
        if len(ids)!=1:raise ValueError('Select one source channel')
        c=self.store.channels[ids[0]];workspace=self.active_workspace
        operation=self.operation.currentText();params={key:field.value() for key,field in self.parameter_fields.items()}
        from app_processing_preflight import processing_preflight
        check=processing_preflight(c,operation,params['cutoff'])
        if not check['valid']:raise ValueError(check['message'])
        def complete(result):
            if self.store.channels.get(c.id) is not c:return
            self.store.add(result);workspace.assign([result.id]);self.sync_visibility()
        self.background(lambda:transform(c,operation,**params),complete,title=operation+' · '+c.name)

    def define_unit(self):
        from app_adaptive_ui import ContentDialog
        from app_compact_forms import add_help,ElidedComboBox
        dialog=ContentDialog(self);dialog.setWindowTitle('Define Local Unit');layout=QtWidgets.QVBoxLayout(dialog);form=QtWidgets.QFormLayout();layout.addLayout(form)
        symbol=QtWidgets.QLineEdit();reference=ElidedComboBox();reference.addItems([key for key in UNIT_DEFINITIONS if key]);scale=QtWidgets.QDoubleSpinBox();scale.setDecimals(10);scale.setRange(1e-10,1e12);scale.setValue(1)
        form.addRow('New unit symbol',symbol);form.addRow('Reference unit',reference);form.addRow('Scale relative to reference',scale)
        error=QtWidgets.QLabel();error.setWordWrap(True);layout.addWidget(error)
        add_help(layout,'One value in the new unit equals Scale values in the reference unit. For mW relative to W use 0.001. This defines a conversion; it does not change or calibrate recorded samples.')
        buttons=QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Save|QtWidgets.QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons);buttons.rejected.connect(dialog.reject)
        def save():
            key=symbol.text().strip()
            if not key:error.setText('Enter a unit symbol.');return
            if key in UNIT_DEFINITIONS:error.setText('That symbol is already defined; choose a new symbol.');return
            dimension,factor=UNIT_DEFINITIONS[reference.currentText()];UNIT_DEFINITIONS[key]=(dimension,factor*scale.value());dialog.accept()
        buttons.accepted.connect(save);dialog.open();self.unit_definition_dialog=dialog

    def readouts(self):
        if hasattr(self,'stats_scope'):
            for workspace in self.workspaces:workspace.statistics_scope=self.stats_scope.currentText()
        if hasattr(self,'readout_timer') and not self.readout_timer.isActive():self.readout_timer.start(16)

    def statistics_for_display(self,pane,channel_id,stats):
        if self.stats_scope.currentIndex()==0:return stats
        channel=self.store.channels[channel_id]
        if not len(channel.x):return stats
        whole=pane.summaries[channel_id][1].query(float(channel.x[0]+channel.shift),float(channel.x[-1]+channel.shift))
        return {**stats,**{key:whole[key] for key in ('Min','Max','Mean')}}

    def locked_cursor_texts(self,pane):
        import html
        a,b=[line.value() for line in pane.cursor_lines]
        locked=[]
        for index,lock in enumerate(pane.cursor_locks):
            if not lock or lock['channel'] not in self.store.channels:continue
            channel=self.store.channels[lock['channel']];point=(a,b)[index];value=pane.cursor_value(channel.id,index)
            reading=f'{value:.6g} {html.escape(channel.unit)}' if np.isfinite(value) else 'No reading'
            if channel.attributes.get('actuator_binary'):
                from app_actuators import state_text
                reading=state_text(value)
            from app_channel_identity import channel_label
            label=self.interval_card.fontMetrics().elidedText(channel_label(self.store,channel),QtCore.Qt.TextElideMode.ElideMiddle,max(100,int(self.interval_card.width()*.65)))
            locked.append(f'<span style="color:{CURSOR_COLORS[index]};background:#182033;padding:4px"><b>{("A","B")[index]} locked · {html.escape(label)} = {reading}</b> @ {point:.6g} {html.escape(channel.coordinate_unit)}</span>')
        return locked

    def _readouts(self):
        if not self.active_workspace.active:return
        pane=self.active_workspace.active
        self.sync_visibility()
        a,b=[line.value() for line in pane.cursor_lines]
        pane_number=self.active_workspace.panes.index(pane)+1
        coordinate=pane.coordinate or ('No channels selected','')
        self.cursor_caption.setText(f'Active pane {pane_number} · {coordinate[0]} ({coordinate[1]}) &nbsp; <span style="color:{CURSOR_COLORS[0]};background:#182033;padding:4px"><b>A</b> {a:.6g}</span> &nbsp; <span style="color:{CURSOR_COLORS[1]};background:#182033;padding:4px"><b>B</b> {b:.6g}</span>')
        self.cursor_caption.setWordWrap(True)
        if hasattr(self,'studio'):
            live=self.studio.live_readout(pane,a)
            if live:self.cursor_caption.setText(self.cursor_caption.text()+' &nbsp; '+live)
        try:measurements=self.active_workspace.measurement_rows()
        except KeyError:return
        self.readout.setRowCount(len(measurements));self.intervals.setRowCount(len(measurements))
        self.readout.setColumnHidden(4,not any(match_color(self.store.channels[id].attributes.get('match_percent')) for id in measurements))
        def display(value):return f'{value:.6g}' if np.isfinite(value) else 'Unknown'
        for row,(id,(owner,interval_stats)) in enumerate(measurements.items()):
            stats=self.statistics_for_display(owner,id,interval_stats)
            c=self.store.channels[id]
            from app_channel_identity import channel_label,channel_details
            label=channel_label(self.store,c)
            cells=[label,c.unit or 'Unknown',display(stats['A']),display(stats['B']),f"{float(c.attributes['match_percent']):.1f}%" if match_color(c.attributes.get('match_percent')) else '—',display(stats['ΔY']),display(stats['Min']),display(stats['Max']),display(stats['Mean'])]
            if c.attributes.get('actuator_binary'):
                from app_actuators import state_text
                cells[2]=state_text(stats['A']);cells[3]=state_text(stats['B']);cells[5]=cells[2]+' → '+cells[3];cells[6]=state_text(stats['Min']);cells[7]=state_text(stats['Max']);cells[8]=f"{100*stats['Mean']:.4g}% ON" if np.isfinite(stats['Mean']) else 'Unknown'
            for col,text in enumerate(cells):
                item=QtWidgets.QTableWidgetItem(text);item.setToolTip(channel_details(self.store,c)+'\n'+text)
                if col in (2,3):
                    item.setForeground(QtGui.QColor(CURSOR_COLORS[col-2]));item.setBackground(QtGui.QColor('#182033'))
                if col==4:
                    color=match_color(c.attributes.get('match_percent'))
                    if color:item.setBackground(QtGui.QColor(color));item.setForeground(QtGui.QColor('#101828'))
                self.readout.setItem(row,col,item)
            labels=['ΔX','ΔY','Mean','RMS','Min','Max','Peak-to-Peak','Slope','Integral','Coverage']
            measure_unit=c.coordinate_unit
            physical=c.unit or 'Unknown unit'
            units=[c.coordinate_unit,physical,physical,physical,physical,physical,physical,physical+'/'+measure_unit,physical+'·'+measure_unit,'fraction']
            self.intervals.setItem(row,0,QtWidgets.QTableWidgetItem(label))
            for col,(label,unit) in enumerate(zip(labels,units),1):self.intervals.setItem(row,col,QtWidgets.QTableWidgetItem(display(interval_stats[label])+' '+unit))

        self.update_interval_card()

    def engineering_import(self,paths,calculate,complete):
        """Review every native TDMS parameter before starting derived analysis.

        Nothing is merged on cancellation. Loading and analysis stay in workers;
        the dialog and template writes stay on the UI thread, like Open.
        """
        from pathlib import Path
        tdms=list(dict.fromkeys(str(p) for p in paths if p and Path(p).suffix.lower()=='.tdms'))
        if not tdms:
            self.background(calculate,complete)
            return
        def load():
            native=ChannelStore()
            for path in tdms:ingest(native,path)
            return native
        def reviewed(native):
            if self.review_tdms_import(native):self.background(calculate,complete)
            else:self.statusBar().showMessage('TDMS import cancelled; workspace unchanged')
        self.background(load,reviewed)

    def align(self):
        power,machine,strategy,offset=self.power_path.text(),self.machine_path.text(),self.sync.currentData() or self.sync.currentText(),self.offset.value()
        from app_analysis_service import align_recordings
        def calculate():return align_recordings(power,machine,strategy,offset,self.studio.plugins)
        def complete(result):
            other,frame=result
            from app_tdms_templates import ParameterTemplates
            ParameterTemplates().apply(other)
            self.aligned_frame=frame
            self.engineering_notes.setPlainText(json.dumps(frame.attrs.get('sync_report',{}),default=str,indent=2))
            self.merge_store(other,self.dashboard,deduplicate_alignment=True);self.tabs.setCurrentIndex(0);self.studio.apply_display()
        self.engineering_import((power,machine),calculate,complete)

    def compare(self):
        machine,simulation=self.machine_path.text(),self.simulation_path.text()
        if not machine or not simulation:raise ValueError('Choose machine and simulation recordings')
        settings=dict(self.studio.reference_settings);calibration=dict(self.studio.calibration);mapping=dict(self.studio.bench_columns)
        def calculate():
            from app_analysis_service import compare_recordings
            return compare_recordings(machine,simulation,reference_settings=settings,calibration=calibration,bench_columns=mapping,tolerances=dict(self.studio.tolerances),detailed=True)
        def complete(result):
            from app_tdms_templates import ParameterTemplates
            ParameterTemplates().apply(result.store)
            self.comparison_result=result
            from app_reporting import match_scorecard
            self.scorecard_data=match_scorecard(result.score);self.scorecard.setModel(FrameModel(self.scorecard_data))
            self.merge_store(result.store,self.comparison);self.tabs.setCurrentIndex(1);self.show_dock('Engineering Controls');self.studio.apply_display()
        self.engineering_import((machine,),calculate,complete)

    def ui_state(self):
        return {'app_version':VERSION,'geometry':bytes(self.saveGeometry().toBase64()).decode(),'docks':bytes(self.saveState().toBase64()).decode(),
                'panel_folding':self.panel_folding.state() if hasattr(self,'panel_folding') else None,
                'stats_scope':self.stats_scope.currentText(),'tab':getattr(self,'_plot_tab_index',0),'selection':self.portal.selected(),'source':self.source_selector.currentData(),
                'scorecard':self.scorecard_data.to_json(orient='split') if getattr(self,'scorecard_data',None) is not None else None,
                'focus_graph':{'enabled':self.compact.focus_action.isChecked(),'normal':bytes(self.compact.focus_state.toBase64()).decode() if self.compact.focus_state is not None else ''},'engineering_session':self.engineering.state(),'studio':self.studio.state(),'units':UNIT_DEFINITIONS,'engineering':{'power':self.power_path.text(),'machine':self.machine_path.text(),'simulation':self.simulation_path.text(),'strategy':self.sync.currentData() or self.sync.currentText(),'offset':self.offset.value()}}

    def save(self):
        from app_dialog_history import save_file
        self.mutate();path,_=save_file(self,'Save portable workspace',str(output_path('Workspace.json','workspaces')),'Workspace (*.json)',purpose='WorkspaceSave')
        if path:
            store=self.store;views=[w.state() for w in self.workspaces];ui=self.ui_state()
            self.background(lambda:save_workspace(path,store,views,ui),lambda saved:self.statusBar().showMessage(f'Saved {saved} and adjacent NPZ; keep both files together.'),title='Saving workspace')

    def restore(self):
        from app_dialog_history import open_file
        self.mutate()
        path,_=open_file(self,'Restore workspace','','Workspace (*.json *.xml *.ini *.cfg)',purpose='WorkspaceOpen')
        if path:self.background(lambda:load_workspace(path),lambda result:self.restore_loaded(*result),title='Restoring workspace')

    def restore_path(self,path,upgrade_defaults=False):
        store,views,ui=load_workspace(path)
        self.restore_loaded(store,views,ui,upgrade_defaults)

    def restore_loaded(self,store,views,ui,upgrade_defaults=False):
        self.exit_graph_fullscreen()
        if ui.get('engineering_session'):
            from app_engineering_session import validate_session
            validate_session(ui['engineering_session'])
        from app_actuators import interpret_channel
        converted=set()
        for id,channel in list(store.channels.items()):
            dataset=store.datasets.get(channel.dataset_id);column=channel.attributes.get('data_column');source=None
            if channel.raw_y is None and dataset is not None and column in dataset.frame and len(dataset.frame)==len(channel.y):source=dataset.frame[column]
            updated=interpret_channel(channel,raw_series=source);store.channels[id]=updated
            if updated.attributes.get('actuator_binary') and not channel.attributes.get('actuator_binary'):converted.add(id)
        for workspace in views:
            for pane in workspace.get('panes',[]):
                for id in converted.intersection(pane.get('ids',[])):
                    if pane.get('bindings',{}).get(id) in ('state','',None):pane.setdefault('bindings',{})[id]='Actuators'
                if converted.intersection(pane.get('ids',[])) and not pane.get('normalized'):
                    pane.setdefault('axes',{})['Actuators']=[-.08,1.08]
                    if pane['ids'][0] in converted and 'range' in pane:pane['range'][1]=[-.08,1.08]
        from app_time_units import normalize_minutes
        normalize_minutes(store,views)
        if len(views)==3:
            views=[views[2] if ui.get('tab')==2 else views[0],views[1]]
            if ui.get('tab')==2:ui['tab']=0
        if store is not self.store:
            self.removal_undo=None;self.undo_removal_action.setEnabled(False)
        self.generation+=1;self.busy=False;self.apply_button.setEnabled(True);self.store=store;self.portal.store=store
        # Very early source-only workspaces had no view snapshots. Never leave
        # a viewport pointing at the previous store when such a file is opened.
        for index,workspace in enumerate(self.workspaces):
            workspace.store=store
            state=views[index] if index<len(views) else {'layout':'Single','panes':[{'ids':[]}],'active':0}
            workspace.restore(state)
        self.store.observe(self.store_changed);self.store_changed(set())
        for encoded,method in [(ui.get('geometry'),self.restoreGeometry),(ui.get('docks'),self.restoreState)]:
            if encoded:method(QtCore.QByteArray.fromBase64(encoded.encode()))
        # Older workspaces may contain show_channel_kind. Its removed portal
        # column has no display state to restore; channel metadata stays intact.
        # An explicit legacy dock layout wins over today's startup defaults.
        # Missing folding metadata is reflected from Qt, never treated as a
        # request to reopen all supporting panels.
        if hasattr(self,'panel_folding'):self.panel_folding.restore(ui.get('panel_folding'))
        self.stats_scope.setCurrentText(ui.get('stats_scope','Cursor interval'))
        self.tabs.setCurrentIndex(min(ui.get('tab',0),len(self.workspaces)-1));self.source_selector.setCurrentIndex(max(0,self.source_selector.findData(ui.get('source'))))
        selected=set(ui.get('selection',[]))
        iterator=QtWidgets.QTreeWidgetItemIterator(self.portal.tree)
        while iterator.value():
            item=iterator.value();item.setSelected(item.data(0,QtCore.Qt.ItemDataRole.UserRole) in selected);iterator+=1
        from io import StringIO
        self.scorecard_data=pd.read_json(StringIO(ui['scorecard']),orient='split') if ui.get('scorecard') else None
        self.scorecard.setModel(FrameModel(self.scorecard_data))
        UNIT_DEFINITIONS.update(ui.get('units',{}))
        engineering=ui.get('engineering',{})
        for key,field in [('power',self.power_path),('machine',self.machine_path),('simulation',self.simulation_path)]:field.setText(engineering.get(key,''))
        self.studio.select_sync(engineering.get('strategy',self.sync.currentData() or self.sync.currentText()));self.offset.setValue(engineering.get('offset',0))
        self.compact.restore_focus(ui.get('focus_graph',{}))
        self.studio.restore(ui.get('studio',{}));self.engineering.restore(ui.get('engineering_session'));self.readouts()

    def report(self):
        from app_reporting import export_report
        from app_dialog_history import save_file
        if not any(p.ids for p in self.active_workspace.visible_panes()):raise ValueError('Check at least one channel before exporting')
        self.mutate()
        filters='PDF plot and cursor summary (*.pdf);;Excel interval samples and cursor summary (*.xlsx);;CSV interval samples (*.csv);;High-resolution PNG snapshot (*.png)'
        path,selected=save_file(self,'Export Report',str(output_path('Signal report.pdf')),filters,purpose='ExportReport')
        if path:
            extensions={'PDF':'.pdf','Excel':'.xlsx','CSV':'.csv','High-resolution':'.png'}
            suffix=next((v for k,v in extensions.items() if selected.startswith(k)),'.pdf')
            if not Path(path).suffix:path+=suffix
            if Path(path).suffix.lower() not in ('.pdf','.xlsx','.csv','.png'):raise ValueError('Choose PDF, Excel, CSV or PNG')
            # Capture widget state on the GUI thread. The worker only sees
            # immutable source data and plain snapshots, never Qt plot items.
            store=self.store;state=deepcopy(self.active_workspace.state());score=getattr(self,'scorecard_data',None) if self.active_workspace is self.comparison else None
            state['workspace_name']='Comparison' if self.active_workspace is self.comparison else 'Analysis'
            state['report_kind']='comparison' if self.active_workspace is self.comparison else 'analysis'
            state['statistics_scope']=self.stats_scope.currentText()
            metadata=self.report_metadata()
            score=score.copy(deep=True) if score is not None else None;title=self.studio.options['title']
            def complete(_):
                self.last_export=Path(path);self.open_export_button.show();self.open_export_folder_button.show()
                self.statusBar().showMessage(f'Report saved: {path}')
            self.background(lambda:export_report(path,store,state,score,title=title,metadata=metadata),complete,title='Exporting active workspace')

    def set_snap(self,value):
        for pane in self.active_workspace.visible_panes():
            pane.snap=value;pane._cursor_changed()
        self.readouts()

    def workspace_changed(self,*args):
        if self.tabs.currentIndex()<2:
            self._plot_tab_index=self.tabs.currentIndex()
        if hasattr(self,'layout_combo'):
            for workspace in self.workspaces:workspace.navigation_bar.setVisible(workspace is self.active_workspace)
            pane=self.active_workspace.active
            for widget,value in ((self.layout_combo,self.active_workspace.layout_name),(self.cursor_combo,pane.cursor_mode)):
                if widget is self.layout_combo and widget.findText(value)<0:widget.addItem(value)
                blocker=QtCore.QSignalBlocker(widget);widget.setCurrentIndex(widget.findData(value)) if widget is self.cursor_combo else widget.setCurrentText(value);del blocker
            blocker=QtCore.QSignalBlocker(self.snap_checkbox);self.snap_checkbox.setChecked(pane.snap);del blocker
        if hasattr(self,'compact'):self.compact.sync()
        self.sync_visibility();self.readouts()

    def show_dock(self,name):
        self.docks[name].show();self.docks[name].raise_()

    def sync_visibility(self):
        if hasattr(self,'portal'):self.portal.set_visible([id for p in self.active_workspace.visible_panes() for id in p.ids])

    def set_channel_visibility(self,ids,visible):
        self.mutate()
        try:self.active_workspace.set_visible(ids,visible)
        finally:self.sync_visibility()
        self._readouts()

    def closeEvent(self,event):
        if hasattr(self,'info') and not self.info.prepare_close():event.ignore();return
        self.exit_graph_fullscreen()
        self.generation+=1
        if hasattr(self,'engineering'):self.engineering.cancel_token.set();self.engineering.watch.stop()
        if hasattr(self,'studio'):self.studio.pause()
        self.theme.timer.stop();QtWidgets.QApplication.instance().removeEventFilter(self.theme)
        if self.busy:
            self.cancel_operation();self.statusBar().showMessage('Waiting for the current safe processing step before closing…');self.pool.waitForDone()
        for workspace in self.workspaces:workspace.close()
        self.readout_timer.stop()
        self.info_dialog.close();self.help_dialog.close()
        event.accept()


def run_workbench():
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion');from app_identity import apply_identity
    from app_lifecycle import prepare_user_data,finalize_installation
    prepare_user_data()
    apply_identity();window=AdvancedStudioWindow();window.showMaximized()
    startup_ready=True
    if '--restore' in sys.argv:
        index=sys.argv.index('--restore')
        if index+1<len(sys.argv):
            try:window.restore_path(sys.argv[index+1],upgrade_defaults=True)
            except Exception as exc:
                startup_ready=False
                if '--update-request' in sys.argv:
                    from app_update_transaction import acknowledge_startup
                    acknowledge_startup(False,str(exc),window=window);window.close();return 1
                window.guard(lambda:(_ for _ in ()).throw(ValueError(str(exc))))
    def startup_complete():
        from app_update_transaction import acknowledge_startup
        try:acknowledged=acknowledge_startup(startup_ready,window=window)
        except Exception as exc:
            from app_update_transaction import acknowledge_failure
            acknowledge_failure(str(exc));window.close();app.exit(1);return
        if acknowledged is False:
            window.close();app.exit(1);return
        if startup_ready and getattr(sys,'frozen',False) and sys.platform=='win32':
            window.background(finalize_installation,lambda _:None,title='Checking settings compatibility')
    # A running event loop and visible restored window are part of update
    # completion. Merely creating a child process cannot acknowledge success.
    QtCore.QTimer.singleShot(1500,startup_complete)
    return app.exec()

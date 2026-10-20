"""Progressively disclosed tools for the single Qt frontend."""
import json
from app_output import output_path
import time
from pathlib import Path
import numpy as np
import pandas as pd
from PySide6 import QtCore,QtGui,QtWidgets
from app_channel_store import Channel,ChannelStore
from app_trace_colors import channel_colors
from app_channel_identity import channel_label,channel_details
from app_compact_forms import ElidedComboBox,add_help,choose_item
from app_extensions import PluginManager
from app_studio_state import (STYLES,channel_preset,validate_preset,recorded_phases,export_full_workbook)


class PhaseStrip(QtWidgets.QWidget):
    seekRequested=QtCore.Signal(float)
    def __init__(self,spans,bounds,parent=None):
        super().__init__(parent);self.spans=spans;self.bounds=bounds;self.setMinimumHeight(42);self.setMouseTracking(True)
        self.setToolTip('Observed state/code intervals. Click to seek; no phase names are inferred.')
    def paintEvent(self,event):
        painter=QtGui.QPainter(self);low,high=self.bounds;span=max(high-low,1e-12)
        for i,record in enumerate(self.spans):
            left=(record['start']-low)/span*self.width();width=(record['end']-record['start'])/span*self.width()
            rect=QtCore.QRectF(left,0,max(width,1),self.height())
            painter.fillRect(rect,QtGui.QColor(('#3487bb','#9d77c8','#318a70','#b67e24')[i%4]))
            painter.setPen(QtGui.QColor('white'))
            if width>35:painter.drawText(rect,QtCore.Qt.AlignmentFlag.AlignCenter,record['label'])
    def mouseMoveEvent(self,event):
        low,high=self.bounds;point=low+(high-low)*event.position().x()/max(1,self.width())
        record=next((r for r in self.spans if r['start']<=point<=r['end']),None)
        self.setToolTip(f"{record['label']}: {record['start']:.6g}–{record['end']:.6g} {record['unit']} · duration {record['end']-record['start']:.6g} {record['unit']}" if record else 'No phase evidence at this time')
        super().mouseMoveEvent(event)

    def mousePressEvent(self,event):
        low,high=self.bounds;self.seekRequested.emit(low+(high-low)*np.clip(event.position().x()/max(1,self.width()),0,1))


class StudioTools(QtCore.QObject):
    def __init__(self,window):
        super().__init__(window);self.window=window;self.plugins=PluginManager();self.dialogs=[]
        self.reference_settings={};self.calibration={};self.bench_columns={};self.tolerances={}
        self.options={'title':'Signal analysis','show_grid':True,'show_legends':True,'font_size':9,'annotate_peak':False,'highlight_overlap':False}
        self.play_timer=QtCore.QTimer(self);self.play_timer.setInterval(50);self.play_timer.timeout.connect(self.tick)
        self.play_context=None;self.pending_preset=None
        self.build_menu();self.refresh_sync()
        if self.plugins.config.exists():
            try:self.plugins.reload();self.refresh_sync()
            except Exception as exc:window.statusBar().showMessage(f'Extensions could not load: {exc}')

    def build_menu(self):
        w=self.window;menu=w.menuBar().addMenu('Tools');self.menu=menu
        groups={'Data': [('Open simulation reference…',self.open_reference),('Import with coordinate settings…',self.import_settings),('Save channel preset…',self.save_preset),('Load channel preset…',self.load_preset),('Reset workspace',self.reset)],
                'Plot': [('Channel mapping & appearance…',self.channel_settings),('Display options…',self.display_options),('Playback & recorded phases…',self.playback),('Subsystem view…',self.subsystem),('Normalized stacked tracks',self.toggle_normalized),('Back',lambda:self.pane.navigate_history(-1)),('Forward',lambda:self.pane.navigate_history(1)),('Fit',lambda:self.window.active_workspace.navigate('reset')),('Zoom in',lambda:self.zoom(.8)),('Zoom out',lambda:self.zoom(1.25)),('Pan',lambda:self.navigation('pan')),('Zoom X',lambda:self.navigation('x')),('Zoom Y',lambda:self.navigation('y')),('Zoom XY',lambda:self.navigation('xy')),('Lock cursors to channel…',self.cursor_lock_dialog),('Move cursors…',self.cursor_positions),('Copy cursor readout',self.copy_readout)],
                'Processing': [('Channel math & filters',lambda:w.show_dock('Channel Math')),('Preview selected operation…',self.preview_processing)],
                'Engineering': [('Recording controls',lambda:w.show_dock('Engineering Controls')),('KPIs & data quality…',self.diagnostics),('Comparison signal mapping…',self.comparison_mapping),('Reference units…',self.reference_units),('Image reference calibration…',self.image_calibration),('Reference details…',self.reference_details)],
                'Export': [('Export All Diagnostic Tables as Excel…',self.export_workbook),('Export All Aligned Samples as CSV…',self.export_aligned_csv),('Export Selected or Active-Pane Channels…',self.export_channels),('Export Active Workspace as SVG / HTML / Markdown…',self.export_presentation)],
                'Extensions': [('Manage plugins…',self.extensions_dialog),('Run plot extensions…',self.plugin_plots)],
                'Examples': [('Load illustrative cycle into workspace',self.illustrative)]}
        self.submenus={};self.navigation_menu_actions={}
        navigation={'Fit':'reset','Zoom in':'in','Zoom out':'out','Pan':'pan','Zoom X':'x','Zoom Y':'y','Zoom XY':'xy'}
        for name,items in groups.items():
            submenu=menu.addMenu(name);self.submenus[name]=submenu
            for text,fn in items:
                display={'Zoom X':'Zoom Time Axis','Zoom Y':'Zoom Value Axes','Zoom XY':'Zoom Both Axes','Fit':'Reset View','Pan':'Pan Graph','Back':'Previous View','Forward':'Next View','KPIs & data quality…':'Measurements and Data Quality…','Channel math & filters':'Calculate Channels and Apply Filters','ROI':'Mark Interval'}.get(text,text)
                command=navigation.get(text) if name=='Plot' else None
                if command:
                    # A menu is another presentation of the graph's actual
                    # action, so mode checks and context-menu state cannot drift.
                    action=w.active_workspace.navigation_actions[command]
                    submenu.addAction(action);self.navigation_menu_actions[command]=action
                else:action=submenu.addAction(display)
                shortcut={'Back':'Alt+Left','Forward':'Alt+Right','Zoom in':'Ctrl+=','Zoom out':'Ctrl+-','Fit':'Ctrl+0','Pan':'Ctrl+4','Zoom X':'Ctrl+1','Zoom Y':'Ctrl+2','Zoom XY':'Ctrl+3','Lock cursors to channel…':'Ctrl+L'}.get(text)
                if shortcut:action.setShortcut(shortcut)
                if not command:action.triggered.connect(lambda checked=False,f=fn:w.guard(f))

        self._navigation_menu_owner=w.active_workspace
        w.tabs.currentChanged.connect(self.sync_navigation_menu)

        from app_version import VERSION
        about=menu.addAction(f'About version {VERSION}')
        about.triggered.connect(w.show_info)

    def sync_navigation_menu(self,*_):
        """Move menu references/shortcuts to the active graph, preserving order."""
        workspace=self.window.active_workspace
        if workspace is self._navigation_menu_owner:return
        shortcuts={'x':'Ctrl+1','y':'Ctrl+2','xy':'Ctrl+3','pan':'Ctrl+4',
                   'in':'Ctrl+=','out':'Ctrl+-','reset':'Ctrl+0'}
        menu=self.submenus['Plot']
        for command,old in tuple(self.navigation_menu_actions.items()):
            order=menu.actions();index=order.index(old)
            before=order[index+1] if index+1<len(order) else None
            old.setShortcut(QtGui.QKeySequence());menu.removeAction(old)
            action=workspace.navigation_actions[command]
            menu.insertAction(before,action) if before else menu.addAction(action)
            action.setShortcut(shortcuts[command]);self.navigation_menu_actions[command]=action
        self._navigation_menu_owner=workspace

    @property
    def pane(self):return self.window.active_workspace.active

    def dialog(self,title):
        from app_adaptive_ui import ContentDialog
        dialog=ContentDialog(self.window);dialog.setWindowTitle(title)
        dialog.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose);self.dialogs.append(dialog)
        dialog.destroyed.connect(lambda *_:self.dialogs.remove(dialog) if dialog in self.dialogs else None)
        layout=QtWidgets.QVBoxLayout(dialog);return dialog,layout

    def table_dialog(self,title,tables):
        from app_workbench import FrameModel
        dialog,layout=self.dialog(title);tabs=QtWidgets.QTabWidget();layout.addWidget(tabs)
        for name,frame in tables.items():
            view=QtWidgets.QTableView();view.setModel(FrameModel(frame))
            if 'accent' in frame:view.setColumnHidden(list(frame.columns).index('accent'),True)
            view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
            tabs.addTab(view,name)
        dialog.show();return dialog

    def state(self):
        return {'options':self.options,'reference_settings':self.reference_settings,'calibration':self.calibration,'bench_columns':self.bench_columns,'tolerances':self.tolerances,'pending_preset':self.pending_preset}

    def restore(self,state):
        self.pause()
        if self.play_context:self.play_context['dialog'].close()
        self.options={**self.options,**state.get('options',{})}
        for key in ('reference_settings','calibration','bench_columns','tolerances','pending_preset'):
            setattr(self,key,state.get(key,{} if key!='pending_preset' else None))
        self.apply_display()
        if hasattr(self.window,'compact'):self.window.compact.sync()

    def refresh_sync(self):
        from app_data import BUILTIN_SYNC_STRATEGIES
        value=self.window.sync.currentData() or self.window.sync.currentText();self.window.sync.clear()
        for strategy in [*BUILTIN_SYNC_STRATEGIES,*self.plugins.custom_sync_hooks]:
            self.window.sync.addItem('Manual time offset' if strategy.startswith('Manual') else strategy,strategy)
        self.select_sync(value)

    def select_sync(self,value):
        for index in range(self.window.sync.count()):
            if value in (self.window.sync.itemData(index),self.window.sync.itemText(index)):
                self.window.sync.setCurrentIndex(index);return True
        return False

    def import_settings(self):
        w=self.window;w.mutate();path,_=QtWidgets.QFileDialog.getOpenFileName(w,'Import recording')
        if not path:return
        from app_ingestion import read_tables,ingest
        frames=read_tables(path)
        if not frames:raise ValueError('No tables found')
        clock,ok=choose_item(w,'Coordinates','Coordinate column (first table)', ['Automatic','Sample index',*[str(c) for c in frames[0][1].columns]])
        if not ok:return
        unit,ok=choose_item(w,'Coordinates','Coordinate unit',['Auto','s','min','h','sample'])
        if not ok:return
        workspace=w.active_workspace
        def load():
            store=ChannelStore();ingest(store,path,None if clock in ('Automatic','Sample index') else clock,None if unit=='Auto' else unit,force_sample=clock=='Sample index');return store
        w.background(load,lambda store:w.finish_import(store,workspace))

    def open_reference(self):
        w=self.window;w.mutate();path,_=QtWidgets.QFileDialog.getOpenFileName(w,'Open simulation reference','','Reference (*.csv *.zip *.png *.jpg *.jpeg *.bmp *.tif *.tiff)')
        if not path:return
        from app_analysis_service import load_reference
        workspace=w.active_workspace;settings=dict(self.reference_settings);calibration=dict(self.calibration)
        w.simulation_path.setText(path);w.background(lambda:load_reference(path,settings,calibration),lambda store:w.merge_store(store,workspace))

    def live_readout(self,pane,position):
        from app_data import find_power_column,find_energy_column,get_column_unit,convert_signal_units
        from app_inspection import prepare_trace,sample_trace
        if not pane.coordinate or pane.coordinate[0]!='time':return ''
        dataset=next((d for d in reversed(list(self.window.store.datasets.values())) if d.frame.attrs.get('studio_sheet')=='Synchronized_Series'),None)
        if dataset is None or not any(self.window.store.channels[id].dataset_id==dataset.id for id in pane.ids):return ''
        frame=dataset.frame;unit=pane.coordinate[1];when=position/60 if unit=='s' else position*60 if unit=='h' else position
        parts=[]
        for column,target,label in ((find_power_column(frame.columns),'W','Power'),(find_energy_column(frame.columns),'Wh','Energy')):
            if column is None:continue
            key=(dataset.id,str(column),target)
            if not hasattr(self,'_live_traces'):self._live_traces={}
            if key not in self._live_traces:
                values=convert_signal_units(frame[column],get_column_unit(frame,column),target)
                self._live_traces[key]=prepare_trace(frame['relative_minutes'],values)
            value=sample_trace(self._live_traces[key],when)
            parts.append(f'{label} {value:.4g} {target}' if np.isfinite(value) else f'{label} —')
        return ' &nbsp; · &nbsp; '.join(parts)

    def save_preset(self):
        path,_=QtWidgets.QFileDialog.getSaveFileName(self.window,'Save reusable channel preset',str(output_path('Channel preset.json','presets')),'JSON (*.json)')
        if not path:return
        from app_support import atomic_output
        options={**self.options,'sync_strategy':self.window.sync.currentData() or self.window.sync.currentText(),'offset_minutes':self.window.offset.value()/60.,'reference_settings':self.reference_settings,'calibration':self.calibration,'bench_columns':self.bench_columns}
        record=channel_preset(self.window.store,self.window.active_workspace,options)
        with atomic_output(path) as temporary:Path(temporary).write_text(json.dumps(record,indent=2,allow_nan=False),encoding='utf-8')

    def load_preset(self):
        path,_=QtWidgets.QFileDialog.getOpenFileName(self.window,'Load channel preset','','Configurations (*.json *.xml *.ini *.cfg)')
        if path:
            from app_config_migration import read_configuration
            self.apply_preset(read_configuration(path))

    def apply_preset(self,record):
        from app_config_migration import migrate_configuration
        record=migrate_configuration(record)
        w=self.window;w.mutate();signals,options=validate_preset(record)
        if not w.store.channels:self.pending_preset=record;w.statusBar().showMessage('Preset validated; import data to apply it.');return 0
        changes=[];panels={};matched=0
        for c in w.store.channels.values():
            source=c.attributes.get('source_column',c.name)
            candidates=[value for key,value in signals.items() if (value.get('source_col',key)==source or key==c.name) and (not value.get('source_path') or not c.source or Path(value['source_path']).name==Path(c.source).name)]
            if len(candidates)!=1:continue
            entry=candidates[0];style={'color':entry.get('color','#58b6ff'),'width':float(entry.get('width',1)),'style':STYLES.get(entry.get('style'),entry.get('style','solid')),'side':'right' if entry.get('twin',False) else 'left','ymin':entry.get('ymin',''),'ymax':entry.get('ymax','')}
            from app_actuators import interpret_channel
            from dataclasses import replace
            attrs={**c.attributes,'plot_style':style}
            if entry.get('unit',c.unit)!=c.unit:attrs['raw_unit']=entry['unit']
            updated=interpret_channel(replace(c,attributes=attrs),entry.get('value_interpretation',c.attributes.get('value_interpretation','auto')))
            changes.append((c.id,dict(name=entry.get('name',c.name),unit=updated.unit if updated.attributes.get('actuator_binary') else entry.get('unit',updated.unit),kind=updated.kind,y=updated.y,raw_y=updated.raw_y,attributes=updated.attributes)));matched+=1
            if entry.get('enabled',True):panels.setdefault(int(entry.get('panel','Panel 1').split()[-1])-1,[]).append(c.id)
        with w.store.batch():
            for id,change in changes:w.store.update(id,**change)
        self.options={**self.options,**{k:v for k,v in options.items() if k in self.options}}
        for key in ('reference_settings','calibration','bench_columns'):
            if key in options:setattr(self,key,options[key])
        if 'offset_minutes' in options:w.offset.setValue(float(options['offset_minutes'])*60)
        if 'sync_strategy' in options:self.select_sync(options['sync_strategy'])
        if panels:
            workspace=w.active_workspace;count=max(panels)+1
            workspace.set_layout('Single' if count==1 else 'Horizontal split' if count==2 else '2×2' if count<=4 else '10 panels')
            for i,pane in enumerate(workspace.panes):pane.bind(panels.get(i,[]))
            workspace.link()
        self.pending_preset=None;self.apply_display();w._readouts();w.statusBar().showMessage(f'Applied settings to {matched} channels. Unmatched channels were retained.')
        return matched

    def channel_settings(self):
        w=self.window
        if not w.store.channels:raise ValueError('Load data before configuring channels')
        dialog,layout=self.dialog('Channel mapping & appearance');table=QtWidgets.QTableWidget(0,10)
        table.setHorizontalHeaderLabels(['Show','Source / channel','Label','Unit','Panel','Right axis','Style','Width','Color','Y bounds (min,max)']);layout.addWidget(table)
        entries=[];visible={id for p in w.active_workspace.visible_panes() for id in p.ids};colors=channel_colors(w.store)
        for row,c in enumerate(w.store.channels.values()):
            table.insertRow(row);style=c.attributes.get('plot_style',{})
            show=QtWidgets.QCheckBox();show.setChecked(c.id in visible);table.setCellWidget(row,0,show)
            original=QtWidgets.QTableWidgetItem(channel_label(w.store,c,include_source=True));original.setToolTip(channel_details(w.store,c));original.setFlags(original.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable);table.setItem(row,1,original)
            for col,value in ((2,c.name),(3,c.unit),(7,str(style.get('width',1))),(8,colors[c.id]),(9,f"{style.get('ymin','')},{style.get('ymax','')}")):table.setItem(row,col,QtWidgets.QTableWidgetItem(value))
            panel=QtWidgets.QComboBox();panel.addItems([f'Panel {i}' for i in range(1,11)]);panel.setCurrentIndex(next((i for i,p in enumerate(w.active_workspace.panes) if c.id in p.ids),0));table.setCellWidget(row,4,panel)
            right=QtWidgets.QCheckBox();right.setChecked(style.get('side')=='right');table.setCellWidget(row,5,right)
            pattern=QtWidgets.QComboBox();pattern.addItems(list(STYLES));pattern.setCurrentIndex(list(STYLES.values()).index(style.get('style','solid')));table.setCellWidget(row,6,pattern)
            entries.append((c,row,show,panel,right,pattern))
        table.cellDoubleClicked.connect(lambda row,col:self.pick_color(table,row,col) if col==8 else None)
        apply=QtWidgets.QPushButton('Apply to workspace');layout.addWidget(apply)
        def save():
            signals={}
            for c,row,show,panel,right,pattern in entries:
                bounds=table.item(row,9).text().split(',')
                if len(bounds)!=2:raise ValueError('Y bounds must be min,max; leave both empty for auto')
                signals[c.id]={'source_col':c.attributes.get('source_column',c.name),'source_path':c.source,'name':table.item(row,2).text(),'unit':table.item(row,3).text(),'enabled':show.isChecked(),'panel':panel.currentText(),'twin':right.isChecked(),'style':pattern.currentText(),'width':table.item(row,7).text(),'color':table.item(row,8).text(),'ymin':bounds[0].strip(),'ymax':bounds[1].strip()}
            # Stable IDs disambiguate identical source columns within the current session.
            self.apply_channel_entries(signals);dialog.accept()
        apply.clicked.connect(lambda:w.guard(save));dialog.show();return dialog

    def apply_channel_entries(self,signals):
        validate_preset({'version':3,'signals':signals});w=self.window;w.mutate();panels={}
        with w.store.batch():
            for id,entry in signals.items():
                c=w.store.channels[id];attrs={**c.attributes,'plot_style':{'color':entry['color'],'width':float(entry['width']),'style':STYLES.get(entry['style'],entry['style']),'side':'right' if entry['twin'] else 'left','ymin':entry['ymin'],'ymax':entry['ymax']}}
                w.store.update(id,name=entry['name'],unit=entry['unit'],attributes=attrs)
                if entry['enabled']:panels.setdefault(int(entry['panel'].split()[-1])-1,[]).append(id)
        count=max(panels,default=0)+1;workspace=w.active_workspace
        workspace.set_layout('Single' if count==1 else 'Horizontal split' if count==2 else '2×2' if count<=4 else '10 panels')
        for i,pane in enumerate(workspace.panes):pane.bind(panels.get(i,[]))
        workspace.link();w._readouts()

    def pick_color(self,table,row,col):
        color=QtWidgets.QColorDialog.getColor(QtGui.QColor(table.item(row,col).text()),self.window)
        if color.isValid():table.item(row,col).setText(color.name())

    def preview_processing(self):
        w=self.window;ids=w.portal.selected()
        if len(ids)!=1:raise ValueError('Select one source channel in the channel list')
        from app_signal_processing import transform
        source=w.store.channels[ids[0]];workspace=w.active_workspace
        operation=w.operation.currentText();parameters={key:field.value() for key,field in w.parameter_fields.items()}
        def complete(result):
            from app_plot_workspace import PlotWorkspace
            dialog,layout=self.dialog('Processing result — not yet applied');store=ChannelStore();store.add(result)
            source_row=QtWidgets.QFormLayout();source_name=QtWidgets.QLineEdit(channel_label(w.store,source,include_source=True));source_name.setReadOnly(True)
            source_name.setToolTip(channel_details(w.store,source));source_name.setAccessibleDescription(channel_details(w.store,source));source_row.addRow('Source',source_name);layout.addLayout(source_row)
            plot=PlotWorkspace(store);plot.assign([result.id]);layout.addWidget(plot)
            summary=QtWidgets.QLabel(f'{len(result.x):,} calculated samples · not yet added');layout.addWidget(summary)
            add_help(layout,f'Source: {channel_label(w.store,source,include_source=True)}\n{channel_details(w.store,source)}\nOriginal data remains unchanged until Apply to workspace is chosen.')
            apply=QtWidgets.QPushButton('Apply to workspace');layout.addWidget(apply)
            def save():
                w.mutate()
                if w.store.channels.get(source.id) is not source:raise ValueError('Source changed; preview the operation again')
                w.store.add(result);workspace.assign([result.id]);dialog.accept()
            apply.clicked.connect(lambda:w.guard(save));dialog.show()
        w.background(lambda:transform(source,operation,**parameters),complete)

    def display_options(self):
        self.options={**self.options,**getattr(self.window.active_workspace,'display_options',{})}
        for workspace in self.window.workspaces:
            if not getattr(workspace,'display_options',None):workspace.display_options=dict(self.options)
        dialog,layout=self.dialog('Plot display options');form=QtWidgets.QFormLayout();layout.addLayout(form)
        title=QtWidgets.QLineEdit(self.options['title']);form.addRow('Report / plot title',title)
        font=QtWidgets.QSpinBox();font.setRange(7,20);font.setValue(int(self.options['font_size']));form.addRow('Plot font size',font);checks={}
        for key,label in [('show_grid','Grid'),('show_legends','Legends'),('annotate_peak','Peak power marker'),('highlight_overlap','Inlet / drain overlap')]:
            check=QtWidgets.QCheckBox(label);check.setChecked(self.options[key]);form.addRow(check);checks[key]=check
        apply=QtWidgets.QPushButton('Apply');layout.addWidget(apply)
        def save():
            self.options.update(title=title.text(),font_size=font.value(),**{key:check.isChecked() for key,check in checks.items()});self.window.active_workspace.display_options=dict(self.options);self.apply_display([self.window.active_workspace],rebind=False);dialog.accept()
        apply.clicked.connect(lambda:self.window.guard(save))
        for check in checks.values():check.toggled.connect(lambda *_:save_live())
        def save_live():
            self.options.update(title=title.text(),font_size=font.value(),**{key:check.isChecked() for key,check in checks.items()});self.window.active_workspace.display_options=dict(self.options);self.apply_display([self.window.active_workspace],rebind=False)
        title.editingFinished.connect(save_live);font.valueChanged.connect(lambda *_:save_live())
        dialog.show();return dialog

    def apply_display(self,workspaces=None,rebind=True):
        w=self.window
        for workspace in (workspaces or w.workspaces):
            options={**self.options,**getattr(workspace,'display_options',{})}
            for pane in workspace.panes:
                pane.show_grid=options['show_grid'];pane.show_legends=options['show_legends']
                pane.getPlotItem().setTitle(options['title']);font=QtGui.QFont();font.setPointSize(int(options['font_size']))
                for axis in [pane.getAxis('left'),pane.getAxis('bottom'),*[a for a,_ in pane.axes.values()]]:axis.setStyle(tickFont=font)
                if rebind:pane.bind(pane.ids,pane.bindings,fit=False)
                else:
                    pane.showGrid(x=pane.show_grid,y=pane.show_grid,alpha=.2);pane.legend.setVisible(pane.show_legends and bool(pane.ids) and len(pane.ids)<=12)
                pane.annotations=[a for a in pane.annotations if not a.get('studio_generated')]
                for vb,item in pane.annotation_items:vb.removeItem(item)
                pane.annotation_items=[]
                for record in pane.annotations:pane._annotation(record)
                if options['annotate_peak']:
                    power=next((w.store.channels[id] for id in pane.ids if w.store.channels[id].unit in ('W','kW') and len(w.store.channels[id].x)),None)
                    if power:
                        x,y=power.values()
                        if np.isfinite(y).any():
                            record={'kind':'Marker','start':float(x[np.nanargmax(y)]),'end':0.,'text':'Peak power','axis':None,'studio_generated':True};pane.annotations.append(record);pane._annotation(record)
                if options['highlight_overlap']:self.highlight_overlap(pane)

        for workspace in (workspaces or w.workspaces):workspace.update_channel_legend()
        if hasattr(w,'compact'):w.compact.sync()

    def highlight_overlap(self,pane):
        from app_channel_store import Channel
        channels=[self.window.store.channels[id] for id in pane.ids]
        drain=next((c for c in channels if 'drain' in c.name.lower()),None)
        inlets=[c for c in channels if any(k in c.name.lower() for k in ('inlet','pre-wash','main wash','out vavle'))]
        if drain is None or not inlets:return
        x,y=drain.values()
        known_inlet=np.zeros(len(x),dtype=bool)
        for channel in inlets:
            cx,cy=channel.values()
            if not len(cx):continue
            indices=np.searchsorted(cx,x,side='right')-1
            valid=(indices>=0)&(x<=cx[-1]);indices=np.clip(indices,0,len(cx)-1)
            known_inlet|=valid&np.isfinite(cy[indices])&(cy[indices]>0)
        active=(np.isfinite(y)&(y>0)&known_inlet)[:-1]
        transitions=np.diff(np.r_[False,active,False].astype(int));starts=np.flatnonzero(transitions==1);ends=np.flatnonzero(transitions==-1)
        for start,end in zip(starts,ends):
            pane.annotations.append({'kind':'Mark interval','start':float(x[start]),'end':float(x[end]),'text':'Inlet / drain overlap','axis':None,'studio_generated':True})
        for record in pane.annotations:
            if record.get('text')=='Inlet / drain overlap':pane._annotation(record)

    def add_plot_note(self):
        self.window.mutate()
        if not self.pane.ids:raise ValueError('Select a channel before adding a note')
        point=self.pane.cursor_lines[0].value()
        text,ok=QtWidgets.QInputDialog.getText(self.window,'Add plot note',f'Note at cursor A ({point:.6g} {self.pane.coordinate[1]}):')
        if ok and text.strip():self.pane.annotate('Marker',point,text=text.strip())

    def zoom(self,factor):
        self.window.active_workspace.navigate('in' if factor<1 else 'out',factor)

    def navigation(self,mode):
        self.window.active_workspace.navigate(mode)

    def cursor_lock_dialog(self):
        pane=self.pane;dialog,layout=self.dialog('Lock cursors to channel');form=QtWidgets.QFormLayout();layout.addLayout(form);fields=[]
        for index,name in enumerate(('A','B')):
            field=ElidedComboBox();field.setAccessibleName('Cursor '+name+' source channel');field.addItem('Unlocked',None)
            for id in pane.ids:field.addItem(channel_label(self.window.store,id),id,channel_details(self.window.store,id))
            lock=pane.cursor_locks[index]
            if lock:field.setCurrentIndex(max(0,field.findData(lock['channel'])))
            form.addRow('Cursor '+name,field);fields.append(field)
        add_help(layout,'Locked cursors stay on real source samples while panning. Drag to scrub; ←/→ steps Cursor A, Shift+←/→ steps Cursor B. Other channels update at that time. The matching locked value and source are shown in Readout. Choose Unlocked to release a cursor.')
        apply=QtWidgets.QPushButton('Apply');layout.addWidget(apply)
        def save():
            for index,field in enumerate(fields):pane.lock_cursor(index,field.currentData())
            dialog.accept()
        apply.clicked.connect(lambda:self.window.guard(save));dialog.show();return dialog

    def cursor_positions(self):
        dialog,layout=self.dialog('Move cursors');form=QtWidgets.QFormLayout();layout.addLayout(form);fields=[]
        for name,line in zip(('A','B'),self.pane.cursor_lines):
            spin=QtWidgets.QDoubleSpinBox();spin.setRange(-1e15,1e15);spin.setDecimals(8);spin.setValue(line.value());form.addRow(name,spin);fields.append(spin)
        for label,index,which in [('A start',0,0),('A end',0,1),('B start',1,0),('B end',1,1)]:
            button=QtWidgets.QPushButton(label);layout.addWidget(button);button.clicked.connect(lambda checked=False,i=index,k=which:fields[i].setValue(self.bounds(self.pane)[k]))
        apply=QtWidgets.QPushButton('Move');layout.addWidget(apply)
        apply.clicked.connect(lambda:([line.setValue(field.value()) for line,field in zip(self.pane.cursor_lines,fields)],dialog.accept()));dialog.show()

    def copy_readout(self):
        w=self.window;w._readouts();columns=w.readout.columnCount()
        rows=[[w.readout.horizontalHeaderItem(col).text() for col in range(columns)]]
        for row in range(w.readout.rowCount()):rows.append([w.readout.item(row,col).text() if w.readout.item(row,col) else '' for col in range(columns)])
        QtWidgets.QApplication.clipboard().setText('\n'.join('\t'.join(row) for row in rows))

    def toggle_normalized(self):
        pane=self.pane
        if not pane.normalized:pane.normalization_bindings=dict(pane.bindings)
        pane.normalized=not pane.normalized;pane.bind(pane.ids,pane.normalization_bindings if not pane.normalized else {});self.window._readouts()

    def subsystem(self):
        name,ok=QtWidgets.QInputDialog.getItem(self.window,'Subsystem','Show',['All','Thermal','Mechanical','Water / valves','Controller'],0,False)
        if not ok:return
        words={'Thermal':('temp','heat','power'),'Mechanical':('drum','drump','rpm','speed','motor'),'Water / valves':('water','pressure','inlet','valve','drain','pump'),'Controller':('stwf','stage','code','state','remain')}
        ids=[c.id for c in self.window.store.channels.values() if name=='All' or any(k in c.name.lower() for k in words[name])]
        workspace=self.window.active_workspace
        for pane in workspace.panes:pane.bind([])
        if ids:workspace.assign(ids)
        self.window._readouts()

    def bounds(self,pane):
        channels=[self.window.store.channels[id] for id in pane.ids if len(self.window.store.channels[id].x)]
        if not channels:raise ValueError('Select nonempty channels first')
        return min(c.x[0]+c.shift for c in channels),max(c.x[-1]+c.shift for c in channels)

    def seek(self,point):
        pane=self.play_context['pane'] if self.play_context else self.pane;low,high=self.bounds(pane);point=float(np.clip(point,low,high))
        left,right=pane.getViewBox().viewRange()[0]
        if not left<=point<=right:
            width=max(right-left,(high-low)/10);pane.setXRange(max(low,point-width*.4),min(high,point+width*.6),padding=0)
        pane.cursor_lines[0].setValue(point)
        if self.play_context:
            self.play_context['position']=point
            blocker=QtCore.QSignalBlocker(self.play_context['slider']);self.play_context['slider'].setValue(round((point-low)/max(high-low,1e-12)*1000));del blocker
            self.play_context['label'].setText(f'{point:.6g} {pane.coordinate[1]}')

    def playback(self):
        return self.window.compact.playback()

    def tick(self):
        if not self.play_context:self.pause();return
        pane=self.play_context['pane']
        if pane not in [p for workspace in self.window.workspaces for p in workspace.panes]:self.pause();return
        elapsed=time.monotonic()-self._last_tick;self._last_tick=time.monotonic();unit=pane.coordinate[1] if pane.coordinate else 's';factor=60 if unit=='min' else 3600 if unit=='h' else 1
        point=pane.cursor_lines[0].value()+elapsed*self.play_context['speed'].value()/factor
        # Accumulate continuous playback time; snapping must not stall on sparse samples.
        point=max(point,self.play_context.get('position',pane.cursor_lines[0].value())+elapsed*self.play_context['speed'].value()/factor)
        self.play_context['position']=point;self.seek(point)
        if point>=self.bounds(pane)[1]:self.pause()

    def pause(self):
        self.play_timer.stop()
        if self.play_context:
            try:self.play_context['button'].setText('Play');self.play_context.pop('position',None)
            except RuntimeError:pass

    def close_playback(self,dialog):
        if self.play_context and self.play_context['dialog'] is dialog:self.pause();self.play_context=None

    def diagnostics(self):
        from app_analysis_service import quality_frame
        tables={d.name:d.frame for d in self.window.store.datasets.values() if d.frame.attrs.get('studio_sheet') in ('Summary_KPIs','Data_Quality','Report_Info','Comparison_Info','Bench_Data_Quality')}
        if not tables:tables={d.name:quality_frame(d.frame) for d in self.window.store.datasets.values()}
        if not tables and self.window.store.channels:
            tables={'Channel quality':pd.DataFrame([{'Channel':c.name,'Samples':len(c.y),'Missing / non-finite':int((~np.isfinite(c.y)).sum()),'Unit':c.unit} for c in self.window.store.channels.values()])}
        if not tables:raise ValueError('Load or align data first')
        return self.table_dialog('Engineering KPIs, quality & synchronization',tables)

    def comparison_mapping(self):
        from app_data import smart_read_file
        from app_simulation import CSV_LEGEND_SPECS
        frame=smart_read_file(self.window.machine_path.text())
        if frame.empty:raise ValueError('Choose a bench recording in Engineering Controls first')
        dialog,layout=self.dialog('Simulation ↔ bench signal mapping');form=QtWidgets.QFormLayout();layout.addLayout(form);fields={}
        for spec in CSV_LEGEND_SPECS:
            field=ElidedComboBox();field.addItems(['Auto','None',*[str(c) for c in frame.columns]])
            value=self.bench_columns.get(spec['key'],'Auto');field.setCurrentText('None' if value is None else value);form.addRow(spec['label'],field);fields[spec['key']]=field
        apply=QtWidgets.QPushButton('Apply mapping');layout.addWidget(apply)
        def save():
            self.bench_columns={k:None if f.currentText()=='None' else f.currentText() for k,f in fields.items() if f.currentText()!='Auto'};dialog.accept()
        apply.clicked.connect(save);dialog.show();return dialog

    def reference_units(self):
        dialog,layout=self.dialog('Reference units');form=QtWidgets.QFormLayout();layout.addLayout(form);fields={}
        for key,label,values in [('time_unit','Numeric time unit',['min','s','h']),('pressure_unit','Source pressure metadata',['unknown','Pa','mbar','bar','kPa']),('remaining_time_unit','Remaining time unit',['min','s'])]:
            field=ElidedComboBox();field.addItems(values);field.setCurrentText(self.reference_settings.get(key,values[0]));form.addRow(label,field);fields[key]=field
        add_help(layout,'Choose the units recorded in the source metadata. These settings describe the imported values; changing metadata does not rescale measurements. Physical conversion requires a verified source unit and calibration. Unknown units remain unknown.')
        apply=QtWidgets.QPushButton('Apply');layout.addWidget(apply);apply.clicked.connect(lambda:(self.reference_settings.update({k:f.currentText() for k,f in fields.items()}),dialog.accept()));dialog.show();return dialog

    def image_calibration(self):
        from app_reference_image import SimulationImageAnalyzer,SIMULATION_LEGEND_SPECS
        path=self.window.simulation_path.text()
        if Path(path).suffix.lower() not in ('.png','.jpg','.jpeg','.bmp','.tif','.tiff'):
            path,_=QtWidgets.QFileDialog.getOpenFileName(self.window,'Choose simulation image','','Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff)')
            if not path:return
        analyzer=SimulationImageAnalyzer(path,calibration=self.calibration)
        dialog,layout=self.dialog('Image reference calibration');form=QtWidgets.QFormLayout();layout.addLayout(form)
        duration=QtWidgets.QDoubleSpinBox();duration.setRange(.000001,1e7);duration.setDecimals(6);duration.setValue(analyzer.duration_min);form.addRow('Duration (minutes)',duration)
        height=QtWidgets.QDoubleSpinBox();height.setRange(1,100000);height.setValue(analyzer.reference_height);form.addRow('Reference height (pixels)',height)
        bounds=QtWidgets.QLineEdit(','.join(map(str,self.calibration.get('plot_bounds',[]))));form.addRow('Plot bounds left,right,top,bottom (blank = auto)',bounds)
        time_verified=QtWidgets.QCheckBox('Time ticks verified');time_verified.setChecked(self.calibration.get('time_verified',False));form.addRow(time_verified)
        image=QtWidgets.QLabel();pixmap=QtGui.QPixmap(path);image.setPixmap(pixmap.scaled(600,160,QtCore.Qt.AspectRatioMode.KeepAspectRatio));image.setMinimumWidth(0);image.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,QtWidgets.QSizePolicy.Policy.Preferred);layout.addWidget(image)
        table=QtWidgets.QTableWidget(len(SIMULATION_LEGEND_SPECS),6);table.setHorizontalHeaderLabels(['Signal','Tick 1 px','Value 1','Tick 2 px','Value 2','Verified']);layout.addWidget(table);checks={}
        verified=self.calibration.get('axis_verified',False)
        for row,spec in enumerate(SIMULATION_LEGEND_SPECS):
            item=QtWidgets.QTableWidgetItem(spec['label']);item.setFlags(item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable);table.setItem(row,0,item)
            points=self.calibration.get('axis_calibration',{}).get(spec['key'],spec['axis_calibration'])
            for col,value in enumerate(points,1):table.setItem(row,col,QtWidgets.QTableWidgetItem(str(value)))
            check=QtWidgets.QCheckBox();check.setChecked(verified.get(spec['key'],False) if isinstance(verified,dict) else verified);table.setCellWidget(row,5,check);checks[spec['key']]=check
        apply=QtWidgets.QPushButton('Apply calibration');layout.addWidget(apply)
        def save():
            proposed={'duration_min':duration.value(),'reference_height':height.value(),'time_verified':time_verified.isChecked(),'axis_verified':{key:field.isChecked() for key,field in checks.items()},'axis_calibration':{spec['key']:[float(table.item(row,col).text()) for col in range(1,5)] for row,spec in enumerate(SIMULATION_LEGEND_SPECS)}}
            if bounds.text().strip():proposed['plot_bounds']=[int(v.strip()) for v in bounds.text().split(',')]
            SimulationImageAnalyzer(path,calibration=proposed);self.calibration=proposed;self.window.simulation_path.setText(path);dialog.accept()
        apply.clicked.connect(lambda:self.window.guard(save));dialog.show();return dialog

    def reference_details(self):
        tables={d.name:d.frame for d in self.window.store.datasets.values() if d.frame.attrs.get('studio_sheet') in ('CSV_Trace_Quality','CSV_Units','Image_Trace_Quality','Image_Calibration','Package_Files','Package_Metadata')}
        if not tables:raise ValueError('Run comparison to inspect its reference and package details')
        return self.table_dialog('Reference quality & package metadata',tables)

    def export_workbook(self):
        path,_=QtWidgets.QFileDialog.getSaveFileName(self.window,'Export complete diagnostic workbook',str(output_path('Diagnostics.xlsx','diagnostics')),'Excel (*.xlsx)')
        if path:export_full_workbook(path,self.window.store,self.window.active_workspace.state(),getattr(self.window,'scorecard_data',None))

    def export_aligned_csv(self):
        dataset=next((d for d in reversed(list(self.window.store.datasets.values())) if d.frame.attrs.get('studio_sheet')=='Synchronized_Series'),None)
        if dataset is None:raise ValueError('Align recordings first')
        path,_=QtWidgets.QFileDialog.getSaveFileName(self.window,'Export complete synchronized series',str(output_path('Synchronized.csv')),'CSV (*.csv)')
        if path:
            from app_support import atomic_output
            with atomic_output(path) as temporary:dataset.frame.to_csv(temporary,index=False)

    def export_channels(self):
        from app_workspace_io import export_processed
        selected=self.window.portal.selected();ids=selected or self.pane.ids
        if not ids:raise ValueError('Select channels first')
        scope='selected in Data Portal' if selected else 'in active graph pane'
        path,_=QtWidgets.QFileDialog.getSaveFileName(self.window,f'Export all samples — {len(ids)} channels {scope}',str(output_path('Processed channels.csv')),'CSV samples (*.csv);;Excel samples (*.xlsx)')
        if path:export_processed(path,[self.window.store.channels[id] for id in ids])

    def export_presentation(self):
        from app_workspace_io import render_report
        path,_=QtWidgets.QFileDialog.getSaveFileName(self.window,'Export presentation',str(output_path('Presentation.svg')),'SVG (*.svg);;HTML (*.html);;Markdown (*.md)')
        if path:render_report(path,self.window.store,self.window.active_workspace.state(),title=self.options['title'])

    def extensions_dialog(self):
        self.window.mutate();dialog,layout=self.dialog('Extensions')
        add_help(layout,'Python extensions run local code and use register_patch(manager). Install only extensions you trust. Extension files and any loading errors remain visible in the table.')
        table=QtWidgets.QTableWidget(0,3);table.setHorizontalHeaderLabels(['Enabled','File','Description / error']);layout.addWidget(table)
        def refresh():
            errors=self.plugins.reload();self.refresh_sync();table.blockSignals(True);table.setRowCount(0)
            for row,name in enumerate(self.plugins.files()):
                table.insertRow(row);item=QtWidgets.QTableWidgetItem();item.setFlags(item.flags()|QtCore.Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(QtCore.Qt.CheckState.Checked if self.plugins.patch_states.get(name,True) else QtCore.Qt.CheckState.Unchecked);table.setItem(row,0,item)
                table.setItem(row,1,QtWidgets.QTableWidgetItem(name));table.setItem(row,2,QtWidgets.QTableWidgetItem(errors.get(name,self.plugins.patch_descriptions.get(name,''))))
            table.blockSignals(False)
        def toggle(item):
            if item.column()==0:self.plugins.set_enabled(table.item(item.row(),1).text(),item.checkState()==QtCore.Qt.CheckState.Checked);refresh()
        table.itemChanged.connect(lambda item:self.window.guard(lambda:toggle(item)))
        row=QtWidgets.QHBoxLayout();layout.addLayout(row)
        def install():
            path,_=QtWidgets.QFileDialog.getOpenFileName(dialog,'Install Python extension','','Python (*.py)')
            if path:self.plugins.install(path);refresh()
        def remove():
            selected=table.currentRow()
            if selected<0:return
            name=table.item(selected,1).text()
            if QtWidgets.QMessageBox.question(dialog,'Remove extension',f'Remove {name}?')==QtWidgets.QMessageBox.StandardButton.Yes:self.plugins.remove(name);refresh()
        for title,fn in [('Install…',install),('Remove',remove),('Reload',refresh),('Open folder',lambda:QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.plugins.directory))))]:
            button=QtWidgets.QPushButton(title);row.addWidget(button);button.clicked.connect(lambda checked=False,f=fn:self.window.guard(f))
        refresh();dialog.show();return dialog

    def plugin_plots(self):
        if not self.plugins.custom_plot_hooks:raise ValueError('No plot extensions are enabled')
        frame=next((d.frame for d in reversed(list(self.window.store.datasets.values())) if d.frame.attrs.get('studio_sheet')=='Synchronized_Series'),None)
        if frame is None:raise ValueError('Align a recording before running plot extensions')
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        fig=Figure();workspace=self.window.active_workspace
        from app_plot_workspace import LAYOUTS
        rows,cols=LAYOUTS[workspace.layout_name];axes=list(fig.subplots(rows,cols,squeeze=False).flat)
        for axis,pane in zip(axes,workspace.visible_panes()):
            for id in pane.ids:
                c=self.window.store.channels[id];x,y=c.values();axis.plot(x,y,label=channel_label(self.window.store,c))
            if pane.ids:axis.legend(fontsize=7)
        for hook in self.plugins.custom_plot_hooks:hook(fig,axes,frame.copy(deep=True))
        dialog,layout=self.dialog('Extension plot');canvas=FigureCanvasQTAgg(fig);layout.addWidget(canvas);canvas.draw()
        save=QtWidgets.QPushButton('Export plot');layout.addWidget(save)
        def export():
            path,_=QtWidgets.QFileDialog.getSaveFileName(dialog,'Save extension plot',str(output_path('Extension plot.png')),'PNG (*.png);;PDF (*.pdf);;SVG (*.svg)')
            if path:fig.savefig(path,dpi=300)
        save.clicked.connect(lambda:self.window.guard(export));dialog.show();return dialog

    def illustrative(self):
        from app_studio_examples import demo_signals
        from app_channel_store import Dataset
        w=self.window;w.mutate();other=ChannelStore();ds=Dataset('Illustrative cycle — synthetic',pd.DataFrame(),source='synthetic');ds.frame.attrs['illustrative']=True;other.datasets[ds.id]=ds
        for signal in demo_signals():
            x,y,kind=signal.trace;other.add(Channel(signal.label,x,y,unit=signal.unit,kind='analog' if kind=='analog' else 'discrete',coordinate_unit='min',dataset_id=ds.id,source='synthetic',attributes={'illustrative':True,'signal_kind':kind,'parameter':signal.key}))
        w.merge_store(other);w.statusBar().showMessage('Illustrative synthetic cycle — not measured data.')

    def reset(self):
        w=self.window;w.mutate();self.pause()
        if w.store.channels and QtWidgets.QMessageBox.question(w,'Reset workspace','Clear loaded data and plots? Saved files are kept.')!=QtWidgets.QMessageBox.StandardButton.Yes:return
        w.generation+=1;w.store=ChannelStore();w.portal.store=w.store;w.store.observe(w.store_changed)
        for workspace in w.workspaces:
            workspace.store=w.store;workspace.restore({'layout':'Single','panes':[{'ids':[]}],'active':0})
        w.scorecard_data=None;self.bench_columns={};self._live_traces={}
        for field in (w.power_path,w.machine_path,w.simulation_path):field.clear()
        from app_workbench import FrameModel
        w.scorecard.setModel(FrameModel());w.engineering_notes.clear();w.store_changed(set())

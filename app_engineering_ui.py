"""Engineering configuration/results integrated into the existing Qt workbench."""
import copy
import json
import threading
from pathlib import Path
import numpy as np
import pandas as pd
from PySide6 import QtCore,QtGui,QtWidgets
import pyqtgraph as pg
from app_appliance_profiles import load_profile,recognize,validate_profile,channel_key
from app_engineering_session import default_session,validate_session,analyze_session
from app_engineering_analytics import reviewed_mapping_rows
from app_output import output_path
from app_studio_tools import PhaseStrip


class EngineeringTools(QtCore.QObject):
    def __init__(self,window):
        super().__init__(window);self.w=window;self.session=default_session()
        from app_engineering_templates import MappingTemplates
        self.templates=MappingTemplates();self.session['mappings']=self.templates.get(self.session['profile']);self.session['source_units']=self.templates.get_units(self.session['profile'])
        self.result=None;self.cancel_token=threading.Event();self.overlays=[];self.projection_ids=[]
        # Use the spare right side of the existing upper navigation row.
        # Both workspaces share these session actions; only the active row shows.
        actions=[]
        for text,fn in [('Engineering Setup',self.configure),('Analyze Engineering Data',self.analyze),('Generate Engineering Report',self.report)]:
            action=QtGui.QAction(text,self);action.setToolTip(text);action.triggered.connect(lambda _,f=fn:window.guard(f));actions.append(action)
            window.studio.submenus['Engineering'].addAction(action)
        self.operation_actions=actions
        self.cancel_action=QtGui.QAction('Cancel Engineering Task',self);self.cancel_action.setToolTip('Cancel analysis/report; keep the last valid workspace and output');self.cancel_action.setEnabled(False);self.cancel_action.triggered.connect(lambda:self.cancel_token.set())
        cancel_button=QtWidgets.QToolButton();cancel_button.setDefaultAction(self.cancel_action);window.statusBar().addPermanentWidget(cancel_button)
        self.result_action=window.studio.submenus['Engineering'].addAction('Engineering Results',lambda:window.guard(self.show_results))
        self.plot_action=window.studio.submenus['Engineering'].addAction('Plot Engineering Comparison',lambda:window.guard(self.plot_comparison))
        self.envelope_action=QtGui.QAction('Toggle Tolerance Envelope',self);self.envelope_action.setToolTip('Show configured comparison limits and breach intervals');self.envelope_action.setCheckable(True);self.envelope_action.setChecked(True);self.envelope_action.toggled.connect(self.toggle_envelopes)
        window.studio.submenus['Engineering'].addAction(self.envelope_action)
        for workspace in window.workspaces:
            workspace.navigation_bar.addSeparator()
            for action in [*actions,self.envelope_action]:workspace.navigation_bar.addAction(action)
        self.phase_strips={}
        for workspace in window.workspaces:
            strip=PhaseStrip([], (0,1),workspace);strip.setMaximumHeight(42);strip.hide();workspace.layout().insertWidget(1,strip);self.phase_strips[workspace]=strip
            workspace.activeChanged.connect(lambda *_:self.refresh_overlays())
            for pane in workspace.panes:pane.getViewBox().sigXRangeChanged.connect(lambda *_:self.update_ribbon())
        self.watch=QtCore.QTimer(self);self.watch.setInterval(250);self.watch.timeout.connect(self.update_ribbon);self.watch.start()

    def prune_runs(self):
        for role,id in self.session['runs'].items():
            if id is not None and id not in self.w.store.datasets:self.session['runs'][role]=None

    def state(self):
        self.prune_runs();return copy.deepcopy(self.session)
    def restore(self,state):
        self.clear_overlays();self.result=None
        self.session=validate_session(state) if state else default_session()
        self.prune_runs();self.envelope_action.setChecked(self.session.get('show_tolerances',True));self.update_ribbon()

    def configure(self):
        self.w.mutate()
        w=self.w;dialog,layout=w.studio.dialog('Engineering Setup');tabs=QtWidgets.QTabWidget();layout.addWidget(tabs)
        form_widget=QtWidgets.QWidget();form=QtWidgets.QFormLayout(form_widget);tabs.addTab(form_widget,'Profile and Runs')
        profile=QtWidgets.QComboBox();profile.addItems(['washing_machine','refrigerator','dishwasher','hvac','generic_appliance']);profile.setCurrentText(self.session['profile']['id']);form.addRow('Appliance profile',profile)
        from app_compact_forms import CollapsibleHelp,ElidedComboBox
        form.addRow(CollapsibleHelp('Configure mappings, phases, calibrations and acceptance limits. Blank limits remain Not Evaluated.'))
        warning=self.session.get('profile_warning') or self.templates.warning
        if warning:
            label=QtWidgets.QLabel('Configuration warning: '+warning);label.setWordWrap(True);form.addRow(label)
        run_boxes={}
        usable={c.dataset_id for c in w.store.channels.values() if not c.attributes.get('engineering_projection')}
        for role in ('analysis','reference','candidate','golden'):
            box=ElidedComboBox();box.addItem('Select a dataset',None)
            for id in usable:
                ds=w.store.datasets.get(id);box.addItem(ds.name if ds else id,id)
            box.setCurrentIndex(max(0,box.findData(self.session['runs'].get(role))));form.addRow(role.title()+' Run',box);run_boxes[role]=box
        editor=QtWidgets.QPlainTextEdit(json.dumps(self.session['profile'],indent=2,ensure_ascii=False));editor.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap);tabs.addTab(editor,'Profile Configuration')
        mapping=QtWidgets.QTableWidget(0,5);mapping.setHorizontalHeaderLabels(['Source channel','Source unit','Mapping and review status','Canonical parameter','Reviewed role / unit']);tabs.addTab(mapping,'Review Channel Mapping');mapping_entries=[]
        def populate():
            proposed=validate_profile(json.loads(editor.toPlainText()));allowed={c['id'] for c in proposed['channels']};overrides={**self.templates.get(proposed),**{k:v for k,v in self.session['mappings'].items() if v is None or v in allowed}};rows=reviewed_mapping_rows(w.store,proposed,overrides,source_units={**self.templates.get_units(proposed),**self.session.get('source_units',{})});mapping.setRowCount(0);mapping_entries.clear()
            for row,record in enumerate(rows):
                c=w.store.channels[record['channel_id']]
                if c.attributes.get('engineering_projection'):continue
                row=mapping.rowCount();mapping.insertRow(row)
                source_unit=self.session.get('source_units',{}).get(c.id,self.templates.get_units(proposed).get(channel_key(c),c.unit))
                for col,value in enumerate((c.name,source_unit,record['method']+' · '+record['review_status'])):
                    item=QtWidgets.QTableWidgetItem(value);item.setToolTip(f'{c.source}\n{record.get("review_reason","")}\nReview the physical source role and logger unit. Confirming a unit does not rescale original samples.')
                    if col!=1:item.setFlags(item.flags()&~QtCore.Qt.ItemFlag.ItemIsEditable)
                    mapping.setItem(row,col,item)
                box=ElidedComboBox();box.addItem('Unmapped / review',None)
                for definition in proposed['channels']:box.addItem(definition['name']+' ['+definition['unit']+']',definition['id'])
                box.setCurrentIndex(max(0,box.findData(record['canonical_id'])));mapping.setCellWidget(row,3,box)
                reviewed=QtWidgets.QTableWidgetItem('Confirmed' if record['review_status']=='Confirmed' else 'Confirm after review');reviewed.setFlags(QtCore.Qt.ItemFlag.ItemIsEnabled|QtCore.Qt.ItemFlag.ItemIsUserCheckable);reviewed.setCheckState(QtCore.Qt.CheckState.Checked if record['review_status']=='Confirmed' else QtCore.Qt.CheckState.Unchecked);reviewed.setToolTip('Check only after confirming the selected physical source role and logger unit; unreviewed proposals remain unconfirmed');mapping.setItem(row,4,reviewed)
                box.currentIndexChanged.connect(lambda _,item=reviewed:item.setCheckState(QtCore.Qt.CheckState.Checked))
                mapping_entries.append((c.id,box))
            mapping.resizeColumnsToContents()
        populate()
        def change_profile(name):editor.setPlainText(json.dumps(load_profile(name),indent=2,ensure_ascii=False));w.guard(populate)
        profile.currentTextChanged.connect(lambda name:w.guard(lambda:change_profile(name)))
        anchors=QtWidgets.QPlainTextEdit(json.dumps(self.session['anchors'],indent=2));tabs.addTab(anchors,'Timeline Anchors')
        anchors.setToolTip('JSON per role: {"reference":{"mode":"actuator","channel_id":"..."}}. Modes: recorded, actuator, phase, cursor/event/manual with time_s. Native heater/drum alignment remains in Engineering Controls.')
        metadata=QtWidgets.QPlainTextEdit(json.dumps(self.session['metadata'],indent=2));tabs.addTab(metadata,'Advanced Report Metadata')
        identity_widget=QtWidgets.QWidget();identity_form=QtWidgets.QFormLayout(identity_widget);identity_fields={}
        for field in ('Test ID','Operator','Manufacturer','Model','Program / Settings','Intended load','Ambient conditions','Inlet conditions','Instrumentation / Calibration','Acceptance plan revision'):
            entry=QtWidgets.QLineEdit(str(self.session['metadata'].get(field,'')));entry.setPlaceholderText('Enter reviewed test information');entry.setToolTip('Verified test information only. Filenames are not treated as confirmed conditions.');identity_form.addRow(field,entry);identity_fields[field]=entry
        tabs.insertTab(1,identity_widget,'Reviewed Test Identity')
        helpers=QtWidgets.QHBoxLayout();layout.addLayout(helpers)
        for text,kind in [('Add Phase Rule','phase'),('Set Tolerance','tolerance'),('Set Acceptance Limit','acceptance'),('Set Timeline Anchor','anchor')]:
            button=QtWidgets.QPushButton(text);helpers.addWidget(button);button.clicked.connect(lambda _,k=kind:w.guard(lambda:self.edit_rule(k,editor,anchors)))
        buttons=QtWidgets.QHBoxLayout();layout.addLayout(buttons)
        refresh=QtWidgets.QPushButton('Refresh Mapping Review');refresh.clicked.connect(lambda:w.guard(populate));buttons.addWidget(refresh)
        load=QtWidgets.QPushButton('Import Profile');buttons.addWidget(load)
        def import_profile():
            path,_=QtWidgets.QFileDialog.getOpenFileName(w,'Import appliance profile','','JSON (*.json)')
            if path:editor.setPlainText(json.dumps(load_profile(path),indent=2,ensure_ascii=False));populate()
        load.clicked.connect(lambda:w.guard(import_profile))
        export=QtWidgets.QPushButton('Save Profile');buttons.addWidget(export)
        def save_profile():
            proposed=validate_profile(json.loads(editor.toPlainText()));path,_=QtWidgets.QFileDialog.getSaveFileName(w,'Save appliance profile',str(output_path(proposed['id']+'.json','templates')),'JSON (*.json)')
            if path:
                from app_support import atomic_output
                with atomic_output(path) as temp:Path(temp).write_text(json.dumps(proposed,indent=2,ensure_ascii=False),encoding='utf-8')
        export.clicked.connect(lambda:w.guard(save_profile))
        apply=QtWidgets.QPushButton('Save Engineering Setup');buttons.addWidget(apply)
        def save():
            proposed={**self.session,'profile':json.loads(editor.toPlainText()),'mappings':{id:box.currentData() for row,(id,box) in enumerate(mapping_entries) if mapping.item(row,4).checkState()==QtCore.Qt.CheckState.Checked},'runs':{role:box.currentData() for role,box in run_boxes.items()},'anchors':json.loads(anchors.toPlainText()),'metadata':json.loads(metadata.toPlainText())}
            validated=validate_session(proposed,w.store)
            reviewed_rows=[(row,id,box) for row,(id,box) in enumerate(mapping_entries) if mapping.item(row,4).checkState()==QtCore.Qt.CheckState.Checked]
            identities={channel_key(w.store.channels[id]):box.currentData() for row,id,box in reviewed_rows}
            from app_engineering_units import unit,UNITS
            updates=[]
            for row,id,box in reviewed_rows:
                declared=unit(mapping.item(row,1).text())
                if declared not in UNITS:raise ValueError('Unknown source unit: '+declared)
                updates.append((id,declared))
            source_units={channel_key(w.store.channels[id]):declared for id,declared in updates}
            self.templates.save(validated['profile'],identities,source_units,replace_profile=True);validated['mappings']={**identities,**validated['mappings']}
            validated['source_units']={**source_units,**dict(updates)}
            # Physical source-unit confirmations belong to this saved engineering
            # template. The recording's original unit and source identity stay intact.
            validated['metadata'].update({field:entry.text().strip() for field,entry in identity_fields.items()})
            validated['metadata']['Reviewed identity fields']=[field for field,entry in identity_fields.items() if entry.text().strip()]
            self.session=validated;self.result=None;self.clear_overlays();dialog.accept()
        apply.clicked.connect(lambda:w.guard(save));dialog.show();return dialog

    def edit_rule(self,kind,editor,anchor_editor):
        """Guided editors cover common rules; JSON retains advanced flexibility."""
        profile=validate_profile(json.loads(editor.toPlainText()));dialog,layout=self.w.studio.dialog('Configure '+kind.title());form=QtWidgets.QFormLayout();layout.addLayout(form)
        from app_compact_forms import ElidedComboBox
        channel=ElidedComboBox()
        for spec in profile['channels']:channel.addItem(spec['name']+' ['+spec['unit']+']',spec['id'])
        name=QtWidgets.QLineEdit();value=QtWidgets.QDoubleSpinBox();value.setRange(-1e12,1e12);value.setDecimals(6)
        method=QtWidgets.QComboBox();role=QtWidgets.QComboBox();role.addItems(['analysis','reference','candidate','golden'])
        if kind=='phase':
            form.addRow('Phase name',name);form.addRow('Recorded parameter',channel);method.addItems(['eq','gt','ge','lt','le','on','off']);form.addRow('Condition',method);form.addRow('Recorded value / threshold',value)
            duration=QtWidgets.QDoubleSpinBox();duration.setRange(0,86400);duration.setSuffix(' s');form.addRow('Minimum duration',duration)
        elif kind=='tolerance':
            form.addRow('Parameter',channel);method.addItems(['Absolute','Relative percent']);form.addRow('Tolerance type',method);value.setMinimum(0);form.addRow('Tolerance width',value)
        elif kind=='acceptance':
            channel.clear()
            for kpi in profile['kpis']:channel.addItem(kpi['name']+' ['+kpi['unit']+']',kpi['id'])
            form.addRow('KPI',channel);method.addItems(['Maximum','Minimum']);form.addRow('Acceptance bound',method);form.addRow('Confirmed engineering limit',value)
        else:
            form.addRow('Run role',role);method.addItems(['recorded','actuator','phase','cursor','event','manual']);form.addRow('Anchor method',method)
            channel.clear()
            from app_channel_identity import channel_label,channel_details
            for c in self.w.store.channels.values():channel.addItem(channel_label(self.w.store,c),c.id,channel_details(self.w.store,c))
            form.addRow('Actuator channel',channel);form.addRow('Configured phase name',name);value.setValue(self.w.active_workspace.active.cursor_lines[0].value()*60);form.addRow('Event / cursor time (seconds)',value)
        apply=QtWidgets.QPushButton('Add Configuration');layout.addWidget(apply)
        def save():
            key=channel.currentData()
            if kind=='phase':
                if not name.text().strip():raise ValueError('Enter a phase name')
                rule={'name':name.text().strip(),'conditions':[{'channel':key,'op':method.currentText(),'value':value.value()}],'minimum_seconds':duration.value(),'debounce_seconds':0}
                profile['phases']=[p for p in profile['phases'] if p['name']!=rule['name']]+[rule]
            elif kind=='tolerance':
                unit=next(c['unit'] for c in profile['channels'] if c['id']==key)
                profile['tolerances'][key]={'relative_percent':value.value()} if method.currentText()=='Relative percent' else {'absolute':value.value(),'unit':unit}
            elif kind=='acceptance':
                unit=next(k['unit'] for k in profile['kpis'] if k['id']==key)
                profile['acceptance'][key]={**profile['acceptance'].get(key,{}),('max' if method.currentText()=='Maximum' else 'min'):value.value(),'unit':unit}
            else:
                definitions=json.loads(anchor_editor.toPlainText());definitions[role.currentText()]={'mode':method.currentText(),'channel_id':key,'phase':name.text().strip(),'time_s':value.value()};anchor_editor.setPlainText(json.dumps(definitions,indent=2));dialog.accept();return
            validate_profile(profile);editor.setPlainText(json.dumps(profile,indent=2,ensure_ascii=False));dialog.accept()
        apply.clicked.connect(lambda:self.w.guard(save));dialog.show();return dialog

    def task(self,work,complete):
        self.w.mutate()
        self.cancel_token=threading.Event();token=self.cancel_token;self.cancel_action.setEnabled(True)
        def run():
            try:return work(token),None
            except InterruptedError:return None,'Cancelled; prior workspace and output retained'
            except Exception as exc:return None,str(exc)
        def done(record):
            self.cancel_action.setEnabled(False);value,error=record
            if token.is_set() and not error and isinstance(value,dict) and value.get('output_committed'):
                complete(value);self.w.statusBar().showMessage('Report completed before cancellation: '+value['output_committed']);return
            if token.is_set() or error:self.w.statusBar().showMessage(error or 'Cancelled; previous results retained');return
            complete(value)
        try:self.w.background(run,done,managed_cancel=True,title='Engineering analysis / report')
        except Exception:self.cancel_action.setEnabled(False);raise

    def analyze(self):
        session=self.state();workspace=self.w.active_workspace;comparison=workspace is self.w.comparison;store=self.w.store
        def complete(result):self.result=result;self.result_workspace=workspace;self.w.statusBar().showMessage('Engineering results ready; open Engineering Results or Generate Engineering Report');self.show_results();self.update_ribbon()
        self.task(lambda token:analyze_session(store,session,comparison,token),complete)

    def show_results(self):
        if not self.result:raise ValueError('Choose Engineering Setup, then Analyze Engineering Data first')
        tables={}
        for run in self.result['runs']:
            prefix=run['role'].title()+' · '+run.get('report_scope','whole_recording').replace('_',' ')
            tables[prefix+' · Readiness']=pd.DataFrame(run.get('readiness',[]))
            tables[prefix+' · Source Review']=pd.DataFrame(run['mapping'])
            tables[prefix+' · Timing Quality']=pd.DataFrame([{'Canonical role':key,'Source':trace.channel.name,**trace.quality(run.get('scope_start_s'),run.get('scope_end_s'))} for key,trace in run.get('quality_traces',run['traces']).items()])
            rows=[{k:v for k,v in result.items() if k!='definition'} for result in run['kpis']]
            for group in dict.fromkeys(r['group'] for r in rows):tables[prefix+' · '+group]=pd.DataFrame([r for r in rows if r['group']==group])
            tables[prefix+' · Phases']=pd.DataFrame([{k:v for k,v in p.items() if k not in ('metrics','definition')} for p in run['phases']])
            for category in ('Data Quality','Appliance Event','Rule Evaluation'):
                tables[prefix+' · '+category]=pd.DataFrame([event for event in run['anomalies'] if event.get('category')==category])
            tables[prefix+' · Warnings']=pd.DataFrame([{'status':'Not evaluated','reason':warning} for warning in run['warnings']])
        if self.result['comparison']:
            tables['Delta KPIs']=pd.DataFrame(self.result['comparison']['kpis'])
            if self.result['comparison']['golden_kpis']:tables['Golden vs Candidate']=pd.DataFrame(self.result['comparison']['golden_kpis'])
        return self.w.studio.table_dialog('Engineering Results — units, coverage and acceptance',tables)

    def report(self):
        """Choose a clear engineering scope; keep the existing quick export separate."""
        self.w.mutate()
        dialog,layout=self.w.studio.dialog('Generate Engineering Report')
        form=QtWidgets.QFormLayout();layout.addLayout(form)
        scope=QtWidgets.QComboBox()
        for label,key in [('Whole recording','whole_recording'),('Active cursor interval','cursor_interval'),('Whole recording and cursor interval','both')]:scope.addItem(label,key)
        form.addRow('Results and plot scope',scope)
        appendix=QtWidgets.QCheckBox('Include complete event appendix in PDF');appendix.setChecked(False)
        appendix.setToolTip('All events are always retained in companion Excel / JSON / CSV evidence. The optional PDF appendix can add many pages.')
        form.addRow(appendix)
        view=self.w.active_workspace.active.state()
        positions=view.get('cursors',[])
        temporal=self.w.active_workspace.active.coordinate and self.w.active_workspace.active.coordinate[0]=='time'
        cursor_interval=[float(value)*60 for value in positions[:2]] if temporal and len(positions)>=2 else None
        preview=QtWidgets.QLabel();preview.setWordWrap(True);form.addRow('PDF preview',preview)
        from app_compact_forms import CollapsibleHelp
        form.addRow(CollapsibleHelp('The PDF has four main sections. Complete KPI, event, mapping and configuration evidence is saved beside it as Excel, CSV and JSON. Primary / mandatory results can continue onto readable extra pages. An optional full-event appendix can add many pages; its estimate uses prior analysis until the selected scope has been recalculated.'))
        def refresh():
            from app_engineering_reports import report_preview
            runs=self.result['runs'] if self.result else []
            record=report_preview(runs,scope=scope.currentData(),view=view,detailed_appendix=appendix.isChecked())
            count=record.get('event_records',0)
            from app_channel_identity import dataset_aliases
            aliases=dataset_aliases(self.w.store)
            roles=('reference','candidate','golden') if self.w.active_workspace is self.w.comparison else ('analysis',)
            sources='; '.join(role.title()+': '+aliases.get(self.session['runs'].get(role),'Select dataset in Engineering Setup') for role in roles if role!='golden' or self.session['runs'].get(role))
            preview.setText(f"Expected {record['expected_pages']} pages" +(' (estimate from prior scope)' if appendix.isChecked() and not record['event_count_exact'] else '')+'\n'+
                            (f"Prior analysis: {count:,} event records\n" if runs else 'Event counts calculated during analysis\n')+
                            sources+('\nCursor interval unavailable: activate a time plot with two distinct cursors.' if scope.currentData()!='whole_recording' and (not cursor_interval or cursor_interval[0]==cursor_interval[1]) else ''))
        scope.currentIndexChanged.connect(refresh);appendix.toggled.connect(refresh);refresh()
        export=QtWidgets.QPushButton('Choose Output and Generate');layout.addWidget(export)
        def generate():
            chosen_scope=scope.currentData();detailed=appendix.isChecked()
            if chosen_scope!='whole_recording' and (not cursor_interval or cursor_interval[0]==cursor_interval[1]):raise ValueError('Use two distinct cursors on an active time plot for interval reporting')
            path,_=QtWidgets.QFileDialog.getSaveFileName(self.w,'Generate Engineering Report',str(output_path('Engineering report.pdf')),'PDF (*.pdf);;Excel (*.xlsx)')
            if not path:return
            session=self.state();workspace=self.w.active_workspace;comparison=workspace is self.w.comparison;store=self.w.store
            selected=list(dict.fromkeys(id for pane in workspace.visible_panes() for id in pane.ids))
            dialog.accept()
            def work(token):
                from app_engineering_reports import export_engineering
                result=analyze_session(store,session,comparison,token,report_scope=chosen_scope,cursor_interval_s=cursor_interval)
                export_engineering(path,store,result['runs'],result['comparison'],{**session['metadata'],'View':view,'Engineering session':session,'Interval comparison':result.get('interval_comparison')},view,token,selected,scope=chosen_scope,detailed_appendix=detailed)
                result['output_committed']=path;return result
            def complete(result):
                self.result=result;self.result_workspace=workspace;self.w.statusBar().showMessage('Engineering report and complete evidence saved: '+path)
                message=QtWidgets.QMessageBox(self.w);message.setWindowTitle('Engineering Report Saved');message.setText('Report saved: '+Path(path).name);message.setInformativeText('Complete evidence files are saved beside the PDF.' if path.lower().endswith('.pdf') else 'The workbook contains the complete engineering evidence.');open_file=message.addButton('Open File',QtWidgets.QMessageBox.ButtonRole.ActionRole);open_folder=message.addButton('Open Folder',QtWidgets.QMessageBox.ButtonRole.ActionRole);message.addButton(QtWidgets.QMessageBox.StandardButton.Close)
                open_file.clicked.connect(lambda:QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(Path(path).resolve()))));open_folder.clicked.connect(lambda:QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(Path(path).resolve().parent))));message.open()
            self.task(work,complete)
        export.clicked.connect(lambda:self.w.guard(generate));dialog.show();return dialog

    def clear_overlays(self):
        for vb,item in self.overlays:
            try:vb.removeItem(item)
            except RuntimeError:pass
        self.overlays=[]

    def toggle_envelopes(self,value):self.session['show_tolerances']=value;self.refresh_overlays()

    def plot_comparison(self):
        self.result_workspace=self.w.comparison
        if not self.result or not self.result['comparison']:raise ValueError('Analyze Reference and Candidate runs in Comparison first')
        from app_channel_store import Channel
        self.clear_overlays();store=self.w.store
        for id in self.projection_ids:
            if id in store.channels:store.delete([id])
        ids=[]
        with store.batch():
            preferred=[run for run in self.result['runs'] if run.get('report_scope','whole_recording')=='whole_recording'] or self.result['runs']
            for run in preferred:
                for key,trace in run['traces'].items():
                    c=trace.channel;actuator=next(spec for spec in self.result['session']['profile']['channels'] if spec['id']==key)['domain']=='actuator_state'
                    values=np.where(np.isfinite(trace.raw_y),(trace.raw_y!=0).astype(float),np.nan) if actuator else trace.raw_y
                    projection=store.add(Channel(c.name+' · '+run['role'],trace.raw_t/60,values,raw_y=trace.raw_y if actuator else None,unit=trace.unit,kind=trace.kind,coordinate_unit='min',dataset_id=c.dataset_id,source=c.source,group='Engineering Comparison',parents=[c.id],attributes={'actuator_binary':actuator,'engineering_projection':True,'canonical_id':key,'run_role':run['role']}));ids.append(projection.id)
        self.projection_ids=ids;self.w.comparison.assign(ids);self.w.tabs.setCurrentIndex(1);self.refresh_overlays()

    def refresh_overlays(self):
        self.clear_overlays()
        if not self.result or not self.result['comparison'] or not self.session.get('show_tolerances',True):return
        pane=self.w.comparison.active
        for key,record in self.result['comparison']['envelopes'].items():
            id=next((id for id in pane.ids if self.w.store.channels[id].attributes.get('canonical_id')==key and self.w.store.channels[id].attributes.get('engineering_projection')),None)
            if id is None:continue
            vb=pane.curves[id][0];x=record['grid']/60
            low=pg.PlotCurveItem(x,record['lower'],pen=pg.mkPen('#73b98b',width=.7));high=pg.PlotCurveItem(x,record['upper'],pen=pg.mkPen('#73b98b',width=.7));fill=pg.FillBetweenItem(low,high,brush=(80,170,100,35))
            for item in (low,high,fill):item.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton);vb.addItem(item,ignoreBounds=True);self.overlays.append((vb,item))
            for breach in record['breaches']:
                region=pg.LinearRegionItem((breach['start_s']/60,breach['end_s']/60),movable=False,brush=(220,75,75,35));region.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton);vb.addItem(region,ignoreBounds=True);self.overlays.append((vb,region))

    def update_ribbon(self):
        for action in self.operation_actions:action.setEnabled(not self.w.busy)
        self.prune_runs()
        if self.result:
            stale=any(self.w.store.channels.get(trace.channel.id) is not trace.channel for run in self.result['runs'] for trace in run.get('quality_traces',run['traces']).values())
            if stale:self.result=None;self.clear_overlays();self.w.statusBar().showMessage('Engineering inputs changed; analyze again for current results')
        for workspace,strip in self.phase_strips.items():
            pane=workspace.active;signature=(id(self.result),id(pane),tuple(pane.getViewBox().viewRange()[0]),self.session.get('show_phases',True),id(getattr(self,'result_workspace',None)))
            if getattr(strip,'_ribbon_state',None)==signature:continue
            strip._ribbon_state=signature;rows=[]
            if self.result and self.session.get('show_phases',True) and workspace is getattr(self,'result_workspace',workspace):
                for p in self.result['runs'][0]['phases']:rows.append({'start':p['start_s']/60,'end':p['end_s']/60,'label':p['name'],'unit':'min'})
            if rows and pane.coordinate and pane.coordinate[0]=='time':strip.spans=rows;strip.bounds=tuple(pane.getViewBox().viewRange()[0]);strip.show();strip.update()
            else:strip.hide()

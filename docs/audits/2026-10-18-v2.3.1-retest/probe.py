import os,sys,json,re
from pathlib import Path
root=Path(__file__).parent
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
os.environ['ANALIZER_OUTPUT_DIR']=str(root/'outputs');os.environ['ANALIZER_SETTINGS_DIR']=str(root/'settings')
sys.path.insert(0,'/workspace/Analizer')
import numpy as np,pandas as pd
from PySide6 import QtWidgets,QtCore,QtTest
from app_workbench import AdvancedStudioWindow
from app_channel_store import ChannelStore,Channel,Dataset
from app_workspace_io import render_report
from app_reporting import match_scorecard,interval_tables
from app_studio_state import channel_preset
app=QtWidgets.QApplication([])
w=AdvancedStudioWindow();w.resize(1536,912);w.show();app.processEvents()
result={'source':'8c3ce86','version':'2.3.1','platform':'Linux Qt offscreen','qt_scale':app.devicePixelRatio(),'geometry_cases':[]}
x=np.linspace(0,265,2651);ds=Dataset('Synthetic bench',pd.DataFrame({'time_min':x}),source='synthetic-bench.csv')
w.store.datasets[ds.id]=ds
with w.store.batch():
    out=w.store.add(Channel('out Valve',x,((x<4)|((x>238)&(x<245))).astype(float),unit='state',kind='discrete',coordinate_unit='min',dataset_id=ds.id,attributes={'actuator_binary':True}))
    drain=w.store.add(Channel('Drain Valve',x,((x>248)&(x<254)).astype(float),unit='state',kind='discrete',coordinate_unit='min',dataset_id=ds.id,attributes={'actuator_binary':True}))
    pressure=w.store.add(Channel('Water Pressure',x,1650+5*np.sin(x/5),unit='Pa',coordinate_unit='min',dataset_id=ds.id))
    power=w.store.add(Channel('Power',x,np.full(len(x),3600.),unit='W',coordinate_unit='min',dataset_id=ds.id))
w.dashboard.assign([out.id]);w.show_dock('Data Portal');w.theme.apply('Dark');app.processEvents();QtTest.QTest.qWait(50)
ws=w.dashboard;ws.set_layout('Vertical split');ws.panes[1].bind([drain.id,pressure.id]);ws.link();w.layout_combo.setCurrentText('Vertical split');app.processEvents();QtTest.QTest.qWait(50)
ws.panes[0].cursor_lines[0].setValue(66.2596);ws.panes[0].cursor_lines[1].setValue(198.767);w._readouts()
def geometry(label):
    app.processEvents();QtTest.QTest.qWait(30)
    panes=[]
    for p in ws.visible_panes():
        rect=p.getViewBox().sceneBoundingRect()
        panes.append({'names':[w.store.channels[id].name for id in p.ids],'widget':[p.width(),p.height()],'viewbox_height':round(rect.height(),2),'size_hint':[p.sizeHint().width(),p.sizeHint().height()]})
    record={'scenario':label,'window':[w.width(),w.height()],'workspace':[ws.width(),ws.height()],'panes':panes,'row_stretch':[ws.grid.rowStretch(i) for i in range(2)],'readout_width':w.readout.width(),'readout_content_width':w.readout.horizontalHeader().length()}
    result['geometry_cases'].append(record);return record
geometry('Single to Vertical split, logical 1536x912');w.grab().save(str(root/'split-dark-large.png'))
w.resize(1024,680);geometry('Resized 1024x680');w.grab().save(str(root/'split-dark-1024.png'))
w.resize(1920,1140);geometry('Resized 1920x1140');w.grab().save(str(root/'split-dark-1920.png'))
w.resize(1536,912);geometry('Return to 1536x912, baseline')
for row in range(2):ws.grid.setRowStretch(row,1);ws.panes[row].setMinimumHeight(180)
geometry('Diagnostic only: equal stretch and 180px minimum')
w.grab().save(str(root/'diagnostic-balanced-split.png'))
ws.active=ws.panes[0];w.workspace_changed()
dialog=w.studio.cursor_lock_dialog();app.processEvents();fields=dialog.findChildren(QtWidgets.QComboBox)
result['lock_dialog']={'size':[dialog.width(),dialog.height()],'options':[[box.itemText(i) for i in range(box.count())] for box in fields]}
fields[0].setCurrentIndex(fields[0].findData(out.id));fields[1].setCurrentIndex(fields[1].findData(out.id))
next(button for button in dialog.findChildren(QtWidgets.QPushButton) if button.text()=='Apply').click();app.processEvents()
p=ws.panes[0];result['cursor_locks_created']=[lock is not None and lock['channel']==out.id for lock in p.cursor_locks]
before=p.cursor_lines[0].value();p.step_cursor(0,1);after=p.cursor_lines[0].value();result['cursor_step']={'before':before,'after':after,'is_real_sample':bool(np.any(out.x==after))}
coords=[line.value() for line in p.cursor_lines];p.setXRange(100,150,padding=0);app.processEvents();result['locked_positions_preserved_on_pan']=np.allclose(coords,[line.value() for line in p.cursor_lines])
result['navigation']={'has_quick_zoom':hasattr(ws,'quick_zoom_bar'),'tab_corner_present':w.tabs.cornerWidget(QtCore.Qt.Corner.TopRightCorner) is not None,'icons':{key:not ws.navigation_actions[key].icon().isNull() for key in ('in','out','reset','pan')}}
p.cursor_locks=[None,None];p.bind([power.id]);p.cursor_lines[0].setValue(2);p.cursor_lines[1].setValue(4);w._readouts();result['energy_card']=w.interval_card.text()
score=match_scorecard(pd.DataFrame([{'parameter':'RETEST_SIGNED_DELTA','sim_val':'100 W','raw_val':'115 W','delta':'+15.00 W','percent':'+15.00%','status':'YELLOW'}]))
render_report(root/'comparison-delta.pdf',w.store,w.dashboard.state(),scorecard=score)
for mode in ('Dark','Light','Dark','Light'):
    w.theme.apply(mode);app.processEvents()
result['light_legend']=[{'text':label.text,'html':label.item.toHtml()} for _,label in p.legend.items]
w.grab().save(str(root/'theme-light-retest.png'))
# Repeat the two-file identity and filtered selection probes independently of layout measurements.
other=ChannelStore();temperature_ids=[]
for name in ('Run A','Run B'):
    d=Dataset(name,pd.DataFrame({'time_min':[0,1,2]}),source=name+'.csv');other.datasets[d.id]=d
    for label,unit in [('Temperature','°C'),('Pressure','Pa')]:
        c=other.add(Channel(label,[0,1,2],[20,30,40],unit=unit,coordinate_unit='min',dataset_id=d.id,source=d.source))
        if label=='Temperature':temperature_ids.append(c.id)
w.merge_store(other);w.comparison.assign(temperature_ids);w.tabs.setCurrentIndex(1);w._readouts()
result['same_name_readout']=[w.readout.item(row,0).text() for row in range(w.readout.rowCount())]
w.portal.search.setText('Temperature');app.processEvents();first=next(iter(other.datasets))
result['filter_select_all']={'visible_children':w.portal.dataset_roots[first].child(0).childCount(),'affected_channels':len(w.portal.dataset_channels(first))}
from app_trace_colors import channel_colors
colors=channel_colors(w.store);preset=channel_preset(w.store,w.comparison,w.studio.options)
result['preset_color_mismatches']=[{'name':c.name,'rendered':colors[c.id],'saved':record['color']} for c in w.store.channels.values() for record in preset['signals'].values() if record.get('source_path')==c.source and record.get('source_col')==c.attributes.get('source_column',c.name) and record['color']!=colors[c.id]]
(root/'observations.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));w.close();app.processEvents()

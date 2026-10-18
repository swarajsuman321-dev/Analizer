"""Replay user-facing reliability contracts with the four committed recordings.

This is a diagnostic audit, not a replacement for unit tests. Exit 1 means a
user contract is unmet; results distinguish those findings from execution errors.
No application settings, source recording, or production workspace is overwritten.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=Path, default=PROJECT/'tests/samples/recordings')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    os.environ['ANALIZER_OUTPUT_DIR'] = str(args.output/'outputs')
    os.environ['ANALIZER_SETTINGS_DIR'] = str(args.output/'settings')
    import numpy as np
    import pandas as pd
    from PySide6 import QtCore, QtGui, QtWidgets, QtTest
    from app_channel_store import ChannelStore
    from app_ingestion import ingest
    from app_plot_workspace import LAYOUTS
    from app_workbench import AdvancedStudioWindow
    from app_signal_processing import formula, transform
    from app_tdms_templates import ParameterReview, ParameterTemplates
    from app_version import VERSION

    result = {'version': VERSION, 'platform': sys.platform,
              'qt_platform': os.environ.get('QT_QPA_PLATFORM'),
              'inputs': [], 'contracts': [], 'time_lock_cases': [],
              'dialog_inventory': [], 'processing': [], 'execution_errors': []}

    def portable(value):
        if isinstance(value, np.generic): return value.item()
        if isinstance(value, np.ndarray): return value.tolist()
        if isinstance(value, Path): return str(value)
        raise TypeError(type(value).__name__)

    def save():
        (args.output/'results.json').write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=portable)+'\n', encoding='utf-8')

    def contract(id, description, passed, observed):
        result['contracts'].append({'id': id, 'user_expectation': description,
                                   'status': 'passed' if passed else 'unmet', 'observed': observed})
        save()

    manifest = json.loads((args.samples/'manifest.json').read_text(encoding='utf-8'))
    store = ChannelStore()
    role_ids = {}
    for entry in manifest['files']:
        path = args.samples/entry['filename']
        with path.open('rb') as f: digest = hashlib.file_digest(f, 'sha256').hexdigest()
        if digest != entry['sha256']: raise ValueError('Sample checksum mismatch: '+path.name)
        other = ChannelStore()
        ingest(other, path)
        store.datasets.update(other.datasets)
        store.channels.update(other.channels)
        role_ids[entry['role']] = list(other.channels)
        result['inputs'].append({**entry, 'source_rows': [len(d.frame) for d in other.datasets.values()],
            'channels': [{'id': c.id, 'name': c.name, 'unit': c.unit, 'kind': c.kind,
                          'samples': len(c.x), 'start_min': float(c.x[0]), 'end_min': float(c.x[-1]),
                          'duplicate_times': int((np.diff(c.x)==0).sum()),
                          'unknown_values': int((~np.isfinite(c.y)).sum())}
                         for c in other.channels.values()]})
    save()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window = AdvancedStudioWindow()
    window.resize(1536, 960)
    window.show()
    window.store.datasets.update(store.datasets)
    with window.store.batch():
        for c in store.channels.values(): window.store.add(c)
    store = window.store
    for role, field in [('power', window.power_path), ('machine', window.machine_path),
                        ('simulation', window.simulation_path)]:
        field.setText(str(args.samples/next(e['filename'] for e in manifest['files'] if e['role']==role)))
    errors = []
    current_scenario = [None]
    old_hook = sys.excepthook
    def hook(kind, value, tb): errors.append({'scenario':current_scenario[0], 'error':''.join(traceback.format_exception(kind, value, tb))})
    sys.excepthook = hook
    def events(): app.processEvents(); QtTest.QTest.qWait(20); app.processEvents()
    def run(name, fn):
        previous=current_scenario[0];current_scenario[0]=name
        try: return fn()
        except Exception:
            result['execution_errors'].append({'scenario': name, 'error': traceback.format_exc()})
            save()
            return None
        finally: current_scenario[0]=previous
    def choose(role, predicate):
        return next((store.channels[id] for id in role_ids[role] if predicate(store.channels[id])),
                    store.channels[role_ids[role][0]])
    tdms = [store.channels[id] for id in role_ids['tdms']]
    a = next((c for c in tdms if c.unit in ('°C', 'degC', 'C')), tdms[0])
    b = next((c for c in tdms if c.id!=a.id and c.unit==a.unit), tdms[1])
    pressure = choose('machine', lambda c: c.unit=='Pa')
    valve = choose('machine', lambda c: c.kind!='analog' and 'out' in c.name.lower())
    power = choose('power', lambda c: c.unit in ('W', 'kW') or 'p-e1' in c.name.lower())
    simulation = choose('simulation', lambda c: 'water_temp' in c.name.lower())
    ws = window.dashboard

    def menu_tree(menu):
        records = []
        for action in menu.actions():
            if action.isSeparator(): continue
            record = {'text': action.text(), 'enabled': action.isEnabled()}
            if action.menu(): record['children'] = menu_tree(action.menu())
            records.append(record)
        return records

    def baseline():
        ws.assign([a.id]); events()
        button = ws.navigation_bar.widgetForAction(ws.navigation_actions['in'])
        delta = abs(button.mapToGlobal(button.rect().center()).y()-
                    window.tabs.tabBar().mapToGlobal(window.tabs.tabBar().rect().center()).y())
        contract('NAV-HEADER', 'Zoom/pan controls are on the graph header beside Analysis/Comparison, not in a separate global toolbar.',
                 delta<=16 and ws.navigation_bar.parentWidget() is not window,
                 {'row_center_difference_px': delta, 'toolbar_parent': type(ws.navigation_bar.parentWidget()).__name__})
        window.show_dock('Data Portal'); window.theme.apply('Dark'); events()
        window.grab().save(str(args.output/'current-header.png'))
        p = ws.active
        position = p.mapFromScene(p.getViewBox().sceneBoundingRect().center())
        QtTest.QTest.mouseClick(p.viewport(), QtCore.Qt.MouseButton.RightButton, pos=position)
        events()
        menu = app.activePopupWidget()
        if not isinstance(menu, QtWidgets.QMenu): menu = p.getViewBox().getMenu(None)
        records = menu_tree(menu)
        result['context_menu'] = records
        menu.grab().save(str(args.output/'current-context-menu.png'))
        text = json.dumps(records).lower()
        needed = ['zoom xy', 'zoom x', 'zoom y', 'cursor', 'revert zoom', 'comments']
        contract('RIGHT-CLICK', 'Right-click offers chart tasks: Hand/Pan, Cursor, Zoom XY/X/Y, previous zoom and comments on the clicked pane.',
                 all(term in text for term in needed), {'menu': records, 'missing_task_labels': [s for s in needed if s not in text]})
        menu.close(); events()
        item=p.getPlotItem();before_x=p.curves[a.id][1].xData.copy();before_y=p.curves[a.id][1].yData.copy()
        item.ctrl.fftCheck.setChecked(True);events()
        result['native_fft_probe']={'checkbox_checked':item.ctrl.fftCheck.isChecked(),
            'framework_managed_curve_count':len(item.curves),'coordinate':p.coordinate,
            'display_data_unchanged':bool(np.array_equal(before_x,p.curves[a.id][1].xData) and np.array_equal(before_y,p.curves[a.id][1].yData,equal_nan=True))}
        item.ctrl.fftCheck.setChecked(False);events()
    run('header and context menu', baseline)

    def lock_case(name, channel_groups, layout='Vertical split', action=None):
        ws.set_time_lock(False)
        for p in ws.panes: p.bind([])
        ws.set_layout(layout)
        for p, ids in zip(ws.visible_panes(), channel_groups): p.bind(ids)
        events(); ws.set_time_lock(True); events()
        ws.active = ws.panes[0]
        ws.panes[0].setXRange(40, 80, padding=0); events()
        if action: action()
        events()
        panes = ws.visible_panes()
        ranges = [list(p.getViewBox().viewRange()[0]) for p in panes if p.ids]
        equal = all(np.allclose(ranges[0], x, rtol=0, atol=1e-7) for x in ranges[1:])
        detail = {'name': name, 'layout': layout, 'x_ranges_min': ranges, 'same_visible_time': equal,
                  'plot_pixels': [{'name': [store.channels[id].name for id in p.ids],
                       'view_rect': p.getViewBox().sceneBoundingRect().getRect()} for p in panes if p.ids]}
        result['time_lock_cases'].append(detail)
        contract('TIME-'+str(len(result['time_lock_cases'])),
                 'With Lock Time Axes on, compatible visible time plots have identical left/right limits after '+name+'.', equal, detail)
        return equal

    cases = [
        ('same-unit panes', [[a.id], [b.id]], 'Vertical split', None),
        ('different units, stacked', [[a.id], [valve.id, pressure.id]], 'Vertical split', None),
        ('different units, side by side', [[a.id], [valve.id, pressure.id]], 'Horizontal split', None),
        ('resize while locked', [[a.id], [valve.id, pressure.id]], 'Vertical split', lambda: window.resize(1280, 900)),
        ('pan second pane while locked', [[a.id], [valve.id, pressure.id]], 'Vertical split', lambda: ws.panes[1].setXRange(60, 120, padding=0)),
        ('zoom X while locked', [[a.id], [valve.id, pressure.id]], 'Vertical split', lambda: (ws.navigate('x'), ws.navigate('in'))),
        ('fit/reset while locked', [[a.id], [simulation.id]], 'Vertical split', lambda: ws.navigate('reset')),
        ('hide and show a pressure channel', [[a.id], [valve.id, pressure.id]], 'Vertical split', lambda: (ws.set_visible([pressure.id],False), ws.set_visible([pressure.id],True))),
        ('theme change while locked', [[a.id], [valve.id, pressure.id]], 'Vertical split', lambda: window.theme.apply('Light')),
        ('tab switch while locked', [[a.id], [valve.id, pressure.id]], 'Vertical split', lambda: (window.tabs.setCurrentIndex(1),window.tabs.setCurrentIndex(0))),
        ('restore saved view while locked', [[a.id], [valve.id, pressure.id]], 'Vertical split', lambda: ws.restore(ws.state())),
        ('four mixed-unit panes', [[a.id], [b.id], [valve.id, pressure.id], [power.id]], '2×2', None),
    ]
    for name, groups, layout, action in cases: run(name, lambda n=name,g=groups,l=layout,f=action:lock_case(n,g,l,f))
    def unlocked():
        ws.set_time_lock(False); ws.panes[0].setXRange(10,30,padding=0); ws.panes[1].setXRange(50,90,padding=0); events()
        values=[p.getViewBox().viewRange()[0] for p in ws.panes[:2]]
        contract('TIME-OFF','With Lock Time Axes off, I can inspect different time windows independently.',not np.allclose(*values),values)
    run('unlocked independence', unlocked)

    def layouts():
        window.resize(1536,912);window.theme.apply('Dark')
        ws.set_layout('Vertical split');ws.panes[0].bind([valve.id]);ws.panes[1].bind([pressure.id,power.id]);ws.link();events()
        for size in [(1536,912),(1024,680)]:
            window.resize(*size);events()
            heights=[p.getViewBox().sceneBoundingRect().height() for p in ws.visible_panes()]
            contract('PANE-'+str(size[0]), 'Every visible split plot retains at least 150 logical pixels of drawing height or scrolls instead of being crushed.',
                     min(heights)>=150,{'window':size,'drawing_heights':heights})
            window.grab().save(str(args.output/f'real-split-{size[0]}.png'))
        result['layout_inventory']=[]
        for name in LAYOUTS:
            ws.set_layout(name);events()
            result['layout_inventory'].append({'layout':name,'visible_panes':len(ws.visible_panes()),'widget_heights':[p.height() for p in ws.visible_panes()]})
        window.resize(1536,960);ws.set_layout('Vertical split');events()
    run('layouts', layouts)

    def dialogs():
        window.resize(1536,960);ws.active=ws.panes[0];ws.active.bind([a.id,b.id]);events()
        def record(name, create):
            before=list(window.studio.dialogs);dialog=create();events()
            if dialog is None: dialog=next(d for d in reversed(window.studio.dialogs) if d not in before)
            if not dialog.isVisible(): dialog.show(); events()
            labels=[l.text() for l in dialog.findChildren(QtWidgets.QLabel) if len(l.text())>90 and not l.wordWrap()]
            record={'name':name,'title':dialog.windowTitle(),'size':[dialog.width(),dialog.height()],
                    'size_hint':[dialog.sizeHint().width(),dialog.sizeHint().height()],
                    'tables':[{'rows':t.model().rowCount(),'columns':t.model().columnCount()} for t in dialog.findChildren(QtWidgets.QTableView) if t.model()],
                    'long_unwrapped_explanations':labels}
            result['dialog_inventory'].append(record)
            if name in ('Cursor locks','Reference units','Move cursors'):
                dialog.grab().save(str(args.output/('dialog-'+name.lower().replace(' ','-')+'.png')))
            dialog.close();events();QtCore.QCoreApplication.sendPostedEvents(None,QtCore.QEvent.Type.DeferredDelete)
        creators=[('Plot display',window.studio.display_options),('Cursor locks',window.studio.cursor_lock_dialog),
                  ('Move cursors',window.studio.cursor_positions),('Channel mapping',window.studio.channel_settings),
                  ('Measurements / quality',window.studio.diagnostics),('Comparison mapping',window.studio.comparison_mapping),
                  ('Reference units',window.studio.reference_units),('Engineering setup',window.engineering.configure),
                  ('Extensions',window.studio.extensions_dialog)]
        for name, create in creators: run('dialog '+name,lambda n=name,f=create:record(n,f))
        profile=QtWidgets.QPlainTextEdit(json.dumps(window.engineering.session['profile']))
        anchors=QtWidgets.QPlainTextEdit('{}')
        for kind in ('phase','tolerance','acceptance','anchor'):
            run('rule '+kind,lambda k=kind:record('Rule '+k,lambda:window.engineering.edit_rule(k,profile,anchors)))
        tdms_store=ChannelStore();tdms_store.channels={id:store.channels[id] for id in role_ids['tdms']}
        run('TDMS review dialog',lambda:record('TDMS first review',lambda:ParameterReview(ParameterTemplates().unknown(tdms_store),window)))
        for name,dialog in [('About / Updates',window.info_dialog),('User Manual',window.help_dialog)]:
            run(name,lambda n=name,d=dialog:record(n,lambda:(d.show(),d)[1]))
        result['dialog_note']='Screen-bounded is not the same as appropriately compact; screenshots and long unwrapped labels need a task-based review.'
    run('dialog inventory',dialogs)

    def processing():
        strict_rejections=('resample','uniform','finite','clock','increasing','support')
        for operation in ['Offset and scale','Time shift','Descriptive statistics','Histogram','Cumulative integration',
                          'Moving average','Savitzky–Golay','Butterworth low-pass','Differentiation','FFT','Welch PSD','Peak and valley detection']:
            try:
                output=transform(power,operation)
                row={'operation':operation,'status':'passed','samples':len(output.x),'unit':output.unit,'coordinate_unit':output.coordinate_unit}
            except ValueError as e:
                row={'operation':operation,'status':'rejected_with_message','message':str(e),
                     'known_clock_or_support_requirement':any(word in str(e).lower() for word in strict_rejections)}
            result['processing'].append(row)
        default_filter=next(row for row in result['processing'] if row['operation']=='Butterworth low-pass')
        contract('FILTER-DEFAULT', 'The default low-pass cutoff fits the loaded sample rate, or the UI explains a valid range before Apply.',
                 default_filter['status']=='passed', default_filter)
        retry=transform(power,'Butterworth low-pass',cutoff=.1)
        result['processing'].append({'operation':'Butterworth low-pass, cutoff 0.1 Hz','status':'passed','samples':len(retry.x),'unit':retry.unit})
        try:
            formula(store,'Ch("'+a.id+'") - Ch("'+simulation.id+'")')
            guarded=False
        except ValueError as exc: guarded=True;result['mixed_clock_formula_message']=str(exc)
        contract('MATH-CLOCK','A formula must not silently combine unrelated recording clocks.',guarded,result.get('mixed_clock_formula_message'))
        ws.active.bind([power.id]);ws.active.cursor_lines[0].setValue(20);ws.active.cursor_lines[1].setValue(25);window._readouts()
        result['real_power_interval_card']=window.interval_card.text()
    run('real-data processing',processing)

    def duplicate_cursor():
        choices=[]
        for id in role_ids['machine']:
            c=store.channels[id];x,y=c.values()
            indices=np.flatnonzero((np.diff(x)==0)&np.isfinite(y[:-1])&np.isfinite(y[1:])&(y[:-1]!=y[1:]))
            if len(indices):choices.append((c,int(indices[0])))
        if not choices:result['duplicate_cursor']='No changed-value adjacent duplicate found';return
        c,i=choices[0];p=ws.active;p.bind([c.id]);p.lock_cursor(0,c.id);p.cursor_lines[0].setValue(float(c.x[i]));events()
        index=p.cursor_locks[0]['index'];reading=c.sample(p.cursor_lines[0].value())
        marker_x,marker_y=p.cursor_markers[0].getData();marker_value=float(marker_y[0]);window._readouts()
        displayed_readout=window.readout.item(0,2).text()
        contract('CURSOR-DUPLICATE','At a duplicate timestamp, the locked marker and numeric readout identify the same sample/value.',
                 np.isclose(reading,marker_value,equal_nan=True),{'channel':c.name,'time':float(c.x[i]),'anchor_index':index,'marker_value':marker_value,'readout_value':reading,'displayed_readout_A':displayed_readout})
    run('duplicate cursor sample',duplicate_cursor)

    result['control_state_observations']={'peak_marker_enabled':window.compact.toggles['annotate_peak'].isEnabled()}
    result['execution_errors'].extend({'scenario':'Qt callback during '+str(e['scenario']),'kind':'application_callback','error':e['error']} for e in errors)
    result['summary']={'contracts':len(result['contracts']),
                       'passed':sum(r['status']=='passed' for r in result['contracts']),
                       'unmet':sum(r['status']=='unmet' for r in result['contracts']),
                       'execution_errors':len(result['execution_errors']),
                       'application_callback_errors':len(errors),
                       'audit_runner_errors':len(result['execution_errors'])-len(errors)}
    result['source_files_unchanged']=True
    for entry in manifest['files']:
        with (args.samples/entry['filename']).open('rb') as f:
            result['source_files_unchanged'] &= hashlib.file_digest(f,'sha256').hexdigest()==entry['sha256']
    save();sys.excepthook=old_hook;window.close();app.processEvents()
    print(json.dumps(result['summary']))
    return 1 if result['summary']['unmet'] or result['execution_errors'] else 0


if __name__=='__main__':
    raise SystemExit(main())

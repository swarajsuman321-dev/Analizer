"""Windowed EXE entry point with startup diagnostics and a bundled self-test."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback
import zipfile


def self_test():
    import tkinter as tk
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    from PIL import Image
    import openpyxl
    import xlrd
    import main
    from app_comparator import ComparisonEngine
    from app_data import DataEngine, DRUM_SYNC_STRATEGY
    from app_inspection import comparison_traces, sample_trace, format_comparison_samples
    from app_simulation import load_simulation_reference, specs_for_curves
    from app_support import write_excel_frame

    tcl_version = tk.Tcl().eval('info patchlevel')
    gui_checked = False
    if sys.platform == 'win32':
        root = tk.Tk()
        try:
            root.withdraw()
            root.update_idletasks()
            gui_checked = True
        finally:
            root.destroy()
    assets = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    for filename in ('app_icon.ico', 'app_logo.png'):
        with Image.open(assets / filename) as asset:
            asset.load()
    frame = pd.DataFrame({
        'time': [0,1,1,2,3,4], 'drum_speed': [0,40,50,1000,800,0],
        'water_volume': [0,5,5,3,0,0], 'water_amount': [0,5,5,5,5,5],
        'water_temp': [15,20,20,25,22,20], 'water_pressure': [0,500,500,300,0,0],
        'process_state': [0,3,11,26,49,0], 'stwf_number': [0,41,159,2907,73,0],
        'pre_wash_valve_open': [0,1,0,0,0,0], 'main_wash_valve_open': [0,0,0,0,0,0],
        'drain_open': [0,0,0,1,1,0], 'heater_power': [0,2000,2000,0,0,0],
    })
    with tempfile.TemporaryDirectory(prefix='analyzer_exe_check_') as directory:
        directory = Path(directory)
        csv = directory / 'run_simulated_values.csv'
        frame.to_csv(csv, index=False)
        package = directory / 'simulation.zip'
        pd_sync = directory / 'power_sync.csv'
        rd_sync = directory / 'machine_sync.csv'
        pd.DataFrame({'time':[0,1,2,3,4,5], 'P-E1':[2,3,2,53,53,2]}).to_csv(pd_sync,index=False)
        pd.DataFrame({'timestamp':pd.date_range('2026-10-03 10:25:56',periods=6,freq='s'),
                      'Drump speed feedback':[6,0,0,23,30,0]}).to_csv(rd_sync,index=False)
        aligned = DataEngine(str(pd_sync),str(rd_sync),DRUM_SYNC_STRATEGY)
        report = aligned.sync_report
        if (report['drum_event_timestamp'] != report['power_event_timestamp_aligned']
                or report['drum_event_elapsed_seconds'] != 3 or len(aligned.get_data()) != 6):
            raise RuntimeError('First-drum / first-power-rise synchronization failed.')
        with zipfile.ZipFile(package, 'w') as archive:
            archive.write(csv, 'test/run_simulated_values.csv')
        adapter = load_simulation_reference(package, pressure_unit='unknown', pressure_display_unit='Pa', preserve_pressure_numbers=True)
        try:
            curves = adapter.extract_curves()
            if len(curves) != 10 or len(adapter.frame) != 6:
                raise RuntimeError('CSV signals or duplicate samples were lost.')
            if curves['pressure']['value'].max() != 500 or curves['pressure'].attrs['unit'] != 'Pa':
                raise RuntimeError('Original pressure numbers or Pa label were changed.')
            if curves['actual_remaining_time']['value'].iloc[-1] != 0:
                raise RuntimeError('Actual remaining time did not reach zero.')
            bench = pd.DataFrame({'time_min':[0,1,2,3,4], 'heat valve':[0,128,0,0,0],
                                  'water pressure [mbar]':[0,500,300,0,0],
                                  'Drump Speed':[0,1200,1200,1200,0],
                                  'Drump speed feedback':[0,40,1000,800,0]})
            specs = specs_for_curves(curves)
            columns = ComparisonEngine.find_bench_columns(bench,specs)
            pressure = comparison_traces(bench,curves,columns,specs)['pressure']
            if sample_trace(pressure['bench'],1) != 500 or sample_trace(pressure['sim'],1) != 500:
                raise RuntimeError('Pressure cursor converted original numbers.')
            if columns['drum_speed'] != 'Drump speed feedback':
                raise RuntimeError('Actual RPM feedback was not selected.')
            traces = comparison_traces(bench,curves,columns,specs)['heater_power']
            sim = sample_trace(traces['sim'],1.5)
            state = sample_trace(traces['bench'],1.5)
            spec = next(spec for spec in specs if spec['key']=='heater_power')
            if format_comparison_samples(spec,sim,state,traces['bench_kind'])[2] != 'MATCH':
                raise RuntimeError('Heater watts/state mapping failed.')
            card = ComparisonEngine.generate_scorecard(bench,curves).set_index('parameter')
            if card.loc['Total Heating Active Duration','raw_val'] != '1.00 min' or card.loc['Total Heating Active Duration','status'] != 'GREEN':
                raise RuntimeError('Raw 128 heater ON time or colour band failed.')
            fig, axes, twins, error = ComparisonEngine.render_comparison_figure(bench,curves)
            if error or len(axes) != 10 or len(twins) != 1:
                raise RuntimeError('Bundled plot renderer failed.')
            fig.savefig(directory / 'comparison.png')
            plt.close(fig)
            with pd.ExcelWriter(directory / 'comparison.xlsx',engine='openpyxl') as writer:
                write_excel_frame(writer,ComparisonEngine.heater_state_report(bench,curves),'Heater_State_Comparison')
            restored = pd.read_excel(directory / 'comparison.xlsx')
            if len(restored) != 11:
                raise RuntimeError('Excel export/readback did not retain all rows.')
        finally:
            adapter.close()
    telemetry_gui_checked = False
    if sys.platform == 'win32':
        app = main.ApplianceSignalStudioPro()
        try:
            app.telemetry.load_demo()
            app.update()
            if len(app.telemetry.signals) != 10 or len(app.tabs.tabs()) != 5:
                raise RuntimeError('Bundled telemetry workspace or original workspaces are missing.')
            app.telemetry.view.current(2)
            app.telemetry.draw()
            app.telemetry.seek(99.6)
            app.update()
            if len(app.telemetry.axes) != 1 or app.telemetry.when != 99.6:
                raise RuntimeError('Bundled telemetry subsystem selector or cursor failed.')
            telemetry_gui_checked = True
        finally:
            app._close_application()
    from app_workbench_selftest import self_test as qt_self_test
    modern = qt_self_test()
    return {'ok':True, 'modern':modern, 'frozen':bool(getattr(sys,'frozen',False)),
            'python':sys.version.split()[0], 'tcl':tcl_version, 'windows_gui_checked':gui_checked, 'telemetry_gui_checked':telemetry_gui_checked,
            'pandas':pd.__version__, 'numpy':np.__version__, 'matplotlib':matplotlib.__version__,
            'openpyxl':openpyxl.__version__, 'xlrd':xlrd.__version__,
            'checks':['Tkinter','icons','ZIP/CSV import','original pressure numbers with Pa labels','actual remaining time',
                      'RPM feedback','first drum / first power-rise synchronization','128 heater ON time','difference colours',
                      'heater watts/ON-OFF cursor','plot rendering','Excel export/readback']}


def startup_error(details):
    base = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ApplianceSignalStudio'
    try:
        base.mkdir(parents=True,exist_ok=True)
        log = base / 'startup-error.log'
        log.write_text(details,encoding='utf-8')
        message = f'The analyzer could not start. Details are saved in:\n{log}'
    except OSError:
        message = 'The analyzer could not start. Run the diagnostic build for details.'
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None,message,'Appliance Signal Studio',0x10)
    elif sys.stderr is not None:
        print(message,file=sys.stderr)


def entry_main():
    parser = argparse.ArgumentParser(description='Appliance Signal Studio')
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--legacy',action='store_true')
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    report = args.report.resolve() if args.report else None
    if args.self_test:
        try:
            result = self_test()
        except Exception:
            result = {'ok':False,'error':traceback.format_exc()}
        if report:
            report.parent.mkdir(parents=True,exist_ok=True)
            report.write_text(json.dumps(result,indent=2),encoding='utf-8')
        elif sys.stdout is not None:
            print(json.dumps(result,indent=2))
        return 0 if result['ok'] else 1
    try:
        from main import run
        return run(legacy=args.legacy)
    except Exception:
        startup_error(traceback.format_exc())
        return 1


if __name__=='__main__':
    raise SystemExit(entry_main())

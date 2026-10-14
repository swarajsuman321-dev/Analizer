import os
import sys
import ctypes
import re
import json
import logging
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, colorchooser
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from PIL import Image, ImageTk

from app_data import DataEngine, DataReadError, smart_read_file, extract_datetime_series, find_power_column, find_energy_column, find_column_by_keywords, infer_pressure_units, classify_signal_kind, normalize_control_series, normalize_program_stage_series, get_column_unit, convert_signal_units, BUILTIN_SYNC_STRATEGIES
from app_plotter import DashboardPlotter
from app_telemetry import TelemetryWorkspace, install_dark_theme, signals_from_aligned, UI_FONT
from app_zoom import ZoomInteractionManager
from app_patches import PatchManager, STORAGE_DIR
from app_comparator import ComparisonEngine
from app_comparator import SIMULATION_LEGEND_SPECS
from app_image_analysis import SimulationImageAnalyzer
from app_simulation import SimulationCsvAdapter, specs_for_curves, is_simulation_frame, load_simulation_reference
from app_inspection import prepare_trace, sample_trace, format_sample, format_comparison_samples, comparison_traces, engineering_metrics
from app_support import atomic_output, write_excel_frame, configure_logging, export_timestamp

def get_app_paths():
    if getattr(sys, 'frozen', False):
        exe_path = sys.executable
        exe_dir = os.path.dirname(os.path.abspath(exe_path))
        bundle_dir = getattr(sys, '_MEIPASS', exe_dir)
    else:
        exe_path = os.path.abspath(__file__)
        exe_dir = os.path.dirname(exe_path)
        bundle_dir = exe_dir
    return exe_path, exe_dir, bundle_dir

EXE_PATH, EXE_DIR, BUNDLE_DIR = get_app_paths()

try:
    os.chdir(EXE_DIR)
except Exception:
    pass

def resource_path(relative_path):
    return os.path.join(BUNDLE_DIR, relative_path)

def storage_path(relative_path):
    return os.path.join(EXE_DIR, relative_path)


class _SavedValue:
    """Keep the plotted signal configuration independent of editable widgets."""
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def cget(self, _option):
        return self.value

try:
    myappid = 'bsh.appliancesignalstudio.workstation.2'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

def categorize_signal(col_name, pressure_unit=None):
    col_str = str(col_name).strip()
    col_clean = re.sub(r'[^a-z0-9]', ' ', col_str.lower()).strip()
    tokens = col_clean.split()

    if col_clean in [
        'store no', 'date', 'datum', 'day', 'tag', 'time e1', 'time1', 'timestamp', 'time stamp',
        'datetime', 'date time', 'date time stamp', 'clock', 'elapsed', 'elapsed time', 'relative time',
        'seconds', 'second', 'sekunden', 'time s', 'time sec', 'time seconds', 'time min', 'time minutes', 'uhrzeit'
    ] or (col_clean == 'time' and not any(u in col_str.lower() for u in ['[s]', '(s)', 'sec'])):
        return {
            'type': 'METADATA', 'name': col_str, 'panel': 'Panel 10', 'twin': False,
            'style': 'Continuous (-)', 'width': '1.0', 'enabled': False, 'color': '#888888',
            'ymin': '', 'ymax': ''
        }

    if any(k in col_clean for k in ['left time', 'remaining time', 'restzeit', 'countdown', 'dauer left']):
        return {
            'type': 'TIMER', 'name': 'Remaining Time (min)', 'panel': 'Panel 10', 'twin': False,
            'style': 'Dotted (:)', 'width': '1.2', 'enabled': False, 'color': '#708090',
            'ymin': '', 'ymax': ''
        }

    if any(k in col_clean for k in ['programmer', 'programm']):
        return {
            'type': 'PROGRAM_ID', 'name': 'Program ID', 'panel': 'Panel 10', 'twin': False,
            'style': 'Continuous (-)', 'width': '1.0', 'enabled': False, 'color': '#708090',
            'ymin': '', 'ymax': ''
        }
    if any(k in col_clean for k in ['wash stage', 'cycle state', 'program phase', 'machine state', 'state machine', 'schritt', 'phase nr', 'step nr']):
        return {
            'type': 'STAGE', 'name': 'Program Stage', 'panel': 'Panel 8', 'twin': False,
            'style': 'Continuous (-)', 'width': '1.2', 'enabled': True, 'color': '#7B2CBF',
            'ymin': '1', 'ymax': '3'
        }

    if any(k in col_clean for k in ['start pause', 'start/pause', 'run state', 'machine running']):
        return {
            'type': 'STATUS_FLAG', 'name': 'Run State (Start/Pause)', 'panel': 'Panel 10', 'twin': False,
            'style': 'Continuous (-)', 'width': '1.2', 'enabled': False, 'color': '#2E8B57',
            'ymin': '0', 'ymax': '1'
        }

    if any(k in col_clean for k in ['oob retry', 'oob_retry', 'retry times', 'unbalance retry']):
        return {
            'type': 'RETRY_COUNTER', 'name': 'OOB Retries (Count)', 'panel': 'Panel 10', 'twin': False,
            'style': 'Continuous (-)', 'width': '1.0', 'enabled': False, 'color': '#8B0000',
            'ymin': '', 'ymax': ''
        }
    if col_clean == 'oob' or any(k in col_clean for k in ['unbalance', 'unwucht', 'vibration']):
        return {
            'type': 'UNBALANCE', 'name': 'Unbalance / OOB (g)', 'panel': 'Panel 9', 'twin': False,
            'style': 'Continuous (-)', 'width': '1.2', 'enabled': False, 'color': '#DC143C',
            'ymin': '', 'ymax': ''
        }

    if any(k in col_clean for k in ['weight', 'gewicht', 'beladung', 'laundry load']) and not any(ign in col_clean for ign in ['factor', 'offset']):
        return {
            'type': 'WEIGHT', 'name': 'Load Weight (kg)', 'panel': 'Panel 9', 'twin': False,
            'style': 'Continuous (-)', 'width': '1.5', 'enabled': False, 'color': '#556B2F',
            'ymin': '', 'ymax': ''
        }

    if any(k in col_clean for k in ['temp', 'temperatur', 'temperatuer', 'temprature', 'ntc', 'pt100']) or any(u in col_str.lower() for u in ['°c', 'deg c', 'degc']):
        if any(k in col_clean for k in ['motor', 'antrieb']):
            return {
                'type': 'MOTOR_TEMP', 'name': 'Motor Temp (°C)', 'panel': 'Panel 3', 'twin': True,
                'style': 'Dotted (:)', 'width': '1.5', 'enabled': True, 'color': '#9467BD',
                'ymin': '', 'ymax': ''
            }
        elif any(k in col_clean for k in ['dest', 'destination', 'target', 'dst', 'set', 'soll', 'sollwert']):
            return {
                'type': 'TARGET_TEMP', 'name': 'Target Temp (°C)', 'panel': 'Panel 3', 'twin': False,
                'style': 'Dashed (--)', 'width': '1.5', 'enabled': True, 'color': '#D32F2F',
                'ymin': '', 'ymax': ''
            }
        elif any(k in col_clean for k in ['ambient', 'umgebung', 'room']):
            return {
                'type': 'AMBIENT_TEMP', 'name': 'Ambient Temp (°C)', 'panel': 'Panel 3', 'twin': False,
                'style': 'Dashed (--)', 'width': '1.5', 'enabled': True, 'color': '#808080',
                'ymin': '', 'ymax': ''
            }
        elif any(k in col_clean for k in ['evap', 'evaporator', 'verdampfer']):
            return {
                'type': 'EVAP_TEMP', 'name': 'Evaporator Temp (°C)', 'panel': 'Panel 3', 'twin': False,
                'style': 'Continuous (-)', 'width': '1.8', 'enabled': True, 'color': '#008080',
                'ymin': '', 'ymax': ''
            }
        elif any(k in col_clean for k in ['cabinet', 'freezer', 'fridge', 'gefaech', 'kuehl']):
            return {
                'type': 'CABINET_TEMP', 'name': 'Cabinet Temp (°C)', 'panel': 'Panel 3', 'twin': False,
                'style': 'Continuous (-)', 'width': '1.8', 'enabled': True, 'color': '#003366',
                'ymin': '', 'ymax': ''
            }
        else:
            return {
                'type': 'WATER_TEMP', 'name': 'Actual Temp (°C)', 'panel': 'Panel 3', 'twin': False,
                'style': 'Continuous (-)', 'width': '2.0', 'enabled': True, 'color': '#003366',
                'ymin': '', 'ymax': ''
            }

    if any(k in col_clean for k in ['speed', 'rpm', 'drehzahl', 'drump', 'velocity']):
        if any(k in col_clean for k in ['dest', 'target', 'dst', 'set', 'soll']):
            return {
                'type': 'TARGET_SPEED', 'name': 'Target Speed (RPM)', 'panel': 'Panel 2', 'twin': False,
                'style': 'Dashed (--)', 'width': '1.5', 'enabled': True, 'color': '#A0522D',
                'ymin': '', 'ymax': ''
            }
        elif any(k in col_clean for k in ['compressor', 'kompressor', 'verdichter']):
            return {
                'type': 'COMP_SPEED', 'name': 'Compressor Speed (RPM)', 'panel': 'Panel 2', 'twin': False,
                'style': 'Continuous (-)', 'width': '1.5', 'enabled': True, 'color': '#8B4513',
                'ymin': '', 'ymax': ''
            }
        elif 'feedback' in col_clean:
            return {
                'type': 'SPEED_FEEDBACK', 'name': 'Drum Speed Feedback (RPM)', 'panel': 'Panel 2', 'twin': False,
                'style': 'Continuous (-)', 'width': '1.5', 'enabled': True, 'color': '#0F766E',
                'ymin': '', 'ymax': ''
            }
        else:
            return {
                'type': 'SPEED', 'name': 'Drum Speed (RPM)', 'panel': 'Panel 2', 'twin': False,
                'style': 'Continuous (-)', 'width': '1.5', 'enabled': True, 'color': '#8B4513',
                'ymin': '', 'ymax': ''
            }

    if any(k in col_clean for k in ['pressure', 'druck', 'mbar', 'bar', 'pressur']) and not any(ign in col_clean for ign in ['power', 'pump']):
        unit = pressure_unit or (
            'µs' if re.search(r'\b(?:pulse|usec|microseconds?|u\s*sec|µs|μs|us)\b', col_str.lower()) else
            ("bar" if any(u in col_str.lower() for u in ['[bar]', '(bar)']) else "mbar")
        )
        if unit == 'unknown':
            return {
                'type': 'PRESSURE_UNKNOWN', 'name': 'Pressure (unit unconfirmed)',
                'panel': 'Panel 4', 'twin': False, 'style': 'Continuous (-)',
                'width': '1.2', 'enabled': False, 'color': '#475467', 'ymin': '', 'ymax': ''
            }
        if any(token in col_clean for token in ['dst', 'dest', 'target', 'setpoint']):
            title = 'Target Pressure Pulse' if unit == 'µs' else 'Target Water Pressure'
            return {
                'type': 'TARGET_PRESSURE', 'name': f"{title} ({unit})", 'panel': 'Panel 4', 'twin': False,
                'style': 'Dashed (--)', 'width': '1.2', 'enabled': False, 'color': '#34495E',
                'ymin': '', 'ymax': ''
            }
        if unit == 'µs':
            return {
                'type': 'PRESSURE_PULSE', 'name': 'Pressure Pulse (µs)', 'panel': 'Panel 4', 'twin': True,
                'style': 'Continuous (-)', 'width': '1.2', 'enabled': False, 'color': '#C2410C',
                'ymin': '', 'ymax': ''
            }
        return {
            'type': 'PRESSURE', 'name': f"Water Pressure ({unit})", 'panel': 'Panel 4', 'twin': False,
            'style': 'Continuous (-)', 'width': '1.5', 'enabled': True, 'color': '#E377C2',
            'ymin': '', 'ymax': ''
        }

    if (any(k in col_clean for k in ['volume', 'volumen', 'liter', 'litres', 'flotte', 'water level', 'fluid level']) or any(u in col_str.lower() for u in ['[l]', '(l)'])) and not any(v in col_clean for v in ['volt', 'voltage', 'urms', 'vbus']):
        if any(k in col_clean for k in ['dest', 'target', 'dst', 'set', 'soll', 'sollwert']):
            return {
                'type': 'TARGET_VOL', 'name': 'Target Vol (L)', 'panel': 'Panel 5', 'twin': False,
                'style': 'Dashed (--)', 'width': '1.5', 'enabled': True, 'color': '#BCBD22',
                'ymin': '', 'ymax': ''
            }
        else:
            return {
                'type': 'WATER_VOL', 'name': 'Actual Vol (L)', 'panel': 'Panel 5', 'twin': False,
                'style': 'Continuous (-)', 'width': '1.5', 'enabled': True, 'color': '#17BECF',
                'ymin': '', 'ymax': ''
            }

    if any(k in col_clean for k in ['door', 'lock', 'tür', 'schloss', 'turschloss', 'interlock', 'lid switch']):
        return {
            'type': 'DOOR_LOCK', 'name': 'Door Lock State', 'panel': 'Panel 6', 'twin': False,
            'style': 'Continuous (-)', 'width': '1.5', 'enabled': True, 'color': '#2CA02C',
            'ymin': '0', 'ymax': '1'
        }

    if any(k in col_clean for k in ['valve', 'vavle', 'heater', 'pump', 'pumpe', 'ventil', 'heizung', 'ctrl', 'relay', 'relais', 'damper', 'fan']) and not any(k in col_clean for k in ['power', 'energy', 'current', 'voltage', 'frequency']):
        if any(k in col_clean for k in ['inlet', 'pre', 'einlauf']):
            name, col_b = 'Inlet Valve', '#1E90FF'
        elif any(k in col_clean for k in ['out', 'main', 'haupt']):
            name, col_b = 'Main Wash Valve', '#FF8C00'
        elif any(k in col_clean for k in ['heat', 'heiz', 'defrost']):
            name, col_b = 'Heater Relay', '#D32F2F'
        elif any(k in col_clean for k in ['drain', 'ablauf', 'pump', 'pumpe', 'drain valve']):
            name, col_b = 'Drain Pump', '#2E8B57'
        elif any(k in col_clean for k in ['circulation', 'umwaelz']):
            name, col_b = 'Circulation Pump', '#20B2AA'
        elif any(k in col_clean for k in ['dispenser', 'spueler']):
            name, col_b = 'Dispenser Valve', '#BA55D3'
        elif any(k in col_clean for k in ['fan', 'luefter']):
            name, col_b = 'Fan State', '#4682B4'
        else:
            name, col_b = col_str, '#333333'
        return {
            'type': 'VALVE', 'name': name, 'panel': 'Panel 7', 'twin': False,
            'style': 'Dashed (--)', 'width': '1.5', 'enabled': True, 'color': col_b,
            'ymin': '0', 'ymax': '1'
        }

    is_energy = False
    if not any(ign in col_clean for ign in ['factor', 'set', 'dst', 'target', 'dest', 'limit']):
        if any(tok in ['wp', 'wh', 'kwh', 'mwh'] for tok in tokens) or \
           any(tok.startswith('wp') for tok in tokens) or \
           'wp e1' in col_clean or 'wp tot' in col_clean or 'wp total' in col_clean or \
           any(phrase in col_clean for phrase in ['power consumed', 'energy consumed', 'active energy', 'consumed power', 'consumed energy', 'total energy', 'wirkenergie', 'energie verbrauch', 'verbrauch']) or \
           ('energy' in tokens and not any(ign in col_clean for ign in ['meter', 'ratio'])) or \
           (col_clean == 'e' and any(u in col_str.lower() for u in ['wh', 'kwh', 'j', 'joule'])) or \
           any(u in col_str.lower() for u in ['[wh]', '(wh)', '[kwh]', '(kwh)']):
            is_energy = True

    if is_energy:
        unit = "kWh" if any(u in col_str.lower() for u in ['kwh']) else "Wh"
        return {
            'type': 'POWER_CONSUMED', 'name': f"Power Consumed ({unit})", 'panel': 'Panel 1', 'twin': True,
            'style': 'Dashed (--)', 'width': '1.8', 'enabled': True, 'color': '#FF8C00',
            'ymin': '', 'ymax': ''
        }

    is_power = False
    if not any(ign in col_clean for ign in ['factor', 'cos', 'reactive', 'apparent', 'blind', 'schein', 'pressure', 'pump']):
        if col_clean in ['p', 'p e1', 'p e2', 'p e3', 'p total', 'ptot', 'psum', 'p1', 'p2', 'p3', 'pac', 'pact', 'p meas', 'p w', 'p kw']:
            is_power = True
        elif any(phrase in col_clean for phrase in ['real power', 'active power', 'activepower', 'realpower', 'wirkleistung', 'active p', 'p active']):
            is_power = True
        elif any(tok in ['power', 'leistung'] for tok in tokens) and not any(ign in col_clean for ign in ['consumed', 'factor', 'loss', 'supply']):
            is_power = True
        elif tokens and tokens[0] == 'p' and (len(tokens) == 1 or tokens[1] in ['w', 'kw', 'watt', 'watts', 'e1', 'e2', 'e3', 'tot', 'total', 'avg', 'mean']):
            is_power = True
        elif any(u in col_str.lower() for u in ['[w]', '(w)', '[kw]', '(kw)']) and not any(u in col_str.lower() for u in ['wh', 'kwh']):
            is_power = True

    if is_power:
        unit = "kW" if any(u in col_str.lower() for u in ['kw']) else "W"
        return {
            'type': 'REAL_POWER', 'name': f"Real Power ({unit})", 'panel': 'Panel 1', 'twin': False,
            'style': 'Continuous (-)', 'width': '1.8', 'enabled': True, 'color': '#003366',
            'ymin': '', 'ymax': ''
        }

    if any(k in col_clean for k in ['fu e1', 'fu', 'freq', 'frequency', 'frequenz', 'hertz']) or col_clean == 'f' or any(u in col_str.lower() for u in ['[hz]', '(hz)']):
        return {
            'type': 'FREQUENCY', 'name': 'Frequency (Hz)', 'panel': 'Panel 8', 'twin': False,
            'style': 'Continuous (-)', 'width': '1.2', 'enabled': False, 'color': '#7F7F7F',
            'ymin': '', 'ymax': ''
        }

    if any(k in col_clean for k in ['power factor', 'powerfactor', 'cos phi', 'cosphi', 'pf e1', 'pf', 'leistungsfaktor']):
        return {
            'type': 'POWER_FACTOR', 'name': 'Power Factor (cos φ)', 'panel': 'Panel 8', 'twin': True,
            'style': 'Dotted (:)', 'width': '1.2', 'enabled': False, 'color': '#795548',
            'ymin': '0', 'ymax': '1'
        }

    if any(k in col_clean for k in ['vbus', 'v bus', 'vdc', 'u dc', 'dc bus', 'zwischenkreis', 'inverter bus']):
        return {
            'type': 'DC_VOLTAGE', 'name': 'DC Bus Voltage (V)', 'panel': 'Panel 8', 'twin': False,
            'style': 'Continuous (-)', 'width': '1.2', 'enabled': False, 'color': '#4A148C',
            'ymin': '', 'ymax': ''
        }
    is_voltage = False
    if any(k in col_clean for k in ['urms', 'voltage', 'spannung', 'mains voltage', 'netzspannung', 'u1', 'u2', 'u3']) or col_clean == 'u':
        is_voltage = True
    elif col_clean in ['u e1', 'u e2', 'u e3', 'u-e1', 'u-e2', 'u-e3']:
        is_voltage = True
    elif any(u in col_str.lower() for u in ['[v]', '(v)']) and not any(u in col_str.lower() for u in ['valve', 'vavle']):
        is_voltage = True

    if is_voltage:
        return {
            'type': 'VOLTAGE', 'name': 'Voltage (V)', 'panel': 'Panel 8', 'twin': False,
            'style': 'Continuous (-)', 'width': '1.2', 'enabled': False, 'color': '#1F77B4',
            'ymin': '', 'ymax': ''
        }

    non_electrical_qualifiers = ['temp', 'temperature', 'speed', 'rpm', 'pressure', 'volume', 'state', 'status', 'step', 'phase', 'mode', 'cycle', 'time', 'program', 'offset', 'limit', 'target', 'dest', 'left']
    is_current = False

    if any(k in col_clean for k in ['irms', 'strom', 'ampere', 'amperes', 'amp']) or any(u in col_str.lower() for u in ['[a]', '(a)', 'a_rms', 'arms']):
        is_current = True
    elif any(k in col_clean for k in ['i e1', 'i1', 'i2', 'i3', 'i rms', 'motor current', 'phase current', 'line current', 'load current', 'ac current', 'dc current']):
        is_current = True
    elif col_clean == 'i' or col_clean == 'current':
        is_current = True
    elif 'current' in tokens and not any(q in col_clean for q in non_electrical_qualifiers):
        is_current = True

    if is_current:
        return {
            'type': 'CURRENT', 'name': 'Current (A)', 'panel': 'Panel 8', 'twin': True,
            'style': 'Continuous (-)', 'width': '1.2', 'enabled': False, 'color': '#D62728',
            'ymin': '', 'ymax': ''
        }

    return {
        'type': 'OTHER', 'name': col_str, 'panel': 'Panel 8', 'twin': False,
        'style': 'Continuous (-)', 'width': '1.2', 'enabled': False, 'color': '#555555',
        'ymin': '', 'ymax': ''
    }


class ScrollableFigureHost(ttk.Frame):
    """Keep plot rows readable while adapting to the available graph width."""

    def __init__(self, master, figure, row_count):
        super().__init__(master)
        self.figure = figure
        self.row_count = max(1, row_count)
        self._resize_job = None
        self._content_size = None
        self._scrolling = False
        self._horizontal_scrolling = False
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.viewport = tk.Canvas(
            self, background='white', highlightthickness=0,
            borderwidth=0, xscrollincrement=48, yscrollincrement=48
        )
        self.viewport.grid(row=0, column=0, sticky=tk.NSEW)
        self.scrollbar = ttk.Scrollbar(
            self, orient=tk.VERTICAL, command=self.viewport.yview
        )
        self.horizontal_scrollbar = ttk.Scrollbar(
            self, orient=tk.HORIZONTAL, command=self.viewport.xview
        )
        self.viewport.configure(
            yscrollcommand=self.scrollbar.set,
            xscrollcommand=self.horizontal_scrollbar.set
        )
        self.canvas = FigureCanvasTkAgg(figure, master=self.viewport)
        layout = getattr(figure, '_signal_layout', None)
        if layout is not None:
            layout.on_size_change = self._queue_resize
        self.plot_widget = self.canvas.get_tk_widget()
        self.window_id = self.viewport.create_window(
            (0, 0), window=self.plot_widget, anchor=tk.NW
        )
        self.viewport.bind('<Configure>', self._queue_resize)
        # The graph retains wheel zoom and Shift+wheel Y zoom. Alt+wheel
        # scrolls the larger figure when the readable rows need more height.
        self.viewport.bind('<Alt-MouseWheel>', self._scroll_blocks)
        self.plot_widget.bind('<Alt-MouseWheel>', self._scroll_blocks)
        self.viewport.bind('<Alt-Shift-MouseWheel>', self._scroll_blocks)
        self.plot_widget.bind('<Alt-Shift-MouseWheel>', self._scroll_blocks)
        self.bind('<Destroy>', self._cancel_resize, add='+')
        self._resize_job = self.after_idle(self._resize_content)

    def _queue_resize(self, _event=None):
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(60, self._resize_content)

    def _minimum_height(self, width):
        layout = getattr(self.figure, '_signal_layout', None)
        minimum_height = getattr(layout, 'minimum_height', None)
        minimum = minimum_height(width) if callable(minimum_height) else None
        if minimum is None:
            minimum = getattr(self.figure, '_signal_minimum_height_px', None)
        return int(minimum or (110 + 155 * self.row_count))

    def _minimum_width(self):
        layout = getattr(self.figure, '_signal_layout', None)
        minimum_width = getattr(layout, 'minimum_width', None)
        return int(minimum_width()) if callable(minimum_width) else 500

    def _resize_content(self):
        self._resize_job = None
        if not self.winfo_exists():
            return
        host_width, host_height = self.winfo_width(), self.winfo_height()
        if host_width <= 1 or host_height <= 1:
            return
        minimum_width = self._minimum_width()
        vertical_width = self.scrollbar.winfo_reqwidth()
        horizontal_height = self.horizontal_scrollbar.winfo_reqheight()
        # Start from the full client area on every resize. Existing bars must
        # not keep one another visible after the window grows. A newly required
        # bar may make the other necessary, so resolve both before applying.
        horizontal_scrolling = scrolling = False
        for _ in range(3):
            viewport_width = max(1, host_width - (vertical_width if scrolling else 0))
            viewport_height = max(1, host_height - (horizontal_height if horizontal_scrolling else 0))
            content_width = max(viewport_width, minimum_width)
            next_horizontal = horizontal_scrolling or minimum_width > viewport_width
            next_vertical = scrolling or self._minimum_height(content_width) > viewport_height + 1
            if (next_horizontal, next_vertical) == (horizontal_scrolling, scrolling):
                break
            horizontal_scrolling, scrolling = next_horizontal, next_vertical

        bars_changed = (
            horizontal_scrolling != self._horizontal_scrolling or
            scrolling != self._scrolling
        )
        if horizontal_scrolling:
            self.horizontal_scrollbar.grid(row=1, column=0, sticky=tk.EW)
        else:
            self.horizontal_scrollbar.grid_remove()
            if self._horizontal_scrolling:
                self.viewport.xview_moveto(0)
        if scrolling:
            self.scrollbar.grid(row=0, column=1, sticky=tk.NS)
        else:
            self.scrollbar.grid_remove()
            if self._scrolling:
                self.viewport.yview_moveto(0)
        self._horizontal_scrolling, self._scrolling = horizontal_scrolling, scrolling
        if bars_changed:
            self.update_idletasks()
        content_width = max(self.viewport.winfo_width(), minimum_width)
        content_height = max(
            self.viewport.winfo_height(), self._minimum_height(content_width)
        )
        size = (content_width, content_height)
        if size != self._content_size:
            self._content_size = size
            # Updating the embedded TkAgg widget triggers Matplotlib's own
            # resize event, preserving the same axes, zoom and cursor objects.
            self.viewport.itemconfigure(
                self.window_id, width=content_width, height=content_height
            )
            self.viewport.configure(
                scrollregion=(0, 0, content_width, content_height)
            )
            self.figure.set_size_inches(
                content_width / self.figure.dpi,
                content_height / self.figure.dpi, forward=False
            )
            layout = getattr(self.figure, '_signal_layout', None)
            if layout is not None:
                layout.reflow(content_width, content_height)
            self.canvas.draw_idle()

    def _scroll_blocks(self, event):
        steps = int(-event.delta / 120)
        if not steps and event.delta:
            steps = -1 if event.delta > 0 else 1
        if event.state & 0x0001 and self._horizontal_scrolling:
            self.viewport.xview_scroll(steps, 'units')
        elif self._scrolling:
            self.viewport.yview_scroll(steps, 'units')
        return 'break'

    def _cancel_resize(self, event):
        if event.widget is self:
            for attribute in ('_idle_draw_id', '_event_loop_id'):
                callback = getattr(self.canvas, attribute, None)
                if callback is not None:
                    try:
                        self.plot_widget.after_cancel(callback)
                    except tk.TclError:
                        pass
                    setattr(self.canvas, attribute, None)
            layout = getattr(self.figure, '_signal_layout', None)
            if layout is not None and layout.on_size_change == self._queue_resize:
                layout.on_size_change = None
            if layout is not None and hasattr(layout, 'dispose'):
                layout.dispose()
            if self._resize_job is not None:
                self.after_cancel(self._resize_job)
                self._resize_job = None


class ApplianceSignalStudioPro(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Appliance Signal Studio - Industrial Test Bench Workstation")
        self.geometry("1680x980")
        self.minsize(1200, 750)
        install_dark_theme(self)

        ico_file = resource_path("app_icon.ico")
        png_file = resource_path("app_logo.png")

        if os.path.exists(ico_file):
            try: self.iconbitmap(ico_file)
            except Exception: pass

        if os.path.exists(png_file):
            try:
                self._app_icon_photo = tk.PhotoImage(file=png_file)
                self.iconphoto(True, self._app_icon_photo)
            except Exception: pass

        self.patch_manager = PatchManager()
        self.aligned_df = None
        self.current_fig = None
        self.current_axes = []
        self.current_twin_axes = []
        self.c1_lines = []
        self.c2_lines = []
        self.zoom_manager = None
        self.grid_widgets = {}

        self.var_annotate_peak = tk.BooleanVar(value=True)
        self.var_valve_overlap = tk.BooleanVar(value=False)
        self.var_grid_toggle = tk.BooleanVar(value=True)
        self.var_show_legends = tk.BooleanVar(value=False)

        self.comp_sim_csv_path = None
        self.comp_csv_adapter = None
        self.comp_csv_settings = {'time_unit': 'min', 'pressure_unit': 'unknown', 'remaining_time_unit': 'min', 'pressure_display_unit': 'Pa', 'preserve_pressure_numbers': True}
        self.comp_sim_img_path = None
        self.comp_raw_path = None
        self.comp_raw_df = None
        self.comp_sim_curves = None
        self.comp_image_analyzer = None
        self.comp_scorecard_df = None
        self.comp_fig = None
        self.comp_axes = []
        self.comp_twin_axes = []
        self.comp_canvas = None
        self.comp_zoom_manager = None
        self.comp_signal_visibility = {}
        self.comp_signal_bench_columns = {}
        self.comp_cursor_lines = []
        self.comp_cursor_traces = {}
        self.comp_cursor_time = None
        self.comp_tolerances = {'duration_percent': 10.0, 'peak_speed_rpm': 50.0,
                                'spin_start_minutes': 15.0}
        self.comp_image_calibration = {}
        self._cursor_trace_cache = {}
        self._cursor_cache_frame = None
        self._kpi_rows = []
        self.logger = configure_logging(STORAGE_DIR)
        self.protocol('WM_DELETE_WINDOW', self._close_application)

        self.bind('<Control-s>', self._save_active_report)
        self.bind('<Control-S>', self._save_active_report)
        self.bind('<BackSpace>', lambda e: self._zoom_back_trigger())
        self.bind('<Alt-Left>', lambda e: self._zoom_back_trigger())
        self.bind('<Alt-Right>', lambda e: self._zoom_forward_trigger())
        self.bind('<Escape>', lambda e: self._set_tool("HAND"))

        self._build_ui()

    def report_callback_exception(self, exc_type, exc_value, exc_traceback):
        logger = getattr(self, 'logger', logging.getLogger('appliance_signal_studio'))
        logger.error('Application action failed', exc_info=(exc_type, exc_value, exc_traceback))
        messagebox.showerror('Action Failed',
                             f'{exc_value}\n\nDetails are recorded in application.log.', parent=self)

    def _close_application(self):
        for name in ('zoom_manager', 'comp_zoom_manager'):
            manager = getattr(self, name, None)
            if manager is not None and hasattr(manager, 'dispose'):
                manager.dispose()
        for figure in (self.current_fig, self.comp_fig):
            if figure is not None:
                layout = getattr(figure, '_signal_layout', None)
                if layout is not None and hasattr(layout, 'dispose'):
                    layout.dispose()
                plt.close(figure)
        self.destroy()

    def _active_zoom_manager(self):
        if self.tabs.select() == str(self.tab_comparator):
            return self.comp_zoom_manager
        if self.tabs.select() == str(self.tab_dashboard):
            return self.zoom_manager
        return None

    def _dispose_manager(self, name):
        manager = getattr(self, name, None)
        if manager is not None and hasattr(manager, 'dispose'):
            manager.dispose()
        setattr(self, name, None)

    def _save_active_report(self, _event=None):
        if self.tabs.select() == str(self.tab_telemetry):
            self.telemetry.export_image()
            return 'break'
        if self.tabs.select() == str(self.tab_comparator):
            self.export_comp_excel()
        else:
            self.export_excel()
        return 'break'

    def _build_ui(self):
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill=tk.BOTH, expand=True)

        self.tab_telemetry = ttk.Frame(self.tabs)
        self.tabs.add(self.tab_telemetry, text="Telemetry")
        self.telemetry = TelemetryWorkspace(self.tab_telemetry, self)
        self.telemetry.pack(fill=tk.BOTH, expand=True)

        self.tab_config = ttk.Frame(self.tabs)
        self.tab_dashboard = ttk.Frame(self.tabs)
        self.tab_comparator = ttk.Frame(self.tabs)
        self.tab_patches = ttk.Frame(self.tabs)

        self.tabs.add(self.tab_config, text="Data & Signal Mapping")
        self.tabs.add(self.tab_dashboard, text="Engineering Dashboard")
        self.tabs.add(self.tab_comparator, text="Simulation vs. Bench")
        self.tabs.add(self.tab_patches, text="Plugins & Patches")

        self._setup_config_tab()
        self._setup_dashboard_tab()
        self._setup_comparator_tab()
        self.patch_manager.on_change = self._refresh_sync_options
        self.patch_manager.setup_ui(self.tab_patches)

    def _refresh_sync_options(self):
        choices = list(BUILTIN_SYNC_STRATEGIES) + sorted(self.patch_manager.custom_sync_hooks)
        self.sync_mode.configure(values=choices)
        if self.sync_mode.get() not in choices:
            self.sync_mode.set('Raw Timestamps (No Shift)')

    def _setup_config_tab(self):
        f_frame = ttk.LabelFrame(self.tab_config, text="1. Load Input Datasets (Supports any CSV, Excel .xlsx, TXT, or TSV)", padding=10)
        f_frame.pack(fill=tk.X, padx=15, pady=6)

        ttk.Button(f_frame, text="📁 Power / Primary Data", command=self.load_pd).grid(row=0, column=0, padx=5, pady=5)
        self.lbl_pd = ttk.Label(f_frame, text="No file selected", foreground="gray", width=28)
        self.lbl_pd.grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Button(f_frame, text="📁 Operational / Machine Data", command=self.load_rd).grid(row=0, column=2, padx=5, pady=5)
        self.lbl_rd = ttk.Label(f_frame, text="No file selected", foreground="gray", width=28)
        self.lbl_rd.grid(row=0, column=3, sticky=tk.W, padx=5)

        ttk.Button(f_frame, text="🔍 Auto-Map Channels & Signals", command=self.populate_signal_grid).grid(row=0, column=4, padx=15)
        ttk.Button(f_frame, text="🔄 Reset Workspace", command=self.reset_all).grid(row=0, column=5, padx=5)

        s_frame = ttk.LabelFrame(self.tab_config, text="2. Alignment, Synchronization & Layout Options", padding=10)
        s_frame.pack(fill=tk.X, padx=15, pady=6)

        ttk.Label(s_frame, text="Sync Strategy:").grid(row=0, column=0, padx=5, pady=4, sticky=tk.W)
        self.sync_mode = ttk.Combobox(
            s_frame,
            values=BUILTIN_SYNC_STRATEGIES,
            width=44,
            state="readonly"
        )
        self.sync_mode.set("Intelligent (Heater ON to >1.5kW Spike)")
        self.sync_mode.grid(row=0, column=1, padx=5, pady=4)

        ttk.Label(s_frame, text="Offset (Min):").grid(row=0, column=2, padx=5, pady=4)
        self.manual_offset = ttk.Entry(s_frame, width=8)
        self.manual_offset.insert(0, "0.0")
        self.manual_offset.grid(row=0, column=3, padx=5, pady=4)

        ttk.Label(s_frame, text="Graph Title:").grid(row=0, column=4, padx=5, pady=4)
        self.txt_title = ttk.Entry(s_frame, width=38)
        self.txt_title.insert(0, "Cycle Test - Thermal & Dynamic Profile")
        self.txt_title.grid(row=0, column=5, padx=5, pady=4)

        ttk.Label(s_frame, text='Drum-start sync uses first rotation, not final high-speed spin. Review detected events under Data Quality.',
                  foreground='#b2bac7').grid(row=2, column=0, columnspan=6, sticky=tk.W, padx=5, pady=3)

        opt_frame = ttk.Frame(s_frame)
        opt_frame.grid(row=1, column=0, columnspan=6, sticky=tk.W, pady=4)

        ttk.Checkbutton(opt_frame, text="Show Legends", variable=self.var_show_legends, command=self._on_legend_toggle).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(opt_frame, text="Show Grid", variable=self.var_grid_toggle, command=self._on_grid_toggle).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(opt_frame, text="Inlet / Drain Overlap", variable=self.var_valve_overlap).pack(side=tk.LEFT, padx=5)
        ttk.Checkbutton(opt_frame, text="Annotate Peak Motor Power", variable=self.var_annotate_peak).pack(side=tk.LEFT, padx=5)

        ttk.Label(opt_frame, text="Font Size:").pack(side=tk.LEFT, padx=(20, 5))
        self.slider_font = ttk.Scale(opt_frame, from_=7, to=14, orient=tk.HORIZONTAL, length=90)
        self.slider_font.set(9)
        self.slider_font.pack(side=tk.LEFT)

        grid_frame = ttk.LabelFrame(self.tab_config, text="3. Signal Customization & Channel Mapping (Auto-Discovered from Files)", padding=8)
        grid_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=6)

        sel_bar = ttk.Frame(grid_frame)
        sel_bar.pack(fill=tk.X, pady=2)
        ttk.Button(sel_bar, text="☑ Select All", command=self.select_all_signals).pack(side=tk.LEFT, padx=4)
        ttk.Button(sel_bar, text="☐ Deselect All", command=self.deselect_all_signals).pack(side=tk.LEFT, padx=4)
        ttk.Label(sel_bar, text="💡 Each signal has its own colored Y scale. Right Y-Axis? chooses its side; blank Y-Min/Max auto-fit.", foreground="#969da9").pack(side=tk.LEFT, padx=15)

        self.canvas_grid = tk.Canvas(grid_frame, bg="#111214", highlightthickness=0)
        scrollbar = ttk.Scrollbar(grid_frame, orient=tk.VERTICAL, command=self.canvas_grid.yview)
        self.scroll_frame = ttk.Frame(self.canvas_grid)

        self.scroll_frame.bind("<Configure>", lambda e: self.canvas_grid.configure(scrollregion=self.canvas_grid.bbox("all")))
        self.canvas_grid.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas_grid.configure(yscrollcommand=scrollbar.set)

        self.canvas_grid.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        b_frame = ttk.Frame(self.tab_config)
        b_frame.pack(fill=tk.X, padx=15, pady=8)
        ttk.Button(b_frame, text="💾 Save Preset JSON", command=self.save_preset).pack(side=tk.LEFT, padx=5)
        ttk.Button(b_frame, text="📂 Load Preset JSON", command=self.load_preset).pack(side=tk.LEFT, padx=5)
        ttk.Button(b_frame, text="📊 Save Aligned Data (Excel)", command=self.export_excel).pack(side=tk.LEFT, padx=5)
        ttk.Button(b_frame, text="🚀 Render Dashboard", command=self.execute_and_view).pack(side=tk.RIGHT, padx=5)

    def _setup_dashboard_tab(self):
        top_header = ttk.Frame(self.tab_dashboard, padding=(8, 4))
        top_header.pack(side=tk.TOP, fill=tk.X)

        self.export_box = ttk.LabelFrame(top_header, text="💾 Save & Export Suite", padding=(6, 3))
        self.export_box.pack(side=tk.RIGHT, padx=6)

        self.btn_save_excel = ttk.Button(self.export_box, text="📊 Save Excel [Ctrl+S]", command=self.export_excel)
        self.btn_save_excel.pack(side=tk.LEFT, padx=3, pady=1)

        self.btn_save_img = ttk.Button(self.export_box, text="💾 Save Image (PNG/PDF)", command=self.export_image)
        self.btn_save_img.pack(side=tk.LEFT, padx=3, pady=1)

        self.btn_save_csv = ttk.Button(self.export_box, text="📋 Save CSV", command=self.export_csv)
        self.btn_save_csv.pack(side=tk.LEFT, padx=3, pady=1)
        ttk.Button(self.export_box, text='Data Quality', command=self.show_data_quality).pack(side=tk.LEFT, padx=3, pady=1)

        title_box = ttk.Frame(top_header)
        title_box.pack(side=tk.LEFT, fill=tk.X, expand=True)

        png_file = resource_path("app_logo.png")
        if os.path.exists(png_file):
            try:
                pil_img = Image.open(png_file).resize((28, 28), Image.Resampling.LANCZOS)
                self.header_logo = ImageTk.PhotoImage(pil_img)
                lbl_icon = ttk.Label(title_box, image=self.header_logo)
                lbl_icon.pack(side=tk.LEFT, padx=(2, 6))
            except Exception: pass

        self.lbl_test_title = ttk.Label(
            title_box, text="Program: Cycle Analysis", font=(UI_FONT, 11, "bold"), foreground="#96cdf1"
        )
        self.lbl_test_title.pack(side=tk.LEFT, padx=2)
        self.lbl_data_notice = ttk.Label(self.tab_dashboard, foreground='#a4aebb', wraplength=1300)
        self.lbl_data_notice.pack(side=tk.TOP, fill=tk.X, padx=12)

        top_tools = ttk.Frame(self.tab_dashboard, padding=(8, 2))
        top_tools.pack(side=tk.TOP, fill=tk.X)

        quick_load_box = ttk.LabelFrame(top_tools, text="Quick Data Load", padding=(6, 3))
        quick_load_box.pack(side=tk.LEFT, padx=(0, 6))

        ttk.Button(quick_load_box, text="📁 Power Data", command=self.load_pd).pack(side=tk.LEFT, padx=2, pady=1)
        self.lbl_pd_quick = ttk.Label(quick_load_box, text="No file", foreground="gray", width=12)
        self.lbl_pd_quick.pack(side=tk.LEFT, padx=2)

        ttk.Button(quick_load_box, text="📁 Machine Data", command=self.load_rd).pack(side=tk.LEFT, padx=2, pady=1)
        self.lbl_rd_quick = ttk.Label(quick_load_box, text="No file", foreground="gray", width=12)
        self.lbl_rd_quick.pack(side=tk.LEFT, padx=2)

        ttk.Button(quick_load_box, text="🚀 Re-Plot", command=self.execute_and_view).pack(side=tk.LEFT, padx=3, pady=1)
        ttk.Button(quick_load_box, text="⚙️ Config", command=lambda: self.tabs.select(self.tab_config)).pack(side=tk.LEFT, padx=2, pady=1)

        overlay_strip = ttk.LabelFrame(top_tools, text="Display & Overlay Options", padding=(6, 3))
        overlay_strip.pack(side=tk.LEFT, padx=4)

        ttk.Checkbutton(overlay_strip, text="Legends", variable=self.var_show_legends, command=self._on_legend_toggle).pack(side=tk.LEFT, padx=3)
        ttk.Checkbutton(overlay_strip, text="Grid", variable=self.var_grid_toggle, command=self._on_grid_toggle).pack(side=tk.LEFT, padx=3)
        ttk.Checkbutton(overlay_strip, text="Inlet / Drain Overlap", variable=self.var_valve_overlap, command=self._quick_replot).pack(side=tk.LEFT, padx=3)
        ttk.Checkbutton(overlay_strip, text="Peak Motor", variable=self.var_annotate_peak, command=self._quick_replot).pack(side=tk.LEFT, padx=3)
        ttk.Label(overlay_strip, text="Signal colors identify each trace and scale", foreground="#969da9", font=(UI_FONT, 8, "italic")).pack(side=tk.LEFT, padx=(4, 2))

        nav_strip = ttk.LabelFrame(top_tools, text="Interaction Tool", padding=(6, 3))
        nav_strip.pack(side=tk.LEFT, padx=4)

        self.btn_hand = ttk.Button(nav_strip, text="✋ Hand [ESC]", command=lambda: self._set_tool("HAND"))
        self.btn_hand.pack(side=tk.LEFT, padx=2, pady=1)

        self.btn_cursor = ttk.Button(nav_strip, text="📍 Cursor", command=lambda: self._set_tool("CURSOR"))
        self.btn_cursor.pack(side=tk.LEFT, padx=2, pady=1)

        self.btn_zx = ttk.Button(nav_strip, text="🔍 Zoom X", command=lambda: self._set_tool("ZOOM_X"))
        self.btn_zx.pack(side=tk.LEFT, padx=2, pady=1)

        self.btn_zy = ttk.Button(nav_strip, text="🔍 Zoom Y", command=lambda: self._set_tool("ZOOM_Y"))
        self.btn_zy.pack(side=tk.LEFT, padx=2, pady=1)

        self.btn_zxy = ttk.Button(nav_strip, text="🔎 Zoom XY", command=lambda: self._set_tool("ZOOM_XY"))
        self.btn_zxy.pack(side=tk.LEFT, padx=2, pady=1)

        self.btn_zoom_back = ttk.Button(nav_strip, text="◀ Zoom Back", command=self._zoom_back_trigger)
        self.btn_zoom_back.pack(side=tk.LEFT, padx=2, pady=1)

        self.btn_zoom_fwd = ttk.Button(nav_strip, text="▶ Zoom Fwd", command=self._zoom_forward_trigger)
        self.btn_zoom_fwd.pack(side=tk.LEFT, padx=2, pady=1)

        ttk.Button(nav_strip, text="🔄 Reset Zoom", command=self._reset_zoom_trigger).pack(side=tk.LEFT, padx=2, pady=1)

        bot_bar = ttk.Frame(self.tab_dashboard, padding=(8, 4), relief="groove")
        bot_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.lbl_c1_info = ttk.Label(bot_bar, text="🔴 C1: 0.00 min", font=(UI_FONT, 9, "bold"), foreground="#ff9393")
        self.lbl_c1_info.pack(side=tk.LEFT, padx=6)

        self.lbl_c2_info = ttk.Label(bot_bar, text="🔵 C2: Off", font=(UI_FONT, 9, "bold"), foreground="#96cdf1")
        self.lbl_c2_info.pack(side=tk.LEFT, padx=6)

        self.lbl_diff_info = ttk.Label(bot_bar, text="⏱ Δt: —", font=(UI_FONT, 9, "bold"), foreground="#b8e67f")
        self.lbl_diff_info.pack(side=tk.LEFT, padx=6)

        self.lbl_live_p = ttk.Label(bot_bar, text="⚡ P: — W", font=(UI_FONT, 9, "bold"), foreground="#96cdf1")
        self.lbl_live_p.pack(side=tk.LEFT, padx=6)

        self.lbl_live_e = ttk.Label(bot_bar, text="🔋 E: — Wh", font=(UI_FONT, 9, "bold"), foreground="#B85D00")
        self.lbl_live_e.pack(side=tk.LEFT, padx=6)

        self.lbl_hover_info = ttk.Label(bot_bar, text="🖱 Mouse: —", font=(UI_FONT, 9), foreground="#969da9")
        self.lbl_hover_info.pack(side=tk.LEFT, padx=8)

        ttk.Button(bot_bar, text="📏 Toggle Dual Cursor (Δt)", command=self._toggle_dual_cursor_btn).pack(side=tk.LEFT, padx=8)

        lbl_target = ttk.Label(bot_bar, text="Click Moves:", font=(UI_FONT, 9, "bold"), foreground="#c2c7d0")
        lbl_target.pack(side=tk.LEFT, padx=(4, 2))

        self.var_cursor_target = tk.StringVar(value="C1")
        self.rb_c1 = ttk.Radiobutton(bot_bar, text="🔴 C1", value="C1", variable=self.var_cursor_target, command=self._on_target_changed)
        self.rb_c1.pack(side=tk.LEFT, padx=2)

        self.rb_c2 = ttk.Radiobutton(bot_bar, text="🔵 C2", value="C2", variable=self.var_cursor_target, command=self._on_target_changed)
        self.rb_c2.pack(side=tk.LEFT, padx=2)

        ttk.Button(bot_bar, text="⏭ C2 End", command=self._jump_c2_end).pack(side=tk.RIGHT, padx=2)
        ttk.Button(bot_bar, text="⏮ C2 Start", command=self._jump_c2_start).pack(side=tk.RIGHT, padx=2)
        ttk.Button(bot_bar, text="⏭ C1 End", command=self._jump_c1_end).pack(side=tk.RIGHT, padx=2)
        ttk.Button(bot_bar, text="⏮ C1 Start", command=self._jump_c1_start).pack(side=tk.RIGHT, padx=2)

        main_split = ttk.PanedWindow(self.tab_dashboard, orient=tk.HORIZONTAL)
        main_split.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

        left_sidebar = ttk.Frame(main_split, width=440)
        self.dashboard_split = main_split
        self.dashboard_sidebar = left_sidebar
        self.dashboard_sidebar_previous_width = 440
        self.dashboard_sidebar_expanded = True
        main_split.add(left_sidebar, weight=0)

        self.dashboard_sidebar_content = ttk.Frame(left_sidebar)
        self.dashboard_sidebar_content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.btn_sidebar_toggle = tk.Button(
            left_sidebar, text="◀", width=2, command=self._toggle_dashboard_sidebar,
            bg="#25272b", fg="#c4ff84", activebackground="#34383d",
            activeforeground="#123A5A", relief=tk.FLAT, bd=0,
            font=(UI_FONT, 11, "bold"), cursor="hand2"
        )
        self.btn_sidebar_toggle.pack(side=tk.RIGHT, fill=tk.Y)

        live_values_group = ttk.Frame(self.dashboard_sidebar_content)
        live_values_group.pack(fill=tk.X, padx=5, pady=4)

        caliper_card = ttk.LabelFrame(live_values_group, text="📍 Active Caliper & Real-Time Readout", padding=6)
        caliper_card.pack(fill=tk.X, padx=5, pady=4)

        row_c_frame = ttk.Frame(caliper_card)
        row_c_frame.pack(fill=tk.X)
        self.lbl_caliper_c1 = ttk.Label(row_c_frame, text="🔴 C1: 0.00 min", font=(UI_FONT, 9, "bold"), foreground="#ff9393")
        self.lbl_caliper_c1.pack(side=tk.LEFT, padx=4)

        self.lbl_caliper_c2 = ttk.Label(row_c_frame, text="🔵 C2: Off", font=(UI_FONT, 9, "bold"), foreground="#96cdf1")
        self.lbl_caliper_c2.pack(side=tk.LEFT, padx=8)

        row_delta_frame = ttk.Frame(caliper_card)
        row_delta_frame.pack(fill=tk.X, pady=(2, 0))
        self.lbl_caliper_dt = ttk.Label(row_delta_frame, text="⏱ Δt: —", font=(UI_FONT, 9, "bold"), foreground="#b8e67f")
        self.lbl_caliper_dt.pack(side=tk.LEFT, padx=4)

        self.lbl_caliper_pe = ttk.Label(row_delta_frame, text="⚡ P: — W  |  🔋 E: — Wh", font=(UI_FONT, 9, "bold"), foreground="#96cdf1")
        self.lbl_caliper_pe.pack(side=tk.RIGHT, padx=4)

        lbl_frame_sig = ttk.LabelFrame(live_values_group, text="Analog & Discrete Signals (C1, C2 & Δ)", padding=5)
        lbl_frame_sig.pack(fill=tk.BOTH, expand=True, padx=5, pady=3)
        lbl_frame_sig.rowconfigure(0, weight=1)
        lbl_frame_sig.columnconfigure(0, weight=1)

        sig_columns = ("name", "c1", "c2", "delta", "min", "max", "mean")
        self.sig_tree = ttk.Treeview(lbl_frame_sig, columns=sig_columns, show="headings", height=8)
        self.sig_tree.heading("name", text="Signal")
        self.sig_tree.heading("c1", text="C1 (Red)")
        self.sig_tree.heading("c2", text="C2 (Blue)")
        self.sig_tree.heading("delta", text="Δ (C2-C1)")
        self.sig_tree.heading("min", text="Min")
        self.sig_tree.heading("max", text="Max")
        self.sig_tree.heading("mean", text="Mean")

        self.sig_tree.column("name", width=180, minwidth=150, anchor=tk.W)
        self.sig_tree.column("c1", width=68, minwidth=68, anchor=tk.E)
        self.sig_tree.column("c2", width=68, minwidth=68, anchor=tk.E)
        self.sig_tree.column("delta", width=68, minwidth=68, anchor=tk.E)
        self.sig_tree.column("min", width=48, minwidth=48, anchor=tk.E)
        self.sig_tree.column("max", width=48, minwidth=48, anchor=tk.E)
        self.sig_tree.column("mean", width=48, minwidth=48, anchor=tk.E)

        sig_scroll = ttk.Scrollbar(lbl_frame_sig, orient=tk.VERTICAL, command=self.sig_tree.yview)
        sig_scroll_horizontal = ttk.Scrollbar(lbl_frame_sig, orient=tk.HORIZONTAL, command=self.sig_tree.xview)
        self.sig_tree.configure(yscrollcommand=sig_scroll.set, xscrollcommand=sig_scroll_horizontal.set)
        self.sig_tree.grid(row=0, column=0, sticky=tk.NSEW)
        sig_scroll.grid(row=0, column=1, sticky=tk.NS)
        sig_scroll_horizontal.grid(row=1, column=0, sticky=tk.EW)

        self.sig_tree.bind("<Button-3>", self._show_tree_context_menu)

        lbl_frame_kpi = ttk.LabelFrame(self.dashboard_sidebar_content, text="Calculated Values & Engineering KPIs", padding=5)
        lbl_frame_kpi.pack(fill=tk.BOTH, expand=True, padx=5, pady=3)

        kpi_columns = ("kpi", "val")
        self.kpi_tree = ttk.Treeview(lbl_frame_kpi, columns=kpi_columns, show="headings", height=6)
        self.kpi_tree.heading("kpi", text="Engineering Metric")
        self.kpi_tree.heading("val", text="Result")
        self.kpi_tree.column("kpi", width=220, anchor=tk.W)
        self.kpi_tree.column("val", width=160, anchor=tk.E)

        kpi_scroll = ttk.Scrollbar(lbl_frame_kpi, orient=tk.VERTICAL, command=self.kpi_tree.yview)
        self.kpi_tree.configure(yscrollcommand=kpi_scroll.set)
        self.kpi_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        kpi_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        side_save_box = ttk.LabelFrame(self.dashboard_sidebar_content, text="💾 Save / Export Report", padding=6)
        side_save_box.pack(fill=tk.X, padx=5, pady=4)

        ttk.Button(side_save_box, text="📊 Save to Excel Workbook (.xlsx)", command=self.export_excel).pack(fill=tk.X, pady=2)
        ttk.Button(side_save_box, text="💾 Save Graph Image (PNG/PDF)", command=self.export_image).pack(fill=tk.X, pady=2)
        ttk.Button(side_save_box, text="📋 Save Synchronized CSV", command=self.export_csv).pack(fill=tk.X, pady=2)

        self.plot_container = ttk.Frame(main_split)
        main_split.add(self.plot_container, weight=4)

    def _on_legend_toggle(self):
        show = self.var_show_legends.get()
        layout = getattr(self.current_fig, '_signal_layout', None)
        if layout is not None:
            layout.set_show_legends(show)
            host = getattr(self, 'dashboard_figure_host', None)
            if host is not None and host.winfo_exists():
                host._queue_resize()
            if self.zoom_manager and self.zoom_manager.canvas:
                self.zoom_manager.canvas.draw_idle()
            return
        all_axes = list(self.current_axes or []) + list(self.current_twin_axes or [])
        for ax in all_axes:
            leg = ax.get_legend()
            if leg:
                leg.set_visible(show)
        if self.zoom_manager and self.zoom_manager.canvas:
            self.zoom_manager.canvas.draw_idle()

    def _toggle_dashboard_sidebar(self):
        """Collapse the results sidebar horizontally to give the graph room."""
        if self.dashboard_sidebar_expanded:
            sash_position = self.dashboard_split.sashpos(0)
            if sash_position > 60:
                self.dashboard_sidebar_previous_width = sash_position
            self.dashboard_sidebar_content.pack_forget()
            self.dashboard_sidebar_expanded = False
            self.btn_sidebar_toggle.config(text="▶")
            self.dashboard_sidebar.configure(width=36)
            self.dashboard_split.update_idletasks()
            self.dashboard_split.sashpos(0, 36)
        else:
            self.dashboard_sidebar.configure(width=self.dashboard_sidebar_previous_width)
            self.dashboard_sidebar_content.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            self.dashboard_sidebar_expanded = True
            self.btn_sidebar_toggle.config(text="◀")
            self.dashboard_split.update_idletasks()
            self.dashboard_split.sashpos(0, self.dashboard_sidebar_previous_width)

    def _on_grid_toggle(self):
        show = self.var_grid_toggle.get()
        if self.current_axes:
            for ax in self.current_axes:
                if show:
                    ax.grid(True, linestyle=':', alpha=0.6)
                else:
                    ax.grid(False)
            if self.zoom_manager and self.zoom_manager.canvas:
                self.zoom_manager.canvas.draw_idle()

    def _quick_replot(self):
        if self.aligned_df is None or self.aligned_df.empty or getattr(self, 'dashboard_inputs_changed', False):
            self.execute_and_view()
            return

        try:
            cur_xlim = self.current_axes[0].get_xlim() if self.current_axes else None
            cursor_state = self._capture_dashboard_cursors()

            options = {
                'title': self.txt_title.get(),
                'font_size': int(self.slider_font.get()),
                'show_grid': self.var_grid_toggle.get(),
                'show_legends': self.var_show_legends.get(),
                'annotate_peak': self.var_annotate_peak.get(),
                'highlight_overlap': self.var_valve_overlap.get(),
                'custom_plot_hooks': self.patch_manager.custom_plot_hooks
            }

            fig, axes, twin_axes, c1_lines, c2_lines, error_msg = DashboardPlotter.render(
                self.aligned_df, self.grid_widgets, options
            )
            if error_msg:
                messagebox.showwarning("Notice", error_msg)
                return

            self._dispose_manager('zoom_manager')
            for w in self.plot_container.winfo_children():
                w.destroy()
            if self.current_fig is not None:
                plt.close(self.current_fig)

            if cur_xlim and axes:
                for ax in axes:
                    ax.set_xlim(cur_xlim)

            self.current_fig = fig
            self.dashboard_grid_widgets = self._freeze_signal_settings()
            self.dashboard_result_settings['Signals'] = self._signal_settings()
            self.current_axes = axes
            self.current_twin_axes = twin_axes
            self.c1_lines = c1_lines
            self.c2_lines = c2_lines

            host = ScrollableFigureHost(self.plot_container, fig, len(axes))
            host.pack(fill=tk.BOTH, expand=True)
            self.dashboard_figure_host = host
            canvas = host.canvas
            canvas.draw()

            self.zoom_manager = ZoomInteractionManager(
                canvas, axes, twin_axes, c1_lines, c2_lines,
                on_cursor_change=self._on_cursor_updated,
                on_hover=self._on_hover_updated,
                on_export_excel=self.export_excel,
                on_export_image=self.export_image,
                on_export_csv=self.export_csv
            )
            self._restore_dashboard_cursors(cursor_state)
            self._on_cursor_updated()
            self.telemetry.set_signals(signals_from_aligned(self.aligned_df, self.dashboard_grid_widgets),
                                       'Aligned bench recording · ' + self.txt_title.get())

        except Exception as e:
            self.logger.exception('Dashboard replot failed')
            messagebox.showerror("Re-Plot Error", str(e))

    def _capture_dashboard_cursors(self):
        manager = self.zoom_manager
        return {
            'c1': float(self.c1_lines[0].get_xdata()[0]) if self.c1_lines else None,
            'c2': float(self.c2_lines[0].get_xdata()[0]) if self.c2_lines else None,
            'dual': manager.dual_cursor_active if manager else False,
            'target': manager.active_cursor_target if manager else 'C1',
            'mode': manager.mode if manager else 'CURSOR',
        }

    def _restore_dashboard_cursors(self, state):
        manager = self.zoom_manager
        if not manager:
            return
        if state.get('dual'):
            manager.toggle_dual_cursor()
        manager.set_active_cursor_target(state.get('target', 'C1'))
        if state.get('c1') is not None:
            manager._set_c1_time(state['c1'])
        if state.get('c2') is not None and manager.dual_cursor_active:
            manager._set_c2_time(state['c2'])
        manager.set_mode(state.get('mode', 'CURSOR'))

    def _setup_comparator_tab(self):
        top_ctrl = ttk.Frame(self.tab_comparator, padding=(10, 6))
        top_ctrl.pack(side=tk.TOP, fill=tk.X)

        load_box = ttk.LabelFrame(top_ctrl, text="1. Select Inputs for Comparative Validation", padding=(6, 4))
        load_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        ttk.Button(load_box, text="📁 Raw Test CSV", command=self.load_comp_raw_file).grid(row=0, column=0, padx=4, pady=2)
        self.lbl_comp_raw = ttk.Label(load_box, text="No raw file selected", foreground="gray", width=24)
        self.lbl_comp_raw.grid(row=0, column=1, padx=4, sticky=tk.W)
        self._refresh_comp_raw_label()

        ttk.Button(load_box, text="📈 Sim Reference ZIP / CSV / PNG", command=self.load_comp_sim_plot).grid(row=0, column=2, padx=6, pady=2)
        self.lbl_comp_sim = ttk.Label(load_box, text="No simulation reference selected", foreground="gray", width=28)
        self.lbl_comp_sim.grid(row=0, column=3, padx=4, sticky=tk.W)

        act_box = ttk.LabelFrame(top_ctrl, text="2. Validation Actions", padding=(6, 4))
        act_box.pack(side=tk.RIGHT, padx=4)
        for index, (label, command) in enumerate((
            ('🚀 Run Validation', self.execute_comparison), ('🔎 Preview Reference', self.preview_sim_reference),
            ('Reference Units / Calibration', self.configure_reference_units), ('Difference Colours', self.configure_comparison_tolerances),
            ('📊 Export Excel Report', self.export_comp_excel), ('💾 Save Plot Image', self.export_comp_plot_image),
        )):
            ttk.Button(act_box, text=label, command=command).grid(row=index // 3, column=index % 3, padx=4, pady=2, sticky=tk.EW)

        comp_split = ttk.PanedWindow(self.tab_comparator, orient=tk.HORIZONTAL)
        comp_split.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        left_comp = ttk.Frame(comp_split, width=540)
        comp_split.add(left_comp, weight=0)

        self.card_verdict = ttk.LabelFrame(left_comp, text="Validation Result Summary", padding=8)
        self.card_verdict.pack(fill=tk.X, padx=4, pady=(2, 6))

        self.lbl_comp_badge = ttk.Label(
            self.card_verdict,
            text="⚪ Pending Validation — Load Bench Data & Sim CSV to Begin",
            font=(UI_FONT, 10, "bold"),
            foreground="#c2c7d0"
        )
        self.lbl_comp_badge.pack(anchor=tk.W, pady=2)

        self.lbl_comp_subsummary = ttk.Label(
            self.card_verdict,
            text="Key Metrics: Peak Speed, Total Duration, Wash Temp, Heating Profile & Actuators",
            font=(UI_FONT, 8),
            foreground="#969da9",
            wraplength=490,
            justify=tk.LEFT
        )
        self.lbl_comp_subsummary.pack(anchor=tk.W)

        self.comp_signal_box = ttk.LabelFrame(
            left_comp, text="Simulation / Bench Signals · Visibility", padding=(4, 3)
        )
        self.comp_signal_box.pack(fill=tk.X, padx=4, pady=2)
        visibility_actions = ttk.Frame(self.comp_signal_box)
        visibility_actions.pack(fill=tk.X, padx=3, pady=(0, 3))
        for text, source, enabled in [('Sim All', 'sim', True), ('Sim None', 'sim', False),
                                      ('Bench All', 'bench', True), ('Bench None', 'bench', False)]:
            ttk.Button(visibility_actions, text=text,
                       command=lambda s=source, value=enabled: self._set_comp_visibility(s, value)).pack(
                side=tk.LEFT, padx=2)
        signal_header = ttk.Frame(self.comp_signal_box)
        signal_header.pack(fill=tk.X, padx=(3, 13))
        ttk.Label(signal_header, text="", width=2, anchor=tk.CENTER,
                  font=(UI_FONT, 8, "bold")).grid(row=0, column=0)
        ttk.Label(signal_header, text="Legend / value block", width=36, anchor=tk.W,
                  font=(UI_FONT, 8, "bold")).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(signal_header, text="Sim", width=6, anchor=tk.CENTER,
                  font=(UI_FONT, 8, "bold")).grid(row=0, column=2)
        ttk.Label(signal_header, text="Bench", width=7, anchor=tk.CENTER,
                  font=(UI_FONT, 8, "bold")).grid(row=0, column=3)

        signal_scroll_frame = ttk.Frame(self.comp_signal_box)
        signal_scroll_frame.pack(fill=tk.X, expand=False)
        self.comp_signal_canvas = tk.Canvas(
            signal_scroll_frame, height=188, highlightthickness=0, borderwidth=0
        )
        signal_scroll = ttk.Scrollbar(
            signal_scroll_frame, orient=tk.VERTICAL, command=self.comp_signal_canvas.yview
        )
        self.comp_signal_canvas.configure(yscrollcommand=signal_scroll.set)
        self.comp_signal_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        signal_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.comp_signal_rows = ttk.Frame(self.comp_signal_canvas)
        self.comp_signal_window = self.comp_signal_canvas.create_window(
            (0, 0), window=self.comp_signal_rows, anchor="nw"
        )
        self.comp_signal_rows.bind(
            "<Configure>",
            lambda _event: self.comp_signal_canvas.configure(
                scrollregion=self.comp_signal_canvas.bbox("all")
            )
        )
        self.comp_signal_canvas.bind(
            "<Configure>",
            lambda event: self.comp_signal_canvas.itemconfigure(
                self.comp_signal_window, width=event.width
            )
        )
        self.comp_signal_canvas.bind(
            "<MouseWheel>",
            lambda event: self.comp_signal_canvas.yview_scroll(
                int(-1 * (event.delta / 120)), "units"
            )
        )
        self._clear_comp_signal_rows()

        cursor_frame = ttk.LabelFrame(left_comp, text='Comparison Cursor · Same Time', padding=4)
        cursor_frame.pack(fill=tk.X, padx=4, pady=3)
        self.lbl_comp_cursor = ttk.Label(cursor_frame, text='Click a graph in Cursor mode to inspect values.',
                                         foreground='#b2bac7')
        self.lbl_comp_cursor.pack(anchor=tk.W)
        cursor_table = ttk.Frame(cursor_frame)
        cursor_table.pack(fill=tk.X)
        cursor_columns = ('signal', 'sim', 'bench', 'difference')
        self.tree_comp_cursor = ttk.Treeview(cursor_table, columns=cursor_columns,
                                             show='headings', height=4)
        for key, title, width in [('signal', 'Signal', 150), ('sim', 'Sim', 85),
                                   ('bench', 'Bench', 85), ('difference', 'Bench − Sim', 105)]:
            self.tree_comp_cursor.heading(key, text=title)
            self.tree_comp_cursor.column(key, width=width, minwidth=width,
                                          anchor=tk.W if key == 'signal' else tk.E)
        cursor_y = ttk.Scrollbar(cursor_table, orient=tk.VERTICAL, command=self.tree_comp_cursor.yview)
        cursor_x = ttk.Scrollbar(cursor_table, orient=tk.HORIZONTAL, command=self.tree_comp_cursor.xview)
        self.tree_comp_cursor.configure(yscrollcommand=cursor_y.set, xscrollcommand=cursor_x.set)
        self.tree_comp_cursor.grid(row=0, column=0, sticky=tk.NSEW)
        cursor_y.grid(row=0, column=1, sticky=tk.NS)
        cursor_x.grid(row=1, column=0, sticky=tk.EW)
        cursor_table.columnconfigure(0, weight=1)

        tbl_frame = ttk.LabelFrame(left_comp, text="Comparative Values & Differences", padding=4)
        tbl_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)

        columns = ("param", "sim", "raw", "delta", "pct", "tol", "status")
        self.tree_comp = ttk.Treeview(tbl_frame, columns=columns, show="headings", height=14)

        self.tree_comp.heading("param", text="Parameter / Cycle Metric")
        self.tree_comp.heading("sim", text="Sim Ref")
        self.tree_comp.heading("raw", text="Raw Test")
        self.tree_comp.heading("delta", text="Δ (Diff)")
        self.tree_comp.heading("pct", text="Difference %")
        self.tree_comp.heading("tol", text="Notes")
        self.tree_comp.heading("status", text="Difference Band")

        self.tree_comp.column("param", width=230, anchor=tk.W)
        self.tree_comp.column("sim", width=100, anchor=tk.E)
        self.tree_comp.column("raw", width=100, anchor=tk.E)
        self.tree_comp.column("delta", width=100, anchor=tk.E)
        self.tree_comp.column("pct", width=95, anchor=tk.E)
        self.tree_comp.column("tol", width=270, anchor=tk.W)
        self.tree_comp.column("status", width=110, anchor=tk.CENTER)

        self.tree_comp.tag_configure('GREEN', foreground='#007E33', background='#E8F5E9')
        self.tree_comp.tag_configure('YELLOW', foreground='#725300', background='#FFF3B0')
        self.tree_comp.tag_configure('RED', foreground='#B42318', background='#FDE8E7')
        self.tree_comp.tag_configure('VALUE', foreground='#b2bac7')
        self.tree_comp.tag_configure("REVIEW", foreground="#a4aebb")
        self.tree_comp.tag_configure("MISSING", foreground="#a4aebb")

        t_scroll_y = ttk.Scrollbar(tbl_frame, orient=tk.VERTICAL, command=self.tree_comp.yview)
        t_scroll_x = ttk.Scrollbar(tbl_frame, orient=tk.HORIZONTAL, command=self.tree_comp.xview)
        for key in columns:
            self.tree_comp.column(key, minwidth=self.tree_comp.column(key, 'width'), stretch=False)
        self.tree_comp.configure(yscrollcommand=t_scroll_y.set, xscrollcommand=t_scroll_x.set)
        self.tree_comp.grid(row=0, column=0, sticky=tk.NSEW)
        t_scroll_y.grid(row=0, column=1, sticky=tk.NS)
        t_scroll_x.grid(row=1, column=0, sticky=tk.EW)
        tbl_frame.columnconfigure(0, weight=1)
        tbl_frame.rowconfigure(0, weight=1)

        self.comp_plot_frame = ttk.Frame(comp_split)
        comp_split.add(self.comp_plot_frame, weight=3)

    def configure_comparison_tolerances(self):
        messagebox.showinfo('Difference Colours',
                            'Green: absolute percentage difference below 10%.\n'
                            'Yellow: 10% through 20%, including both boundaries.\n'
                            'Red: above 20%.\n\n'
                            'These are difference colours, without acceptance limits.\n'
                            'Valve and pump rows show count differences only.\n'
                            'A zero simulation value has no percentage denominator.', parent=self)

    def configure_image_calibration(self):
        if self.comp_sim_csv_path:
            self.configure_reference_units()
            return
        image_path = self.comp_sim_img_path
        if not image_path or not os.path.isfile(image_path):
            candidate = resource_path(
                'SB30LF0_Cotton60LabelIN19_var4_12000g_1200RPM_Default_R58_0000005_simulated_values.png'
            )
            image_path = candidate if os.path.isfile(candidate) else None
            if image_path:
                self.comp_image_calibration = {}
                self.comp_sim_img_path = image_path
                base = os.path.basename(image_path)
                self.lbl_comp_sim.config(
                    text=base[:24] + '..' if len(base) > 26 else base, foreground='#e8e9ed'
                )
        if image_path is None:
            messagebox.showwarning(
                'Missing Reference Plot',
                'Select a supported simulator reference image before configuring its calibration.',
                parent=self
            )
            return

        try:
            analyzer = SimulationImageAnalyzer(
                image_path, calibration=self.comp_image_calibration
            )
        except Exception as exc:
            messagebox.showerror(
                'Image Calibration', f'Could not inspect the selected image:\n{exc}', parent=self
            )
            return

        calibration = analyzer.calibration
        window = tk.Toplevel(self)
        window.title('Simulation Image Calibration')
        window.geometry('1060x760')
        window.minsize(900, 620)
        window.transient(self)
        ttk.Label(
            window,
            text=(f'{os.path.basename(image_path)} · {analyzer.width} × {analyzer.height} px · '
                  'Y tick positions use the reference height below.'),
            padding=(10, 8), wraplength=1000
        ).pack(fill=tk.X)

        time_box = ttk.LabelFrame(window, text='Time Axis', padding=8)
        time_box.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(time_box, text='Total cycle duration (minutes)').grid(row=0, column=0, sticky=tk.W)
        duration_entry = ttk.Entry(time_box, width=14)
        duration_entry.insert(0, f'{analyzer.duration_min:g}')
        duration_entry.grid(row=0, column=1, padx=(8, 20), sticky=tk.W)
        time_verified = tk.BooleanVar(value=bool(calibration.get('time_verified', False)))
        ttk.Checkbutton(
            time_box, text='I verified the duration against the image time ticks',
            variable=time_verified
        ).grid(row=0, column=2, sticky=tk.W)
        ttk.Label(
            time_box, text='Leave the confirmation off when the duration is only an estimate.',
            foreground='#a4aebb'
        ).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=(5, 0))

        geometry_box = ttk.LabelFrame(window, text='Image Coordinates', padding=8)
        geometry_box.pack(fill=tk.X, padx=10, pady=5)
        ttk.Label(geometry_box, text='Reference height (px)').grid(row=0, column=0, sticky=tk.W)
        reference_height_entry = ttk.Entry(geometry_box, width=10)
        reference_height_entry.insert(0, f'{analyzer.reference_height:g}')
        reference_height_entry.grid(row=0, column=1, padx=(6, 18), sticky=tk.W)
        ttk.Label(
            geometry_box, text='Plot bounds in image pixels (left, right, top, bottom)'
        ).grid(row=0, column=2, columnspan=4, sticky=tk.W)
        plot_bounds = calibration.get('plot_bounds')
        plot_bound_entries = []
        for index, label in enumerate(('Left', 'Right', 'Top', 'Bottom')):
            ttk.Label(geometry_box, text=label).grid(row=1, column=2 + index, padx=(4, 1))
            entry = ttk.Entry(geometry_box, width=8)
            if plot_bounds is not None:
                entry.insert(0, f'{float(plot_bounds[index]):g}')
            entry.grid(row=2, column=2 + index, padx=(4, 1))
            plot_bound_entries.append(entry)
        ttk.Label(
            geometry_box, text='Leave all four bounds blank for automatic plot-frame detection.',
            foreground='#a4aebb'
        ).grid(row=3, column=2, columnspan=4, sticky=tk.W, pady=(4, 0))

        axis_box = ttk.LabelFrame(
            window, text='Signal Y-Axis Calibration · Tick 1 px/value and Tick 2 px/value', padding=6
        )
        axis_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        axis_canvas = tk.Canvas(axis_box, highlightthickness=0, borderwidth=0)
        axis_scroll = ttk.Scrollbar(axis_box, orient=tk.VERTICAL, command=axis_canvas.yview)
        axis_canvas.configure(yscrollcommand=axis_scroll.set)
        axis_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        axis_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        axis_rows = ttk.Frame(axis_canvas)
        axis_window = axis_canvas.create_window((0, 0), window=axis_rows, anchor='nw')
        axis_rows.bind(
            '<Configure>',
            lambda _event: axis_canvas.configure(scrollregion=axis_canvas.bbox('all'))
        )
        axis_canvas.bind(
            '<Configure>', lambda event: axis_canvas.itemconfigure(axis_window, width=event.width)
        )
        axis_canvas.bind(
            '<MouseWheel>',
            lambda event: axis_canvas.yview_scroll(int(-1 * (event.delta / 120)), 'units')
        )
        for column, title in enumerate(('Signal', 'Tick 1 px', 'Value', 'Tick 2 px', 'Value', 'Verified')):
            ttk.Label(axis_rows, text=title, font=(UI_FONT, 9, 'bold')).grid(
                row=0, column=column, padx=5, pady=4, sticky=tk.W
            )

        axis_calibration = calibration.get('axis_calibration', {})
        axis_verified = calibration.get('axis_verified', False)
        axis_inputs = {}
        for row_index, spec in enumerate(SIMULATION_LEGEND_SPECS, start=1):
            key = spec['key']
            values = axis_calibration.get(key, spec.get('axis_calibration'))
            values = tuple(values) if values is not None else ('', '', '', '')
            verified = (bool(axis_verified.get(key, False)) if isinstance(axis_verified, dict)
                        else bool(axis_verified))
            ttk.Label(axis_rows, text=spec['label'], width=24).grid(
                row=row_index, column=0, padx=5, pady=3, sticky=tk.W
            )
            entries = []
            for column, value in enumerate(values, start=1):
                entry = ttk.Entry(axis_rows, width=10)
                if value != '':
                    entry.insert(0, f'{float(value):g}')
                entry.grid(row=row_index, column=column, padx=4, pady=3)
                entries.append(entry)
            verified_var = tk.BooleanVar(value=verified)
            ttk.Checkbutton(axis_rows, variable=verified_var).grid(
                row=row_index, column=5, padx=14, pady=3
            )
            axis_inputs[key] = (entries, verified_var)

        ttk.Label(
            window,
            text=('Clear all four values in a row to use that signal’s built-in profile calibration. '
                  'Confirm a Y axis only after checking its tick marks.'),
            foreground='#a4aebb', padding=(10, 3), wraplength=1000
        ).pack(fill=tk.X)
        button_row = ttk.Frame(window, padding=(10, 6))
        button_row.pack(fill=tk.X)

        def apply_calibration():
            try:
                new_calibration = {
                    'duration_min': float(duration_entry.get().strip()),
                    'reference_height': float(reference_height_entry.get().strip()),
                    'time_verified': bool(time_verified.get()),
                    'axis_verified': {
                        key: bool(verified_var.get())
                        for key, (_entries, verified_var) in axis_inputs.items()
                    },
                }
                bound_text = [entry.get().strip() for entry in plot_bound_entries]
                if any(bound_text):
                    if not all(bound_text):
                        raise ValueError('Enter all four plot bounds or leave all four blank.')
                    bounds = [float(value) for value in bound_text]
                    if not np.isfinite(bounds).all():
                        raise ValueError('Plot bounds must be finite pixel coordinates.')
                    if any(value != int(value) for value in bounds):
                        raise ValueError('Plot bounds must be whole image pixels.')
                    new_calibration['plot_bounds'] = [int(value) for value in bounds]

                overrides = {}
                for key, (entries, _verified_var) in axis_inputs.items():
                    values = [entry.get().strip() for entry in entries]
                    if not any(values):
                        continue
                    if not all(values):
                        raise ValueError(
                            f'Enter all four tick coordinates and values for {key}, or clear the row.'
                        )
                    points = [float(value) for value in values]
                    if not np.isfinite(points).all():
                        raise ValueError(f'{key}: tick coordinates and values must be finite numbers.')
                    if points[0] == points[2] or points[1] == points[3]:
                        raise ValueError(
                            f'{key}: the two tick positions and values must each be distinct.'
                        )
                    overrides[key] = points
                if overrides:
                    new_calibration['axis_calibration'] = overrides

                # Validate the proposed settings before replacing the current ones.
                SimulationImageAnalyzer(image_path, calibration=new_calibration)
                self.comp_image_calibration = new_calibration
                self.comp_image_analyzer = None
                self._clear_comparison_results()
                self.lbl_comp_badge.config(
                    text='⚪ Calibration changed — run validation again.', foreground='#c2c7d0'
                )
                window.destroy()
            except (OSError, TypeError, ValueError) as exc:
                messagebox.showerror('Invalid Image Calibration', str(exc), parent=window)

        ttk.Button(button_row, text='Apply Calibration', command=apply_calibration).pack(
            side=tk.RIGHT, padx=(4, 0)
        )
        ttk.Button(button_row, text='Cancel', command=window.destroy).pack(side=tk.RIGHT, padx=4)

    def _display_comp_scorecard(self):
        self.tree_comp.delete(*self.tree_comp.get_children())
        totals = dict.fromkeys(('GREEN','YELLOW','RED','VALUE','REVIEW','MISSING'), 0)
        for _, row in self.comp_scorecard_df.iterrows():
            status = str(row['status'])
            totals[status] = totals.get(status, 0) + 1
            self.tree_comp.insert('', tk.END, values=(
                row['parameter'], row['sim_val'], row['raw_val'], row['delta'],
                row['percent'], row['notes'], status), tags=(status,))
        text = (f'Differences: {totals["GREEN"]} green · {totals["YELLOW"]} yellow · '
                f'{totals["RED"]} red · {totals["VALUE"]} values/counts')
        if totals['REVIEW'] or totals['MISSING']:
            text += f' · {totals["REVIEW"] + totals["MISSING"]} incomplete/unverified'
        self.lbl_comp_badge.config(text=text, foreground='#b2bac7')

    def _set_comp_visibility(self, source, enabled):
        for key, state in self.comp_signal_visibility.items():
            if source == 'sim':
                curve = (self.comp_sim_curves or {}).get(key)
                available = isinstance(curve, pd.DataFrame) and not curve.empty
            else:
                column = self.comp_signal_bench_columns.get(key)
                available = self.comp_raw_df is not None and column in self.comp_raw_df.columns
            state[source].set(bool(enabled and available))
        self._on_comp_visibility_changed()

    def _on_comp_cursor_updated(self):
        if not self.comp_cursor_lines:
            return
        self.comp_cursor_time = float(self.comp_cursor_lines[0].get_xdata()[0])
        self.lbl_comp_cursor.config(text=f'Cursor: {self.comp_cursor_time:.3f} min')
        self.tree_comp_cursor.delete(*self.tree_comp_cursor.get_children())
        for spec in specs_for_curves(self.comp_sim_curves):
            visibility = self.comp_signal_visibility.get(spec['key'], {})
            if not any(variable.get() for variable in visibility.values()):
                continue
            traces = self.comp_cursor_traces.get(spec['key'], {})
            sim = sample_trace(traces.get('sim'), self.comp_cursor_time) if visibility['sim'].get() else np.nan
            bench = sample_trace(traces.get('bench'), self.comp_cursor_time) if visibility['bench'].get() else np.nan
            sim_text, bench_text, difference = format_comparison_samples(spec, sim, bench, traces.get('bench_kind'))
            self.tree_comp_cursor.insert('', tk.END, values=(spec['label'],sim_text,bench_text,difference))

    def _get_comparison_raw_path(self):
        return (
            getattr(self, 'comp_raw_path', None)
            or getattr(self, 'rd_path', None)
            or getattr(self, 'pd_path', None)
        )

    def _refresh_comp_raw_label(self):
        if not hasattr(self, 'lbl_comp_raw'):
            return
        selected_path = getattr(self, 'comp_raw_path', None)
        active_path = selected_path or getattr(self, 'rd_path', None) or getattr(self, 'pd_path', None)
        if not active_path:
            self.lbl_comp_raw.config(text="No raw file selected", foreground="gray")
            return
        prefix = "Selected" if selected_path else "Active"
        display = f"{prefix}: {os.path.basename(active_path)}"
        if len(display) > 25:
            display = display[:22] + ".."
        self.lbl_comp_raw.config(text=display, foreground="#e8e9ed")

    def _clear_comparison_results(self):
        self.comp_csv_adapter = None
        self.comp_image_analyzer = None
        self._dispose_manager('comp_zoom_manager')
        old_figure = getattr(self, 'comp_fig', None)
        if old_figure is not None:
            plt.close(old_figure)
        self.comp_raw_df = None
        self.comp_sim_curves = None
        self.comp_scorecard_df = None
        self.comp_fig = None
        self.comp_axes = []
        self.comp_twin_axes = []
        self.comp_canvas = None
        self.comp_zoom_manager = None
        self.comp_signal_visibility = {}
        self.comp_signal_bench_columns = {}
        self.comp_cursor_lines = []
        self.comp_cursor_traces = {}
        self.comp_cursor_time = None
        if hasattr(self, 'tree_comp_cursor'):
            self.tree_comp_cursor.delete(*self.tree_comp_cursor.get_children())
            self.lbl_comp_cursor.config(text='Click a graph in Cursor mode to inspect values.')
        if hasattr(self, 'tree_comp'):
            for item in self.tree_comp.get_children():
                self.tree_comp.delete(item)
        self._clear_comp_signal_rows()
        if hasattr(self, 'comp_plot_frame'):
            for widget in self.comp_plot_frame.winfo_children():
                widget.destroy()
        if hasattr(self, 'lbl_comp_badge'):
            self.lbl_comp_badge.config(
                text="⚪ Pending Validation — Load Bench Data & Simulation Reference to Begin",
                foreground="#c2c7d0"
            )
        if hasattr(self, 'lbl_comp_subsummary'):
            self.lbl_comp_subsummary.config(
                text="Key Metrics: Peak Speed, Total Duration, Wash Temp, Heating Profile & Actuators"
            )

    def _clear_comp_signal_rows(self):
        if not hasattr(self, 'comp_signal_rows'):
            return
        for widget in self.comp_signal_rows.winfo_children():
            widget.destroy()
        ttk.Label(
            self.comp_signal_rows,
            text="Run validation to list the reference signals.",
            foreground="#666666", padding=(5, 8)
        ).grid(row=0, column=0, sticky=tk.W)

    def _build_comp_signal_controls(self):
        self.comp_signal_bench_columns = ComparisonEngine.find_bench_columns(self.comp_raw_df, specs_for_curves(self.comp_sim_curves))
        self.comp_cursor_traces = comparison_traces(
            self.comp_raw_df, self.comp_sim_curves, self.comp_signal_bench_columns, specs_for_curves(self.comp_sim_curves))
        for widget in self.comp_signal_rows.winfo_children():
            widget.destroy()

        for row_index, spec in enumerate(specs_for_curves(self.comp_sim_curves)):
            sim_curve = self.comp_sim_curves.get(spec['key'], pd.DataFrame())
            sim_available = isinstance(sim_curve, pd.DataFrame) and not sim_curve.empty
            bench_col = self.comp_signal_bench_columns.get(spec['key'])
            bench_available = bench_col in self.comp_raw_df.columns if bench_col is not None else False
            sim_var = tk.BooleanVar(value=sim_available)
            bench_var = tk.BooleanVar(value=bench_available)
            self.comp_signal_visibility[spec['key']] = {
                'sim': sim_var, 'bench': bench_var
            }

            row = ttk.Frame(self.comp_signal_rows)
            row.grid(row=row_index, column=0, sticky=tk.EW, pady=1)
            row.columnconfigure(1, weight=1)
            unit = spec['unit'] if spec['unit'] not in ('state', 'stage', 'code') else ''
            block = f"{spec['block']} ({unit})" if unit else spec['block']
            signal_text = f"{spec['label']}  ·  {block}"
            if spec['key'] == 'heater_power' and ComparisonEngine.heater_bench_is_state(self.comp_raw_df,bench_col):
                signal_text += '  ·  Sim W / Bench ON–OFF'
            if spec['key'] == 'pressure' and spec['unit'] == 'unknown':
                signal_text += '  ·  confirm source unit in Reference Units to compare'
            if spec['key'] == 'pressure' and not bench_available:
                pulse_columns = [
                    column for column, pressure_unit in infer_pressure_units(self.comp_raw_df).items()
                    if pressure_unit == 'µs'
                ]
                if pulse_columns:
                    signal_text += "  ·  pulse (µs) excluded; no confirmed pressure match"
            color_key = tk.Canvas(row, width=22, height=12, highlightthickness=0, borderwidth=0)
            color_key.create_rectangle(1, 1, 10, 11, fill=spec['color'], outline='#a4aebb')
            color_key.create_rectangle(11, 1, 20, 11, fill=spec['bench_color'], outline='#a4aebb')
            color_key.grid(row=0, column=0, padx=(4, 5), pady=2)
            ttk.Label(
                row, text=signal_text, width=36,
                anchor=tk.W, wraplength=245, foreground='#202124'
            ).grid(row=0, column=1, sticky=tk.W, padx=(1, 2))
            sim_check = ttk.Checkbutton(
                row, variable=sim_var, command=self._on_comp_visibility_changed
            )
            sim_check.grid(row=0, column=2, padx=(8, 12))
            if not sim_available:
                sim_check.state(['disabled'])
            bench_check = ttk.Checkbutton(
                row, variable=bench_var, command=self._on_comp_visibility_changed
            )
            bench_check.grid(row=0, column=3, padx=(6, 8))
            if not bench_available:
                bench_check.state(['disabled'])

        if hasattr(self, 'comp_signal_canvas'):
            self.comp_signal_canvas.yview_moveto(0)

    def _comparison_visibility_values(self):
        return {
            key: {source: variable.get() for source, variable in state.items()}
            for key, state in self.comp_signal_visibility.items()
        }

    def _on_comp_visibility_changed(self):
        if self.comp_raw_df is not None and self.comp_sim_curves is not None:
            self._render_comparison_plot(preserve_xlim=True)

    def _render_comparison_plot(self, preserve_xlim=False):
        previous_mode = self.comp_zoom_manager.mode if self.comp_zoom_manager is not None else 'CURSOR'
        previous_xlim = None
        if preserve_xlim and self.comp_axes:
            try:
                previous_xlim = self.comp_axes[0].get_xlim()
            except Exception:
                previous_xlim = None

        self._dispose_manager('comp_zoom_manager')

        for widget in self.comp_plot_frame.winfo_children():
            widget.destroy()
        if self.comp_fig is not None:
            plt.close(self.comp_fig)
        self.comp_fig = None
        self.comp_zoom_manager = None
        self.comp_canvas = None

        fig, axes, twin_axes, error_message = ComparisonEngine.render_comparison_figure(
            self.comp_raw_df, self.comp_sim_curves,
            visibility=self._comparison_visibility_values(),
            bench_columns=self.comp_signal_bench_columns,
            actuator_analysis=getattr(self.comp_image_analyzer, 'actuator_analysis', {})
        )
        if error_message:
            ttk.Label(
                self.comp_plot_frame, text=error_message, foreground="#666666",
                font=(UI_FONT, 11)
            ).pack(expand=True)
            self.comp_axes = []
            self.comp_twin_axes = []
            return

        self.comp_fig = fig
        self.comp_axes = axes
        self.comp_twin_axes = twin_axes
        # The comparison panel uses the same cursor interaction manager as the
        # dashboard. Give it a linked vertical guide on every signal axis.
        self.comp_cursor_lines = [
            axis.axvline(
                self.comp_cursor_time if self.comp_cursor_time is not None else 0.0,
                color='#D92D20', linestyle='--', linewidth=0.9,
                alpha=0.85, zorder=20, visible=self.comp_cursor_time is not None
            )
            for axis in axes
        ]
        if previous_xlim:
            for axis in axes:
                axis.set_xlim(previous_xlim)

        nav = ttk.Frame(self.comp_plot_frame, padding=(4, 2))
        nav.pack(side=tk.TOP, fill=tk.X)
        host = ScrollableFigureHost(self.comp_plot_frame, fig, len(axes))
        host.pack(fill=tk.BOTH, expand=True)
        self.comp_figure_host = host
        canvas = host.canvas
        self.comp_canvas = canvas
        self.comp_zoom_manager = ZoomInteractionManager(
            canvas, axes, twin_axes, c1_lines=self.comp_cursor_lines,
            on_cursor_change=self._on_comp_cursor_updated,
            on_export_excel=self.export_comp_excel,
            on_export_image=self.export_comp_plot_image
        )
        zoom_tools = [
            ("Hand", "HAND"), ("Cursor", "CURSOR"),
            ("Zoom X", "ZOOM_X"), ("Zoom Y", "ZOOM_Y"), ("Zoom XY", "ZOOM_XY")
        ]
        for label, mode in zoom_tools:
            ttk.Button(
                nav, text=label,
                command=lambda selected=mode: self.comp_zoom_manager.set_mode(selected)
            ).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav, text="◀ Back", command=self.comp_zoom_manager.zoom_back).pack(side=tk.LEFT, padx=(8, 2))
        ttk.Button(nav, text="Forward ▶", command=self.comp_zoom_manager.zoom_forward).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav, text="Fit", command=self.comp_zoom_manager.reset_zoom).pack(side=tk.LEFT, padx=2)
        self.comp_zoom_manager.set_mode("HAND")
        if self.comp_cursor_time is not None:
            self._on_comp_cursor_updated()
        canvas.draw()

    def load_comp_raw_file(self):
        p = filedialog.askopenfilename(filetypes=[("Data Files", "*.csv;*.CSV;*.xlsx;*.xls"), ("All Files", "*.*")])
        if p:
            self.comp_raw_path = p
            self._refresh_comp_raw_label()
            self._clear_comparison_results()

    def load_comp_sim_plot(self):
        path = filedialog.askopenfilename(
            title="Select simulation package ZIP, CSV or reference image",
            filetypes=[("Simulation Package", "*.zip"), ("Simulation CSV", "*.csv"),
                       ("Reference Images", "*.png;*.jpg;*.jpeg;*.bmp;*.tiff")])
        if not path:
            return
        self._clear_comparison_results()
        self.comp_sim_csv_path = path if path.lower().endswith(('.csv', '.zip')) else None
        self.comp_sim_img_path = None if self.comp_sim_csv_path else path
        self.comp_image_calibration = {}
        self.comp_image_analyzer = None
        self.comp_csv_adapter = None
        prefix = ('ZIP: ' if path.lower().endswith('.zip') else 'CSV: ') if self.comp_sim_csv_path else 'Image: '
        base = os.path.basename(path)
        self.lbl_comp_sim.config(text=prefix + (base[:20] + '..' if len(base) > 22 else base), foreground='#e8e9ed')

    def configure_reference_units(self):
        if not self.comp_sim_csv_path:
            self.configure_image_calibration()
            return
        window = tk.Toplevel(self)
        window.title('Simulation Reference Units')
        window.transient(self)
        ttk.Label(window, text='ZIP definitions and CSV unit rows determine time units.\n'
                  'Pressure keeps the original numbers for both sources and is labelled Pa.', padding=12).grid(row=0, column=0, columnspan=2)
        choices = {'time_unit': ('min', 's', 'ms', 'h')}
        labels = {'time_unit': 'Time column'}
        variables = {}
        for row, (key, options) in enumerate(choices.items(), start=1):
            ttk.Label(window, text=labels[key], padding=8).grid(row=row, column=0, sticky=tk.W)
            variables[key] = tk.StringVar(value=self.comp_csv_settings.get(key, 'min'))
            ttk.Combobox(window, textvariable=variables[key], values=options, state='readonly', width=12).grid(row=row, column=1, padx=8)
        preview_text = tk.StringVar()
        def update_pressure_preview(*_args):
            try:
                settings = dict(self.comp_csv_settings)
                settings.update({key: var.get() for key, var in variables.items()})
                settings.update(pressure_display_unit='Pa', preserve_pressure_numbers=True)
                adapter = load_simulation_reference(self.comp_sim_csv_path, **settings)
                curve = adapter.curves.get('pressure')
                if curve is None:
                    preview_text.set('No water_pressure column in this reference.')
                    return
                preview_text.set(f'Original pressure peak: {curve["value"].max():g} Pa. No pressure conversion.')
                if hasattr(adapter, 'close'):
                    adapter.close()
            except Exception as exc:
                preview_text.set(str(exc))
        ttk.Label(window, textvariable=preview_text, padding=12, wraplength=500).grid(
            row=4, column=0, columnspan=2, sticky=tk.W)
        for var in variables.values():
            var.trace_add('write', update_pressure_preview)
        update_pressure_preview()
        def apply():
            self.comp_csv_settings.update({key: var.get() for key, var in variables.items()})
            self.comp_csv_settings.update(pressure_display_unit='Pa', preserve_pressure_numbers=True)
            self.comp_csv_adapter = None
            self._clear_comparison_results()
            window.destroy()
        ttk.Button(window, text='Apply', command=apply).grid(row=5, column=1, pady=12)

    def preview_sim_reference(self):
        if not self.comp_sim_csv_path:
            self.preview_sim_image_analysis()
            return
        try:
            settings = {**self.comp_csv_settings, 'pressure_display_unit': 'Pa', 'preserve_pressure_numbers': True}
            adapter = load_simulation_reference(self.comp_sim_csv_path, **settings)
            curves = adapter.extract_curves()
            empty_bench = pd.DataFrame({'time_min': []})
            fig, _, _, error = ComparisonEngine.render_comparison_figure(empty_bench, curves)
            if error:
                raise ValueError(error)
            window = tk.Toplevel(self)
            window.title('Simulation Reference Preview')
            window.geometry('1400x900')
            ttk.Label(window, text=f'{len(adapter.frame):,} samples · {adapter.duration_min:.2f} min · '
                      'All samples retained; analog plots use extrema, states use every transition. '
                      f'{getattr(adapter, "package_summary", "")}', padding=8).pack(side=tk.BOTTOM, fill=tk.X)
            host = ScrollableFigureHost(window, fig, len(fig.axes))
            host.pack(fill=tk.BOTH, expand=True)
            toolbar = NavigationToolbar2Tk(host.canvas, window, pack_toolbar=False)
            toolbar.update()
            toolbar.pack(side=tk.TOP, fill=tk.X)
            def close_preview():
                plt.close(fig)
                window.destroy()
            window.protocol('WM_DELETE_WINDOW', close_preview)
        except Exception as exc:
            messagebox.showerror('CSV Preview Error', str(exc))

    def preview_sim_image_analysis(self):
        if not self.comp_sim_img_path or not os.path.exists(self.comp_sim_img_path):
            candidate = resource_path(
                "SB30LF0_Cotton60LabelIN19_var4_12000g_1200RPM_Default_R58_0000005_simulated_values.png"
            )
            if os.path.exists(candidate):
                self.comp_sim_img_path = candidate
                self.comp_image_calibration = {}
                base = os.path.basename(candidate)
                self.lbl_comp_sim.config(text=base[:24] + ".." if len(base) > 26 else base, foreground="#e8e9ed")
            else:
                messagebox.showwarning(
                    "Missing Reference Plot", "Select a simulation reference image before analyzing it."
                )
                return
        try:
            analyzer = SimulationImageAnalyzer(
                self.comp_sim_img_path, calibration=self.comp_image_calibration
            )
            curves = analyzer.extract_curves()
            fig, _axes = analyzer.render_preview(curves)

            window = tk.Toplevel(self)
            window.title("Simulation Image Analysis · One Scale per Signal")
            window.geometry("1480x920")
            window.minsize(1100, 720)
            status = ttk.Label(
                window, text=analyzer.report_text(), padding=(8, 4),
                foreground="#b2bac7", wraplength=1320
            )
            status.pack(side=tk.BOTTOM, fill=tk.X)
            canvas = FigureCanvasTkAgg(fig, master=window)
            toolbar = NavigationToolbar2Tk(canvas, window, pack_toolbar=False)
            toolbar.update()
            toolbar.pack(side=tk.TOP, fill=tk.X)
            canvas.draw()
            canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=True)

            def close_preview():
                plt.close(fig)
                window.destroy()

            window.protocol("WM_DELETE_WINDOW", close_preview)
            self.comp_image_analyzer = analyzer
        except Exception as exc:
            messagebox.showerror("Image Analysis Error", f"Could not analyze the reference plot:\n{exc}")

    def execute_comparison(self):
        try:
            self._clear_comparison_results()
            self.comp_image_analyzer = None
            self.comp_csv_adapter = None
            raw_path = self._get_comparison_raw_path()
            if not raw_path or not os.path.exists(raw_path):
                messagebox.showwarning('Missing Bench Data', 'Please select the bench CSV/Excel file first.')
                return
            reference_path = self.comp_sim_csv_path or self.comp_sim_img_path
            if not reference_path or not os.path.exists(reference_path):
                messagebox.showwarning('Missing Simulation Reference', 'Select a simulation ZIP, CSV or PNG reference.')
                return
            df = smart_read_file(raw_path)
            reference_settings = {**self.comp_csv_settings, 'pressure_display_unit': 'Pa', 'preserve_pressure_numbers': True}
            if df.empty:
                raise DataReadError('The bench file contains no valid samples.')
            if is_simulation_frame(df):
                # Also supports comparing two simulator CSVs without datetime conversion.
                bench_adapter = SimulationCsvAdapter(raw_path, **reference_settings)
                df = bench_adapter.frame.copy()
                invalid_times = 0
                duplicate_times = int(df['time_min'].duplicated().sum())
            else:
                df['dt'] = extract_datetime_series(df, fallback=False)
                invalid_times = int(df['dt'].isna().sum())
                df = df.dropna(subset=['dt']).sort_values('dt', kind='stable').reset_index(drop=True)
                if df.empty:
                    raise DataReadError('The bench file has no recognizable date/time column.')
                df['time_min'] = (df['dt'] - df['dt'].min()).dt.total_seconds() / 60.0
                duplicate_times = int(df['dt'].duplicated().sum())
            ComparisonEngine.apply_pressure_default(df, 'Pa' if self.comp_sim_csv_path else 'mbar')
            df.attrs['comparison_data_quality'] = {
                'invalid_timestamp_rows_excluded': invalid_times,
                'duplicate_timestamps': duplicate_times,
                'duplicate_policy': 'Every sample retained for metrics/export; cursor uses last sample at equal time.'}
            self.comp_raw_df = df
            self.comp_result_source = raw_path
            if self.comp_sim_csv_path:
                self.comp_csv_adapter = load_simulation_reference(self.comp_sim_csv_path, **reference_settings)
                self.comp_sim_curves = self.comp_csv_adapter.extract_curves()
                reference_summary = (f'Simulation reference: {self.comp_csv_adapter.duration_min:.2f} min; '
                                     f'{len(self.comp_csv_adapter.frame):,} samples. '
                                     'Pressure: original numbers for both sources, labelled Pa. '
                                     'Ten parameters; actual remaining time; heater power in watts.'
                                     f' {getattr(self.comp_csv_adapter, "package_summary", "")}')
            else:
                self.comp_image_analyzer = SimulationImageAnalyzer(self.comp_sim_img_path, calibration=self.comp_image_calibration)
                self.comp_sim_curves = self.comp_image_analyzer.extract_curves()
                reference_summary = self.comp_image_analyzer.report_text()
            self._build_comp_signal_controls()
            self.comp_scorecard_df = ComparisonEngine.generate_scorecard(df, self.comp_sim_curves, tolerances=self.comp_tolerances)
            self._display_comp_scorecard()
            self.lbl_comp_subsummary.config(text=(
                f"Bench: {self.comp_scorecard_df.attrs['benchmark_duration']:.2f} min | "
                f"Peak absolute RPM: {self.comp_scorecard_df.attrs['benchmark_peak_text']}\n"
                f'{reference_summary}\n'
                f'Timing quality: {invalid_times} invalid rows excluded; {duplicate_times} duplicate timestamps retained.'))
            self._render_comparison_plot()
        except Exception as exc:
            self.logger.exception('Comparative validation failed')
            self._clear_comparison_results()
            messagebox.showerror('Validation Error', f'Failed to execute comparative validation:\n{exc}')

    def export_comp_excel(self):
        if self.comp_scorecard_df is None or self.comp_scorecard_df.empty:
            messagebox.showwarning("No Data", "Please run validation first before exporting.")
            return
        p = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel Workbook", "*.xlsx")])
        if p:
            try:
                raw_rows = len(self.comp_raw_df) if self.comp_raw_df is not None else 0
                visible_traces = []
                for spec in specs_for_curves(self.comp_sim_curves):
                    state = self.comp_signal_visibility.get(spec['key'], {})
                    if state.get('sim') is not None and state['sim'].get():
                        visible_traces.append(f"Sim: {spec['label']}")
                    if state.get('bench') is not None and state['bench'].get():
                        visible_traces.append(
                            f"Bench: {self.comp_signal_bench_columns.get(spec['key'], spec['label'])}"
                        )
                with atomic_output(p) as temporary:
                    with pd.ExcelWriter(temporary, engine='openpyxl') as writer:
                        write_excel_frame(writer, self.comp_scorecard_df, 'Scorecard_Summary')
                        if self.comp_raw_df is not None:
                            write_excel_frame(writer, self.comp_raw_df, 'Raw_Test_Log')
                            write_excel_frame(writer, self._data_quality_frame(self.comp_raw_df), 'Bench_Data_Quality')
                        for curve_name, curve_df in (self.comp_sim_curves or {}).items():
                            if isinstance(curve_df, pd.DataFrame):
                                safe_name = re.sub(r'[^A-Za-z0-9]+', '_', str(curve_name)).strip('_')
                                write_excel_frame(writer, curve_df, f'Sim_{safe_name}')
                        heater_states = ComparisonEngine.heater_state_report(self.comp_raw_df,self.comp_sim_curves)
                        if not heater_states.empty:
                            write_excel_frame(writer,heater_states,'Heater_State_Comparison')
                        if self.comp_csv_adapter is not None:
                            write_excel_frame(writer, self.comp_csv_adapter.frame, 'Simulation_CSV')
                            write_excel_frame(writer, self.comp_csv_adapter.report_dataframe(), 'CSV_Trace_Quality')
                            write_excel_frame(writer, self._metadata_frame(self.comp_csv_adapter.analysis_info()), 'CSV_Units')
                            if hasattr(self.comp_csv_adapter, 'file_report'):
                                write_excel_frame(writer, self.comp_csv_adapter.file_report(), 'Package_Files')
                                write_excel_frame(writer, self._metadata_frame(self.comp_csv_adapter.package_metadata), 'Package_Metadata')
                        if self.comp_image_analyzer is not None:
                            write_excel_frame(writer, self.comp_image_analyzer.report_dataframe(), 'Image_Trace_Quality')
                            write_excel_frame(writer, self._metadata_frame(self.comp_image_analyzer.analysis_info()), 'Image_Calibration')
                        write_excel_frame(writer, self._metadata_frame({
                            'Exported at': export_timestamp(),
                            'Bench source': getattr(self, 'comp_result_source', ''),
                            'Simulation reference source': self.comp_sim_csv_path or self.comp_sim_img_path or '',
                            'Reference type': ('ZIP' if self.comp_sim_csv_path.lower().endswith('.zip') else 'CSV') if self.comp_sim_csv_path else 'Image',
                            'Bench rows': raw_rows, 'Rows exported': raw_rows,
                            'Time alignment': 'First valid sample is time zero; no automatic stretching or phase alignment.',
                            'Visible plot traces': visible_traces,
                            'Difference colour bands': self.comp_scorecard_df.attrs.get('colour_bands', {}),
                            'Bench quality': self.comp_raw_df.attrs.get('comparison_data_quality', {}),
                            'Scorecard notes': self.comp_scorecard_df.attrs,
                        }), 'Comparison_Info')
                messagebox.showinfo("Export Successful", f"Validation workbook saved to:\n{p}")
            except Exception as exc:
                self.logger.exception('Comparison workbook export failed')
                messagebox.showerror("Export Failed", f"Could not write the validation workbook:\n{exc}")

    def export_comp_plot_image(self):
        if not self.comp_fig:
            messagebox.showwarning("No Graph", "Please run validation to generate a comparison plot first.")
            return
        p = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG Image", "*.png"), ("PDF Document", "*.pdf"), ("SVG Vector", "*.svg")])
        if p:
            try:
                with atomic_output(p) as temporary:
                    self.comp_fig.savefig(temporary, dpi=300, bbox_inches='tight')
                messagebox.showinfo("Export Successful", f"High-resolution comparison plot exported to:\n{p}")
            except Exception as exc:
                self.logger.exception('Comparison image export failed')
                messagebox.showerror("Export Failed", f"Could not save the comparison plot:\n{exc}")

    def _show_tree_context_menu(self, event):
        item = self.sig_tree.identify_row(event.y)
        if not item: return
        self.sig_tree.selection_set(item)
        values = self.sig_tree.item(item, "values")
        if not values: return
        sig_name = values[0]
        tree_menu = tk.Menu(self, tearoff=0)
        tree_menu.add_command(label=f"📋 Copy '{sig_name}' Data", command=lambda: self._copy_to_clipboard(f"{sig_name}: C1={values[1]}, C2={values[2]}, Δ={values[3]}"))
        tree_menu.add_separator()
        tree_menu.add_command(label="📊 Save Full Dataset to Excel (.xlsx)", command=self.export_excel)
        tree_menu.add_command(label="💾 Save Dashboard Image (PNG/PDF)", command=self.export_image)
        try: tree_menu.tk_popup(event.x_root, event.y_root)
        finally: tree_menu.grab_release()

    def _copy_to_clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()

    def select_all_signals(self):
        for conf in self.grid_widgets.values(): conf['enabled'].set(True)

    def deselect_all_signals(self):
        for conf in self.grid_widgets.values(): conf['enabled'].set(False)

    def reset_all(self):
        self._dispose_manager('zoom_manager')
        if self.current_fig is not None:
            plt.close(self.current_fig)
            self.current_fig = None
        self.current_axes = []
        self.current_twin_axes = []
        self.c1_lines = []
        self.c2_lines = []
        self.zoom_manager = None
        self.aligned_df = None
        self._cursor_trace_cache = {}
        self._cursor_cache_frame = None
        self._kpi_rows = []
        self.comp_image_analyzer = None
        self.comp_image_calibration = {}
        if hasattr(self, 'pd_path'): del self.pd_path
        if hasattr(self, 'rd_path'): del self.rd_path
        self.comp_raw_path = None
        self.comp_sim_csv_path = None
        self.comp_csv_adapter = None
        self.comp_csv_settings = {'time_unit': 'min', 'pressure_unit': 'unknown', 'remaining_time_unit': 'min', 'pressure_display_unit': 'Pa', 'preserve_pressure_numbers': True}
        self.comp_sim_img_path = None
        self.lbl_pd.config(text="No file selected", foreground="gray")
        self.lbl_rd.config(text="No file selected", foreground="gray")
        if hasattr(self, 'lbl_comp_sim'): self.lbl_comp_sim.config(text="No simulation reference selected", foreground="gray")
        if hasattr(self, 'lbl_pd_quick'): self.lbl_pd_quick.config(text="No file", foreground="gray")
        if hasattr(self, 'lbl_rd_quick'): self.lbl_rd_quick.config(text="No file", foreground="gray")
        for w in self.scroll_frame.winfo_children(): w.destroy()
        for w in self.plot_container.winfo_children(): w.destroy()
        for item in self.sig_tree.get_children(): self.sig_tree.delete(item)
        for item in self.kpi_tree.get_children(): self.kpi_tree.delete(item)
        self.grid_widgets.clear()
        if self.telemetry._adapter:
            self.telemetry._adapter.close()
            self.telemetry._adapter = None
        self.telemetry.set_signals([], 'No recording loaded')
        self._refresh_comp_raw_label()
        self._clear_comparison_results()
        messagebox.showinfo("Reset", "Workspace reset successfully.")

    def load_pd(self):
        p = filedialog.askopenfilename(filetypes=[("Data Files", "*.csv;*.CSV;*.xlsx;*.xls;*.tsv;*.txt"), ("All Files", "*.*")])
        if p:
            try:
                if smart_read_file(p).empty:
                    raise DataReadError('The selected file contains no data rows.')
            except DataReadError as exc:
                messagebox.showerror('File Read Error', str(exc))
                return
            self.pd_path = p
            self.dashboard_inputs_changed = True
            self.lbl_data_notice.config(text='Inputs changed. Render the dashboard to apply them; the displayed graph still uses its previous data.')
            base = os.path.basename(p)
            self.lbl_pd.config(text=base, foreground="#e8e9ed")
            if hasattr(self, 'lbl_pd_quick'):
                short_name = (base[:15] + "..") if len(base) > 17 else base
                self.lbl_pd_quick.config(text=short_name, foreground="#e8e9ed")
            if not getattr(self, 'comp_raw_path', None) and not getattr(self, 'rd_path', None):
                self._refresh_comp_raw_label()
                self._clear_comparison_results()
            self.populate_signal_grid()

    def load_rd(self):
        p = filedialog.askopenfilename(filetypes=[("Data Files", "*.csv;*.CSV;*.xlsx;*.xls;*.tsv;*.txt"), ("All Files", "*.*")])
        if p:
            try:
                if smart_read_file(p).empty:
                    raise DataReadError('The selected file contains no data rows.')
            except DataReadError as exc:
                messagebox.showerror('File Read Error', str(exc))
                return
            self.rd_path = p
            self.dashboard_inputs_changed = True
            self.lbl_data_notice.config(text='Inputs changed. Render the dashboard to apply them; the displayed graph still uses its previous data.')
            base = os.path.basename(p)
            self.lbl_rd.config(text=base, foreground="#e8e9ed")
            if hasattr(self, 'lbl_rd_quick'):
                short_name = (base[:15] + "..") if len(base) > 17 else base
                self.lbl_rd_quick.config(text=short_name, foreground="#e8e9ed")
            if not getattr(self, 'comp_raw_path', None):
                self._refresh_comp_raw_label()
                self._clear_comparison_results()
            self.populate_signal_grid()

    def populate_signal_grid(self):
        if not hasattr(self, 'pd_path') and not hasattr(self, 'rd_path'): return
        previous = self._signal_settings()

        try:
            raw_pd = smart_read_file(getattr(self, 'pd_path', ''))
            raw_rd = smart_read_file(getattr(self, 'rd_path', ''))
        except DataReadError as exc:
            messagebox.showerror("File Read Error", str(exc))
            return

        for w in self.scroll_frame.winfo_children(): w.destroy()

        headers = ["Plot?", "Original Column", "Display Label", "Subplot Panel", "Right Y-Axis?", "Style", "Width", "Color", "Y-Min", "Y-Max"]
        for col_idx, h in enumerate(headers):
            ttk.Label(self.scroll_frame, text=h, font=(UI_FONT, 9, "bold")).grid(row=0, column=col_idx, padx=6, pady=4, sticky=tk.W)

        signals = []
        pd_pressure_units = infer_pressure_units(raw_pd)
        rd_pressure_units = infer_pressure_units(raw_rd)
        if not raw_pd.empty:
            for col in raw_pd.columns:
                if categorize_signal(col)['type'] != 'METADATA' and not str(col).lower().startswith('unnamed'):
                    signals.append((str(col), str(col), 'File 1', str(col), f"{col}_BIN", pd_pressure_units.get(col)))
        if not raw_rd.empty:
            for col in raw_rd.columns:
                if categorize_signal(col)['type'] != 'METADATA' and not str(col).lower().startswith('unnamed'):
                    is_duplicate = col in raw_pd.columns
                    existing_ids = {signal[0] for signal in signals}
                    signal_id = f"{col} [File 2]" if str(col) in existing_ids else str(col)
                    data_col = f"{col}_ops" if is_duplicate else str(col)
                    binary_col = f"{col}_BIN_ops" if is_duplicate else f"{col}_BIN"
                    signals.append((signal_id, str(col), 'File 2', data_col, binary_col, rd_pressure_units.get(col)))

        self.grid_widgets = {}

        for row_idx, (signal_id, col_str, origin, data_col, binary_col, pressure_unit) in enumerate(signals, start=1):
            lbl_orig = f"[{origin}] {col_str}"
            cfg = categorize_signal(col_str, pressure_unit=pressure_unit)
            source_path = getattr(self, 'pd_path' if origin == 'File 1' else 'rd_path', '')
            source_frame = raw_pd if origin == 'File 1' else raw_rd
            declared_unit = get_column_unit(source_frame, col_str)
            if declared_unit and cfg['type'] not in ('VALVE', 'DOOR_LOCK', 'STAGE', 'STATUS_FLAG'):
                cfg['name'] = re.sub(r'\([^)]*\)$', f'({declared_unit})', cfg['name'])
            saved = previous.get(signal_id, {})
            if saved.get('source_path') == source_path and saved.get('source_col') == col_str:
                cfg.update({key: saved[key] for key in cfg if key in saved})

            chk = ttk.Checkbutton(self.scroll_frame, variable=(enabled_var := tk.BooleanVar(value=cfg['enabled'])))
            chk.grid(row=row_idx, column=0, padx=4)

            ttk.Label(self.scroll_frame, text=lbl_orig).grid(row=row_idx, column=1, sticky=tk.W, padx=4)

            ent_name = ttk.Entry(self.scroll_frame, width=22)
            ent_name.insert(0, cfg['name'])
            ent_name.grid(row=row_idx, column=2, padx=4)

            cb_panel = ttk.Combobox(self.scroll_frame, values=[f"Panel {i}" for i in range(1, 11)], width=9, state="readonly")
            cb_panel.set(cfg['panel'])
            cb_panel.grid(row=row_idx, column=3, padx=4)

            twin_var = tk.BooleanVar(value=cfg['twin'])
            chk_twin = ttk.Checkbutton(self.scroll_frame, variable=twin_var)
            chk_twin.grid(row=row_idx, column=4, padx=4)

            cb_style = ttk.Combobox(self.scroll_frame, values=["Continuous (-)", "Dashed (--)", "Dotted (:)", "Dash-dot (-.)"], width=14, state="readonly")
            cb_style.set(cfg['style'])
            cb_style.grid(row=row_idx, column=5, padx=4)

            ent_lw = ttk.Entry(self.scroll_frame, width=5)
            try:
                default_line_width = float(saved['width']) if saved.get('source_path') == source_path and 'width' in saved else min(float(cfg['width']), 1.25)
            except (TypeError, ValueError):
                default_line_width = 1.0
            ent_lw.insert(0, f"{default_line_width:g}")
            ent_lw.grid(row=row_idx, column=6, padx=4)

            btn_col = tk.Button(self.scroll_frame, bg=cfg['color'], width=4, relief="ridge")
            btn_col.config(command=lambda b=btn_col: self._pick_color(b))
            btn_col.grid(row=row_idx, column=7, padx=4)

            ent_ymin = ttk.Entry(self.scroll_frame, width=6)
            ent_ymin.insert(0, cfg['ymin'])
            ent_ymin.grid(row=row_idx, column=8, padx=3)

            ent_ymax = ttk.Entry(self.scroll_frame, width=6)
            ent_ymax.insert(0, cfg['ymax'])
            ent_ymax.grid(row=row_idx, column=9, padx=3)

            self.grid_widgets[signal_id] = {
                "enabled": enabled_var, "name": ent_name, "panel": cb_panel, "twin": twin_var,
                "style": cb_style, "width": ent_lw, "btn_col": btn_col, "ymin": ent_ymin, "ymax": ent_ymax,
                "source_col": col_str, "data_col": data_col, "binary_col": binary_col
                , "source_path": source_path, "origin": origin
            }

    def _pick_color(self, button):
        color = colorchooser.askcolor(color=button.cget("bg"))[1]
        if color: button.config(bg=color)

    def execute_and_view(self):
        try:
            offset_val = float(self.manual_offset.get().strip() or "0")
            if not np.isfinite(offset_val):
                raise ValueError('The time offset must be a finite number of minutes.')
            pd_path = getattr(self, 'pd_path', None)
            rd_path = getattr(self, 'rd_path', None)

            if not pd_path and not rd_path:
                messagebox.showwarning("Missing Data", "Please select at least one data file.")
                return

            if not self.grid_widgets:
                self.populate_signal_grid()

            strategy = self.sync_mode.get()
            selected_hook = self.patch_manager.custom_sync_hooks.get(strategy)
            engine = DataEngine(pd_path, rd_path, 'Raw Timestamps (No Shift)' if selected_hook else strategy, offset_val)
            merged = engine.get_data()

            if merged.empty:
                messagebox.showerror("No Data", "Unable to extract valid data from the selected file(s).")
                return
            if engine.used_synthetic_time:
                messagebox.showwarning(
                    "Assumed Time Axis",
                    "No time column was found. The chart uses an assumed 1-second interval between rows."
                )

            if selected_hook is not None:
                inherited = merged.attrs.copy()
                merged = selected_hook(merged.copy())
                if not isinstance(merged, pd.DataFrame) or merged.empty or 'relative_minutes' not in merged:
                    raise ValueError('The selected synchronization plugin must return data with relative_minutes.')
                merged.attrs = {**inherited, **merged.attrs}
                merged.attrs['sync_report'] = {**merged.attrs.get('sync_report', {}), 'selected_plugin': strategy}

            options = {
                'title': self.txt_title.get(),
                'font_size': int(self.slider_font.get()),
                'show_grid': self.var_grid_toggle.get(),
                'show_legends': self.var_show_legends.get(),
                'annotate_peak': self.var_annotate_peak.get(),
                'highlight_overlap': self.var_valve_overlap.get(),
                'custom_plot_hooks': self.patch_manager.custom_plot_hooks
            }

            fig, axes, twin_axes, c1_lines, c2_lines, error_msg = DashboardPlotter.render(
                merged, self.grid_widgets, options
            )
            if error_msg:
                messagebox.showwarning("Notice", error_msg)
                return

            self._dispose_manager('zoom_manager')
            for widget in self.plot_container.winfo_children():
                widget.destroy()
            if self.current_fig is not None:
                plt.close(self.current_fig)
            self.aligned_df = merged
            self.dashboard_grid_widgets = self._freeze_signal_settings()
            self.dashboard_inputs_changed = False
            self._cursor_cache_frame = None
            self.dashboard_result_settings = {
                'Primary file': pd_path, 'Machine file': rd_path,
                'Sync strategy': strategy, 'Manual offset minutes': offset_val,
                'Title': self.txt_title.get(), 'Signals': self._signal_settings(),
            }

            self.current_fig = fig
            self.current_axes = axes
            self.current_twin_axes = twin_axes
            self.c1_lines = c1_lines
            self.c2_lines = c2_lines

            host = ScrollableFigureHost(self.plot_container, fig, len(axes))
            host.pack(fill=tk.BOTH, expand=True)
            self.dashboard_figure_host = host
            canvas = host.canvas
            canvas.draw()

            self.zoom_manager = ZoomInteractionManager(
                canvas, axes, twin_axes, c1_lines, c2_lines,
                on_cursor_change=self._on_cursor_updated,
                on_hover=self._on_hover_updated,
                on_export_excel=self.export_excel,
                on_export_image=self.export_image,
                on_export_csv=self.export_csv
            )

            self.lbl_test_title.config(text=f"Program: {self.txt_title.get()}")
            warnings = merged.attrs.get('data_warnings', [])
            self.lbl_data_notice.config(text=('Data notes: ' + ' · '.join(map(str, warnings))) if warnings else '')
            self._update_kpi_table()
            self._on_cursor_updated()

            self.telemetry.set_signals(signals_from_aligned(merged, self.dashboard_grid_widgets),
                                       "Aligned bench recording · " + self.txt_title.get())
            self.tabs.select(self.tab_telemetry)

        except Exception as e:
            self.logger.exception('Dashboard processing failed')
            messagebox.showerror("Execution Failure", f"Processing error: {str(e)}")

    def _set_tool(self, tool_name):
        manager = self._active_zoom_manager()
        if manager: manager.set_mode(tool_name)

    def _zoom_back_trigger(self):
        manager = self._active_zoom_manager()
        if manager: manager.zoom_back()

    def _zoom_forward_trigger(self):
        manager = self._active_zoom_manager()
        if manager: manager.zoom_forward()

    def _reset_zoom_trigger(self):
        manager = self._active_zoom_manager()
        if manager: manager.reset_zoom()

    def _toggle_dual_cursor_btn(self):
        if self.zoom_manager: self.zoom_manager.toggle_dual_cursor()

    def _on_target_changed(self):
        if self.zoom_manager:
            target = self.var_cursor_target.get()
            self.zoom_manager.set_active_cursor_target(target)
            if target == "C2" and not self.zoom_manager.dual_cursor_active:
                self.zoom_manager.toggle_dual_cursor()

    def _jump_c1_start(self):
        if self.aligned_df is not None and not self.aligned_df.empty and self.zoom_manager:
            self.zoom_manager._set_c1_time(float(self.aligned_df['relative_minutes'].min()))

    def _jump_c1_end(self):
        if self.aligned_df is not None and not self.aligned_df.empty and self.zoom_manager:
            self.zoom_manager._set_c1_time(float(self.aligned_df['relative_minutes'].max()))

    def _jump_c2_start(self):
        if self.aligned_df is not None and not self.aligned_df.empty and self.zoom_manager:
            if not self.zoom_manager.dual_cursor_active: self.zoom_manager.toggle_dual_cursor()
            self.zoom_manager._set_c2_time(float(self.aligned_df['relative_minutes'].min()))

    def _jump_c2_end(self):
        if self.aligned_df is not None and not self.aligned_df.empty and self.zoom_manager:
            if not self.zoom_manager.dual_cursor_active: self.zoom_manager.toggle_dual_cursor()
            self.zoom_manager._set_c2_time(float(self.aligned_df['relative_minutes'].max()))

    def _on_hover_updated(self, x, y):
        if hasattr(self, 'lbl_hover_info') and y is not None:
            self.lbl_hover_info.config(text=f"🖱 Mouse: t = {x:.3f} min | y = {y:.1f}")

    def _cursor_trace(self, column, kind='analog'):
        if self._cursor_cache_frame is not self.aligned_df:
            self._cursor_trace_cache = {}
            self._cursor_cache_frame = self.aligned_df
        key = (column, kind)
        if key not in self._cursor_trace_cache:
            values = self.aligned_df[column]
            if kind in ('digital', 'lock'):
                values = normalize_control_series(values, column)
            elif kind == 'stage':
                values = normalize_program_stage_series(values)
            self._cursor_trace_cache[key] = prepare_trace(
                self.aligned_df['relative_minutes'], values, kind)
        return self._cursor_trace_cache[key]

    def _on_cursor_updated(self):
        if self.aligned_df is None or self.aligned_df.empty or len(self.c1_lines) == 0: return

        t_c1 = float(self.c1_lines[0].get_xdata()[0])
        c1_text = f"🔴 C1: {t_c1:.2f} min ({t_c1 * 60.0:.1f} s)"
        self.lbl_c1_info.config(text=c1_text)
        if hasattr(self, 'lbl_caliper_c1'): self.lbl_caliper_c1.config(text=c1_text)

        t_c2 = None
        if self.zoom_manager and self.zoom_manager.dual_cursor_active and len(self.c2_lines) > 0:
            t_c2 = float(self.c2_lines[0].get_xdata()[0])
            dt = abs(t_c2 - t_c1)
            c2_text = f"🔵 C2: {t_c2:.2f} min ({t_c2 * 60.0:.1f} s)"
            dt_text = f"⏱ Δt: {dt:.2f} min ({dt * 60.0:.1f} s / {dt/60.0:.2f} h)"
            self.lbl_c2_info.config(text=c2_text)
            self.lbl_diff_info.config(text=dt_text)
            if hasattr(self, 'lbl_caliper_c2'): self.lbl_caliper_c2.config(text=c2_text)
            if hasattr(self, 'lbl_caliper_dt'): self.lbl_caliper_dt.config(text=f"⏱ Δt: {dt:.2f} min ({dt * 60.0:.1f} s)")
        else:
            self.lbl_c2_info.config(text="🔵 C2: Off")
            self.lbl_diff_info.config(text="⏱ Δt: —")
            if hasattr(self, 'lbl_caliper_c2'): self.lbl_caliper_c2.config(text="🔵 C2: Off")
            if hasattr(self, 'lbl_caliper_dt'): self.lbl_caliper_dt.config(text="⏱ Δt: —")

        p_col = find_power_column(self.aligned_df.columns)
        e_col = find_energy_column(self.aligned_df.columns)

        p_str, e_str = "—", "—"
        self.lbl_live_p.config(text="⚡ P: — W")
        self.lbl_live_e.config(text="🔋 E: — Wh")
        if p_col is not None:
            try:
                p_val = sample_trace(self._cursor_trace(p_col), t_c1)
                p_val = float(convert_signal_units(pd.Series([p_val]), get_column_unit(self.aligned_df, p_col), 'W').iloc[0])
                if np.isfinite(p_val):
                    self.lbl_live_p.config(text=f"⚡ P: {p_val:.1f} W")
                    p_str = f"{p_val:.1f} W"
            except Exception: pass

        if e_col is not None:
            try:
                e_val = sample_trace(self._cursor_trace(e_col), t_c1)
                e_val = float(convert_signal_units(pd.Series([e_val]), get_column_unit(self.aligned_df, e_col), 'Wh').iloc[0])
                if np.isfinite(e_val):
                    self.lbl_live_e.config(text=f"🔋 E: {e_val:.2f} Wh")
                    e_str = f"{e_val:.2f} Wh"
            except Exception: pass

        if hasattr(self, 'lbl_caliper_pe'):
            self.lbl_caliper_pe.config(text=f"⚡ P: {p_str}  |  🔋 E: {e_str}")

        self._refresh_signal_table(t_c1, t_c2)

    def _refresh_signal_table(self, t_c1, t_c2):
        for item in self.sig_tree.get_children(): self.sig_tree.delete(item)

        for col, conf in getattr(self, 'dashboard_grid_widgets', self.grid_widgets).items():
            if not conf['enabled'].get(): continue
            target_col = conf.get('binary_col', f"{conf.get('data_col', col)}_BIN")
            if target_col not in self.aligned_df.columns:
                target_col = conf.get('data_col', col)
            if target_col not in self.aligned_df.columns: continue

            disp_name = conf['name'].get()
            source_kind = classify_signal_kind(conf.get('source_col', col))
            kind = {'control': 'digital', 'door_lock': 'lock', 'stage': 'stage'}.get(source_kind, 'analog')
            trace = self._cursor_trace(target_col, kind)
            val1, val2 = sample_trace(trace, t_c1), sample_trace(trace, t_c2)
            val1_str, val2_str = format_sample(val1, kind), format_sample(val2, kind)
            diff_str = f'{val2 - val1:+.2f}' if np.isfinite(val1) and np.isfinite(val2) else '—'
            values = trace[1][np.isfinite(trace[1])]
            min_str = f'{values.min():.2f}' if values.size else '—'
            max_str = f'{values.max():.2f}' if values.size else '—'
            mean_str = f'{values.mean():.2f}' if values.size else '—'

            self.sig_tree.insert("", tk.END, values=(disp_name, val1_str, val2_str, diff_str, min_str, max_str, mean_str))

    def _update_kpi_table(self):
        for item in self.kpi_tree.get_children(): self.kpi_tree.delete(item)
        if self.aligned_df is None or self.aligned_df.empty: return
        metrics = engineering_metrics(self.aligned_df)

        for hook in self.patch_manager.custom_kpi_hooks:
            try:
                extra = hook(self.aligned_df)
                if isinstance(extra, list): metrics.extend(extra)
            except Exception:
                self.logger.exception('KPI plugin failed')
                metrics.append(('Plugin KPI', 'Unavailable · see application.log'))

        self._kpi_rows = metrics

        for label, val in metrics:
            self.kpi_tree.insert("", tk.END, values=(label, val))

    @staticmethod
    def _metadata_frame(metadata):
        return pd.DataFrame([
            {'Setting': str(key), 'Value': (json.dumps(value, default=str, ensure_ascii=False)
                                          if isinstance(value, (dict, list, tuple)) else str(value))}
            for key, value in metadata.items()
        ], columns=['Setting', 'Value'])

    @staticmethod
    def _data_quality_frame(frame):
        rows = []
        for column in frame.columns:
            series = frame[column]
            numeric = pd.to_numeric(series, errors='coerce')
            invalid_numeric = int((numeric.notna() & ~np.isfinite(numeric.to_numpy(dtype=float, na_value=np.nan))).sum())
            rows.append({'Signal': str(column), 'Rows': len(series),
                         'Missing readings': int(series.isna().sum()),
                         'Non-finite numeric readings': invalid_numeric,
                         'Unit': get_column_unit(frame, column) or 'Not stated'})
        return pd.DataFrame(rows)

    def show_data_quality(self):
        if self.aligned_df is None or self.aligned_df.empty:
            messagebox.showinfo('Data Quality', 'Render a dashboard first to inspect its recorded data.')
            return
        window = tk.Toplevel(self)
        window.title('Data Quality & Synchronization')
        window.geometry('850x550')
        notes = self.aligned_df.attrs.get('data_warnings', [])
        report = self.aligned_df.attrs.get('sync_report', {})
        ttk.Label(window, text='\n'.join(map(str, notes)) or 'No data warnings were reported.',
                  foreground='#b2bac7', wraplength=800, padding=10).pack(fill=tk.X)
        ttk.Label(window, text=json.dumps(report, ensure_ascii=False, default=str),
                  wraplength=800, padding=(10, 0)).pack(fill=tk.X)
        body = ttk.Frame(window, padding=10)
        body.pack(fill=tk.BOTH, expand=True)
        frame = self._data_quality_frame(self.aligned_df)
        tree = ttk.Treeview(body, columns=list(frame.columns), show='headings')
        for column in frame.columns:
            tree.heading(column, text=column)
            tree.column(column, width=180 if column == 'Signal' else 140, stretch=False)
        vertical = ttk.Scrollbar(body, orient=tk.VERTICAL, command=tree.yview)
        horizontal = ttk.Scrollbar(body, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        tree.grid(row=0, column=0, sticky=tk.NSEW)
        vertical.grid(row=0, column=1, sticky=tk.NS)
        horizontal.grid(row=1, column=0, sticky=tk.EW)
        for row in frame.itertuples(index=False, name=None):
            tree.insert('', tk.END, values=row)

    def export_image(self):
        if not self.current_fig:
            messagebox.showinfo('No Graph', 'Render a dashboard before saving an image.')
            return
        p = filedialog.asksaveasfilename(defaultextension=".png", filetypes=[("PNG Image", "*.png"), ("PDF Document", "*.pdf"), ("SVG Vector", "*.svg")])
        if p:
            try:
                with atomic_output(p) as temporary:
                    self.current_fig.savefig(temporary, dpi=300, bbox_inches='tight')
                messagebox.showinfo("Export Successful", f"High-res figure exported to:\n{p}")
            except Exception as exc:
                self.logger.exception('Dashboard image export failed')
                messagebox.showerror('Export Failed', f'Could not save the graph:\n{exc}')

    def export_excel(self):
        if self.aligned_df is None or self.aligned_df.empty:
            messagebox.showinfo('No Data', 'Render a dashboard before exporting its data.')
            return
        p = filedialog.asksaveasfilename(defaultextension=".xlsx", filetypes=[("Excel Workbook", "*.xlsx")])
        if p:
            try:
                with atomic_output(p) as temporary:
                    with pd.ExcelWriter(temporary, engine='openpyxl') as writer:
                        write_excel_frame(writer, pd.DataFrame(self._kpi_rows, columns=['Parameter', 'Value']), 'Summary_KPIs')
                        write_excel_frame(writer, self.aligned_df, 'Synchronized_Series')
                        write_excel_frame(writer, self._data_quality_frame(self.aligned_df), 'Data_Quality')
                        write_excel_frame(writer, self._metadata_frame({
                            'Exported at': export_timestamp(),
                            'Dashboard sources and settings': getattr(self, 'dashboard_result_settings', {}),
                            'Data warnings': self.aligned_df.attrs.get('data_warnings', []),
                            'Synchronization': self.aligned_df.attrs.get('sync_report', {}),
                        }), 'Report_Info')
                messagebox.showinfo("Export Successful", f"Workbook saved to:\n{p}")
            except Exception as exc:
                self.logger.exception('Dashboard workbook export failed')
                messagebox.showerror('Export Failed', f'Could not save the workbook:\n{exc}')

    def export_csv(self):
        if self.aligned_df is None or self.aligned_df.empty:
            messagebox.showinfo('No Data', 'Render a dashboard before exporting its data.')
            return
        p = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Data File", "*.csv")])
        if p:
            try:
                with atomic_output(p) as temporary:
                    self.aligned_df.to_csv(temporary, index=False)
                messagebox.showinfo("Export Successful", f"CSV file exported to:\n{p}")
            except Exception as exc:
                self.logger.exception('Dashboard CSV export failed')
                messagebox.showerror('Export Failed', f'Could not save the data:\n{exc}')

    def _signal_settings(self):
        signals = {}
        for column, configuration in self.grid_widgets.items():
            signals[str(column)] = {
                key: configuration[key].get()
                for key in ('enabled', 'name', 'panel', 'twin', 'style', 'width', 'ymin', 'ymax')
            }
            signals[str(column)]['color'] = configuration['btn_col'].cget('bg')
            signals[str(column)].update({key: configuration.get(key, '')
                                        for key in ('source_col', 'source_path', 'origin')})
        return signals

    def _freeze_signal_settings(self):
        return {
            column: {
                key: (_SavedValue(value.cget('bg')) if key == 'btn_col' else
                      _SavedValue(value.get()) if key in ('enabled', 'name', 'panel', 'twin', 'style', 'width', 'ymin', 'ymax') else value)
                for key, value in configuration.items()
            }
            for column, configuration in self.grid_widgets.items()
        }

    def save_preset(self):
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Preset", "*.json")])
        if p:
            data = {'version': 2, 'signals': self._signal_settings(), 'options': {
                'title': self.txt_title.get(), 'sync_strategy': self.sync_mode.get(),
                'offset_minutes': self.manual_offset.get(), 'font_size': self.slider_font.get(),
                'show_grid': self.var_grid_toggle.get(), 'show_legends': self.var_show_legends.get(),
                'annotate_peak': self.var_annotate_peak.get(), 'highlight_overlap': self.var_valve_overlap.get(),
                            }}
            try:
                with atomic_output(p) as temporary:
                    with open(temporary, 'w', encoding='utf-8') as file:
                        json.dump(data, file, indent=2, ensure_ascii=False)
                messagebox.showinfo("Saved", "Signal settings and layout options saved.")
            except (OSError, ValueError) as exc:
                self.logger.exception('Preset save failed')
                messagebox.showerror('Save Failed', f'Could not save the preset:\n{exc}')

    def load_preset(self):
        p = filedialog.askopenfilename(filetypes=[("JSON Preset", "*.json")])
        if p and os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f: data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("Preset root must be a JSON object.")
                if 'version' in data and data['version'] != 2:
                    raise ValueError('This preset version is not supported.')
                signals = data.get('signals', {}) if 'version' in data else data
                options = data.get('options', {}) if 'version' in data else {}
                if not isinstance(signals, dict) or not isinstance(options, dict):
                    raise ValueError('Preset signal settings and options must be JSON objects.')
                for column, values in signals.items():
                    if not isinstance(values, dict):
                        raise ValueError(f'Invalid settings for {column}.')
                    for field in ('enabled', 'twin'):
                        if field in values and not isinstance(values[field], bool):
                            raise ValueError(f'{column}: {field} must be true or false.')
                    width = float(values.get('width', '1.5'))
                    if not np.isfinite(width) or width <= 0:
                        raise ValueError(f'{column}: line width must be positive and finite.')
                    bounds = [float(values[field]) if str(values.get(field, '')).strip() else None for field in ('ymin', 'ymax')]
                    if any(value is not None and not np.isfinite(value) for value in bounds):
                        raise ValueError(f'{column}: axis limits must be finite.')
                    if all(value is not None for value in bounds) and bounds[0] >= bounds[1]:
                        raise ValueError(f'{column}: Y-Min must be less than Y-Max.')
                    if values.get('panel', 'Panel 1') not in [f'Panel {i}' for i in range(1, 11)]:
                        raise ValueError(f'{column}: unknown panel.')
                    if values.get('style', 'Continuous (-)') not in ('Continuous (-)', 'Dashed (--)', 'Dotted (:)', 'Dash-dot (-.)'):
                        raise ValueError(f'{column}: unknown line style.')
                    self.winfo_rgb(values.get('color', '#003366'))
                offset = float(options.get('offset_minutes', 0))
                font = float(options.get('font_size', 9))
                if not np.isfinite(offset) or not np.isfinite(font) or not 7 <= font <= 14:
                    raise ValueError('Invalid time offset or font size in preset.')
                for field in ('show_grid', 'show_legends', 'annotate_peak', 'highlight_overlap'):
                    if field in options and not isinstance(options[field], bool):
                        raise ValueError(f'{field} must be true or false.')
                tolerances = options.get('comparison_tolerances', self.comp_tolerances)
                if not isinstance(tolerances, dict) or any(key not in self.comp_tolerances for key in tolerances):
                    raise ValueError('Invalid comparison tolerance settings.')
                tolerances = {key: float(tolerances.get(key, value)) for key, value in self.comp_tolerances.items()}
                if any(not np.isfinite(value) or value < 0 for value in tolerances.values()):
                    raise ValueError('Comparison tolerances must be finite and zero or greater.')
            except (OSError, json.JSONDecodeError, ValueError, TypeError, tk.TclError) as exc:
                messagebox.showerror("Invalid Preset", f"Could not load this preset:\n{exc}")
                return
            matched = 0
            for col, vals in signals.items():
                if col in self.grid_widgets and isinstance(vals, dict):
                    matched += 1
                    self.grid_widgets[col]["enabled"].set(vals.get("enabled", True))
                    self.grid_widgets[col]["name"].delete(0, tk.END)
                    self.grid_widgets[col]["name"].insert(0, vals.get("name", col))
                    panel = vals.get("panel", "Panel 1")
                    if panel not in [f"Panel {i}" for i in range(1, 11)]: panel = "Panel 1"
                    self.grid_widgets[col]["panel"].set(panel)
                    self.grid_widgets[col]["twin"].set(vals.get("twin", False))
                    if "style" in vals: self.grid_widgets[col]["style"].set(vals.get("style", "Continuous (-)"))
                    if "width" in vals:
                        self.grid_widgets[col]["width"].delete(0, tk.END)
                        self.grid_widgets[col]["width"].insert(0, vals.get("width", "1.5"))
                    self.grid_widgets[col]["btn_col"].config(bg=vals.get("color", "#003366"))
                    self.grid_widgets[col]["ymin"].delete(0, tk.END)
                    self.grid_widgets[col]["ymin"].insert(0, vals.get("ymin", ""))
                    self.grid_widgets[col]["ymax"].delete(0, tk.END)
                    self.grid_widgets[col]["ymax"].insert(0, vals.get("ymax", ""))
            for field, variable in (('show_grid', self.var_grid_toggle), ('show_legends', self.var_show_legends),
                                    ('annotate_peak', self.var_annotate_peak), ('highlight_overlap', self.var_valve_overlap)):
                if field in options:
                    variable.set(options[field])
            if 'title' in options:
                self.txt_title.delete(0, tk.END)
                self.txt_title.insert(0, str(options['title']))
            if 'offset_minutes' in options:
                self.manual_offset.delete(0, tk.END)
                self.manual_offset.insert(0, str(offset))
            if 'font_size' in options:
                self.slider_font.set(font)
            if options.get('sync_strategy') in self.sync_mode.cget('values'):
                self.sync_mode.set(options['sync_strategy'])
            self.comp_tolerances = tolerances
            if self.comp_raw_df is not None and self.comp_sim_curves is not None:
                self.comp_scorecard_df = ComparisonEngine.generate_scorecard(
                    self.comp_raw_df, self.comp_sim_curves, tolerances=tolerances)
                self._display_comp_scorecard()
            self.dashboard_inputs_changed = True
            self.lbl_data_notice.config(text='Preset loaded. Render the dashboard to apply these settings.')
            messagebox.showinfo("Loaded", f"Restored {matched} signal settings; {len(signals) - matched} signals did not match loaded files.\nRender the dashboard to apply them.")

if __name__ == "__main__":
    app = ApplianceSignalStudioPro()
    app.mainloop()

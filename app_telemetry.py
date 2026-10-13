"""Video-inspired telemetry presentation; original analysis stays in its workspaces."""
from dataclasses import dataclass
from pathlib import Path
import re
import time
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from app_data import normalize_control_series, normalize_program_stage_series, classify_signal_kind, get_column_unit
from app_inspection import prepare_trace, sample_trace, format_sample
from app_simulation import load_simulation_reference, specs_for_curves

UI_FONT = 'Segoe UI' if sys.platform == 'win32' else 'Helvetica'
UI_MONO = 'Consolas' if sys.platform == 'win32' else 'Courier'

BG = '#101113'
CARD = '#1b1c1f'
PLOT = '#111214'
EDGE = '#303239'
TEXT = '#e8e9ed'
MUTED = '#969da9'
ACCENT = '#c4ff84'
COLORS = ['#96cdf1', '#e4ce80', '#a7afe0', '#73e999', '#80cbea',
          '#cab8ed', '#e6e4c9', '#e79bcf', '#d9d8b8', '#b8e67f']
VIEWS = ['All Normalized Tracks · Stacked Comparison',
         'Thermal Subsystem · Temperature & Heater',
         'Mechanical Drive · Drum Speed',
         'Water & Valves · Pressure, Water, Inlets, Drain',
         'Controller State · STWF & Remaining Time']
GROUPS = {
    'temperature': 1, 'heater_power': 1, 'drum_speed': 2,
    'pressure': 3, 'water': 3, 'pre_wash_valve_open': 3,
    'wash_valve_open': 3, 'drain_open': 3,
    'stwf_number': 4, 'actual_remaining_time': 4,
}
ORDER = ['temperature', 'heater_power', 'drum_speed', 'pressure', 'water',
         'pre_wash_valve_open', 'wash_valve_open', 'drain_open',
         'stwf_number', 'actual_remaining_time']
LABELS = ['Temperature', 'Heater Power', 'Drum Speed', 'Pressure', 'Water',
          'Pre-wash Valve', 'Wash Valve', 'Drain Valve', 'STWF Code', 'Remaining Time']


@dataclass
class TelemetrySignal:
    key: str
    label: str
    unit: str
    kind: str
    trace: tuple
    color: str
    group: int


def signals_from_curves(curves):
    specs = {s['key']: s for s in specs_for_curves(curves)}
    signals = []
    for key in ORDER:
        curve = curves.get(key)
        if curve is None or curve.empty:
            continue
        spec = specs[key]
        signals.append(TelemetrySignal(key, spec['label'], curve.attrs.get('unit', spec['unit']),
                       ('step' if spec.get('step') and spec['kind'] == 'analog' else spec['kind']),
                       prepare_trace(curve['time_min'], curve['value'], 'step' if spec.get('step') and spec['kind'] == 'analog' else spec['kind']),
                       COLORS[ORDER.index(key)], GROUPS[key]))
    return signals


def signals_from_aligned(frame, settings):
    """Use the existing channel mapping, including extra/custom signals."""
    result = []
    for key, conf in settings.items():
        enabled = conf['enabled'].get() if hasattr(conf['enabled'], 'get') else conf['enabled']
        col = conf.get('data_col', key)
        if not enabled or col not in frame:
            continue
        label = conf['name'].get() if hasattr(conf['name'], 'get') else conf['name']
        kind = classify_signal_kind(conf.get('source_col', col))
        kind = {'door_lock': 'lock', 'control': 'digital'}.get(kind, kind)
        if 'stwf' in str(col).lower():
            kind = 'code'
        values = (normalize_control_series(frame[col]) if kind in ('digital', 'lock') else
                  normalize_program_stage_series(frame[col]) if kind == 'stage' else frame[col])
        unit_match = re.search(r'\(([^()]*)\)\s*$', label)
        unit = get_column_unit(frame, col) or (unit_match.group(1) if unit_match else '')
        short = re.sub(r'\s*\([^()]*\)\s*$', '', label)
        lower = (short + ' ' + str(col)).lower()
        group = 1 if any(k in lower for k in ('temp', 'heater', 'heat valve', 'power')) else (
            2 if any(k in lower for k in ('drum', 'drump', 'rpm', 'motor', 'speed')) else (
                3 if any(k in lower for k in ('water', 'pressure', 'valve', 'drain', 'inlet', 'pump')) else 4))
        result.append(TelemetrySignal(str(key), short, unit, kind,
                      prepare_trace(frame['relative_minutes'], values, kind), COLORS[len(result) % 10], group))
    return result


def normalized_values(values):
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if not len(finite):
        return np.full(values.shape, np.nan)
    lo, hi = finite.min(), finite.max()
    if hi == lo:
        return np.where(np.isfinite(values), .5, np.nan)
    return (values - lo) / (hi - lo)


def demo_signals():
    """Illustrative preview only; never enters measured analysis/export pipelines."""
    t = np.linspace(0, 186, 373)
    spin = np.zeros_like(t)
    for start, peak in ((150, 700), (164, 700), (173, 700), (181, 1500)):
        spin += np.maximum(0, 1 - np.abs(t-start)/2.5) * peak
    water = np.interp(t, [0, 5, 23, 35, 145, 148, 157, 162, 169, 174, 179, 186],
                      [0, 26, 26, 28, 28, 10, 42, 0, 35, 0, 26, 0])
    values = [np.interp(t, [0, 8, 25, 40, 145, 160, 186], [22, 22, 34, 40, 40, 29, 27]),
              np.where(((t > 15) & (t < 23)) | ((t > 26) & (t < 35)), 2000, 0),
              np.where(spin > 0, spin, np.where(t > 8, 45, 0)), water * 25,
              water, (t < 10).astype(float),
              (((t < 15) & (t > 5)) | ((t > 148) & (t < 153)) | ((t > 165) & (t < 169))).astype(float),
              (((t > 146) & (t < 150)) | ((t > 158) & (t < 162)) | ((t > 170) & (t < 174)) | (t > 179)).astype(float),
              np.select([t < 15, t < 23, t < 35, t < 148, t < 178], [3, 11, 26, 31, 41], default=49),
              186-t]
    units = ['°C', 'W', 'RPM', 'Pa', 'L', 'state', 'state', 'state', 'code', 'min']
    return [TelemetrySignal(k, LABELS[i], units[i], 'digital' if i in (5,6,7) else 'code' if i == 8 else 'analog',
                            prepare_trace(t, values[i], 'digital' if i in (5,6,7) else 'code' if i == 8 else 'analog'),
                            COLORS[i], GROUPS[k]) for i,k in enumerate(ORDER)]


def demo_phases():
    return [(0,15,'Fill','#96cdf1'), (15,23,'Soak','#a7afe0'), (23,35,'Heat','#73e999'),
            (35,148,'Main Wash',ACCENT), (148,178,'Rinse','#96cdf1'), (178,186,'Spin','#e79bcf')]


def recorded_phase_spans(signals, start, end):
    stage = next((s for s in signals if s.kind in ('stage', 'code')), None)
    if stage is None or not len(stage.trace[0]):
        return [(start,end,'Recording timeline · Phase names unavailable','#32363d')]
    times, values, _kind = stage.trace
    spans = []
    for i, (timestamp,value) in enumerate(zip(times,values)):
        stop = times[i+1] if i+1 < len(times) else end
        label = format_sample(value,stage.kind,stage.unit)
        label = 'Unknown' if label == '—' else ('STWF ' + label if stage.kind == 'code' else label)
        color = COLORS[int(value) % len(COLORS)] if np.isfinite(value) else '#32363d'
        if spans and spans[-1][2:] == (label,color) and spans[-1][1] == timestamp:
            spans[-1] = (spans[-1][0],stop,label,color)
        else:
            spans.append((timestamp,stop,label,color))
    if times[0] > start:
        spans.insert(0,(start,times[0],'Unknown','#32363d'))
    return spans


def install_dark_theme(root):
    style = ttk.Style(root)
    style.theme_use('clam')
    root.configure(background=BG)
    root.option_add('*Font', '{' + UI_FONT + '} 10')
    root.option_add('*TCombobox*Listbox.background', CARD)
    root.option_add('*TCombobox*Listbox.foreground', TEXT)
    root.option_add('*TCombobox*Listbox.selectBackground', '#374834')
    root.option_add('*TCombobox*Listbox.selectForeground', ACCENT)
    style.configure('.', background=CARD, foreground=TEXT, font=(UI_FONT, 10), bordercolor=EDGE,
                    lightcolor=EDGE, darkcolor=EDGE, troughcolor=PLOT, selectbackground='#374834', selectforeground=TEXT)
    style.configure('TFrame', background=BG)
    style.configure('TLabel', background=BG, foreground=TEXT)
    style.configure('TLabelframe', background=BG, bordercolor=EDGE, relief='solid')
    style.configure('TLabelframe.Label', background=BG, foreground=MUTED, font=(UI_FONT, 9, 'bold'))
    style.configure('TButton', background='#25272b', foreground=TEXT, padding=(12, 7), borderwidth=1)
    style.map('TButton', background=[('active', '#34383d'), ('pressed', '#374834')], foreground=[('disabled', '#69707a')])
    style.configure('Accent.TButton', background=ACCENT, foreground='#182013', font=(UI_FONT, 10, 'bold'))
    style.map('Accent.TButton', background=[('active', '#d4ffa6'), ('pressed', '#a4df64')], foreground=[('active', '#182013')])
    style.configure('TEntry', fieldbackground=PLOT, foreground=TEXT, insertcolor=TEXT, padding=5)
    style.configure('TCombobox', fieldbackground=PLOT, foreground=TEXT, arrowcolor=MUTED, padding=6)
    style.map('TCombobox', fieldbackground=[('readonly', PLOT)], foreground=[('readonly', TEXT)], selectbackground=[('readonly', PLOT)])
    for name in ('TCheckbutton', 'TRadiobutton'):
        style.configure(name, background=BG, foreground=TEXT, padding=3)
        style.map(name, background=[('active', BG)], indicatorcolor=[('selected', ACCENT), ('!selected', EDGE)])
    style.configure('TNotebook', background=BG, borderwidth=0, tabmargins=(12, 8, 12, 0))
    style.configure('TNotebook.Tab', background=BG, foreground=MUTED, padding=(17, 11))
    style.map('TNotebook.Tab', background=[('selected', CARD)], foreground=[('selected', ACCENT)])
    style.configure('Treeview', background=PLOT, fieldbackground=PLOT, foreground=TEXT, rowheight=29, borderwidth=0)
    style.configure('Treeview.Heading', background='#25272b', foreground=MUTED, padding=7, relief='flat')
    style.map('Treeview', background=[('selected', '#374834')], foreground=[('selected', TEXT)])
    style.configure('TScrollbar', background='#34373d', arrowcolor=MUTED, borderwidth=0)


class TelemetryWorkspace(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.signals = []
        self.visible = []
        self.when = 0.
        self.playing = False
        self._job = None
        self._last_tick = None
        self._drawing = False
        self.demo = False
        self._adapter = None
        self._phase_ids = []
        self._build()
        self.bind('<Destroy>', self._destroy, add='+')
        self.after_idle(self.draw)

    def _label(self, parent, text='', **kw):
        return tk.Label(parent, text=text, bg=kw.pop('bg', CARD), fg=kw.pop('fg', TEXT), **kw)

    def _build(self):
        outer = tk.Frame(self, bg=BG)
        outer.pack(fill='both', expand=True, padx=28, pady=(22, 14))
        heading = tk.Frame(outer, bg=BG)
        heading.pack(fill='x', pady=(0, 18))
        self._label(heading, 'SIGNAL STUDIO  /  TELEMETRY', bg=BG, fg=ACCENT,
                    font=(UI_FONT, 10, 'bold')).pack(side='left')
        ttk.Button(heading, text='Open simulation ZIP / CSV', command=self.open_reference).pack(side='right')
        ttk.Button(heading, text='Load bench data', command=lambda: self.app.tabs.select(self.app.tab_config)).pack(side='right', padx=8)
        self.card = tk.Frame(outer, bg=CARD, highlightbackground=EDGE, highlightthickness=1)
        self.card.pack(fill='both', expand=True)
        header = tk.Frame(self.card, bg=CARD)
        header.pack(fill='x', padx=24, pady=(20, 4))
        self._label(header, 'Washing Machine Telemetry', font=(UI_FONT, 23)).pack(side='left')
        self.badge = self._label(header, 'NO RECORDING', fg=MUTED, bg='#282b30', padx=10, pady=4,
                                font=(UI_MONO, 10, 'bold'))
        self.badge.pack(side='left', padx=16)
        self.source_label = self._label(self.card, 'Open a recording to explore synchronized subsystem tracks.', fg=MUTED,
                                        font=(UI_FONT, 10), anchor='w')
        self.source_label.pack(fill='x', padx=25)
        controls = tk.Frame(self.card, bg=CARD)
        controls.pack(fill='x', padx=24, pady=(16, 12))
        self.view = ttk.Combobox(controls, values=VIEWS, state='readonly', width=57)
        self.view.current(0)
        self.view.pack(side='left')
        self.view.bind('<<ComboboxSelected>>', lambda _e: self.draw())
        self._label(controls, 'VIEW', fg=MUTED, font=(UI_MONO, 9)).pack(side='left', padx=12)
        ttk.Button(controls, text='Save telemetry image', command=self.export_image).pack(side='right')
        self.phase_header = tk.Frame(self.card, bg=CARD)
        self.phase_header.pack(fill='x', padx=24, pady=(0, 5))
        self._label(self.phase_header, 'Cycle Phase Sequence', font=(UI_FONT, 10, 'italic')).pack(side='left')
        self.time_label = self._label(self.phase_header, 'Time: —', font=(UI_MONO, 11, 'italic'))
        self.time_label.pack(side='right')
        self.phase = tk.Canvas(self.card, bg=CARD, height=25, highlightthickness=0)
        self.phase.pack(fill='x', padx=24, pady=(0, 12))
        self.phase.bind('<Configure>', lambda _e: self._draw_phase())
        self.phase.bind('<Button-1>', self._phase_seek)
        chart = tk.Frame(self.card, bg=PLOT, highlightbackground=EDGE, highlightthickness=1)
        chart.pack(fill='both', expand=True, padx=24)
        self.figure = Figure(figsize=(12, 3), facecolor=PLOT, dpi=100)
        self.viewport = tk.Canvas(chart, bg=PLOT, highlightthickness=0, height=260)
        self.chart_scroll = ttk.Scrollbar(chart, orient='vertical', command=self.viewport.yview)
        self.chart_scroll.pack(side='right', fill='y')
        self.viewport.pack(side='left', fill='both', expand=True)
        self.viewport.configure(yscrollcommand=self.chart_scroll.set)
        self.canvas = FigureCanvasTkAgg(self.figure, master=self.viewport)
        self.canvas.get_tk_widget().configure(bg=PLOT, highlightthickness=0)
        self.chart_window = self.viewport.create_window(0,0,window=self.canvas.get_tk_widget(),anchor='nw')
        self.viewport.bind('<Configure>', self._resize_chart)
        self.canvas.get_tk_widget().bind('<Map>', lambda _e: self.after_idle(self._resize_chart), add='+')
        self.canvas.mpl_connect('motion_notify_event', self._hover)
        self.canvas.mpl_connect('button_press_event', self._click)
        self.canvas.mpl_connect('scroll_event', self._scroll)
        self.readout = tk.Frame(self.card, bg=PLOT)
        self.readout.pack(side='bottom', fill='x', padx=24, pady=(12, 18), before=chart)
        player = tk.Frame(outer, bg=BG)
        player.pack(fill='x', pady=(14, 0))
        self.play_button = ttk.Button(player, text='▶  Play', command=self.toggle_play, width=12, style='Accent.TButton')
        self.play_button.pack(side='left')
        ttk.Button(player, text='↺  Start', command=lambda: self.seek(self.start)).pack(side='left', padx=8)
        self.position = tk.DoubleVar(value=0)
        self.seekbar = ttk.Scale(player, variable=self.position, from_=0, to=1, command=self._slider)
        self.seekbar.pack(side='left', fill='x', expand=True, padx=16)
        self.speed = ttk.Combobox(player, values=['1×', '5×', '20×', '60×'], state='readonly', width=5)
        self.speed.set('20×')
        self.speed.pack(side='left')
        self.clock = self._label(player, '— / — min', bg=BG, fg=MUTED, font=(UI_MONO, 10), width=23)
        self.clock.pack(side='left', padx=(14, 0))
        footer = tk.Frame(outer, bg=BG)
        footer.pack(side='bottom', fill='x', pady=(10, 0), before=self.card)
        player.pack_configure(side='bottom', before=self.card)
        self.note = self._label(footer, 'Hover to inspect · Click to seek · Wheel to zoom · Scrollbar for tracks · Double-click to reset', bg=BG,
                                fg=MUTED, font=(UI_FONT, 9), wraplength=650, justify='left')
        self.note.pack(side='left')
        ttk.Button(footer, text='Preview sample', command=self.load_demo).pack(side='right')
        ttk.Button(footer, text='Engineering dashboard', command=lambda: self.app.tabs.select(self.app.tab_dashboard)).pack(side='right', padx=8)
        self.cursor_lines = []
        self.values = {}
        self.axes = []
        self.start, self.end = 0., 1.

    def set_signals(self, signals, source, *, demo=False):
        self.pause()
        self.signals = signals
        self.demo = demo
        times = [s.trace[0] for s in signals if len(s.trace[0])]
        if times:
            self.start = min(float(t[0]) for t in times)
            self.end = max(float(t[-1]) for t in times)
        else:
            self.start, self.end = 0., 1.
        self.when = self.start
        self.seekbar.configure(from_=self.start, to=max(self.end, self.start + 1e-6))
        self.source_label.config(text=f'{len(signals)} signal tracks  ({self.start:g}-{self.end:g} min)  ·  {source}')
        self.badge.config(text='SAMPLE PREVIEW' if demo else ('RECORDING' if signals else 'NO RECORDING'), bg=ACCENT if demo else '#2d3c28', fg='#1b2514' if demo else ACCENT)
        self.note.config(text=('Illustrative sample · Not measured data · ' if demo else '') +
                         'Hover to inspect · Click to seek · Wheel to zoom · Scrollbar for tracks · Double-click to reset')
        self.draw()
        self._draw_phase()
        self.seek(self.start)

    def open_reference(self):
        path = filedialog.askopenfilename(parent=self, title='Open simulation reference',
                   filetypes=[('Simulation ZIP / CSV', '*.zip *.csv'), ('All files', '*.*')])
        if not path:
            return
        try:
            adapter = load_simulation_reference(path, **self.app.comp_csv_settings)
            signals = signals_from_curves(adapter.extract_curves())
        except Exception as exc:
            if 'adapter' in locals():
                adapter.close()
            messagebox.showerror('Cannot open recording', str(exc), parent=self)
            return
        if self._adapter:
            self._adapter.close()
        self._adapter = adapter
        self.set_signals(signals, Path(path).name + ' · Simulation reference · Pressure labels follow reference settings')

    def load_demo(self):
        self.set_signals(demo_signals(), 'Illustrative 186-minute cycle · Not measured data', demo=True)
        self.seek(83.2)

    def draw(self):
        self._drawing = True
        selected = self.view.current()
        self.visible = [s for s in self.signals if selected == 0 or s.group == selected]
        self.figure.clear()
        self.axes, self.cursor_lines, self.values = [], [], {}
        for w in self.readout.winfo_children():
            w.destroy()
        if not self.visible:
            ax = self.figure.add_subplot(111)
            ax.set_facecolor(PLOT)
            ax.axis('off')
            ax.text(.5, .56, 'Your next cycle, in focus.', ha='center', va='center', color=TEXT,
                    fontsize=23, transform=ax.transAxes)
            ax.text(.5, .43, 'Open a simulation ZIP / CSV or render your bench recording.\n'
                    'All original analysis tools remain available in the tabs above.' if not self.signals else
                    'No mapped signals in this subsystem. Choose another view.',
                    ha='center', va='center', color=MUTED, fontsize=11, linespacing=1.8, transform=ax.transAxes)
        else:
            count = len(self.visible)
            for i, signal in enumerate(self.visible):
                ax = self.figure.add_subplot(count, 1, i+1, sharex=self.axes[0] if self.axes else None)
                self.axes.append(ax)
                ax.set_facecolor(PLOT)
                t, y, kind = signal.trace
                display_y = normalized_values(y) if selected == 0 else y
                # Full-resolution traces retain spikes, gaps and transitions.
                ax.plot(t, display_y, color=signal.color, lw=1.35,
                        drawstyle='steps-post' if kind in ('digital', 'lock', 'code', 'stage', 'step') else 'default',
                        marker='o' if len(t) <= 500 else None, markersize=2.3, markevery=max(1, len(t)//65))
                ax.set_ylabel(signal.label, color=TEXT, fontsize=9, rotation=0, ha='right', va='center', labelpad=18)
                ax.tick_params(colors=MUTED, labelsize=8, length=0, pad=6)
                ax.spines[['top','right','left']].set_visible(False)
                ax.spines['bottom'].set_color('#23262b')
                ax.grid(axis='x', color='#2c2f34', linestyle=(0,(2,5)), linewidth=.6)
                if selected == 0:
                    ax.set_ylim(-.15, 1.2)
                    ax.set_yticks([])
                    ax.text(-.025, .90, signal.unit or 'value', color=MUTED, fontsize=7,
                            ha='right', transform=ax.transAxes)
                else:
                    ax.margins(y=.18)
                    ax.text(0, .96, signal.unit or 'value', color=MUTED, fontsize=8, transform=ax.transAxes, va='top')
                ax.tick_params(labelbottom=i == count-1)
                ax.set_xlim(self.start, max(self.end, self.start+1))
                self.cursor_lines.append(ax.axvline(self.when, color='#c9ccd2', ls=(0,(3,3)), lw=1))
                cell = tk.Frame(self.readout, bg=PLOT)
                cell.grid(row=i//5, column=i%5, sticky='ew', padx=12, pady=9)
                self._label(cell, '●  '+signal.label, fg=signal.color, bg=PLOT, font=(UI_FONT, 9), anchor='w').pack(fill='x')
                val = self._label(cell, '—', bg=PLOT, font=(UI_MONO, 11, 'bold'), anchor='w')
                val.pack(fill='x', pady=(3,0))
                self.values[signal.key] = val
            for c in range(min(count,5)):
                self.readout.columnconfigure(c, weight=1, uniform='readout')
            self.axes[-1].xaxis.set_major_formatter(lambda v, _p: f'{v:g}m')
            self.figure.subplots_adjust(left=.16, right=.976, top=.925, bottom=.10, hspace=.2)
            self.cursor_tag = self.axes[0].annotate('', xy=(self.when, 1), xycoords=('data','axes fraction'),
                         xytext=(0,9), textcoords='offset points', ha='center', va='bottom', fontsize=9,
                         color='#121316', bbox=dict(boxstyle='round,pad=.3', fc='#dfe1e6', ec='none'))
        self._drawing = False
        self.viewport.yview_moveto(0)
        self.seek(self.when)
        self._resize_chart()
        self.canvas.draw_idle()

    def _resize_chart(self, _event=None):
        width = max(200, self.viewport.winfo_width())
        height = max(self.viewport.winfo_height(), len(self.visible)*30+45, 180)
        self.viewport.itemconfigure(self.chart_window, width=width, height=height)
        self.viewport.configure(scrollregion=(0,0,width,height))
        if height <= self.viewport.winfo_height() + 1:
            self.chart_scroll.pack_forget()
        elif not self.chart_scroll.winfo_manager():
            self.chart_scroll.pack(side='right', fill='y', before=self.viewport)
        self.figure.set_size_inches(width/self.figure.dpi, height/self.figure.dpi, forward=False)
        self.canvas.draw_idle()

    def _draw_phase(self):
        self.phase.delete('all')
        width = max(1, self.phase.winfo_width())
        if self.demo:
            spans = demo_phases()
        else:
            # Never infer named wash phases from unrelated STWF codes or time fractions.
            spans = recorded_phase_spans(self.signals, self.start, self.end)
        duration = max(self.end-self.start, 1e-9)
        for a,b,label,color in spans:
            x0=(a-self.start)/duration*width; x1=(b-self.start)/duration*width
            self.phase.create_rectangle(x0+1, 2, x1-1, 22, fill=color, outline='')
            if x1-x0 > max(36, len(label)*6):
                self.phase.create_text((x0+x1)/2,12,text=label,fill='#172015' if color != '#32363d' else MUTED,
                                       font=(UI_MONO,9,'bold'))
        self.phase_cursor = self.phase.create_line(0,0,0,25,fill=TEXT,width=2)
        self._update_phase_cursor()

    def _update_phase_cursor(self):
        if hasattr(self, 'phase_cursor'):
            x = (self.when-self.start)/max(self.end-self.start, 1e-9)*self.phase.winfo_width()
            self.phase.coords(self.phase_cursor,x,0,x,25)

    def seek(self, when):
        self.when = float(np.clip(when, self.start, self.end))
        self.position.set(self.when)
        self.time_label.config(text=f'Time: {self.when:.1f} min' if self.signals else 'Time: —')
        self.clock.config(text=f'{self.when:.1f} / {self.end:.1f} min' if self.signals else '— / — min')
        for signal in self.visible:
            value = sample_trace(signal.trace, self.when)
            self.values[signal.key].config(text=format_sample(value, signal.kind, signal.unit))
        for line in self.cursor_lines:
            line.set_xdata([self.when,self.when])
        if self.cursor_lines:
            self.cursor_tag.xy = (self.when, 1)
            self.cursor_tag.set_text(f'{self.when:.1f}m')
        self._update_phase_cursor()
        if self.demo:
            phase = next((label for a,b,label,_c in demo_phases() if a <= self.when < b), 'Complete')
            self.badge.config(text='SAMPLE · ' + phase.upper())
        if not self._drawing:
            self.canvas.draw_idle()

    def _slider(self, value):
        if not self._drawing and abs(float(value) - self.when) > 1e-8:
            self.seek(float(value))

    def _hover(self, event):
        if not self.playing and event.inaxes in self.axes and event.xdata is not None:
            self.seek(event.xdata)

    def _click(self, event):
        if event.inaxes not in self.axes or event.xdata is None:
            return
        if event.dblclick:
            self.axes[0].set_xlim(self.start, max(self.end,self.start+1))
        self.seek(event.xdata)

    def _scroll(self, event):
        if event.inaxes not in self.axes or event.xdata is None:
            return
        a,b=self.axes[0].get_xlim()
        factor=.8 if event.button == 'up' else 1.25
        a=event.xdata+(a-event.xdata)*factor; b=event.xdata+(b-event.xdata)*factor
        a=max(self.start,a); b=min(max(self.end,self.start+1),b)
        if b-a > 1e-6:
            self.axes[0].set_xlim(a,b)
            self.canvas.draw_idle()

    def _phase_seek(self, event):
        self.seek(self.start + event.x/max(1,self.phase.winfo_width())*(self.end-self.start))

    def toggle_play(self):
        if self.playing:
            self.pause()
        elif self.signals:
            if self.when >= self.end:
                self.seek(self.start)
            self.playing = True
            self.play_button.config(text='Ⅱ  Pause')
            self._last_tick = time.monotonic()
            self._tick()

    def _tick(self):
        self._job = None
        if not self.playing:
            return
        now=time.monotonic()
        self.seek(self.when+(now-self._last_tick)*float(self.speed.get().rstrip('×'))/60)
        self._last_tick=now
        if self.when >= self.end:
            self.pause()
        else:
            self._job=self.after(60,self._tick)

    def pause(self):
        self.playing = False
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        if hasattr(self,'play_button'):
            self.play_button.config(text='▶  Play')

    def export_image(self):
        if not self.visible:
            messagebox.showinfo('No chart', 'Open a recording or sample preview first.', parent=self)
            return
        path=filedialog.asksaveasfilename(parent=self, defaultextension='.png',
                    filetypes=[('PNG image','*.png'),('PDF document','*.pdf')])
        if path:
            try:
                self.figure.savefig(path, dpi=180, facecolor=PLOT,
                   metadata={'Title': 'Illustrative sample telemetry' if self.demo else 'Recording telemetry'})
            except Exception as exc:
                messagebox.showerror('Export failed',str(exc),parent=self)

    def _destroy(self, event):
        if event.widget is self:
            self.playing = False
            if self._job is not None:
                self.after_cancel(self._job)
                self._job = None
            if self._adapter:
                self._adapter.close()
            self.figure.clear()

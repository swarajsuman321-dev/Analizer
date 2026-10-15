"""Explicitly synthetic fixtures, loaded directly into the active workspace."""
from dataclasses import dataclass
import numpy as np
from app_inspection import prepare_trace
COLORS = ['#96cdf1','#e4ce80','#a7afe0','#73e999','#80cbea','#cab8ed','#e6e4c9','#e79bcf','#d9d8b8','#b8e67f']
GROUPS={'temperature':1,'heater_power':1,'drum_speed':2,'pressure':3,'water':3,'pre_wash_valve_open':3,'wash_valve_open':3,'drain_open':3,'stwf_number':4,'actual_remaining_time':4}
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

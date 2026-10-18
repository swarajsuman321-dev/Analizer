"""Explicit physical unit conversions; never infer calibration from magnitude."""
import numpy as np
# dimension, multiplier to base, affine offset to base
UNITS={
    '°C':('temperature',1,273.15),'K':('temperature',1,0),'°F':('temperature',5/9,255.3722222222222),
    'Pa':('pressure',1,0),'kPa':('pressure',1000,0),'bar':('pressure',100000,0),'mbar':('pressure',100,0),'mm H₂O':('pressure',9.80665,0),
    'L/s':('flow',1,0),'L/min':('flow',1/60,0),'L':('volume',1,0),'mL':('volume',.001,0),
    'Hz':('frequency',1,0),'kHz':('frequency',1000,0),'RPM':('rotation',1,0),'rps':('rotation',60,0),
    'g':('acceleration',9.80665,0),'m/s²':('acceleration',1,0),'mm':('length',.001,0),'m':('length',1,0),'N·m':('torque',1,0),
    'V':('voltage',1,0),'mV':('voltage',.001,0),'A':('current',1,0),'mA':('current',.001,0),
    'W':('power',1,0),'kW':('power',1000,0),'Wh':('energy',3600,0),'kWh':('energy',3600000,0),'J':('energy',1,0),
    '%':('ratio',.01,0),'':('ratio',1,0),'1':('ratio',1,0),'μS/cm':('conductivity',1,0),
    's':('time',1,0),'ms':('time',.001,0),'us':('time',1e-6,0),'min':('time',60,0),'h':('time',3600,0),
    'count':('count',1,0),'state':('state',1,0),'code':('code',1,0),'°C/min':('heating_rate',1,0),'RPM/s':('acceleration_rotation',1,0),
}
ALIASES={'rpm':'RPM','mmH2O':'mm H₂O','mm H2O':'mm H₂O','µS/cm':'μS/cm','uS/cm':'μS/cm','Nm':'N·m','degC':'°C','µs':'us'}


def unit(value):return ALIASES.get(str(value).strip(),str(value).strip())


def convert(values,source,target):
    source,target=unit(source),unit(target)
    a,b=UNITS.get(source),UNITS.get(target)
    if not a or not b or a[0]!=b[0]:raise ValueError(f'No verified conversion from {source or "unitless"} to {target or "unitless"}')
    return (np.asarray(values,dtype=float)*a[1]+a[2]-b[2])/b[1]


def convert_difference(values,source,target):
    """Affine offsets cancel for standard deviations, deltas and band widths."""
    return convert(values,source,target)-convert(0,source,target)


def seconds(channel):
    if channel.coordinate_kind!='time':raise ValueError('Engineering calculations require a time coordinate')
    return convert(channel.values()[0],channel.coordinate_unit,'s')


def calibrated(values,definition,target):
    """Only explicitly verified, bounded piecewise calibration is applied."""
    if not definition.get('verified') or not definition.get('id'):raise ValueError('A verified calibration identifier is required')
    x=np.asarray(definition.get('x',[]),float);y=np.asarray(definition.get('y',[]),float)
    if len(x)<2 or len(x)!=len(y) or not np.isfinite(x).all() or not np.isfinite(y).all() or np.any(np.diff(x)<=0):raise ValueError('Calibration needs finite increasing X points and paired Y points')
    result=np.interp(values,x,y,left=np.nan,right=np.nan)
    return convert(result,definition['output_unit'],target)

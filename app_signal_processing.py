"""Numerical operations with explicit clock, unit, and missing-data rules."""
import ast
from dataclasses import dataclass
import operator
import numpy as np
from scipy import signal
from app_channel_store import Channel

UNIT_DEFINITIONS = {'W':('power',1), 'kW':('power',1000), 'V':('voltage',1), 'mV':('voltage',.001),
                    'A':('current',1), 'mA':('current',.001), 'Pa':('pressure',1), 'kPa':('pressure',1000),
                    'bar':('pressure',100000), 's':('time',1), 'min':('time',60), 'h':('time',3600),
                    'Hz':('frequency',1), 'kHz':('frequency',1000), 'rpm':('rotation',1), '':('',1)}


def conversion(source, target):
    if source == target:
        return 1
    a, b = UNIT_DEFINITIONS.get(source), UNIT_DEFINITIONS.get(target)
    if not a or not b or a[0] != b[0]:
        raise ValueError(f'Incompatible units: {source} and {target}')
    return a[1]/b[1]


def strict_clock(channel):
    x,y = channel.values()
    if len(x) < 3 or np.any(np.diff(x) <= 0):
        raise ValueError('Explicitly resample onto a strictly increasing uniform clock first')
    d = np.diff(x)
    if not np.allclose(d, np.median(d), rtol=1e-4, atol=1e-9):
        raise ValueError('Explicitly resample onto a uniform clock first')
    if not np.isfinite(y).all():
        raise ValueError('Operation requires finite data; missing or masked spans must remain explicit')
    scale = 60 if channel.coordinate_unit == 'min' else 3600 if channel.coordinate_unit == 'h' else 1
    return x,y,float(np.median(d))*scale


def interval_moments(x,y,kind='analog'):
    """Shared integration kernel for cursor and appliance measurements.

    Gap policies remain with the caller; this kernel preserves the established
    linear-analog / held-discrete definitions and positive finite intervals.
    """
    d=np.diff(x);a,b=y[:-1],y[1:];valid=np.isfinite(a)&np.isfinite(b)&(d>0)
    if kind=='analog':area=d*(a+b)/2;square=d*(a*a+a*b+b*b)/3
    else:area=d*a;square=d*a*a
    return area,square,d,valid


class IntervalSummary:
    """Prefix integrals for span-weighted statistics, with no unknown-gap bridging."""
    def __init__(self, c):
        self.channel = c
        self.x, self.y = c.values()
        area,square,d,self.valid=interval_moments(self.x,self.y,c.kind)
        self.prefix = [np.r_[0,np.cumsum(np.where(self.valid,v,0))] for v in (area,square,d)]
        # Block extrema avoid full-channel scans while dragging cursors.
        self.block = 256
        self.low, self.high = [], []
        for i in range(0,len(self.y),self.block):
            finite = self.y[i:i+self.block]
            finite = finite[np.isfinite(finite)]
            self.low.append(finite.min() if len(finite) else np.nan)
            self.high.append(finite.max() if len(finite) else np.nan)

    def _integrals(self, point):
        x,y = self.x,self.y
        if len(x)<2 or point <= x[0]:
            return np.zeros(3)
        if point >= x[-1]:
            return np.array([p[-1] for p in self.prefix])
        i = int(np.searchsorted(x, point, side='right')-1)
        value = np.array([p[i] for p in self.prefix])
        if self.valid[i]:
            d = point-x[i]
            a = y[i]
            b = self.channel.sample(point) if self.channel.kind == 'analog' else a
            value += [d*(a+b)/2, d*(a*a+a*b+b*b)/3, d]
        return value

    def query(self, a, b):
        a,b = sorted((a,b))
        area,square,coverage = self._integrals(b)-self._integrals(a)
        left = int(np.searchsorted(self.x,a,side='left'))
        right = int(np.searchsorted(self.x,b,side='right'))
        lo = ((left+self.block-1)//self.block)*self.block
        hi = (right//self.block)*self.block
        samples = list(self.y[left:min(lo,right)]) + list(self.y[max(hi,left):right])
        samples += [self.channel.sample(a), self.channel.sample(b)]
        if hi>lo:
            samples += self.low[lo//self.block:hi//self.block] + self.high[lo//self.block:hi//self.block]
        finite = np.array(samples)
        finite = finite[np.isfinite(finite)]
        low,high = (float(finite.min()),float(finite.max())) if len(finite) else (np.nan,np.nan)
        first,last = self.channel.sample(a),self.channel.sample(b)
        seconds = 60 if self.channel.coordinate_unit=='min' else 3600 if self.channel.coordinate_unit=='h' else 1
        delta=b-a
        return {'ΔX':delta,'ΔY':last-first,'Mean':area/coverage if coverage else np.nan,
                'RMS':np.sqrt(max(0,square/coverage)) if coverage else np.nan,'Min':low,'Max':high,
                'Peak-to-Peak':high-low,'Slope':(last-first)/(delta*seconds) if delta else np.nan,
                'Integral':area*seconds,'Coverage':coverage/delta if delta else 0}


@dataclass
class Quantity:
    x: np.ndarray
    y: np.ndarray
    unit: str
    coordinate_unit: str
    coordinate_kind: str
    parents: list
    kind: str = 'analog'


def formula(store, expression, name='Formula'):
    """AST evaluator: no Python evaluation, attributes, indexing, or arbitrary calls."""
    def visit(node):
        if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)):
            return float(node.value)
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.USub,ast.UAdd)):
            value=visit(node.operand)
            factor=-1 if isinstance(node.op,ast.USub) else 1
            if isinstance(value,Quantity):
                return Quantity(value.x,value.y*factor,value.unit,value.coordinate_unit,value.coordinate_kind,value.parents,value.kind)
            return factor*value
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name):
            args=node.args
            if node.keywords:
                raise ValueError('Formula keyword arguments are unsupported')
            if node.func.id=='Ch' and len(args)==1 and isinstance(args[0],ast.Constant) and isinstance(args[0].value,str):
                key=args[0].value
                matches=[c for c in store.channels.values() if c.id==key or c.name==key]
                if len(matches)!=1:
                    raise ValueError(f'Channel {key!r} must resolve uniquely')
                c=matches[0];x,y=c.values()
                return Quantity(x,y,c.unit,c.coordinate_unit,c.coordinate_kind,[c.id],c.kind)
            if node.func.id=='convert' and len(args)==2 and isinstance(args[1],ast.Constant) and isinstance(args[1].value,str):
                value=visit(args[0]);target=args[1].value
                if not isinstance(value,Quantity):
                    raise ValueError('convert requires a channel expression')
                return Quantity(value.x,value.y*conversion(value.unit,target),target,value.coordinate_unit,value.coordinate_kind,value.parents,value.kind)
        if isinstance(node,ast.BinOp) and isinstance(node.op,(ast.Add,ast.Sub,ast.Mult,ast.Div)):
            a,b=visit(node.left),visit(node.right)
            op={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv}[type(node.op)]
            qa,qb=isinstance(a,Quantity),isinstance(b,Quantity)
            if not qa and not qb:
                return op(a,b)
            base=a if qa else b
            unit=base.unit
            if qa and qb:
                if a.coordinate_kind!=b.coordinate_kind or a.coordinate_unit!=b.coordinate_unit or not np.array_equal(a.x,b.x):
                    raise ValueError('Channel clocks differ; explicitly resample before combining them')
                if isinstance(node.op,(ast.Add,ast.Sub)):
                    av,bv=a.y,b.y*conversion(b.unit,a.unit)
                else:
                    av,bv=a.y,b.y
                    unit = '*'.join(filter(None,[a.unit,b.unit])) if isinstance(node.op,ast.Mult) else ('' if a.unit==b.unit else f'{a.unit}/{b.unit}')
            else:
                av,bv=a.y if qa else a,b.y if qb else b
                if isinstance(node.op,ast.Div) and qb:
                    unit=f'1/{unit}' if unit else ''
            with np.errstate(all='ignore'):
                y=op(av,bv)
            parents=list(dict.fromkeys((a.parents if qa else [])+(b.parents if qb else [])))
            return Quantity(base.x,y,unit,base.coordinate_unit,base.coordinate_kind,parents,base.kind)
        raise ValueError('Unsupported formula; use Ch("name"), convert, numbers, and + - * /')
    value=visit(ast.parse(expression,mode='eval').body)
    if not isinstance(value,Quantity):
        raise ValueError('Formula must reference at least one channel')
    parent=store.channels[value.parents[0]]
    return Channel(name,value.x,value.y,unit=value.unit,coordinate_unit=value.coordinate_unit,
                   coordinate_kind=value.coordinate_kind,kind=value.kind,dataset_id=parent.dataset_id,group='Derived',
                   parents=value.parents,recipe={'operation':'formula','expression':expression})


def transform(c, operation, **p):
    x,y=c.values();unit=c.unit;cu=c.coordinate_unit;ck=c.coordinate_kind;kind=c.kind
    def parameter(name, default):
        return float(p.get(name,default))
    if operation=='Offset and scale':
        y=y*parameter('scale',1)+parameter('offset',0)
    elif operation=='Time shift':
        x=x+parameter('shift',0)
    elif operation=='Resampling':
        step=parameter('step',1)
        if step<=0 or not len(x):
            raise ValueError('Resampling step must be positive, with nonempty source data')
        count=int(np.floor((x[-1]-x[0])/step))+1
        if count>5_000_000:
            raise ValueError('Resampling would exceed five million points')
        newx=x[0]+np.arange(count)*step
        # Last duplicate wins, while source data remains unchanged.
        last=np.r_[np.diff(x)!=0,True]
        ux,uy=x[last],y[last]
        pos=np.searchsorted(ux,newx,side='right')-1
        valid=(pos>=0)&(pos<len(ux))
        newy=np.full(len(newx),np.nan)
        if kind=='analog':
            newy=np.interp(newx,ux,uy,left=np.nan,right=np.nan)
            # np.interp retains unknown spans between nonfinite support.
        else:
            newy[valid]=uy[pos[valid]]
        x,y=newx,newy
    elif operation=='Cumulative integration':
        out=np.full(len(y),np.nan);acc=0.;pending_gap=False
        seconds=60 if cu=='min' else 3600 if cu=='h' else 1
        for i in range(len(y)):
            if i:
                d=(x[i]-x[i-1])*seconds
                supported=np.isfinite(y[i]) and np.isfinite(y[i-1])
                if d>0 and not supported:pending_gap=True
                if np.isfinite(y[i]):
                    if pending_gap:acc=0.;pending_gap=False
                    elif d>0 and supported:acc+=d*((y[i]+y[i-1])/2 if kind=='analog' else y[i-1])
            if np.isfinite(y[i]):out[i]=acc
        y=out;unit=f'{unit}·'+('s' if ck=='time' else cu)
    elif operation=='Histogram':
        y,edges=np.histogram(y[np.isfinite(y)],bins=int(parameter('bins',30)))
        x=(edges[:-1]+edges[1:])/2;cu=unit;unit='count';ck='histogram';kind='discrete'
    elif operation=='Descriptive statistics':
        finite=y[np.isfinite(y)]
        if not len(finite):
            raise ValueError('No finite samples')
        y=np.array([finite.mean(),np.sqrt(np.mean(finite**2)),finite.min(),finite.max(),np.ptp(finite),finite.std(),len(finite)])
        x=np.arange(len(y));cu='metric';ck='statistics';kind='discrete'
    else:
        x,y,dt=strict_clock(c)
        window=int(parameter('window',11))
        if operation=='Moving average':
            if window<1 or window>len(y):
                raise ValueError('Window must fit the data')
            y=np.convolve(y,np.ones(window)/window,mode='same')
            y[:window//2]=np.nan;y[len(y)-(window-1)//2:]=np.nan
        elif operation=='Savitzky–Golay':
            y=signal.savgol_filter(y,window,int(parameter('order',2)))
        elif operation=='Butterworth low-pass':
            cutoff=parameter('cutoff',1)
            sos=signal.butter(int(parameter('order',4)),cutoff,fs=1/dt,output='sos')
            y=signal.sosfiltfilt(sos,y)
        elif operation=='Differentiation':
            y=np.gradient(y,dt);unit=f'{unit}/'+('s' if ck=='time' else cu)
        elif operation in ('FFT','Welch PSD'):
            if ck!='time':
                raise ValueError('Frequency analysis requires temporal coordinates')
            if operation=='FFT':
                y=np.abs(np.fft.rfft(y-y.mean()))*2/len(y)
                x=np.fft.rfftfreq(len(c.y),dt)
            else:
                x,y=signal.welch(y,fs=1/dt,nperseg=min(256,len(y)))
                unit=f'{unit}²/Hz'
            cu='Hz';ck='frequency';kind='analog'
        elif operation=='Peak and valley detection':
            peaks,_=signal.find_peaks(y,prominence=parameter('prominence',0))
            valleys,_=signal.find_peaks(-y,prominence=parameter('prominence',0))
            indices=np.sort(np.r_[peaks,valleys]);x,y=x[indices],y[indices];kind='discrete'
        else:
            raise ValueError(f'Unknown operation {operation}')
    attrs={}
    if operation=='Descriptive statistics':
        attrs={'metric_labels':['Mean','RMS','Min','Max','Peak-to-Peak','Standard deviation','Count'],
               'metric_units':[c.unit]*6+['count']}
        unit='mixed'
    return Channel(f'{c.name} · {operation}',x,y,unit=unit,kind=kind,coordinate_unit=cu,coordinate_kind=ck,
                   dataset_id=c.dataset_id,group='Derived',parents=[c.id],attributes=attrs,
                   recipe={'operation':operation,'parameters':p})

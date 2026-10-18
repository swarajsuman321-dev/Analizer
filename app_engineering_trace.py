"""Gap-aware analysis projections. Source timestamps and measurements stay immutable."""
import numpy as np
from app_engineering_units import seconds,convert,calibrated


class Trace:
    def __init__(self,channel,target=None,calibration=None,max_gap_seconds=None,offset=0,source_unit=None):
        self.channel=channel;self.kind=channel.kind;self._stats_cache={}
        t=seconds(channel)+offset;y=channel.values()[1]
        # Last duplicate is the established cursor convention. Original arrays are untouched.
        keep=np.r_[np.diff(t)>0,True] if len(t) else np.array([],bool)
        self.raw_t=t;self.raw_y=y;self.unit=target or source_unit or channel.unit;source_unit=source_unit if source_unit is not None else channel.unit
        if calibration:
            if not calibration.get('input_unit'):raise ValueError('Calibration must declare its input unit')
            self.raw_y=calibrated(convert(y,source_unit,calibration['input_unit']),calibration,self.unit)
        elif target:self.raw_y=convert(y,source_unit,target)
        self.t=t[keep];self.y=self.raw_y[keep];self.duplicates=int(len(t)-len(self.t))
        d=np.diff(self.t);positive=d[d>0]
        self.max_gap=float(max_gap_seconds) if max_gap_seconds is not None else (3*float(np.median(positive)) if len(positive) else 0)
        if not np.isfinite(self.max_gap) or self.max_gap<0:raise ValueError('Gap limit must be finite and nonnegative')

    def to_unit(self,target):
        if target==self.unit:return self
        if not hasattr(self,'_unit_views'):self._unit_views={}
        if target in self._unit_views:return self._unit_views[target]
        import copy
        converted=copy.copy(self);converted.y=convert(self.y,self.unit,target);converted.raw_y=convert(self.raw_y,self.unit,target);converted.unit=target;converted._stats_cache={};converted._unit_views={}
        self._unit_views[target]=converted
        return converted

    def sample(self,points):
        points=np.asarray(points,float);out=np.full(points.shape,np.nan)
        if not len(self.t):return out
        i=np.searchsorted(self.t,points,side='right')-1;safe=np.clip(i,0,len(self.t)-1)
        exact=(i>=0)&(points==self.t[safe]);out[exact]=self.y[safe[exact]]
        inner=(i>=0)&(i<len(self.t)-1)&~exact
        where=np.flatnonzero(inner);j=safe[inner]
        valid=(self.t[j+1]-self.t[j]<=self.max_gap)&np.isfinite(self.y[j])&np.isfinite(self.y[j+1])
        where=where[valid];j=j[valid]
        if self.kind=='analog':out[where]=self.y[j]+(self.y[j+1]-self.y[j])*(points[where]-self.t[j])/(self.t[j+1]-self.t[j])
        else:out[where]=self.y[j]
        return out

    def coverage_at(self,points):
        """Cumulative supported seconds, used to validate every stall window."""
        points=np.asarray(points,float)
        if len(self.t)<2:return np.zeros(points.shape)
        d=np.diff(self.t);valid=np.isfinite(self.y[:-1])&np.isfinite(self.y[1:])&(d>0)&(d<=self.max_gap)
        prefix=np.r_[0,np.cumsum(np.where(valid,d,0))]
        indices=np.searchsorted(self.t,points,side='right')-1;safe=np.clip(indices,0,len(self.t)-1)
        extra=np.maximum(0,points-self.t[safe]);eligible=(indices>=0)&(indices<len(self.t)-1)
        allowed=np.r_[valid,False][safe]&eligible
        result=prefix[safe]+np.where(allowed,extra,0);result=np.where(indices<0,0,result)
        return result

    def window(self,start=None,end=None):
        if not len(self.t):return np.array([]),np.array([])
        a=self.t[0] if start is None else max(float(start),self.t[0]);b=self.t[-1] if end is None else min(float(end),self.t[-1])
        if b<a:return np.array([]),np.array([])
        left=np.searchsorted(self.t,a,side='left');right=np.searchsorted(self.t,b,side='right')
        t=np.unique(np.r_[a,self.t[left:right],b]);return t,self.sample(t)

    def recorded_window(self,start=None,end=None):
        a=self.raw_t[0] if start is None and len(self.raw_t) else start
        b=self.raw_t[-1] if end is None and len(self.raw_t) else end
        if a is None or b is None:return np.array([])
        return self.raw_y[np.searchsorted(self.raw_t,a,side='left'):np.searchsorted(self.raw_t,b,side='right')]

    def stats(self,start=None,end=None):
        key=(start,end)
        if key in self._stats_cache:return self._stats_cache[key]
        t,y=self.window(start,end)
        if not len(t):return {'coverage':0.,'duration_s':0.,'samples':0}
        from app_signal_processing import interval_moments
        area,square,d,valid=interval_moments(t,y,self.kind);valid&=d<=self.max_gap
        covered=float(d[valid].sum());duration=float(t[-1]-t[0]);left=np.searchsorted(self.raw_t,t[0],side='left');right=np.searchsorted(self.raw_t,t[-1],side='right')
        readings=np.r_[y,self.raw_y[left:right]];finite=readings[np.isfinite(readings)];timed=y[np.isfinite(y)]
        integral=float(area[valid].sum());square=float(square[valid].sum());mean=integral/covered if covered else np.nan
        centered_square=interval_moments(t,y-mean,self.kind)[1]
        variance=float(centered_square[valid].sum())/covered if covered else np.nan
        result={'coverage':covered/duration if duration else 0.,'duration_s':duration,'known_s':covered,'samples':len(finite),'integral':integral if covered else np.nan,'mean':mean,'rms':np.sqrt(max(0,square/covered)) if covered else np.nan,'std':np.sqrt(max(0,variance)) if covered else np.nan}
        if len(finite):result.update(min=float(finite.min()),max=float(finite.max()),absmax=float(np.abs(finite).max()))
        if len(timed):result.update(first=float(timed[0]),last=float(timed[-1]))
        self._stats_cache[key]=result
        return result

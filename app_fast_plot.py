"""Cached min/max envelope pyramid and binary-search viewport selection."""
import numpy as np


class EnvelopeCache:
    def __init__(self, x, y):
        self.x,self.y=x,y
        self.levels={1:(x,y)}
        step=4
        while len(x)//step>32:
            self.levels[step]=self._envelope(x,y,step)
            step*=4

    @staticmethod
    def _envelope(x,y,step):
        count=len(y)//step
        values=y[:count*step].reshape(count,step)
        finite=np.isfinite(values)
        low=np.argmin(np.where(finite,values,np.inf),axis=1)
        high=np.argmax(np.where(finite,values,-np.inf),axis=1)
        offsets=np.arange(count)*step
        pairs=np.sort(np.stack([offsets+low,offsets+high],axis=1),axis=1).ravel()
        outx=x[pairs].reshape(count,2)
        outy=y[pairs].reshape(count,2).copy()
        outy[~finite.all(axis=1)]=np.nan  # Never hide a missing span during reduction.
        return np.r_[outx.ravel(),x[count*step:]],np.r_[outy.ravel(),y[count*step:]]

    def visible(self, left, right, budget=2000):
        a,b=np.searchsorted(self.x,[left,right])
        count=max(0,b-a)
        step=1
        for candidate in self.levels:
            if count/candidate*2<=budget:
                step=candidate;break
            step=candidate
        x,y=self.levels[step]
        a=max(0,np.searchsorted(x,left)-2);b=min(len(x),np.searchsorted(x,right)+2)
        return x[a:b],y[a:b]

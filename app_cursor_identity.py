"""Source-sample cursor identity shared by plots, readouts and reports.

A timestamp is not a sample identifier: imported clocks can contain several
observations at the same instant. A lock therefore always retains the channel
ID and original row index. No observation is removed to resolve a duplicate.
"""
import numpy as np
from app_presentation import cursor_sample


def nearest_index(x, point, preferred=None):
    """Choose a real row, preserving an explicitly selected duplicate row."""
    if not len(x):
        return None
    if preferred is not None:
        preferred = int(np.clip(preferred, 0, len(x)-1))
        if x[preferred] == point:
            return preferred
    right = min(len(x)-1, int(np.searchsorted(x, point, side='left')))
    left = max(0, right-1)
    chosen = left if abs(x[left]-point) <= abs(x[right]-point) else right
    # An unlocked timestamp follows Channel.sample's established last-row
    # policy; explicit locks/keyboard steps override it using ``preferred``.
    return int(np.searchsorted(x, x[chosen], side='right')-1)


def locked_index(channel, lock):
    if not lock or lock.get('channel') != channel.id or not len(channel.x):
        return None
    try:
        return int(np.clip(int(lock['index']), 0, len(channel.x)-1))
    except (KeyError, ValueError, TypeError, OverflowError):
        return None


def cursor_value(channel, point, snap=True, lock=None):
    """Return the exact effective locked reading, including masks and NaN."""
    index = locked_index(channel, lock)
    if index is not None:
        return float(channel.values()[1][index])
    return cursor_sample(channel, point, snap)


def interval_rows(channel, a, b, locks=()):
    """Select source rows in the interval, respecting locked duplicate ends.

    With both endpoints at one timestamp, index order defines the interval.
    Interior duplicate observations remain intact. Other channels use their
    own clocks and the common numerical time interval.
    """
    x = channel.values()[0]
    low, high = sorted((a, b))
    left = int(np.searchsorted(x, low, side='left'))
    right = int(np.searchsorted(x, high, side='right'))
    indices = [locked_index(channel, lock) for lock in list(locks)[:2]]
    while len(indices) < 2:
        indices.append(None)
    if a == b and all(i is not None for i in indices):
        left, right = min(indices), max(indices)+1
    else:
        first, last = indices if a <= b else indices[::-1]
        if first is not None and x[first] == low:
            left = first
        if last is not None and x[last] == high:
            right = last+1
    mask = np.zeros(len(x), dtype=bool)
    mask[left:right] = True
    return mask


def interval_statistics(channel, summary, a, b, locks=(), snap=True):
    """Keep interval endpoints and duplicate extrema consistent with locks.

    Prefix integrals still use supported time; zero-duration duplicate rows do
    not invent elapsed time. Extrema only include the source rows between the
    selected duplicate endpoints. Block extrema keep cursor scrubbing bounded.
    """
    locks=list(locks)
    locks=(locks+[None,None])[:2]
    result=summary.query(a,b)
    va=cursor_value(channel,a,snap,locks[0]);vb=cursor_value(channel,b,snap,locks[1])
    result.update(A=va,B=vb,**{'ΔY':vb-va})
    indices=[locked_index(channel,lock) for lock in locks]
    if any(index is not None for index in indices):
        x,y=channel.values();low,high=sorted((a,b))
        left=int(np.searchsorted(x,low,side='left'));right=int(np.searchsorted(x,high,side='right'))
        first,last=indices if a<=b else indices[::-1]
        if a==b and all(index is not None for index in indices):left,right=min(indices),max(indices)+1
        else:
            if first is not None and x[first]==low:left=first
            if last is not None and x[last]==high:right=last+1
        lo=((left+summary.block-1)//summary.block)*summary.block
        hi=(right//summary.block)*summary.block
        samples=list(y[left:min(lo,right)])+list(y[max(hi,left):right])+[va,vb]
        if hi>lo:samples+=summary.low[lo//summary.block:hi//summary.block]+summary.high[lo//summary.block:hi//summary.block]
        finite=np.asarray(samples);finite=finite[np.isfinite(finite)]
        minimum,maximum=(float(finite.min()),float(finite.max())) if len(finite) else (np.nan,np.nan)
        result.update(Min=minimum,Max=maximum,**{'Peak-to-Peak':maximum-minimum})
        scale={'min':60.,'h':3600.}.get(channel.coordinate_unit,1.)
        result['Slope']=(vb-va)/(abs(b-a)*scale) if a!=b else np.nan
    return result

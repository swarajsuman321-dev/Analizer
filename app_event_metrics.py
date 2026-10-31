"""Generic, evidence-safe event metrics for sampled binary actuator channels.

No appliance or channel names are assumed. Times are seconds, values are
confirmed states (0/1); None denotes unknown. Intervals are [start, end).
Only adjacent known samples with a supported time delta establish occupancy.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from math import isfinite
from typing import Sequence


@dataclass(frozen=True)
class Episode:
    start_s: float
    end_s: float
    left_censored: bool
    right_censored: bool


def _state(value):
    if value is None:
        return None
    if isinstance(value, bool) or value in (0, 1):
        return int(value)
    raise ValueError('Expected confirmed 0/1 states or None; no threshold inference')


def _prepare(times: Sequence[float], states: Sequence[int | None], max_gap_s: float):
    if len(times) != len(states):
        raise ValueError('Time/state lengths differ')
    if not isfinite(max_gap_s) or max_gap_s <= 0:
        raise ValueError('max_gap_s must be positive and finite')
    pairs = []
    for t, value in zip(times, states):
        t = float(t)
        if not isfinite(t):
            raise ValueError('Nonfinite timestamp')
        if pairs and t <= pairs[-1][0]:
            raise ValueError('Timestamps must strictly increase; resolve duplicates upstream')
        pairs.append((t, _state(value)))
    return pairs


def analyse_binary(times, states, *, max_gap_s):
    """Calculate known ON/OFF occupancy and observed transition edges.

    A new ON block after a gap is left-censored, not an observed ON edge.
    End-of-recording active blocks are right-censored. No event time is
    interpolated: transition times are first observed new-state timestamps.
    """
    rows = _prepare(times, states, max_gap_s)
    known_s = on_s = off_s = 0.0
    starts = stops = 0
    events = []
    episodes = []
    current_start = None
    left_censored = False
    for i in range(len(rows)-1):
        a, prev = rows[i]
        b, nxt = rows[i+1]
        supported = b-a <= max_gap_s and prev is not None and nxt is not None
        if not supported:
            if current_start is not None:
                episodes.append(Episode(current_start, a, left_censored, True))
                current_start = None
            continue
        known_s += b-a
        if prev == 1:
            on_s += b-a
            if current_start is None:
                current_start, left_censored = a, True
        else:
            off_s += b-a
        if prev == 0 and nxt == 1:
            starts += 1
            events.append({'event':'ON','time_s':b,'bracket_s':[a,b]})
            current_start, left_censored = b, False
        elif prev == 1 and nxt == 0:
            stops += 1
            events.append({'event':'OFF','time_s':b,'bracket_s':[a,b]})
            if current_start is not None:
                episodes.append(Episode(current_start,b,left_censored,False))
            current_start = None
    if current_start is not None:
        episodes.append(Episode(current_start,rows[-1][0],left_censored,True))
    return {'known_duration_s':known_s, 'on_duration_s':on_s,
            'off_duration_s':off_s,'duty_fraction':on_s/known_s if known_s else None,
            'observed_on_edges':starts,'observed_off_edges':stops,
            'episodes':[asdict(e) for e in episodes], 'events':events,
            'limitations':['No states inferred across gaps or unknown samples',
                           'Edges reported at first observed new state; bracket retained']}


def simultaneous_on(times_a, states_a, times_b, states_b, *, max_gap_s, max_gap_b_s=None):
    """Compute overlap only on intervals supported by both held-state clocks."""
    a = _prepare(times_a,states_a,max_gap_s)
    max_gap_b_s=max_gap_s if max_gap_b_s is None else max_gap_b_s
    b = _prepare(times_b,states_b,max_gap_b_s)
    if len(a)<2 or len(b)<2:
        return {'common_known_s':0.,'simultaneous_on_s':0.,'fraction':None}
    knots = sorted(set(t for t,_ in a) | set(t for t,_ in b))
    from bisect import bisect_right
    overlap = known = 0.0
    ta,sa=zip(*a);tb,sb=zip(*b)
    for left,right in zip(knots,knots[1:]):
        ia=bisect_right(ta,left)-1;ib=bisect_right(tb,left)-1
        if ia<0 or ib<0 or ia+1>=len(a) or ib+1>=len(b):
            continue
        if right>ta[ia+1] or right>tb[ib+1]:
            continue
        if ta[ia+1]-ta[ia]>max_gap_s or tb[ib+1]-tb[ib]>max_gap_b_s:
            continue
        if None in (sa[ia],sa[ia+1],sb[ib],sb[ib+1]):
            continue
        known+=right-left
        if sa[ia]==1 and sb[ib]==1:
            overlap+=right-left
    return {'common_known_s':known,'simultaneous_on_s':overlap,
            'fraction':overlap/known if known else None}

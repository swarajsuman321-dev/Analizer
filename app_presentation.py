"""Shared visual semantics for the interactive workbench and exported reports."""
import numpy as np

CURSOR_COLORS = ('#00D2FF', '#FF9F1C')
MATCH_COLORS = ('#22a06b', '#e5a000', '#dc4545')


def match_color(value):
    """Only a finite percentage in [0, 100] receives a match accent."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(value) or not 0 <= value <= 100:
        return None
    return MATCH_COLORS[0 if value >= 90 else 1 if value >= 70 else 2]


def cursor_sample(channel, point, snap=True):
    if not snap or not len(channel.x):
        return channel.sample(point)
    x, y = channel.values()
    if point < x[0] or point > x[-1]:
        return float('nan')
    i = min(len(x)-1, int(np.searchsorted(x, point)))
    if i and point-x[i-1] < x[i]-point:
        i -= 1
    # Retain the established last-duplicate policy and masked/missing values.
    return channel.sample(float(x[i]))

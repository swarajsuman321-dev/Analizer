"""Widget-independent, observable channel domain model."""
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from uuid import uuid4
import numpy as np
import pandas as pd


def identity():
    return uuid4().hex


def immutable(values):
    result = np.array(values, dtype=float, copy=True)
    result.setflags(write=False)
    return result


@dataclass
class Channel:
    name: str
    x: np.ndarray
    y: np.ndarray
    unit: str = ''
    kind: str = 'analog'
    coordinate_unit: str = 's'
    coordinate_kind: str = 'time'
    dataset_id: str = ''
    group: str = 'Channels'
    id: str = field(default_factory=identity)
    attributes: dict = field(default_factory=dict)
    source: str = ''
    parents: list = field(default_factory=list)
    recipe: dict = field(default_factory=dict)
    revision: int = 0
    shift: float = 0
    masks: list = field(default_factory=list)
    raw_y: np.ndarray | None = None

    def __post_init__(self):
        self.x, self.y = immutable(self.x), immutable(self.y)
        if self.raw_y is not None:
            self.raw_y=immutable(self.raw_y)
            if self.raw_y.shape!=self.y.shape:raise ValueError('Original readings must match the channel samples')
        if self.coordinate_unit.lower()=='hz':self.coordinate_unit='Hz'
        if not np.isfinite(self.shift):raise ValueError('Shift must be finite')
        if any(not np.isfinite([a,b]).all() for a,b in self.masks):raise ValueError('Masks must have finite bounds')
        if self.x.ndim != 1 or self.x.shape != self.y.shape:
            raise ValueError('Channel coordinates and values must be equal one-dimensional arrays')
        if not np.isfinite(self.x).all() or np.any(np.diff(self.x) < 0):
            raise ValueError('Coordinates must be finite and nondecreasing; explicitly sort source projections')

    def values(self):
        if hasattr(self, '_effective'):
            return self._effective
        x = self.x + self.shift
        y = self.y.copy()
        for a, b in self.masks:
            y[(x >= min(a,b)) & (x <= max(a,b))] = np.nan
        x.setflags(write=False); y.setflags(write=False)
        self._effective = (x, y)
        return x, y

    def sample(self, point):
        if any(min(a,b) <= point <= max(a,b) for a,b in self.masks):
            return float('nan')
        x, y = self.values()
        i = np.searchsorted(x, point, side='right') - 1
        if i < 0 or i >= len(x) or point > x[-1]:
            return float('nan')
        if x[i] == point or self.kind != 'analog':
            return float(y[i])
        if i+1 >= len(x) or not np.isfinite(y[i:i+2]).all():
            return float('nan')
        return float(y[i] + (y[i+1]-y[i]) * (point-x[i])/(x[i+1]-x[i]))


@dataclass
class Dataset:
    name: str
    frame: pd.DataFrame
    source: str = ''
    id: str = field(default_factory=identity)


class ChannelStore:
    def __init__(self):
        self.datasets = {}
        self.channels = {}
        self.listeners = []
        self._depth = 0
        self._pending = set()

    def observe(self, callback):
        self.listeners.append(callback)

    def changed(self, *ids):
        self._pending.update(ids)
        if not self._depth:
            pending, self._pending = self._pending, set()
            for callback in tuple(self.listeners):
                callback(pending)

    @contextmanager
    def batch(self):
        self._depth += 1
        try:
            yield
        finally:
            self._depth -= 1
            if not self._depth:
                self.changed()

    def add(self, channel):
        if channel.id in self.channels:
            raise ValueError('Duplicate channel identity')
        self.channels[channel.id] = channel
        self.changed(channel.id)
        return channel

    def update(self, id, **changes):
        current = self.channels[id]
        channel = replace(current, **changes, revision=current.revision+1)
        self.channels[id] = channel
        self.changed(id)
        return channel

    def delete(self, ids):
        with self.batch():
            for id in ids:
                self.channels.pop(id, None)
                self.changed(id)

    def duplicate(self, id):
        c = self.channels[id]
        return self.add(replace(c, id=identity(), name=c.name+' copy', attributes=dict(c.attributes), masks=list(c.masks), parents=[c.id]))

    def derived(self, parent, name, x, y, **metadata):
        c = self.channels[parent]
        return self.add(Channel(name, x, y, dataset_id=c.dataset_id, group='Derived', parents=[parent], **metadata))

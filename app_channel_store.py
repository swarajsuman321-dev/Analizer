"""Widget-independent, observable channel domain model."""
from contextlib import contextmanager
from copy import copy, deepcopy
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


@dataclass
class RemovalSnapshot:
    """Recoverable removal state; immutable numerical samples are shared safely.

    Mutable metadata and source tables are copied so later changes cannot alter
    the saved version.  UI owners separately capture bindings and cursor locks.
    """
    datasets: dict
    channels: dict
    dataset_order: tuple
    channel_order: tuple
    requested_dataset_ids: frozenset
    dependent_ids: frozenset

    @property
    def channel_ids(self):
        return frozenset(self.channels)


class ChannelStore:
    def __init__(self):
        self.datasets = {}
        self.channels = {}
        self.listeners = []
        self._depth = 0
        self._pending = set()

    def observe(self, callback):
        # Undo can restore views onto the same store.  Registering an existing
        # bound callback again would repeat every plot rebuild thereafter.
        if callback not in self.listeners:
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

    def removal_plan(self, dataset_ids, clear_all=False):
        """Preview the complete transitive dependency closure without mutation."""
        dataset_ids=set(dataset_ids)
        direct={c.id for c in self.channels.values() if c.dataset_id in dataset_ids}
        removed=set(self.channels) if clear_all else set(direct)
        while True:
            dependent={c.id for c in self.channels.values() if removed.intersection(c.parents)}
            if dependent<=removed:break
            removed.update(dependent)
        return {'dataset_ids':set(self.datasets) if clear_all else dataset_ids & self.datasets.keys(),
                'channel_ids':removed,
                # Most derived channels live in the source's own dataset. They
                # still need to appear in the removal preview, not just cross-
                # recording descendants discovered by the closure above.
                'dependent_ids':{id for id in removed if self.channels[id].parents}}

    def removal_snapshot(self, dataset_ids, clear_all=False):
        """Capture an exact undo version before removing source or derived data."""
        plan=self.removal_plan(dataset_ids,clear_all)
        datasets={}
        for id in plan['dataset_ids']:
            dataset=copy(self.datasets[id]);dataset.frame=dataset.frame.copy(deep=True)
            dataset.frame.attrs=deepcopy(dataset.frame.attrs);datasets[id]=dataset
        channels={}
        for id in plan['channel_ids']:
            channel=copy(self.channels[id])
            for key in ('attributes','parents','recipe','masks'):
                setattr(channel,key,deepcopy(getattr(channel,key)))
            channels[id]=channel
        return RemovalSnapshot(datasets,channels,tuple(self.datasets),tuple(self.channels),
                               frozenset(plan['dataset_ids']),frozenset(plan['dependent_ids']))

    def restore_removal(self, snapshot):
        """Restore stable identities without overwriting work created after removal.

        A collision is rejected atomically.  Original ordering is recovered for
        restored entries while subsequently added entries keep their order.
        """
        if set(snapshot.datasets) & self.datasets.keys() or set(snapshot.channels) & self.channels.keys():
            raise ValueError('Cannot undo removal because a saved identity is already in use')
        missing_parents={parent for channel in snapshot.channels.values() for parent in channel.parents
                         if parent not in self.channels and parent not in snapshot.channels}
        if missing_parents:
            raise ValueError('Cannot undo removal because a required parent channel is no longer available')
        with self.batch():
            self.datasets.update(snapshot.datasets);self.channels.update(snapshot.channels)
            self.datasets={id:self.datasets[id] for id in dict.fromkeys((*snapshot.dataset_order,*self.datasets)) if id in self.datasets}
            self.channels={id:self.channels[id] for id in dict.fromkeys((*snapshot.channel_order,*self.channels)) if id in self.channels}
            self.changed(*snapshot.channels)
        return set(snapshot.channels)

    def remove_datasets(self, dataset_ids):
        """Drop complete recordings and dependent derived traces, in one notification."""
        plan=self.removal_plan(dataset_ids)
        with self.batch():
            for id in plan['dataset_ids']:self.datasets.pop(id,None)
            self.delete(plan['channel_ids'])
        return plan['channel_ids']

    def duplicate(self, id):
        c = self.channels[id]
        return self.add(replace(c, id=identity(), name=c.name+' copy', attributes=dict(c.attributes), masks=list(c.masks), parents=[c.id]))

    def derived(self, parent, name, x, y, **metadata):
        c = self.channels[parent]
        return self.add(Channel(name, x, y, dataset_id=c.dataset_id, group='Derived', parents=[parent], **metadata))

"""Cooperative cancellation and progress for domain work, without Qt dependencies.

The GUI installs one context per worker thread. Numerical/file readers remain
usable from scripts and tests, where checkpoints are intentionally inexpensive
no-ops. Cancellation is observed at safe boundaries, never during a commit.
"""
from contextlib import contextmanager
import threading

_local = threading.local()


@contextmanager
def operation_context(cancel, progress):
    previous = getattr(_local, 'context', None)
    state = {'cancel': cancel, 'progress': progress, 'committed': False}
    _local.context = state
    try:
        yield state
    finally:
        _local.context = previous


def checkpoint(stage=None, current=None, total=None):
    context = getattr(_local, 'context', None)
    if context is None:
        return
    cancel, progress = context['cancel'], context['progress']
    if cancel.is_set():
        raise InterruptedError('Operation cancelled; the previous workspace and completed files were kept.')
    if stage is not None:
        percent = -1 if not total or current is None else min(100, max(0, round(100 * current / total)))
        progress(str(stage), percent)


def cancellation_requested():
    context = getattr(_local, 'context', None)
    return bool(context is not None and context['cancel'].is_set())


def mark_committed():
    """Record that an atomic output commit already completed successfully."""
    context = getattr(_local, 'context', None)
    if context is not None:
        context['committed'] = True

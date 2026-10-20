"""Commit a single exported artifact only after its writer finishes safely."""
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
from app_operation_context import checkpoint,mark_committed


@contextmanager
def atomic_export(path):
    path=Path(path)
    if not path.parent.is_dir():raise ValueError('Choose an existing writable output folder')
    descriptor,name=tempfile.mkstemp(prefix='.'+path.stem+'-',suffix=path.suffix,dir=path.parent)
    os.close(descriptor);temporary=Path(name)
    try:
        checkpoint('Writing '+path.name)
        yield temporary
        checkpoint('Committing '+path.name)
        os.replace(temporary,path);mark_committed()
    finally:
        temporary.unlink(missing_ok=True)

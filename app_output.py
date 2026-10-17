"""Persistent user outputs live beside the executable, never in its unpack directory."""
from pathlib import Path
import os
import sys


def output_directory():
    override=os.environ.get('ANALIZER_OUTPUT_DIR')
    base=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parent
    preferred=Path(override).expanduser() if override else base/'SignalStudio_Output'
    candidates=[preferred] if override else [preferred,Path.home()/'Documents'/'SignalStudio_Output']
    for root in candidates:
        try:
            root.mkdir(parents=True,exist_ok=True)
            # Check actual write access, including a read-only application folder.
            import tempfile
            with tempfile.TemporaryFile(dir=root):pass
            return root
        except OSError:
            if root==candidates[-1]:raise


def output_path(name,category='reports'):
    if category not in ('reports','workspaces','templates','diagnostics','presets'):
        raise ValueError('Unknown output category')
    from app_lifecycle import settings_directory
    root=(settings_directory() if category in ('templates','presets') else output_directory())/category;root.mkdir(exist_ok=True)
    return root/Path(name).name

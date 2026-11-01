"""Versioned, trusted reader adapters and explicit import-option contracts.

Readers return ``[(table_name, DataFrame), ...]``. Source tables and their attrs
are preserved; plotting and analysis remain consumers of this common model.
"""
from dataclasses import dataclass, field
from pathlib import Path
import re


TABULAR_OPTIONS = {
    'reader_id': 'explicit registered adapter selected by the user',
    'delimiter': 'one-character separator or auto', 'header': 'zero-based row or null',
    'decimal': 'decimal separator', 'encoding': 'text encoding',
    'time_column': 'source column or null', 'unit': 'coordinate unit',
    'column_units': 'declared source-column units',
    'clock_domain': 'relative, absolute, sample, or declared shared domain',
    'acquisition_policy': 'sampled, held_state, event_log, or unknown',
}


class UnsupportedFormatError(ValueError):
    def __init__(self, path, readers):
        self.result = {'status': 'unsupported', 'path': str(path),
                       'reason': 'No registered reader supports this file extension.',
                       'supported_formats': sorted({s for r in readers for s in r.suffixes}),
                       'import_options': dict(TABULAR_OPTIONS)}
        super().__init__('Unsupported file format '+(Path(path).suffix or '(no extension)')+
                         '; choose a supported reader or convert to a supported tabular format.')


@dataclass(frozen=True)
class ReaderSpec:
    id: str
    version: str
    suffixes: tuple
    read: object
    options: dict = field(default_factory=dict)
    description: str = ''


_READERS = {}


def register_reader(reader):
    """Register an explicitly installed adapter; input data never loads code."""
    if not isinstance(reader, ReaderSpec):
        raise TypeError('Readers must implement ReaderSpec')
    if not isinstance(reader.id,str) or not re.fullmatch(r'[a-z][a-z0-9_.-]*', reader.id) or not isinstance(reader.version,str) or not reader.version.strip():
        raise ValueError('Reader identity and implementation version are required')
    if not callable(reader.read) or not reader.suffixes or not all(
            isinstance(s, str) and re.fullmatch(r'\.[a-z0-9]+', s) for s in reader.suffixes):
        raise ValueError('A reader requires a callable and explicit lowercase extensions')
    if not isinstance(reader.options, dict):
        raise ValueError('Reader options must be a declared dictionary')
    if reader.id in _READERS:
        raise ValueError('Duplicate reader identity: '+reader.id)
    occupied={suffix for r in _READERS.values() for suffix in r.suffixes}
    if occupied.intersection(reader.suffixes):
        raise ValueError('A file extension already has a registered reader')
    _READERS[reader.id] = reader
    return reader


def readers():
    from app_ingestion import _register_builtin_readers
    _register_builtin_readers()
    return tuple(_READERS.values())


def reader_for(path, reader_id=None):
    available = readers()
    if reader_id is not None:
        for reader in available:
            if reader.id == reader_id:return reader
        raise ValueError('Unknown reader adapter: '+str(reader_id))
    for reader in available:
        if Path(path).suffix.lower() in reader.suffixes:
            return reader
    raise UnsupportedFormatError(path, available)


def validate_options(options, reader=None):
    options = dict(options or {})
    unknown = set(options)-set(TABULAR_OPTIONS)-set(reader.options if reader is not None else ())
    if unknown:
        raise ValueError('Unsupported reader options: '+', '.join(sorted(unknown)))
    if options.get('header') is not None and ('header' in options) and (
            isinstance(options['header'], bool) or not isinstance(options['header'], int) or options['header']<0):
        raise ValueError('Header must be a nonnegative row number or null')
    if 'delimiter' in options and options['delimiter'] not in (None,'auto') and (
            not isinstance(options['delimiter'],str) or len(options['delimiter'])!=1):
        raise ValueError('delimiter must be one character')
    if 'decimal' in options and (not isinstance(options['decimal'],str) or len(options['decimal'])!=1):
        raise ValueError('decimal must be one character')
    if options.get('acquisition_policy','unknown') not in ('sampled','held_state','event_log','unknown'):
        raise ValueError('Unknown acquisition policy')
    if 'column_units' in options and not isinstance(options['column_units'],dict):
        raise ValueError('Column units must map source columns to units')
    for key in ('reader_id','encoding','time_column','unit','clock_domain'):
        if key in options and options[key] is not None and (not isinstance(options[key],str) or not options[key].strip()):
            raise ValueError(key+' must be a nonempty string or null')
    if 'column_units' in options and any(not isinstance(k,str) or not isinstance(v,str) for k,v in options['column_units'].items()):
        raise ValueError('Column-unit names and values must be strings')
    return options

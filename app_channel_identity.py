"""Readable, unique source labels without changing scientific channel identity.

Display aliases are presentation only.  Stable channel/dataset IDs, original
names and technical source metadata remain available for provenance and restore.
"""
from pathlib import PureWindowsPath
import re


def _short_name(value, limit=28):
    # PureWindowsPath also handles backslashes while running tests on Linux.
    text = PureWindowsPath(str(value or 'Recording')).name
    text = re.sub(r'\.(csv|tdms|xlsx?|zip|parquet|json|txt)$', '', text, flags=re.I)
    text = ' '.join(text.split()) or 'Recording'
    return text if len(text) <= limit else text[:limit - 1].rstrip() + '…'


def dataset_aliases(store):
    """Return short aliases, disambiguated even when basenames are identical."""
    proposed = {id: _short_name(dataset.frame.attrs.get('display_alias') or dataset.name)
                for id, dataset in store.datasets.items()}
    groups = {}
    for id, alias in proposed.items():
        groups.setdefault(alias.casefold(), []).append(id)
    result = dict(proposed)
    for ids in groups.values():
        if len(ids) > 1:
            for number, id in enumerate(ids, 1):
                # IDs are deliberately not used as the user's primary source label.
                result[id] = f'{proposed[id]} [{number}]'
    used = set()
    for id, alias in tuple(result.items()):
        candidate = alias; number = 2
        while candidate.casefold() in used:
            candidate = f'{alias} [{number}]'; number += 1
        result[id] = candidate; used.add(candidate.casefold())
    # A real recording may itself be called "Generated".  Generated channels
    # still need an unambiguous source label beside that recording's channels.
    generated='Generated';number=2
    while generated.casefold() in used:
        generated=f'Generated [{number}]';number+=1
    result.setdefault('', generated)
    return result


def channel_label(store, channel_or_id, include_source=None):
    """Label channels consistently; multiple recordings always show the source."""
    channel = store.channels[channel_or_id] if isinstance(channel_or_id, str) else channel_or_id
    if include_source is None:
        include_source = len(store.datasets) > 1 or len({c.dataset_id for c in store.channels.values()}) > 1
    if not include_source:
        return channel.name
    alias = dataset_aliases(store).get(channel.dataset_id, 'Generated')
    return f'{alias} · {channel.name}'


def channel_details(store, channel_or_id):
    """Full source details for tooltips, accessibility and local evidence."""
    channel = store.channels[channel_or_id] if isinstance(channel_or_id, str) else channel_or_id
    dataset = store.datasets.get(channel.dataset_id)
    lines = [f'Channel: {channel.name}']
    original = channel.attributes.get('source_column') or channel.attributes.get('original_name')
    if original and str(original) != channel.name:
        lines.append(f'Original parameter: {original}')
    if dataset:
        lines.append(f'Recording: {dataset.name}')
    source = channel.source or (dataset.source if dataset else '')
    if source:
        lines.append(f'Source: {source}')
    lines.extend([f'Channel ID: {channel.id}', f'Unit: {channel.unit or "Unknown"}'])
    return '\n'.join(lines)

"""Merge an editor's deliberate metadata changes with newer channel metadata."""
from copy import deepcopy


_MISSING = object()


def merge_metadata_edits(base, edited, current):
    """Retain external edits unless the user changed the same JSON field.

    Properties can stay open while another action updates a trace color. A
    recursive three-way merge preserves that color when the user later changes
    a name, note or line width. Explicit field removal still removes the field.
    Lists and scalar values are single user-editable values, not merged arrays.
    """
    if not all(isinstance(value, dict) for value in (base, edited, current)):
        raise ValueError('Channel metadata must be a JSON object')

    def merge(old, draft, latest):
        if old is not _MISSING and draft == old:
            return _MISSING if latest is _MISSING else deepcopy(latest)
        if isinstance(draft, dict) and isinstance(latest, dict) and (isinstance(old, dict) or old is _MISSING):
            old = {} if old is _MISSING else old
            result = deepcopy(latest)
            for key in old.keys() | draft.keys():
                if key not in draft:
                    result.pop(key, None)
                else:
                    result[key] = merge(old.get(key, _MISSING), draft[key], latest.get(key, _MISSING))
                    if result[key] is _MISSING:
                        result.pop(key)
            return result
        return deepcopy(draft)

    return merge(base, edited, current)

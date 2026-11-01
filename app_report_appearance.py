"""Presentation choices for exports, independent of measurement and UI state."""

CURSOR_LINES_OPTION = 'Include cursor lines in exported plots'


def include_cursor_lines(metadata=None):
    """Clean report plots are the default; only an explicit choice adds overlays.

    Cursor positions, locks and statistical scopes always remain in the result
    evidence. This option must never change a live workspace's cursor mode.
    """
    return (metadata or {}).get(CURSOR_LINES_OPTION) is True

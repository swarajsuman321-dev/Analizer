"""Report-only appearance; never changes the interactive cursor state."""


def show_cursor_guides(metadata=None):
    """Older workspaces also get clean plots until the user opts in."""
    return (metadata or {}).get('show_cursor_guides') is True

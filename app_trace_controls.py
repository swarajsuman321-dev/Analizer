"""Direct trace-color editing without rebuilding a user's graph arrangement.

The color is ordinary channel ``plot_style`` metadata, so the existing legend,
preset, workspace and export services all consume the same value.  Numerical
samples and cursor identities are never transformed by this presentation action.
"""
from copy import deepcopy
import json

from PySide6 import QtGui, QtWidgets
from shiboken6 import isValid

from app_channel_identity import channel_label
from app_compact_forms import choose_item
from app_trace_colors import PALETTE


class TraceColorControls:
    """One color-picker route shared by channel, Properties and chart actions."""

    def __init__(self, window):
        self.window = window

    def _dialog_parent(self):
        """Keep modal pickers above the currently detached fullscreen graph."""
        fullscreen = getattr(self.window, 'graph_fullscreen', None)
        host = getattr(fullscreen, 'fullscreen_window', None)
        if (fullscreen is not None and fullscreen.is_active
                and isinstance(host, QtWidgets.QWidget) and isValid(host)):
            return host
        return self.window

    def _ids(self, channel_ids):
        """Validate the entire stable-ID selection before changing anything."""
        if isinstance(channel_ids, str):
            channel_ids = [channel_ids]
        try:
            ids = list(dict.fromkeys(channel_ids))
        except (TypeError, ValueError) as exc:
            raise ValueError('Select channels before changing their trace color.') from exc
        if not ids:
            raise ValueError('Select at least one channel to change its trace color.')
        if any(channel_id not in self.window.store.channels for channel_id in ids):
            raise ValueError('A selected channel is no longer loaded. Select the channel again.')
        return ids

    def choose(self, channel_ids=None):
        """Pick a color for explicit or currently selected channels.

        Without a portal selection, a multi-trace graph asks which trace to
        change.  Cancellation returns an empty list and leaves metadata intact,
        including automatic-color allocation for channels not yet plotted.
        """
        window = self.window
        window.mutate()
        if channel_ids is None:
            channel_ids = window.portal.selected()
            if not channel_ids:
                pane = window.active_workspace.active
                channel_ids = [channel_id for channel_id in pane.ids
                               if channel_id in window.store.channels] if pane else []
                if len(channel_ids) > 1:
                    labels = [channel_label(window.store, channel_id, include_source=True)
                              for channel_id in channel_ids]
                    # A pathological source can contain equally named channels.
                    # Numbering keeps even those entries unambiguous by index.
                    choices = [f'{index + 1}. {label}' for index, label in enumerate(labels)]
                    selected, accepted = choose_item(self._dialog_parent(), 'Change Trace Color',
                                                     'Channel', choices)
                    if not accepted:
                        return []
                    channel_ids = [channel_ids[choices.index(selected)]]
        ids = self._ids(channel_ids)
        channel = window.store.channels[ids[0]]
        style = channel.attributes.get('plot_style', {})
        if not isinstance(style, dict):
            raise ValueError('The selected channel has invalid appearance settings.')
        initial = QtGui.QColor(style.get('color') or channel.attributes.get('trace_color')
                               or PALETTE[0])
        if not initial.isValid():
            initial = QtGui.QColor(PALETTE[0])
        title = 'Change Trace Color' if len(ids) == 1 else f'Change Trace Color — {len(ids)} channels'
        color = QtWidgets.QColorDialog.getColor(initial, self._dialog_parent(), title)
        if not color.isValid():
            return []
        return self.set_color(ids, color)

    def _refresh_properties_color(self, changes):
        """Reflect this leaf edit without discarding a Properties draft.

        The table and JSON editor can each contain unsaved changes.  Update
        their own style objects rather than repopulating either from the store;
        leave invalid JSON or a non-object style for the user to finish editing.
        """
        window = self.window
        selected = window.portal.selected()
        channel_id = getattr(window, '_property_channel_id', None)
        if not selected or selected[0] != channel_id or channel_id not in changes:
            return
        color = changes[channel_id]['plot_style']['color']

        raw = window.prop_attrs.toPlainText()
        try:
            attributes = json.loads(raw or '{}')
        except (ValueError, TypeError):
            attributes = None
        if isinstance(attributes, dict):
            style = attributes.get('plot_style', {})
            if isinstance(style, dict):
                attributes['plot_style'] = {**style, 'color': color}
                updated = json.dumps(attributes, indent=2, ensure_ascii=False)
                # A hidden, unchanged JSON editor must remain unchanged relative
                # to its snapshot, so pending structured edits keep precedence.
                pristine = raw == getattr(window, '_metadata_snapshot', raw)
                window.prop_attrs.setPlainText(updated)
                if pristine:
                    window._metadata_snapshot = updated

        table = window.prop_metadata
        rows = [row for row in range(table.rowCount())
                if table.item(row, 0) is not None
                and table.item(row, 0).text().strip() == 'plot_style']
        if not rows:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QtWidgets.QTableWidgetItem('plot_style'))
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(json.dumps({'color': color})))
        elif len(rows) == 1:
            item = table.item(rows[0], 1)
            try:
                style = json.loads(item.text()) if item is not None else None
            except (ValueError, TypeError):
                style = None
            if isinstance(style, dict):
                item.setText(json.dumps({**style, 'color': color}, ensure_ascii=False))

    def set_color(self, channel_ids, color):
        """Set one opaque color while retaining all graph and cursor state.

        ChannelStore notifies the existing workbench to refresh all bound panes.
        Its general refresh also reapplies saved axis limits and emits range
        callbacks.  Preserve the user's current zoom and history around that
        notification rather than sending this small edit through the bulk
        channel-mapping/layout service.
        """
        window = self.window
        window.mutate()
        ids = self._ids(channel_ids)
        try:
            chosen = QtGui.QColor(color)
        except (TypeError, ValueError) as exc:
            raise ValueError('Choose a valid trace color.') from exc
        if not chosen.isValid() or chosen.alpha() != 255:
            raise ValueError('Choose a valid opaque trace color.')
        value = chosen.name()
        changes = {}
        for channel_id in ids:
            channel = window.store.channels[channel_id]
            style = channel.attributes.get('plot_style', {})
            if not isinstance(style, dict):
                raise ValueError('The selected channel has invalid appearance settings.')
            if style.get('color') == value:
                continue
            attributes = dict(channel.attributes)
            attributes['plot_style'] = {**style, 'color': value}
            changes[channel_id] = attributes
        if not changes:
            return []

        # Keep the existing pane objects: rebuilding a workspace would discard
        # layout proportions, transient history and the selected active pane.
        workspaces = list(window.workspaces)
        guards = [(workspace, workspace._range_syncing, workspace._syncing)
                  for workspace in workspaces]
        panes = [(pane, deepcopy(pane.state()), deepcopy(pane.history),
                  pane.history_index, pane._history_restoring,
                  getattr(pane, '_restored_positions', False))
                 for workspace in workspaces for pane in workspace.panes]
        previous_channels = {channel_id: window.store.channels[channel_id]
                             for channel_id in changes}
        try:
            for workspace, _, _ in guards:
                workspace._range_syncing = True
                workspace._syncing = True
            for pane, _, _, _, _, _ in panes:
                pane._history_restoring = True
            try:
                with window.store.batch():
                    for channel_id, attributes in changes.items():
                        window.store.update(channel_id, attributes=attributes)
            except Exception:
                # A failed observer refresh must not leave half-applied colors.
                with window.store.batch():
                    window.store.channels.update(previous_channels)
                    window.store.changed(*previous_channels)
                raise
        finally:
            try:
                for pane, state, history, index, restoring, restored_positions in panes:
                    try:
                        pane.restore_ranges(state)
                    finally:
                        pane.history = history
                        pane.history_index = index
                        pane._history_restoring = restoring
                        pane._restored_positions = restored_positions
            finally:
                for workspace, range_syncing, syncing in guards:
                    workspace._range_syncing = range_syncing
                    workspace._syncing = syncing
        for workspace in workspaces:
            workspace.update_channel_legend()
            workspace.measurementsChanged.emit()
        self._refresh_properties_color(changes)
        window.statusBar().showMessage(f'Trace color updated for {len(changes)} channel(s).')
        return list(changes)

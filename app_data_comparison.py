"""Compare any imported channels using the existing shared plotting workspace.

This is a selection and presentation controller. It never imports a second copy
of an existing channel, resamples a clock, invents matching scores, or changes
the engineering reference/candidate interpretation.
"""
from copy import deepcopy

from PySide6 import QtCore, QtWidgets

from app_adaptive_ui import ContentDialog
from app_channel_identity import channel_details, dataset_aliases
from app_compact_forms import add_help
from app_plot_workspace import LAYOUTS


class DataComparisonDialog(ContentDialog):
    """One searchable source-partitioned chooser, with no cross-file master."""

    def __init__(self, controls, selected=()):
        super().__init__(controls.window)
        self.controls = controls
        self.pending_ids = set(selected)
        self.setWindowTitle('Compare Data')
        self.setWindowModality(QtCore.Qt.WindowModality.WindowModal)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QtWidgets.QVBoxLayout(self)
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText('Find a recording, channel or unit…')
        self.search.setAccessibleName('Find comparison channels')
        layout.addWidget(self.search)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(['Recording / Channel', 'Unit'])
        self.tree.setMinimumSize(360, 220)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setAccessibleName('Channels grouped by recording')
        layout.addWidget(self.tree)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.error = QtWidgets.QLabel()
        self.error.setWordWrap(True)
        self.error.setAccessibleName('Comparison selection error')
        self.error.hide()
        layout.addWidget(self.error)
        add_help(layout, 'Choose channels from any loaded recording, then Add to Comparison. '
                 'Each recording checkbox selects only that recording, including channels hidden by the search. '
                 'Existing Comparison traces remain; unchecking this list does not remove them. '
                 'Original sample times, units, names and colors are retained. Different coordinate systems '
                 'use separate graph panes. Use the ordinary cursors and readout to inspect differences. '
                 'Open More Files uses the normal import and TDMS review, then returns here.')
        buttons = QtWidgets.QHBoxLayout()
        self.open_button = QtWidgets.QPushButton('Open More Files…')
        self.open_button.setToolTip('Open any supported data files with the normal import and parameter review')
        self.add_button = QtWidgets.QPushButton('Add to Comparison')
        self.add_button.setDefault(True)
        self.cancel_button = QtWidgets.QPushButton('Cancel')
        buttons.addWidget(self.open_button)
        buttons.addStretch()
        buttons.addWidget(self.add_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        self.search.textChanged.connect(self.rebuild)
        self.tree.itemChanged.connect(self._changed)
        self.open_button.clicked.connect(lambda: controls.window.guard(controls.open_more_files))
        self.add_button.clicked.connect(self._apply)
        self.cancel_button.clicked.connect(self.reject)
        self.rebuild()

    def selected_ids(self):
        # Store insertion order is deterministic and does not depend on sorting
        # or filtering the visible tree.
        return [id for id in self.controls.window.store.channels if id in self.pending_ids]

    def rebuild(self, *_):
        store = self.controls.window.store
        self.pending_ids.intersection_update(store.channels)
        query = self.search.text().strip().casefold()
        aliases = dataset_aliases(store)
        grouped = {id: [] for id in store.datasets}
        for channel in store.channels.values():
            grouped.setdefault(channel.dataset_id, []).append(channel)
        self.source_ids = {id: [channel.id for channel in channels] for id, channels in grouped.items()}
        self.roots = {}
        self.items = {}
        blocker = QtCore.QSignalBlocker(self.tree)
        self.tree.clear()
        for dataset_id, channels in grouped.items():
            dataset = store.datasets.get(dataset_id)
            alias = aliases.get(dataset_id, 'Unassigned channels')
            root = QtWidgets.QTreeWidgetItem(self.tree, [alias])
            root.setData(0, QtCore.Qt.ItemDataRole.UserRole + 1, dataset_id)
            root.setFlags(root.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
            details = (dataset.name + '\n' + dataset.source + '\n' if dataset else '')
            root.setToolTip(0, details + 'Select channels in this recording only, including any hidden by the search.')
            self.roots[dataset_id] = root
            matches = 0
            for channel in channels:
                text = ' '.join((channel.name, channel.unit, channel.group, channel.source,
                                 dataset.name if dataset else '', str(channel.attributes))).casefold()
                if query and query not in text:
                    continue
                matches += 1
                item = QtWidgets.QTreeWidgetItem(root, [channel.name, channel.unit or 'Unknown'])
                item.setData(0, QtCore.Qt.ItemDataRole.UserRole, channel.id)
                item.setFlags(item.flags() | QtCore.Qt.ItemFlag.ItemIsUserCheckable)
                details = channel_details(store, channel) + f'\nCoordinates: {channel.coordinate_kind} ({channel.coordinate_unit})'
                item.setToolTip(0, details)
                item.setData(0, QtCore.Qt.ItemDataRole.AccessibleDescriptionRole, details)
                self.items[channel.id] = item
            root.setData(0, QtCore.Qt.ItemDataRole.UserRole + 2, matches)
        self.tree.expandAll()
        self._update_checks()
        del blocker

    def _update_checks(self):
        store = self.controls.window.store
        aliases = dataset_aliases(store)
        blocker = QtCore.QSignalBlocker(self.tree)
        for dataset_id, root in self.roots.items():
            ids = set(self.source_ids[dataset_id])
            checked = ids & self.pending_ids
            state = (QtCore.Qt.CheckState.Checked if ids and checked == ids else
                     QtCore.Qt.CheckState.PartiallyChecked if checked else QtCore.Qt.CheckState.Unchecked)
            root.setCheckState(0, state)
            action = 'Deselect All' if ids and checked == ids else 'Select All'
            count = f'{len(checked)}/{len(ids)} selected'
            if self.search.text().strip():
                count += f' · {root.data(0, QtCore.Qt.ItemDataRole.UserRole + 2)} matches'
            root.setText(0, f'{aliases.get(dataset_id, "Unassigned channels")} — {action} · {count}')
        for id, item in self.items.items():
            item.setCheckState(0, QtCore.Qt.CheckState.Checked if id in self.pending_ids else QtCore.Qt.CheckState.Unchecked)
        count = len(self.pending_ids)
        self.status.setText(f'{count} channels selected. Existing Comparison traces will be kept.' if store.channels else
                            'No channels loaded. Open files to choose data for comparison.')
        self.add_button.setEnabled(bool(count))
        del blocker

    def _changed(self, item, column):
        if column != 0:
            return
        dataset_id = item.data(0, QtCore.Qt.ItemDataRole.UserRole + 1)
        ids = self.source_ids.get(dataset_id, []) if dataset_id is not None else [item.data(0, QtCore.Qt.ItemDataRole.UserRole)]
        if item.checkState(0) == QtCore.Qt.CheckState.Checked:
            self.pending_ids.update(id for id in ids if id)
        else:
            self.pending_ids.difference_update(ids)
        self.error.hide()
        self._update_checks()

    def _apply(self):
        try:
            self.controls.add_channels(self.selected_ids())
        except Exception as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self.accept()


class DataComparisonControls(QtCore.QObject):
    """Public workbench hook for ordinary arbitrary-data overlay comparison."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.dialog = None
        self.last_result = None
        self._selection = []
        self._pending_open = False
        self._import_store = None
        self._import_generation = None
        self._resume = QtCore.QTimer(self)
        self._resume.setInterval(100)
        self._resume.timeout.connect(self._resume_after_open)
        window.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.window and event.type() == QtCore.QEvent.Type.Close:
            # Stop before a close handler waits for a worker, which can run a
            # nested event loop. A rejected close simply cancels auto-reopening.
            self._pending_open = False
            self._resume.stop()
            if self.dialog is not None:
                self.dialog.reject()
        return super().eventFilter(obj, event)

    def show_dialog(self):
        self.window.mutate()
        if self.dialog is not None:
            self.dialog.rebuild()
            self.dialog.show()
            self.dialog.raise_()
            self.dialog.activateWindow()
            return self.dialog
        initial = self._selection or self.window.portal.selected()
        dialog = DataComparisonDialog(self, initial)
        self.dialog = dialog
        dialog.finished.connect(lambda _result, current=dialog: self._dialog_finished(current))
        dialog.show()
        return dialog

    def _dialog_finished(self, dialog):
        self._selection = dialog.selected_ids()
        if self.dialog is dialog:
            self.dialog = None

    def _layout_for(self, workspace, ids, selected):
        """Preflight the existing assign heuristic before any plot mutation."""
        coordinates = list(dict.fromkeys((self.window.store.channels[id].coordinate_kind,
                                          self.window.store.channels[id].coordinate_unit) for id in ids))
        # A repeated selection already in a hidden pane should become visible,
        # without adding the same stable identity to a second pane.
        selected_panes = [index + 1 for index, pane in enumerate(workspace.panes) if set(pane.ids) & set(selected)]
        minimum = max(selected_panes, default=1)
        current_count = len(workspace.visible_panes())
        candidates = list(dict.fromkeys((workspace.layout_name, 'Horizontal split', '2×2', '10 panels')))
        for name in candidates:
            rows, columns = LAYOUTS[name]
            count = rows * columns
            if count < max(current_count, minimum):
                continue
            slots = [workspace.panes[index].coordinate if index < len(workspace.panes) and workspace.panes[index].ids else None
                     for index in range(count)]
            target = workspace.panes.index(workspace.active)
            for coordinate in coordinates:
                if slots[target] is not None and slots[target] != coordinate:
                    target = next((index for index, value in enumerate(slots) if value is None or value == coordinate), None)
                    if target is None:
                        break
                slots[target] = coordinate
            else:
                return name
        raise ValueError('These coordinate systems need more than ten graph panes. Compare fewer coordinate families at once.')

    def add_channels(self, ids):
        """Append unique existing identities and return explicit selection counts.

        No domain data is copied or changed. Existing populated panes retain
        their ranges, cursors, locks, bindings and annotations when traces are
        added. Known invalid selections fail before any workspace is modified.
        """
        self.window.mutate()
        if isinstance(ids, str):
            ids = [ids]
        try:
            selected = list(dict.fromkeys(ids))
        except (TypeError, ValueError) as exc:
            raise ValueError('Select at least one loaded channel to compare.') from exc
        if not selected:
            raise ValueError('Select at least one channel to compare.')
        missing = [id for id in selected if id not in self.window.store.channels]
        if missing:
            raise ValueError(f'{len(missing)} selected channels are no longer loaded. Open Compare Data again and review the selection.')
        workspace = self.window.comparison
        present = {id for pane in workspace.panes for id in pane.ids}
        additions = [id for id in selected if id not in present]
        layout = self._layout_for(workspace, additions, selected)
        exit_fullscreen = getattr(self.window, 'exit_graph_fullscreen', None)
        if exit_fullscreen is not None:
            exit_fullscreen()
        previous = deepcopy(workspace.state())
        original_panes = list(workspace.panes)
        histories = [(pane, deepcopy(pane.history), pane.history_index,
                      pane._history_restoring, bool(pane.ids)) for pane in original_panes]
        for pane, _history, _index, _restoring, populated in histories:
            if populated:
                pane._history_restoring = True
        failed = False
        try:
            if layout != workspace.layout_name:
                workspace.set_layout(layout)
                # Layout changes copy the active pane's cursor controls to
                # every pane. Adding traces must retain each existing pane's
                # choices, including panes that stay hidden in the new layout.
                for pane, saved in zip(original_panes, previous['panes']):
                    pane.snap = saved['snap']
                    pane.set_cursor_mode(saved['cursor_mode'])
            if additions:
                workspace.set_visible(additions, True)
        except Exception:
            failed = True
            self._restore_failed_add(workspace, previous, original_panes)
            raise
        finally:
            for pane, history, index, restoring, populated in histories:
                if populated or failed:
                    pane.history = history
                    pane.history_index = index
                pane._history_restoring = restoring
        self.window.tabs.setCurrentWidget(workspace)
        self.window.sync_visibility()
        self.window.readouts()
        total = {id for pane in workspace.panes for id in pane.ids}
        result = {'added': len(additions), 'already_present': len(selected) - len(additions),
                  'total': len(total), 'datasets': len({self.window.store.channels[id].dataset_id for id in selected})}
        self.last_result = result
        self.window.statusBar().showMessage(f'{result["added"]} channels added to Comparison; '
                                            f'{result["already_present"]} already present. Original data and Analysis are unchanged.')
        return result

    @staticmethod
    def _restore_failed_add(workspace, state, original_panes):
        """Roll back presentation without replacing panes used by playback."""
        range_syncing, cursor_syncing = workspace._range_syncing, workspace._syncing
        workspace._range_syncing = workspace._syncing = True
        try:
            for pane in workspace.panes[len(original_panes):]:
                workspace.grid.removeWidget(pane)
                pane.hide()
                pane.stop_callbacks();pane.deleteLater()
            workspace.panes = original_panes
            workspace.active = original_panes[state.get('active', 0)]
            workspace.layout_proportions = deepcopy(state.get('layout_proportions', {}))
            workspace.set_layout(state['layout'])
            for pane, saved in zip(original_panes, state['panes']):
                pane.restore(saved)
        finally:
            workspace._range_syncing, workspace._syncing = range_syncing, cursor_syncing
        workspace.update_channel_legend()
        workspace.measurementsChanged.emit()

    def open_more_files(self):
        """Use ordinary Open, then return after its one import/review finishes."""
        self.window.mutate()
        self._resume.stop()
        if self.dialog is not None:
            self.dialog.reject()
        self.window.tabs.setCurrentWidget(self.window.comparison)
        self._import_store = self.window.store
        self._import_generation = self.window.generation
        self._pending_open = True
        try:
            self.window.open_data(plot_import=False)
        except Exception:
            self._pending_open = False
            self.show_dialog()
            raise
        if self._pending_open:
            self._resume.start()

    def _resume_after_open(self):
        if not self._pending_open:
            self._resume.stop()
            return
        window = self.window
        if (not window.isVisible() or window.store is not self._import_store or
                window.generation != self._import_generation):
            self._pending_open = False
            self._resume.stop()
            return
        # busy is cleared before Open's completion callback, whose TDMS review
        # can enter a modal loop. Both conditions must have settled first.
        if window.busy or window.workers or QtWidgets.QApplication.activeModalWidget() is not None:
            return
        self._pending_open = False
        self._resume.stop()
        self.show_dialog()

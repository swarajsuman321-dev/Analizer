"""Reversible dock folding with a compact, always-reachable Panels menu.

Folding uses QDockWidget.hide(), never removes a dock, replaces its widget or
changes its tab group. Native QMainWindow state remains the layout authority.
An inactive tab is open: visibilityChanged(False) alone does not mean folded.
"""
from PySide6 import QtCore, QtGui, QtWidgets


class PanelFoldingControls(QtCore.QObject):
    """Manage the docks in ``window.docks`` without changing their contents.

    Add ``button`` to an existing header/toolbar. Call apply_defaults only for an
    ordinary new session. For a saved workspace, restore native dock state first
    and then call restore; restore(None) simply reflects a legacy native layout.
    Extra panels are never folded implicitly, including tab-group neighbours.
    """

    changed = QtCore.Signal(str, bool)  # Panel name and whether it is folded.

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.docks = dict(window.docks)
        self._sizes = {}
        self._folded = {}
        self._revision = {name: 0 for name in self.docks}
        self._restoring = False
        self.menu = QtWidgets.QMenu('Panels', window)
        self.menu.setObjectName('panelFoldingMenu')
        self.menu.setToolTipsVisible(True)
        self.button = QtWidgets.QToolButton(window)
        self.button.setObjectName('panelFoldingButton')
        self.button.setText('Panels')
        self.button.setAccessibleName('Expand or fold panels')
        self.button.setAccessibleDescription(
            'Open the Panels menu to expand or fold a panel without losing its data.')
        self.button.setToolTip('Expand or fold panels; checked panels are open')
        self.button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.button.setMenu(self.menu)
        self.button.setSizePolicy(QtWidgets.QSizePolicy.Policy.Minimum,
                                  QtWidgets.QSizePolicy.Policy.Fixed)
        self.actions = {}
        for name, dock in self.docks.items():
            action = QtGui.QAction(name, self.menu)
            action.setObjectName('panelFoldingAction_' + name.replace(' ', '_'))
            action.setCheckable(True)
            action.toggled.connect(lambda checked, name=name: self.set_folded(name, not checked))
            self.menu.addAction(action)
            self.actions[name] = action
            dock.installEventFilter(self)
            dock.visibilityChanged.connect(lambda _visible, name=name: self._dock_changed(name))
            dock.toggleViewAction().toggled.connect(lambda _checked, name=name: self._dock_changed(name))
            dock.topLevelChanged.connect(lambda _floating, name=name: self._dock_changed(name))
            self._folded[name] = dock.isHidden()
            self._remember_size(name)
        self.menu.aboutToShow.connect(self.sync)
        self.sync()

    def _dock(self, name):
        if name not in self.docks:
            raise KeyError('Unknown panel: ' + str(name))
        return self.docks[name]

    def _remember_size(self, name):
        if self._restoring:
            return
        dock = self.docks[name]
        if dock.isHidden():
            return
        width, height = dock.width(), dock.height()
        if width > 0 and height > 0:
            self._sizes[name] = {'width': width, 'height': height}

    def is_folded(self, name):
        """Use explicit hiding, not the visibility of the selected dock tab."""
        return self._dock(name).isHidden()

    def _dock_changed(self, name):
        from shiboken6 import isValid
        if not isValid(self.window) or not isValid(self.docks[name]) or not isValid(self.actions[name]):return
        folded = self.is_folded(name)
        previous = self._folded.get(name)
        self._folded[name] = folded
        if not folded:
            self._remember_size(name)
        action = self.actions[name]
        blocker = QtCore.QSignalBlocker(action)
        action.setChecked(not folded)
        action.setText(('Expand ' if folded else 'Fold ') + name)
        action.setToolTip(('Expand ' if folded else 'Fold ') + name +
                          ' panel. Panel contents and settings are retained.')
        style = self.window.style()
        action.setIcon(style.standardIcon(QtWidgets.QStyle.StandardPixmap.SP_ArrowRight if folded
                                         else QtWidgets.QStyle.StandardPixmap.SP_ArrowDown))
        del blocker
        if previous is not None and previous != folded:
            self.changed.emit(name, folded)

    def sync(self):
        """Reflect native View-menu/close/show-all/restore actions in the menu."""
        for name in self.docks:
            self._dock_changed(name)

    def apply_defaults(self, names=('Properties',)):
        """Fold exactly the authorized names; preserve all other panel states."""
        names = tuple(names)
        for name in names:
            self._dock(name)  # Validate the full list before changing anything.
        for name in names:
            self.set_folded(name, True)

    def set_folded(self, name, folded):
        """Hide/show a native dock, retaining tabs, floating state and prior size."""
        dock = self._dock(name)
        folded = bool(folded)
        self._revision[name] += 1
        revision = self._revision[name]
        # Native restoreState already restores open tabs and their geometry.
        # Reopening an inactive tab would select it and overwrite that layout.
        if dock.isHidden() == folded:
            self._dock_changed(name)
            return folded
        if folded:
            self._remember_size(name)
            dock.hide()
        else:
            # Showing may synchronously resize the dock. Keep the pre-fold size
            # before those native events update the remembered geometry.
            size = dict(self._sizes.get(name, {}))
            dock.show()
            if not self._restoring:
                dock.raise_()
            self._restore_size(name, revision, size)
            # Qt can finish dock layout on the next event-loop turn. Ignore an
            # obsolete request if the user folds/toggles the panel meanwhile.
            QtCore.QTimer.singleShot(0, self, lambda: self._restore_size(name, revision, size))
        self._dock_changed(name)
        return folded

    def toggle(self, name):
        return self.set_folded(name, not self.is_folded(name))

    def _restore_size(self, name, revision, size):
        dock = self.docks[name]
        if revision != self._revision[name] or dock.isHidden() or not size:
            return
        width, height = size.get('width'), size.get('height')
        if not all(type(value) is int and 0 < value < 100_000 for value in (width, height)):
            return
        if dock.isFloating():
            dock.resize(width, height)
        else:
            area = self.window.dockWidgetArea(dock)
            horizontal = area in (QtCore.Qt.DockWidgetArea.LeftDockWidgetArea,
                                  QtCore.Qt.DockWidgetArea.RightDockWidgetArea)
            self.window.resizeDocks([dock], [width if horizontal else height],
                                    QtCore.Qt.Orientation.Horizontal if horizontal
                                    else QtCore.Qt.Orientation.Vertical)

    def state(self):
        """Return JSON-compatible folding metadata alongside native dock state."""
        self.sync()
        return {'schema': 1, 'panels': {
            name: dict(self._sizes.get(name, {}), folded=self.is_folded(name))
            for name in self.docks}}

    def restore(self, state):
        """Restore folding after native restoreState; never apply new defaults.

        A missing/legacy folding record leaves the restored native layout intact.
        Unknown panels are ignored so configurations from other versions remain
        usable. Native QMainWindow state owns positions, tab groups and floating.
        """
        if not isinstance(state, dict) or state.get('schema') != 1 or not isinstance(state.get('panels'), dict):
            self.sync()
            return False
        pending = []
        for name, record in state['panels'].items():
            if name not in self.docks or not isinstance(record, dict) or type(record.get('folded')) is not bool:
                continue
            size = {key: value for key in ('width', 'height')
                    if type(value := record.get(key)) is int and 0 < value < 100_000}
            pending.append((name, record['folded'], size))
        self._restoring = True
        try:
            for name, folded, size in pending:
                if len(size) == 2:
                    self._sizes[name] = size
                self.set_folded(name, folded)
        finally:
            self._restoring = False
        self.sync()
        return True

    restore_state = restore

    def eventFilter(self, watched, event):
        name = next((name for name, dock in self.docks.items() if dock is watched), None)
        if name is not None:
            kind = event.type()
            if kind in (QtCore.QEvent.Type.Close, QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Move):
                self._remember_size(name)
            if kind in (QtCore.QEvent.Type.Show, QtCore.QEvent.Type.Hide,
                        QtCore.QEvent.Type.ShowToParent, QtCore.QEvent.Type.HideToParent):
                self._dock_changed(name)
        return super().eventFilter(watched, event)

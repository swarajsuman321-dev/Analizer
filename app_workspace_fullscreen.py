"""Show a workspace's original split graph layout in one fullscreen window.

The entire existing graph container moves between scroll areas. Plot panes,
curves, axis bindings, cursor/sample identities and layout weights are never
copied or rebound. The selected-graph controller remains a separate capability.
"""
from PySide6 import QtCore, QtWidgets

from app_graph_fullscreen import GraphFullscreenController, _alive


class WorkspaceFullscreenController(GraphFullscreenController):
    """A reversible fullscreen host for every visible pane in one workspace.

    The proven fullscreen navigation and measurement widgets are shared with
    selected-graph fullscreen. Clicking another pane changes the live readout;
    it never hides the other plots or forces the previous pane active again.
    """
    def __init__(self, window):
        super().__init__(window)
        self.action.setText('Fullscreen Workspace')
        self.action.setObjectName('fullscreenWorkspace')
        self.action.setToolTip('Expand all graphs in the current split layout, with navigation and live values. F11 or Esc returns.')
        self.exit_action.setObjectName('exitWorkspaceFullscreen')
        self.exit_action.setToolTip('Return every graph to the workspace (Esc or F11).')
        self._pane_selector_signature = None
        self._workspace_hover_pane = None

    def _build_window(self):
        if self.fullscreen_window is not None:
            return
        super()._build_window()
        self.fullscreen_window.setObjectName('workspaceFullscreenWindow')
        self.graph_scroll.setObjectName('fullscreenWorkspaceGraphs')
        self.exit_button.setAccessibleName('Exit Fullscreen Workspace')
        self.readout.setAccessibleName('Live active graph cursor values and range statistics')
        selector_row = QtWidgets.QWidget(self.readout_panel)
        row = QtWidgets.QHBoxLayout(selector_row)
        row.setContentsMargins(0, 0, 0, 0)
        label = QtWidgets.QLabel('Values for', selector_row)
        self.pane_selector = QtWidgets.QComboBox(selector_row)
        self.pane_selector.setObjectName('fullscreenActiveGraph')
        self.pane_selector.setMinimumContentsLength(18)
        self.pane_selector.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.pane_selector.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.pane_selector.setAccessibleName('Graph for live cursor values')
        self.pane_selector.setToolTip('Click a graph, or choose it here, to inspect its cursor values and interval statistics. All graphs remain visible.')
        label.setBuddy(self.pane_selector)
        row.addWidget(label)
        row.addWidget(self.pane_selector, 1)
        self.readout_panel.layout().insertWidget(0, selector_row)
        self.pane_selector.currentIndexChanged.connect(self._select_pane)

    def toggle(self, checked=False):
        return self.exit() if self.is_active else self.enter()

    def enter(self, workspace=None):
        """Move the original graph container, preserving its entire layout."""
        if workspace is None:
            workspace = self.window.active_workspace
        # Accept a graph as a convenient context-menu target as well.
        if workspace not in self.window.workspaces:
            workspace = next((item for item in self.window.workspaces if workspace in item.panes), None)
        if workspace is None or workspace not in self.window.workspaces:
            raise ValueError('Choose an analysis workspace before entering fullscreen.')
        selected = getattr(self.window, 'graph_fullscreen', None)
        if selected is not None and selected is not self and selected.is_active:
            # A selected-pane session has removed a real pane from this
            # container. Restore it before moving the complete layout, rather
            # than fullscreening a placeholder alongside the other graphs.
            selected.exit(restore_focus=False)
            if selected.is_active:
                raise ValueError('Wait for the selected graph to finish returning before expanding the workspace.')
        if self.is_active:
            if workspace is self.workspace:
                self.fullscreen_window.raise_()
                return self.fullscreen_window
            self.exit(restore_focus=False)
        container, scroll = workspace.container, workspace.scroll
        if scroll.widget() is not container:
            raise ValueError('The workspace graph layout is already displayed elsewhere. Exit its current fullscreen view first.')
        panes = tuple(workspace.visible_panes())
        if not panes:
            raise ValueError('The workspace has no graph layout to expand.')
        self._build_window()
        placeholder = QtWidgets.QWidget()
        placeholder.setObjectName('fullscreenWorkspacePlaceholder')
        placeholder.setAccessibleName('This graph layout is open in fullscreen')
        self._snapshot = {
            'container': container, 'scroll': scroll, 'placeholder': placeholder,
            'panes': panes, 'layout_name': workspace.layout_name,
            'focus': QtWidgets.QApplication.focusWidget(),
            'tab': self.window.tabs.currentIndex(), 'active': workspace.active,
            'screen': container.screen(),
            'scroll_position': (scroll.horizontalScrollBar().value(), scroll.verticalScrollBar().value()),
            'main_geometry': QtCore.QRect(self.window.geometry()),
            'main_normal_geometry': QtCore.QRect(self.window.normalGeometry()),
            'main_docks': QtCore.QByteArray(self.window.saveState()),
            'main_window_state': self.window.windowState(),
            'initial_readout_pending': True,
        }
        self.workspace, self.pane = workspace, workspace.active
        self._transition = True
        try:
            scroll.takeWidget()
            scroll.setWidget(placeholder)
            self.graph_scroll.setWidget(container)
            container.show()
            self.window.tabs.setCurrentIndex(self.window.workspaces.index(workspace))
            self._release_navigation()
            excluded = {self.action, self.exit_action}
            for name in ('graph_fullscreen', 'workspace_fullscreen'):
                controller = getattr(self.window, name, None)
                if controller is not None:
                    excluded.add(controller.action)
            for action in workspace.navigation_bar.actions():
                if action in excluded:
                    continue
                self.navigation_bar.addAction(action)
                button = self.navigation_bar.widgetForAction(action)
                if button is not None:
                    button.setAccessibleName(action.text())
                    if not action.icon().isNull():
                        button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
            plot_menu = getattr(getattr(self.window, 'studio', None), 'submenus', {}).get('Plot')
            if plot_menu is not None:
                for action in plot_menu.actions():
                    if action not in excluded and not action.shortcut().isEmpty() and action not in self.navigation_bar.actions():
                        self.fullscreen_window.addAction(action)
                        self._extra_shortcuts.append(action)
            self._connect(workspace.measurementsChanged, self.queue_readouts)
            self._connect(workspace.activeChanged, self._keep_selected_pane)
            self._connect(self.window.tabs.currentChanged, self._keep_selected_workspace)
            for pane in panes:
                self._connect(pane.cursorsChanged, self.queue_readouts)
                self._connect(pane.hoverChanged, lambda state, item=pane: self._pane_hover_changed(item, state))
                self._connect(pane.destroyed, self._pane_destroyed)
            if hasattr(self.window, 'stats_scope'):
                self._connect(self.window.stats_scope.currentTextChanged, self.queue_readouts)
            if hasattr(self.window, 'theme'):
                self._connect(self.window.theme.themeChanged, self.queue_readouts)
            host = self.fullscreen_window
            host.setWindowTitle('All Graphs — '+self.window.windowTitle())
            if hasattr(host, 'setScreen') and _alive(self._snapshot['screen']):
                host.setScreen(self._snapshot['screen'])
            QtWidgets.QApplication.instance().installEventFilter(self)
            self._pane_selector_signature = None
            self._workspace_hover_pane = None
            self._pane_hover_changed(self.pane, None)
            self.refresh_readouts()
            host.showFullScreen()
            self.splitter.setSizes([max(350, host.height()-250), 220])
            session = self._snapshot
            QtCore.QTimer.singleShot(0, self, lambda: self._fit_initial_readout(session))
            workspace.queue_canvas_alignment()
            host.raise_()
            host.activateWindow()
            if _alive(self.pane):
                self.pane.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
            blocker = QtCore.QSignalBlocker(self.action)
            self.action.setChecked(True)
            del blocker
        except Exception:
            self._transition = False
            self.exit(restore_focus=False)
            raise
        finally:
            self._transition = False
        return self.fullscreen_window

    def _keep_selected_pane(self, pane):
        if not self.is_active or self._transition:
            return
        if self._structure_changed():
            self.structure_timer.start(0)
            return
        if pane in self.workspace.visible_panes():
            self.pane = pane
        self.queue_readouts()

    def _select_pane(self, index):
        if not self.is_active or self._transition:
            return
        panes = self.workspace.visible_panes()
        if 0 <= index < len(panes):
            self.workspace.set_active(panes[index])
            self.pane = panes[index]
            self.pane.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
            self.queue_readouts()

    def _pane_hover_changed(self, pane, state):
        if not self.is_active:
            return
        if state is None and self._workspace_hover_pane is not None and pane is not self._workspace_hover_pane:
            return
        self._workspace_hover_pane = pane if state else None
        # Hover is read-only and must not silently change the active graph.
        text = pane.hover_text if state else 'Mouse X/Y · Move over a graph to inspect values'
        if state:
            number = self.workspace.visible_panes().index(pane)+1
            text = 'Graph '+str(number)+' · '+text
        self.hover_readout.setToolTip(text)
        self.hover_readout.setAccessibleName(text)
        width = max(100, self.hover_readout.contentsRect().width())
        self.hover_readout.setText('\n'.join(self.hover_readout.fontMetrics().elidedText(
            line, QtCore.Qt.TextElideMode.ElideRight, width) for line in text.splitlines()[:2]))

    def refresh_readouts(self):
        if not self.is_active or not _alive(self.workspace):
            return
        panes = self.workspace.visible_panes()
        if self.workspace.active in panes:
            self.pane = self.workspace.active
        if not _alive(self.pane) or self.pane not in panes:
            return
        labels = []
        for index, pane in enumerate(panes):
            names = [pane.store.channels[channel_id].name for channel_id in pane.ids if channel_id in pane.store.channels]
            label = 'Graph '+str(index+1)+' · '+(', '.join(names[:2]) or 'No channels selected')
            if len(names)>2:
                label += ' +'+str(len(names)-2)
            labels.append(label)
        signature = tuple(labels)
        blocker = QtCore.QSignalBlocker(self.pane_selector)
        if signature != self._pane_selector_signature:
            self.pane_selector.clear()
            self.pane_selector.addItems(labels)
            self._pane_selector_signature = signature
        self.pane_selector.setCurrentIndex(panes.index(self.pane))
        del blocker
        super().refresh_readouts()
        self.interval_caption.setAccessibleDescription('Values and statistics for graph '+str(panes.index(self.pane)+1))

    def _structure_changed(self):
        if not self.is_active:
            return False
        saved = self._snapshot
        return (not _alive(self.workspace) or not _alive(saved['container']) or
                self.workspace.container is not saved['container'] or
                self.workspace.layout_name != saved['layout_name'] or
                tuple(self.workspace.visible_panes()) != saved['panes'] or
                saved['container'].parentWidget() is not self.graph_scroll.viewport() or
                any(not _alive(pane) for pane in saved['panes']))

    def exit(self, checked=False, *, restore_focus=True, restore_main_state=True, preserve_workspace_layout=False):
        """Restore the original container, keeping deliberate graph navigation."""
        if not self.is_active or self._transition:
            return False
        self._transition = True
        saved, workspace = self._snapshot, self.workspace
        active = workspace.active if _alive(workspace) else None
        self.refresh_timer.stop()
        self.structure_timer.stop()
        self._disconnect()
        QtWidgets.QApplication.instance().removeEventFilter(self)
        try:
            if _alive(self.fullscreen_window):
                self.fullscreen_window.hide()
            container, scroll = saved['container'], saved['scroll']
            if _alive(container) and _alive(scroll):
                if self.graph_scroll.widget() is container:
                    self.graph_scroll.takeWidget()
                if scroll.widget() is saved['placeholder']:
                    scroll.takeWidget()
                # Respect a deliberate external replacement rather than
                # deleting its new widget through QScrollArea.setWidget().
                if scroll.widget() is None:
                    scroll.setWidget(container)
                    container.show()
                    scroll.horizontalScrollBar().setValue(saved['scroll_position'][0])
                    scroll.verticalScrollBar().setValue(saved['scroll_position'][1])
                elif _alive(workspace):
                    # An external plugin replaced the scroll content. Keep its
                    # replacement and give the old container an owning QObject
                    # parent rather than leaving a detached top-level widget.
                    container.setParent(workspace)
                    container.hide()
            if _alive(saved['placeholder']):
                saved['placeholder'].hide()
                saved['placeholder'].deleteLater()
            self._snapshot = None
            self.pane = self.workspace = None
            blocker = QtCore.QSignalBlocker(self.action)
            self.action.setChecked(False)
            del blocker
            self._release_navigation()
            for action in self._extra_shortcuts:
                if _alive(action):
                    self.fullscreen_window.removeAction(action)
            self._extra_shortcuts.clear()
            if _alive(self.window) and restore_main_state:
                self._restore_main_geometry(saved)
                if self.window.saveState() != saved['main_docks']:
                    self.window.restoreState(saved['main_docks'])
                self.window.tabs.setCurrentIndex(saved['tab'])
            if _alive(workspace):
                if _alive(active) and active in workspace.visible_panes():
                    workspace.set_active(active)
                workspace.queue_canvas_alignment()
            if restore_focus and _alive(self.window):
                self.window.raise_()
                self.window.activateWindow()
                focus = saved['focus']
                if _alive(focus) and focus.isVisible():
                    focus.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
        finally:
            self._transition = False
        return True

    def eventFilter(self, obj, event):
        kind = event.type()
        if self.is_active and not self._transition and obj is self._snapshot['container'] and kind in (
                QtCore.QEvent.Type.ParentChange, QtCore.QEvent.Type.Hide):
            self.structure_timer.start(0)
        # The base handles Escape, main-window close and the one-time readout
        # fit on native fullscreen resize. Its pane guard is harmless here;
        # validation uses the entire container and complete pane identity list.
        return super().eventFilter(obj, event)

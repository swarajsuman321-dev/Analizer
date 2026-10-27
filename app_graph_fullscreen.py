"""Expand one existing graph without copying channels or changing its identity.

The detached PlotPane remains part of its original PlotWorkspace.  Navigation
uses the workspace's actual QAction objects and source-sample readouts use the
same measurement methods as the normal workbench.  A placeholder preserves the
original grid slot; returning the graph never rebuilds curves or binds channels.

Integration: call ``exit()`` before replacing/restoring a workspace, removing a
dataset, or deliberately changing graph layouts.  The main-window Close event
also exits defensively.  The existing Focus Graph command remains independent.
"""
import html
import math

from PySide6 import QtCore, QtGui, QtWidgets
from shiboken6 import isValid

from app_channel_identity import channel_details, channel_label
from app_presentation import CURSOR_COLORS, match_color


def _alive(value):
    return value is not None and isValid(value)


def _number(value):
    return f'{value:.6g}' if math.isfinite(value) else 'Unknown'


class _GraphFullscreenWindow(QtWidgets.QMainWindow):
    def __init__(self, controller):
        super().__init__(controller.window, QtCore.Qt.WindowType.Window)
        self.controller = controller
        self.setObjectName('selectedGraphFullscreenWindow')
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose, False)

    def closeEvent(self, event):
        self.controller.exit()
        event.accept()


class GraphFullscreenController(QtCore.QObject):
    """Own a reversible selected-graph fullscreen session for one workbench."""
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.pane = None
        self.workspace = None
        self.fullscreen_window = None
        self._snapshot = None
        self._connections = []
        self._transition = False
        self._alignment_timer = None
        self._extra_shortcuts = []
        self.refresh_timer = QtCore.QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.setInterval(16)
        self.refresh_timer.timeout.connect(self.refresh_readouts)
        self.structure_timer = QtCore.QTimer(self)
        self.structure_timer.setSingleShot(True)
        self.structure_timer.timeout.connect(self._validate_structure)
        self.action = QtGui.QAction('Fullscreen Selected Graph', self)
        self.action.setObjectName('fullscreenSelectedGraph')
        self.action.setCheckable(True)
        self.action.setShortcut('F11')
        self.action.setShortcutContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        self.action.setToolTip('Expand only the selected graph, with zoom controls and live cursor values. F11 or Esc returns to the workspace.')
        self.action.triggered.connect(self.toggle)
        window.addAction(self.action)
        self.exit_action = QtGui.QAction('Exit Fullscreen', self)
        self.exit_action.setObjectName('exitSelectedGraphFullscreen')
        self.exit_action.setToolTip('Return this graph to its original position (Esc or F11).')
        self.exit_action.triggered.connect(self.exit)
        window.installEventFilter(self)

    @property
    def is_active(self):
        return self._snapshot is not None

    def toggle(self, checked=False):
        return self.exit() if self.is_active else self.enter()

    def _connect(self, signal, slot):
        signal.connect(slot)
        self._connections.append((signal, slot))

    def _disconnect(self):
        for signal, slot in self._connections:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                # A workspace can already be scheduled for deletion during
                # shutdown.  No deferred callback may retain its detached pane.
                pass
        self._connections.clear()

    def _release_navigation(self):
        # These actions belong to the original workspace toolbar. In PySide,
        # QToolBar.clear() can destroy actions created by another toolbar's
        # addAction(text) overload even while that toolbar still uses them.
        # Removing associations individually preserves their original ownership.
        for action in tuple(self.navigation_bar.actions()):
            self.navigation_bar.removeAction(action)

    def _build_window(self):
        if self.fullscreen_window is not None:
            return
        host = self.fullscreen_window = _GraphFullscreenWindow(self)
        host.setWindowIcon(self.window.windowIcon())
        host.addAction(self.action)
        host.addAction(self.exit_action)
        body = QtWidgets.QWidget(host)
        layout = QtWidgets.QVBoxLayout(body)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        row = QtWidgets.QHBoxLayout()
        self.navigation_bar = QtWidgets.QToolBar('Fullscreen Graph Navigation', host)
        self.navigation_bar.setObjectName('fullscreenGraphNavigation')
        self.navigation_bar.setMovable(False)
        self.navigation_bar.setMinimumWidth(0)
        self.navigation_bar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed)
        row.addWidget(self.navigation_bar, 1)
        self.exit_button = QtWidgets.QToolButton(host)
        self.exit_button.setDefaultAction(self.exit_action)
        self.exit_button.setText('Exit Fullscreen (F11)')
        self.exit_button.setAccessibleName('Exit Fullscreen Graph')
        self.exit_button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        row.addWidget(self.exit_button)
        layout.addLayout(row)
        self.hover_readout = QtWidgets.QLabel('Mouse X/Y · Move over the graph to inspect values', host)
        self.hover_readout.setObjectName('fullscreenMouseReadout')
        self.hover_readout.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.hover_readout.setMinimumHeight(28)
        self.hover_readout.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed)
        self.hover_readout.setAccessibleName('Mouse X and Y values')
        layout.addWidget(self.hover_readout)
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, host)
        self.splitter.setChildrenCollapsible(False)
        self.graph_scroll = QtWidgets.QScrollArea(host)
        self.graph_scroll.setWidgetResizable(True)
        self.graph_scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.graph_scroll.setMinimumHeight(230)
        self.splitter.addWidget(self.graph_scroll)
        readout_panel = self.readout_panel = QtWidgets.QWidget(host)
        readout_layout = QtWidgets.QVBoxLayout(readout_panel)
        readout_layout.setContentsMargins(0, 2, 0, 0)
        readout_layout.setSpacing(3)
        cards = QtWidgets.QHBoxLayout()
        self.cursor_cards = []
        for index, name in enumerate(('A', 'B')):
            card = QtWidgets.QLabel(readout_panel)
            card.setObjectName('fullscreenCursor'+name)
            card.setTextFormat(QtCore.Qt.TextFormat.RichText)
            card.setStyleSheet('QLabel { color: '+CURSOR_COLORS[index]+'; background: #182033; padding: 5px; border-radius: 3px; }')
            card.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Fixed)
            card.setMinimumHeight(44)
            cards.addWidget(card, 1)
            self.cursor_cards.append(card)
        self.interval_caption = QtWidgets.QLabel(readout_panel)
        self.interval_caption.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.interval_caption.setWordWrap(True)
        self.interval_caption.setMinimumWidth(100)
        cards.addWidget(self.interval_caption)
        readout_layout.addLayout(cards)
        self.readout = QtWidgets.QTableWidget(0, 10, readout_panel)
        self.readout.setObjectName('fullscreenCursorReadout')
        self.readout.setHorizontalHeaderLabels(['Channel', 'Unit', 'A', 'B', 'Δ value', 'Min', 'Max', 'Average', 'Coverage', 'Match'])
        self.readout.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.readout.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.readout.verticalHeader().hide()
        self.readout.verticalHeader().setDefaultSectionSize(25)
        self.readout.setMinimumHeight(100)
        self.readout.setAccessibleName('Live selected graph cursor values and range statistics')
        header = self.readout.horizontalHeader()
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        for column in range(1, self.readout.columnCount()):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        readout_layout.addWidget(self.readout, 1)
        readout_panel.setMinimumHeight(160)
        self.splitter.addWidget(readout_panel)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)
        layout.addWidget(self.splitter, 1)
        host.setCentralWidget(body)

    def enter(self, pane=None):
        """Expand the same visible PlotPane, retaining its source/curve objects."""
        if pane is None:
            pane = self.window.active_workspace.active
        if self.is_active:
            if pane is self.pane:
                self.fullscreen_window.raise_()
                return self.fullscreen_window
            self.exit(restore_focus=False)
        workspace = next((item for item in self.window.workspaces if pane in item.panes), None)
        if workspace is None or pane not in workspace.visible_panes():
            raise ValueError('Select a visible graph before entering fullscreen.')
        position = workspace.grid.indexOf(pane)
        if position < 0:
            raise ValueError('The selected graph is not in its workspace layout.')
        item = workspace.grid.itemAt(position)
        self._build_window()
        original_parent = pane.parentWidget()
        placeholder = QtWidgets.QWidget(original_parent)
        placeholder.setObjectName('fullscreenGraphPlaceholder')
        placeholder.setMinimumSize(pane.minimumSize())
        placeholder.setSizePolicy(pane.sizePolicy())
        placeholder.setAccessibleName('Selected graph is open in fullscreen')
        self._snapshot = {
            'parent': original_parent, 'grid': workspace.grid,
            'position': workspace.grid.getItemPosition(position), 'alignment': item.alignment(),
            'placeholder': placeholder, 'visible': pane.isVisible(),
            'focus': QtWidgets.QApplication.focusWidget(), 'tab': self.window.tabs.currentIndex(),
            'active': workspace.active, 'layout_name': workspace.layout_name,
            'screen': pane.screen(),
            'main_geometry': QtCore.QRect(self.window.geometry()),
            'main_normal_geometry': QtCore.QRect(self.window.normalGeometry()),
            'main_docks': QtCore.QByteArray(self.window.saveState()),
            'main_window_state': self.window.windowState(),
            'minimum_size': QtCore.QSize(pane.minimumSize()),
            'maximum_size': QtCore.QSize(pane.maximumSize()),
            'canvas_padding': tuple(getattr(pane, '_canvas_padding', (0, 0))),
            'initial_readout_pending': True,
        }
        self.pane, self.workspace = pane, workspace
        self._transition = True
        try:
            # Shared-column alignment is inappropriate while this pane occupies
            # another window.  Keep numeric time links and real axes intact.
            timer = getattr(workspace, '_canvas_alignment_timer', None)
            if timer is not None:
                self._alignment_timer = (timer, timer.blockSignals(True))
                timer.stop()
            if hasattr(pane, 'set_canvas_padding'):
                pane.set_canvas_padding(0, 0)
            workspace.grid.replaceWidget(pane, placeholder)
            self.graph_scroll.setWidget(pane)
            pane.show()
            self.window.tabs.setCurrentIndex(self.window.workspaces.index(workspace))
            workspace.set_active(pane)
            self._release_navigation()
            for action in workspace.navigation_bar.actions():
                if action is not self.action:
                    self.navigation_bar.addAction(action)
                    button = self.navigation_bar.widgetForAction(action)
                    if button is not None:
                        button.setAccessibleName(action.text())
                        if not action.icon().isNull():
                            button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
            # Cursor locking and previous/next view shortcuts live in the
            # existing Plot menu rather than the header. Associate those same
            # actions with this window so their WindowShortcut context follows
            # the selected graph too; no second command implementation exists.
            plot_menu = getattr(getattr(self.window, 'studio', None), 'submenus', {}).get('Plot')
            if plot_menu is not None:
                for action in plot_menu.actions():
                    if not action.shortcut().isEmpty() and action not in self.navigation_bar.actions():
                        self.fullscreen_window.addAction(action)
                        self._extra_shortcuts.append(action)
            self._connect(workspace.measurementsChanged, self.queue_readouts)
            self._connect(pane.cursorsChanged, self.queue_readouts)
            self._connect(pane.hoverChanged, self._hover_changed)
            self._connect(workspace.activeChanged, self._keep_selected_pane)
            self._connect(self.window.tabs.currentChanged, self._keep_selected_workspace)
            if hasattr(self.window, 'stats_scope'):
                self._connect(self.window.stats_scope.currentTextChanged, self.queue_readouts)
            if hasattr(self.window, 'theme'):
                self._connect(self.window.theme.themeChanged, self.queue_readouts)
            self._connect(pane.destroyed, self._pane_destroyed)
            host = self.fullscreen_window
            host.setWindowTitle('Selected Graph — '+self.window.windowTitle())
            if hasattr(host, 'setScreen') and _alive(self._snapshot['screen']):
                host.setScreen(self._snapshot['screen'])
            app = QtWidgets.QApplication.instance()
            app.installEventFilter(self)
            self.refresh_readouts()
            host.showFullScreen()
            self.splitter.setSizes([max(350, host.height()-220), 190])
            # The window manager applies fullscreen geometry asynchronously.
            # Fit the initial value panel after that resize, instead of leaving
            # a short channel list in a large empty table. The user can still
            # resize the splitter afterwards.
            session = self._snapshot
            QtCore.QTimer.singleShot(0, self, lambda: self._fit_initial_readout(session))
            host.raise_()
            host.activateWindow()
            pane.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
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

    def _fit_initial_readout(self, session):
        if not self.is_active or self._snapshot is not session or not session['initial_readout_pending']:
            return
        host = self.fullscreen_window
        # showFullScreen() can deliver its first queued callback while the host
        # still has its ordinary size. A later native resize must fit the panel
        # using the actual screen geometry, rather than scaling an early ratio.
        if not host.isFullScreen() or host.size() != host.screen().geometry().size():
            return
        host.layout().activate()
        host.centralWidget().layout().activate()
        rows = min(6, max(1, self.readout.rowCount()))
        table_height = (self.readout.horizontalHeader().height() +
            sum(self.readout.rowHeight(row) if row < self.readout.rowCount() else
                self.readout.verticalHeader().defaultSectionSize() for row in range(rows)) +
            2*self.readout.frameWidth())
        table_minimum = max(self.readout.minimumHeight(), self.readout.minimumSizeHint().height())
        panel_minimum = max(self.readout_panel.minimumHeight(), self.readout_panel.minimumSizeHint().height())
        extra_height = self.readout_panel.layout().minimumSize().height() - table_minimum
        values_height = max(panel_minimum, min(280, table_height + extra_height))
        available = self.splitter.height() - self.splitter.handleWidth()
        graph_minimum = max(self.graph_scroll.minimumHeight(), self.graph_scroll.minimumSizeHint().height())
        session['initial_readout_pending'] = False
        self.splitter.setSizes([max(graph_minimum, available-values_height), values_height])

    def queue_readouts(self, *args):
        if self.is_active and not self.refresh_timer.isActive():
            self.refresh_timer.start()

    def _keep_selected_pane(self, pane):
        if self.is_active and not self._transition and self._structure_changed():
            self.structure_timer.start(0)
            return
        if self.is_active and not self._transition and pane is not self.pane and self.pane in self.workspace.visible_panes():
            self.workspace.set_active(self.pane)
        self.queue_readouts()

    def _keep_selected_workspace(self, index):
        if self.is_active and not self._transition:
            selected = self.window.workspaces.index(self.workspace)
            if index != selected:
                self.window.tabs.setCurrentIndex(selected)

    def _hover_changed(self, state):
        text = self.pane.hover_text if state and _alive(self.pane) else 'Mouse X/Y · Move over the graph to inspect values'
        self.hover_readout.setToolTip(text)
        self.hover_readout.setAccessibleName(text)
        width = max(100, self.hover_readout.contentsRect().width())
        lines = [self.hover_readout.fontMetrics().elidedText(line, QtCore.Qt.TextElideMode.ElideRight, width)
                 for line in text.splitlines()[:2]]
        self.hover_readout.setText('\n'.join(lines))

    def refresh_readouts(self):
        """Read source-sample endpoints, including duplicate/locked identities."""
        if not self.is_active or not _alive(self.pane):
            return
        pane = self.pane
        positions = [line.value() for line in pane.cursor_lines]
        coordinate = pane.coordinate or ('time', 'min')
        for index, card in enumerate(self.cursor_cards):
            name = ('A', 'B')[index]
            first = f'{name}  {_number(positions[index])} {coordinate[1]}'
            lock = pane.cursor_locks[index]
            second = 'Free cursor'
            full = first
            if lock and lock.get('channel') in pane.store.channels:
                channel = pane.store.channels[lock['channel']]
                value = pane.cursor_value(channel.id, index)
                reading = _number(value)+' '+(channel.unit or 'Unknown unit')
                if channel.attributes.get('actuator_binary'):
                    from app_actuators import state_text
                    reading = state_text(value)
                label = channel_label(pane.store, channel)
                full += f' · Locked to {label} = {reading} · sample {lock["index"]}'
                short = card.fontMetrics().elidedText(label, QtCore.Qt.TextElideMode.ElideMiddle,
                    max(80, card.width()-card.fontMetrics().horizontalAdvance('Locked:  = '+reading)-16))
                second = 'Locked: '+short+' = '+reading
            card.setText('<b>'+html.escape(first)+'</b><br>'+html.escape(second))
            card.setToolTip(full)
            card.setAccessibleName('Cursor '+full)
        scope = self.window.stats_scope.currentText() if hasattr(self.window, 'stats_scope') else 'Cursor interval'
        delta_label = 'Δ time' if coordinate[0] == 'time' else 'Δ X'
        self.interval_caption.setText(delta_label+' '+_number(abs(positions[1]-positions[0]))+' '+coordinate[1]+'\nStatistics: '+scope)
        # A direct empty selection is a normal state.  Its original empty-canvas
        # placeholder remains in the same pane and no orphan axes are created.
        measurements = pane.measurements() if all(channel_id in pane.store.channels for channel_id in pane.ids) else {}
        self.readout.setRowCount(len(measurements))
        self.readout.setAccessibleDescription('No channels selected' if not measurements else 'Values follow the source samples and cursor locks in this graph.')
        for row, (channel_id, interval) in enumerate(measurements.items()):
            channel = pane.store.channels[channel_id]
            stats = self.window.statistics_for_display(pane, channel_id, interval) if hasattr(self.window, 'statistics_for_display') else interval
            values = [channel_label(pane.store, channel), channel.unit or 'Unknown',
                      _number(stats['A']), _number(stats['B']), _number(stats['ΔY']),
                      _number(stats['Min']), _number(stats['Max']), _number(stats['Mean']),
                      f'{stats["Coverage"]*100:.4g}%' if math.isfinite(stats['Coverage']) else 'Unknown', '—']
            if channel.attributes.get('actuator_binary'):
                from app_actuators import state_text
                values[2:5] = [state_text(stats['A']), state_text(stats['B']), state_text(stats['A'])+' → '+state_text(stats['B'])]
                values[5:8] = [state_text(stats['Min']), state_text(stats['Max']), f'{100*stats["Mean"]:.4g}% ON' if math.isfinite(stats['Mean']) else 'Unknown']
            percent = channel.attributes.get('match_percent')
            color = match_color(percent)
            if color:
                values[9] = f'{float(percent):.1f}%'
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem(value)
                item.setData(QtCore.Qt.ItemDataRole.UserRole, channel_id)
                item.setToolTip(channel_details(pane.store, channel)+'\n'+value)
                if column in (2, 3):
                    item.setForeground(QtGui.QColor(CURSOR_COLORS[column-2]))
                    item.setBackground(QtGui.QColor('#182033'))
                elif column == 0 and channel_id in pane.curves:
                    item.setForeground(pane.curves[channel_id][1].pen.color())
                elif column == 9 and color:
                    item.setBackground(QtGui.QColor(color))
                    item.setForeground(QtGui.QColor('#101828'))
                self.readout.setItem(row, column, item)

    def _pane_destroyed(self, *args):
        # Structural changes should exit before deleting panes.  This final
        # guard cleans up a missed call without restoring an obsolete workspace.
        if self.is_active and not self._transition:
            self.exit(restore_focus=False, restore_main_state=False, preserve_workspace_layout=True)

    def _structure_changed(self):
        return (not _alive(self.pane) or self.pane not in self.workspace.panes or
                self.workspace.layout_name != self._snapshot['layout_name'] or
                self.pane.parentWidget() is not self.graph_scroll.viewport() or self.pane.isHidden())

    def _validate_structure(self):
        if self.is_active and not self._transition and self._structure_changed():
            # A direct plugin/layout call can bypass a workbench hook. Wait
            # until its mutation has finished, then respect the resulting layout
            # instead of inserting an obsolete pane into its previous grid slot.
            self.exit(restore_focus=False, restore_main_state=False, preserve_workspace_layout=True)

    def _restore_main_geometry(self, saved):
        window = self.window
        relevant = (QtCore.Qt.WindowState.WindowMaximized | QtCore.Qt.WindowState.WindowMinimized |
                    QtCore.Qt.WindowState.WindowFullScreen)
        wanted, current = saved['main_window_state'] & relevant, window.windowState() & relevant
        if current != wanted:
            window.showNormal()
            normal = saved['main_normal_geometry']
            window.setGeometry(normal if normal.isValid() else saved['main_geometry'])
            window.setWindowState(saved['main_window_state'])
        elif not wanted and window.geometry() != saved['main_geometry']:
            window.setGeometry(saved['main_geometry'])
        # Do not call restoreGeometry or reset an unchanged maximized state:
        # Qt clamps restored geometry to the screen and can overwrite the
        # original normalGeometry even though this feature never resized it.

    def exit(self, checked=False, *, restore_focus=True, restore_main_state=True, preserve_workspace_layout=False):
        """Put the original pane back in its exact slot; keep user navigation."""
        if not self.is_active or self._transition:
            return False
        self._transition = True
        saved, pane, workspace = self._snapshot, self.pane, self.workspace
        self.refresh_timer.stop()
        self.structure_timer.stop()
        self._disconnect()
        app = QtWidgets.QApplication.instance()
        app.removeEventFilter(self)
        try:
            if _alive(self.fullscreen_window):
                self.fullscreen_window.hide()
            if _alive(pane):
                explicitly_hidden = pane.isHidden()
                if self.graph_scroll.widget() is pane and pane.parentWidget() is self.graph_scroll.viewport():
                    self.graph_scroll.takeWidget()
                if pane.parentWidget() is not saved['parent']:
                    pane.setParent(saved['parent'])
                pane.setMinimumSize(saved['minimum_size'])
                pane.setMaximumSize(saved['maximum_size'])
                if hasattr(pane, 'set_canvas_padding'):
                    pane.set_canvas_padding(*saved['canvas_padding'], minimum_width=saved['minimum_size'].width())
                    pane.setMinimumSize(saved['minimum_size'])
                if _alive(saved['grid']):
                    already_placed = saved['grid'].indexOf(pane) >= 0
                    should_place = not preserve_workspace_layout or pane in workspace.visible_panes()
                    if should_place and not already_placed and saved['grid'].indexOf(saved['placeholder']) >= 0:
                        saved['grid'].replaceWidget(saved['placeholder'], pane)
                    elif should_place and not already_placed:
                        saved['grid'].addWidget(pane, *saved['position'], saved['alignment'])
                pane.setVisible((pane in workspace.visible_panes() and not explicitly_hidden)
                    if preserve_workspace_layout else saved['visible'])
            if _alive(saved['placeholder']):
                if _alive(saved['grid']):
                    saved['grid'].removeWidget(saved['placeholder'])
                saved['placeholder'].hide()
                saved['placeholder'].deleteLater()
            if self._alignment_timer is not None:
                timer, blocked = self._alignment_timer
                if _alive(timer):
                    timer.stop()
                    timer.blockSignals(blocked)
                self._alignment_timer = None
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
                if _alive(workspace) and saved['active'] in workspace.visible_panes():
                    workspace.set_active(saved['active'])
            if _alive(workspace):
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
        if obj is self.window and kind == QtCore.QEvent.Type.Close and self.is_active:
            self.exit(restore_focus=False)
        if self.is_active and kind == QtCore.QEvent.Type.Resize and obj is self.fullscreen_window:
            # Re-elide names to the actual card width after fullscreen geometry
            # or display scaling changes, keeping the locked value discoverable.
            self.queue_readouts()
            if self._snapshot['initial_readout_pending']:
                session = self._snapshot
                QtCore.QTimer.singleShot(0, self, lambda: self._fit_initial_readout(session))
        if self.is_active and not self._transition and obj is self.pane and kind in (QtCore.QEvent.Type.ParentChange, QtCore.QEvent.Type.Hide):
            self.structure_timer.start(0)
        if self.is_active and not self._transition and kind in (QtCore.QEvent.Type.ShortcutOverride, QtCore.QEvent.Type.KeyPress):
            if event.key() == QtCore.Qt.Key.Key_Escape and isinstance(obj, QtWidgets.QWidget) and obj.window() is self.fullscreen_window:
                event.accept()
                if kind == QtCore.QEvent.Type.KeyPress:
                    self.exit()
                return True
        return super().eventFilter(obj, event)

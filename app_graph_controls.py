"""Small, discoverable graph arrangement controls shared by both workspaces."""
from PySide6 import QtCore, QtGui, QtWidgets


class GraphControls(QtCore.QObject):
    """Add an empty graph directly; use its menu for orientation and arrangement.

    The controller edits viewport layout only. It neither duplicates source
    channels nor replaces the established zoom, pan or cursor actions.
    """
    def __init__(self,window):
        super().__init__(window)
        self.window=window
        self.add_action=QtGui.QAction('Add Graph',self)
        self.add_action.setObjectName('addGraph')
        self.add_action.setToolTip('Add a blank graph below the selected graph; double-click channels in Data Portal to add them here')
        self.add_action.triggered.connect(lambda:self._run('add_graph','below'))
        self.menu=QtWidgets.QMenu('Arrange Graphs',window)
        self.menu.setToolTipsVisible(True)
        self.menu.addAction(self.add_action)
        right=self.menu.addAction('Add Graph to the Right')
        right.triggered.connect(lambda:self._run('add_graph','right'))
        self.menu.addSeparator()
        self.remove_action=self.menu.addAction('Remove Selected Graph')
        self.remove_action.setToolTip('Close this graph; original channels stay in Data Portal')
        self.remove_action.triggered.connect(lambda:self._run('remove_graph'))
        self.menu.addSeparator()
        self.move_actions={}
        for direction in ('up','down','left','right'):
            action=self.menu.addAction('Move Graph '+direction.title())
            action.triggered.connect(lambda checked=False,direction=direction:self._run('move_graph',direction))
            self.move_actions[direction]=action
        self.button=QtWidgets.QToolButton(window)
        self.button.setObjectName('addGraphButton')
        self.button.setDefaultAction(self.add_action)
        self.button.setMenu(self.menu)
        self.button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.button.setAccessibleName('Add graph and arrange graphs')

    def _run(self,method,value=None):
        def edit():
            self.window.mutate()
            self.window.exit_graph_fullscreen()
            workspace=self.window.active_workspace
            if method=='move_graph':result=workspace.move_graph(direction=value)
            elif method=='add_graph':result=workspace.add_graph(value)
            else:result=workspace.remove_graph()
            self.window.sync_visibility();self.window.readouts()
            if method=='add_graph':
                self.window.show_dock('Data Portal')
                self.window.statusBar().showMessage('Blank graph added. Double-click channels in Data Portal to add them here; drag dividers to resize graphs.')
            elif method=='remove_graph':
                self.window.statusBar().showMessage('Graph removed. Source channels remain available in Data Portal.')
            return result
        return self.window.guard(edit)

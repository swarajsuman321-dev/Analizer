"""Accessible palettes, OS theme changes, and delayed tooltips."""
from PySide6 import QtCore,QtGui,QtWidgets


class ThemeController(QtCore.QObject):
    themeChanged=QtCore.Signal(bool)
    def __init__(self,app,parent=None):
        super().__init__(parent or app);self.app=app;self.mode='System';self.timer=QtCore.QTimer(self);self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.show_tip);self.target=None
        app.installEventFilter(self);app.styleHints().colorSchemeChanged.connect(self.system_changed)
        self.apply('System')

    def system_changed(self,*args):
        self.apply(self.mode)

    def apply(self,mode):
        self.mode=mode
        dark=mode=='Dark' or (mode=='System' and self.app.styleHints().colorScheme()==QtCore.Qt.ColorScheme.Dark)
        palette=QtGui.QPalette()
        values={QtGui.QPalette.ColorRole.Window:'#151b26' if dark else '#f5f7fb',
                QtGui.QPalette.ColorRole.WindowText:'#e3eaf5' if dark else '#182033',
                QtGui.QPalette.ColorRole.Base:'#202a3b' if dark else '#ffffff',
                QtGui.QPalette.ColorRole.AlternateBase:'#28354a' if dark else '#e9edf5',
                QtGui.QPalette.ColorRole.Text:'#e3eaf5' if dark else '#182033',
                QtGui.QPalette.ColorRole.Button:'#28354a' if dark else '#e5eaf3',
                QtGui.QPalette.ColorRole.ButtonText:'#e3eaf5' if dark else '#182033',
                QtGui.QPalette.ColorRole.Highlight:'#216eb5',QtGui.QPalette.ColorRole.HighlightedText:'#ffffff',
                QtGui.QPalette.ColorRole.ToolTipBase:'#fff6d5',QtGui.QPalette.ColorRole.ToolTipText:'#182033'}
        for role,color in values.items():palette.setColor(role,QtGui.QColor(color))
        self.app.setPalette(palette)
        self.app.setStyleSheet("""
            QMainWindow { font-family: 'Segoe UI', sans-serif; font-size: 10pt; }
            QToolBar { spacing: 6px; padding: 6px; border: none; }
            QToolButton { padding: 5px 8px; }
            QPushButton { padding: 5px 9px; }
            QLineEdit, QComboBox, QDoubleSpinBox { padding: 4px; }
            QDockWidget::title { padding: 7px; font-weight: 600; }
            QTreeView::item { min-height: 27px; }
            QHeaderView::section { padding: 6px; border: none; }
            QTabBar::tab { padding: 8px 18px; }
            QTableView { gridline-color: #8293a940; }
        """)
        self.themeChanged.emit(dark)

    def eventFilter(self,obj,event):
        if isinstance(obj,QtWidgets.QWidget):
            if event.type()==QtCore.QEvent.Type.Enter and obj.toolTip():
                self.target=obj;self.timer.start(2500)
            elif event.type()==QtCore.QEvent.Type.Leave and obj is self.target:
                self.timer.stop();QtWidgets.QToolTip.hideText();self.target=None
            elif event.type()==QtCore.QEvent.Type.ToolTip:
                return True
        return False

    def show_tip(self):
        if self.target is not None:
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(),self.target.toolTip(),self.target)

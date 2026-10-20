"""Shared compact form controls with keyboard-accessible detail disclosure."""
from PySide6 import QtCore, QtWidgets


class CollapsibleHelp(QtWidgets.QWidget):
    """Optional prose never participates in a collapsed form's initial size."""
    def __init__(self, text, parent=None, title='Help'):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.button = QtWidgets.QToolButton(self)
        self.button.setText('&' + title)
        self.button.setCheckable(True)
        self.button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.button.setArrowType(QtCore.Qt.ArrowType.RightArrow)
        self.button.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.button.setAccessibleName(title)
        self.button.setToolTip(f'Show or hide {title.lower()} (Alt+{title[0]})')
        self.details = QtWidgets.QLabel(text, self)
        self.details.setWordWrap(True)
        self.details.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.details.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByKeyboard |
                                             QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details.setMinimumWidth(0)
        self.details.setMaximumWidth(420)
        self.details.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Preferred)
        self.details.hide()
        layout.addWidget(self.button)
        layout.addWidget(self.details)
        self.button.toggled.connect(self._toggle)

    def _toggle(self, expanded):
        self.details.setVisible(expanded)
        self.button.setArrowType(QtCore.Qt.ArrowType.DownArrow if expanded else QtCore.Qt.ArrowType.RightArrow)
        window = self.window()
        if window.layout():
            window.layout().activate()
        window.adjustSize()
        screen = window.screen() or QtWidgets.QApplication.primaryScreen()
        if screen:
            area = screen.availableGeometry().adjusted(16, 16, -16, -16)
            window.resize(min(window.width(), area.width()), min(window.height(), area.height()))


class ElidedComboBox(QtWidgets.QComboBox):
    """A bounded selection field whose complete values stay discoverable."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizeAdjustPolicy(self.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(20)
        self.setMinimumWidth(160)
        self.setMaximumWidth(420)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        self.view().setTextElideMode(QtCore.Qt.TextElideMode.ElideMiddle)
        self.currentIndexChanged.connect(self._describe)

    def addItem(self, text, userData=None, details=None):
        super().addItem(text, userData)
        self.setItemData(self.count()-1, details or text, QtCore.Qt.ItemDataRole.ToolTipRole)
        self._describe()

    def addItems(self, texts):
        for text in texts:
            self.addItem(text)

    def _describe(self, *_):
        details = self.currentData(QtCore.Qt.ItemDataRole.ToolTipRole) or self.currentText()
        self.setToolTip(details)
        self.setAccessibleDescription(details)

    def paintEvent(self, event):
        painter = QtWidgets.QStylePainter(self)
        option = QtWidgets.QStyleOptionComboBox()
        self.initStyleOption(option)
        rect = self.style().subControlRect(QtWidgets.QStyle.ComplexControl.CC_ComboBox, option,
                                          QtWidgets.QStyle.SubControl.SC_ComboBoxEditField, self)
        option.currentText = self.fontMetrics().elidedText(option.currentText,
                                QtCore.Qt.TextElideMode.ElideMiddle, max(0, rect.width()-4))
        painter.drawComplexControl(QtWidgets.QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QtWidgets.QStyle.ControlElement.CE_ComboBoxLabel, option)


def add_help(layout, text, title='Help'):
    help_widget = CollapsibleHelp(text, title=title)
    layout.addWidget(help_widget)
    return help_widget


def choose_item(parent, title, label, items, current=0):
    """Choose a complete value without letting long values widen the dialog.

    Return the same ``(text, accepted)`` pair as Qt's item input dialog.  The
    display alone is elided: item text, keyboard selection, tooltip and returned
    value retain the complete source identity.
    """
    from app_adaptive_ui import ContentDialog
    dialog = ContentDialog(parent)
    dialog.setWindowTitle(title)
    layout = QtWidgets.QVBoxLayout(dialog)
    prompt = QtWidgets.QLabel(label)
    prompt.setWordWrap(True)
    prompt.setMinimumWidth(0)
    prompt.setMaximumWidth(420)
    prompt.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Preferred)
    field = ElidedComboBox(dialog)
    field.setAccessibleName(label.replace('&', ''))
    field.addItems([str(item) for item in items])
    if field.count():
        field.setCurrentIndex(max(0, min(int(current), field.count()-1)))
    prompt.setBuddy(field)
    layout.addWidget(prompt)
    layout.addWidget(field)
    buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.StandardButton.Ok |
                                        QtWidgets.QDialogButtonBox.StandardButton.Cancel)
    buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok).setEnabled(bool(field.count()))
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    field.setFocus()
    try:
        accepted = dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted
        return field.currentText(), accepted
    finally:
        dialog.deleteLater()

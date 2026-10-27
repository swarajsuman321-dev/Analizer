"""A wrapping interval card whose complete contents remain scrollable."""
from PySide6 import QtWidgets


class ReadoutDetailsLabel(QtWidgets.QLabel):
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self._sizing = False
        self.setWordWrap(True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,
                           QtWidgets.QSizePolicy.Policy.Minimum)

    def _fit_content(self):
        if self._sizing or self.width() <= 0:
            return
        self._sizing = True
        try:
            height = max(110, self.heightForWidth(self.width()))
            if self.minimumHeight() != height:
                self.setMinimumHeight(height)
        finally:
            self._sizing = False

    def setText(self, text):
        super().setText(text)
        self._fit_content()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_content()

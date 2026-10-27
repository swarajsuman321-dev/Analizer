"""Screen-aware Qt dialogs and self-contained high-DPI navigation artwork."""
from PySide6 import QtCore,QtGui,QtWidgets


def navigation_icon(kind, dark=False):
    """Draw each size natively, avoiding platform-theme icon dependencies."""
    icon=QtGui.QIcon()
    for size in (20,24,32,48,64):
        pix=QtGui.QPixmap(size,size);pix.fill(QtCore.Qt.GlobalColor.transparent)
        painter=QtGui.QPainter(pix);painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.scale(size/24,size/24);painter.setPen(QtGui.QPen(QtGui.QColor('#e3eaf5' if dark else '#182033'),1.8))
        if kind in ('in','out'):
            painter.drawEllipse(QtCore.QRectF(3,3,12,12));painter.drawLine(14,14,21,21);painter.drawLine(6,9,12,9)
            if kind=='in':painter.drawLine(9,6,9,12)
        elif kind=='reset':
            for x,y,sx,sy in ((3,3,1,1),(21,3,-1,1),(3,21,1,-1),(21,21,-1,-1)):
                painter.drawLine(x,y,x+sx*6,y);painter.drawLine(x,y,x,y+sy*6)
            painter.drawRect(QtCore.QRectF(8,8,8,8))
        elif kind=='fullscreen':
            for x,y,sx,sy in ((3,3,1,1),(21,3,-1,1),(3,21,1,-1),(21,21,-1,-1)):
                painter.drawLine(x,y,x+sx*6,y);painter.drawLine(x,y,x,y+sy*6)
                painter.drawLine(x,y,x+sx*7,y+sy*7)
        else:
            path=QtGui.QPainterPath();path.moveTo(8,21);path.lineTo(3,13);path.cubicTo(2,11,4,10,6,12);path.lineTo(7,13);path.lineTo(7,5);path.cubicTo(7,2,10,2,10,5);path.lineTo(10,11);path.lineTo(10,3);path.cubicTo(10,1,13,1,13,3);path.lineTo(13,11);path.lineTo(13,4);path.cubicTo(13,2,16,2,16,4);path.lineTo(16,12);path.lineTo(16,7);path.cubicTo(16,5,19,5,19,7);path.lineTo(19,16);path.lineTo(16,21);path.closeSubpath();painter.drawPath(path)
        painter.end();icon.addPixmap(pix)
    return icon


class DialogBounds(QtCore.QObject):
    """Clamp application and input dialogs on show, including high-DPI screens."""
    def eventFilter(self,obj,event):
        if isinstance(obj,QtWidgets.QDialog) and event.type()==QtCore.QEvent.Type.Show:
            screen=obj.screen() or QtWidgets.QApplication.primaryScreen()
            if screen:
                area=screen.availableGeometry().adjusted(12,12,-12,-12)
                obj.setMinimumSize(min(obj.minimumWidth(),area.width()),min(obj.minimumHeight(),area.height()))
                obj.resize(min(obj.width(),area.width()),min(obj.height(),area.height()))
                frame=obj.frameGeometry();obj.move(max(area.left(),min(frame.left(),area.right()-frame.width())),max(area.top(),min(frame.top(),area.bottom()-frame.height())))
        return super().eventFilter(obj,event)


class ContentDialog(QtWidgets.QDialog):
    """Small forms fit content; data-heavy views receive a useful resizable area."""
    def showEvent(self,event):
        if not self.property('sized'):
            self.setProperty('sized',True)
            table=bool(self.findChildren(QtWidgets.QTableView) or self.findChildren(QtWidgets.QTreeView))
            self.adjustSize()
            area=(self.screen() or QtWidgets.QApplication.primaryScreen()).availableGeometry().adjusted(16,16,-16,-16)
            if self.sizeHint().width()>area.width() or self.sizeHint().height()>area.height():
                old=self.layout();content=QtWidgets.QWidget();content.setLayout(old)
                root=QtWidgets.QVBoxLayout(self);scroll=QtWidgets.QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(content);root.addWidget(scroll)
                self.setMinimumSize(0,0)
            if table:self.resize(max(self.width(),720),max(self.height(),420))
        super().showEvent(event)
        area=(self.screen() or QtWidgets.QApplication.primaryScreen()).availableGeometry().adjusted(16,16,-16,-16)
        self.resize(min(self.width(),area.width()),min(self.height(),area.height()))

"""Run in a fresh Qt process for each scale; usable on native Windows CI."""
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6 import QtCore,QtWidgets
from app_workbench import AdvancedStudioWindow
from app_channel_store import Channel


def check():
    app=QtWidgets.QApplication([]);w=AdvancedStudioWindow();w.resize(1280,900);w.show()
    w.store.add(Channel('Power',[0,1,2],[0,100,50],unit='W',coordinate_unit='min'));w.dashboard.assign(list(w.store.channels));app.processEvents()
    for theme in ('Dark','Light'):
        w.theme.apply(theme);app.processEvents()
        for key in ('in','out','reset','pan'):
            action=w.dashboard.navigation_actions[key];pix=action.icon().pixmap(32,32)
            assert not pix.isNull() and pix.width()>=32, 'Missing zoom icon'
        for create in (w.studio.display_options,w.engineering.configure):
            dialog=create();app.processEvents();area=dialog.screen().availableGeometry()
            assert dialog.width()<=area.width() and dialog.height()<=area.height(), 'Dialog exceeds available screen'
            dialog.close();app.processEvents()
    assert not hasattr(w.dashboard,'quick_zoom_bar'), 'Duplicate navigation'
    assert w.dashboard.hover_readout.mapToGlobal(w.dashboard.hover_readout.rect().bottomLeft()).y()<w.dashboard.active.mapToGlobal(w.dashboard.active.rect().topLeft()).y()
    print(json.dumps({'scale':app.devicePixelRatio(),'screen':app.primaryScreen().availableGeometry().getRect(),'native_windows':sys.platform=='win32','themes':['Dark','Light'],'dialogs':'passed','icons':'passed'}))
    w.close();app.processEvents()


if __name__=='__main__':check()

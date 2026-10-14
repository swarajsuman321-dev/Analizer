"""Bundle smoke test for the modern frontend and its core runtime dependencies."""
def self_test():
    import tempfile
    from pathlib import Path
    import numpy as np
    from PySide6 import QtWidgets
    from app_workbench import AdvancedStudioWindow
    from app_signal_processing import transform
    from app_workspace_io import save_workspace,load_workspace,render_report
    app=QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    window=AdvancedStudioWindow();window.show()
    from app_channel_store import Channel
    x=np.linspace(0,10,1001)
    first=window.store.add(Channel('Synthetic test signal',x,np.sin(x),unit='V',attributes={'match_percent':90}))
    window.dashboard.assign([first.id]);app.processEvents()
    try:
        first=next(iter(window.store.channels.values()));fft=window.store.add(transform(first,'FFT'))
        window.dashboard.assign([fft.id]);app.processEvents()
        if window.dashboard.layout_name!='Horizontal split':raise RuntimeError('Frequency layout separation failed')
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);path=save_workspace(root/'workspace.json',window.store,[w.state() for w in window.workspaces],window.ui_state())
            restored,views,ui=load_workspace(path)
            for id,c in window.store.channels.items():np.testing.assert_array_equal(c.y,restored.channels[id].y)
            render_report(root/'report.svg',window.store,window.dashboard.state())
            if (root/'report.svg').stat().st_size<100:raise RuntimeError('SVG export failed')
            from app_reporting import export_report
            for suffix in ('pdf','png','xlsx','csv'):
                export_report(root/('report.'+suffix),window.store,window.dashboard.state())
                if (root/('report.'+suffix)).stat().st_size<100:raise RuntimeError(f'{suffix} report export failed')
        return {'qt_gui_checked':True,'channels':len(window.store.channels),'checks':['Qt startup','synthetic channel data','FFT coordinate separation','portable workspace','SVG presentation','PDF/PNG reports','interval Excel/CSV']}
    finally:window.close();app.processEvents()

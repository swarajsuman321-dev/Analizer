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
    window=AdvancedStudioWindow();window.show();window.demo();app.processEvents()
    try:
        first=next(iter(window.store.channels.values()));fft=window.store.add(transform(first,'FFT'))
        window.telemetry.assign([fft.id]);app.processEvents()
        if window.telemetry.layout_name!='Horizontal split':raise RuntimeError('Frequency layout separation failed')
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);path=save_workspace(root/'workspace.json',window.store,[w.state() for w in window.workspaces],window.ui_state())
            restored,views,ui=load_workspace(path)
            for id,c in window.store.channels.items():np.testing.assert_array_equal(c.y,restored.channels[id].y)
            render_report(root/'report.svg',window.store,window.telemetry.state())
            if (root/'report.svg').stat().st_size<100:raise RuntimeError('SVG export failed')
        return {'qt_gui_checked':True,'channels':len(window.store.channels),'checks':['Qt startup','sample telemetry','FFT coordinate separation','portable workspace','SVG presentation']}
    finally:window.close();app.processEvents()

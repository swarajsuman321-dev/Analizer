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
    first=window.store.add(Channel('Synthetic test signal',x,np.sin(x),unit='V',coordinate_unit='min',attributes={'match_percent':90}))
    window.dashboard.assign([first.id]);app.processEvents()
    try:
        if window.windowIcon().isNull() or app.windowIcon().isNull():raise RuntimeError('Application icon was not loaded')
        first=next(iter(window.store.channels.values()));fft=window.store.add(transform(first,'FFT'))
        window.dashboard.assign([fft.id]);app.processEvents()
        if window.dashboard.layout_name!='Horizontal split':raise RuntimeError('Frequency layout separation failed')
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);path=save_workspace(root/'workspace.json',window.store,[w.state() for w in window.workspaces],window.ui_state())
            restored,views,ui=load_workspace(path)
            for id,c in window.store.channels.items():np.testing.assert_array_equal(c.y,restored.channels[id].y)
            render_report(root/'report.svg',window.store,window.dashboard.state())
            if (root/'report.svg').stat().st_size<100:raise RuntimeError('SVG export failed')
            from app_version import VERSION
            if VERSION not in window.info.manuals or 'Updates' not in window.info.manual.toPlainText():raise RuntimeError('Bundled Info manual is missing')
            if window.tabs.count()!=2 or not hasattr(window,'help_action') or window.help.topics.findText('View menu and panel layout')<0:raise RuntimeError('Top-toolbar manual navigation is missing')
            if not window.info_dialog.isModal() or window.help_dialog.isModal() or window.help.parentWidget() is not window.help_dialog:raise RuntimeError('About/Help window separation failed')
            if hasattr(window.portal,'select_all') or not window.dashboard.navigation_actions:raise RuntimeError('Dataset isolation or header navigation is missing')
            import sys
            if sys.platform=='win32' and getattr(sys,'frozen',False):
                from app_lifecycle import windows_product_version,PRODUCT
                metadata=windows_product_version(sys.executable)
                if not metadata or metadata['ProductName']!=PRODUCT or metadata['FileVersion']!=VERSION+'.0':raise RuntimeError('Windows product/version metadata mismatch')
            from app_reporting import export_report
            for suffix in ('pdf','png','xlsx','csv'):
                export_report(root/('report.'+suffix),window.store,window.dashboard.state())
                if (root/('report.'+suffix)).stat().st_size<100:raise RuntimeError(f'{suffix} report export failed')
            from app_studio_state import channel_preset,export_full_workbook
            preset=channel_preset(window.store,window.dashboard,window.studio.options)
            if window.studio.apply_preset(preset)!=2:raise RuntimeError('Channel preset roundtrip failed')
            window.studio.toggle_normalized();window.studio.toggle_normalized()
            from app_extensions import PluginManager
            plugin=root/'smoke_plugin.py';plugin.write_text("def register_patch(manager):\n manager.custom_kpi_hooks.append(lambda frame:[('Rows',len(frame))])\n manager.custom_plot_hooks.append(lambda fig,axes,frame:axes[0].plot(frame.relative_minutes,frame.power))\n")
            window.studio.plugins=PluginManager(root/'extensions');window.studio.plugins.install(plugin)
            import pandas as pd
            from app_analysis_service import add_table,load_reference
            frame=pd.DataFrame({'relative_minutes':x,'power':np.sin(x)})
            add_table(window.store,'Smoke data',frame,sheet='Synchronized_Series')
            dialog=window.studio.plugin_plots();app.processEvents();dialog.close()
            export_full_workbook(root/'complete.xlsx',window.store,window.dashboard.state())
            if (root/'complete.xlsx').stat().st_size<100:raise RuntimeError('Complete workbook failed')
            from nptdms import TdmsWriter,ChannelObject
            from app_channel_store import ChannelStore
            from app_ingestion import ingest
            tdms=root/'smoke.tdms'
            with TdmsWriter(tdms) as writer:
                writer.write_segment([ChannelObject('Temperature','Time',np.array([0.,60.,120.]),properties={'unit_string':'s'}),ChannelObject('Temperature','Reading',np.array([20.,21.,22.]),properties={'unit_string':'°C'})])
            tdms_store=ChannelStore();ingest(tdms_store,tdms);tdms_channel=next(iter(tdms_store.channels.values()))
            np.testing.assert_allclose(tdms_channel.x,[0,1,2])
            if tdms_channel.unit!='°C':raise RuntimeError('Bundled TDMS reader lost engineering units')
            from app_tdms_templates import ParameterTemplates,ParameterReview
            templates=ParameterTemplates(root/'parameters.json');review=ParameterReview(templates.unknown(tdms_store),window)
            templates.save(review.entries());review.close();templates.apply(tdms_store)
            if templates.unknown(tdms_store):raise RuntimeError('Bundled TDMS template did not persist')
            window.merge_store(tdms_store);dataset_ids=list(tdms_store.datasets);window.drop_recordings(dataset_ids)
            if any(id in window.store.channels for id in tdms_store.channels):raise RuntimeError('Complete recording removal failed')
            hover_pane=window.dashboard.panes[0];positions=[line.value() for line in hover_pane.cursor_lines]
            hover_pane._mouse_hover((hover_pane.getViewBox().sceneBoundingRect().center(),))
            if hover_pane.hover_state is None:raise RuntimeError('Mouse XY hover failed')
            if hasattr(hover_pane,'hover_label') or 'Mouse X' not in window.dashboard.hover_readout.toolTip():raise RuntimeError('Mouse readout must stay outside the canvas')
            if window.dashboard.navigation_bar.parentWidget() is not window or not {'x','y','xy','pan','reset'}<=window.dashboard.navigation_actions.keys():raise RuntimeError('Header navigation controls are missing')
            if window.dashboard.quick_zoom_bar.actions()!=[window.dashboard.navigation_actions[key] for key in ('in','out','reset')]:raise RuntimeError('Shared quick zoom controls are missing')
            if [line.value() for line in hover_pane.cursor_lines]!=positions:raise RuntimeError('Hover moved measurement cursors')
            hover_pane.clear_hover()
            from PIL import Image,ImageDraw
            image=Image.new('RGB',(800,704),'white');draw=ImageDraw.Draw(image)
            draw.rectangle((50,40,750,620),outline='black',width=2);draw.line((55,250,745,250),fill=(32,32,32),width=3);image.save(root/'reference.png')
            reference=load_reference(root/'reference.png',calibration={'duration_min':10,'plot_bounds':[50,750,40,620]})
            if not reference.channels:raise RuntimeError('Image reference extraction failed')
        return {'qt_gui_checked':True,'channels':len(window.store.channels),'checks':['Qt startup','application and window icons','bundled version manual','separate About and User Manual windows','header navigation, fixed hover readout and shared quick zoom','per-file channel controls','Windows product/version identity','TDMS reader and units','TDMS parameter review and saved template','whole recording removal','mouse XY hover','synthetic channel data','FFT coordinate separation','portable workspace','SVG presentation','PDF/PNG reports','interval Excel/CSV','presets','normalized tracks','extension hooks and Qt plot','full workbook','image-reference calibration']}
    finally:window.close();app.processEvents()

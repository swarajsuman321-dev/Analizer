"""One-click workbench controls using the existing plotting/playback services."""
import time
from PySide6 import QtCore,QtGui,QtWidgets
from app_adaptive_ui import navigation_icon
from app_studio_state import recorded_phases


class PlaybackStrip(QtWidgets.QWidget):
    def __init__(self,tools,parent):
        super().__init__(parent);self.tools=tools
    def closeEvent(self,event):
        self.tools.close_playback(self);super().closeEvent(event)


class CompactControls(QtCore.QObject):
    def __init__(self,window):
        super().__init__(window);self.w=window;self.toggles={};self.focus_state=None
        bar=next(t for t in window.findChildren(QtWidgets.QToolBar) if t.objectName()=='Workbench')
        for key,text in [('show_legends','Legend'),('show_grid','Grid'),('annotate_peak','Peak Power Marker')]:
            action=bar.addAction(text);action.setCheckable(True);action.setToolTip('Show or hide '+text.lower()+' in the active workspace')
            action.toggled.connect(lambda value,k=key:self.toggle(k,value));self.toggles[key]=action
        action=bar.addAction('Playback');action.setToolTip('Show compact playback controls');action.triggered.connect(lambda:window.guard(self.playback))
        more=QtGui.QAction('More',self);more.setToolTip('Advanced tools and application preferences');more.setMenu(window.studio.menu);bar.addAction(more)
        bar.widgetForAction(more).setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        # Optional peak marker follows primary actions and can use native overflow.
        bar.removeAction(self.toggles['annotate_peak']);bar.addAction(self.toggles['annotate_peak'])
        categories={'Data':'Import / Export Utilities','Plot':'Plot Appearance / Layout','Processing':'Signal Processing / Derived Channels','Engineering':'Engineering Diagnostics','Export':'Export Utilities','Extensions':'Presets / Extensions'}
        for old,new in categories.items():window.studio.submenus[old].setTitle(new)
        manage=window.studio.menu.addMenu('Channel Management')
        for action in window.menuBar().actions():
            if action.text()=='Channel':
                for item in action.menu().actions():manage.addAction(item)
        prefs=window.studio.menu.addMenu('Application Preferences')
        self.focus_action=prefs.addAction('Focus Graph');self.focus_action.setCheckable(True);self.focus_action.setShortcut('Ctrl+Shift+F');self.focus_action.toggled.connect(self.focus)
        prefs.addAction('Restore Normal Workspace',lambda:self.focus_action.setChecked(False))
        prefs.addAction('Show Engineering Controls',lambda:window.show_dock('Engineering Controls'))
        prefs.addAction('Show Channel Math',lambda:window.show_dock('Channel Math'))
        self.strip=None
        window.theme.themeChanged.connect(self.icons);self.icons(False)
        self.sync()

    def icons(self,dark):
        for workspace in self.w.workspaces:
            for key in ('in','out','reset','pan'):
                action=workspace.navigation_actions[key];action.setIcon(navigation_icon(key,dark));action.setToolTip(action.toolTip() or action.text())
                button=workspace.navigation_bar.widgetForAction(action);button.setAccessibleName(action.text())
                button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)

    def sync(self):
        options={**self.w.studio.options,**getattr(self.w.active_workspace,'display_options',{})}
        for key,action in self.toggles.items():
            blocker=QtCore.QSignalBlocker(action);action.setChecked(options[key]);del blocker

    def toggle(self,key,value):
        workspace=self.w.active_workspace
        # Freeze the other workspace's defaults before changing the active one.
        for item in self.w.workspaces:
            if not getattr(item,'display_options',None):item.display_options=dict(self.w.studio.options)
        workspace.display_options[key]=value
        self.w.studio.apply_display([workspace],rebind=False);self.sync()

    def focus(self,enabled):
        if enabled:
            self.focus_state=self.w.saveState()
            for dock in self.w.docks.values():dock.hide()
        elif self.focus_state is not None:
            self.w.restoreState(self.focus_state);self.focus_state=None

    def restore_focus(self,state):
        normal=QtCore.QByteArray.fromBase64(state.get('normal','').encode())
        enabled=bool(state.get('enabled') and normal)
        self.focus_state=normal if enabled else None
        blocker=QtCore.QSignalBlocker(self.focus_action);self.focus_action.setChecked(enabled);del blocker

    def playback(self):
        tools=self.w.studio;tools.pause();pane=tools.pane;low,high=tools.bounds(pane)
        if self.strip is not None:self.strip.close();self.strip.deleteLater()
        workspace=self.w.active_workspace;strip=PlaybackStrip(tools,workspace);self.strip=strip
        layout=QtWidgets.QVBoxLayout(strip);layout.setContentsMargins(4,2,4,2);row=QtWidgets.QHBoxLayout();layout.addLayout(row)
        play=QtWidgets.QPushButton('Play');play.setToolTip('Play or pause cursor playback');row.addWidget(play)
        for text,direction in [('Previous Sample',-1),('Next Sample',1)]:
            button=QtWidgets.QPushButton(text);button.setToolTip('Step cursor A by one recorded sample');row.addWidget(button)
            button.clicked.connect(lambda _,d=direction:self.step(pane,d))
        speed=QtWidgets.QDoubleSpinBox();speed.setRange(.1,128);speed.setValue(getattr(workspace,'playback_speed',10));speed.setSuffix('×');speed.setToolTip('Playback speed');speed.valueChanged.connect(lambda v:setattr(workspace,'playback_speed',v));row.addWidget(speed)
        slider=QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal);slider.setRange(0,1000);slider.setToolTip('Seek recording');row.addWidget(slider,1)
        label=QtWidgets.QLabel();label.setMinimumWidth(70);row.addWidget(label)
        close=QtWidgets.QToolButton();close.setText('Close Playback');row.addWidget(close);close.clicked.connect(strip.close)
        spans=recorded_phases([self.w.store.channels[id] for id in pane.ids])
        if spans:
            details=QtWidgets.QToolButton();details.setText('Observed Phase Details');details.setCheckable(True);layout.addWidget(details)
            from app_studio_tools import PhaseStrip
            phase=PhaseStrip(spans,(low,high),strip);phase.hide();layout.addWidget(phase);details.toggled.connect(phase.setVisible);phase.seekRequested.connect(tools.seek)
        else:layout.addWidget(QtWidgets.QLabel('No recorded phase channel selected.'))
        tools.play_context={'pane':pane,'slider':slider,'speed':speed,'label':label,'button':play,'dialog':strip}
        def toggle():
            if tools.play_timer.isActive():tools.pause()
            else:tools._last_tick=time.monotonic();tools.play_timer.start();play.setText('Pause')
        play.clicked.connect(toggle);slider.valueChanged.connect(lambda v:tools.seek(low+(high-low)*v/1000))
        workspace.layout().insertWidget(1,strip);tools.seek(pane.cursor_lines[0].value());strip.show();return strip

    def step(self,pane,direction):
        import numpy as np
        channels=[self.w.store.channels[id] for id in pane.ids if len(self.w.store.channels[id].x)]
        if channels:
            x=channels[0].values()[0];point=pane.cursor_lines[0].value();index=int(np.searchsorted(x,point,side='right' if direction>0 else 'left'))
            index=index if direction>0 else index-1;self.w.studio.seek(float(x[np.clip(index,0,len(x)-1)]))

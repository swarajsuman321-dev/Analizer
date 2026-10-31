"""Linked multi-axis plotting and portable per-view state."""
from PySide6 import QtCore, QtWidgets, QtGui
import html
import numpy as np
import pyqtgraph as pg
from app_fast_plot import EnvelopeCache
from app_presentation import CURSOR_COLORS
from app_signal_processing import IntervalSummary
from app_trace_colors import channel_colors
from app_cursor_identity import nearest_index, cursor_value, locked_index, interval_statistics
from app_channel_identity import channel_label, channel_details

pg.setConfigOptions(antialias=False, background='#151b26', foreground='#e3eaf5')
COLORS=['#58b6ff','#ffb454','#79dba8','#d4a1ff','#ff8096','#e5da69','#83e1e8']
PRESET_LAYOUTS={'Single':(1,1),'Horizontal split':(1,2),'Vertical split':(2,1),'2×2':(2,2),'Stacked':(4,1),'3 stacked':(3,1),'10 panels':(10,1)}
LAYOUTS={**PRESET_LAYOUTS,**{f'{count} graphs':(count,1) for count in range(1,33)}}


class GraphHeaderNavigation(QtWidgets.QStackedWidget):
    """One native-overflow toolbar beside the graph's Analysis/Comparison tabs."""
    def __init__(self,tabs,workspaces):
        super().__init__(tabs);self.tabs=tabs;self._header_width=40;self._header_height=30;self._fitting_header=False;self._tab_style=tabs.tabBar().styleSheet();self.setObjectName('graphHeaderNavigation')
        self.setMinimumWidth(0);self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,QtWidgets.QSizePolicy.Policy.Fixed)
        for workspace in workspaces:
            workspace.layout().removeWidget(workspace.navigation_bar)
            workspace.navigation_bar.setMinimumWidth(0)
            workspace.navigation_bar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,QtWidgets.QSizePolicy.Policy.Fixed)
            self.addWidget(workspace.navigation_bar)
        tabs.tabBar().setExpanding(False);tabs.installEventFilter(self);tabs.tabBar().installEventFilter(self)
        tabs.currentChanged.connect(self.setCurrentIndex)
        self.setCurrentIndex(max(0,tabs.currentIndex()))
        tabs.setCornerWidget(self,QtCore.Qt.Corner.TopRightCorner)
        self._fit_header()

    def _fit_header(self):
        if self._fitting_header:return
        self._fitting_header=True
        try:self._fit_header_geometry()
        finally:self._fitting_header=False

    def _fit_header_geometry(self):
        # QTabWidget gives corner widgets their size hint; cap that width so a
        # long action set never steals the Analysis/Comparison tab labels.
        available=max(40,self.tabs.width()-self.tabs.tabBar().sizeHint().width()-8)
        self._header_width=available
        self.setFixedWidth(available)
        # QTabWidget lays out its frame from actual tab rectangles, not the
        # QTabBar widget's minimumHeight. Size the tabs themselves so the corner
        # toolbar cannot extend into the page. Use toolbar intrinsic height only
        # to avoid a padding/size-hint feedback loop after applying the style.
        height=max([30,*[self.widget(i).sizeHint().height() for i in range(self.count())]])
        if self.tabs.tabBar().property('navigationHeaderHeight')!=height:
            self.tabs.tabBar().setProperty('navigationHeaderHeight',height)
            self.tabs.tabBar().setStyleSheet(self._tab_style+f'\nQTabBar::tab {{ min-height: {height}px; padding-top: 0px; padding-bottom: 0px; }}')
        self._header_height=height
        self.setFixedHeight(height)
        self.tabs.tabBar().setMinimumHeight(height)
        self.updateGeometry()

    def sizeHint(self):
        # A stacked page deliberately uses Ignored width so QToolBar can
        # overflow. The corner widget must still advertise its real width:
        # otherwise QTabWidget positions a zero-width corner outside the tabs.
        return QtCore.QSize(self._header_width,self._header_height)

    def minimumSizeHint(self):return self.sizeHint()

    def eventFilter(self,obj,event):
        if event.type() in (QtCore.QEvent.Type.Resize,QtCore.QEvent.Type.Show,QtCore.QEvent.Type.FontChange):self._fit_header()
        return super().eventFilter(obj,event)


def install_graph_navigation(tabs,workspaces):
    """Mount existing actions once; shortcuts, menu state and icons survive."""
    header=GraphHeaderNavigation(tabs,workspaces)
    tabs.graph_navigation_header=header
    return header


class NavigationViewBox(pg.ViewBox):
    """Apply a plot gesture equally in screen space to every physical Y axis."""
    owner=None

    def _gesture(self,method,event,axis):
        if self.owner is None:return method(event,axis=axis)
        workspace=getattr(self.owner,'workspace',None)
        if workspace:workspace.set_active(self.owner)
        primary=self.owner.getViewBox()
        if self is not primary:
            return getattr(primary,'wheelEvent' if method.__name__=='wheelEvent' else 'mouseDragEvent')(event,axis=axis)
        before={view:list(view.viewRange()[1]) for view in self.owner.y_views()}
        self.owner.remember_view()
        method(event,axis=axis)
        self.owner.sync_y_gesture(self,before)
        self.owner.remember_view()

    def constrained_rectangle(self,rectangle):
        rectangle=QtCore.QRectF(rectangle).normalized();bounds=self.viewRect()
        x_enabled,y_enabled=self.state['mouseEnabled']
        if not x_enabled:rectangle.setLeft(bounds.left());rectangle.setRight(bounds.right())
        if not y_enabled:rectangle.setTop(bounds.top());rectangle.setBottom(bounds.bottom())
        return rectangle

    def updateScaleBox(self,p1,p2):
        rectangle=self.constrained_rectangle(self.childGroup.mapRectFromParent(QtCore.QRectF(p1,p2)))
        self.rbScaleBox.setPos(rectangle.topLeft());self.rbScaleBox.setTransform(QtGui.QTransform.fromScale(rectangle.width(),rectangle.height()));self.rbScaleBox.show()

    def showAxRect(self,rectangle,**kwargs):
        rectangle=self.constrained_rectangle(rectangle)
        x_enabled,y_enabled=self.state['mouseEnabled'];ranges={}
        if x_enabled:ranges['xRange']=(rectangle.left(),rectangle.right())
        if y_enabled:ranges['yRange']=(rectangle.top(),rectangle.bottom())
        if ranges:self.setRange(**ranges,**kwargs)
        self.sigRangeChangedManually.emit(self.state['mouseEnabled'])

    def mouseDragEvent(self,event,axis=None):self._gesture(super().mouseDragEvent,event,axis)
    def wheelEvent(self,event,axis=None):self._gesture(super().wheelEvent,event,axis)

    def raiseContextMenu(self,event):
        """Do not append framework transforms to the supported chart menu."""
        if self.owner is None:return super().raiseContextMenu(event)
        self.owner._context_position=float(self.owner.getViewBox().mapSceneToView(event.scenePos()).x())
        menu=self.owner.create_context_menu()
        menu.popup(event.screenPos().toPoint())

    def getMenu(self,event=None):
        return self.owner.create_context_menu() if self.owner else super().getMenu(event)


class PreparedCurve(pg.GraphicsObject):
    """Paint a prepared path with stable source bounds, avoiding scene churn."""
    def __init__(self,x,y,color):
        super().__init__();self.pen=pg.mkPen(color,width=1);self.path=QtGui.QPainterPath();self.xData=np.array([]);self.yData=np.array([])
        finite=y[np.isfinite(y)]
        left,right=(float(x[0]),float(x[-1])) if len(x) else (0.,1.)
        low,high=(float(finite.min()),float(finite.max())) if len(finite) else (0.,1.)
        self.bounds=((left,right),(low,high));self.rect=QtCore.QRectF(left,low,max(right-left,1e-12),max(high-low,1e-12))
    def boundingRect(self):return self.rect
    def dataBounds(self,axis,frac=1.,orthoRange=None):return self.bounds[axis]
    def paint(self,painter,option,widget=None):
        painter.setPen(self.pen);painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing,False);painter.drawPath(self.path)
    def setData(self,x,y,**kwargs):
        self.xData,self.yData=x,y
        self.path=pg.functions.arrayToQPath(x,y,connect='finite',finiteCheck=True);self.update()


class PlotPane(pg.PlotWidget):
    cursorsChanged=QtCore.Signal()
    hoverChanged=QtCore.Signal(object)
    contextRequested=QtCore.Signal(str,object)

    def __init__(self, store):
        view=NavigationViewBox();super().__init__(viewBox=view);view.owner=self
        self.store=store;self.ids=[];self.bindings={};self.axes={};self.curves={};self.cache={};self.summaries={}
        self.dark=True;self.display_budget=12000
        self._normalizing=False;self._synchronizing=False;self.normalized=False;self.normalization_bindings={};self._normalization={}
        self.show_legends=True;self.show_grid=True;self.history=[];self.history_index=-1;self._history_restoring=False
        self.coordinate=None;self.snap=True;self.cursor_mode='dual';self.cursor_locks=[None,None]
        self._canvas_padding=(0.,0.);self._axis_minimum_width=380
        self.annotations=[];self.annotation_items=[];self.cycle_boundaries=[];self.cycle_snap=False;self.comments_movable=False
        self.setMinimumSize(380,230)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.showGrid(x=True,y=True,alpha=.2)
        self.getPlotItem().hideButtons()
        self._supported_processing_only()
        self.getPlotItem().layout.setContentsMargins(0,0,0,0)
        self.getViewBox().sigResized.connect(self._resize)
        for side in ('left','right'):
            self.getAxis(side).geometryChanged.connect(self._queue_canvas_alignment)
        self.getViewBox().sigYRangeChanged.connect(self.clear_hover)
        self.getViewBox().sigXRangeChanged.connect(self._schedule)
        self.timer=QtCore.QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self._render)
        self.cursor_lines=[pg.InfiniteLine(pos=0,angle=90,movable=True,pen=pg.mkPen(color,width=2),hoverPen=pg.mkPen(color,width=3),label=name,labelOpts={'color':color,'position':.95}) for color,name in zip(CURSOR_COLORS,('A','B'))]
        self.empty_label=QtWidgets.QLabel('No channels selected',self)
        self.empty_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.empty_label.setStyleSheet('font-size:16px; color:#8293a9; background:transparent;')
        for line in self.cursor_lines:
            # Measurement handles must win hit testing over passive hover
            # crosshairs/markers, including when both share a timestamp.
            line.setZValue(1100)
            line.addMarker('v',position=.98,size=9)
            self.addItem(line,ignoreBounds=True);line.sigPositionChanged.connect(self._cursor_changed)
        self.cursor_markers=[pg.ScatterPlotItem(size=11,brush=color,pen=pg.mkPen('#182033',width=1.5)) for color in CURSOR_COLORS]
        self.marker_views=[None,None]
        for marker in self.cursor_markers:marker.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton);marker.setZValue(1000);marker.hide()
        self.scene().sigMouseClicked.connect(self._click)
        self._build_hover()
        self.legend=self.addLegend(offset=(12,12));self.legend.hide()
        # Newly added empty panes also participate in canvas alignment before
        # any channel has been bound to them.
        self._layout_axes()

    def _supported_processing_only(self):
        """Keep graphics decorations outside native numerical transforms.

        Prepared paths and scatter cursor markers are not PlotDataItem curves.
        The application's FFT service validates clocks/units and creates a
        separate frequency channel; native FFT/log/decimation menus cannot do
        this safely. Reset old framework control state and expose app routes.
        """
        plot=self.getPlotItem();plot.setMenuEnabled(False)
        controls=plot.ctrl
        for name,slot in [('fftCheck','updateSpectrumMode'),('logXCheck','updateLogMode'),
                          ('logYCheck','updateLogMode'),('derivativeCheck','updateDerivativeMode'),
                          ('phasemapCheck','updatePhasemapMode'),('subtractMeanCheck','updateSubtractMeanMode'),
                          ('downsampleCheck','updateDownsampling'),('autoDownsampleCheck','updateDownsampling'),
                          ('subsampleRadio','updateDownsampling'),('meanRadio','updateDownsampling'),
                          ('clipToViewCheck','updateDownsampling')]:
            control=getattr(controls,name,None)
            if control is None:continue
            try:control.toggled.disconnect(getattr(plot,slot))
            except (RuntimeError,TypeError):pass
            control.setEnabled(False)
            control.setToolTip('Use Calculate Channel for validated application processing.')
            def reset(checked,c=control):
                blocker=QtCore.QSignalBlocker(c);c.setChecked(False);del blocker
            control.toggled.connect(reset)
            reset(False)

    def cursor_value(self,channel_id,index):
        """Single source of truth for locked readings in every UI surface."""
        channel=self.store.channels[channel_id]
        return cursor_value(channel,self.cursor_lines[index].value(),self.snap,self.cursor_locks[index])

    def close(self):
        if self.plotItem is None:return True
        self.stop_callbacks()
        return super().close()

    def stop_callbacks(self):
        if getattr(self,'_callbacks_stopped',False):return
        self._callbacks_stopped=True
        self._closing=True;self.timer.stop();self.hover_proxy.disconnect();self.clear_hover()
        # Clear framework hover owners while PlotItem and its auto button
        # still exist. Reparenting during PlotWidget.close emits a later Leave
        # event, after that button has already been destroyed.
        self.scene().leaveEvent(QtCore.QEvent(QtCore.QEvent.Type.Leave))

    def _build_hover(self):
        pen=pg.mkPen('#8394a8',width=1,style=QtCore.Qt.PenStyle.DashLine)
        self.hover_lines=[pg.InfiniteLine(angle=90,pen=pen),pg.InfiniteLine(angle=0,pen=pen)]
        for line in self.hover_lines:
            line.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton);line.setZValue(900);self.addItem(line,ignoreBounds=True);line.hide()
        self.hover_marker=pg.ScatterPlotItem(size=9,brush=None,pen=pg.mkPen('#ffffff',width=2))
        self.hover_marker.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton);self.hover_marker.setZValue(901);self.addItem(self.hover_marker,ignoreBounds=True);self.hover_marker.hide()
        self.hover_state=None;self.hover_text=''
        # Only passive crosshairs/markers live in the canvas. Text is emitted to
        # the workspace's fixed readout strip so it never covers a trace.
        self.hover_proxy=pg.SignalProxy(self.scene().sigMouseMoved,rateLimit=30,slot=self._live_hover);self.hover_proxy.setParent(self)
        self.viewport().setMouseTracking(True)

    def clear_hover(self):
        had_state=getattr(self,'hover_state',None) is not None
        self.hover_state=None;self.hover_text=''
        if not hasattr(self,'hover_marker'):return
        for _,marker in getattr(self,'inspection_markers',{}).values():marker.hide()
        self.hover_marker.hide()
        for line in self.hover_lines:line.hide()
        if had_state:self.hoverChanged.emit(None)

    def inspect_time(self,point):
        """Mark each trace on its own value axis at a common temporal position."""
        from app_presentation import cursor_sample
        if not hasattr(self,'inspection_markers'):self.inspection_markers={}
        rows=[]
        for id,(view,curve) in self.curves.items():
            c=self.store.channels[id];x,y=c.values()
            value=cursor_sample(c,point,True)
            sample=nearest_index(x,point) if len(x) and x[0]<=point<=x[-1] else None
            if id not in self.inspection_markers:
                marker=pg.ScatterPlotItem(size=9,brush=None,pen=pg.mkPen(curve.pen.color(),width=2))
                marker.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton);marker.setZValue(902)
                view.addItem(marker,ignoreBounds=True);self.inspection_markers[id]=(view,marker)
            marker=self.inspection_markers[id][1]
            if sample is not None and np.isfinite(value):
                display=value
                if id in self._normalization:
                    low,high,offset=self._normalization[id];display=((value-low)/(high-low) if high>low else .5)+offset
                marker.setData([float(x[sample])],[display]);marker.show()
            else:marker.hide()
            rows.append({'channel':id,'name':channel_label(self.store,id),'value':float(value),
                         'sample_time':float(x[sample]) if sample is not None else None,'unit':c.unit})
        return rows

    def leaveEvent(self,event):
        self.clear_hover();super().leaveEvent(event)

    def hover_values(self,position):
        primary=self.getViewBox()
        if not self.ids or not primary.sceneBoundingRect().contains(position):return None
        point=primary.mapSceneToView(position);x=float(point.x());axes=[];nearest=None
        for unit in dict.fromkeys(self.bindings.values()):
            view=self.axes[unit][1] if unit in self.axes else primary
            axes.append({'unit':unit or 'Value','y':float(view.mapSceneToView(position).y())})
        for id,(view,curve) in self.curves.items():
            channel=self.store.channels[id];xs,ys=channel.values()
            if not len(xs) or x<xs[0] or x>xs[-1]:continue
            index=min(len(xs)-1,int(np.searchsorted(xs,x)));previous=max(0,index-1)
            if abs(xs[previous]-x)<=abs(xs[index]-x):index=previous
            value=ys[index]
            if not np.isfinite(value):continue
            display=value
            if id in self._normalization:
                low,high,offset=self._normalization[id];display=((value-low)/(high-low) if high>low else .5)+offset
            scene=view.mapViewToScene(QtCore.QPointF(float(xs[index]),float(display)))
            distance=(scene.x()-position.x())**2+(scene.y()-position.y())**2
            if nearest is None or distance<nearest['distance']:
                nearest={'channel':id,'name':channel_label(self.store,channel),'x':float(xs[index]),'y':float(value),'unit':channel.unit,'distance':distance,'scene':scene}
        return {'x':x,'coordinate_unit':self.coordinate[1] if self.coordinate else '', 'axes':axes,'nearest':nearest}

    def _live_hover(self,args):
        # SignalProxy coalesces motion. Its saved scene point can be stale by
        # callback time, and native nested viewports can have a stale underMouse
        # flag. Resolve the actual pointer and owning widget instead: this also
        # prevents late callbacks from drawing through a menu or another pane.
        viewport=self.viewport();position=QtGui.QCursor.pos()
        local=viewport.mapFromGlobal(position);owner=QtWidgets.QApplication.widgetAt(position)
        if (getattr(self,'_closing',False) or not viewport.isVisible() or
                not viewport.rect().contains(local) or owner is None or
                (owner is not viewport and not viewport.isAncestorOf(owner))):
            self.clear_hover();return
        self._mouse_hover((self.mapToScene(local),))

    def _mouse_hover(self,args):
        position=args[0];state=self.hover_values(position)
        if state is None:self.clear_hover();return
        self.hover_state=state;primary=self.getViewBox();point=primary.mapSceneToView(position)
        for line,value in zip(self.hover_lines,(point.x(),point.y())):line.setValue(value);line.show()
        text=[f"Mouse X  {state['x']:.6g} {state['coordinate_unit']}  |  Mouse Y  "+'  |  '.join(('ON/OFF track' if a['unit']=='Actuators' else f"{a['y']:.6g} {a['unit']}") for a in state['axes'])]
        nearest=state['nearest']
        if nearest:
            channel=self.store.channels[nearest['channel']]
            from app_actuators import state_text
            value=state_text(nearest['y']) if channel.attributes.get('actuator_binary') else f"{nearest['y']:.6g} {nearest['unit']}"
            text.append(f"{nearest['name']}  |  Sample  {nearest['x']:.6g} {state['coordinate_unit']}  ·  {value}")
            self.hover_marker.setPen(pg.mkPen(self.curves[nearest['channel']][1].pen.color(),width=2))
            marker=primary.mapSceneToView(nearest['scene']);self.hover_marker.setData([marker.x()],[marker.y()]);self.hover_marker.show()
        else:text.append('No sample available here');self.hover_marker.hide()
        self.hover_text='\n'.join(text)
        self.hoverChanged.emit(state)

    def _cursor_changed(self):
        if self.sender() in self.cursor_lines and not getattr(self,'_restoring_cursors',False):self._restored_positions=False
        if self._normalizing:return
        if not self._synchronizing:
            self._normalizing=True
            try:
                channels=[self.store.channels[id] for id in self.ids if id in self.store.channels and len(self.store.channels[id].x)]
                workspace=getattr(self,'workspace',None)
                shared=workspace is not None and workspace._temporal_group(self) is not None
                if shared:
                    channels=list({c.id:c for pane in workspace.visible_panes() if pane.coordinate==self.coordinate
                        for id in pane.ids if (c:=self.store.channels.get(id)) is not None and len(c.x)}.values())
                if channels:
                    left=min(c.x[0]+c.shift for c in channels);right=max(c.x[-1]+c.shift for c in channels)
                    vl,vr=self.getViewBox().viewRange()[0]
                    low,high=max(left,vl),min(right,vr)
                    if shared:low,high=left,right
                    if low>high:low,high=left,right
                    reference=channels[0].values()[0]
                    begin,end=np.searchsorted(reference,[low,high],side='left');end=np.searchsorted(reference,high,side='right')
                    candidates=reference[begin:end]
                    sender=self.sender()
                    for index,line in enumerate(self.cursor_lines):
                        if shared and sender in self.cursor_lines and sender is not line:continue
                        lock=self.cursor_locks[index]
                        if lock and lock['channel'] in self.store.channels:
                            x=self.store.channels[lock['channel']].values()[0]
                            if len(x):
                                if sender is line:
                                    lock['index']=nearest_index(x,line.value(),lock.get('index'))
                                lock['index']=int(np.clip(lock['index'],0,len(x)-1))
                                line.setValue(float(x[lock['index']]))
                                continue
                        value=float(np.clip(line.value(),low,high))
                        if self.cycle_snap and self.cycle_boundaries:
                            boundaries=np.asarray(self.cycle_boundaries)
                            choices=boundaries[(boundaries>=low)&(boundaries<=high)]
                            if len(choices):
                                line.setValue(float(choices[np.argmin(np.abs(choices-value))]));continue
                        choices=candidates
                        if shared:
                            reference_channel=next((self.store.channels[id] for id in self.ids
                                if len(self.store.channels[id].x) and self.store.channels[id].values()[0][0]<=value<=self.store.channels[id].values()[0][-1]),None)
                            if reference_channel is None:
                                reference_channel=next((c for c in channels if c.values()[0][0]<=value<=c.values()[0][-1]),None)
                            choices=reference_channel.values()[0] if reference_channel is not None else np.array([])
                        if self.snap and len(choices):
                            i=min(len(choices)-1,int(np.searchsorted(choices,value)));j=max(0,i-1)
                            value=float(choices[i] if abs(choices[i]-value)<abs(choices[j]-value) else choices[j])
                        line.setValue(value)
            finally:self._normalizing=False
        self.update_cursor_markers()
        self.cursorsChanged.emit()

    def update_cursor_markers(self):
        if not hasattr(self,'cursor_markers'):return
        for index,marker in enumerate(self.cursor_markers):
            lock=self.cursor_locks[index]
            if not lock or lock['channel'] not in self.curves or self.cursor_mode=='off':marker.hide();continue
            channel=self.store.channels[lock['channel']];x,y=channel.values()
            if not len(x):marker.hide();continue
            sample=locked_index(channel,lock)
            if sample is None:marker.hide();continue
            value=self.cursor_value(channel.id,index)
            if not np.isfinite(value):marker.hide();continue
            if lock['channel'] in self._normalization:
                low,high,offset=self._normalization[lock['channel']];value=((value-low)/(high-low) if high>low else .5)+offset
            view=self.curves[lock['channel']][0]
            if self.marker_views[index] is not view:
                if self.marker_views[index] is not None:self.marker_views[index].removeItem(marker)
                view.addItem(marker,ignoreBounds=True);self.marker_views[index]=view
            marker.setData([float(x[sample])],[float(value)]);marker.setVisible(index==0 or self.cursor_mode=='dual')

    def lock_cursor(self,index,channel_id):
        if channel_id is None:
            self.cursor_locks[index]=None
        else:
            if channel_id not in self.ids:raise ValueError('Choose a visible channel in this plot')
            x=self.store.channels[channel_id].values()[0]
            if not len(x):raise ValueError('This channel has no samples')
            point=self.cursor_lines[index].value()
            previous=locked_index(self.store.channels[channel_id],self.cursor_locks[index])
            self.cursor_locks[index]={'channel':channel_id,'index':nearest_index(x,point,previous)}
        lock=self.cursor_locks[index];name=('A','B')[index]
        self.cursor_lines[index].label.setFormat(name+(' · '+channel_label(self.store,channel_id).replace('{','{{').replace('}','}}') if lock else ''))
        self._cursor_changed()

    def step_cursor(self,index,direction):
        lock=self.cursor_locks[index]
        channel_id=lock['channel'] if lock else next((id for id in self.ids if len(self.store.channels[id].x)),None)
        if channel_id not in self.store.channels:return
        x=self.store.channels[channel_id].values()[0]
        if not len(x):return
        current=lock['index'] if lock else min(len(x)-1,int(np.searchsorted(x,self.cursor_lines[index].value())))
        target=int(np.clip(current+direction,0,len(x)-1))
        if lock:lock['index']=target
        low,high=self.getViewBox().viewRange()[0]
        if x[target]<low or x[target]>high:
            width=high-low;self.setXRange(float(x[target]-width/2),float(x[target]+width/2),padding=0)
        self.cursor_lines[index].setValue(float(x[target]));self._cursor_changed()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if getattr(self,'_closing',False):return
        self.clear_hover()
        self._compact_legend_labels()
        if hasattr(self,'empty_label'):self.empty_label.setGeometry(self.rect().adjusted(60,40,-60,-40))

    def _click(self,event):
        if event.button()!=QtCore.Qt.MouseButton.LeftButton or not self.sceneBoundingRect().contains(event.scenePos()):
            return
        point=self.getViewBox().mapSceneToView(event.scenePos()).x()
        index=1 if event.modifiers()&QtCore.Qt.KeyboardModifier.ShiftModifier and self.cursor_mode=='dual' else 0
        self.cursor_lines[index].setValue(point)

    def set_cursor_mode(self,mode):
        self.cursor_mode=mode
        for i,line in enumerate(self.cursor_lines):
            line.setVisible(bool(self.ids) and mode!='off' and (i==0 or mode=='dual'))
        self.update_cursor_markers()

    def keyPressEvent(self,event):
        if event.key() in (QtCore.Qt.Key.Key_Left,QtCore.Qt.Key.Key_Right):
            self.step_cursor(1 if event.modifiers()&QtCore.Qt.KeyboardModifier.ShiftModifier else 0,1 if event.key()==QtCore.Qt.Key.Key_Right else -1);return
        if event.key()==QtCore.Qt.Key.Key_Escape:
            workspace=getattr(self,'workspace',None)
            if workspace:workspace.set_active(self);workspace.navigate('pan')
            else:self.getViewBox().setMouseMode(pg.ViewBox.PanMode);self.getViewBox().setMouseEnabled(x=True,y=True)
            return
        if event.key()==QtCore.Qt.Key.Key_R:
            workspace=getattr(self,'workspace',None)
            if workspace:workspace.set_active(self);workspace.navigate('reset')
            else:self.fit()
            return
        if event.key()==QtCore.Qt.Key.Key_C:
            self.set_cursor_mode('off' if self.cursor_mode!='off' else 'dual');return
        if event.key()==QtCore.Qt.Key.Key_Space:
            workspace=getattr(self,'workspace',None)
            if workspace:workspace.set_active(self);workspace.navigate('pan')
            else:self.getViewBox().setMouseMode(pg.ViewBox.PanMode)
            return
        super().keyPressEvent(event)

    def create_context_menu(self):
        """Build one pane-scoped menu using the same navigation actions."""
        workspace=getattr(self,'workspace',None)
        if workspace:workspace.set_active(self)
        previous=getattr(self,'_context_menu',None)
        if previous is not None:previous.deleteLater()
        menu=QtWidgets.QMenu(self);menu.setObjectName('paneChartMenu')
        menu._submenus=[]  # Keep Python ownership of the pane's popup submenus.
        menu._submenu_actions=[]
        self._context_menu=menu  # retain the nonblocking popup until closed
        if workspace:
            for command in ('pan','cursor','xy','x','y'):
                menu.addAction(workspace.navigation_actions[command])
            graphs=menu.addMenu('Arrange Graphs');menu._submenus.append(graphs)
            graphs.addAction('Add Blank Graph',workspace.add_graph)
            graphs.addAction('Move Graph Up',lambda:workspace.move_graph(self,-1))
            graphs.addAction('Move Graph Down',lambda:workspace.move_graph(self,1))
            graphs.addAction('Graph Height…',lambda:workspace.resize_graph(self))
            remove=graphs.addAction('Remove Graph',lambda:workspace.remove_graph(self))
            remove.setEnabled(len(workspace.visible_panes())>1)
        menu.addSeparator()
        expand_all=menu.addAction('Full Screen Workspace')
        expand_all.setToolTip('Expand every graph in the current split layout (F11)')
        expand_all.triggered.connect(lambda:self.contextRequested.emit('fullscreen-workspace',self))
        expand=menu.addAction('Full Screen Graph')
        expand.setToolTip('Expand this graph with zoom controls and cursor values (Shift+F11)')
        expand.triggered.connect(lambda:self.contextRequested.emit('fullscreen',self))
        colors=menu.addMenu('Change Trace Color');colors.setEnabled(bool(self.ids))
        menu._submenus.append(colors)
        menu._submenu_actions.append(colors.menuAction())
        for channel_id in self.ids:
            if channel_id not in self.store.channels:continue
            action=colors.addAction(channel_label(self.store,channel_id))
            action.triggered.connect(lambda checked=False,id=channel_id:self.contextRequested.emit('trace-color:'+id,self))
        compare=menu.addAction('Add Graph Channels to Comparison');compare.setEnabled(bool(self.ids))
        compare.triggered.connect(lambda:self.contextRequested.emit('compare',self))
        menu.addSeparator()
        cycles=menu.addAction('Snap to Cycles');cycles.setCheckable(True);cycles.setChecked(self.cycle_snap)
        cycles.setEnabled(len(self.cycle_boundaries)>=2)
        cycles.setToolTip('Snap to reviewed cycle boundaries.' if cycles.isEnabled() else 'Configure at least two reviewed cycle boundaries before enabling cycle snapping.')
        cycles.toggled.connect(lambda checked:setattr(self,'cycle_snap',checked));menu.setToolTipsVisible(True)
        revert=menu.addAction('Revert Zoom');revert.setEnabled(self.history_index>0)
        revert.setToolTip('Restore the preceding chart view; Fit shows the full recording.')
        revert.triggered.connect(lambda:self.navigate_history(-1))
        definition=menu.addAction('Configure Cycle Boundaries…');definition.setEnabled(bool(self.coordinate and self.coordinate[0]=='time'))
        definition.setToolTip('Enter reviewed positions in this pane’s time unit; no appliance cycles are inferred.');definition.triggered.connect(self.configure_cycle_boundaries)
        menu.addSeparator()
        comments=menu.addMenu('Comments')
        menu._submenus.append(comments)
        menu._submenu_actions.append(comments.menuAction())
        add=comments.addAction('Add Annotation…');add.setEnabled(bool(self.ids));add.triggered.connect(self.add_context_annotation)
        move=comments.addAction('Move Comments');move.setCheckable(True);move.setChecked(self.comments_movable);move.setEnabled(bool(self.annotations))
        move.setToolTip('Enable dragging existing annotation lines or interval edges.');move.toggled.connect(self.set_comments_movable)
        menu.addSeparator()
        menu.addAction('Copy Chart',self.copy_chart)
        export=menu.addAction('Export Report…');export.setEnabled(bool(self.ids));export.triggered.connect(lambda:self.contextRequested.emit('export',self))
        processing=menu.addMenu('Calculate Channel')
        menu._submenus.append(processing)
        menu._submenu_actions.append(processing.menuAction())
        fft=processing.addAction('FFT — Frequency Spectrum…');fft.setEnabled(bool(self.ids) and self.coordinate is not None and self.coordinate[0]=='time')
        fft.setToolTip('Open the application FFT calculation. A supported regular time clock is required.');fft.triggered.connect(lambda:self.contextRequested.emit('fft',self))
        return menu

    def set_cycle_boundaries(self,values):
        boundaries=np.asarray(values,dtype=float)
        if boundaries.ndim!=1 or len(boundaries)<2 or not np.isfinite(boundaries).all() or np.any(np.diff(boundaries)<=0):
            raise ValueError('Cycle boundaries must contain at least two increasing finite positions in this pane’s coordinate unit')
        if not self.coordinate or self.coordinate[0]!='time':raise ValueError('Cycle snapping requires a temporal pane')
        self.cycle_boundaries=boundaries.tolist()

    def configure_cycle_boundaries(self):
        unit=self.coordinate[1] if self.coordinate else ''
        initial=', '.join(f'{value:.8g}' for value in self.cycle_boundaries)
        text,ok=QtWidgets.QInputDialog.getText(self,'Cycle Boundaries',f'Reviewed positions ({unit}), separated by commas',text=initial)
        if not ok:return
        try:self.set_cycle_boundaries([float(value.strip()) for value in text.split(',')])
        except (ValueError,TypeError) as exc:QtWidgets.QMessageBox.warning(self,'Invalid Cycle Boundaries',str(exc));return
        self.contextRequested.emit('changed',self)

    def add_context_annotation(self):
        if not self.ids:return
        guard=getattr(getattr(self,'workspace',None),'mutation_guard',None)
        if guard:
            try:guard()
            except ValueError as exc:QtWidgets.QMessageBox.information(self,'Annotation unavailable',str(exc));return
        point=getattr(self,'_context_position',self.cursor_lines[0].value())
        text,ok=QtWidgets.QInputDialog.getText(self,'Add Annotation',f'Comment at {point:.6g} {self.coordinate[1]}')
        if ok and text.strip():
            if guard:
                try:guard()
                except ValueError as exc:QtWidgets.QMessageBox.information(self,'Annotation unavailable',str(exc));return
            self.annotate('Marker',point,text=text.strip())
            self.contextRequested.emit('changed',self)

    def set_comments_movable(self,enabled):
        self.comments_movable=bool(enabled)
        for _,item in self.annotation_items:
            if hasattr(item,'setMovable'):item.setMovable(self.comments_movable)

    def copy_chart(self):
        """Copy the clicked pane, including its axes, legends and cursors."""
        QtWidgets.QApplication.clipboard().setPixmap(self.grab())

    def bind(self, ids, assignments=None, fit=True):
        ids=[id for id in ids if id in self.store.channels]
        self.clear_hover()
        for view,marker in getattr(self,'inspection_markers',{}).values():view.removeItem(marker)
        self.inspection_markers={}
        workspace=getattr(self,'workspace',None)
        shared_source=next((p for p in workspace.visible_panes() if p is not self and p.ids
            and p.coordinate in {(self.store.channels[id].coordinate_kind,self.store.channels[id].coordinate_unit) for id in ids}),None) if workspace else None
        shared_state=shared_source.state() if shared_source is not None and shared_source.coordinate[0]=='time' else None
        for index,view in enumerate(self.marker_views):
            if view is not None:view.removeItem(self.cursor_markers[index]);self.marker_views[index]=None
        coordinates={(self.store.channels[id].coordinate_kind,self.store.channels[id].coordinate_unit) for id in ids if id in self.store.channels}
        if len(coordinates)>1:raise ValueError('Different coordinate systems require separate viewports')
        saved=self.state()
        for vb,item in self.annotation_items:vb.removeItem(item)
        self.annotation_items=[]
        for item in self.curves.values():
            item[0].removeItem(item[1])
        self.curves={};self._normalization={}
        if hasattr(self,'legend'):self.legend.clear()
        for key,(axis,vb) in self.axes.items():
            self.getPlotItem().layout.removeItem(axis);self.scene().removeItem(axis);self.scene().removeItem(vb)
        self.axes={}
        self.ids=[id for id in ids if id in self.store.channels]
        for index,lock in enumerate(self.cursor_locks):
            if lock and lock['channel'] not in self.store.channels:self.cursor_locks[index]=None;self.cursor_lines[index].label.setFormat(('A','B')[index])
        self.cache={k:v for k,v in self.cache.items() if k[0] in self.ids}
        self.summaries={k:v for k,v in self.summaries.items() if k in self.ids}
        coordinates={(self.store.channels[id].coordinate_kind,self.store.channels[id].coordinate_unit) for id in self.ids}
        if len(coordinates)>1:
            raise ValueError('Different coordinate systems require separate viewports')
        self.coordinate=next(iter(coordinates),None)
        self.bindings={id:('Normalized tracks' if self.normalized else ('Actuators' if self.store.channels[id].attributes.get('actuator_binary') and (assignments or {}).get(id,self.store.channels[id].unit) in ('state','Actuators') else (assignments or {}).get(id,self.store.channels[id].unit))) for id in self.ids}
        units=list(dict.fromkeys(self.bindings.values()))
        colors=channel_colors(self.store)
        primary=self.getViewBox()
        for i,unit in enumerate(units):
            color=QtGui.QColor(COLORS[i%len(COLORS)])
            if not self.dark:color=color.darker(170)
            color=color.name()
            if i==0:
                side=self.store.channels[next(id for id in self.ids if self.bindings[id]==unit)].attributes.get('plot_style',{}).get('side','left')
                axis=self.getAxis('right' if side=='right' else 'left');axis.linkToView(primary);axis.setVisible(True);axis.setLabel(unit or 'Value',color=color);axis.setPen(color);axis.setTextPen(color)
                vb=primary
            else:
                side=self.store.channels[next(id for id in self.ids if self.bindings[id]==unit)].attributes.get('plot_style',{}).get('side','right')
                axis=pg.AxisItem('left' if side=='left' else 'right');axis.setLabel(unit or 'Value',color=color);axis.setPen(color);axis.setTextPen(color)
                axis.geometryChanged.connect(self._queue_canvas_alignment)
                vb=NavigationViewBox();vb.owner=self;vb.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton);self.scene().addItem(vb);axis.linkToView(vb)
                self.axes[unit]=(axis,vb);vb.sigYRangeChanged.connect(self.clear_hover)
            if unit=='Actuators':axis.setTicks([[(0,'OFF'),(1,'ON')]])
            else:axis.setTicks(None)
            for j,id in enumerate(id for id in self.ids if self.bindings[id]==unit):
                c=self.store.channels[id];x,y=c.values()
                color=QtGui.QColor(colors[id])
                if not self.dark:color=color.darker(170)
                style=c.attributes.get('plot_style',{})
                if style.get('color'):color=QtGui.QColor(style['color'])
                display_y=y
                if self.normalized:
                    finite=y[np.isfinite(y)];low,high=(float(finite.min()),float(finite.max())) if len(finite) else (0.,1.)
                    offset=self.ids.index(id);self._normalization[id]=(low,high,offset)
                    display_y=np.where(np.isfinite(y),(y-low)/(high-low) if high>low else .5,np.nan)+offset
                curve=PreparedCurve(x,display_y,color)
                pens={'solid':QtCore.Qt.PenStyle.SolidLine,'dash':QtCore.Qt.PenStyle.DashLine,'dot':QtCore.Qt.PenStyle.DotLine,'dashdot':QtCore.Qt.PenStyle.DashDotLine}
                curve.pen=pg.mkPen(color,width=float(style.get('width',1)),style=pens.get(style.get('style'),QtCore.Qt.PenStyle.SolidLine))
                if j==0:axis.setPen(color);axis.setTextPen(color)
                if c.unit=='min':axis.enableAutoSIPrefix(False)
                vb.addItem(curve);self.curves[id]=(vb,curve)
                if hasattr(self,'legend') and len(self.ids)<=12:
                    self.legend.addItem(pg.PlotDataItem(pen=curve.pen),channel_label(self.store,c))
                    sample,label=self.legend.items[-1]
                    label.full_channel_label=channel_label(self.store,c)
                    sample.setToolTip(channel_details(self.store,c));label.setToolTip(channel_details(self.store,c));label.item.setToolTip(channel_details(self.store,c))
                key=(id,c.revision)
                if key not in self.cache:
                    self.cache={k:v for k,v in self.cache.items() if k[0]!=id}
                    self.cache[key]=EnvelopeCache(x,y)
                    self.summaries[id]=(c.revision,IntervalSummary(c))
        self.getAxis('bottom').enableAutoSIPrefix(False if self.coordinate and self.coordinate[1]=='min' else True)
        self.setLabel('bottom',self.coordinate[0] if self.coordinate else 'Coordinate',units=self.coordinate[1] if self.coordinate else '')
        self.empty_label.setVisible(not self.ids);self.empty_label.setGeometry(self.rect().adjusted(60,40,-60,-40))
        self.getAxis('left').setVisible(bool(self.ids));self.getAxis('right').hide()
        if self.ids:
            first=self.store.channels[self.ids[0]];side=first.attributes.get('plot_style',{}).get('side','left')
            self.getAxis('left').setVisible(side!='right');self.getAxis('right').setVisible(side=='right')
        self._layout_axes();self.set_cursor_mode(self.cursor_mode)
        self._resize()
        if fit:
            self.fit()
        else:
            self.restore_ranges(saved)
        if shared_state is not None:
            previous=self._synchronizing;self._synchronizing=True
            try:
                self.cursor_locks=[dict(lock) if lock else None for lock in shared_state.get('cursor_locks',[None,None])]
                for line,value in zip(self.cursor_lines,shared_state['cursors']):line.setValue(value)
            finally:self._synchronizing=previous
            if workspace is not None:workspace._cursors(self)
        self._render()
        if hasattr(self,'legend'):
            self.legend.setLabelTextColor('#e3eaf5' if self.dark else '#182033')
            # pyqtgraph updates LabelItem.opts but leaves existing rich text unchanged.
            # Re-render the current label to apply the effective theme immediately.
            for _,label in self.legend.items:label.setText(label.text)
            self.legend.setBrush(pg.mkBrush(21,27,38,145) if self.dark else pg.mkBrush(255,255,255,170))
            self.legend.setPen(pg.mkPen('#637084',width=.5))
            self.legend.layout.setContentsMargins(4,2,4,2)
            self.legend.layout.setVerticalSpacing(0)
            self.legend.setColumnCount(max(1,min(4,(len(self.ids)+5)//6)))
            self.legend.setVisible(self.show_legends and bool(self.ids) and len(self.ids)<=12)
            self._compact_legend_labels()
        self.showGrid(x=self.show_grid,y=self.show_grid,alpha=.2)
        for unit in units:
            bounds=next((self.store.channels[id].attributes.get('plot_style',{}) for id in self.ids if self.bindings[id]==unit),{})
            low,high=bounds.get('ymin'),bounds.get('ymax')
            if not self.normalized and low not in (None,'') and high not in (None,''):
                (self.axes[unit][1] if unit in self.axes else primary).setYRange(float(low),float(high),padding=0)
        for record in self.annotations:self._annotation(record)
        self.update_cursor_markers()
        self._queue_canvas_alignment()

    def _layout_axes(self):
        plot=self.getPlotItem();layout=plot.layout
        if not hasattr(self,'_canvas_spacers'):
            self._canvas_spacers=[QtWidgets.QGraphicsWidget(plot),QtWidgets.QGraphicsWidget(plot)]
            for spacer in self._canvas_spacers:
                spacer.setSizePolicy(QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,QtWidgets.QSizePolicy.Policy.Ignored))
                spacer.setMinimumWidth(0);spacer.setPreferredWidth(0);spacer.setMaximumWidth(0)
        else:
            for spacer in self._canvas_spacers:layout.removeItem(spacer)
        left=[axis for axis,_ in self.axes.values() if axis.orientation=='left']
        right=[axis for axis,_ in self.axes.values() if axis.orientation!='left']
        central=2+len(left)
        for record in plot.axes.values():layout.removeItem(record['item'])
        layout.removeItem(plot.vb);layout.removeItem(plot.titleLabel)
        for column in range(layout.columnCount()):layout.setColumnStretchFactor(column,0)
        positions={'left':(2,central-1),'right':(2,central+1),'top':(1,central),'bottom':(3,central)}
        for name,position in positions.items():
            plot.axes[name]['pos']=position;layout.addItem(plot.axes[name]['item'],*position)
        layout.addItem(plot.vb,2,central);layout.addItem(plot.titleLabel,0,central)
        for i,axis in enumerate(left):layout.addItem(axis,2,i+1)
        for i,axis in enumerate(right):layout.addItem(axis,2,central+2+i)
        layout.addItem(self._canvas_spacers[0],2,0)
        layout.addItem(self._canvas_spacers[1],2,central+2+len(right))
        layout.setColumnStretchFactor(central,100)
        # Keep a usable drawing area even when the user explicitly overlays many axes.
        visible_axes=[record['item'] for record in plot.axes.values() if record['item'].isVisible() and record['item'].orientation in ('left','right')]+left+right
        self._axis_minimum_width=int(380+sum(max(62.,axis.width()) for axis in visible_axes)+30)
        self.setMinimumWidth(int(self._axis_minimum_width+sum(self._canvas_padding)))

    def _queue_canvas_alignment(self,*_):
        workspace=getattr(self,'workspace',None)
        if workspace is not None and not getattr(self,'_closing',False):workspace.queue_canvas_alignment()

    def canvas_gutters(self):
        """Natural axis gutters, excluding the workspace's alignment padding.

        AxisItems keep measuring their own tick labels. Measuring their rendered
        geometry also includes hidden axes, custom sides and layout spacing.
        """
        plot=self.getPlotItem();plot.layout.activate()
        view=self.getViewBox();low,high=view.viewRange()[0]
        # Use the data transform rather than the ViewBox's bounding border,
        # whose half-pixel pen allowance can differ from the drawn time edges.
        transform=self.viewportTransform()
        left=transform.map(view.mapViewToScene(QtCore.QPointF(low,0))).x()
        right=transform.map(view.mapViewToScene(QtCore.QPointF(high,0))).x()
        # Subtract the space Qt actually allocated, rather than the requested
        # constraint. Native layouts can quantize a fractional spacer size.
        padding=[transform.mapRect(spacer.sceneBoundingRect()).width()
                 for spacer in self._canvas_spacers]
        # Keep signed residuals: a native inset can leave the scene one pixel
        # wider than its viewport. Clamping that residual loses the same pixel
        # we need to align when another pane has a different viewport origin.
        return (left-padding[0],self.viewport().width()-right-padding[1])

    def set_canvas_padding(self,left,right,minimum_width=0):
        requested=(max(0.,float(left)),max(0.,float(right)))
        # Opposite panes can provide the widest left and right axes. Reserve
        # their combined gutters as well as useful canvas space; narrow windows
        # can then scroll instead of clipping tick labels or crushing the plot.
        # Geometry measurements pass through several fractional transforms.
        # Do not turn an integral logical-pixel width plus floating-point noise
        # into an extra pixel, then remove it again on the next layout pass.
        required=int(np.ceil(max(self._axis_minimum_width+sum(requested),minimum_width)-1e-6))
        if self.minimumWidth()!=required:self.setMinimumWidth(required)
        if all(abs(a-b)<.05 for a,b in zip(requested,self._canvas_padding)):return
        self._canvas_padding=requested
        for spacer,width in zip(self._canvas_spacers,requested):
            spacer.setMinimumWidth(width);spacer.setPreferredWidth(width);spacer.setMaximumWidth(width)
        self.getPlotItem().layout.invalidate()

    def y_views(self):
        return [self.getViewBox(),*[vb for axis,vb in self.axes.values()]]

    def sync_y_gesture(self,source,before):
        low,high=before[source];new_low,new_high=source.viewRange()[1]
        if high<=low or np.allclose([low,high],[new_low,new_high],rtol=0,atol=1e-12):return
        for view,(a,b) in before.items():
            if view is not source:
                view.setYRange(a+(new_low-low)/(high-low)*(b-a),a+(new_high-low)/(high-low)*(b-a),padding=0)

    def zoom_all(self,factor):
        self.remember_view();before={view:list(view.viewRange()[1]) for view in self.y_views()}
        primary=self.getViewBox();enabled=primary.state['mouseEnabled'];primary.scaleBy((factor if enabled[0] else 1.,factor if enabled[1] else 1.));self.sync_y_gesture(primary,before);self.remember_view()

    def _resize(self):
        if getattr(self,'_closing',False):return
        for axis,vb in self.axes.values():
            vb.setGeometry(self.getViewBox().sceneBoundingRect());vb.setXRange(*self.getViewBox().viewRange()[0],padding=0)
        self._compact_legend_labels()
        self._queue_canvas_alignment()

    def _compact_legend_labels(self):
        """Keep the inline legend bounded without discarding channel identity."""
        # PlotWidget.close clears plotItem before detaching its viewport, which
        # emits a final resize. Graphics callbacks must not dereference that
        # released view or its legend labels during shutdown.
        if getattr(self,'_closing',False) or self.__dict__.get('plotItem') is None:return
        if not hasattr(self,'legend') or not self.legend.items:return
        columns=max(1,self.legend.columnCount)
        available=max(100.,min(460.,self.getViewBox().width()*.55))
        width=max(24.,available/columns-38.)
        for _,label in self.legend.items:
            full=getattr(label,'full_channel_label',label.text)
            text=QtGui.QFontMetricsF(label.item.font()).elidedText(full,QtCore.Qt.TextElideMode.ElideMiddle,int(width))
            escaped=html.escape(text)
            if label.text!=escaped:label.setText(escaped)
            # LabelItem updates its minimum hint when text changes but retains
            # the old width until its parent layout runs. LegendItem measures
            # current widths, so shrink this geometry before measuring it.
            label.resize(label.minimumWidth(),label.minimumHeight())
        self.legend.updateSize()

    def _schedule(self,*args):
        if getattr(self,'_closing',False):return
        self.clear_hover()
        # Numerical copying avoids pyqtgraph's screen-edge offset when axes
        # have unequal widths. Independent Y viewboxes share the same clock.
        for _,view in self.axes.values():view.setXRange(*self.getViewBox().viewRange()[0],padding=0)
        workspace=getattr(self,'workspace',None)
        if self.ids and not getattr(self,'_restored_positions',False) and not (workspace and workspace._temporal_group(self)):
            self._cursor_changed()
        if not self.timer.isActive():
            self.timer.start(0)

    def _render(self):
        if getattr(self,'_closing',False):return
        left,right=self.getViewBox().viewRange()[0]
        budget=max(32,int(self.display_budget/max(1,len(self.ids))))
        for id,(vb,curve) in self.curves.items():
            c=self.store.channels.get(id)
            if c is None:
                continue
            x,y=self.cache[(id,c.revision)].visible(left,right,budget)
            if id in self._normalization:
                low,high,offset=self._normalization[id];y=np.where(np.isfinite(y),(y-low)/(high-low) if high>low else .5,np.nan)+offset
            if c.attributes.get('actuator_binary') and len(x)>1:x=np.repeat(x,2)[1:];y=np.repeat(y,2)[:-1]
            curve.setData(x,y,connect='finite',skipFiniteCheck=False)

    def fit(self):
        if not self.ids:
            return
        channels=[self.store.channels[id] for id in self.ids if len(self.store.channels[id].x)]
        if not channels:
            return
        self.remember_view()
        left=min(c.x[0]+c.shift for c in channels);right=max(c.x[-1]+c.shift for c in channels)
        workspace=getattr(self,'workspace',None)
        if workspace is not None and workspace._temporal_group(self) is not None:
            peers=[self.store.channels[id] for pane in workspace.visible_panes() if pane.coordinate==self.coordinate
                for id in pane.ids if len(self.store.channels[id].x)]
            left=min(c.values()[0][0] for c in peers);right=max(c.values()[0][-1] for c in peers)
        self.setXRange(left,right if right>left else left+1,padding=.02)
        for unit in dict.fromkeys(self.bindings.values()):
            values=[]
            for c in channels:
                if self.bindings[c.id]==unit:
                    y=c.values()[1];finite=y[np.isfinite(y)]
                    if len(finite):values.extend([finite.min(),finite.max()])
            vb=self.axes[unit][1] if unit in self.axes else self.getViewBox()
            if values:
                low,high=min(values),max(values);vb.setYRange(low,high if high>low else low+1,padding=.08)
        if self.normalized:self.setYRange(-.2,len(self.ids)+.2,padding=0)
        for index,(line,fraction) in enumerate(zip(self.cursor_lines,(.25,.75))):
            if not self.cursor_locks[index]:line.setValue(left+(right-left)*fraction)
        self._cursor_changed()
        self.remember_view()

    def remember_view(self):
        if self._history_restoring:return
        state={'range':self.getViewBox().viewRange(),'axes':{unit:vb.viewRange()[1] for unit,(axis,vb) in self.axes.items()}}
        if self.history and state==self.history[self.history_index]:return
        self.history=self.history[:self.history_index+1]+[state];self.history=self.history[-50:];self.history_index=len(self.history)-1

    def navigate_history(self,step):
        index=self.history_index+step
        if not 0<=index<len(self.history):return
        self._history_restoring=True
        try:self.restore_ranges(self.history[index]);self.history_index=index
        finally:self._history_restoring=False

    def measurements(self):
        a,b=[line.value() for line in self.cursor_lines]
        result={}
        for id in self.ids:
            c=self.store.channels[id]
            revision,summary=self.summaries[id]
            if revision!=c.revision:
                summary=IntervalSummary(c);self.summaries[id]=(c.revision,summary)
            from app_time_units import presentation_statistics
            result[id]=presentation_statistics(c,interval_statistics(c,summary,a,b,self.cursor_locks,self.snap))
        return result

    def annotate(self,kind,start,end=None,text='',axis=None):
        record={'kind':kind,'start':float(start),'end':float(end if end is not None else start),'text':text,'axis':axis}
        self.annotations.append(record);self._annotation(record)

    def _annotation(self,record):
        kind=record['kind'];start=record['start']
        if kind=='ROI':
            item=pg.LinearRegionItem([start,record['end']],movable=False,brush=(80,170,255,35))
        else:
            item=pg.InfiniteLine(start,angle=0 if kind=='Threshold' else 90,movable=False,
                                 pen=pg.mkPen('#cfa3ff',style=QtCore.Qt.PenStyle.DashLine),label=record['text'].replace('{','{{').replace('}','}}'))
        unit=record.get('axis');vb=self.axes[unit][1] if unit in self.axes else self.getViewBox()
        vb.addItem(item,ignoreBounds=True);self.annotation_items.append((vb,item))
        if hasattr(item,'setMovable'):item.setMovable(self.comments_movable)
        def moved():
            if kind=='ROI':record['start'],record['end']=map(float,item.getRegion())
            else:record['start']=float(item.value());record['end']=float(item.value())
            self.contextRequested.emit('changed',self)
        if kind=='ROI':item.sigRegionChangeFinished.connect(moved)
        else:item.sigPositionChangeFinished.connect(moved)

    def state(self):
        return {'ids':list(self.ids),'bindings':dict(self.bindings),'range':self.getViewBox().viewRange(),
                'axes':{unit:vb.viewRange()[1] for unit,(axis,vb) in self.axes.items()},
                'cursors':[l.value() for l in self.cursor_lines],'cursor_mode':self.cursor_mode,
                'cursor_locks':[dict(lock) if lock else None for lock in self.cursor_locks],'snap':self.snap,'annotations':list(self.annotations),'cycle_boundaries':list(self.cycle_boundaries),'cycle_snap':self.cycle_snap,'normalized':self.normalized,'normalization_bindings':self.normalization_bindings,'show_grid':self.show_grid,'show_legends':self.show_legends}

    def restore_ranges(self,state):
        # Restore serialized anchors atomically. Geometry/range notifications
        # must not clamp an offscreen saved cursor or broadcast a half-restored
        # pair into another viewport while the layout is still settling.
        self._restoring_cursors=True;self._restored_positions=True
        previous=self._synchronizing;self._synchronizing=True
        blocker=QtCore.QSignalBlocker(self)
        try:
            if 'cursor_locks' in state:
                self.cursor_locks=[dict(lock) if lock and lock.get('channel') in self.store.channels else None for lock in state['cursor_locks']]
            if 'range' in state:
                self.setXRange(*state['range'][0],padding=0);self.setYRange(*state['range'][1],padding=0)
            for unit,bounds in state.get('axes',{}).items():
                if unit in self.axes:self.axes[unit][1].setYRange(*bounds,padding=0)
            for index,(line,pos) in enumerate(zip(self.cursor_lines,state.get('cursors',[]))):
                lock=self.cursor_locks[index]
                if lock and lock['channel'] in self.store.channels:
                    x=self.store.channels[lock['channel']].values()[0]
                    sample=locked_index(self.store.channels[lock['channel']],lock)
                    if sample is not None:lock['index']=sample;pos=float(x[sample])
                line.setValue(pos)
                line.label.setFormat(('A','B')[index]+(' · '+channel_label(self.store,lock['channel']).replace('{','{{').replace('}','}}') if lock else ''))
        finally:
            self._synchronizing=previous;self._restoring_cursors=False
            del blocker
        self.update_cursor_markers()

    def restore(self,state):
        try:
            boundaries=np.asarray(state.get('cycle_boundaries',[]),dtype=float)
            self.cycle_boundaries=boundaries.tolist() if boundaries.ndim==1 and len(boundaries)>=2 and np.isfinite(boundaries).all() and np.all(np.diff(boundaries)>0) else []
        except (ValueError,TypeError):self.cycle_boundaries=[]
        self.cycle_snap=bool(state.get('cycle_snap',False) and len(self.cycle_boundaries)>=2)
        self.snap=state.get('snap',True);self.normalized=state.get('normalized',False);self.normalization_bindings=state.get('normalization_bindings',{})
        self.show_grid=state.get('show_grid',True);self.show_legends=state.get('show_legends',True)
        self.bind(state['ids'],state.get('bindings'),fit=False);self.restore_ranges(state)
        self.snap=state.get('snap',True);self.set_cursor_mode(state.get('cursor_mode','dual'))
        for vb,item in self.annotation_items:vb.removeItem(item)
        self.annotation_items=[];self.annotations=list(state.get('annotations',[]))
        for record in self.annotations:self._annotation(record)


class PlotWorkspace(QtWidgets.QWidget):
    graphStructureChanging=QtCore.Signal()
    activeChanged=QtCore.Signal(object)
    measurementsChanged=QtCore.Signal()
    contextRequested=QtCore.Signal(str,object)

    def __init__(self,store):
        super().__init__();self.store=store;self.panes=[];self.active=None;self.layout_name='Single';self._syncing=False;self._range_syncing=False;self.time_axes_locked=True;self.navigation_mode='pan';self._hover_pane=None;self.layout_proportions={}
        self._canvas_alignment_timer=QtCore.QTimer(self);self._canvas_alignment_timer.setSingleShot(True)
        self._canvas_alignment_timer.timeout.connect(self._align_canvas_gutters)
        self._canvas_alignment_running=False;self._canvas_alignment_dirty=False
        outer=QtWidgets.QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        self.scroll=QtWidgets.QScrollArea();self.scroll.setWidgetResizable(True);outer.addWidget(self.scroll)
        self.container=QtWidgets.QWidget();self.scroll.setWidget(self.container)
        self.grid=QtWidgets.QGridLayout(self.container);self.grid.setContentsMargins(0,0,0,0)
        # The main window mounts this same toolbar beside its graph tabs. A
        # standalone workspace retains a normal layout row, never an overlay.
        self.navigation_bar=QtWidgets.QToolBar('Graph Navigation',self)
        self.navigation_bar.setObjectName('graphNavigation');self.navigation_bar.setMovable(False)
        self.navigation_actions={};self.mode_group=QtGui.QActionGroup(self);self.mode_group.setExclusive(True)
        for label,command in [('Zoom X','x'),('Zoom Y','y'),('Zoom XY','xy'),('Hand / Pan','pan'),('Zoom In','in'),('Zoom Out','out'),('Reset View','reset')]:
            action=self.navigation_bar.addAction(label);action.triggered.connect(lambda checked=False,c=command:self.navigate(c));self.navigation_actions[command]=action
            if command in ('x','y','xy','pan'):
                action.setCheckable(True);self.mode_group.addAction(action)
                action.setToolTip({'x':'Box zoom in time only (Ctrl+1)','y':'Box zoom in value axes only (Ctrl+2)','xy':'Box zoom in time and values (Ctrl+3)','pan':'Drag to pan the graph (Ctrl+4)'}[command])
        self.navigation_actions['pan'].setChecked(True)
        self.navigation_actions['box']=self.navigation_actions['xy']
        cursor_action=QtGui.QAction('Cursor',self);cursor_action.setCheckable(True);self.mode_group.addAction(cursor_action)
        cursor_action.setToolTip('Inspect values with Cursor A; Shift-click positions Cursor B.');cursor_action.triggered.connect(lambda:self.navigate('cursor'));self.navigation_actions['cursor']=cursor_action
        self.time_lock_action=self.navigation_bar.addAction('Lock Time Axes');self.time_lock_action.setCheckable(True);self.time_lock_action.setChecked(True)
        self.time_lock_action.toggled.connect(self.set_time_lock)
        outer.insertWidget(0,self.navigation_bar)
        self.hover_strip=QtWidgets.QWidget(self);self.hover_strip.setObjectName('graphReadoutAndQuickZoom')
        self.hover_strip.setFixedHeight(48)
        strip_layout=QtWidgets.QHBoxLayout(self.hover_strip);strip_layout.setContentsMargins(0,0,4,0);strip_layout.setSpacing(4)
        self.hover_readout=QtWidgets.QLabel('Mouse X/Y · Move over a graph to inspect values',self.hover_strip)
        self.hover_readout.setObjectName('mouseXYReadout');self.hover_readout.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        self.hover_readout.setFixedHeight(48);self.hover_readout.setContentsMargins(8,2,8,2)
        self.hover_readout.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored,QtWidgets.QSizePolicy.Policy.Fixed)
        strip_layout.addWidget(self.hover_readout,1)
        outer.insertWidget(1,self.hover_strip)
        self.channel_legend=QtWidgets.QListWidget(self);self.channel_legend.setObjectName('compactChannelLegend')
        self.channel_legend.setViewMode(QtWidgets.QListView.ViewMode.IconMode);self.channel_legend.setMovement(QtWidgets.QListView.Movement.Static)
        self.channel_legend.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust);self.channel_legend.setMaximumHeight(70)
        self.channel_legend.setToolTip('Active graph channels · scroll to inspect all legend entries');self.channel_legend.hide()
        outer.insertWidget(1,self.channel_legend)
        self.activeChanged.connect(lambda *_:self.update_channel_legend());self.measurementsChanged.connect(self.update_channel_legend)
        self.set_layout('Single')

    def update_channel_legend(self):
        if not hasattr(self,'channel_legend') or self.active is None:return
        pane=self.active;visible=pane.show_legends and len(pane.ids)>12
        self.channel_legend.setVisible(visible)
        signature=tuple((id,pane.curves[id][1].pen.color().name(),channel_label(self.store,id)) for id in pane.ids if id in pane.curves and id in self.store.channels)
        if signature==getattr(self,'_legend_signature',None):return
        self._legend_signature=signature;self.channel_legend.clear()
        for id,color,name in signature:
            item=QtWidgets.QListWidgetItem('━ '+name);item.setForeground(QtGui.QColor(color));item.setToolTip(channel_details(self.store,id));self.channel_legend.addItem(item)

    def _hover_changed(self,pane,state):
        if state is None and pane is not self._hover_pane:return
        self._hover_pane=pane if state else None
        text=pane.hover_text if state else 'Mouse X/Y · Move over a graph to inspect values'
        if state and self._temporal_group(pane) is not None:
            values=[]
            for target in self.visible_panes():
                if target.coordinate!=pane.coordinate:continue
                for row in target.inspect_time(state['x']):
                    reading=f"{row['value']:.6g} {row['unit']}" if np.isfinite(row['value']) else 'Unknown'
                    if row['sample_time'] is not None:reading+=f" @ {row['sample_time']:.6g} {state['coordinate_unit']}"
                    values.append(row['name']+': '+reading)
            if values:text+='\n'+' | '.join(values)
        elif state is None:
            for target in self.visible_panes():
                for _,marker in getattr(target,'inspection_markers',{}).values():marker.hide()
        self.hover_readout.setToolTip(text)
        width=max(0,self.hover_readout.contentsRect().width())
        lines=text.splitlines()
        if state and self.hover_readout.fontMetrics().horizontalAdvance(lines[0])>width:
            # Keep both coordinates legible before shortening trace details.
            # The tooltip always retains the original precision and wording.
            values=' | '.join('ON/OFF' if a['unit']=='Actuators' else f"{a['y']:.4g} {a['unit']}" for a in state['axes'])
            lines[0]=f"X {state['x']:.4g} {state['coordinate_unit']} | Y {values}"
        self.hover_readout.setText('\n'.join(self.hover_readout.fontMetrics().elidedText(line,QtCore.Qt.TextElideMode.ElideRight,width) for line in lines))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.queue_canvas_alignment()
        # Leave room for coordinates even with both sidebars open. QToolBar
        # exposes its existing overflow menu when the center column is narrow.
        if self._hover_pane:self._hover_changed(self._hover_pane,self._hover_pane.hover_state)

    def navigate(self,command,factor=None):
        """Scale synchronized X once, and every independent Y axis once."""
        active=self.active
        if active is None:return
        targets=[p for p in self.visible_panes() if p is active or (self.time_axes_locked and self._temporal_group(active)==self._temporal_group(p) and self._temporal_group(active) is not None)]
        if command in ('x','y','xy','box','pan','cursor'):
            self.navigation_mode='xy' if command=='box' else command
            self.navigation_actions[self.navigation_mode].setChecked(True)
            for pane in self.visible_panes():
                view=pane.getViewBox();view.setMouseMode(view.PanMode if command in ('pan','cursor') else view.RectMode)
                view.setMouseEnabled(x=command not in ('y','cursor'),y=command not in ('x','cursor'))
                if command=='cursor' and pane.cursor_mode=='off':pane.set_cursor_mode('dual')
        elif command=='reset':
            for pane in targets:pane.fit()
            channels=[self.store.channels[id] for pane in targets for id in pane.ids if len(self.store.channels[id].x)]
            if channels:active.setXRange(min(c.values()[0][0] for c in channels),max(c.values()[0][-1] for c in channels),padding=.02)
        elif command in ('in','out'):
            factor=factor if factor is not None else (.8 if command=='in' else 1.25)
            active.zoom_all(factor)
            if active.getViewBox().state['mouseEnabled'][1]:
                for pane in targets:
                    if pane is active:continue
                    pane.remember_view()
                    for view in pane.y_views():view.scaleBy(y=factor)
                    pane.remember_view()
        self.measurementsChanged.emit()

    def set_time_lock(self,locked):
        self.time_axes_locked=bool(locked)
        blocker=QtCore.QSignalBlocker(self.time_lock_action);self.time_lock_action.setChecked(self.time_axes_locked);del blocker
        self.link()

    def set_active(self,pane):
        if pane not in self.visible_panes():return
        if self.active is not pane:self.active=pane;self.activeChanged.emit(pane)

    @staticmethod
    def _temporal_group(pane):
        return pane.coordinate if pane.coordinate and pane.coordinate[0]=='time' else None

    def _time_range_changed(self,pane,bounds):
        """Synchronize numbers, never screen edges or source timestamps."""
        if self._range_syncing or pane not in self.visible_panes():return
        group=self._temporal_group(pane)
        if group is None or not np.isfinite(bounds).all():return
        self._range_syncing=True
        try:
            for target in self.visible_panes():
                if target is not pane and self._temporal_group(target)==group:
                    source_datasets={self.store.channels[id].dataset_id for id in pane.ids if self.store.channels[id].dataset_id}
                    target_datasets={self.store.channels[id].dataset_id for id in target.ids if self.store.channels[id].dataset_id}
                    if not self.time_axes_locked and not source_datasets.intersection(target_datasets):continue
                    target.setXRange(float(bounds[0]),float(bounds[1]),padding=0)
        finally:self._range_syncing=False

    def set_pane_proportions(self,rows=None,columns=None):
        """Retain explicit layout weights without reusing stale grid rows."""
        height,width=LAYOUTS[self.layout_name];saved=self.layout_proportions.setdefault(self.layout_name,{})
        for name,values,count in [('rows',rows,height),('columns',columns,width)]:
            if values is not None:
                if len(values)!=count or any(not np.isfinite(v) or v<=0 for v in values):raise ValueError('Pane proportions must be finite positive weights for every visible row/column')
                saved[name]=list(map(float,values))
        self._apply_proportions()

    def queue_canvas_alignment(self):
        """Coalesce axis/font/layout changes into a single geometry pass."""
        if getattr(self,'_closed',False):return
        if self._canvas_alignment_running:
            self._canvas_alignment_dirty=True
            return
        # Wait for one frame's axis/viewport resize events to settle. Reposting
        # a zero-time timer from those events can starve native Qt layouts.
        if not self._canvas_alignment_timer.isActive():self._canvas_alignment_timer.start(16)

    def _align_canvas_gutters(self):
        """Align drawing edges within each grid column without changing ranges.

        A synchronized time interval must also occupy the same screen width.
        Padding only the missing gutter keeps each real axis fully automatic;
        this does not introduce geometry-dependent X linking or fixed tick widths.
        """
        if getattr(self,'_closed',False):return
        if self._canvas_alignment_running:
            self._canvas_alignment_dirty=True
            return
        self._canvas_alignment_running=True;self._canvas_alignment_dirty=False
        try:
            _,columns=LAYOUTS[self.layout_name];groups={}
            for index,pane in enumerate(self.visible_panes()):
                if (getattr(pane,'_closing',False) or pane.__dict__.get('plotItem') is None
                        or self.grid.indexOf(pane)<0):continue
                groups.setdefault(index%columns,[]).append(pane)
            for panes in groups.values():
                margins=[pane.canvas_gutters() for pane in panes]
                if len(panes)==1:
                    panes[0].set_canvas_padding(0,0,380+sum(margins[0]));continue
                # Different native viewport insets can leave equal-width plot
                # widgets with unequal viewport origins or widths. Equal local
                # gutters then still draw the same time one pixel apart. Align
                # the actual drawing intersection in their shared screen space.
                origins=[pane.viewport().mapToGlobal(QtCore.QPoint()).x() for pane in panes]
                edges=[(origin+left,origin+pane.viewport().width()-right)
                       for pane,origin,(left,right) in zip(panes,origins,margins)]
                left=max(edge[0] for edge in edges);right=min(edge[1] for edge in edges)
                for pane,(own_left,own_right),(edge_left,edge_right) in zip(panes,margins,edges):
                    padding=(left-edge_left,edge_right-right)
                    frame=pane.width()-pane.viewport().width()
                    pane.set_canvas_padding(*padding,minimum_width=380+own_left+own_right+sum(padding)+frame)
        finally:
            self._canvas_alignment_running=False
            if self._canvas_alignment_dirty and not self._canvas_alignment_timer.isActive():
                self._canvas_alignment_timer.start(16)

    def _apply_proportions(self):
        rows,cols=LAYOUTS[self.layout_name];saved=self.layout_proportions.get(self.layout_name,{})
        for row in range(max(self.grid.rowCount(),rows)):
            weights=saved.get('rows',[]);weight=weights[row] if row<len(weights) else 1
            self.grid.setRowStretch(row,max(1,int(weight*100)) if row<rows else 0)
            self.grid.setRowMinimumHeight(row,230 if row<rows else 0)
        for col in range(max(self.grid.columnCount(),cols)):
            weights=saved.get('columns',[]);weight=weights[col] if col<len(weights) else 1
            self.grid.setColumnStretch(col,max(1,int(weight*100)) if col<cols else 0)
            self.grid.setColumnMinimumWidth(col,380 if col<cols else 0)

    def set_layout(self,name):
        rows,cols=LAYOUTS[name];required=rows*cols
        previous=self.active
        for pane in self.panes:self.grid.removeWidget(pane)
        while len(self.panes)<required:
            self.panes.append(self._new_pane())
        for i,pane in enumerate(self.panes):
            pane.dark=self.panes[0].dark;pane.setBackground(self.panes[0].backgroundBrush())
            pane.getAxis('bottom').setTextPen('#e3eaf5' if pane.dark else '#182033')
            pane.snap=self.active.snap if self.active else True
            pane.set_cursor_mode(self.active.cursor_mode if self.active else 'dual')
            pane.setMinimumHeight(230)
            pane.display_budget=12000/required
            if i<required:self.grid.addWidget(pane,i//cols,i%cols)
            # Reparenting into a visible layout hides newly created widgets.
            pane.setVisible(i<required)
        self.layout_name=name;self._apply_proportions();self.active=previous if previous in self.visible_panes() else self.panes[0];self.activeChanged.emit(self.active)
        self.navigate(self.navigation_mode);self.link()
        self.queue_canvas_alignment()

    def _new_pane(self):
        pane=PlotPane(self.store);pane.installEventFilter(self);pane.workspace=self
        pane.hoverChanged.connect(lambda state,p=pane:self._hover_changed(p,state))
        pane.cursorsChanged.connect(lambda p=pane:self._cursors(p))
        pane.getViewBox().sigXRangeChanged.connect(lambda view,bounds,p=pane:self._time_range_changed(p,bounds))
        pane.contextRequested.connect(self.contextRequested)
        return pane

    def closeEvent(self,event):
        self._closed=True
        self._canvas_alignment_timer.stop()
        for pane in self.panes:pane.stop_callbacks()
        super().closeEvent(event)

    def add_graph(self):
        count=len(self.visible_panes())
        if len(self.panes)>=32:raise ValueError('This workspace supports up to 32 graphs including retained layouts; use another workspace for more.')
        self.graphStructureChanging.emit()
        pane=self._new_pane();self.panes.insert(count,pane)
        self.set_layout(f'{count+1} graphs');self.set_active(pane)
        self.measurementsChanged.emit()
        return pane

    def remove_graph(self,pane=None):
        pane=pane or self.active;count=len(self.visible_panes())
        if pane not in self.visible_panes() or count<=1:return
        self.graphStructureChanging.emit()
        self.grid.removeWidget(pane);self.panes.remove(pane)
        pane.close();pane.deleteLater()
        self.set_layout(f'{count-1} graphs');self.measurementsChanged.emit()

    def move_graph(self,pane,step):
        if pane not in self.visible_panes():return
        index=self.panes.index(pane);target=index+step
        if not 0<=target<len(self.visible_panes()):return
        self.graphStructureChanging.emit()
        self.panes[index],self.panes[target]=self.panes[target],self.panes[index]
        self.set_layout(self.layout_name);self.set_active(pane)

    def resize_graph(self,pane):
        if pane not in self.visible_panes():return
        rows,cols=LAYOUTS[self.layout_name]
        weights=list(self.layout_proportions.get(self.layout_name,{}).get('rows',[1.]*rows))
        row=self.panes.index(pane)//cols
        value,accepted=QtWidgets.QInputDialog.getDouble(self,'Graph Height','Relative height for this graph row',weights[row],.1,20.,2)
        if accepted:
            weights[row]=value;self.set_pane_proportions(rows=weights)

    def eventFilter(self,obj,event):
        if event.type()==QtCore.QEvent.Type.FocusIn and obj in self.panes:
            self.set_active(obj)
        return super().eventFilter(obj,event)

    def link(self):
        # Explicit numerical propagation is stable across unequal axis widths,
        # scroll positions and DPI. setXLink aligns scene pixels and can silently
        # change a requested 40–80 interval to 40.7463–80 on a narrower pane.
        groups={}
        for pane in self.visible_panes():
            pane.setXLink(None)
            group=self._temporal_group(pane)
            if group is not None:groups.setdefault(group,[]).append(pane)
        for panes in groups.values():
            source=self.active if self.active in panes else panes[0]
            self._time_range_changed(source,source.getViewBox().viewRange()[0])
            self._cursors(source)

    def visible_panes(self):
        rows,cols=LAYOUTS[self.layout_name]
        return self.panes[:rows*cols]

    def measurement_rows(self):
        """A shared time readout with the owning pane retained for each channel."""
        if self.active is None:return {}
        panes=[self.active]
        if self._temporal_group(self.active) is not None:
            panes += [p for p in self.visible_panes() if p is not self.active and p.coordinate==self.active.coordinate]
        result={}
        for pane in panes:
            for id,stats in pane.measurements().items():result.setdefault(id,(pane,stats))
        return result

    def _cursors(self,pane):
        if self._syncing:return
        self._syncing=True
        try:
            for target in self.visible_panes():
                if target is not pane and target.coordinate==pane.coordinate and self._temporal_group(pane) is not None:
                    target.cursor_locks=[dict(lock) if lock and lock['channel'] in self.store.channels else None for lock in pane.cursor_locks]
                    for index,lock in enumerate(target.cursor_locks):
                        target.cursor_lines[index].label.setFormat(('A','B')[index]+(' · '+channel_label(self.store,lock['channel']).replace('{','{{').replace('}','}}') if lock else ''))
                    target._synchronizing=True
                    try:
                        for a,b in zip(target.cursor_lines,pane.cursor_lines):a.setValue(b.value())
                    finally:target._synchronizing=False
                    target.update_cursor_markers()
            self.measurementsChanged.emit()
        finally:self._syncing=False

    def assign(self,ids,replace=False):
        groups={}
        for id in ids:
            c=self.store.channels[id];groups.setdefault((c.coordinate_kind,c.coordinate_unit),[]).append(id)
        target=self.active
        for coordinate,channels in groups.items():
            if target.ids and target.coordinate!=coordinate:
                target=next((p for p in self.visible_panes() if p.coordinate==coordinate or not p.ids),None)
                if target is None:
                    if self.layout_name=='Single':self.set_layout('Horizontal split')
                    elif len(self.visible_panes())<4:self.set_layout('2×2')
                    target=next((p for p in self.visible_panes() if not p.ids),None)
                if target is None:raise ValueError('All viewports have incompatible coordinates; clear a viewport first')
            new=channels if replace else list(dict.fromkeys(target.ids+channels))
            target.bind(new,target.bindings,fit=True)
        self.activeChanged.emit(self.active)
        self.link();self.measurementsChanged.emit()

    def arrange_readable(self,max_units=3):
        """Group crowded overlays into full-width plots, retaining original channels."""
        groups={}
        for pane in self.visible_panes():
            for id in pane.ids:
                c=self.store.channels[id];groups.setdefault((c.coordinate_kind,c.coordinate_unit),{}).setdefault('Actuators' if c.attributes.get('actuator_binary') else c.unit,[])
                key='Actuators' if c.attributes.get('actuator_binary') else c.unit
                if id not in groups[(c.coordinate_kind,c.coordinate_unit)][key]:groups[(c.coordinate_kind,c.coordinate_unit)][key].append(id)
        chunks=[]
        for units in groups.values():
            entries=list(units.values())
            for start in range(0,len(entries),max_units):chunks.append([id for group in entries[start:start+max_units] for id in group])
        if not chunks:return
        if len(chunks)>10:return
        layout='Single' if len(chunks)==1 else 'Vertical split' if len(chunks)==2 else '3 stacked' if len(chunks)==3 else 'Stacked' if len(chunks)==4 else '10 panels'
        self.set_layout(layout)
        for i,pane in enumerate(self.panes):pane.bind(chunks[i] if i<len(chunks) else [])
        self.link();self.measurementsChanged.emit()

    def set_visible(self,ids,visible):
        if visible:
            saved=[(pane,pane.state()) for pane in self.visible_panes() if pane.ids]
            self.assign(ids)
            for pane,state in saved:pane.restore_ranges(state)
            self.measurementsChanged.emit()
        else:
            for pane in self.panes:
                for index,lock in enumerate(pane.cursor_locks):
                    if lock and lock['channel'] in ids:pane.cursor_locks[index]=None;pane.cursor_lines[index].label.setFormat(('A','B')[index])
            for pane in self.panes:pane.bind([id for id in pane.ids if id not in ids],pane.bindings,fit=False)
            self.link();self.measurementsChanged.emit()

    def refresh(self):
        for pane in self.panes:
            pane.bind(pane.ids,pane.bindings,fit=False)
        self.link()

    def state(self):
        return {'time_axes_locked':self.time_axes_locked,'navigation_mode':self.navigation_mode,'layout_proportions':self.layout_proportions,'statistics_scope':getattr(self,'statistics_scope','Cursor interval'),'layout':self.layout_name,'panes':[p.state() for p in self.panes],
                'display_options':getattr(self,'display_options',{}),'playback_speed':getattr(self,'playback_speed',10),'active':self.panes.index(self.active)}

    def restore(self,state):
        self.layout_proportions=dict(state.get('layout_proportions',{}))
        self.display_options=dict(state.get('display_options',{}));self.playback_speed=float(np.clip(state.get('playback_speed',10),.1,128))
        mode=state.get('navigation_mode','pan');self.navigation_mode=mode if mode in ('x','y','xy','pan','cursor') else 'pan'
        if self._hover_pane:self._hover_changed(self._hover_pane,None)
        self.time_axes_locked=bool(state.get('time_axes_locked',True))
        blocker=QtCore.QSignalBlocker(self.time_lock_action);self.time_lock_action.setChecked(self.time_axes_locked);del blocker
        self.statistics_scope=state.get('statistics_scope','Cursor interval')
        # Restoring into fresh panes avoids stale channel bindings.
        self._canvas_alignment_timer.stop()
        for pane in self.panes:
            self.grid.removeWidget(pane);pane.stop_callbacks();pane.deleteLater()
        self.panes=[]
        required=max(len(state['panes']),LAYOUTS[state['layout']][0]*LAYOUTS[state['layout']][1])
        if required>32:raise ValueError('Workspace exceeds the 32 graph limit')
        if required>LAYOUTS[state['layout']][0]*LAYOUTS[state['layout']][1]:self.set_layout(f'{required} graphs')
        self.set_layout(state['layout'])
        for pane,saved in zip(self.panes,state['panes']):pane.restore(saved)
        self.active=self.panes[min(state.get('active',0),len(self.visible_panes())-1)]
        self.activeChanged.emit(self.active)
        self.link();self.measurementsChanged.emit()

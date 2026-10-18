"""Linked multi-axis plotting and portable per-view state."""
from PySide6 import QtCore, QtWidgets, QtGui
import numpy as np
import pyqtgraph as pg
from app_fast_plot import EnvelopeCache
from app_presentation import CURSOR_COLORS,cursor_sample
from app_signal_processing import IntervalSummary

pg.setConfigOptions(antialias=False, background='#151b26', foreground='#e3eaf5')
COLORS=['#58b6ff','#ffb454','#79dba8','#d4a1ff','#ff8096','#e5da69','#83e1e8']
LAYOUTS={'Single':(1,1),'Horizontal split':(1,2),'Vertical split':(2,1),'2×2':(2,2),'Stacked':(4,1),'3 stacked':(3,1),'10 panels':(10,1)}


class NavigationViewBox(pg.ViewBox):
    """Apply a plot gesture equally in screen space to every physical Y axis."""
    owner=None

    def _gesture(self,method,event,axis):
        if self.owner is None:return method(event,axis=axis)
        primary=self.owner.getViewBox()
        if self is not primary:
            return getattr(primary,'wheelEvent' if method.__name__=='wheelEvent' else 'mouseDragEvent')(event,axis=axis)
        before={view:list(view.viewRange()[1]) for view in self.owner.y_views()}
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

    def __init__(self, store):
        view=NavigationViewBox();super().__init__(viewBox=view);view.owner=self
        self.store=store;self.ids=[];self.bindings={};self.axes={};self.curves={};self.cache={};self.summaries={}
        self.dark=True;self.display_budget=12000
        self._normalizing=False;self._synchronizing=False;self.normalized=False;self.normalization_bindings={};self._normalization={}
        self.show_legends=False;self.show_grid=True;self.history=[];self.history_index=-1;self._history_restoring=False
        self.coordinate=None;self.snap=True;self.cursor_mode='dual';self.cursor_locks=[None,None]
        self.annotations=[];self.annotation_items=[]
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.showGrid(x=True,y=True,alpha=.2)
        self.getPlotItem().hideButtons()
        self.getPlotItem().layout.setContentsMargins(0,0,0,0)
        self.getViewBox().sigResized.connect(self._resize)
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

    def close(self):
        if self.plotItem is None:return True
        self._closing=True;self.timer.stop();self.hover_proxy.disconnect();self.clear_hover()
        return super().close()

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
        self.hover_marker.hide()
        for line in self.hover_lines:line.hide()
        if had_state:self.hoverChanged.emit(None)

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
                nearest={'channel':id,'name':channel.name,'x':float(xs[index]),'y':float(value),'unit':channel.unit,'distance':distance,'scene':scene}
        return {'x':x,'coordinate_unit':self.coordinate[1] if self.coordinate else '', 'axes':axes,'nearest':nearest}

    def _live_hover(self,args):
        if self.viewport().underMouse():self._mouse_hover(args)
        else:self.clear_hover()

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
                if channels:
                    left=min(c.x[0]+c.shift for c in channels);right=max(c.x[-1]+c.shift for c in channels)
                    vl,vr=self.getViewBox().viewRange()[0]
                    low,high=max(left,vl),min(right,vr)
                    if low>high:low,high=left,right
                    reference=channels[0].values()[0]
                    begin,end=np.searchsorted(reference,[low,high],side='left');end=np.searchsorted(reference,high,side='right')
                    candidates=reference[begin:end]
                    sender=self.sender()
                    for index,line in enumerate(self.cursor_lines):
                        lock=self.cursor_locks[index]
                        if lock and lock['channel'] in self.store.channels:
                            x=self.store.channels[lock['channel']].values()[0]
                            if len(x):
                                if sender is line:
                                    i=int(np.searchsorted(x,line.value()));i=min(len(x)-1,i);j=max(0,i-1)
                                    lock['index']=i if abs(x[i]-line.value())<abs(x[j]-line.value()) else j
                                lock['index']=int(np.clip(lock['index'],0,len(x)-1))
                                line.setValue(float(x[lock['index']]))
                                continue
                        value=float(np.clip(line.value(),low,high))
                        if self.snap and len(candidates):
                            i=min(len(candidates)-1,int(np.searchsorted(candidates,value)));j=max(0,i-1)
                            value=float(candidates[i] if abs(candidates[i]-value)<abs(candidates[j]-value) else candidates[j])
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
            sample=int(np.clip(lock['index'],0,len(x)-1));value=y[sample]
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
            point=self.cursor_lines[index].value();i=min(len(x)-1,int(np.searchsorted(x,point)));j=max(0,i-1)
            self.cursor_locks[index]={'channel':channel_id,'index':i if abs(x[i]-point)<abs(x[j]-point) else j}
        lock=self.cursor_locks[index];name=('A','B')[index]
        self.cursor_lines[index].label.setFormat(name+(' · '+self.store.channels[channel_id].name.replace('{','{{').replace('}','}}') if lock else ''))
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
        self.clear_hover()
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
            self.getViewBox().setMouseMode(pg.ViewBox.PanMode);self.getViewBox().setMouseEnabled(x=True,y=True);return
        if event.key()==QtCore.Qt.Key.Key_R:
            self.fit();return
        if event.key()==QtCore.Qt.Key.Key_C:
            self.set_cursor_mode('off' if self.cursor_mode!='off' else 'dual');return
        if event.key()==QtCore.Qt.Key.Key_Space:
            self.getViewBox().setMouseMode(pg.ViewBox.PanMode);return
        super().keyPressEvent(event)

    def bind(self, ids, assignments=None, fit=True):
        self.clear_hover()
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
                vb=NavigationViewBox();vb.owner=self;vb.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton);self.scene().addItem(vb);axis.linkToView(vb);vb.setXLink(primary)
                self.axes[unit]=(axis,vb);vb.sigYRangeChanged.connect(self.clear_hover)
            if unit=='Actuators':axis.setTicks([[(0,'OFF'),(1,'ON')]])
            else:axis.setTicks(None)
            for j,id in enumerate(id for id in self.ids if self.bindings[id]==unit):
                c=self.store.channels[id];x,y=c.values()
                color=QtGui.QColor(COLORS[i%len(COLORS)])
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
                if hasattr(self,'legend'):self.legend.addItem(pg.PlotDataItem(pen=curve.pen),c.name)
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
        self._render()
        if hasattr(self,'legend'):self.legend.setVisible(self.show_legends and bool(self.ids))
        self.showGrid(x=self.show_grid,y=self.show_grid,alpha=.2)
        for unit in units:
            bounds=next((self.store.channels[id].attributes.get('plot_style',{}) for id in self.ids if self.bindings[id]==unit),{})
            low,high=bounds.get('ymin'),bounds.get('ymax')
            if not self.normalized and low not in (None,'') and high not in (None,''):
                (self.axes[unit][1] if unit in self.axes else primary).setYRange(float(low),float(high),padding=0)
        for record in self.annotations:self._annotation(record)
        self.update_cursor_markers()

    def _layout_axes(self):
        plot=self.getPlotItem();layout=plot.layout
        left=[axis for axis,_ in self.axes.values() if axis.orientation=='left']
        right=[axis for axis,_ in self.axes.values() if axis.orientation!='left']
        central=1+len(left)
        for record in plot.axes.values():layout.removeItem(record['item'])
        layout.removeItem(plot.vb);layout.removeItem(plot.titleLabel)
        for column in range(layout.columnCount()):layout.setColumnStretchFactor(column,0)
        positions={'left':(2,central-1),'right':(2,central+1),'top':(1,central),'bottom':(3,central)}
        for name,position in positions.items():
            plot.axes[name]['pos']=position;layout.addItem(plot.axes[name]['item'],*position)
        layout.addItem(plot.vb,2,central);layout.addItem(plot.titleLabel,0,central)
        for i,axis in enumerate(left):layout.addItem(axis,2,i)
        for i,axis in enumerate(right):layout.addItem(axis,2,central+2+i)
        layout.setColumnStretchFactor(central,100)
        # Keep a usable drawing area even when the user explicitly overlays many axes.
        visible_axes=[record['item'] for record in plot.axes.values() if record['item'].isVisible() and record['item'].orientation in ('left','right')]+left+right
        self.setMinimumWidth(int(380+sum(max(62.,axis.width()) for axis in visible_axes)+30))

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
        for axis,vb in self.axes.values():
            vb.setGeometry(self.getViewBox().sceneBoundingRect());vb.linkedViewChanged(self.getViewBox(),vb.XAxis)

    def _schedule(self,*args):
        if getattr(self,'_closing',False):return
        self.clear_hover()
        if self.ids and not getattr(self,'_restored_positions',False):self._cursor_changed()
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
        left=min(c.x[0]+c.shift for c in channels);right=max(c.x[-1]+c.shift for c in channels)
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
            va,vb=cursor_sample(c,a,self.snap),cursor_sample(c,b,self.snap)
            from app_time_units import presentation_statistics
            result[id]={**presentation_statistics(c,summary.query(a,b)),'A':va,'B':vb,'ΔY':vb-va}
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

    def state(self):
        return {'ids':list(self.ids),'bindings':dict(self.bindings),'range':self.getViewBox().viewRange(),
                'axes':{unit:vb.viewRange()[1] for unit,(axis,vb) in self.axes.items()},
                'cursors':[l.value() for l in self.cursor_lines],'cursor_mode':self.cursor_mode,
                'cursor_locks':[dict(lock) if lock else None for lock in self.cursor_locks],'snap':self.snap,'annotations':list(self.annotations),'normalized':self.normalized,'normalization_bindings':self.normalization_bindings,'show_grid':self.show_grid,'show_legends':self.show_legends}

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
                    if len(x):pos=float(x[int(np.clip(lock['index'],0,len(x)-1))])
                line.setValue(pos)
                line.label.setFormat(('A','B')[index]+(' · '+self.store.channels[lock['channel']].name.replace('{','{{').replace('}','}}') if lock else ''))
        finally:
            self._synchronizing=previous;self._restoring_cursors=False
            del blocker
        self.update_cursor_markers()

    def restore(self,state):
        self.snap=state.get('snap',True);self.normalized=state.get('normalized',False);self.normalization_bindings=state.get('normalization_bindings',{})
        self.show_grid=state.get('show_grid',True);self.show_legends=state.get('show_legends',False)
        self.bind(state['ids'],state.get('bindings'),fit=False);self.restore_ranges(state)
        self.snap=state.get('snap',True);self.set_cursor_mode(state.get('cursor_mode','dual'))
        for vb,item in self.annotation_items:vb.removeItem(item)
        self.annotation_items=[];self.annotations=list(state.get('annotations',[]))
        for record in self.annotations:self._annotation(record)


class PlotWorkspace(QtWidgets.QWidget):
    activeChanged=QtCore.Signal(object)
    measurementsChanged=QtCore.Signal()

    def __init__(self,store):
        super().__init__();self.store=store;self.panes=[];self.active=None;self.layout_name='Single';self._syncing=False;self.time_axes_locked=True;self.navigation_mode='pan';self._hover_pane=None
        outer=QtWidgets.QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        self.scroll=QtWidgets.QScrollArea();self.scroll.setWidgetResizable(True);outer.addWidget(self.scroll)
        self.container=QtWidgets.QWidget();self.scroll.setWidget(self.container)
        self.grid=QtWidgets.QGridLayout(self.container);self.grid.setContentsMargins(0,0,0,0)
        # The main window mounts this toolbar in its upper toolbar area. A
        # standalone workspace also gets a normal layout row, never an overlay.
        self.navigation_bar=QtWidgets.QToolBar('Graph Navigation',self)
        self.navigation_bar.setObjectName('graphNavigation');self.navigation_bar.setMovable(False)
        self.navigation_actions={};self.mode_group=QtGui.QActionGroup(self);self.mode_group.setExclusive(True)
        for label,command in [('Zoom X','x'),('Zoom Y','y'),('Zoom XY','xy'),('Pan','pan'),('Zoom In','in'),('Zoom Out','out'),('Reset View','reset')]:
            action=self.navigation_bar.addAction(label);action.triggered.connect(lambda checked=False,c=command:self.navigate(c));self.navigation_actions[command]=action
            if command in ('x','y','xy','pan'):
                action.setCheckable(True);self.mode_group.addAction(action)
                action.setToolTip({'x':'Box zoom in time only (Ctrl+1)','y':'Box zoom in value axes only (Ctrl+2)','xy':'Box zoom in time and values (Ctrl+3)','pan':'Drag to pan the graph (Ctrl+4)'}[command])
        self.navigation_actions['pan'].setChecked(True)
        self.navigation_actions['box']=self.navigation_actions['xy']
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
        # Share QAction instances with the header so shortcuts, mode constraints
        # and linked-axis behavior cannot diverge between the two locations.
        self.quick_zoom_bar=QtWidgets.QToolBar('Quick Zoom',self.hover_strip)
        self.quick_zoom_bar.setObjectName('quickZoom');self.quick_zoom_bar.setMovable(False)
        self.quick_zoom_bar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,QtWidgets.QSizePolicy.Policy.Fixed)
        for command in ('in','out','reset'):self.quick_zoom_bar.addAction(self.navigation_actions[command])
        self.quick_mode_button=QtWidgets.QToolButton(self.hover_strip)
        self.quick_mode_button.setAccessibleName('Zoom and pan mode');self.quick_mode_button.setAutoRaise(True)
        self.quick_mode_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QtWidgets.QMenu(self.quick_mode_button)
        for command in ('x','y','xy','pan'):menu.addAction(self.navigation_actions[command])
        self.quick_mode_button.setMenu(menu);self.quick_mode_button.setDefaultAction(self.navigation_actions['pan'])
        strip_layout.addWidget(self.quick_zoom_bar);strip_layout.addWidget(self.quick_mode_button)
        outer.insertWidget(1,self.hover_strip)
        self.set_layout('Single')

    def _hover_changed(self,pane,state):
        if state is None and pane is not self._hover_pane:return
        self._hover_pane=pane if state else None
        text=pane.hover_text if state else 'Mouse X/Y · Move over a graph to inspect values'
        self.hover_readout.setToolTip(text)
        width=max(0,self.hover_readout.contentsRect().width())
        self.hover_readout.setText('\n'.join(self.hover_readout.fontMetrics().elidedText(line,QtCore.Qt.TextElideMode.ElideRight,width) for line in text.splitlines()))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        # Leave room for coordinates even with both sidebars open. QToolBar
        # exposes its existing overflow menu when the center column is narrow.
        if hasattr(self,'quick_zoom_bar'):self.quick_zoom_bar.setMaximumWidth(max(80,int(self.width()*.5)))
        if self._hover_pane:self._hover_changed(self._hover_pane,self._hover_pane.hover_state)

    def navigate(self,command,factor=None):
        """Scale synchronized X once, and every independent Y axis once."""
        active=self.active
        targets=[p for p in self.visible_panes() if p is active or (self.time_axes_locked and active.coordinate and p.coordinate==active.coordinate)]
        if command in ('x','y','xy','box','pan'):
            self.navigation_mode='xy' if command=='box' else command
            self.navigation_actions[self.navigation_mode].setChecked(True)
            self.quick_mode_button.setDefaultAction(self.navigation_actions[self.navigation_mode])
            for pane in self.visible_panes():
                view=pane.getViewBox();view.setMouseMode(view.PanMode if command=='pan' else view.RectMode)
                view.setMouseEnabled(x=command!='y',y=command!='x')
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
        self.time_axes_locked=bool(locked);self.link()

    def set_layout(self,name):
        rows,cols=LAYOUTS[name];required=rows*cols
        for pane in self.panes:self.grid.removeWidget(pane)
        while len(self.panes)<required:
            pane=PlotPane(self.store);pane.installEventFilter(self)
            pane.hoverChanged.connect(lambda state,p=pane:self._hover_changed(p,state))
            pane.cursorsChanged.connect(lambda p=pane:self._cursors(p))
            self.panes.append(pane)
        for i,pane in enumerate(self.panes):
            pane.dark=self.panes[0].dark;pane.setBackground(self.panes[0].backgroundBrush())
            pane.snap=self.active.snap if self.active else True
            pane.set_cursor_mode(self.active.cursor_mode if self.active else 'dual')
            pane.setMinimumHeight(180 if required>=3 else 0)
            pane.display_budget=12000/required
            if i<required:self.grid.addWidget(pane,i//cols,i%cols)
            # Reparenting into a visible layout hides newly created widgets.
            pane.setVisible(i<required)
        self.layout_name=name;self.active=self.panes[0];self.activeChanged.emit(self.active)
        self.navigate(self.navigation_mode);self.link()

    def eventFilter(self,obj,event):
        if event.type()==QtCore.QEvent.Type.FocusIn and obj in self.panes:
            self.active=obj;self.activeChanged.emit(obj)
        return super().eventFilter(obj,event)

    def link(self):
        groups={}
        for pane in self.visible_panes():
            pane.setXLink(None)
            if not self.time_axes_locked:continue
            if pane.coordinate in groups and pane.coordinate:
                pane.setXLink(groups[pane.coordinate])
            elif pane.coordinate:
                groups[pane.coordinate]=pane

    def visible_panes(self):
        rows,cols=LAYOUTS[self.layout_name]
        return self.panes[:rows*cols]

    def _cursors(self,pane):
        if self._syncing:return
        self._syncing=True
        try:
            for target in self.visible_panes():
                if target is not pane and target.coordinate==pane.coordinate:
                    target.cursor_locks=[dict(lock) if lock and lock['channel'] in self.store.channels else None for lock in pane.cursor_locks]
                    for index,lock in enumerate(target.cursor_locks):
                        target.cursor_lines[index].label.setFormat(('A','B')[index]+(' · '+self.store.channels[lock['channel']].name.replace('{','{{').replace('}','}}') if lock else ''))
                    target._synchronizing=True
                    try:
                        for a,b in zip(target.cursor_lines,pane.cursor_lines):a.setValue(b.value())
                    finally:target._synchronizing=False
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
        return {'time_axes_locked':self.time_axes_locked,'navigation_mode':self.navigation_mode,'statistics_scope':getattr(self,'statistics_scope','Cursor interval'),'layout':self.layout_name,'panes':[p.state() for p in self.panes],
                'active':self.panes.index(self.active)}

    def restore(self,state):
        mode=state.get('navigation_mode','pan');self.navigation_mode=mode if mode in ('x','y','xy','pan') else 'pan'
        if self._hover_pane:self._hover_changed(self._hover_pane,None)
        self.time_axes_locked=bool(state.get('time_axes_locked',True))
        blocker=QtCore.QSignalBlocker(self.time_lock_action);self.time_lock_action.setChecked(self.time_axes_locked);del blocker
        self.statistics_scope=state.get('statistics_scope','Cursor interval')
        # Restoring into fresh panes avoids stale channel bindings.
        for pane in self.panes:self.grid.removeWidget(pane);pane.deleteLater()
        self.panes=[]
        if len(state['panes'])>LAYOUTS[state['layout']][0]*LAYOUTS[state['layout']][1]:self.set_layout('10 panels' if len(state['panes'])>4 else '2×2')
        self.set_layout(state['layout'])
        for pane,saved in zip(self.panes,state['panes']):pane.restore(saved)
        self.active=self.panes[min(state.get('active',0),len(self.visible_panes())-1)]
        self.activeChanged.emit(self.active)
        self.link();self.measurementsChanged.emit()

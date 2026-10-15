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

    def __init__(self, store):
        super().__init__()
        self.store=store;self.ids=[];self.bindings={};self.axes={};self.curves={};self.cache={};self.summaries={}
        self.dark=True;self.display_budget=12000
        self._normalizing=False;self._synchronizing=False;self.normalized=False;self.normalization_bindings={};self._normalization={}
        self.show_legends=False;self.show_grid=True;self.history=[];self.history_index=-1;self._history_restoring=False
        self.coordinate=None;self.snap=True;self.cursor_mode='dual';self.cursor_locks=[None,None]
        self.annotations=[];self.annotation_items=[]
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.showGrid(x=True,y=True,alpha=.2)
        self.getPlotItem().hideButtons()
        self.getViewBox().sigResized.connect(self._resize)
        self.getViewBox().sigXRangeChanged.connect(self._schedule)
        self.timer=QtCore.QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self._render)
        self.cursor_lines=[pg.InfiniteLine(pos=0,angle=90,movable=True,pen=pg.mkPen(color,width=2),hoverPen=pg.mkPen(color,width=3),label=name,labelOpts={'color':color,'position':.95}) for color,name in zip(CURSOR_COLORS,('A','B'))]
        self.empty_label=QtWidgets.QLabel('No channels selected',self)
        self.empty_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.empty_label.setStyleSheet('font-size:16px; color:#8293a9; background:transparent;')
        for line in self.cursor_lines:
            line.addMarker('v',position=.98,size=9)
            self.addItem(line,ignoreBounds=True);line.sigPositionChanged.connect(self._cursor_changed)
        self.scene().sigMouseClicked.connect(self._click)
        self.getViewBox().sigRangeChangedManually.connect(lambda *_:self.remember_view())
        self.legend=self.addLegend(offset=(12,12));self.legend.hide()

    def _cursor_changed(self):
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
        self.cursorsChanged.emit()

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
        self.cursor_lines[index].label.setFormat(name+(' · '+self.store.channels[channel_id].name if lock else ''))
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
        self.bindings={id:('Normalized tracks' if self.normalized else (assignments or {}).get(id,self.store.channels[id].unit)) for id in self.ids}
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
                vb=pg.ViewBox();self.scene().addItem(vb);axis.linkToView(vb);vb.setXLink(primary)
                self.axes[unit]=(axis,vb)
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

    def _resize(self):
        for axis,vb in self.axes.values():
            vb.setGeometry(self.getViewBox().sceneBoundingRect());vb.linkedViewChanged(self.getViewBox(),vb.XAxis)

    def _schedule(self,*args):
        if self.ids:self._cursor_changed()
        if not self.timer.isActive():
            self.timer.start(0)

    def _render(self):
        left,right=self.getViewBox().viewRange()[0]
        budget=max(32,int(self.display_budget/max(1,len(self.ids))))
        for id,(vb,curve) in self.curves.items():
            c=self.store.channels.get(id)
            if c is None:
                continue
            x,y=self.cache[(id,c.revision)].visible(left,right,budget)
            if id in self._normalization:
                low,high,offset=self._normalization[id];y=np.where(np.isfinite(y),(y-low)/(high-low) if high>low else .5,np.nan)+offset
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
        for line,fraction in zip(self.cursor_lines,(.25,.75)):
            line.setValue(left+(right-left)*fraction)
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
                                 pen=pg.mkPen('#cfa3ff',style=QtCore.Qt.PenStyle.DashLine),label=record['text'])
        unit=record.get('axis');vb=self.axes[unit][1] if unit in self.axes else self.getViewBox()
        vb.addItem(item,ignoreBounds=True);self.annotation_items.append((vb,item))

    def state(self):
        return {'ids':list(self.ids),'bindings':dict(self.bindings),'range':self.getViewBox().viewRange(),
                'axes':{unit:vb.viewRange()[1] for unit,(axis,vb) in self.axes.items()},
                'cursors':[l.value() for l in self.cursor_lines],'cursor_mode':self.cursor_mode,
                'cursor_locks':[dict(lock) if lock else None for lock in self.cursor_locks],'snap':self.snap,'annotations':list(self.annotations),'normalized':self.normalized,'normalization_bindings':self.normalization_bindings,'show_grid':self.show_grid,'show_legends':self.show_legends}

    def restore_ranges(self,state):
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
            line.label.setFormat(('A','B')[index]+(' · '+self.store.channels[lock['channel']].name if lock else ''))

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
        super().__init__();self.store=store;self.panes=[];self.active=None;self.layout_name='Single';self._syncing=False
        outer=QtWidgets.QVBoxLayout(self);outer.setContentsMargins(0,0,0,0)
        self.scroll=QtWidgets.QScrollArea();self.scroll.setWidgetResizable(True);outer.addWidget(self.scroll)
        self.container=QtWidgets.QWidget();self.scroll.setWidget(self.container)
        self.grid=QtWidgets.QGridLayout(self.container);self.grid.setContentsMargins(0,0,0,0)
        self.set_layout('Single')

    def set_layout(self,name):
        rows,cols=LAYOUTS[name];required=rows*cols
        for pane in self.panes:self.grid.removeWidget(pane)
        while len(self.panes)<required:
            pane=PlotPane(self.store);pane.installEventFilter(self)
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
        self.link()

    def eventFilter(self,obj,event):
        if event.type()==QtCore.QEvent.Type.FocusIn and obj in self.panes:
            self.active=obj;self.activeChanged.emit(obj)
        return super().eventFilter(obj,event)

    def link(self):
        groups={}
        for pane in self.visible_panes():
            pane.setXLink(None)
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
                        target.cursor_lines[index].label.setFormat(('A','B')[index]+(' · '+self.store.channels[lock['channel']].name if lock else ''))
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
                c=self.store.channels[id];groups.setdefault((c.coordinate_kind,c.coordinate_unit),{}).setdefault(c.unit,[])
                if id not in groups[(c.coordinate_kind,c.coordinate_unit)][c.unit]:groups[(c.coordinate_kind,c.coordinate_unit)][c.unit].append(id)
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
        return {'layout':self.layout_name,'panes':[p.state() for p in self.panes],
                'active':self.panes.index(self.active)}

    def restore(self,state):
        # Restoring into fresh panes avoids stale channel bindings.
        for pane in self.panes:self.grid.removeWidget(pane);pane.deleteLater()
        self.panes=[]
        if len(state['panes'])>LAYOUTS[state['layout']][0]*LAYOUTS[state['layout']][1]:self.set_layout('10 panels' if len(state['panes'])>4 else '2×2')
        self.set_layout(state['layout'])
        for pane,saved in zip(self.panes,state['panes']):pane.restore(saved)
        self.active=self.panes[min(state.get('active',0),len(self.visible_panes())-1)]
        self.activeChanged.emit(self.active)
        self.link();self.measurementsChanged.emit()

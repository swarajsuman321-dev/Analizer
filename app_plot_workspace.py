"""Linked multi-axis plotting and portable per-view state."""
from PySide6 import QtCore, QtWidgets, QtGui
import numpy as np
import pyqtgraph as pg
from app_fast_plot import EnvelopeCache
from app_signal_processing import IntervalSummary

pg.setConfigOptions(antialias=False, background='#151b26', foreground='#e3eaf5')
COLORS=['#58b6ff','#ffb454','#79dba8','#d4a1ff','#ff8096','#e5da69','#83e1e8']
LAYOUTS={'Single':(1,1),'Horizontal split':(1,2),'Vertical split':(2,1),'2×2':(2,2),'Stacked':(4,1)}


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
        self.coordinate=None;self.snap=True;self.cursor_mode='dual';self._restoring=False
        self.annotations=[];self.annotation_items=[]
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.showGrid(x=True,y=True,alpha=.2)
        self.getPlotItem().hideButtons()
        self.getViewBox().sigResized.connect(self._resize)
        self.getViewBox().sigXRangeChanged.connect(self._schedule)
        self.timer=QtCore.QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self._render)
        self.cursor_lines=[pg.InfiniteLine(pos=0,angle=90,movable=True,pen=pg.mkPen(color,width=1.5)) for color in ('#ffffff','#ffce69')]
        for line in self.cursor_lines:
            self.addItem(line,ignoreBounds=True);line.sigPositionChanged.connect(self._cursor_changed)
        self.scene().sigMouseClicked.connect(self._click)

    def _cursor_changed(self):
        self.cursorsChanged.emit()

    def _click(self,event):
        if event.button()!=QtCore.Qt.MouseButton.LeftButton or not self.sceneBoundingRect().contains(event.scenePos()):
            return
        point=self.getViewBox().mapSceneToView(event.scenePos()).x()
        if self.snap and self.ids:
            c=self.store.channels[self.ids[0]];x=c.x+c.shift
            if len(x):
                i=min(len(x)-1,np.searchsorted(x,point));j=max(0,i-1)
                point=float(x[i] if abs(x[i]-point)<abs(x[j]-point) else x[j])
        index=1 if event.modifiers()&QtCore.Qt.KeyboardModifier.ShiftModifier and self.cursor_mode=='dual' else 0
        self.cursor_lines[index].setValue(point)

    def set_cursor_mode(self,mode):
        self.cursor_mode=mode
        for i,line in enumerate(self.cursor_lines):
            line.setVisible(mode!='off' and (i==0 or mode=='dual'))

    def keyPressEvent(self,event):
        if event.key()==QtCore.Qt.Key.Key_R:
            self.fit();return
        if event.key()==QtCore.Qt.Key.Key_C:
            self.set_cursor_mode('off' if self.cursor_mode!='off' else 'dual');return
        if event.key()==QtCore.Qt.Key.Key_Space:
            self.getViewBox().setMouseMode(pg.ViewBox.PanMode);return
        super().keyPressEvent(event)

    def bind(self, ids, assignments=None, fit=True):
        saved=self.state()
        for vb,item in self.annotation_items:vb.removeItem(item)
        self.annotation_items=[]
        for item in self.curves.values():
            item[0].removeItem(item[1])
        self.curves={}
        for key,(axis,vb) in self.axes.items():
            self.getPlotItem().layout.removeItem(axis);self.scene().removeItem(axis);self.scene().removeItem(vb)
        self.axes={}
        self.ids=[id for id in ids if id in self.store.channels]
        self.cache={k:v for k,v in self.cache.items() if k[0] in self.ids}
        self.summaries={k:v for k,v in self.summaries.items() if k in self.ids}
        coordinates={(self.store.channels[id].coordinate_kind,self.store.channels[id].coordinate_unit) for id in self.ids}
        if len(coordinates)>1:
            raise ValueError('Different coordinate systems require separate viewports')
        self.coordinate=next(iter(coordinates),None)
        self.bindings={id:(assignments or {}).get(id,self.store.channels[id].unit) for id in self.ids}
        units=list(dict.fromkeys(self.bindings.values()))
        primary=self.getViewBox()
        for i,unit in enumerate(units):
            color=QtGui.QColor(COLORS[i%len(COLORS)])
            if not self.dark:color=color.darker(170)
            color=color.name()
            if i==0:
                axis=self.getAxis('left');axis.setLabel(unit or 'Value',color=color);axis.setPen(color)
                vb=primary
            else:
                axis=pg.AxisItem('right');axis.setLabel(unit or 'Value',color=color);axis.setPen(color)
                vb=pg.ViewBox();self.scene().addItem(vb);axis.linkToView(vb);vb.setXLink(primary)
                self.getPlotItem().layout.addItem(axis,2,2+i)
                self.axes[unit]=(axis,vb)
            for j,id in enumerate(id for id in self.ids if self.bindings[id]==unit):
                c=self.store.channels[id];x,y=c.values()
                color=QtGui.QColor(COLORS[self.ids.index(id)%len(COLORS)])
                if not self.dark:color=color.darker(170)
                curve=PreparedCurve(x,y,color)
                vb.addItem(curve);self.curves[id]=(vb,curve)
                key=(id,c.revision)
                if key not in self.cache:
                    self.cache={k:v for k,v in self.cache.items() if k[0]!=id}
                    self.cache[key]=EnvelopeCache(x,y)
                    self.summaries[id]=(c.revision,IntervalSummary(c))
        self.setLabel('bottom',self.coordinate[0] if self.coordinate else 'Coordinate',units=self.coordinate[1] if self.coordinate else '')
        self._resize()
        if fit:
            self.fit()
        else:
            self.restore_ranges(saved)
        self._render()
        for record in self.annotations:self._annotation(record)

    def _resize(self):
        for axis,vb in self.axes.values():
            vb.setGeometry(self.getViewBox().sceneBoundingRect());vb.linkedViewChanged(self.getViewBox(),vb.XAxis)

    def _schedule(self,*args):
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
        for line,fraction in zip(self.cursor_lines,(.25,.75)):
            line.setValue(left+(right-left)*fraction)

    def measurements(self):
        a,b=[line.value() for line in self.cursor_lines]
        result={}
        for id in self.ids:
            c=self.store.channels[id]
            revision,summary=self.summaries[id]
            if revision!=c.revision:
                summary=IntervalSummary(c);self.summaries[id]=(c.revision,summary)
            result[id]={'A':c.sample(a),'B':c.sample(b),**summary.query(a,b)}
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
                'snap':self.snap,'annotations':list(self.annotations)}

    def restore_ranges(self,state):
        if 'range' in state:
            self.setXRange(*state['range'][0],padding=0);self.setYRange(*state['range'][1],padding=0)
        for unit,bounds in state.get('axes',{}).items():
            if unit in self.axes:self.axes[unit][1].setYRange(*bounds,padding=0)
        for line,pos in zip(self.cursor_lines,state.get('cursors',[])):line.setValue(pos)

    def restore(self,state):
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
        self.grid=QtWidgets.QGridLayout(self);self.grid.setContentsMargins(0,0,0,0)
        self.set_layout('Single')

    def set_layout(self,name):
        states=[p.state() for p in self.panes]
        rows,cols=LAYOUTS[name];required=rows*cols
        for pane in self.panes:self.grid.removeWidget(pane)
        while len(self.panes)<required:
            pane=PlotPane(self.store);pane.installEventFilter(self)
            pane.cursorsChanged.connect(lambda p=pane:self._cursors(p))
            self.panes.append(pane)
        for i,pane in enumerate(self.panes):
            pane.dark=self.panes[0].dark;pane.setBackground(self.panes[0].backgroundBrush())
            pane.setVisible(i<required);pane.display_budget=12000/required
            if i<required:self.grid.addWidget(pane,i//cols,i%cols)
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
                    for a,b in zip(target.cursor_lines,pane.cursor_lines):a.setValue(b.value())
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
        self.link();self.measurementsChanged.emit()

    def refresh(self):
        for pane in self.visible_panes():
            pane.bind(pane.ids,pane.bindings,fit=False)
        self.link()

    def state(self):
        return {'layout':self.layout_name,'panes':[p.state() for p in self.panes],
                'active':self.panes.index(self.active)}

    def restore(self,state):
        # Restoring into fresh panes avoids stale channel bindings.
        for pane in self.panes:self.grid.removeWidget(pane);pane.deleteLater()
        self.panes=[]
        if len(state['panes'])>LAYOUTS[state['layout']][0]*LAYOUTS[state['layout']][1]:self.set_layout('2×2')
        self.set_layout(state['layout'])
        for pane,saved in zip(self.panes,state['panes']):pane.restore(saved)
        self.active=self.panes[min(state.get('active',0),len(self.visible_panes())-1)]
        self.link();self.measurementsChanged.emit()

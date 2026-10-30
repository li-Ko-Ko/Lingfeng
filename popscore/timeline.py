"""Two timeline bands: bar editing above, position/loop ruler below.

Both docked and floating editors use this gesture controller. Musical bar
selection and transport loop bounds deliberately have separate state.
"""
from PySide6.QtCore import QObject,QTimer,QPointF,Qt
from PySide6.QtWidgets import QApplication
from shiboken6 import isValid

KEY_W=66
RULER_TIME_H=30


class TimelineGesture(QObject):
    def __init__(self,host,roll,offset=lambda:0):
        super().__init__(host);self.host=host;self.get_roll=roll;self.offset=offset
        self.state=None;self.last_pos=QPointF();self.menu=None
        self.edge_timer=QTimer(self);self.edge_timer.setInterval(30);self.edge_timer.timeout.connect(self.scroll_edge)

    def tick(self,pos):
        r=self.get_roll();return r.tick_at(pos.x()-self.offset())

    def press(self,event):
        self.cancel();r=self.get_roll();pos=event.position();button=event.button()
        if pos.x()<KEY_W or button not in (Qt.MouseButton.LeftButton,Qt.MouseButton.RightButton):return
        upper=pos.y()<r.bar_ruler_height
        if not upper and button==Qt.MouseButton.RightButton:return
        self.last_pos=QPointF(pos);tick=self.tick(pos)
        self.state=dict(pos=QPointF(pos),tick=tick,button=button,upper=upper,moved=False,mode='range')
        if upper:
            if button==Qt.MouseButton.LeftButton:r.timeline_begin(tick,event.modifiers())
            self.state['modifiers']=event.modifiers()
        else:
            bounds=r.loop_range
            if bounds:
                edges=[(abs(pos.x()-(r.x_at(t)+self.offset())),mode) for t,mode in zip(bounds,('left','right'))]
                distance,mode=min(edges)
                if distance<=5:self.state.update(mode=mode,bounds=tuple(bounds))
            if event.modifiers()&Qt.KeyboardModifier.ShiftModifier:
                anchor=r.loop_anchor if r.loop_anchor is not None else r.cursor_tick
                self.state.update(tick=anchor,moved=True,mode='range')
                self.update_range(tick)
        self.edge_timer.start()

    def move(self,event):
        pos=event.position();self.last_pos=QPointF(pos);r=self.get_roll()
        if not self.state:
            if pos.x()>=KEY_W and pos.y()<r.bar_ruler_height:
                from .theme import roll_pitch_name
                c=r.project.context_at(self.tick(pos));m=r.project.measures[r.project.measure_at(self.tick(pos))]
                self.host.setToolTip(f'1 = {roll_pitch_name(c.tonic)} · {c.mode}   {m.numerator}/{m.denominator}')
            else:self.host.setToolTip('')
            edge=pos.y()>=r.bar_ruler_height and r.loop_range and any(abs(pos.x()-r.x_at(t)-self.offset())<=5 for t in r.loop_range)
            self.host.setCursor(Qt.CursorShape.SizeHorCursor if edge else Qt.CursorShape.ArrowCursor);return
        s=self.state
        if (pos-s['pos']).manhattanLength()>=4:s['moved']=True
        if s['moved']:self.update_selection(self.tick(pos))

    def update_selection(self,tick):
        s=self.state;r=self.get_roll()
        if s['upper']:
            if r.timeline_drag_state is None:r.timeline_begin(s['tick'],s['modifiers'])
            r.timeline_move(tick)
        else:self.update_range(tick)
        self.host.update()

    def update_range(self,tick):
        r=self.get_roll();s=self.state
        if s['mode']=='left':
            end=s['bounds'][1];start=min(r.snap_time(tick),r.bucket(end-1)[0]);bounds=(max(0,start),end)
        elif s['mode']=='right':
            start=s['bounds'][0];end=max(r.snap_time(tick),r.bucket(start)[1]);bounds=(start,min(r.project.end,end))
        else:
            a,b=r.bucket(s['tick']);c,d=r.bucket(tick);bounds=(min(a,c),max(b,d))
        r.loop_anchor=r.bucket(s['tick'])[0]
        r.loop_range=tuple(bounds);r.loopRangeChanged.emit(bounds);r.refresh()

    def release(self,event):
        s=self.state
        if not s or event.button()!=s['button']:return
        r=self.get_roll()
        if s['upper']:
            if s['button']==Qt.MouseButton.RightButton:
                self.menu=r.timeline_menu(QPointF(event.position().x()-self.offset(),10).toPoint(),preserve=s['moved'])
                self.menu.popup(event.globalPosition().toPoint())
        elif not s['moved']:
            tick=max(0,min(r.grid_points()[-2],r.snap_time(self.tick(event.position()))))
            r.loop_anchor=tick;r.playheadChanged.emit(tick)
        self.cancel();self.host.update()

    def double_click(self,event):
        r=self.get_roll()
        if event.button()==Qt.MouseButton.LeftButton and event.position().x()>=KEY_W and event.position().y()<r.bar_ruler_height:
            self.cancel();r.measureActivated.emit(r.project.measure_at(self.tick(event.position())));return
        if event.button()==Qt.MouseButton.LeftButton and event.position().x()>=KEY_W and event.position().y()>=self.get_roll().bar_ruler_height:
            self.cancel();r=self.get_roll();r.playRequested.emit(max(0,min(r.grid_points()[-2],r.snap_time(self.tick(event.position())))))

    def scroll_edge(self):
        s=self.state
        if not s or not self.host.isVisible() or not QApplication.mouseButtons()&s['button']:
            self.edge_timer.stop();return
        if not s['moved']:return
        x=self.last_pos.x();left=KEY_W+self.offset();right=self.host.width();delta=0
        if x<left+24:delta=-max(1,min(12,round((left+24-x)/2)))
        elif x>right-24:delta=max(1,min(12,round((x-right+24)/2)))
        r=self.get_roll();bar=r.horizontalScrollBar();before=bar.value()
        if delta:bar.setValue(before+delta);r.navigationRequested.emit()
        if bar.value()!=before:self.update_selection(self.tick(self.last_pos))

    def cancel(self):
        self.state=None
        # Qt can hide a scroll area after deleting its viewport at shutdown.
        if isValid(self.edge_timer):self.edge_timer.stop()
        self.get_roll().timeline_drag_state=None
        if isValid(self.host):self.host.unsetCursor()

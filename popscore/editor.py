from __future__ import annotations
from .i18n import tr
import copy
import math
import time
from fractions import Fraction
from PySide6.QtCore import Qt, QRectF, QPointF, QPoint, Signal, QTimer
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QKeySequence,QPainterPath,QAction
from PySide6.QtWidgets import QAbstractScrollArea, QWidget, QMenu, QApplication,QFrame
from .theme import color as paint_color,roll_color,label_color,colored_category
from . import theme
from .painting import cached_layer,roll_view_key
from .model import PPQ, MODES, COLORS, BACKGROUND_COLORS, NOTE_COLORS, Note, PATTERNS, degree_text, spelling, pitch_name, merge_ranges
from .operations import can_join,can_split,resize_chord
from .chordops import roman_label,chord_details,contextual_chord_name
from .rhythm import label as rhythm_label,analyze as analyze_rhythm
from .timeline import TimelineGesture,RULER_TIME_H
from .keybindings import menu_shortcut
from .navigation import watch_scrollbar

KEY_W, RULER_H = 66, 72


def paint_drag_ghost(painter,rect):
    """Original geometry remains a quiet reference while the target is previewed."""
    painter.save();ink=paint_color('#247D6E');fill=QColor(ink);fill.setAlpha(35)
    painter.setPen(QPen(ink,1.2,Qt.PenStyle.DashLine));painter.setBrush(fill)
    painter.drawRoundedRect(rect,3,3);painter.restore()


class ChordLane(QWidget):
    velocityVisibilityChanged=Signal(bool)
    def selection_event(self,ids):
        self.highlight_ids=set(ids);self.editor.chord_event_lane=self
        try:self.editor.chordSelection.emit(set(ids))
        finally:self.editor.chord_event_lane=None

    def hover_event(self,cid):
        if self.highlight_hover==cid:return
        self.highlight_hover=cid;self.editor.chord_event_lane=self
        try:self.editor.chordHover.emit(cid)
        finally:self.editor.chord_event_lane=None

    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor
        self.structure=editor.role=='harmony'
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.drag=None;self.preview=None;self.previews={};self.drag_originals=[];self.collapse_click=None;self.gesture_moved=False
        self.drag_ids=set();self.drop_tick=None;self.preview_delta=0;self.marquee_anchor=None
        self.edge_timer=QTimer(self);self.edge_timer.setInterval(30);self.edge_timer.timeout.connect(self.scroll_drag_edge)
        self.hold_timer=QTimer(self);self.hold_timer.setSingleShot(True);self.hold_timer.setInterval(280);self.hold_timer.timeout.connect(self.begin_resize)
        self.audition_timer=QTimer(self);self.audition_timer.setSingleShot(True);self.audition_timer.setInterval(320);self.audition_timer.timeout.connect(lambda:self.editor.chordAuditionHeld.emit(self.audition_id) if self.audition_id else None)
        self.last_pos=None;self.press_time=0;self.marquee=None;self.press_pos=None;self.selection_before=set();self.toggle_off=False;self.audition_id=''
        self.highlight_ids=set();self.highlight_hover=''
        self.pan_state=None;self.right_press=False;self.context_handled=0
        self.aux_ruler_scale=1
        self.velocity_visible=False;self.velocity_lane=ChordVelocityLane(self);self.velocity_lane.hide()
        self.velocity_action=QAction(tr('和弦轨力度窗格'),self);self.velocity_action.setCheckable(True)
        self.velocity_action.toggled.connect(self.set_velocity_visible)

    def card_height(self):return self.height()-(58 if self.velocity_visible else 0)

    def set_velocity_visible(self,visible):
        self.velocity_visible=bool(visible);self.velocity_lane.setVisible(self.velocity_visible)
        blocked=self.velocity_action.blockSignals(True);self.velocity_action.setChecked(bool(visible));self.velocity_action.blockSignals(blocked)
        if self is self.editor.lane:self.editor.set_panel('chords',self.editor.panels['chords'])
        else:self.setFixedHeight(62+(58 if visible else 0))
        self.layout_velocity();self.update();self.velocityVisibilityChanged.emit(bool(visible))

    def layout_velocity(self):
        self.velocity_lane.setGeometry(0,self.card_height(),self.width(),58)

    def resizeEvent(self,event):
        super().resizeEvent(event);self.layout_velocity()

    def offset(self):
        if getattr(self.editor,'main_timeline_state',False) or self.window()!=self.editor.window():return 0
        return self.editor.viewport().mapToGlobal(QPoint(0,0)).x()-self.mapToGlobal(QPoint(0,0)).x()

    def x_at(self,tick):return self.editor.x_at(tick)+self.offset()
    def tick_at(self,x):return self.editor.tick_at(x-self.offset())

    def preview_chord(self,chord):
        return self.previews.get(chord.id,self.preview if self.preview and self.preview.id==chord.id else chord)

    def card_rect(self,chord):
        width=chord.duration/PPQ*self.editor.zoom
        inset=min(2,width/4)
        return QRectF(self.x_at(chord.start)+inset,5,width-2*inset,max(30,self.card_height()-10))

    def chord_hit(self,pos):
        # Hit-test the visible top card, following the reverse paint order.
        return next(((r,c) for r,c in reversed(getattr(self,'boxes',[])) if r.contains(pos)),None)

    def paintEvent(self,event):
        p=QPainter(self);e=self.editor
        preview=(self.preview.id,self.preview.start,self.preview.end) if self.preview else None
        key=(roll_view_key(e),self.offset(),preview,str(self.marquee),frozenset(e.selected_chords),e.hovered_chord,e.selected_chord,self.velocity_visible,self.aux_ruler_scale)
        cached_layer(self,p,key,self.paint_content)
        p.setClipRect(KEY_W,0,self.width()-KEY_W,self.height());p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if e.anchor_tick is not None:
            p.setPen(QPen(paint_color('#426BAA'),1.2,Qt.PenStyle.DashLine));p.drawLine(QPointF(self.x_at(e.anchor_tick),0),QPointF(self.x_at(e.anchor_tick),self.height()))
        x=self.x_at(e.visual_tick());p.setPen(QPen(paint_color('#D15F49'),2));p.drawLine(QPointF(x,0),QPointF(x,self.height()))

    def paint_content(self,p):
        from .theme import roll_pitch_name as pitch_name,roll_degree_text as degree_text
        e=self.editor;project=e.project;p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(),paint_color('#FAFBFD'))
        p.setFont(QFont('Microsoft YaHei',9));p.setPen(paint_color('#66768B'))
        p.drawText(9,25,tr('和弦'))
        p.setClipRect(KEY_W,0,self.width()-KEY_W,self.card_height())
        for i,start in enumerate(project.starts[:-1]):
            x=self.x_at(start)
            if -200<x<self.width()+200:
                p.setPen(QPen(paint_color('#E3E8EE'),1));p.drawLine(int(x),0,int(x),self.height())
        self.paint_aux_ruler(p)
        self.boxes=[]
        display=[(original,self.preview_chord(original)) for original in project.chords]
        # Stationary cards first; originals and incoming edits form the overlay.
        # Timeline order must not hide a left chord's preview beneath its neighbor.
        for original,chord in display:
            if chord is original:self.paint_card(p,original,chord)
        for old in self.drag_originals if self.preview else ():
            current=self.preview_chord(old)
            if (old.start,old.end)!=(current.start,current.end):
                p.save();p.setClipRect(QRectF(self.x_at(old.start),0,old.duration/PPQ*e.zoom,self.card_height()),Qt.ClipOperation.IntersectClip)
                paint_drag_ghost(p,self.card_rect(old));p.restore()
        for original,chord in display:
            if chord is not original:self.paint_card(p,original,chord)
        if self.marquee:
            p.setPen(QPen(paint_color('#247D6E'),1,Qt.PenStyle.DashLine));p.setBrush(QColor(88,158,154,50));p.drawRect(self.marquee)

    def paint_card(self,p,original,chord):
        e=self.editor;project=e.project
        x=self.x_at(chord.start);w=chord.duration/PPQ*e.zoom
        if x+w<KEY_W or x>self.width():return
        r=self.card_rect(chord);self.boxes.append((r,chord))
        p.save();p.setClipRect(QRectF(x,0,w,self.card_height()),Qt.ClipOperation.IntersectClip)
        # Reserve a clean gutter even at bar/ruler divisions. Rounded corners
        # and two-pixel highlights must not stack with the neighboring border.
        p.save();p.setRenderHint(QPainter.RenderHint.Antialiasing,False)
        p.fillRect(QRectF(x,3,w,self.card_height()-6),paint_color('#FAFBFD'));p.restore()
        radius=min(6,r.width()/2)
        # The destination covers lower cards' labels; only the original is a ghost.
        p.setPen(QPen(paint_color('#C7D9D7'),min(1,r.width())));p.setBrush(paint_color('#EDF5F2'));p.drawRoundedRect(r,radius,radius)
        p.save();p.setClipRect(r.adjusted(5,3,-4,-3),Qt.ClipOperation.IntersectClip)
        p.setPen(paint_color('#275D54'));p.setFont(QFont('Segoe UI',12,QFont.Weight.DemiBold))
        visible=r.intersected(QRectF(KEY_W,0,self.width()-KEY_W,self.height()))
        title=visible.adjusted(7,3,-5,0);title.setHeight(23)
        info=original
        p.drawText(title,Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(roman_label(project,info),Qt.TextElideMode.ElideRight,max(0,int(title.width()))))
        p.setFont(QFont('Microsoft YaHei',8));p.setPen(paint_color('#65827D'))
        subtitle=visible.adjusted(7,27,-5,0);subtitle.setHeight(18)
        detail=tr('无和弦') if info.notes==[] else contextual_chord_name(project,info)+' · '+rhythm_label(info,project)
        p.drawText(subtitle,Qt.AlignmentFlag.AlignVCenter,p.fontMetrics().elidedText(detail,Qt.TextElideMode.ElideRight,max(0,int(subtitle.width()))));p.restore()
        if chord.id in e.selected_chords or chord.id==e.hovered_chord or chord.id==e.selected_chord:
            p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(paint_color('#247D6E'),min(2,r.width())));p.drawRoundedRect(r,radius,radius)
        if chord is not original:
            self.paint_aux_ruler(p,r)
            p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(paint_color('#247D6E'),min(2,r.width())));p.drawRoundedRect(r,radius,radius)
        p.restore()

    def ruler_ticks(self):
        """Visual beat divisions, independent of the editor's snap grid."""
        if not self.aux_ruler_scale:return
        project=self.editor.project;left=self.tick_at(KEY_W);right=self.tick_at(self.width())
        for bar in range(project.measure_at(left),project.measure_at(right)+1):
            a,b=project.starts[bar:bar+2];beat=PPQ*4//project.measures[bar].denominator
            step=b-a if self.aux_ruler_scale=='bar' else max(1,round(beat*self.aux_ruler_scale))
            first=a+max(0,(left-a)//step)*step
            for tick in range(first,b,step):
                if tick>right:break
                x=self.x_at(tick)
                if x<KEY_W:continue
                whole,remainder=divmod(tick-a,beat);major=tick==a
                label=f'{bar+1}.{whole+1}'+(f'+{Fraction(remainder,beat)}' if remainder else '')
                yield x,14 if major else 9 if not remainder else 5,label

    def paint_aux_ruler(self,p,overlay=None):
        if not self.aux_ruler_scale:return
        p.save();p.setClipRect(overlay or QRectF(KEY_W,0,self.width()-KEY_W,self.card_height()),Qt.ClipOperation.IntersectClip)
        top,bottom=(overlay.top(),overlay.bottom()) if overlay else (0,self.card_height()-1)
        ink=paint_color('#247D6E' if overlay else '#8191A4');ink.setAlpha(180 if overlay else 140)
        p.setPen(QPen(ink,1));p.setFont(QFont('Segoe UI',8));next_label=KEY_W
        for x,length,label in self.ruler_ticks():
            length=min(length,(bottom-top)/3)
            p.drawLine(QPointF(x,top),QPointF(x,top+length));p.drawLine(QPointF(x,bottom-length),QPointF(x,bottom))
            if not overlay and x>=next_label:
                p.drawText(QPointF(x+4,(top+bottom)/2+4),label);next_label=x+p.fontMetrics().horizontalAdvance(label)+16
        p.restore()

    def wheelEvent(self,event):
        self.editor.time_wheel(event,event.position().x()-self.offset())

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.MiddleButton:
            self.pan_state=(QPointF(event.position()),self.editor.horizontalScrollBar().value());self.setCursor(Qt.CursorShape.ClosedHandCursor);return
        if event.button()==Qt.MouseButton.RightButton and event.position().x()>=KEY_W:
            self.setFocus();self.right_press=True;self.gesture_moved=False;self.press_pos=QPointF(event.position());self.last_pos=QPointF(event.position())
            self.editor.edit_target='chords';self.editor.elementSelection.emit('chords')
            self.marquee_anchor=(self.tick_at(event.position().x()),event.position().y());self.selection_before=set(self.editor.selected_chords) if event.modifiers()&(Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier) else set();return
        if event.button()!=Qt.MouseButton.LeftButton or event.position().x()<KEY_W:return
        self.edge_timer.stop();self.marquee_anchor=None;self.collapse_click=None;self.gesture_moved=False;self.previews={};self.drag_originals=[];self.drag=None;self.preview=None
        self.setFocus();self.editor.edit_target='chords';self.editor.elementSelection.emit('chords')
        self.press_pos=QPointF(event.position());self.selection_before=set(self.editor.selected_chords)
        hit=self.chord_hit(event.position())
        self.toggle_off=False;self.audition_id=''
        if hit:
            r,c=hit;e=self.editor
            self.audition_id=c.id;e.chordAudition.emit(c.id);self.audition_timer.start()
            if event.modifiers()&Qt.KeyboardModifier.ShiftModifier and e.chord_anchor:
                ordered=sorted(e.project.chords,key=lambda x:x.start);indices={c.id:i for i,c in enumerate(ordered)}
                if e.chord_anchor in indices:
                    a,b=sorted((indices[e.chord_anchor],indices[c.id]));ids={item.id for item in ordered[a:b+1]}
                    if event.modifiers()&Qt.KeyboardModifier.ControlModifier:ids|=e.selected_chords
                    e.selected_chords=ids;self.selection_event(ids);self.update();return
            self.toggle_off=c.id in e.selected_chords and len(e.selected_chords)==1 and not event.modifiers()
            e.chord_anchor=c.id
            control=bool(event.modifiers()&Qt.KeyboardModifier.ControlModifier)
            ids=set(e.selected_chords) if control or c.id in e.selected_chords else set()
            if not event.modifiers() and c.id in ids and len(ids)>1:self.collapse_click=c.id
            if control and c.id in ids:ids.remove(c.id)
            else:ids.add(c.id)
            e.selected_chords=ids;e.selected_chord=c.id if c.id in ids else '';self.selection_event(ids);e.chordSelected.emit(e.selected_chord)
            if control:self.update();return
            self.press_time=time.monotonic()
            mode='left' if event.position().x()<r.left()+8 else 'end' if event.position().x()>r.right()-8 else 'move'
            self.last_pos=QPointF(event.position());self.drag=(mode,copy.deepcopy(c),self.tick_at(event.position().x()))
            self.drag_ids=set(ids);self.drop_tick=None;self.preview_delta=0
            self.drag_originals=copy.deepcopy([chord for chord in e.project.chords if chord.id in ids])
            if mode!='move':self.drag=('pending',self.drag);self.hold_timer.start()
            self.update()
        else:
            if not event.modifiers()&(Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier):self.selection_before=set()
            self.last_pos=QPointF(event.position());self.marquee_anchor=(self.tick_at(event.position().x()),event.position().y())
            self.marquee=QRectF(self.press_pos,self.press_pos);self.selection_event(self.selection_before)

    def select_marquee(self,pos):
        if self.marquee_anchor is None:return
        tick,y=self.marquee_anchor
        self.marquee=QRectF(QPointF(self.x_at(tick),y),QPointF(max(KEY_W,min(self.width(),pos.x())),pos.y())).normalized()
        self.marquee.setHeight(max(1,self.marquee.height()))
        e=self.editor
        ids=self.selection_before|{c.id for c in e.project.chords if self.marquee.intersects(self.card_rect(c))}
        e.selected_chords=ids;self.selection_event(ids);self.update()

    def begin_resize(self):
        if self.drag and self.drag[0]=='pending':
            self.drag=self.drag[1];self.setCursor(Qt.CursorShape.SizeHorCursor)
            if self.last_pos is not None and self.press_pos is not None and abs(self.last_pos.x()-self.press_pos.x())>=4:
                self.gesture_moved=True;self.move_to(self.last_pos)

    def mouseMoveEvent(self,event):
        if self.pan_state:
            pos,scroll=self.pan_state;self.editor.horizontalScrollBar().setValue(round(scroll+pos.x()-event.position().x()));self.editor.navigationRequested.emit();return
        self.last_pos=QPointF(event.position())
        if self.right_press:
            if (event.position()-self.press_pos).manhattanLength()>=4:self.gesture_moved=True
            if self.gesture_moved:
                self.select_marquee(event.position());self.setCursor(Qt.CursorShape.CrossCursor)
                if not self.edge_timer.isActive():self.edge_timer.start()
            return
        if self.marquee is not None:
            self.select_marquee(event.position())
            if (event.position()-self.press_pos).manhattanLength()>4 and not self.edge_timer.isActive():self.edge_timer.start()
            return
        if not self.drag:
            hit=self.chord_hit(event.position())
            self.hover_event(hit[1].id if hit else '')
            self.setToolTip(chord_details(self.editor.project,hit[1],compact=not getattr(self.editor,'score_mode',False)) if hit else '')
            self.setCursor(Qt.CursorShape.SizeHorCursor if hit and min(event.position().x()-hit[0].left(),hit[0].right()-event.position().x())<8 else Qt.CursorShape.OpenHandCursor)
            return
        mode=self.drag[1][0] if self.drag[0]=='pending' else self.drag[0]
        distance=abs(event.position().x()-self.press_pos.x()) if self.press_pos is not None and mode in ('left','end') else (event.position()-self.press_pos).manhattanLength() if self.press_pos is not None else 0
        if self.press_pos is None or distance>QApplication.startDragDistance():
            self.gesture_moved=True
            self.toggle_off=False;self.move_to(event.position())
            if not self.edge_timer.isActive():self.edge_timer.start()

    def move_to(self,pos):
        if not self.drag or self.drag[0]=='pending':return
        mode,old,tick=self.drag;c=copy.deepcopy(old);e=self.editor
        if mode=='move':
            from .chordops import can_move_horizontal
            selected=[c for c in e.project.chords if c.id in self.drag_ids]
            if not can_move_horizontal(e.project,selected):
                self.preview=None;self.previews={};e.refresh();self.update();return
            raw=int((pos.x()-self.offset()-KEY_W+e.horizontalScrollBar().value())/e.zoom*PPQ)
            self.preview_delta=e.snapped(raw-tick);self.drop_tick=raw;c.start=old.start+self.preview_delta
            from .meter import signature
            valid=not 0<=raw<e.project.end or signature(e.project,raw)==signature(e.project,old.start)
            self.setCursor(Qt.CursorShape.ClosedHandCursor if valid else Qt.CursorShape.ForbiddenCursor)
        else:
            start=max(0,min(old.end-e.grid,e.snap_time(self.tick_at(pos.x())))) if mode=='left' else old.start
            end=min(e.project.end,max(old.start+e.grid,e.snap_time(self.tick_at(pos.x())))) if mode=='end' else old.end
            from .meter import resize_bounds
            c.start,end=resize_bounds(e.project,old,start,end);c.duration=end-c.start
        self.preview=c;self.previews={c.id:c}
        if mode=='move':
            self.previews={}
            for old_chord in self.drag_originals:
                target=copy.deepcopy(old_chord);target.start+=self.preview_delta;self.previews[target.id]=target
        e.refresh();self.update()

    def scroll_drag_edge(self):
        selecting=self.marquee is not None
        if not (selecting or self.drag and self.drag[0]!='pending') or self.last_pos is None or not QApplication.mouseButtons()&(Qt.MouseButton.LeftButton|Qt.MouseButton.RightButton) or not self.isVisible():self.edge_timer.stop();return
        x=self.last_pos.x();left=KEY_W+self.offset();right=self.width();delta=0
        if x<left+24:delta=-max(1,min(12,round((left+24-x)/2)))
        elif x>right-24:delta=max(1,min(12,round((x-right+24)/2)))
        bar=self.editor.horizontalScrollBar();before=bar.value()
        if delta:bar.setValue(before+delta);self.editor.navigationRequested.emit()
        if bar.value()!=before:
            if selecting:self.select_marquee(self.last_pos)
            else:self.move_to(self.last_pos)

    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.MiddleButton:
            self.pan_state=None;self.unsetCursor();return
        if event.button()==Qt.MouseButton.RightButton and self.right_press:
            moved=self.gesture_moved;self.right_press=False;self.edge_timer.stop();self.marquee=None;self.marquee_anchor=None;self.press_pos=None;self.unsetCursor();self.editor.refresh();self.update()
            self.context_handled=time.monotonic();self.active_menu=self.context_menu(event.position().toPoint(),preserve=moved);self.active_menu.popup(event.globalPosition().toPoint());return
        if event.button()!=Qt.MouseButton.LeftButton:return
        self.edge_timer.stop()
        self.audition_timer.stop()
        if self.audition_id:self.editor.chordAuditionReleased.emit()
        self.audition_id=''
        if self.drag and self.drag[0]=='pending' and time.monotonic()-self.press_time>=self.hold_timer.interval()/1000:
            self.last_pos=QPointF(event.position());self.begin_resize()
        self.hold_timer.stop()
        if self.preview and self.drag:
            c=self.preview;old=self.drag[1]
            if self.drag[0]=='move' and self.preview_delta:
                self.editor.chordCommand.emit('drag_move',(set(self.drag_ids),self.preview_delta,self.drop_tick))
            elif (c.start,c.duration)!=(old.start,old.duration):
                # Generate/crop MIDI only on release, never while painting a preview.
                c=resize_chord(old,c.start,c.end,project=self.editor.project)
                (self.editor.chordStructureChanged if self.structure else self.editor.chordMoved).emit(c)
        if self.collapse_click and not self.gesture_moved:
            cid=self.collapse_click;self.editor.selected_chords={cid};self.editor.selected_chord=cid;self.selection_event({cid});self.editor.chordSelected.emit(cid)
        elif self.toggle_off and not self.gesture_moved:
            self.editor.selected_chord='';self.editor.selected_chords=set();self.selection_event(set());self.editor.chordSelected.emit('')
        self.drag=None;self.preview=None;self.previews={};self.drag_originals=[];self.collapse_click=None;self.marquee=None;self.marquee_anchor=None;self.press_pos=None;self.toggle_off=False;self.unsetCursor();self.editor.refresh();self.update()

    def mouseDoubleClickEvent(self,event):
        self.hold_timer.stop()
        self.drag=None;self.preview=None;self.previews={};self.drag_originals=[];self.collapse_click=None
        if event.position().x()<KEY_W:return
        tick=self.tick_at(event.position().x())
        chord=self.editor.project.chord_at(tick)
        if chord:self.editor.chordRequested.emit(chord.id,tick)

    def context_menu(self,pos,preserve=False):
        from .model import SHARP,QUALITIES
        from .chordops import can_merge_chords,can_move_diatonic,can_apply_pattern,quality_items
        e=self.editor;raw_tick=self.tick_at(pos.x());tick=max(0,min(e.project.end-1,e.snap_time(raw_tick)))
        chord=e.project.chord_at(raw_tick) or e.project.chord_at(tick)
        e.edit_target='chords';e.elementSelection.emit('chords')
        ids=set(e.selected_chords)
        if not preserve and chord and chord.id not in ids:ids={chord.id}
        self.selection_event(ids)
        selected=sorted((c for c in e.project.chords if c.id in ids),key=lambda c:c.start)
        chord=chord or (selected[0] if selected else None)
        single=len(selected)==1;known=single and selected[0].recognized
        menu=QMenu(self);menu.setToolTipsVisible(True)
        def action(label,callback,enabled=True,key=None):
            a=menu.addAction(tr(label),callback);a.setEnabled(enabled)
            if key:menu_shortcut(a,e,key)
            return a
        self.insertion_menu(menu,tr('插入空白和弦'),tick)
        self.insertion_menu(menu,tr('在定位线处插入空白和弦'),e.position_tick())
        for label,target in [('在此粘贴和弦',tick),('在定位线处粘贴和弦',e.position_tick())]:
            allowed=getattr(e,'chord_clipboard',None)
            action(label,lambda checked=False,t=target:e.chordCommand.emit('paste',t),bool(allowed and allowed.can_paste(e.project,target)),key='paste_selection' if label=='在定位线处粘贴和弦' else None)
        menu.addSeparator()
        action('复制所选和弦',lambda:e.chordCommand.emit('copy',ids),bool(selected),key='copy_selection')
        position=e.position_tick();at=e.project.chord_at(position)
        action('在定位线处分割和弦',lambda:e.chordCommand.emit('split_at',position),bool(at and at.start<position<at.end))
        action('二等分和弦',lambda:e.chordCommand.emit('split',ids),can_split(selected),key='split')
        action('合并相邻和弦',lambda:e.chordCommand.emit('merge',ids),can_merge_chords(selected,e.project),key='merge')
        menu.addSeparator()
        action('从此和弦开始应用和弦进行…',lambda:e.chordCommand.emit('progression',selected[0].id),single)
        action('按顺序保存为和弦进行…',lambda:e.chordCommand.emit('capture_progression',ids),bool(selected) and all(c.recognized and c.notes!=[] for c in selected))
        action('检索和弦进行…',lambda:e.chordCommand.emit('search_progressions',ids),bool(selected) and all(c.recognized and c.notes!=[] for c in selected))
        menu.addSeparator();moves=menu.addMenu(tr('和弦移动'));menu.move_menu=moves
        from .chordops import can_move_horizontal
        for label,direction in [('向左移动一个格点',-1),('向右移动一个格点',1)]:
            a,b=e.bucket(max(0,min(e.project.end-1,selected[0].start if selected else tick)))
            act=moves.addAction(tr(label),lambda checked=False,d=direction,step=b-a:e.chordCommand.emit('move:'+str(d*step),ids));act.setEnabled(can_move_horizontal(e.project,selected))
            menu_shortcut(act,e,'left' if direction<0 else 'right')
        moves.addSeparator()
        for label,steps in [('根音升高半音（恢复原位）',1),('根音降低半音（恢复原位）',-1)]:
            act=moves.addAction(tr(label),lambda checked=False,v=steps:e.chordCommand.emit(f'root_step:{v}',ids));act.setEnabled(bool(selected) and all(c.recognized for c in selected))
            menu_shortcut(act,e,'up' if steps>0 else 'down')
        moves.addSeparator()
        for label,steps in [('调内上移一级',1),('调内下移一级',-1)]:
            act=moves.addAction(tr(label),lambda checked=False,v=steps:e.chordCommand.emit(f'diatonic:{v}',ids));act.setEnabled(can_move_diatonic(e.project,selected,steps));act.setToolTip(tr('调整和弦性质以保持调内，并恢复原位；节奏型和其它属性保留。'))
            menu_shortcut(act,e,'scale_up' if steps>0 else 'scale_down')
        moves.addSeparator()
        for label,delta in [('升高半音',1),('降低半音',-1),('升高八度',12),('降低八度',-12)]:
            act=moves.addAction(tr(label),lambda checked=False,d=delta:e.chordCommand.emit(f'transpose:{d}',ids));act.setEnabled(bool(selected));act.setToolTip(tr('保留实际音符并锁定为自定义节奏型。'))
        moves.setEnabled(bool(selected))
        menu.addSeparator()
        action('编辑和弦…',lambda:e.chordRequested.emit(chord.id,tick),single,key='edit_chord')
        action('在和弦钢琴卷帘中编辑',lambda:e.harmonyRequested.emit(chord.id),single)
        action('试听实际和弦',lambda:e.chordCommand.emit('audition',ids),bool(selected))
        roots=menu.addMenu(tr('和弦根音'));menu.root_menu=roots;roots.setEnabled(known)
        context=e.project.context_at(chord.start if chord else tick);tonic=context.tonic
        for label,pc in theme.pitch_class_choices(tonic,context.mode):
            a=roots.addAction(label,lambda checked=False,v=pc:e.chordCommand.emit('root:'+str(v),ids));a.setData(pc);a.setCheckable(True);a.setChecked(bool(single and chord and chord.root%12==pc))
        quick=menu.addMenu(tr('和弦性质'));menu.quality_menu=quick;quick.setEnabled(known)
        for quality,label in quality_items():
            a=quick.addAction(label,lambda checked=False,q=quality:e.chordCommand.emit('quality:'+q,ids));a.setCheckable(True);a.setChecked(bool(single and chord and chord.quality==quality))
        bass=menu.addMenu(tr('替换低音'));menu.bass_menu=bass;bass.setEnabled(known)
        for label,pc in theme.pitch_class_choices(tonic,context.mode):
            a=bass.addAction(label,lambda checked=False,v=pc:e.chordCommand.emit('bass:'+str(v),ids));a.setData(pc)
        inversion=menu.addMenu(tr('和弦转位'));menu.inversion_menu=inversion;inversion.setEnabled(known)
        tones=QUALITIES[chord.quality if chord else '']
        for index,title in enumerate(('原位','第一转位','第二转位','第三转位','第四转位')):
            available=known and index<len(tones)
            label=tr(title)+(' · '+SHARP[(chord.root+tones[index])%12] if available else '')
            a=inversion.addAction(label,lambda checked=False,i=index:e.chordCommand.emit('inversion:'+str(i),ids));a.setEnabled(available)
        patterns=menu.addMenu(tr('节奏型'));menu.pattern_menu=patterns;patterns.setEnabled(bool(selected));patterns.setToolTipsVisible(True)
        rhythms=[analyze_rhythm(c,e.project) for c in selected]
        from .rhythm import supports
        for code,label in PATTERNS.items():
            a=patterns.addAction(tr(label),lambda checked=False,c=code:e.chordCommand.emit('pattern:'+c,ids));a.setEnabled(can_apply_pattern(e.project,selected,code));a.setCheckable(True);a.setChecked(bool(rhythms) and all(r and r.pattern==code for r in rhythms))
            if not a.isEnabled():a.setToolTip(tr('更改节奏型要求所选和弦均可识别、拍号相同，且支持该节奏型。'))
            if chord and not supports(code,e.project,chord.start):a.setToolTip(tr('该节奏型不支持和弦起点的拍号。'))
        patterns.addSeparator();custom=patterns.addAction(tr('自定义'));menu.custom_rhythm_action=custom
        custom.setCheckable(True);custom.setChecked(bool(selected) and all(c.custom_rhythm for c in selected))
        custom.setToolTip(tr('勾选后不识别节奏型，移动与伸缩保留实际音符；取消后恢复动态识别。'))
        custom.triggered.connect(lambda checked:e.chordCommand.emit('custom:'+str(int(checked)),ids))
        menu.addSeparator();action('删除所选和弦',lambda:e.chordCommand.emit('delete',ids),bool(selected),key='delete')
        menu.addSeparator();menu.addAction(self.velocity_action)
        menu.action_refs=menu.actions()
        for sub in (moves,roots,quick,inversion,patterns):sub.action_refs=sub.actions()
        return menu

    def insertion_menu(self,menu,title,tick):
        sub=menu.addMenu(title)
        options=[('自动','auto')]+[(f'{n} 拍',f'beats:{n}') for n in (1,2,3)]+[(f'{n} 小节',f'bars:{n}') for n in (1,2,3,4)]
        for label,length in options:
            action=sub.addAction(tr(label),lambda checked=False,l=length:self.editor.chordCommand.emit('insert',(tick,l)))
        sub.setEnabled(0<=tick<self.editor.project.end)
        return sub

    def contextMenuEvent(self,event):
        if self.right_press or time.monotonic()-self.context_handled<.5:return
        if event.pos().x()<KEY_W:return
        self.setFocus()
        self.context_menu(event.pos()).exec(event.globalPos())

    def keyPressEvent(self,event):
        e=self.editor;e.edit_target='chords'
        if event.key()==Qt.Key.Key_Escape:
            self.edge_timer.stop();self.hold_timer.stop();self.drag=None;self.preview=None;self.previews={};self.drag_originals=[];self.collapse_click=None;self.marquee=None;self.marquee_anchor=None;self.selection_event(set());e.refresh();self.update();return
        from .keybindings import binding_owner
        if binding_owner(self) is not None:return super().keyPressEvent(event)
        if event.key() in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace):e.chordCommand.emit('delete',set(e.selected_chords));return
        if event.matches(QKeySequence.StandardKey.SelectAll):self.selection_event({c.id for c in e.project.chords});return
        super().keyPressEvent(event)

    def leaveEvent(self,event):
        self.hover_event('');super().leaveEvent(event)

    def hideEvent(self,event):
        self.pan_state=None;self.right_press=False
        self.edge_timer.stop();self.hold_timer.stop();self.audition_timer.stop()
        if self.audition_id:self.editor.chordAuditionReleased.emit()
        self.audition_id='';self.drag=None;self.preview=None;self.previews={};self.drag_originals=[];self.collapse_click=None
        self.marquee=None;self.marquee_anchor=None;self.press_pos=None;self.toggle_off=False;self.unsetCursor()
        super().hideEvent(event)


class ChordVelocityLane(QWidget):
    """One velocity per chord; explicit note dynamics are changed only on commit."""
    def __init__(self,lane):
        super().__init__(lane);self.lane=lane;self.drag_ids=set();self.value=None
        self.setToolTip(tr('拖动和弦力度柱，统一设置该和弦内所有音符的力度；多选时同时设置所选和弦。'))

    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),paint_color('#F9FBFD'));p.setFont(QFont('Segoe UI',8));p.setPen(paint_color('#8191A4'))
        p.drawText(8,18,tr('力度'));p.drawText(8,36,'1–127');p.setClipRect(KEY_W,0,self.width()-KEY_W,self.height())
        for chord in self.lane.editor.project.chords:
            x=max(KEY_W+4,self.lane.x_at(chord.start)+4)
            if self.lane.x_at(chord.end)<KEY_W or x>self.width():continue
            value=self.value if chord.id in self.drag_ids else chord.velocity
            p.setPen(QPen(paint_color('#247D6E') if chord.id in self.lane.editor.selected_chords else paint_color('#9AB4CB'),5))
            p.drawLine(QPointF(x,self.height()-4),QPointF(x,self.height()-4-value/127*(self.height()-10)))

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or event.position().x()<KEY_W:return
        e=self.lane.editor;chord=e.project.chord_at(self.lane.tick_at(event.position().x()))
        if chord:
            self.lane.setFocus();e.edit_target='chords';e.elementSelection.emit('chords')
            self.drag_ids=set(e.selected_chords) if chord.id in e.selected_chords else {chord.id}
            self.lane.selection_event(self.drag_ids);self.mouseMoveEvent(event)

    def mouseMoveEvent(self,event):
        if self.drag_ids:
            self.value=max(1,min(127,round((self.height()-4-event.position().y())/(self.height()-10)*127)));self.update()

    def mouseReleaseEvent(self,event):
        if self.drag_ids and self.value is not None:
            self.lane.editor.chordCommand.emit('velocity:'+str(self.value),set(self.drag_ids))
        self.drag_ids=set();self.value=None;self.update()

    def wheelEvent(self,event):self.lane.wheelEvent(event)


class VelocityLane(QWidget):
    """Shared time scale; choose a note first to edit voices at the same tick."""
    def __init__(self,editor):
        super().__init__(editor);self.editor=editor;self.drag_note=None
        self.setToolTip(tr('拖动力度柱调整 1–127；同一时刻多个音符时，先在网格选中要修改的音符。'))

    def paintEvent(self,event):
        e=self.editor;p=QPainter(self);p.fillRect(self.rect(),paint_color('#F9FBFD'))
        p.setFont(QFont('Segoe UI',8));p.setPen(paint_color('#8191A4'));p.drawText(8,18,tr('力度'));p.drawText(8,36,'1–127')
        p.setClipRect(KEY_W,0,self.width()-KEY_W,self.height())
        for n in e.notes:
            x=e.x_at(n.start)+4
            if not KEY_W<=x<=self.width():continue
            value=self.drag_note.velocity if self.drag_note and self.drag_note.id==n.id else n.velocity
            p.setPen(QPen(paint_color('#247D6E') if n.id==e.selected_note else paint_color('#9AB4CB'),5 if n.id==e.selected_note else 3))
            p.drawLine(QPointF(x,self.height()-4),QPointF(x,self.height()-4-value/127*(self.height()-10)))

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or event.position().x()<KEY_W:return
        e=self.editor;near=[n for n in e.notes if abs(e.x_at(n.start)+4-event.position().x())<10]
        if near:
            n=next((n for n in near if n.id==e.selected_note),near[-1]);self.drag_note=copy.deepcopy(n)
            e.selected_note=n.id;e.selected_ids={n.id};e.noteSelected.emit(n.id);self.mouseMoveEvent(event)

    def mouseMoveEvent(self,event):
        if self.drag_note:
            self.drag_note.velocity=max(1,min(127,round((self.height()-4-event.position().y())/(self.height()-10)*127)))
            self.update()

    def mouseReleaseEvent(self,event):
        if self.drag_note:
            note=self.drag_note;self.drag_note=None;self.editor.noteMoved.emit(note);self.editor.refresh()


class TimelineNavigator(QWidget):
    def __init__(self,editor):
        super().__init__(editor);self.editor=editor
        self.setToolTip(tr('导航器：点击或拖动浏览，取消跟随但不移动播放游标；Ctrl / Shift + 滚轮缩放。'))

    def segments(self):
        project=self.editor.project;width=max(1,self.width()-KEY_W);band=(self.height()-6)/2
        result=[]
        for index,notes in enumerate((project.notes,project.harmony_notes())):
            low=min((n.pitch for n in notes),default=48);high=max((n.pitch for n in notes),default=72)
            for n in notes:
                x=KEY_W+n.start/project.end*width;y=3+index*band+(high-n.pitch)/max(1,high-low)*(band-4)
                result.append((index,x,y,x+max(1,n.duration/project.end*width)))
        return result

    def paintEvent(self,event):
        e=self.editor;p=QPainter(self);width=max(1,self.width()-KEY_W)
        cached_layer(self,p,roll_view_key(e),self.paint_content)
        p.setClipRect(KEY_W,0,width,self.height());p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if e.anchor_tick is not None:
            x=KEY_W+e.anchor_tick/e.project.end*width;p.setPen(QPen(paint_color('#426BAA'),1.2,Qt.PenStyle.DashLine));p.drawLine(QPointF(x,0),QPointF(x,self.height()))
        x=KEY_W+e.cursor_tick/e.project.end*width;p.setPen(QPen(paint_color('#D15F49'),2));p.drawLine(QPointF(x,0),QPointF(x,self.height()))

    def paint_content(self,p):
        from .theme import roll_pitch_name as pitch_name,roll_degree_text as degree_text
        e=self.editor;p.fillRect(self.rect(),paint_color('#EDF2F7'));width=max(1,self.width()-KEY_W)
        p.setFont(QFont('Microsoft YaHei',7));band=(self.height()-6)/2
        for i,label in enumerate((tr('旋律'),tr('和弦'))):
            p.setPen(paint_color('#438F7E' if i==0 else '#426BAA'));p.drawText(8,round(12+i*band),label)
        p.setClipRect(KEY_W,0,width,self.height())
        for index,x,y,end in self.segments():
            p.setPen(QPen(paint_color('#438F7E' if index==0 else '#426BAA'),1.6));p.drawLine(QPointF(x,y),QPointF(end,y))
        left=e.horizontalScrollBar().value()/e.zoom*PPQ
        visible=(e.viewport().width()-KEY_W)/e.zoom*PPQ
        rect=QRectF(KEY_W+left/e.project.end*width,2,min(visible,e.project.end-left)/e.project.end*width,self.height()-4)
        p.setPen(QPen(paint_color('#44786E'),1));p.setBrush(QColor(88,158,154,35));p.drawRect(rect)

    def browse_to(self,x):
        e=self.editor;tick=max(0,(x-KEY_W)/max(1,self.width()-KEY_W)*e.project.end)
        e.horizontalScrollBar().setValue(int(tick/PPQ*e.zoom-(e.viewport().width()-KEY_W)/2));e.refresh();e.navigationRequested.emit()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.browse_to(event.position().x())

    def mouseMoveEvent(self,event):
        if event.buttons()&Qt.MouseButton.LeftButton:self.browse_to(event.position().x())

    def wheelEvent(self,event):self.editor.wheelEvent(event)


class PianoRoll(QAbstractScrollArea):
    MIN_ZOOM=32
    MAX_ZOOM=2048  # Pixels per quarter note: a 64th remains editable at 128 px.
    notesSelectionChanged=Signal()
    elementSelection=Signal(str)
    noteAdded=Signal(object)
    noteMoved=Signal(object)
    noteSelected=Signal(str)
    noteProperties=Signal(str)
    noteDeleted=Signal(str)
    chordRequested=Signal(str,int)
    deleteChord=Signal(str)
    selectionChanged=Signal(object)
    loopRangeChanged=Signal(object)
    playheadChanged=Signal(int)
    audition=Signal(object)
    auditionReleased=Signal()
    chordAuditionReleased=Signal()
    chordAuditionHeld=Signal(str)
    chordSelected=Signal(str)
    chordMoved=Signal(object)
    chordStructureChanged=Signal(object)
    harmonyRequested=Signal(str)
    notesBatch=Signal(object,object)
    viewChanged=Signal()
    timeViewChanged=Signal()
    navigationRequested=Signal()
    markerPropagationRequested=Signal(int,str)
    markerRequested=Signal(int)
    measureActivated=Signal(int)
    sectionRequested=Signal(object,str)
    insertMeasureRequested=Signal(int)
    deleteMeasuresRequested=Signal(object)
    playRequested=Signal(int)
    contextRequested=Signal(object)
    commandRequested=Signal(str,int)
    notesResized=Signal(object)
    chordCommand=Signal(str,object)
    chordSelection=Signal(object)
    chordHover=Signal(str)
    chordAudition=Signal(str)

    def __init__(self,project,parent=None,role='melody'):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.paint_revision=0;self.cache_renders=0
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.project=project;self.zoom=78;self.row_height=20
        self.role=role;self.tool='smart';self.edit_target='notes';self.selected_chord='';self.selected_ids=set();self.selected_chords=set();self.hovered_chord='';self.chord_anchor='';self.external_ruler=False;self.shared_pitches=None
        self.previews={};self.gesture_notes=[];self.marquee=None;self.has_note_clipboard=False;self.last_created=None;self.shift_pressed=False
        self.notes=project.notes if role=='melody' else project.harmony_notes()
        self.grid=240;self.grid_bars=0;self.duration=-1;self.duration_bars=0;self.previous_duration=None;self.previous_note_id='';self.granularity='grid';self.timeline_anchor=None;self.timeline_drag_state=None;self.last_note_selection=frozenset()
        self.loop_range=None;self.loop_anchor=None;self.timeline_gesture=TimelineGesture(self.viewport(),lambda:self)
        self.pan_state=None;self.right_press=False;self.context_handled=0;self.gap_click=False
        self.marquee_hold=QTimer(self);self.marquee_hold.setSingleShot(True);self.marquee_hold.setInterval(250);self.marquee_hold.timeout.connect(self.begin_marquee)
        self.selection=[[0,3840]];self.selected_note='';self.play_tick=None;self.anchor_tick=None
        self.drag=None;self.preview=None;self.hit_notes=[];self.compact=False;self.cursor_tick=0
        self.panels={'velocity':False,'chords':True,'ruler':True,'navigator':True}
        self.pitches=list(range(108,20,-1))
        self.low,self.high=21,108
        self.setViewportMargins(0,0,0,170)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.lane=ChordLane(self)
        if role=='harmony':self.lane.setParent(self.viewport())
        self.velocity_lane=VelocityLane(self);self.navigator=TimelineNavigator(self)
        self.horizontalScrollBar().valueChanged.connect(self.refresh)
        self.horizontalScrollBar().valueChanged.connect(self.viewChanged)
        self.horizontalScrollBar().valueChanged.connect(self.timeViewChanged)
        watch_scrollbar(self.horizontalScrollBar(),self.navigationRequested.emit)
        watch_scrollbar(self.verticalScrollBar(),self.navigationRequested.emit)
        self.verticalScrollBar().valueChanged.connect(self.refresh)
        self.setMinimumHeight(250)
        self.press_pos=None;self.last_pos=None;self.gesture_moved=False;self.last_delete=None
        self.edge_timer=QTimer(self);self.edge_timer.setInterval(30);self.edge_timer.timeout.connect(self.scroll_drag_edge)
        self.delete_click=False;self.structure_gesture=False;self.structure_boxes=[]
        self.update_ranges()
        self.set_panel('velocity',False)

    def set_project(self,p):
        self.project=p
        self.notes=p.notes if self.role=='melody' else p.harmony_notes()
        self.selected_ids.intersection_update(n.id for n in self.notes)
        self.selected_chords.intersection_update({c.id for c in p.chords}|getattr(self,'transient_chord_ids',set()))
        if self.selected_chord not in {c.id for c in p.chords}:self.selected_chord=''
        self.selection=[[max(0,min(a,p.end-1)),min(b,p.end)] for a,b in self.selection if a<p.end]
        if not self.selection:self.selection=[[0,p.measures[0].ticks]]
        self.update_ranges();self.refresh()

    def update_ranges(self):
        # Allow trailing viewing space, so zooming near the end does not move the anchor.
        self.horizontalScrollBar().setRange(0,max(0,int(self.project.end/PPQ*self.zoom)))
        self.horizontalScrollBar().setPageStep(self.viewport().width())
        used=self.shared_pitches if self.shared_pitches is not None else {n.pitch for n in self.notes}
        self.pitches=sorted(used or {min(108,self.project.context_at(0).tonic+12)},reverse=True) if self.compact else list(range(108,20,-1))
        self.low,self.high=min(self.pitches),max(self.pitches)
        self.verticalScrollBar().setRange(0,max(0,len(self.pitches)*self.row_height-self.viewport().height()+self.ruler_height))
        self.verticalScrollBar().setPageStep(max(1,self.viewport().height()-self.ruler_height))

    @property
    def bar_ruler_height(self):return RULER_H-RULER_TIME_H if self.panels['ruler'] else 22

    @property
    def timeline_height(self):return 0 if self.external_ruler else self.bar_ruler_height+RULER_TIME_H

    @property
    def ruler_height(self):return self.timeline_height+(62+(58 if self.lane.velocity_visible else 0) if self.role=='harmony' else 0)

    def visual_tick(self):
        clock=getattr(self,'playback_clock',None)
        return clock() if clock is not None and self.play_tick is not None else self.cursor_tick

    def position_tick(self):
        return int(self.anchor_tick if self.anchor_tick is not None else self.cursor_tick)

    def set_compact(self,value):
        self.compact=value;self.update_ranges();self.center_pitch(60);self.refresh();self.viewChanged.emit()

    def set_row_height(self,value):
        # Preserve the exact row position at the center of the note area,
        # excluding the ruler and chord structure header.
        anchor=self.vertical_anchor()
        self.row_height=value;self.update_ranges()
        self.set_vertical_anchor(anchor)
        self.has_centered_view=True;self.center_generation=getattr(self,'center_generation',0)+1
        self.refresh();self.viewChanged.emit()

    def vertical_view_key(self):
        return (self.verticalScrollBar().value(),self.row_height,self.viewport().height(),self.ruler_height,tuple(self.pitches))

    def vertical_anchor(self):
        if getattr(self,'pitch_anchor_key',None)==self.vertical_view_key():return self.pitch_anchor
        return (self.verticalScrollBar().value()+max(0,self.viewport().height()-self.ruler_height)/2)/self.row_height

    def set_vertical_anchor(self,anchor):
        middle=max(0,self.viewport().height()-self.ruler_height)/2;value=round(anchor*self.row_height-middle)
        self.verticalScrollBar().setValue(value)
        # Retain subpixel precision across successive size changes. If a range
        # boundary clamps scrolling, use the center that is actually visible.
        self.pitch_anchor=anchor if self.verticalScrollBar().value()==value else (self.verticalScrollBar().value()+middle)/self.row_height
        self.pitch_anchor_key=self.vertical_view_key()

    def set_panel(self,key,visible):
        self.panels[key]=visible
        height=sum(size for name,size in [('velocity',58),('chords',77+(58 if self.lane.velocity_visible else 0)),('navigator',33)] if self.panels[name])
        self.setMinimumHeight(self.ruler_height+height+62)
        self.setViewportMargins(0,0,0,height)
        self.layout_panels();self.update_ranges();self.refresh()

    def layout_panels(self):
        y=self.viewport().geometry().bottom()+1;w=self.viewport().width()
        for key,widget,height in [('velocity',self.velocity_lane,58),('chords',self.lane,77+(58 if self.lane.velocity_visible else 0)),('navigator',self.navigator,33)]:
            if key=='chords' and self.role=='harmony':
                widget.setGeometry(0,self.timeline_height,w,62+(58 if self.lane.velocity_visible else 0));widget.show();widget.raise_();continue
            widget.setVisible(self.panels[key])
            if self.panels[key]:widget.setGeometry(self.viewport().geometry().left(),y,w,height);y+=height

    def center_pitch(self,pitch=60):
        self.has_centered_view=True;self.center_generation=getattr(self,'center_generation',0)+1
        index=min(range(len(self.pitches)),key=lambda i:abs(self.pitches[i]-pitch))
        self.set_vertical_anchor(index+.5)

    def refresh(self,*args):
        if self.role=='harmony' and self.selected_ids:self.selected_ids=self.expand_note_selection(self.selected_ids)
        self.paint_revision+=1
        selection=frozenset(self.selected_ids)
        if selection!=self.last_note_selection:self.last_note_selection=selection;self.notesSelectionChanged.emit()
        self.viewport().update();self.lane.update();self.lane.velocity_lane.update();self.velocity_lane.update();self.navigator.update()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.layout_panels()
        self.update_ranges()

    def x_at(self,tick):
        return KEY_W+tick/PPQ*self.zoom-self.horizontalScrollBar().value()

    def zoom_at(self,factor,x=None):
        """Keep the time under x fixed; clamp at the beginning when zooming out."""
        width=max(0,self.viewport().width()-KEY_W)
        local=width/2 if x is None else max(0,min(width,x-KEY_W))
        bar=self.horizontalScrollBar();beat=(bar.value()+local)/self.zoom
        zoom=max(self.MIN_ZOOM,min(self.MAX_ZOOM,self.zoom*factor))
        if zoom==self.zoom:return
        # Linked views must only observe the final zoom and scroll together.
        blocked=bar.blockSignals(True)
        try:
            self.zoom=zoom;self.update_ranges();bar.setValue(round(beat*zoom-local))
        finally:bar.blockSignals(blocked)
        self.refresh();self.viewChanged.emit();self.timeViewChanged.emit()

    def tick_at(self,x):
        return max(0,min(self.project.end-1,int((x-KEY_W+self.horizontalScrollBar().value())/self.zoom*PPQ)))

    def y_at(self,pitch):
        index=min(range(len(self.pitches)),key=lambda i:abs(self.pitches[i]-pitch))
        return self.ruler_height+index*self.row_height-self.verticalScrollBar().value()

    def pitch_at(self,y):
        index=int((y-self.ruler_height+self.verticalScrollBar().value())//self.row_height)
        return self.pitches[max(0,min(len(self.pitches)-1,index))]

    def snapped(self,tick):
        return int(round(tick/self.grid))*self.grid

    def ensure_tick(self,tick):
        x=self.x_at(tick)
        if x>self.viewport().width()-80:self.horizontalScrollBar().setValue(int(tick/PPQ*self.zoom-self.viewport().width()/3))
        elif x<KEY_W:self.horizontalScrollBar().setValue(int(tick/PPQ*self.zoom))

    def tick_visible(self,tick):
        return KEY_W<=self.x_at(tick)<self.viewport().width()

    def ensure_selection_visible(self,dx=0,dy=0):
        """Keep one selected note visible, without centering the entire selection."""
        notes=self.selected_notes()
        self.ensure_events_visible(notes,dx,dy)

    def ensure_events_visible(self,notes,dx=0,dy=0):
        """Follow the trailing extremity, including selected elements off screen."""
        if not notes:return
        top=self.ruler_height;bottom=self.viewport().height()
        if dy and bottom-top>=self.row_height:
            rows=[self.y_at(n.pitch) for n in notes]
            if not any(top<=y and y+self.row_height<=bottom for y in rows):
                delta=min(rows)+self.row_height-bottom if dy<0 else max(rows)-top
                if (dy<0 and delta>0) or (dy>0 and delta<0):
                    bar=self.verticalScrollBar();bar.setValue(bar.value()+math.ceil(delta))
        if dx:
            left=KEY_W;right=self.viewport().width();candidates=[]
            for note in notes:
                a,b=note.start,note.end
                beat=PPQ*4/self.project.measures[self.project.measure_at(a)].denominator
                required=min((b-a)/PPQ*self.zoom,beat/PPQ*self.zoom,max(1,right-left))
                x1=self.x_at(a);x2=self.x_at(b)
                if min(x2,right)-max(x1,left)>=required-1:return
                candidates.append((x1,x2,required))
            if not candidates:return
            a,b,required=min(candidates,key=lambda c:c[0]) if dx>0 else max(candidates,key=lambda c:c[1])
            delta=a+required-right if dx>0 else b-required-left
            if (dx>0 and delta>0) or (dx<0 and delta<0):
                bar=self.horizontalScrollBar();bar.setValue(bar.value()+math.ceil(delta));self.navigationRequested.emit()

    def scroll_drag_edge(self):
        if not self.drag or self.drag[0] not in ('move','left','resize','draw','marquee') or not self.gesture_moved or self.press_pos is None or not self.isVisible() or not QApplication.mouseButtons()&(Qt.MouseButton.LeftButton|Qt.MouseButton.RightButton):
            self.edge_timer.stop();return
        pos=self.last_pos
        def speed(value,low,high,limit):
            zone=min(28,max(1,(high-low)/4))
            if value<low+zone:return -max(1,round(limit*min(1,(low+zone-value)/zone)))
            if value>high-zone:return max(1,round(limit*min(1,(value-high+zone)/zone)))
            return 0
        dx=speed(pos.x(),KEY_W,self.viewport().width(),12)
        dy=speed(pos.y(),self.ruler_height,self.viewport().height(),8) if self.drag[0] in ('move','draw','marquee') and not (self.drag[0]=='draw' and self.shift_pressed) else 0
        h=self.horizontalScrollBar();v=self.verticalScrollBar();before=(h.value(),v.value())
        h.setValue(h.value()+dx);v.setValue(v.value()+dy)
        if before!=(h.value(),v.value()):self.navigationRequested.emit()
        if before!=(h.value(),v.value()):self.move_gesture(pos)

    def hideEvent(self,event):
        self.pan_state=None;self.right_press=False;self.gap_click=False;self.timeline_gesture.cancel();self.marquee_hold.stop()
        self.edge_timer.stop()
        if self.drag or self.structure_gesture:
            self.auditionReleased.emit()
            self.drag=None;self.preview=None;self.previews={};self.marquee=None;self.press_pos=None;self.collapse_notes=None;self.delete_click=False
            self.structure_gesture=False;self.lane.hold_timer.stop();self.lane.edge_timer.stop()
            self.lane.drag=None;self.lane.preview=None;self.lane.previews={};self.lane.drag_originals=[];self.lane.collapse_click=None
            self.viewport().unsetCursor();self.refresh()
        super().hideEvent(event)

    def note_degree_label(self,pitch,start,end):
        from .theme import roll_degree_text as degree_text
        values=[];previous=None
        for context in self.project.contexts:
            if context.start>=end or context.end<=start:continue
            key=(context.tonic,context.mode)
            if key!=previous:values.append(degree_text(pitch,context.tonic,context.mode));previous=key
        if not values:
            context=self.project.context_at(start);values=[degree_text(pitch,context.tonic,context.mode)]
        return values[0]+(' ('+', '.join(values[1:])+')' if len(values)>1 else '')

    def paintEvent(self,event):
        p=QPainter(self.viewport())
        preview=(self.lane.preview.start,self.lane.preview.end) if self.lane.preview else None
        cached_layer(self,p,(roll_view_key(self),preview),self.paint_content,self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w,h=self.viewport().width(),self.viewport().height()
        p.setClipRect(KEY_W,self.ruler_height,w-KEY_W,h-self.ruler_height)
        if self.play_tick is not None:
            p.setPen(QPen(paint_color('#E9FFF8'),2));p.setBrush(Qt.BrushStyle.NoBrush)
            for rect,note in self.hit_notes:
                if note.start<=self.play_tick<note.end:
                    self.paint_note_outline(p,rect,*self.note_joins.get(note.id,(False,False)),inset=1)
        p.setClipRect(KEY_W,0,w-KEY_W,h)
        if self.anchor_tick is not None:
            x=self.x_at(self.anchor_tick);p.setPen(QPen(paint_color('#426BAA'),1.2,Qt.PenStyle.DashLine));p.drawLine(QPointF(x,0),QPointF(x,h))
        x=self.x_at(self.visual_tick());p.setPen(QPen(paint_color('#D15F49'),2));p.drawLine(QPointF(x,0),QPointF(x,h))

    def category(self,pitch,tick,pitch_sets=None):
        return colored_category(self.project.category(pitch,tick,self.role,pitch_sets),self.role)

    @staticmethod
    def paint_note_outline(painter,rect,left,right,inset=0):
        # Continue the top/bottom stroke through structural joins, without a cap.
        painter.save();painter.setClipRect(rect.adjusted(-1,-2,1,2),Qt.ClipOperation.IntersectClip)
        painter.drawRoundedRect(rect.adjusted(-5 if left else inset,inset,5 if right else -inset,-inset),3,3)
        painter.restore()

    def paint_content(self,p):
        from .theme import roll_pitch_name as pitch_name,roll_degree_text as degree_text
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w,h=self.viewport().width(),self.viewport().height()
        p.fillRect(self.viewport().rect(),paint_color('#FFFFFF'))
        left=self.tick_at(KEY_W);right=self.tick_at(w)
        pitch_sets={}
        boundaries=sorted({left,min(self.project.end,right+PPQ),*[c.start for c in self.project.contexts if left<c.start<=right],*[c.end for c in self.project.contexts if left<c.end<=right],*[c.start for c in self.project.chords if left<c.start<=right],*[c.end for c in self.project.chords if left<c.end<=right]})
        p.setClipRect(KEY_W,self.ruler_height,w-KEY_W,h-self.ruler_height)
        for pitch in self.pitches:
            y=self.y_at(pitch)
            if y+self.row_height<self.ruler_height or y>h:continue
            for a,b in zip(boundaries,boundaries[1:]):
                color=roll_color(self.category(pitch,a,pitch_sets))
                p.fillRect(QRectF(self.x_at(a),y,(b-a)/PPQ*self.zoom,self.row_height),color)
            p.setPen(QPen(paint_color('#E8EDF2'),.6));p.drawLine(QPointF(KEY_W,y+self.row_height),QPointF(w,y+self.row_height))
        for tick in self.grid_points():
            if not left-self.grid<=tick<=right+self.grid:continue
            x=self.x_at(tick);p.setPen(QPen(paint_color('#DAE2EB') if tick%PPQ==0 else paint_color('#EEF1F5'),.8 if tick%PPQ==0 else .5));p.drawLine(QPointF(x,self.ruler_height),QPointF(x,h))
        for start in self.project.starts:
            x=self.x_at(start);p.setPen(QPen(paint_color('#9BACBF'),1.3));p.drawLine(QPointF(x,self.ruler_height),QPointF(x,h))
        # Region guides belong behind notes, just like beat and bar lines.
        if self.role=='harmony':
            for original in self.project.chords:
                c=self.lane.preview_chord(original)
                for tick in (c.start,c.end):
                    x=self.x_at(tick);p.setPen(QPen(paint_color('#7BA79C'),1,Qt.PenStyle.DashLine));p.drawLine(QPointF(x,self.ruler_height),QPointF(x,h))
        for a,b in self.selection:
            p.fillRect(QRectF(self.x_at(a),self.ruler_height,(b-a)/PPQ*self.zoom,h-self.ruler_height),QColor(103,135,177,18))
        if self.role=='melody':
            highlights=getattr(self,'chord_highlights',self.selected_chords|({self.hovered_chord} if self.hovered_chord else set()))
            for chord in self.project.chords:
                if chord.id not in highlights:continue
                # Highlight chord pitch classes, including their octave equivalents.
                # The temporal boundary stays subtle; it is not a full-height wash.
                for pitch in self.pitches:
                    if pitch%12 not in chord.pcs:continue
                    rect=QRectF(self.x_at(chord.start),self.y_at(pitch),chord.duration/PPQ*self.zoom,self.row_height)
                    p.fillRect(rect,QColor(30,180,135,100));p.setPen(QPen(paint_color('#247D6E'),1.6));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRect(rect.adjusted(1,1,-1,-1))
        self.hit_notes=[];self.note_joins={}
        for old in self.gesture_notes if self.previews else ():
            current=self.previews.get(old.id)
            if current and (old.start,old.duration,old.pitch)!=(current.start,current.duration,current.pitch):
                paint_drag_ghost(p,QRectF(self.x_at(old.start)+1,self.y_at(old.pitch)+2,max(3,old.duration/PPQ*self.zoom-2),self.row_height-4))
        display=[(original,self.previews.get(original.id,self.preview if self.preview and original.id==self.preview.id else original)) for original in self.notes if not (self.drag and original.id in getattr(self,'gesture_deleted',set()))]
        if self.drag and self.drag[0]=='draw' and self.preview:display.append((self.preview,self.preview))
        # Render incoming edits on top of the old notes they will overwrite.
        display.sort(key=lambda pair:pair[0].id in self.previews or pair[1] is self.preview)
        joins=set()
        starts={(n.pitch,n.start) for _,n in display};ends={(n.pitch,n.end) for _,n in display}
        for original,note in display:
            if note.start>right+PPQ or note.end<left or not self.low<=note.pitch<=self.high:continue
            joined_left=note.start in joins and (note.pitch,note.start) in ends
            joined_right=note.end in joins and (note.pitch,note.end) in starts
            left_inset=0 if joined_left else 1;right_inset=0 if joined_right else 1
            y=self.y_at(note.pitch);rect=QRectF(self.x_at(note.start)+left_inset,y+2,max(3,note.duration/PPQ*self.zoom-left_inset-right_inset),self.row_height-4)
            if rect.bottom()<self.ruler_height or rect.top()>h:continue
            self.hit_notes.append((rect,original))
            self.note_joins[original.id]=(joined_left,joined_right)
            cuts=sorted({note.start,note.end,*[c.start for c in self.project.chords if note.start<c.start<note.end],*[c.end for c in self.project.chords if note.start<c.end<note.end],*[c.start for c in self.project.contexts if note.start<c.start<note.end]})
            path=QPainterPath();path.addRoundedRect(rect.adjusted(-3 if joined_left else 0,0,3 if joined_right else 0,0),3,3)
            p.save();p.setClipRect(rect,Qt.ClipOperation.IntersectClip);p.setClipPath(path,Qt.ClipOperation.IntersectClip)
            if original.id in self.previews:p.setOpacity(.78)
            # A single rounded silhouette; internal color changes have no gaps or corners.
            for a,b in zip(cuts,cuts[1:]):
                color=roll_color(self.category(note.pitch,a,pitch_sets),'note')
                p.fillRect(QRectF(self.x_at(a),rect.top(),max(0,(b-a)/PPQ*self.zoom),rect.height()),color)
            p.restore()
            if note.id==self.selected_note or note.id in self.selected_ids:
                p.setPen(QPen(paint_color('#1D2D44'),2));p.setBrush(Qt.BrushStyle.NoBrush);self.paint_note_outline(p,rect,joined_left,joined_right)
        if theme.SHOW_NOTE_DEGREES:
            # Paint labels after all joined fragments, so a later fragment cannot
            # erase the text spanning a bar or chord boundary. One label per shape.
            groups=[]
            for _,note in sorted(display,key=lambda pair:(pair[1].pitch,pair[1].start)):
                if groups and groups[-1][-1].pitch==note.pitch and groups[-1][-1].end==note.start and note.start in joins:groups[-1].append(note)
                else:groups.append([note])
            p.setFont(QFont('Segoe UI',9,QFont.Weight.DemiBold))
            for group in groups:
                note=group[0];end=group[-1].end;y=self.y_at(note.pitch)
                if end<left or note.start>right or y+self.row_height<self.ruler_height or y>h:continue
                label=self.note_degree_label(note.pitch,note.start,end)
                x=max(KEY_W,self.x_at(note.start)+1)+5
                rect=QRectF(x,y+2,max(0,min(w,self.x_at(end)-1)-x-3),self.row_height-4)
                p.setPen(label_color(roll_color(self.category(note.pitch,max(note.start,left),pitch_sets),'note')))
                p.drawText(rect,Qt.AlignmentFlag.AlignVCenter,label)
        if self.marquee:
            p.setPen(QPen(paint_color('#247D6E'),1,Qt.PenStyle.DashLine));p.setBrush(QColor(88,158,154,40));p.drawRect(self.marquee)
        # Keyboard is fixed while the time axis scrolls.
        p.setClipping(False);p.fillRect(QRectF(0,self.ruler_height,KEY_W,h-self.ruler_height),paint_color('#FCFDFE'))
        for pitch in self.pitches:
            y=self.y_at(pitch)
            if y<self.ruler_height-self.row_height or y>h:continue
            black=pitch%12 in (1,3,6,8,10)
            p.fillRect(QRectF(0,y,KEY_W-1,self.row_height),paint_color('#EDF1F6') if black else paint_color('#FFFFFF'))
            p.setPen(paint_color('#92A0B0') if black else paint_color('#4A5A6F'));p.setFont(QFont('Segoe UI',8))
            p.drawText(QRectF(8,y,KEY_W-12,self.row_height),Qt.AlignmentFlag.AlignVCenter,pitch_name(pitch))
            p.setPen(paint_color('#E4E9EF'));p.drawLine(QPointF(0,y+self.row_height),QPointF(KEY_W,y+self.row_height))
        if not self.external_ruler:self.paint_ruler(p,w,self.timeline_height,self.x_at)
        if self.external_ruler and self.ruler_height:
            p.fillRect(QRectF(0,0,KEY_W,self.ruler_height),paint_color('#F8FAFC'))
        self.structure_boxes=[]

    def grid_points(self):
        from .timing import grid_points
        return grid_points(self.project,self.grid,self.grid_bars)

    def snap_time(self,tick):
        from .timing import snap_time
        return snap_time(self.project,tick,self.grid,self.grid_bars)

    def bucket(self,tick):
        from .timing import grid_bucket
        return grid_bucket(self.project,tick,self.grid,self.grid_bars)

    def note_duration(self,tick):
        if self.duration==0:a,b=self.bucket(tick);return b-a
        if self.duration==-1:
            note=next((n for n in self.notes if n.id==self.previous_note_id),None)
            if note:self.remember_duration(note)
            if self.previous_duration:return self.previous_duration
            a,b=self.bucket(tick);return b-a
        if self.duration_bars:
            i=self.project.measure_at(tick);j=min(len(self.project.measures),i+self.duration_bars)
            return self.project.starts[j]-self.project.starts[i]
        return self.duration

    def remember_duration(self,note):
        """Track the last edited event, including later edits and linked fragments."""
        note=next((n for n in self.notes if n.id==note.id),None)
        if note is None:return
        self.previous_note_id=note.id
        linked=self.linked_notes(note.id)
        self.previous_duration=max(n.end for n in linked)-min(n.start for n in linked) if linked else note.duration

    def timeline_begin(self,tick,modifiers):
        from .timing import selected_measures
        bar=self.project.measure_at(tick);ctrl=bool(modifiers&Qt.KeyboardModifier.ControlModifier);shift=bool(modifiers&Qt.KeyboardModifier.ShiftModifier)
        old=set(selected_measures(self.project,self.selection)) if ctrl else set()
        anchor=self.timeline_anchor if shift and self.timeline_anchor is not None else bar
        selected=set(range(min(anchor,bar),max(anchor,bar)+1));chosen=(old^selected) if ctrl and not shift else old|selected
        self.selection=[self.project.starts[i:i+2] for i in sorted(chosen)]
        self.timeline_drag_state=(True,anchor,old,ctrl and not shift)
        if not shift:self.timeline_anchor=bar
        self.selection=merge_ranges(self.selection);self.selectionChanged.emit(self.selection);self.refresh()

    def timeline_move(self,tick):
        if self.timeline_drag_state is None:return
        whole,anchor,old,toggle=self.timeline_drag_state
        if whole:
            bar=self.project.measure_at(tick);selected=set(range(min(anchor,bar),max(anchor,bar)+1));chosen=old^selected if toggle else old|selected
            self.selection=[self.project.starts[i:i+2] for i in sorted(chosen)]
        else:
            a,b=self.bucket(tick);self.selection=[[min(anchor,a),max(self.bucket(anchor)[1],b)]]
        self.selection=merge_ranges(self.selection);self.selectionChanged.emit(self.selection);self.refresh()

    def paint_ruler(self,p,w,h,x_at):
        from .theme import roll_pitch_name as pitch_name
        p.save();p.fillRect(QRectF(0,0,w,h),paint_color('#F8FAFC'));p.setClipRect(KEY_W,0,w-KEY_W,h)
        upper=self.bar_ruler_height
        for a,b in self.selection:p.fillRect(QRectF(x_at(a),0,x_at(b)-x_at(a),upper),paint_color('#E5EDF6'))
        p.fillRect(QRectF(KEY_W,upper,w-KEY_W,h-upper),paint_color('#EDF2F7'))
        if self.loop_range:
            a,b=self.loop_range;rect=QRectF(x_at(a),upper+1,x_at(b)-x_at(a),h-upper-2)
            p.fillRect(rect,paint_color('#BBDDD3'));p.setPen(QPen(paint_color('#247D6E'),1.8))
            for tick in (a,b):p.drawLine(QPointF(x_at(tick),upper+1),QPointF(x_at(tick),h-1))
        starts=self.project.starts
        for tick in self.grid_points():
            x=x_at(tick)
            if KEY_W<=x<=w:p.setPen(QPen(paint_color('#9BACBF'),.7));p.drawLine(QPointF(x,h-10),QPointF(x,h))
        for i,(a,b) in enumerate(zip(starts,starts[1:])):
            x=x_at(a);right=x_at(b)
            if right<KEY_W or x>w:continue
            label_x=max(KEY_W,x)
            p.save();p.setClipRect(QRectF(x+2,0,max(0,right-x-5),h),Qt.ClipOperation.IntersectClip)
            p.setFont(QFont('Segoe UI',9,QFont.Weight.DemiBold));p.setPen(paint_color('#34465E'));p.drawText(QPointF(label_x+6,16),str(i+1))
            section_x=label_x+6+p.fontMetrics().horizontalAdvance(str(i+1))+10
            section=self.project.measures[i].section
            if section:
                p.setFont(QFont('Segoe UI',8,QFont.Weight.DemiBold));p.setPen(paint_color('#247D6E'))
                p.drawText(QPointF(section_x,16),p.fontMetrics().elidedText(section,Qt.TextElideMode.ElideRight,max(0,int(right-section_x-6))))
            next_label=label_x+4
            if self.project.marker_visible(i) and self.panels['ruler']:
                c=self.project.context_at(a);m=self.project.measures[i];p.setFont(QFont('Segoe UI',8));p.setPen(paint_color('#34465E'))
                p.drawText(QPointF(label_x+6,34),f'{m.numerator}/{m.denominator}')
                key_x=label_x+6+p.fontMetrics().horizontalAdvance('16/16')+12
                next_tick=min([b]+[c.start for c in self.project.contexts if a<c.start<b])
                width=max(0,min(w,x_at(next_tick))-key_x-6)
                p.drawText(QPointF(key_x,34),p.fontMetrics().elidedText(f'1={pitch_name(c.tonic)} · {c.mode}',Qt.TextElideMode.ElideRight,int(width)))
            # At fine zoom, label visible grid positions as bar.beat + fraction.
            if not self.grid_bars:
                beat=PPQ*4//self.project.measures[i].denominator
                p.setFont(QFont('Segoe UI',8));p.setPen(paint_color('#66768B'))
                step=self.grid if self.grid/PPQ*self.zoom>=48 else max(self.grid,beat)
                for tick in range(a,b,max(1,step)):
                    gx=x_at(tick)+4
                    if gx<next_label or gx>=min(w,right):continue
                    whole,remainder=divmod(tick-a,beat);fraction=Fraction(remainder,beat)
                    label=f'{i+1}.{whole+1}'+(f'+{fraction}' if remainder else '')
                    width=p.fontMetrics().horizontalAdvance(label)
                    if gx+width>min(w,right)-4:continue
                    p.drawText(QPointF(gx,upper+14),label);next_label=gx+width+12
            p.restore();p.setPen(paint_color('#C4D0DF'));p.drawLine(QPointF(x,0),QPointF(x,h))
        if self.panels['ruler']:
            for c in self.project.contexts:
                if c.start in starts:continue
                x=x_at(c.start);end=min(c.end,starts[self.project.measure_at(c.start)+1]);width=max(0,x_at(end)-x-6)
                if width<8 or x>w or x_at(end)<KEY_W:continue
                p.setFont(QFont('Segoe UI',8));p.setPen(paint_color('#927241'));p.drawLine(QPointF(x,20),QPointF(x,h))
                p.drawText(QPointF(x+3,34),p.fontMetrics().elidedText(f'1={pitch_name(c.tonic)} · {c.mode}',Qt.TextElideMode.ElideRight,int(width)))
        p.restore();p.fillRect(QRectF(0,0,KEY_W,h),paint_color('#F8FAFC'));p.setFont(QFont('Microsoft YaHei',8));p.setPen(paint_color('#78879B'));p.drawText(6,17,tr('小节'));p.drawText(6,upper+19,tr('时间尺'))
        p.setPen(QPen(paint_color('#9BACBF'),1));p.drawLine(QPointF(0,upper),QPointF(w,upper))

    def note_hit(self,pos):
        if pos.x()<KEY_W or pos.y()<self.ruler_height:return None
        clip=QRectF(KEY_W,self.ruler_height,self.viewport().width()-KEY_W,self.viewport().height()-self.ruler_height)
        self.note_groups()
        for note in reversed(self.notes):
            if note.pitch not in self.pitches:continue
            group=self._linked[note.id];a=group[0].start;b=group[-1].end
            rect=QRectF(self.x_at(a)+1,self.y_at(note.pitch)+2,max(3,(b-a)/PPQ*self.zoom-2),self.row_height-4).intersected(clip)
            if rect.contains(pos):return rect,note
        return None

    def note_groups(self):
        """The same boundary joins used for painting must behave as one selection."""
        key=(tuple((n.id,n.start,n.duration,n.pitch) for n in self.notes),tuple(self.project.starts),tuple((c.start,c.end) for c in self.project.chords))
        if getattr(self,'_groups_key',None)==key:return self._groups
        joins=set()
        groups=[]
        for n in sorted(self.notes,key=lambda n:(n.pitch,n.start)):
            if groups and groups[-1][-1].pitch==n.pitch and groups[-1][-1].end==n.start and n.start in joins:groups[-1].append(n)
            else:groups.append([n])
        self._groups_key=key;self._groups=groups;self._linked={n.id:g for g in groups for n in g}
        return groups

    def linked_notes(self,nid):
        self.note_groups();return self._linked.get(nid,[])

    def expand_note_selection(self,ids):
        self.note_groups();return {n.id for nid in ids for n in self._linked.get(nid,[])}

    def cell_interior(self,pos):
        if not (KEY_W<pos.x()<self.viewport().width() and self.ruler_height<pos.y()<self.viewport().height()):return False
        raw_tick=(pos.x()-KEY_W+self.horizontalScrollBar().value())/self.zoom*PPQ
        if not 0<=raw_tick<self.project.end:return False
        row=(pos.y()-self.ruler_height+self.verticalScrollBar().value())/self.row_height
        if not 0<=row<len(self.pitches):return False
        a,b=self.bucket(raw_tick);cell_width=(b-a)/PPQ*self.zoom
        dx=(raw_tick-a)/PPQ*self.zoom;dy=(row%1)*self.row_height
        return not self.grid_gap(pos) and min(dy,self.row_height-dy)>2

    def place_cursor(self,pos):
        if pos.x()<KEY_W:return
        if not self.bar_ruler_height<=pos.y()<self.timeline_height and (not self.grid_gap(pos) or self.note_hit(pos)):return
        last=self.grid_points()[-2]
        self.cursor_tick=max(0,min(last,self.snap_time(self.tick_at(pos.x()))))
        self.playheadChanged.emit(self.cursor_tick);self.refresh()

    def grid_gap(self,pos):
        if not (KEY_W<pos.x()<self.viewport().width() and self.ruler_height<=pos.y()<self.viewport().height()):return False
        raw=(pos.x()-KEY_W+self.horizontalScrollBar().value())/self.zoom*PPQ
        if not 0<=raw<self.project.end:return False
        a,b=self.bucket(raw);width=(b-a)/PPQ*self.zoom
        line=min((a,b),key=lambda t:abs(pos.x()-self.x_at(t)))
        base=min(2.5,width*.12)
        pitch=self.pitch_at(pos.y())
        row=[n for n in self.notes if n.pitch==pitch]
        crossing=any(n.start<line<n.end for n in row)
        left=any(n.start<line and n.end>=line for n in row)
        right=any(n.start<=line and n.end>line for n in row)
        empty_side=not (right if raw>=line else left)
        # Keep at least 76% of a narrow cell for note entry. Expand only into
        # genuinely empty space, never over a note body or a two-sided seam.
        limit=base if crossing or left and right or not empty_side else min(8,width*.12,max(base,(width-16)/2))
        return abs(pos.x()-self.x_at(line))<=limit

    def selected_notes(self):
        return [n for n in self.notes if n.id in self.selected_ids]

    def begin_marquee(self):
        if self.tool=='smart' and self.drag and self.drag[0]=='marquee' and self.press_pos is not None:
            self.gesture_moved=True;self.move_gesture(self.last_pos)

    def mousePressEvent(self,event):
        self.marquee_hold.stop()
        pos=event.position()
        if event.button()==Qt.MouseButton.MiddleButton:
            self.pan_state=(QPointF(pos),self.horizontalScrollBar().value(),self.verticalScrollBar().value());self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor);return
        if pos.y()<self.timeline_height:
            self.timeline_gesture.press(event);return
        if event.button() not in (Qt.MouseButton.LeftButton,Qt.MouseButton.RightButton):return
        self.edit_target='notes'
        self.edge_timer.stop()
        self.setFocus();pos=event.position();self.press_pos=QPointF(pos);self.last_pos=QPointF(pos);self.gesture_moved=False
        self.preview=None;self.previews={};self.drag=None;self.marquee=None;self.collapse_notes=None
        self.delete_click=False;self.structure_gesture=False;self.gap_click=False;self.right_press=event.button()==Qt.MouseButton.RightButton
        modifiers=event.modifiers();self.shift_pressed=bool(modifiers&Qt.KeyboardModifier.ShiftModifier)
        structure=next(((r,c) for r,c in self.structure_boxes if r.contains(pos)),None)
        if structure:
            self.lane.boxes=list(self.structure_boxes);self.lane.mousePressEvent(event)
            self.structure_gesture=True;self.right_press=False;self.refresh();return
        if self.right_press:
            if pos.x()<KEY_W or pos.y()<self.ruler_height:self.right_press=False;return
            if self.tool=='draw':return
            old=set(self.selected_ids) if modifiers&(Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier) else set()
            anchor=QPointF((pos.x()-KEY_W+self.horizontalScrollBar().value())/self.zoom*PPQ,(pos.y()-self.ruler_height+self.verticalScrollBar().value())/self.row_height)
            self.drag=('marquee',anchor,old);return
        self.elementSelection.emit('notes')
        if pos.x()<KEY_W:
            if pos.y()>=self.ruler_height:
                pitch=self.pitch_at(pos.y());ids={n.id for n in self.notes if n.pitch==pitch}
                if modifiers&Qt.KeyboardModifier.ControlModifier:self.selected_ids.symmetric_difference_update(ids)
                elif self.shift_pressed:self.selected_ids.update(ids)
                else:self.selected_ids=ids
                self.audition.emit([pitch]);self.refresh()
            return
        hit=self.note_hit(pos)
        if hit:
            rect,note=hit;self.selected_note=note.id
            linked=self.linked_notes(note.id);ids={n.id for n in linked}
            if modifiers&Qt.KeyboardModifier.ControlModifier:
                self.selected_ids.symmetric_difference_update(ids)
                if note.id not in self.selected_ids:self.selected_note=''
                self.refresh();return
            if not modifiers and note.id in self.selected_ids and self.selected_ids-ids:self.collapse_notes=ids.copy()
            if note.id not in self.selected_ids:self.selected_ids=ids
            else:self.selected_ids.update(ids)
            self.remember_duration(note);self.noteSelected.emit(note.id)
            self.gesture_notes=copy.deepcopy(self.selected_notes())
            edge=min(6,rect.width()/3)
            mode='resize' if pos.x()>=rect.right()-edge else 'left' if pos.x()<=rect.left()+edge else 'move'
            anchor=copy.deepcopy(note);anchor.start=min(n.start for n in linked);anchor.duration=max(n.end for n in linked)-anchor.start
            self.drag=(mode,anchor,self.tick_at(pos.x()),self.pitch_at(pos.y()))
            self.gesture_deleted=set()
            self.delete_click=self.tool=='draw' and not modifiers
            if not self.delete_click:self.audition.emit([note.pitch])
            self.refresh();return
        old=set(self.selected_ids) if modifiers&Qt.KeyboardModifier.ControlModifier else set()
        self.selected_note='';self.selected_ids=old;self.refresh()
        if pos.y()<self.ruler_height:return
        self.gap_click=self.grid_gap(pos)
        if self.tool=='smart':
            anchor=QPointF((pos.x()-KEY_W+self.horizontalScrollBar().value())/self.zoom*PPQ,(pos.y()-self.ruler_height+self.verticalScrollBar().value())/self.row_height)
            self.drag=('marquee',anchor,old);self.marquee_hold.start();return
        if self.gap_click:return
        if self.cell_interior(pos):
            start=self.bucket(self.tick_at(pos.x()))[0]
            note=Note(start,min(self.note_duration(start),self.project.end-start),self.pitch_at(pos.y()))
            self.preview=note;self.drag=('draw',copy.deepcopy(note));self.audition.emit([note.pitch]);self.refresh()

    def mouseMoveEvent(self,event):
        pos=event.position();self.last_pos=QPointF(pos);self.shift_pressed=bool(event.modifiers()&Qt.KeyboardModifier.ShiftModifier)
        if self.pan_state:
            point,h,v=self.pan_state;self.horizontalScrollBar().setValue(round(h+point.x()-pos.x()));self.verticalScrollBar().setValue(round(v+point.y()-pos.y()));self.navigationRequested.emit();return
        if self.timeline_gesture.state or pos.y()<self.timeline_height and not self.drag:
            self.timeline_gesture.move(event);return
        if self.structure_gesture:self.lane.mouseMoveEvent(event);return
        if self.press_pos:
            distance=abs(pos.x()-self.press_pos.x()) if self.drag and self.drag[0] in ('left','resize') else (pos-self.press_pos).manhattanLength()
            if distance>=4:self.gesture_moved=True
        if not self.drag:
            structure=next((r for r,c in self.structure_boxes if r.contains(pos)),None)
            if structure:
                self.viewport().setCursor(Qt.CursorShape.SizeHorCursor if min(pos.x()-structure.left(),structure.right()-pos.x())<8 else Qt.CursorShape.OpenHandCursor);return
            hit=self.note_hit(pos)
            if hit:
                rect,_=hit;edge=min(6,rect.width()/3)
                self.viewport().setCursor(Qt.CursorShape.SizeHorCursor if min(pos.x()-rect.left(),rect.right()-pos.x())<=edge else Qt.CursorShape.OpenHandCursor)
            else:self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            return
        if self.gesture_moved:
            self.move_gesture(pos)
            if self.drag[0] in ('move','left','resize','draw','marquee') and not self.edge_timer.isActive():self.edge_timer.start()

    def move_gesture(self,pos):
        if not self.drag:return
        if self.drag[0]=='marquee':
            if self.tool!='smart':return
            self.elementSelection.emit('notes');self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            anchor=self.drag[1]
            origin=QPointF(self.x_at(anchor.x()),self.ruler_height+anchor.y()*self.row_height-self.verticalScrollBar().value())
            edge=QPointF(max(KEY_W,min(self.viewport().width(),pos.x())),max(self.ruler_height,min(self.viewport().height(),pos.y())))
            self.marquee=QRectF(origin,edge).normalized()
            self.selected_ids=self.expand_note_selection(self.drag[2]|{n.id for n in self.notes if self.marquee.intersects(QRectF(self.x_at(n.start)+1,self.y_at(n.pitch)+2,max(3,n.duration/PPQ*self.zoom-2),self.row_height-4))})
            self.refresh();return
        if self.drag[0]=='draw':
            original=self.drag[1];tick=max(0,min(self.project.end,self.snap_time(self.tick_at(pos.x()))))
            self.preview.start=min(original.start,tick)
            self.preview.duration=max(self.grid,max(original.start+self.grid,tick)-self.preview.start)
            self.preview.duration=min(self.preview.duration,self.project.end-self.preview.start)
            self.preview.pitch=original.pitch if self.shift_pressed else self.pitch_at(pos.y())
            self.refresh();return
        if self.drag[0]=='timeline':self.timeline_move(self.tick_at(pos.x()));return
        if self.drag[0]=='select':
            bucket=self.bucket(self.tick_at(pos.x()));initial=self.drag[1]
            self.selection=merge_ranges(self.drag[2]+[[min(initial[0],bucket[0]),max(initial[1],bucket[1])]])
            self.selectionChanged.emit(self.selection);self.refresh();return
        mode,original,tick,pitch=self.drag;notes=self.gesture_notes
        if not notes:return
        selected={n.id for n in notes};groups=[[n for n in group if n.id in selected] for group in self.note_groups()];groups=[g for g in groups if g]
        delta=self.snap_time(original.start+self.tick_at(pos.x())-tick)-original.start
        if mode=='move':
            delta=max(-min(n.start for n in notes),min(self.project.end-max(n.end for n in notes),delta))
            change=max(21-min(n.pitch for n in notes),min(108-max(n.pitch for n in notes),self.pitch_at(pos.y())-pitch))
        elif mode=='left':delta=max(-min(n.start for n in notes),min(min(g[-1].end-g[0].start for g in groups)-self.grid,self.snap_time(self.tick_at(pos.x()))-original.start))
        else:delta=max(self.grid-min(g[-1].end-g[0].start for g in groups),min(self.project.end-max(n.end for n in notes),self.snap_time(self.tick_at(pos.x()))-original.end))
        self.previews={};self.gesture_deleted=set()
        for group in groups:
            a=group[0].start+(delta if mode=='left' else 0);b=group[-1].end+(delta if mode=='resize' else 0)
            for i,old in enumerate(group):
                note=copy.deepcopy(old)
                if mode=='move':note.start+=delta;note.pitch+=change
                else:
                    left=a if i==0 else max(a,old.start);right=b if i==len(group)-1 else min(b,old.end)
                    if left>=right:self.gesture_deleted.add(note.id);continue
                    note.start=left;note.duration=right-left
                self.previews[note.id]=note
        self.preview=self.previews.get(original.id) or next(iter(self.previews.values()),None);self.refresh()

    def mouseReleaseEvent(self,event):
        self.marquee_hold.stop()
        if event.button()==Qt.MouseButton.MiddleButton:self.pan_state=None;self.viewport().unsetCursor();return
        if self.timeline_gesture.state:
            if event.button()==Qt.MouseButton.RightButton:self.context_handled=time.monotonic()
            self.timeline_gesture.release(event);return
        if event.button() not in (Qt.MouseButton.LeftButton,Qt.MouseButton.RightButton):return
        self.edge_timer.stop()
        self.auditionReleased.emit()
        if self.structure_gesture:
            self.lane.mouseReleaseEvent(event);self.structure_gesture=False;self.press_pos=None;self.refresh();return
        drag=self.drag;preview=self.preview;previews=list(self.previews.values())
        self.drag=None;self.preview=None;self.previews={};self.marquee=None;self.viewport().unsetCursor()
        if self.right_press:
            self.right_press=False;self.context_handled=time.monotonic();self.press_pos=None
            self.active_menu=self.note_menu(event.position().toPoint(),preserve=self.gesture_moved);self.active_menu.popup(event.globalPosition().toPoint());return
        if self.gap_click and not self.gesture_moved:self.place_cursor(event.position())
        self.gap_click=False
        if self.delete_click and drag and not self.gesture_moved:
            self.last_delete=(QPointF(event.position()),time.monotonic());self.delete_linked(drag[1].id);self.press_pos=None;self.refresh();return
        if not self.gesture_moved and getattr(self,'collapse_notes',None):
            self.selected_ids=set(self.collapse_notes);self.selected_note=next(iter(self.selected_ids),'')
        if preview and drag:
            if drag[0]=='draw':
                self.last_created=(QPointF(event.position()),time.monotonic());self.noteAdded.emit(preview);self.remember_duration(preview)
            elif self.gesture_moved:
                changed=[n for n in previews if any(n.id==old.id and (n.start,n.duration,n.pitch)!=(old.start,old.duration,old.pitch) for old in self.gesture_notes)]
                if changed or getattr(self,'gesture_deleted',None):
                    if getattr(self,'gesture_deleted',None):self.notesBatch.emit(changed,list(self.gesture_deleted))
                    elif drag[0] in ('left','resize'):self.notesResized.emit(changed)
                    elif len(changed)==1:
                        self.noteMoved.emit(changed[0]);self.audition.emit([changed[0].pitch]);self.auditionReleased.emit()
                    else:self.notesBatch.emit(changed,[])
                    if changed:self.remember_duration(changed[0])
        self.press_pos=None;self.collapse_notes=None;self.refresh()

    def mouseDoubleClickEvent(self,event):
        self.marquee_hold.stop()
        if event.button()!=Qt.MouseButton.LeftButton:return
        self.edge_timer.stop()
        self.drag=None;self.preview=None;self.previews={};self.marquee=None;pos=event.position()
        if self.role=='harmony' and any(r.contains(pos) for r,_ in self.structure_boxes):
            self.lane.hold_timer.stop();self.lane.drag=None;self.structure_gesture=False
            chord=self.project.chord_at(self.tick_at(pos.x()))
            if chord:self.chordRequested.emit(chord.id,self.tick_at(pos.x()))
            return
        if self.last_delete and time.monotonic()-self.last_delete[1]<QApplication.doubleClickInterval()/1000+.1 and (pos-self.last_delete[0]).manhattanLength()<8:return
        if pos.y()<self.timeline_height and pos.x()>=KEY_W:
            self.timeline_gesture.double_click(event);return
        if self.last_created:
            point,when=self.last_created
            if time.monotonic()-when<QApplication.doubleClickInterval()/1000+.1 and (pos-point).manhattanLength()<8:return
        hit=self.note_hit(pos)
        if hit:self.delete_linked(hit[1].id)
        elif self.cell_interior(pos):
            start=self.bucket(self.tick_at(pos.x()))[0]
            note=Note(start,min(self.note_duration(start),self.project.end-start),self.pitch_at(pos.y()))
            self.noteAdded.emit(note);self.remember_duration(note)
            self.audition.emit([self.pitch_at(pos.y())])

    def selection_menu(self,menu,tick):
        notes=self.selected_notes()
        copies=menu.addMenu(tr('复制音符'));menu.copy_menu=copies;copies.setEnabled(bool(notes))
        for label,kind in [('直接复制','direct'),('复制逆行（时间反向）','retrograde'),('复制倒影（音高翻转）','inversion'),('复制逆行倒影','retrograde_inversion')]:
            a=copies.addAction(tr(label),lambda checked=False,k=kind:self.commandRequested.emit('copy:'+k,tick))
            if kind=='direct':menu_shortcut(a,self,'copy_selection')
            a.setEnabled(bool(notes) and (kind=='direct' or all((n.pitch-self.project.context_at(n.start).tonic)%12 in MODES[self.project.context_at(n.start).mode] for n in notes)))
        menu.addSeparator()
        for label,command,key in [('升高半音','chromatic:1','up'),('降低半音','chromatic:-1','down'),('调内上移一级','up','scale_up'),('调内下移一级','down','scale_down')]:
            a=menu.addAction(tr(label),lambda checked=False,c=command:self.commandRequested.emit(c,tick));a.setEnabled(bool(notes))
            menu_shortcut(a,self,key)
        for label,command,key,delta in [('上移八度','chromatic:12','octave_up',12),('下移八度','chromatic:-12','octave_down',-12)]:
            a=menu.addAction(tr(label),lambda checked=False,c=command:self.commandRequested.emit(c,tick));a.setData(key);menu_shortcut(a,self,key)
            a.setEnabled(bool(notes) and all(21<=n.pitch+delta<=108 for n in notes))
        menu.addSeparator()
        join=menu.addAction(tr('合并相邻音符'),lambda:self.commandRequested.emit('join',tick));join.setEnabled(can_join(notes) and (self.role!='harmony' or len({self.project.harmony_owner(n.id).id for n in notes})==1))
        menu_shortcut(join,self,'merge')
        quantize=menu.addAction(tr('按当前格点量化'),lambda:self.commandRequested.emit('quantize',tick));quantize.setEnabled(bool(notes))
        split=menu.addAction(tr('二等分音符'),lambda:self.commandRequested.emit('split',tick));split.setEnabled(can_split(notes,self.grid))
        menu_shortcut(split,self,'split')
        properties=menu.addAction(tr('音符属性…'),lambda:self.noteProperties.emit(notes[0].id));properties.setEnabled(len(notes)==1)
        menu.addSeparator();delete=menu.addAction(tr('删除所选音符'),lambda:self.notesBatch.emit([],list(self.selected_ids)));delete.setEnabled(bool(notes));menu.addSeparator()
        menu_shortcut(delete,self,'delete')
        paste=menu.addAction(tr('在此粘贴音符'),lambda:self.commandRequested.emit('paste',self.snap_time(tick)));paste.setEnabled(self.has_note_clipboard)
        paste=menu.addAction(tr('在定位线处粘贴音符'),lambda:self.commandRequested.emit('paste',self.position_tick()));paste.setEnabled(self.has_note_clipboard)
        menu_shortcut(paste,self,'paste_selection')
        # Keep submenu actions alive when PySide creates temporary wrappers.
        menu.action_refs=menu.actions();copies.action_refs=copies.actions()

    def timeline_menu(self,pos,preserve=False):
        tick=self.tick_at(pos.x());bar=self.project.measure_at(tick);menu=QMenu(self)
        selected=copy.deepcopy(self.selection) if self.selection and (preserve or any(a<=tick<b for a,b in self.selection)) else [self.project.starts[bar:bar+2]]
        from .timing import selected_measures
        bars=selected_measures(self.project,selected);selected=[self.project.starts[i:i+2] for i in bars]
        self.selection=selected;self.selectionChanged.emit(selected);self.refresh()
        menu.addAction(tr('设置所选小节拍号与调性…'),lambda:self.contextRequested.emit(selected))
        sections=QMenu(tr('段落标识'),menu);menu.section_menu=sections
        menu.section_action=menu.addMenu(sections);menu.section_action.setParent(menu)
        from .model import SECTIONS
        sections.addAction(tr('移除段落标识'),lambda:self.sectionRequested.emit(bars,''))
        for name in SECTIONS:sections.addAction(name,lambda checked=False,n=name:self.sectionRequested.emit(bars,n))
        source=bars[0]
        for label,kind in [('将本小节调性应用至后续所有小节','key'),('将本小节拍号应用至后续所有小节','meter')]:
            a=menu.addAction(tr(label),lambda checked=False,k=kind,i=source:self.markerPropagationRequested.emit(i,k));a.setEnabled(len(bars)==1 and source<len(self.project.measures)-1)
        menu.addSeparator()
        for label,index in [('在此小节前插入…',bar),('在此小节后插入…',bar+1)]:
            a=menu.addAction(tr(label),lambda checked=False,i=index:self.insertMeasureRequested.emit(i));a.setEnabled(len(bars)==1)
        menu.addSeparator();delete=menu.addAction(tr('删除所选小节…'),lambda:self.deleteMeasuresRequested.emit(bars));delete.setEnabled(0<len(bars)<len(self.project.measures))
        return menu

    def note_menu(self,pos,preserve=False):
        self.edit_target='notes';self.elementSelection.emit('notes');hit=self.note_hit(pos)
        if not preserve and hit and hit[1].id not in self.selected_ids:self.selected_ids=self.expand_note_selection({hit[1].id});self.selected_note=hit[1].id
        self.refresh();menu=QMenu(self);self.selection_menu(menu,self.tick_at(pos.x()));return menu

    def delete_linked(self,nid):
        ids=[n.id for n in self.linked_notes(nid)]
        if len(ids)>1:self.notesBatch.emit([],ids)
        else:self.noteDeleted.emit(nid)

    def contextMenuEvent(self,event):
        if self.right_press or self.timeline_gesture.state or time.monotonic()-self.context_handled<.5:return
        self.drag=None;self.preview=None;self.previews={};self.marquee=None
        if event.pos().x()<KEY_W:return
        if event.pos().y()<self.timeline_height:
            if event.pos().y()<self.bar_ruler_height:self.timeline_menu(event.pos()).exec(event.globalPos())
            return
        if self.role=='harmony' and any(r.contains(event.pos()) for r,_ in self.structure_boxes):self.lane.contextMenuEvent(event);return
        self.note_menu(event.pos()).exec(event.globalPos())

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:
            self.timeline_gesture.cancel();self.marquee_hold.stop();self.right_press=False;self.pan_state=None;self.gap_click=False
            self.edge_timer.stop()
            self.lane.hold_timer.stop();self.lane.edge_timer.stop();self.lane.drag=None;self.lane.preview=None;self.lane.previews={};self.lane.drag_originals=[];self.lane.collapse_click=None;self.lane.update();self.structure_gesture=False
            self.drag=None;self.preview=None;self.previews={};self.marquee=None;self.collapse_notes=None;self.selected_ids.clear();self.selected_note='';self.refresh();return
        from .keybindings import binding_owner
        if binding_owner(self) is not None:return super().keyPressEvent(event)
        if event.modifiers()&Qt.KeyboardModifier.AltModifier and event.key() in (Qt.Key.Key_Up,Qt.Key.Key_Down):
            self.commandRequested.emit('up' if event.key()==Qt.Key.Key_Up else 'down',self.cursor_tick);return
        if event.key() in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace) and self.selected_ids:self.notesBatch.emit([],list(self.selected_ids))
        elif event.key() in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace) and self.selected_note:self.noteDeleted.emit(self.selected_note)
        elif event.matches(QKeySequence.StandardKey.SelectAll):
            self.selected_ids={n.id for n in self.notes};self.refresh()
        else:super().keyPressEvent(event)

    def wheelEvent(self,event):
        if not self.time_wheel(event,event.position().x()):
            super().wheelEvent(event);self.navigationRequested.emit()

    def time_wheel(self,event,x):
        if event.modifiers()&(Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier):
            self.zoom_at(1.2**(event.angleDelta().y()/120),x);self.navigationRequested.emit();event.accept();return True
        if event.modifiers()&Qt.KeyboardModifier.AltModifier or event.angleDelta().x():
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value()-(event.angleDelta().x() or event.angleDelta().y()));self.navigationRequested.emit();event.accept();return True
        event.ignore();return False

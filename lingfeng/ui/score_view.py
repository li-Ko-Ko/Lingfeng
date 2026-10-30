from lingfeng.platform.i18n import tr
import copy,math
from PySide6.QtCore import Qt, QRectF, Signal, QPointF,QPoint,QTimer
from PySide6.QtGui import QPainter, QColor,QPen,QKeySequence,QPixmap
from PySide6.QtWidgets import QWidget, QScrollArea, QMenu,QToolTip
from lingfeng.music.chord_operations import chord_details
from lingfeng.engraving.notation import ScoreLayout, PAPER_W, PAPER_H, MARGIN
from lingfeng.ui.theme import color, is_dark
from lingfeng.music.model import PPQ
from lingfeng.engraving.presentation import contiguous, forced_row_allowed, compression_candidate, annotation_allowed, active_compressions
from lingfeng.ui.navigation import watch_scrollbar


class ScoreCanvas(QWidget):
    layoutChanged=Signal()
    noteSpelling=Signal(str,bool)
    chordSpelling=Signal(str,bool)
    measureClicked=Signal(int)
    lineBreak=Signal(int)
    playheadChanged=Signal(int)
    pasteRequested=Signal(int)
    commandRequested=Signal(str,object)
    selectionChanged=Signal()
    editorRequested=Signal(str,int)

    def __init__(self,project,parent=None,deferred=False):
        super().__init__(parent)
        self.project=copy.deepcopy(project) if not deferred else project
        self.layout=None if deferred else ScoreLayout(self.project);self.scale=.8;self.view=None;self.suspended=deferred
        self.play_tick=None;self.anchor_tick=None;self.editing=False;self.pan=None;self.grid=240;self.grid_bars=0;self.press_pos=None;self.has_note_clipboard=False
        self.page_cache={};self.cache_key=None;self.cache_renders=0
        self.selection_unit='measure';self.selected_bars=set();self.selected_beats=set();self.selection_anchor=None;self.selection_before=set();self.marquee=None
        self.hovered_chord=''
        self.setMouseTracking(True);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def rebuild(self,project):
        self.project=copy.deepcopy(project);self.layout=ScoreLayout(self.project)
        if self.project.notation.get('font_size',15)!=self.layout.font_size:
            self.project.notation['font_size']=self.layout.font_size;self.layout=ScoreLayout(self.project)
        self.cache_key=None;self.page_cache.clear()
        self.selected_bars.intersection_update(range(len(project.measures)));self.selected_beats={r for r in self.selected_beats if r[1]<=project.end};self.resize_content();self.update()
        self.layoutChanged.emit()

    def clear_layout(self):
        self.layout=None;self.page_cache.clear();self.cache_key=None
        self.selected_bars.clear();self.selected_beats.clear();self.resize_content();self.update()

    def sync_presentation(self,project,spellings=False):
        """Update document information and engraving without importing new music."""
        if self.layout is None or self.suspended:return
        metadata={key:getattr(project,key) for key in ('title','author') if getattr(self.project,key)!=getattr(project,key)}
        keys=['style','per_line','circles','color','lyrics','row_gap','system_gap','font_size','show_scale_lines']
        same_bars=self.project.starts==project.starts
        if same_bars:keys+=['forced_rows','forced_row_fonts','symbols','compressions','lyric_events','lyric_sections']
        changes={k:copy.deepcopy(project.notation.get(k)) for k in keys if self.project.notation.get(k)!=project.notation.get(k)}
        breaks=[m.break_after for m in project.measures] if same_bars else [m.break_after for m in self.project.measures]
        flats={n.id:n.flat for n in project.notes+project.chords} if spellings else {}
        spelling=[n for n in self.project.notes+self.project.chords if n.id in flats and n.flat!=flats[n.id]]
        lyrics={n.id:n.lyric for n in project.notes} if same_bars else {}
        lyric_changes=any(n.id in lyrics and n.lyric!=lyrics[n.id] for n in self.project.notes)
        if not metadata and not changes and not spelling and not lyric_changes and breaks==[m.break_after for m in self.project.measures]:return
        snapshot=copy.deepcopy(self.project)
        for key,value in metadata.items():setattr(snapshot,key,value)
        for k,v in changes.items():
            if v is None:snapshot.notation.pop(k,None)
            else:snapshot.notation[k]=v
        for m,value in zip(snapshot.measures,breaks):m.break_after=value
        for n in snapshot.notes+snapshot.chords:
            if n.id in flats:n.flat=flats[n.id]
        for n in snapshot.notes:
            if n.id in lyrics:n.lyric=lyrics[n.id]
        self.rebuild(snapshot)

    def resize_content(self,width=None):
        if width is not None:self.scale=max(.1,min(4,(width-48)/PAPER_W))
        self.setMinimumSize(math.ceil(PAPER_W*self.scale+48),math.ceil((self.layout.pages if self.layout else 1)*(PAPER_H*self.scale+28)+24))

    def page_origin(self,page):
        return (self.width()-PAPER_W*self.scale)/2,16+page*(PAPER_H*self.scale+28)

    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),color('#E9EEF4'))
        if self.layout is None or self.suspended:return
        ratio=self.devicePixelRatioF();key=(id(self.layout),self.scale,is_dark(),ratio)
        if self.cache_key!=key:
            self.page_cache={};self.cache_key=key
            self.layout.hit_notes=[];self.layout.hit_bars=[];self.layout.hit_chords=[];self.layout.hit_times=[];self.layout.hit_symbols=[]
        for page in range(self.layout.pages):
            x,y=self.page_origin(page)
            if not QRectF(x,y,PAPER_W*self.scale,PAPER_H*self.scale).intersects(QRectF(event.rect())):
                continue
            p.fillRect(QRectF(x+3,y+4,PAPER_W*self.scale,PAPER_H*self.scale),color('#DAE1E9'))
            page_rect=QRectF(x,y,PAPER_W*self.scale,PAPER_H*self.scale)
            # Cache a viewport-sized crop at the actual zoom, never a giant
            # full-page bitmap. Cursor repaints reuse it; scrolling adds margin.
            visible=QRectF(self.rect())
            if self.view:
                origin=self.mapFrom(self.view.viewport(),QPoint(0,0));visible=QRectF(origin.x(),origin.y(),self.view.viewport().width(),self.view.viewport().height())
            needed=visible.intersected(page_rect).translated(-x,-y)
            if needed.isEmpty():continue
            entry=self.page_cache.get(page)
            if entry is None or not entry[1].contains(needed):
                for name in ('hit_notes','hit_bars','hit_chords','hit_times','hit_symbols'):
                    setattr(self.layout,name,[item for item in getattr(self.layout,name) if item[0]!=page])
                if len(self.page_cache)>=4:self.page_cache.pop(next(iter(self.page_cache)))
                crop=needed.adjusted(-48,-48,48,48).intersected(QRectF(0,0,page_rect.width(),page_rect.height()))
                pixmap=QPixmap(math.ceil(crop.width()*ratio),math.ceil(crop.height()*ratio));pixmap.setDevicePixelRatio(ratio);pixmap.fill(Qt.GlobalColor.transparent)
                cached=QPainter(pixmap);cached.translate(-crop.x(),-crop.y());cached.scale(self.scale,self.scale);self.layout.draw(cached,page,dark=is_dark());cached.end();self.page_cache[page]=(pixmap,crop);self.cache_renders+=1
            pixmap,crop=self.page_cache[page]
            p.drawPixmap(QPointF(x+crop.x(),y+crop.y()),pixmap);p.save();p.translate(x,y);p.scale(self.scale,self.scale)
            tick=self.playback_clock() if self.play_tick is not None and getattr(self,'playback_clock',None) else self.play_tick
            self.layout.draw_playhead(p,page,self.anchor_tick,True);self.layout.draw_playhead(p,page,tick)
            p.setPen(QPen(color('#247D6E'),1));p.setBrush(QColor(65,145,137,35))
            for pg,rect,key in self.selection_rects():
                if pg==page and key in self.selected_units():p.drawRect(rect)
            p.restore()
        if self.marquee:p.setPen(QPen(color('#247D6E'),1,Qt.PenStyle.DashLine));p.setBrush(QColor(65,145,137,24));p.drawRect(self.marquee)

    def page_point(self,pos):
        page=int(max(0,(pos.y()-16)//(PAPER_H*self.scale+28)))
        x,y=self.page_origin(page)
        return page,QPointF((pos.x()-x)/self.scale,(pos.y()-y)/self.scale)

    def set_selection_unit(self,unit):
        self.selection_unit=unit;self.selection_anchor=None;self.selected_bars.clear();self.selected_beats.clear();self.update();self.selectionChanged.emit()

    def selected_units(self):return self.selected_bars if self.selection_unit=='measure' else self.selected_beats

    def selection_ranges(self):
        from lingfeng.music.model import merge_ranges
        return merge_ranges([self.project.starts[b:b+2] for b in self.selected_bars] if self.selection_unit=='measure' else list(self.selected_beats))

    def selection_rects(self):
        if self.layout is None:return []
        if self.selection_unit=='measure':return self.layout.hit_bars
        result=[]
        for pg,rect,bar,points,positions in self.layout.hit_times:
            def x_at(tick):
                for i,(a,b) in enumerate(zip(points,points[1:])):
                    if a<=tick<=b:return positions[i]+(positions[i+1]-positions[i])*(tick-a)/(b-a)
                return positions[-1]
            a,z=self.project.starts[bar:bar+2];beat=PPQ*4//self.project.measures[bar].denominator
            for tick in range(a,z,beat):
                end=min(z,tick+beat);left=rect.left() if tick==a else x_at(tick);right=rect.right() if end==z else x_at(end)
                result.append((pg,QRectF(left,rect.top(),right-left,rect.height()),(tick,end)))
        return result

    def unit_at(self,pos):
        page,point=self.page_point(pos)
        return next((key for pg,r,key in self.selection_rects() if pg==page and r.contains(point)),None)

    def context_menu(self,pos):
        if self.layout is None:return QMenu(self)
        page,point=self.page_point(pos)
        note_id=next((nid for pg,r,nid in reversed(self.layout.hit_notes) if pg==page and r.contains(point)),None)
        chord_id=next((cid for pg,r,cid in reversed(self.layout.hit_chords) if pg==page and r.contains(point)),None)
        bar=next((b for pg,r,b in self.layout.hit_bars if pg==page and r.contains(point)),None)
        menu=QMenu(self);menu.setToolTipsVisible(True)
        symbol=next((key for pg,r,key in reversed(self.layout.hit_symbols) if pg==page and r.contains(point)),None)
        if symbol:
            menu.addAction(tr('删除此符号并还原谱面'),lambda:self.commandRequested.emit('remove_structure',dict(bars=[],ranges=[],key=symbol)))
            return menu
        key=self.unit_at(pos)
        if key is not None and key not in self.selected_units():self.selected_units().clear();self.selected_units().add(key);self.update()
        bars=sorted(self.selected_bars) if self.selection_unit=='measure' else []
        ranges=self.selection_ranges();payload=dict(bars=bars,ranges=ranges)
        single=len(self.selected_units())==1;target=self.timeline_at(pos)
        for label,role in [('在旋律钢琴卷帘中编辑','melody'),('在和弦钢琴卷帘中编辑','chords'),('从此处编辑歌词','lyrics')]:
            a=menu.addAction(tr(label),lambda checked=False,r=role:self.editorRequested.emit(r,target[1]));a.setEnabled(target is not None and single)
        paste=menu.addAction(tr('在此粘贴音符'),lambda:self.pasteRequested.emit(target[1]));paste.setEnabled(self.has_note_clipboard and target is not None and single)
        position=self.anchor_tick if self.anchor_tick is not None else self.play_tick
        paste=menu.addAction(tr('在定位线处粘贴音符'),lambda:self.pasteRequested.emit(int(position)));paste.setEnabled(self.has_note_clipboard and position is not None and single)
        from lingfeng.ui.keybindings import menu_shortcut
        menu_shortcut(paste,self,'paste_selection')
        for label,flat in [('显示为 ♯（升号）',False),('显示为 ♭（降号）',True)]:
            a=menu.addAction(tr(label),lambda checked=False,f=flat:(self.noteSpelling if note_id else self.chordSpelling).emit(note_id or chord_id,f));a.setEnabled(single and bool(note_id or chord_id))
        line=menu.addAction(tr('在本小节后换行'),lambda:self.lineBreak.emit(bar));line.setCheckable(True);line.setChecked(bar is not None and self.project.measures[bar].break_after);line.setEnabled(single and bar is not None)
        menu.addSeparator()
        action=menu.addAction(tr('强制合并为一行'),lambda:self.commandRequested.emit('force_row',payload));action.setEnabled(forced_row_allowed(self.project,bars,self.layout.systems))
        action.setToolTip(tr('需要连续小节，且选区从当前谱行开头开始。'))
        action=menu.addAction(tr('恢复选区自动分行'),lambda:self.commandRequested.emit('auto_rows',payload));action.setEnabled(bool(bars))
        copies=menu.addMenu(tr('反复与跳转压缩'));menu.compression_menu=copies
        for label,kind in [('反复记号 · 两遍','repeat'),('D.C. al Fine','dc'),('D.S. al Fine','ds'),('D.C. N/R al Fine','dc_nr'),('D.S. N/R al Fine','ds_nr'),('尾声 · A–B–A–C','coda')]:
            candidate=compression_candidate(self.project,bars,kind);action=copies.addAction(tr(label),lambda checked=False,k=kind:self.commandRequested.emit('compress:'+k,payload))
            action.setEnabled(candidate is not None and not any(candidate['start']<old['end'] and old['start']<candidate['end'] for old in self.project.notation.get('compressions',[])))
            action.setToolTip(tr('根据两轨音符、节奏、力度及调性校验；歌词可不同，跨界延音或重复嵌套时不可用。'))
        expand=menu.addAction(tr('展开选区反复段落'),lambda:self.commandRequested.emit('expand',payload));expand.setEnabled(any(set(bars)&set(range(c['start'],c['end'])) for c in self.project.notation.get('compressions',[])))
        symbols=menu.addMenu(tr('添加谱面符号'));menu.symbol_menu=symbols
        for label,kind in [('小节线','barline'),('双小节线','double_bar'),('结束线','final_bar'),('Segno','segno'),('Coda','coda'),('F.O. · 淡出','fade'),('rit. · 渐慢','rit'),('ad lib. · 自由演奏','adlib'),('Fine','fine')]:
            action=symbols.addAction(tr(label),lambda checked=False,k=kind:self.commandRequested.emit('symbol:'+k,payload));action.setEnabled(len(ranges)==1 and annotation_allowed(self.project,kind,*ranges[0]))
            action.setToolTip(tr('演奏提示只改变谱面；终止、Fine 与淡出须位于实际音乐结尾。'))
        clear=menu.addAction(tr('清除选区符号'),lambda:self.commandRequested.emit('clear_symbols',payload));clear.setEnabled(bool(ranges))
        menu.addSeparator();delete=menu.addAction(tr('删除所选小节…'),lambda:self.commandRequested.emit('delete_bars',payload));delete.setEnabled(0<len(bars)<len(self.project.measures))
        return menu

    def contextMenuEvent(self,event):
        menu=self.context_menu(event.pos())
        if menu.actions():menu.exec(event.globalPos())

    def timeline_at(self,pos):
        if self.layout is None:return None
        page,point=self.page_point(pos)
        hit=next((item for item in self.layout.hit_times if item[0]==page and item[1].contains(point)),None)
        if not hit:return None
        _,rect,bar,points,positions=hit;x=point.x()
        tick=points[0] if x<=positions[0] else points[-1]
        for i in range(len(positions)-1):
            if positions[i]<=x<=positions[i+1]:
                tick=points[i]+(points[i+1]-points[i])*(x-positions[i])/(positions[i+1]-positions[i]);break
        from lingfeng.music.timing import grid_points, snap_time
        last=grid_points(self.project,self.grid,self.grid_bars)[-2]
        return bar,max(0,min(last,snap_time(self.project,tick,self.grid,self.grid_bars)))

    def mousePressEvent(self,event):
        if self.view and (event.button()==Qt.MouseButton.MiddleButton or event.button()==Qt.MouseButton.LeftButton and event.modifiers()&Qt.KeyboardModifier.AltModifier):
            self.pan=(event.globalPosition(),self.view.horizontalScrollBar().value(),self.view.verticalScrollBar().value(),event.button())
            self.press_pos=None;self.marquee=None;self.setCursor(Qt.CursorShape.ClosedHandCursor);event.accept();return
        if event.button()!=Qt.MouseButton.LeftButton:return
        self.setFocus();self.press_pos=event.position();self.marquee=None;self.selection_before=set(self.selected_units())

    def mouseMoveEvent(self,event):
        if self.layout is None:return
        if not self.press_pos and not self.pan:
            page,point=self.page_point(event.position())
            cid=next((cid for pg,r,cid in self.layout.hit_chords if pg==page and r.contains(point)),'')
            chord=next((c for c in self.project.chords if c.id==cid),None)
            if chord:
                target=self.timeline_at(event.position());text=chord_details(self.project,chord,target[1] if target else chord.start)
                QToolTip.showText(event.globalPosition().toPoint(),text,self);self.hovered_chord=cid
            elif self.hovered_chord:QToolTip.hideText();self.hovered_chord=''
        if self.pan:
            delta=event.globalPosition()-self.pan[0]
            self.view.horizontalScrollBar().setValue(round(self.pan[1]-delta.x()))
            self.view.verticalScrollBar().setValue(round(self.pan[2]-delta.y()))
            self.view.navigationRequested.emit()
        elif self.press_pos and (event.position()-self.press_pos).manhattanLength()>4:
            self.marquee=QRectF(self.press_pos,event.position()).normalized();selected=self.selected_units();selected.clear()
            if self.marquee.height()<1:self.marquee.setHeight(1)
            if self.marquee.width()<1:self.marquee.setWidth(1)
            if event.modifiers()&Qt.KeyboardModifier.ControlModifier:selected.update(self.selection_before)
            for pg,r,key in self.selection_rects():
                x,y=self.page_origin(pg);rect=QRectF(x+r.x()*self.scale,y+r.y()*self.scale,r.width()*self.scale,r.height()*self.scale)
                if rect.intersects(self.marquee):selected.add(key)
            self.update()

    def leaveEvent(self,event):
        self.hovered_chord='';QToolTip.hideText();super().leaveEvent(event)

    def mouseReleaseEvent(self,event):
        if self.pan and event.button()==self.pan[3]:
            self.pan=None;self.press_pos=None;self.unsetCursor();self.view.navigationRequested.emit();event.accept();return
        if event.button()!=Qt.MouseButton.LeftButton:return
        if not self.pan and not self.marquee:
            key=self.unit_at(event.position());selected=self.selected_units();modifiers=event.modifiers()
            if key is not None:
                if modifiers&Qt.KeyboardModifier.ShiftModifier and self.selection_anchor is not None:
                    selected.clear()
                    if self.selection_unit=='measure':selected.update(range(min(key,self.selection_anchor),max(key,self.selection_anchor)+1))
                    else:
                        a=min(key[0],self.selection_anchor[0]);z=max(key[1],self.selection_anchor[1])
                        for bar,m in enumerate(self.project.measures):
                            start,end=self.project.starts[bar:bar+2];step=PPQ*4//m.denominator
                            selected.update((t,min(t+step,end)) for t in range(start,end,step) if a<=t<z)
                elif modifiers&Qt.KeyboardModifier.ControlModifier:selected.symmetric_difference_update({key});self.selection_anchor=key
                else:
                    if key in selected:selected.remove(key)
                    else:selected.clear();selected.add(key)
                    self.selection_anchor=key
            elif not modifiers&(Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier):selected.clear();self.selection_anchor=None
            hit=self.timeline_at(event.position())
            if hit:
                bar,tick=hit
                if self.editing:self.measureClicked.emit(bar)
                self.playheadChanged.emit(tick)
        if self.marquee and self.selected_units():self.selection_anchor=min(self.selected_units())
        self.pan=None;self.press_pos=None;self.marquee=None;self.unsetCursor();self.update();self.selectionChanged.emit()

    def hideEvent(self,event):
        self.pan=None;self.press_pos=None;self.marquee=None;self.unsetCursor();super().hideEvent(event)

    def wheelEvent(self,event):
        if self.view and event.modifiers()&Qt.KeyboardModifier.ControlModifier:
            self.view.zoom_wheel(event);return
        event.ignore()

    def keyPressEvent(self,event):
        from lingfeng.ui.keybindings import binding_owner
        if event.key()!=Qt.Key.Key_Escape and binding_owner(self) is not None:return super().keyPressEvent(event)
        if event.key()==Qt.Key.Key_Escape:self.selected_bars.clear();self.selected_beats.clear();self.marquee=None;self.update();self.selectionChanged.emit()
        elif event.matches(QKeySequence.StandardKey.SelectAll):
            self.selected_units().update(key for _,_,key in self.selection_rects());self.update();self.selectionChanged.emit()
        else:super().keyPressEvent(event)


class ScoreView(QScrollArea):
    zoomChanged=Signal(float,str)
    navigationRequested=Signal()

    def __init__(self,project,parent=None,deferred=False):
        super().__init__(parent)
        self.zoom_mode='width';self.adjusting_zoom=False;self.fit_pending=False
        self.setWidgetResizable(True);self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignHCenter)
        self.canvas=ScoreCanvas(project,deferred=deferred);self.canvas.view=self;self.setWidget(self.canvas)
        for bar in (self.horizontalScrollBar(),self.verticalScrollBar()):
            watch_scrollbar(bar,self.navigationRequested.emit)
            bar.sliderReleased.connect(self.navigationRequested.emit)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'canvas') and self.zoom_mode!='manual':
            if not self.adjusting_zoom:self.fit_zoom()
            elif not self.fit_pending:
                self.fit_pending=True;QTimer.singleShot(0,self,self.settle_fit)

    def settle_fit(self):
        self.fit_pending=False
        if self.zoom_mode!='manual':self.fit_zoom()

    def fit_zoom(self,mode=None):
        if mode is not None:self.zoom_mode=mode
        scale=(self.viewport().width()-48)/PAPER_W
        if self.zoom_mode=='page':scale=min(scale,(self.viewport().height()-52)/PAPER_H)
        page,_=self.canvas.page_point(QPointF(self.horizontalScrollBar().value()+self.viewport().width()/2,self.verticalScrollBar().value()+self.viewport().height()/2))
        if abs(self.canvas.scale-max(.1,min(4,scale)))>1e-7 or mode is not None:
            self.set_zoom(scale,anchor=QPointF(0,0) if self.canvas.layout is None else None,mode=self.zoom_mode)
        if self.zoom_mode=='page':
            self.horizontalScrollBar().setValue(0);self.verticalScrollBar().setValue(round(self.canvas.page_origin(page)[1]-16))

    def set_zoom(self,scale,anchor=None,mode='manual'):
        scale=max(.1,min(4,float(scale)))
        point=QPointF(anchor) if anchor is not None else QPointF(self.viewport().rect().center())
        old=QPointF(self.horizontalScrollBar().value(),self.verticalScrollBar().value())+point
        page,paper=self.canvas.page_point(old)
        self.adjusting_zoom=True;self.zoom_mode=mode
        try:
            self.canvas.scale=scale;self.canvas.resize_content()
            self.canvas.resize(max(self.canvas.minimumWidth(),self.viewport().width()),max(self.canvas.minimumHeight(),self.viewport().height()))
            x,y=self.canvas.page_origin(page)
            self.horizontalScrollBar().setValue(round(x+paper.x()*scale-point.x()))
            self.verticalScrollBar().setValue(round(y+paper.y()*scale-point.y()))
        finally:self.adjusting_zoom=False
        self.canvas.update();self.zoomChanged.emit(scale,mode)

    def zoom_wheel(self,event):
        delta=event.angleDelta().y() or event.pixelDelta().y()
        if delta:
            anchor=self.viewport().mapFromGlobal(event.globalPosition().toPoint())
            self.set_zoom(self.canvas.scale*1.15**(delta/120),anchor)
            self.navigationRequested.emit()
        event.accept()

    def wheelEvent(self,event):
        if event.modifiers()&Qt.KeyboardModifier.ControlModifier:self.zoom_wheel(event)
        else:super().wheelEvent(event);self.navigationRequested.emit()

    @property
    def manual_navigation_active(self):
        """A held scrollbar or canvas pan temporarily owns the score camera."""
        return self.canvas.pan is not None or any(bar.isSliderDown() for bar in (self.horizontalScrollBar(),self.verticalScrollBar()))

    def visible_content_rect(self):
        origin=self.canvas.mapFrom(self.viewport(),QPoint(0,0))
        return QRectF(origin.x(),origin.y(),self.viewport().width(),self.viewport().height())

    def bar_visible(self,tick):
        """Whether any of the playing measure remains in the score viewport.

        bar_rect maps repeated/hidden measures through the displayed snapshot;
        unlike the cursor line, a partially visible measure keeps its camera.
        """
        if self.canvas.layout is None or not 0<=tick<self.canvas.project.end:return False
        rect=self.bar_rect(self.canvas.project.measure_at(tick))
        return rect is not None and rect.intersects(self.visible_content_rect())

    def tick_visible(self,tick):
        """Intersect the painted cursor segment with the actual scroll viewport."""
        layout=self.canvas.layout
        if layout is None or not 0<=tick<self.canvas.project.end:return False
        tick=layout.display_tick(tick);bar=self.canvas.project.measure_at(tick)
        system=next((s for s in layout.systems if bar in s.bars),None)
        if system is None:return False
        index=system.bars.index(bar);width=system.bar_widths[index]
        points,positions,*_=layout.bar_map(system,bar,0,width)
        ox,oy=self.canvas.page_origin(system.page);scale=self.canvas.scale
        x=ox+(system.left+sum(system.bar_widths[:index])+layout.interpolate(points,positions,tick))*scale
        top=oy+(system.top+28*system.layout_scale)*scale
        bottom=oy+(system.top+system.grid_bottom*system.layout_scale)*scale
        viewport=self.visible_content_rect()
        return viewport.left()<=x<viewport.right() and bottom>viewport.top() and top<viewport.bottom()

    def bar_rect(self,bar):
        layout=self.canvas.layout
        if layout is None or not 0<=bar<len(self.canvas.project.measures):return None
        bar=self.canvas.project.measure_at(layout.display_tick(self.canvas.project.starts[bar]))
        system=next((s for s in layout.systems if bar in s.bars),None)
        if system is None:return None
        index=system.bars.index(bar);ox,oy=self.canvas.page_origin(system.page);scale=self.canvas.scale
        return QRectF(ox+(system.left+sum(system.bar_widths[:index]))*scale,oy+(system.top-14)*scale,
                      system.bar_widths[index]*scale,(system.height+14)*scale)

    @staticmethod
    def reveal(scroll,low,high,size):
        current=scroll.value();margin=12
        if current<=low and high<=current+size:return
        if low<current+margin or high>current+size-margin:
            target=low-margin if high-low>size-2*margin or low<current+margin else high-size+margin
            scroll.setValue(round(target))

    def locate_bar(self,bar):
        rect=self.bar_rect(bar)
        if rect is not None:
            self.reveal(self.horizontalScrollBar(),rect.left(),rect.right(),self.viewport().width())
            self.reveal(self.verticalScrollBar(),rect.top(),rect.bottom(),self.viewport().height())
            self.canvas.update();return True
        return False

    def locate_tick(self,tick):
        layout=self.canvas.layout
        if layout is None:return
        tick=layout.display_tick(tick);bar=self.canvas.project.measure_at(tick);rect=self.bar_rect(bar)
        if rect is None:return
        system=next(s for s in layout.systems if bar in s.bars);width=system.bar_widths[system.bars.index(bar)]
        points,positions,*_=layout.bar_map(system,bar,0,width)
        x=rect.left()+layout.interpolate(points,positions,tick)*self.canvas.scale
        self.reveal(self.horizontalScrollBar(),x-4,x+4,self.viewport().width())
        self.reveal(self.verticalScrollBar(),rect.top(),rect.bottom(),self.viewport().height())

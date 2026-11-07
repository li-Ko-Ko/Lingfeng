from lingfeng.platform.i18n import tr
import copy,math
from bisect import bisect_right
from PySide6.QtCore import Qt, QRectF, Signal, QPointF,QPoint,QTimer
from PySide6.QtGui import QPainter, QColor,QPen,QKeySequence,QPixmap
from PySide6.QtWidgets import QWidget, QScrollArea, QMenu,QToolTip
from lingfeng.music.chord_operations import chord_details
from lingfeng.engraving.notation import ScoreLayout, PAPER_W, PAPER_H, MARGIN
from lingfeng.ui.theme import color, is_dark
from lingfeng.music.model import PPQ
from lingfeng.engraving.presentation import contiguous, forced_row_allowed, active_compressions, can_add_slur, slur_conflicts
from lingfeng.ui.navigation import watch_scrollbar
from lingfeng.engraving.lyrics import LYRIC_TRACK_KEYS

HIT_LISTS={'measure':'hit_bars','note':'hit_notes','time':'hit_times','chord':'hit_chords','symbol':'hit_symbols'}
HIT_BAND_HEIGHT=96


class PageHits:
    """Page-space rectangles shared by pointer queries and selection overlays."""
    def __init__(self):
        self.items={kind:[] for kind in HIT_LISTS}
        self.bands={}

    def for_unit(self,unit,starts,measures,interpolate):
        if unit not in self.items:
            beats=[]
            for page,rect,bar,points,positions in self.items['time']:
                start,end=starts[bar:bar+2];step=PPQ*4//measures[bar].denominator
                for tick in range(start,end,step):
                    stop=min(tick+step,end)
                    left=rect.left() if tick==start else interpolate(points,positions,tick)
                    right=rect.right() if stop==end else interpolate(points,positions,stop)
                    beats.append((page,QRectF(left,rect.top(),right-left,rect.height()),(tick,stop)))
            self.items['beat']=beats
        return self.items[unit]

    def near(self,kind,items,top,bottom):
        if not items:return ()
        first,last=math.floor(top/HIT_BAND_HEIGHT),math.floor(bottom/HIT_BAND_HEIGHT)
        if kind not in self.bands:
            bands={}
            for index,(_,rect,*_) in enumerate(items):
                for band in range(math.floor(rect.top()/HIT_BAND_HEIGHT),math.floor(rect.bottom()/HIT_BAND_HEIGHT)+1):
                    bands.setdefault(band,[]).append(index)
            self.bands[kind]=bands
        bands=self.bands[kind]
        if first==last:return [items[i] for i in bands.get(first,())]
        if first<=min(bands) and last>=max(bands):return items
        indices={i for band in range(first,last+1) for i in bands.get(band,())}
        return [items[i] for i in sorted(indices)]


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
        self.page_cache={};self.cache_key=None;self.cache_renders=0;self.cache_budget_bytes=24*1024*1024
        self.hit_layout=None;self.hit_pages={};self.timeline_grid=None;self.chords_by_id=None;self.note_spans=None
        self.selection_unit='measure';self.selected_bars=set();self.selected_beats=set();self.selected_notes=set();self.selection_anchor=None;self.selection_before=set();self.marquee=None
        self.hovered_chord='';self.hovered_tooltip='';self.marquee_additive=False
        self.setMouseTracking(True);self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def rebuild(self,project):
        self.project=copy.deepcopy(project);self.layout=ScoreLayout(self.project)
        self.cache_key=None;self.page_cache.clear()
        self.index_layout()
        self.selected_bars.intersection_update(range(len(project.measures)));self.selected_beats={r for r in self.selected_beats if r[1]<=project.end};self.selected_notes.intersection_update(n.id for n in project.notes+project.instrument_notes);self.resize_content();self.update()
        self.layoutChanged.emit()

    def clear_layout(self):
        self.layout=None;self.page_cache.clear();self.cache_key=None
        self.index_layout()
        self.selected_bars.clear();self.selected_beats.clear();self.selected_notes.clear();self.resize_content();self.update()

    def sync_presentation(self,project,spellings=False):
        """Update document information and engraving without importing new music."""
        if self.layout is None or self.suspended:return
        if project.notation['style']=='traditional':
            from lingfeng.engraving.compatibility import melody_overlap
            if not melody_overlap(project) and melody_overlap(self.project,project.notation):
                # A repaired melody may select traditional notation immediately;
                # the old polyphonic snapshot cannot be used for that style.
                self.rebuild(project)
                return
        metadata={key:copy.deepcopy(getattr(project,key)) for key in ('title','author','melody_names')
                  if getattr(self.project,key)!=getattr(project,key)}
        keys=['style','per_line','circles','color','lyrics','row_gap','system_gap','font_size','show_scale_lines','show_melody','show_instrument','show_chords','show_melody_lyrics','show_instrument_lyrics']
        same_bars=self.project.starts==project.starts
        if same_bars:keys+=['forced_rows','forced_row_fonts','symbols','compressions',*(key for pair in LYRIC_TRACK_KEYS for key in pair)]
        changes={k:copy.deepcopy(project.notation.get(k)) for k in keys if self.project.notation.get(k)!=project.notation.get(k)}
        breaks=[m.break_after for m in project.measures] if same_bars else [m.break_after for m in self.project.measures]
        source_notes=project.notes+project.instrument_notes
        snapshot_notes=self.project.notes+self.project.instrument_notes
        flats={n.id:n.flat for n in source_notes+project.chords} if spellings else {}
        spelling=[n for n in snapshot_notes+self.project.chords if n.id in flats and n.flat!=flats[n.id]]
        names={}
        if spellings:
            def symbol(chord):
                return chord.root,chord.quality,chord.bass,chord.recognized,chord.instrument_symbol_preference
            source_chords={chord.id:chord for chord in project.chords}
            for chord in self.project.chords:
                updated=source_chords.get(chord.id)
                if (updated and not (updated.recognition_disabled or chord.recognition_disabled)
                        and (updated.start,updated.duration)==(chord.start,chord.duration)
                        and symbol(updated)!=symbol(chord) and updated.render_notes()==chord.render_notes()):
                    names[chord.id]=symbol(updated)
        lyrics={n.id:n.lyric for n in source_notes} if same_bars else {}
        lyric_changes=any(n.id in lyrics and n.lyric!=lyrics[n.id] for n in snapshot_notes)
        if not metadata and not changes and not spelling and not names and not lyric_changes and breaks==[m.break_after for m in self.project.measures]:return
        snapshot=copy.deepcopy(self.project)
        for key,value in metadata.items():setattr(snapshot,key,value)
        for k,v in changes.items():
            if v is None:snapshot.notation.pop(k,None)
            else:snapshot.notation[k]=v
        for m,value in zip(snapshot.measures,breaks):m.break_after=value
        for n in snapshot.notes+snapshot.instrument_notes+snapshot.chords:
            if n.id in flats:n.flat=flats[n.id]
        if names:
            renamed=[c for c in snapshot.chords if c.id in names]
            for chord in renamed:
                chord.materialize()
                chord.root,chord.quality,chord.bass,chord.recognized,chord.instrument_symbol_preference=names[chord.id]
            snapshot.rescan_instrument_recognition(renamed)
        for n in snapshot.notes+snapshot.instrument_notes:
            if n.id in lyrics:n.lyric=lyrics[n.id]
        self.rebuild(snapshot)

    def resize_content(self,width=None):
        if width is not None:self.scale=max(.1,min(4,(width-48)/PAPER_W))
        self.setMinimumSize(math.ceil(PAPER_W*self.scale+48),math.ceil((self.layout.pages if self.layout else 1)*(PAPER_H*self.scale+28)+24))

    def page_origin(self,page):
        return (self.width()-PAPER_W*self.scale)/2,16+page*(PAPER_H*self.scale+28)

    @property
    def page_cache_bytes(self):
        return sum(pixmap.width()*pixmap.height()*max(1,pixmap.depth()//8) for pixmap,_ in self.page_cache.values())

    def reserve_page_cache(self,needed):
        # One physical viewport may itself exceed the budget at high DPI. Keep
        # that visible crop, but never retain additional old pages alongside it.
        while self.page_cache and (len(self.page_cache)>=4 or self.page_cache_bytes+needed>self.cache_budget_bytes):
            self.page_cache.pop(next(iter(self.page_cache)))

    def index_layout(self):
        if self.hit_layout is self.layout:return
        self.hit_layout=self.layout;self.hit_pages={};self.timeline_grid=None;self.chords_by_id=None
        self.note_order=None;self.note_spans=None;self.note_indices=None
        if self.hovered_chord:QToolTip.hideText();self.hovered_chord=''
        if self.layout is None:return
        self.score_starts=self.project.starts
        for kind,name in HIT_LISTS.items():
            for hit in getattr(self.layout,name):
                page=hit[0]
                if page not in self.hit_pages:self.hit_pages[page]=PageHits()
                self.hit_pages[page].items[kind].append(hit)

    def index_notes(self):
        if self.note_spans is not None:return
        notes=sorted(self.project.notes+self.project.instrument_notes,key=lambda n:(n.start,n.pitch,n.id))
        self.note_order=tuple(n.id for n in notes);self.note_indices={ident:i for i,ident in enumerate(self.note_order)}
        self.note_spans={n.id:(n.start,n.end) for n in notes}

    def visible_rect(self):
        return self.view.visible_content_rect() if self.view else QRectF(self.rect())

    def paper_areas(self,area):
        stride=PAPER_H*self.scale+28
        first=max(0,math.floor((area.top()-16)/stride));last=min(self.layout.pages-1,math.floor((area.bottom()-16)/stride))
        for page in range(first,last+1):
            x,y=self.page_origin(page)
            paper=QRectF((area.x()-x)/self.scale,(area.y()-y)/self.scale,area.width()/self.scale,area.height()/self.scale)
            yield page,x,y,paper

    def paint_page_crop(self,page,cached):
        previous={kind:len(getattr(self.layout,name)) for kind,name in HIT_LISTS.items()}
        self.layout.draw(cached,page,dark=is_dark())
        if page in self.hit_pages:
            # Geometry stays in paper coordinates while the raster crop moves.
            for kind,name in HIT_LISTS.items():del getattr(self.layout,name)[previous[kind]:]
        else:
            hits=PageHits();self.hit_pages[page]=hits
            for kind,name in HIT_LISTS.items():hits.items[kind].extend(getattr(self.layout,name)[previous[kind]:])

    def unit_hits(self,page,top,bottom):
        hits=self.hit_pages.get(page)
        if hits is None:return ()
        items=hits.for_unit(self.selection_unit,self.score_starts,self.project.measures,self.layout.interpolate)
        return hits.near(self.selection_unit,items,top,bottom)

    def hit_at(self,kind,page,point,reverse=False):
        hits=self.hit_pages.get(page)
        if hits is None:return None
        nearby=hits.near(kind,hits.items[kind],point.y(),point.y())
        return next((hit for hit in (reversed(nearby) if reverse else nearby) if hit[1].contains(point)),None)

    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),color('#E9EEF4'))
        if self.layout is None or self.suspended:return
        self.index_layout()
        ratio=self.devicePixelRatioF();key=(id(self.layout),self.scale,is_dark(),ratio)
        if self.cache_key!=key:
            self.page_cache={};self.cache_key=key
        visible=self.visible_rect();paper_page=QRectF(0,0,PAPER_W,PAPER_H)
        tick=self.playback_clock() if self.play_tick is not None and getattr(self,'playback_clock',None) else self.play_tick
        selected=self.selected_units()
        for page,x,y,damage in self.paper_areas(QRectF(event.rect())):
            if not paper_page.intersects(damage):continue
            p.fillRect(QRectF(x+3,y+4,PAPER_W*self.scale,PAPER_H*self.scale),color('#DAE1E9'))
            page_rect=QRectF(x,y,PAPER_W*self.scale,PAPER_H*self.scale)
            # Cache a viewport-sized crop at the actual zoom, never a giant
            # full-page bitmap. Cursor repaints reuse it; scrolling adds margin.
            needed=visible.intersected(page_rect).translated(-x,-y)
            if needed.isEmpty():continue
            entry=self.page_cache.pop(page,None)
            if entry is None or not entry[1].contains(needed):
                crop=needed.adjusted(-48,-48,48,48).intersected(QRectF(0,0,page_rect.width(),page_rect.height()))
                width,height=math.ceil(crop.width()*ratio),math.ceil(crop.height()*ratio)
                self.reserve_page_cache(width*height*4)
                pixmap=entry[0] if entry and entry[0].width()==width and entry[0].height()==height and entry[0].devicePixelRatioF()==ratio else None
                entry=None
                if pixmap is None:pixmap=QPixmap(width,height);pixmap.setDevicePixelRatio(ratio)
                pixmap.fill(Qt.GlobalColor.transparent)
                cached=QPainter(pixmap)
                try:
                    cached.translate(-crop.x(),-crop.y());cached.scale(self.scale,self.scale);self.paint_page_crop(page,cached)
                finally:cached.end()
                entry=(pixmap,crop);self.cache_renders+=1
            self.page_cache[page]=entry
            pixmap,crop=entry
            p.drawPixmap(QPointF(x+crop.x(),y+crop.y()),pixmap);p.save();p.translate(x,y);p.scale(self.scale,self.scale)
            self.layout.draw_playhead(p,page,self.anchor_tick,True);self.layout.draw_playhead(p,page,tick)
            if selected:
                p.setPen(QPen(color('#247D6E'),1));p.setBrush(QColor(65,145,137,35))
                damage=damage.adjusted(-1,-1,1,1)
                for _,rect,key in self.unit_hits(page,damage.top(),damage.bottom()):
                    if key in selected and rect.intersects(damage):p.drawRect(rect)
            p.restore()
        if self.marquee:p.setPen(QPen(color('#247D6E'),1,Qt.PenStyle.DashLine));p.setBrush(QColor(65,145,137,24));p.drawRect(self.marquee)

    def page_point(self,pos):
        page=int(max(0,(pos.y()-16)//(PAPER_H*self.scale+28)))
        x,y=self.page_origin(page)
        return page,QPointF((pos.x()-x)/self.scale,(pos.y()-y)/self.scale)

    def set_selection_unit(self,unit):
        changed=unit!=self.selection_unit or bool(self.selected_units())
        self.selection_unit=unit;self.selection_anchor=None
        self.selected_bars.clear();self.selected_beats.clear();self.selected_notes.clear()
        if changed:self.update();self.selectionChanged.emit()

    def selected_units(self):return self.selected_bars if self.selection_unit=='measure' else self.selected_notes if self.selection_unit=='note' else self.selected_beats

    def selection_ranges(self):
        from lingfeng.music.model import merge_ranges
        self.index_layout()
        if self.selection_unit=='measure':
            starts=self.score_starts if self.layout is not None else self.project.starts
            ranges=[starts[b:b+2] for b in self.selected_bars]
        elif self.selection_unit=='note':
            self.index_notes()
            ranges=[self.note_spans[key] for key in self.selected_notes if key in self.note_spans]
        else:ranges=self.selected_beats
        return merge_ranges(ranges)

    def selection_rects(self):
        if self.layout is None:return []
        if self.selection_unit!='beat':return getattr(self.layout,HIT_LISTS[self.selection_unit])
        self.index_layout()
        return [item for hits in self.hit_pages.values()
                for item in hits.for_unit('beat',self.score_starts,self.project.measures,self.layout.interpolate)]

    def select_all(self):
        selected=self.selected_units()
        added={key for _,_,key in self.selection_rects()}-selected
        if added:
            selected.update(added);self.update();self.selectionChanged.emit()

    def unit_at(self,pos):
        self.index_layout()
        page,point=self.page_point(pos)
        return next((key for _,rect,key in self.unit_hits(page,point.y(),point.y()) if rect.contains(point)),None)

    def context_menu(self,pos):
        if self.layout is None:return QMenu(self)
        self.index_layout()
        page,point=self.page_point(pos)
        def key_for(kind,reverse=False):
            hit=self.hit_at(kind,page,point,reverse)
            return hit[2] if hit else None
        note_id=key_for('note',True);chord_id=key_for('chord',True);bar=key_for('measure')
        menu=QMenu(self);menu.setToolTipsVisible(True)
        key=self.unit_at(pos)
        if key is not None and key not in self.selected_units():
            self.selected_units().clear();self.selected_units().add(key);self.update();self.selectionChanged.emit()
        bars=sorted(self.selected_bars) if self.selection_unit=='measure' else []
        ranges=self.selection_ranges();payload=dict(bars=bars,ranges=ranges,note_ids=sorted(self.selected_notes))
        single=len(self.selected_units())==1;target=self.timeline_at(pos)
        for label,role in [('在旋律卷帘中编辑','melody'),('在旋律卷帘 2 中编辑','instrument'),('在和弦卷帘中编辑','chords'),
                           ('从此处编辑歌词','lyrics'),('从此处编辑歌词 2','instrument_lyrics')]:
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
        slur=menu.addAction(tr('添加连音弧'),lambda:self.commandRequested.emit('slur',payload));slur.setEnabled(can_add_slur(self.project,self.selected_notes))
        if slur_conflicts(self.project,dict(note_ids=self.selected_notes)):slur.setToolTip(tr('歌词连音优先：所选连音弧与歌词 /- 连音冲突。'))
        symbol=key_for('symbol',True)
        if symbol is not None:
            menu.addAction(tr('删除此标识'),lambda:self.commandRequested.emit('remove_structure',dict(bars=[],ranges=[],key=symbol)))
        menu.addSeparator();delete=menu.addAction(tr('删除所选小节…'),lambda:self.commandRequested.emit('delete_bars',payload));delete.setEnabled(0<len(bars)<len(self.project.measures))
        return menu

    def contextMenuEvent(self,event):
        menu=self.context_menu(event.pos())
        if menu.actions():menu.exec(event.globalPos())

    def timeline_at(self,pos):
        if self.layout is None:return None
        self.index_layout()
        page,point=self.page_point(pos)
        hit=self.hit_at('time',page,point)
        if not hit:return None
        _,_,bar,points,positions=hit;x=point.x()
        if x<=positions[0]:tick=points[0]
        elif x>=positions[-1]:tick=points[-1]
        else:tick=self.layout.interpolate(positions,points,x)
        key=self.grid,self.grid_bars
        if self.timeline_grid is None or self.timeline_grid[0]!=key:
            from lingfeng.music.timing import grid_points
            self.timeline_grid=key,grid_points(self.project,*key)
        grid=self.timeline_grid[1]
        index=max(0,min(len(grid)-2,bisect_right(grid,tick)-1));a,b=grid[index:index+2]
        return bar,min(grid[-2],a if tick-a<b-tick else b)

    def update_chord_hover(self,event):
        page,point=self.page_point(event.position());hit=self.hit_at('chord',page,point)
        cid=hit[2] if hit else ''
        if cid==self.hovered_chord:
            if cid and not QToolTip.isVisible():QToolTip.showText(event.globalPosition().toPoint(),self.hovered_tooltip,self)
            return
        self.hovered_chord=cid
        if not cid:QToolTip.hideText();return
        if self.chords_by_id is None:self.chords_by_id={chord.id:chord for chord in self.project.chords}
        chord=self.chords_by_id.get(cid)
        if chord:
            self.hovered_tooltip=chord_details(self.project,chord)
            QToolTip.showText(event.globalPosition().toPoint(),self.hovered_tooltip,self)

    def update_marquee(self,pos,modifiers):
        old=self.marquee
        marquee=QRectF(self.press_pos,pos).normalized()
        marquee.setHeight(max(1,marquee.height()));marquee.setWidth(max(1,marquee.width()))
        additive=bool(modifiers&Qt.KeyboardModifier.ControlModifier)
        if old==marquee and self.marquee_additive==additive:return
        self.marquee=marquee;self.marquee_additive=additive
        selected=self.selected_units();keys=set(self.selection_before) if additive else set()
        for page,_,_,paper in self.paper_areas(marquee):
            keys.update(key for _,rect,key in self.unit_hits(page,paper.top(),paper.bottom()) if rect.intersects(paper))
        if keys!=selected:
            selected.clear();selected.update(keys)
            self.update(self.visible_rect().toAlignedRect())
        else:
            damage=marquee.united(old) if old is not None else marquee
            self.update(damage.toAlignedRect().adjusted(-2,-2,2,2))

    def mousePressEvent(self,event):
        if self.view and (event.button()==Qt.MouseButton.MiddleButton or event.button()==Qt.MouseButton.LeftButton and event.modifiers()&Qt.KeyboardModifier.AltModifier):
            self.pan=(event.globalPosition(),self.view.horizontalScrollBar().value(),self.view.verticalScrollBar().value(),event.button())
            self.press_pos=None;self.marquee=None;self.setCursor(Qt.CursorShape.ClosedHandCursor);event.accept();return
        if event.button()!=Qt.MouseButton.LeftButton:return
        self.setFocus();self.press_pos=event.position();self.marquee=None;self.selection_before=set(self.selected_units())

    def mouseMoveEvent(self,event):
        if self.layout is None:return
        self.index_layout()
        if self.pan:
            delta=event.globalPosition()-self.pan[0]
            self.view.horizontalScrollBar().setValue(round(self.pan[1]-delta.x()))
            self.view.verticalScrollBar().setValue(round(self.pan[2]-delta.y()))
            self.view.navigationRequested.emit()
        elif self.press_pos is None:self.update_chord_hover(event)
        elif self.marquee is not None or (event.position()-self.press_pos).manhattanLength()>4:
            self.update_marquee(event.position(),event.modifiers())

    def leaveEvent(self,event):
        self.hovered_chord='';QToolTip.hideText();super().leaveEvent(event)

    def mouseReleaseEvent(self,event):
        if self.pan and event.button()==self.pan[3]:
            self.pan=None;self.press_pos=None;self.unsetCursor();self.view.navigationRequested.emit();event.accept();return
        if event.button()!=Qt.MouseButton.LeftButton or self.press_pos is None:return
        if self.layout is not None and (self.marquee is not None or (event.position()-self.press_pos).manhattanLength()>4):
            self.index_layout();self.update_marquee(event.position(),event.modifiers())
        if not self.pan and self.marquee is None:
            key=self.unit_at(event.position());selected=self.selected_units();modifiers=event.modifiers()
            if key is not None:
                if modifiers&Qt.KeyboardModifier.ShiftModifier and self.selection_anchor is not None:
                    selected.clear()
                    if self.selection_unit=='measure':selected.update(range(min(key,self.selection_anchor),max(key,self.selection_anchor)+1))
                    elif self.selection_unit=='note':
                        self.index_notes()
                        if key in self.note_indices and self.selection_anchor in self.note_indices:
                            a,b=sorted((self.note_indices[key],self.note_indices[self.selection_anchor]))
                            selected.update(self.note_order[a:b+1])
                    else:
                        a=min(key[0],self.selection_anchor[0]);z=max(key[1],self.selection_anchor[1])
                        first=bisect_right(self.score_starts,a)-1;last=bisect_right(self.score_starts,z-1)-1
                        for bar in range(first,last+1):
                            start,end=self.score_starts[bar:bar+2];step=PPQ*4//self.project.measures[bar].denominator
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
        drag=self.marquee is not None;changed=self.selected_units()!=self.selection_before
        if drag and self.selected_units():self.selection_anchor=min(self.selected_units())
        self.pan=None;self.press_pos=None;self.marquee=None;self.unsetCursor()
        if drag or changed:self.update(self.visible_rect().toAlignedRect())
        if changed:self.selectionChanged.emit()

    def hideEvent(self,event):
        self.page_cache.clear();self.cache_key=None
        self.pan=None;self.press_pos=None;self.marquee=None;self.unsetCursor();super().hideEvent(event)

    def wheelEvent(self,event):
        if self.view and event.modifiers()&Qt.KeyboardModifier.ControlModifier:
            self.view.zoom_wheel(event);return
        event.ignore()

    def keyPressEvent(self,event):
        from lingfeng.ui.keybindings import binding_owner
        if event.key()!=Qt.Key.Key_Escape and binding_owner(self) is not None:return super().keyPressEvent(event)
        if event.key()==Qt.Key.Key_Escape:
            changed=bool(self.selected_units());drag=self.marquee is not None
            self.selected_bars.clear();self.selected_beats.clear();self.selected_notes.clear();self.marquee=None
            if changed or drag:self.update()
            if changed:self.selectionChanged.emit()
        elif event.matches(QKeySequence.StandardKey.SelectAll):
            self.select_all()
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
        raw_x=system.left+sum(system.bar_widths[:index])+layout.interpolate(points,positions,tick)
        transform=layout.system_transform(system)
        first=transform.map(QPointF(raw_x,28));last=transform.map(QPointF(raw_x,system.grid_bottom))
        x=ox+first.x()*scale;top=oy+first.y()*scale;bottom=oy+last.y()*scale
        viewport=self.visible_content_rect()
        return viewport.left()<=x<viewport.right() and bottom>viewport.top() and top<viewport.bottom()

    def bar_rect(self,bar):
        layout=self.canvas.layout
        if layout is None or not 0<=bar<len(self.canvas.project.measures):return None
        bar=self.canvas.project.measure_at(layout.display_tick(self.canvas.project.starts[bar]))
        system=next((s for s in layout.systems if bar in s.bars),None)
        if system is None:return None
        index=system.bars.index(bar);ox,oy=self.canvas.page_origin(system.page);scale=self.canvas.scale
        natural=QRectF(system.left+sum(system.bar_widths[:index]),-14,
                       system.bar_widths[index],system.natural_height+14)
        paper=layout.system_transform(system).mapRect(natural)
        return QRectF(ox+paper.x()*scale,oy+paper.y()*scale,paper.width()*scale,paper.height()*scale)

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
        raw_x=system.left+sum(system.bar_widths[:system.bars.index(bar)])+layout.interpolate(points,positions,tick)
        x=self.canvas.page_origin(system.page)[0]+layout.system_transform(system).map(QPointF(raw_x,0)).x()*self.canvas.scale
        self.reveal(self.horizontalScrollBar(),x-4,x+4,self.viewport().width())
        self.reveal(self.verticalScrollBar(),rect.top(),rect.bottom(),self.viewport().height())

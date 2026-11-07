"""Session-only edit locations; project files contain music, never widget references."""
from PySide6.QtWidgets import QApplication,QWidget
from lingfeng.music.model import Project


class HistoryState(dict):
    """A read-only project snapshot with session-only edit-location metadata.

    Consecutive snapshots reuse unchanged JSON records, without retaining the
    previous state itself. Project.from_dict deep-copies before any edit, so
    live music and restored projects never mutate these shared records.
    """
    def __init__(self,project,location,previous=None):
        super().__init__(_share_records(project,previous) if previous is not None else project)
        self.location=location


_MISSING=object()


def _share_records(value,previous):
    """Retain equal immutable-by-convention JSON subtrees and stable-ID rows."""
    if value is previous:return previous
    if isinstance(value,dict) and isinstance(previous,dict):
        if len(value)==len(previous) and all(item is previous.get(key,_MISSING) for key,item in value.items()):
            return previous
        # Notes and most chord rows contain only scalar values. This common
        # path avoids rebuilding a temporary dictionary for every unchanged row.
        if value==previous and all(not isinstance(item,(dict,list,tuple)) and type(item) is type(previous[key]) for key,item in value.items()):
            return previous
        result={};same=len(value)==len(previous)
        for key,item in value.items():
            old=previous.get(key,_MISSING);shared=_share_records(item,old)
            result[key]=shared;same=same and shared is old
        return previous if same else result
    if isinstance(value,(list,tuple)) and type(value) is type(previous):
        indexed=None
        result=[];same=len(value)==len(previous)
        for index,item in enumerate(value):
            old=previous[index] if index<len(previous) else _MISSING
            candidate=old
            if isinstance(item,dict) and isinstance(item.get('id'),str):
                if not isinstance(old,dict) or old.get('id')!=item['id']:
                    if indexed is None:
                        indexed={row['id']:row for row in previous if isinstance(row,dict) and isinstance(row.get('id'),str)}
                        if len(indexed)!=len(previous):indexed={}
                    if indexed:candidate=indexed.get(item['id'],_MISSING)
            shared=_share_records(item,candidate);result.append(shared)
            same=same and shared is old
        return previous if same else tuple(result) if isinstance(value,tuple) else result
    return previous if type(value) is type(previous) and value==previous else value


class HistoryMixin:
    def edit_dialog_origin(self):
        """Resolve the initiating editor before a modal dialog changes focus."""
        sender=self.sender()
        widget=sender if isinstance(sender,QWidget) else QApplication.focusWidget()
        roll=sender if sender in self.editing_rolls() else self.active_roll()
        window=widget.window() if isinstance(widget,QWidget) else roll.window()
        panes=(self.melody_window,self.harmony_window,self.score_tools,*self.score_floats.values(),*self.melody_floats.values())
        if window not in (self,*panes):window=roll.window()
        if window not in (self,*panes):window=self
        return window,roll

    def restore_dialog_origin(self,window,roll):
        if window.isVisible():
            window.raise_();window.activateWindow()
            if roll.isVisible() and roll.window() is window:roll.setFocus()

    def edit_surface(self,widget):
        if not isinstance(widget,QWidget) or not getattr(self,'workspace_ready',False):return None
        def within(parent):return widget is parent or parent.isAncestorOf(widget)
        if within(self.chord_lane):return 'chords'
        if within(self.timeline):return 'timeline'
        if within(self.harmony_window):return 'harmony'
        if within(self.melody_window):return 'melody'
        if any(within(pane) for pane in self.melody_floats.values()):return 'melody'
        for key,page in self.score_pages.items():
            if within(page) or within(self.score_floats[key]):return key
        if within(self.score_tools):return self.current_score_panel()
        if within(self.score_page):return 'score'
        return None

    def history_location(self,source=None):
        surface=self.edit_surface(QApplication.focusWidget())
        if isinstance(source,str):surface=source
        elif source is not None:
            if source is self.main_roll:surface='chords' if source.edit_target=='chords' else 'timeline'
            elif surface not in ('chords','timeline') or source is not self.active_roll():surface='harmony' if source is self.harmony_window.roll else 'melody'
        surface=surface or ('score' if self.workspace=='score' else getattr(self,'last_main_surface','main'))
        workspace='score' if surface in ('score','logic') or surface in self.lyric_panels else self.workspace
        roll=self.harmony_window.roll if surface=='harmony' else self.docked_roll() if surface in ('chords','timeline') else self.roll
        if surface=='melody':
            editor=source if source in self.editing_rolls() else self.active_roll()
            if editor.role=='melody':roll=editor
        notes=roll.selected_notes();chords=[c for c in self.project.chords if c.id in roll.selected_chords]
        tick=min((n.start for n in notes or chords),default=roll.position_tick())
        return dict(surface=surface,workspace=workspace,tick=tick,notes=set(roll.selected_ids),
                    chords=set(roll.selected_chords),target=roll.edit_target,melody_track=roll.melody_track if surface=='melody' else self.roll.melody_track)

    def history_roll_view(self,location):
        """Music undo keeps the note editor's current time and keyboard view."""
        if not location or location.get('target')!='notes' or location.get('surface') not in ('melody','harmony'):return None
        roll=self.harmony_window.roll if location['surface']=='harmony' else self.melody_roll_for(location.get('melody_track',0))
        anchor=roll.vertical_anchor();index=max(0,min(len(roll.pitches)-1,int(anchor)))
        return roll,roll.horizontalScrollBar().value()/roll.zoom,roll.pitches[index],anchor-index

    def restore_history_roll_view(self,view):
        roll,time,pitch,fraction=view
        # Compact-keyboard edits can insert/remove rows above the visible area.
        # Preserve a musical row and its subpixel offset, not its old row index.
        index=min(range(len(roll.pitches)),key=lambda i:abs(roll.pitches[i]-pitch))
        roll.set_vertical_anchor(index+fraction)
        roll.has_centered_view=True;roll.center_generation=getattr(roll,'center_generation',0)+1
        roll.horizontalScrollBar().setValue(round(time*roll.zoom))
        self.sync_time_views(roll);roll.refresh()

    def restore_history_location(self,location,preserve_view=False):
        if not location or not getattr(self,'workspace_ready',False):return
        surface=location['surface'];self.switch_workspace(location['workspace'])
        melody=self.melody_roll_for(location.get('melody_track',0),reveal=True) if surface=='melody' else self.roll
        window=self;focus=self;roll=None
        if self.workspace=='score':
            canvas=self.score_view.canvas
            if surface=='score' and (canvas.layout is None or canvas.project.starts!=self.project.starts):
                canvas.rebuild(self.project)
            if surface in ('melody','harmony','logic') or surface in self.lyric_panels:
                window=self.show_score_panel(surface)
                focus=self.logic_panel if surface=='logic' else self.lyric_panels.get(surface)
            else:focus=self.score_view.canvas
        elif surface in ('melody','harmony'):
            pane=self.roll_pane(melody) if surface=='melody' else self.harmony_window
            self.show_roll_in_place(pane)
            window=pane if pane.isFloating() else self
        elif surface in ('chords','timeline'):
            self.visibility_actions[surface].setChecked(True)
            focus=self.chord_lane if surface=='chords' else self.timeline
        if surface in ('melody','harmony','chords','timeline'):
            roll=self.harmony_window.roll if surface=='harmony' else self.docked_roll() if surface in ('chords','timeline') else melody
            if surface in ('melody','harmony'):focus=roll
            self.select_element(location['target'],roll)
            roll.selected_ids=location['notes']&{n.id for n in roll.notes};roll.selected_note=next(iter(roll.selected_ids),'')
            if location['target']=='chords':
                self.chord_selection(location['chords']&{c.id for c in self.project.chords},roll)
            if not preserve_view:roll.ensure_tick(min(location['tick'],self.project.end-1))
            roll.refresh()
        elif surface=='score' and not self.transport.playing:self.score_view.locate_tick(location['tick'])
        if window.isMinimized():window.showNormal()
        window.raise_();window.activateWindow()
        if focus is not None:focus.setFocus()

    def restore_history(self,history,opposite):
        self.clear_chord_move_session()
        self.commit_volume()
        if not history:return
        state=history.pop();location=getattr(state,'location',None)
        view=self.history_roll_view(location)
        opposite.append(HistoryState(self.project.to_dict(),location,opposite[-1] if opposite else state))
        playing=self.transport.playing;tick=self.transport.position() if playing else self.playhead
        self.project=Project.from_dict(state);self.dirty=True
        if playing:self.transport.revise(self.project)
        self.refresh(score_spellings=bool(location and location.get('score_spellings')));self.restore_history_location(location,preserve_view=view is not None)
        if view:self.restore_history_roll_view(view)
        if playing and not self.transport.playing:self.resume_edited_playback(tick)

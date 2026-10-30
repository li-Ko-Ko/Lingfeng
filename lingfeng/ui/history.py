"""Session-only edit locations; project files contain music, never widget references."""
from PySide6.QtWidgets import QApplication,QWidget
from lingfeng.music.model import Project


class HistoryState(dict):
    def __init__(self,project,location):
        super().__init__(project);self.location=location


class HistoryMixin:
    def edit_dialog_origin(self):
        """Resolve the initiating editor before a modal dialog changes focus."""
        sender=self.sender()
        widget=sender if isinstance(sender,QWidget) else QApplication.focusWidget()
        roll=sender if sender in (self.roll,self.main_roll,self.harmony_window.roll) else self.active_roll()
        window=widget.window() if isinstance(widget,QWidget) else roll.window()
        panes=(self.melody_window,self.harmony_window,self.score_tools,*self.score_floats.values())
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
        workspace='score' if surface in ('score','logic','lyrics') else self.workspace
        roll=self.harmony_window.roll if surface=='harmony' else self.docked_roll() if surface in ('chords','timeline') else self.roll
        notes=roll.selected_notes();chords=[c for c in self.project.chords if c.id in roll.selected_chords]
        tick=min((n.start for n in notes or chords),default=roll.position_tick())
        return dict(surface=surface,workspace=workspace,tick=tick,notes=set(roll.selected_ids),
                    chords=set(roll.selected_chords),target=roll.edit_target)

    def restore_history_location(self,location):
        if not location or not getattr(self,'workspace_ready',False):return
        surface=location['surface'];self.switch_workspace(location['workspace'])
        window=self;focus=self;roll=None
        if self.workspace=='score':
            if surface in ('melody','harmony','logic','lyrics'):
                window=self.show_score_panel(surface)
                focus=self.logic_panel if surface=='logic' else self.lyric_panel if surface=='lyrics' else None
            else:focus=self.score_view.canvas
        elif surface in ('melody','harmony'):
            pane=self.melody_window if surface=='melody' else self.harmony_window
            self.show_roll_in_place(pane)
            window=pane if pane.isFloating() else self
        elif surface in ('chords','timeline'):
            self.visibility_actions[surface].setChecked(True)
            focus=self.chord_lane if surface=='chords' else self.timeline
        if surface in ('melody','harmony','chords','timeline'):
            roll=self.harmony_window.roll if surface=='harmony' else self.docked_roll() if surface in ('chords','timeline') else self.roll
            if surface in ('melody','harmony'):focus=roll
            self.select_element(location['target'],roll)
            roll.selected_ids=location['notes']&{n.id for n in roll.notes};roll.selected_note=next(iter(roll.selected_ids),'')
            if location['target']=='chords':
                self.chord_selection(location['chords']&{c.id for c in self.project.chords},roll)
            roll.ensure_tick(min(location['tick'],self.project.end-1));roll.refresh()
        elif surface=='score' and not self.transport.playing:self.score_view.locate_tick(location['tick'])
        if window.isMinimized():window.showNormal()
        window.raise_();window.activateWindow()
        if focus is not None:focus.setFocus()

    def restore_history(self,history,opposite):
        self.clear_chord_move_session()
        self.commit_volume()
        if not history:return
        state=history.pop();location=getattr(state,'location',None)
        opposite.append(HistoryState(self.project.to_dict(),location))
        playing=self.transport.playing;tick=self.transport.position() if playing else self.playhead
        self.project=Project.from_dict(state);self.dirty=True
        if playing:self.transport.revise(self.project)
        self.refresh(score_spellings=bool(location and location.get('score_spellings')));self.restore_history_location(location)
        if playing and not self.transport.playing:self.resume_edited_playback(tick)

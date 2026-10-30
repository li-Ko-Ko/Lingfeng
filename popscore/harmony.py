from __future__ import annotations
from .i18n import tr
import copy
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QDialog,QDockWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QCheckBox,QSpinBox,QWidget,QSizePolicy
from PySide6.QtGui import QShortcut,QKeySequence,QAction
from .editor import PianoRoll
from .controls import DurationSelector,GridSelector,RollViewControls,IconButton
from .model import PATTERNS,PPQ
from .dialogs import NoteDialog
from .recognition import recognize
from .rhythm import label as rhythm_label
from .chordops import contextual_chord_name
from .layout import FlowLayout
from .workspace import FloatingPane,RollTransport,RollVolumeControls
from .editor import ChordLane


class HarmonyWindow(FloatingPane):
    """Second, nonmodal piano roll. Project and undo history belong to MainWindow."""
    def __init__(self,owner):
        super().__init__(tr('和弦钢琴卷帘'),owner,'harmony')
        self.owner=owner;self.loading=False;self.current_id='';self.initializing=True;self.view_ready=False
        self.setAllowedAreas(Qt.DockWidgetArea.BottomDockWidgetArea);self.setObjectName('harmonyDock')
        body=QWidget();self.setWidget(body);self.resize(1080,660);self.setMinimumWidth(0)
        layout=QVBoxLayout(body);layout.setContentsMargins(2,2,2,2);layout.setSpacing(3)
        self.header=QWidget();top=QHBoxLayout(self.header);top.setContentsMargins(5,0,0,0);top.setSpacing(8);title=QLabel(tr('和弦钢琴卷帘'));title.setStyleSheet('font-weight:600');top.addWidget(title)
        self.summary=QLabel();self.summary.setMinimumWidth(0);self.summary.setMaximumWidth(180);self.summary.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Preferred);top.addWidget(self.summary)
        self.sync=QAction(tr('同步时间轴'),self);self.sync.setCheckable(True)
        self.sync.setToolTip(tr('同步主界面的滚动、缩放与跟随播放游标；取消后独立控制。'))
        self.sync.toggled.connect(lambda value:owner.set_timeline_sync(value,self.roll))
        self.topLevelChanged.connect(self.sync_position)
        top.addStretch();self.float_button=IconButton('float');self.float_button.activated.connect(lambda:owner.toggle_roll_floating(self));top.addWidget(self.float_button);layout.addWidget(self.header)
        self.hide_button=IconButton('close');self.hide_button.setToolTip(tr('隐藏和弦卷帘'));self.hide_button.setAccessibleName(tr('隐藏和弦卷帘'));self.hide_button.activated.connect(lambda:owner.visibility_actions['harmony'].setChecked(False));top.addWidget(self.hide_button)
        self.toolbar=QWidget();tools=FlowLayout(self.toolbar);tools.setContentsMargins(0,0,0,0);self.tool=QComboBox()
        for label,value in [(tr('智能工具'),'smart'),(tr('绘制工具'),'draw')]:self.tool.addItem(label,value)
        tools.addWidget(self.tool);tools.addWidget(QLabel(tr('时值')));self.length=DurationSelector();self.dotted=self.length.dotted_action;self.length.currentIndexChanged.connect(self.set_duration);tools.addWidget(self.length);self.grid=GridSelector()
        tools.addStretch();layout.addWidget(self.toolbar)
        self.roll=PianoRoll(owner.project,role='harmony');self.roll.set_panel('velocity',False);self.roll.set_panel('navigator',False);self.top_lane=self.roll.lane;layout.addWidget(self.roll,1)
        self.transport_controls=RollTransport(owner);layout.insertWidget(1,self.transport_controls)
        self.volume_controls=RollVolumeControls(owner);layout.addWidget(self.volume_controls)
        self.play_button=self.transport_controls.play;self.replay_button=self.transport_controls.replay
        self.inspector=QWidget();bottom=FlowLayout(self.inspector);bottom.setContentsMargins(0,0,0,0);bottom.addWidget(QLabel(tr('识别候选')));self.candidates=QComboBox();self.candidates.setMinimumWidth(100);bottom.addWidget(self.candidates)
        choose=QPushButton(tr('采用标记'));choose.clicked.connect(self.choose_candidate);bottom.addWidget(choose)
        bottom.addStretch()
        clear=QPushButton(tr('清空当前和弦音符'));clear.clicked.connect(self.clear_notes);bottom.addWidget(clear);layout.insertWidget(layout.indexOf(self.roll),self.inspector)
        views=FlowLayout();self.view_controls=RollViewControls(self.roll);tools.addWidget(QLabel(tr('吸附')));tools.addWidget(self.grid);tools.addWidget(self.view_controls);self.view_controls.options.hide();views.addStretch()
        fold=self.view_controls.visibility_menu.addAction(tr('和弦识别'));fold.setCheckable(True);fold.setChecked(False);fold.toggled.connect(self.inspector.setVisible);self.recognition_action=fold;self.inspector.setVisible(False)
        options=self.transport_controls.options.menu();options.addAction(self.sync);options.addSeparator()
        options.addAction(self.roll.lane.velocity_action)
        for key in ('velocity','ruler'):options.addAction(self.view_controls.panel_actions[key])
        options.addAction(self.recognition_action)
        self.tool.currentIndexChanged.connect(lambda:setattr(self.roll,'tool',self.tool.currentData()))
        self.grid.currentIndexChanged.connect(self.set_grid)
        self.roll.noteAdded.connect(self.change_note);self.roll.noteMoved.connect(self.change_note)
        self.roll.notesResized.connect(lambda notes:owner.edit_notes(self.roll,notes,[],overwrite=True))
        self.roll.commandRequested.connect(lambda command,tick:owner.note_command(self.roll,command,tick))
        self.roll.noteDeleted.connect(lambda nid:owner.edit_notes(self.roll,[],[nid]));self.roll.notesBatch.connect(lambda a,d:owner.edit_notes(self.roll,a,d))
        self.roll.noteProperties.connect(self.note_properties);self.roll.noteSelected.connect(self.note_selected)
        self.roll.chordSelected.connect(self.select_chord);self.roll.chordRequested.connect(owner.edit_chord)
        self.roll.chordMoved.connect(owner.move_chord);self.roll.chordStructureChanged.connect(owner.change_chord_structure);self.roll.deleteChord.connect(owner.delete_chord)
        self.roll.audition.connect(lambda pitches:owner.transport.begin_audition(pitches,True));self.roll.auditionReleased.connect(lambda:owner.transport.end_audition(True));self.roll.playheadChanged.connect(owner.seek)
        self.roll.markerRequested.connect(owner.edit_marker);self.roll.insertMeasureRequested.connect(owner.insert_measure);self.roll.playRequested.connect(owner.play_from)
        self.roll.contextRequested.connect(owner.edit_context)
        self.roll.harmonyRequested.connect(owner.open_harmony);self.roll.viewChanged.connect(lambda:owner.sync_views(self.roll))
        self.roll.selectionChanged.connect(owner.harmony_selection_changed)
        self.set_panel_defaults()
        self.refresh();self.initializing=False;QTimer.singleShot(0,self,self.finish_setup)

    def finish_setup(self):
        if not getattr(self.roll,'has_centered_view',False):self.roll.center_pitch(self.initial_pitch())
        self.view_ready=True

    def initial_pitch(self):
        chord=self.current();pitches=sorted({n.pitch for n in chord.render_notes()}) if chord else []
        return pitches[len(pitches)//2] if pitches else 55

    def set_panel_defaults(self):
        self.roll.set_panel('chords',False)

    def sync_position(self,floating):
        if not self.initializing:self.schedule_center(30)

    def schedule_center(self,delay=0):
        generation=(getattr(self.roll,'center_generation',0),getattr(self.owner.roll,'center_generation',0))
        def settle():
            current=(getattr(self.roll,'center_generation',0),getattr(self.owner.roll,'center_generation',0))
            if current==generation:self.center_after_layout()
        QTimer.singleShot(delay,self,settle)

    def center_after_layout(self):
        # A dock change emits after geometry has already moved. Use musical
        # content, not a stale pixel center, to avoid cumulative octave jumps.
        # A delayed geometry event must never move the keyboard during a gesture.
        if self.roll.drag or self.owner.roll.drag:return
        roll=self.owner.roll;left=roll.tick_at(66);right=roll.tick_at(roll.viewport().width())
        notes=roll.selected_notes() or [n for n in self.owner.project.notes if n.start<right and n.end>left] or self.owner.project.notes
        pitches=sorted({n.pitch for n in notes})
        if pitches:roll.center_pitch(pitches[len(pitches)//2])
        self.roll.center_pitch(self.initial_pitch())
        if self.owner.rolls_linked():self.owner.sync_views(self.owner.roll)

    def set_grid(self):
        self.roll.grid=self.grid.currentData();self.roll.grid_bars=self.grid.bars;self.roll.refresh();self.owner.sync_grid_views(self.roll);self.owner.update_shared_views()

    def set_duration(self):
        self.roll.duration=self.length.currentData();self.roll.duration_bars=self.length.bars

    def current(self):return next((c for c in self.owner.project.chords if c.id==self.current_id),None)

    def refresh(self):
        self.roll.set_project(self.owner.project)
        self.roll.has_note_clipboard=self.owner.note_clipboard is not None
        if not self.current():
            self.current_id=''
        self.select_chord(self.current_id,locate=False,select=False)

    def select_chord(self,cid,locate=True,select=True):
        self.current_id=cid
        if select:self.roll.selected_chord=cid
        c=self.current();self.candidates.clear()
        if c:
            self.summary.setText(tr('{0} · 起点 {1:g} · 时长 {2:g}（四分音符） · ', contextual_chord_name(self.owner.project,c), c.start / PPQ, c.duration / PPQ)+rhythm_label(c,self.owner.project))
            if not self.owner.rolls_linked():self.roll.selection=[[c.start,c.end]]
            for candidate in recognize([n.pitch for n in c.render_notes()],preferred=(c.root%12,c.quality)):
                self.candidates.addItem(candidate.name,candidate)
            if not self.candidates.count():self.candidates.addItem(tr('未匹配 / 空区间'),None)
            if locate:self.roll.ensure_tick(c.start)
        else:self.summary.setText(tr('先添加或选中一个和弦区间'))
        self.summary.setToolTip(self.summary.text())
        if c:self.summary.setText(tr('{0} · {1:g} 拍',contextual_chord_name(self.owner.project,c),c.duration/PPQ))
        self.roll.refresh()

    def note_selected(self,nid):
        c=self.owner.project.harmony_owner(nid)
        if c:self.select_chord(c.id,False,False)

    def change_note(self,note):
        self.owner.edit_notes(self.roll,[note],[])
        self.note_selected(note.id);self.roll.selected_note=note.id;self.roll.selected_ids=self.roll.expand_note_selection({note.id})

    def note_properties(self,nid):
        n=next((n for n in self.roll.notes if n.id==nid),None)
        if not n:return
        dialog=NoteDialog(n,self.owner.project,self);dialog.setWindowTitle(tr('和弦音符'))
        if dialog.exec()==QDialog.DialogCode.Accepted:self.change_note(dialog.value())

    def choose_candidate(self):
        c=self.current();candidate=self.candidates.currentData()
        if not c or not candidate:return
        cid=c.id
        def op(p):
            chord=next(c for c in p.chords if c.id==cid);chord.materialize()
            chord.root=48+candidate.root;chord.quality=candidate.quality;chord.bass=candidate.bass;chord.recognized=True
        self.owner.mutate(tr('已采用候选和弦标记；音符保持不变'),op)

    def clear_notes(self):
        c=self.current()
        if not c:return
        cid=c.id
        def op(p):
            chord=next(c for c in p.chords if c.id==cid);chord.notes=[];chord.recognized=False
        self.owner.mutate(tr('已清空当前和弦音符，可自由绘制；Ctrl+Z 可撤销'),op)

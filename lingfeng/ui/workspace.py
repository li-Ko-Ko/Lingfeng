"""Compact workspace containers; all views share one project and transport."""
from PySide6.QtCore import Qt, QPointF, QPoint, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QAction
from PySide6.QtWidgets import QWidget, QFrame, QHBoxLayout, QVBoxLayout, QLabel, QToolButton, QMenu, QSplitter, QSizePolicy, QApplication, QScrollArea, QScrollBar, QInputDialog
from lingfeng.platform.i18n import tr

from lingfeng.ui.controls import IconButton

from lingfeng.ui.piano_roll import PianoRoll, ChordLane, TimelineNavigator, KEY_W
from lingfeng.ui.theme import PANEL_BORDERS, PANEL_SURFACES, color, is_dark

from lingfeng.ui.painting import cached_layer, time_view_key
from lingfeng.ui.timeline import TimelineGesture, RULER_TIME_H
from lingfeng.ui.navigation import watch_scrollbar
from lingfeng.ui.workspace_tabs import WorkspaceScoreTabs, WorkspaceTabBar
import time


from lingfeng.ui.panes import FloatingPane, RollTransport, RollVolumeControls


class Timeline(QWidget):
    def __init__(self,roll):
        super().__init__();self.roll=roll;self.gesture=TimelineGesture(self,lambda:self.roll,self.offset);self.context_handled=0;self.setMouseTracking(True);self.setFixedHeight(roll.bar_ruler_height+RULER_TIME_H);self.setMinimumWidth(0);self.setToolTip(tr('上方选择小节；下方单击定位，拖动设置循环，Shift 延伸循环。'))
    def offset(self):
        if getattr(self.roll,'main_timeline_state',False) or self.roll.window()!=self.window():return 0
        return self.roll.viewport().mapToGlobal(QPoint(0,0)).x()-self.mapToGlobal(QPoint(0,0)).x()
    def x_at(self,tick):return self.roll.x_at(tick)+self.offset()
    def resizeEvent(self,event):
        super().resizeEvent(event)
        owner=self.window()
        if getattr(owner,'workspace_ready',False):owner.update_shared_views()
    def paintEvent(self,event):
        e=self.roll;p=QPainter(self)
        offset=self.offset();x_at=lambda tick:e.x_at(tick)+offset
        cached_layer(self,p,(time_view_key(e),offset),lambda painter:e.paint_ruler(painter,self.width(),self.height(),x_at))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setClipRect(KEY_W,0,self.width()-KEY_W,self.height())
        if e.anchor_tick is not None:
            p.setPen(QPen(color('#426BAA'),1.2,Qt.PenStyle.DashLine));p.drawLine(QPointF(x_at(e.anchor_tick),0),QPointF(x_at(e.anchor_tick),self.height()))
        p.setPen(QPen(color('#D15F49'),2));p.drawLine(QPointF(x_at(e.visual_tick()),0),QPointF(x_at(e.visual_tick()),self.height()))
    def tick(self,pos):return max(0,min(self.roll.project.end-1,self.roll.snap_time(self.roll.tick_at(pos.x()-self.offset()))))
    def mousePressEvent(self,event):
        self.gesture.press(event);self.update()
    def mouseMoveEvent(self,event):
        self.gesture.move(event);self.update()
    def mouseReleaseEvent(self,event):
        if event.button()==Qt.MouseButton.RightButton:self.context_handled=time.monotonic()
        self.gesture.release(event)
    def mouseDoubleClickEvent(self,event):
        self.gesture.double_click(event)
    def wheelEvent(self,event):
        self.roll.time_wheel(event,event.position().x()-self.offset())
    def contextMenuEvent(self,event):
        if self.gesture.state or time.monotonic()-self.context_handled<.5 or event.pos().y()>=self.roll.bar_ruler_height:return
        self.roll.timeline_menu(event.pos()-QPoint(self.offset(),0)).exec(event.globalPos())
    def hideEvent(self,event):self.gesture.cancel();super().hideEvent(event)


from lingfeng.ui.logic_panel import LogicPanel


class MelodyTrackHeader(QWidget):
    """The active tab opens into the roll through a break in its outline."""

    def __init__(self, tabs):
        super().__init__()
        self.tabs=tabs
        self.setObjectName('melodyTrackHeader')
        tabs.currentChanged.connect(lambda _: self.update())

    def paintEvent(self,event):
        dark=is_dark()
        painter=QPainter(self)
        painter.setPen(QPen(QColor(PANEL_BORDERS[dark]),1))
        if self.tabs.parentWidget() is self and not self.tabs.isHidden():
            self.tabs.paint_rail_outside(painter,self.width())
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        right=self.width()-.5
        bottom=self.height()
        radius=5
        path=QPainterPath(QPointF(.5,bottom))
        path.lineTo(.5,radius+.5)
        path.quadTo(.5,.5,radius+.5,.5)
        path.lineTo(right-radius,.5)
        path.quadTo(right,.5,right,radius+.5)
        path.lineTo(right,bottom)
        painter.fillPath(path,QColor(PANEL_SURFACES[dark]))
        painter.drawPath(path)


class WorkspaceMixin:
    def organize_workspace(self):
        self.workspace_ready=False;self.mounting=False;self.syncing_controls=False;self.syncing_scroll=False;self.syncing_time=False;self.auto_follow=False;self.compose_float_state=(False,False)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().hide()
        ed=self.editor.layout();tools=ed.itemAt(0).layout();bottom=ed.takeAt(ed.count()-1).layout()
        bottom.removeWidget(self.view_controls);tools.addWidget(QLabel(tr('吸附')));tools.addWidget(self.grid);tools.addWidget(self.view_controls);tools.removeWidget(self.view_controls.options);self.view_controls.options.hide()
        tools.removeWidget(self.harmony_button);self.harmony_button.hide()
        ed.takeAt(0);self.melody_toolbar=QWidget();self.melody_toolbar.setLayout(tools)
        ed.removeWidget(self.roll)
        self.melody_tabs=WorkspaceTabBar()
        for track in (0,1):self.melody_tabs.addTab(self.project.melody_name(track))
        self.melody_tabs.currentChanged.connect(self.switch_melody_track)
        self.melody_tabs.tabBarDoubleClicked.connect(self.rename_melody_track)
        self.melody_tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.melody_tabs.customContextMenuRequested.connect(self.melody_tab_menu)
        self.melody_floats={}
        self.melody_track_state={}
        self.melody_window=FloatingPane(tr('旋律钢琴卷帘'),self,'melody');self.melody_window.setObjectName('melodyDock');self.melody_window.setWidget(self.editor)
        self.melody_header=MelodyTrackHeader(self.melody_tabs);head=QHBoxLayout(self.melody_header);head.setContentsMargins(0,0,3,0);head.setSpacing(8)
        head.addWidget(self.melody_tabs,0,Qt.AlignmentFlag.AlignBottom)
        self.melody_title=QLabel()
        self.melody_title.setObjectName('melodySingleTrackTitle')
        self.melody_title.setTextFormat(Qt.TextFormat.PlainText)
        self.melody_title.setContentsMargins(12,0,0,0)
        self.melody_title.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.melody_title.hide()
        head.addWidget(self.melody_title,1)
        from PySide6.QtWidgets import QCheckBox
        self.melody_sync=QAction(tr('同步时间轴'),self.melody_window);self.melody_sync.setCheckable(True);self.melody_sync.setToolTip(tr('同步主界面的滚动、缩放与跟随播放游标；取消后独立控制。'));self.melody_sync.toggled.connect(lambda value:self.set_timeline_sync(value,self.roll));head.addStretch()
        self.floating_melody_chords=True
        self.melody_transport=RollTransport(self);self.melody_options=self.melody_transport.options
        options=QMenu(self.melody_options);self.melody_chords_action=options.addAction(tr('显示和弦轨'));self.melody_chords_action.setCheckable(True);self.melody_chords_action.setChecked(True)
        options.insertAction(self.melody_chords_action,self.melody_sync);options.insertSeparator(self.melody_chords_action)
        self.melody_chords_action.toggled.connect(self.toggle_melody_lane)
        options.addAction(self.roll.lane.velocity_action)
        for key in ('velocity','ruler'):options.addAction(self.view_controls.panel_actions[key])
        self.melody_options.setMenu(options)
        self.melody_float=IconButton('float');self.melody_float.setToolTip(tr('悬浮当前选项卡'));self.melody_float.setAccessibleName(tr('悬浮当前选项卡'));self.melody_float.activated.connect(lambda:self.toggle_roll_floating(self.melody_window));head.addWidget(self.melody_float);ed.insertWidget(0,self.melody_header)
        self.melody_hide=IconButton('close');self.melody_hide.setToolTip(tr('关闭当前选项卡'));self.melody_hide.setAccessibleName(tr('关闭当前选项卡'));self.melody_hide.activated.connect(lambda:self.melody_view_actions[self.roll.melody_track].setChecked(False));head.addWidget(self.melody_hide)
        body=QFrame();body.setObjectName('melodyRollBody')
        self.melody_body_layout=QVBoxLayout(body);self.melody_body_layout.setContentsMargins(1,0,1,2);self.melody_body_layout.setSpacing(0)
        self.melody_body_layout.addWidget(self.melody_transport)
        self.melody_body_layout.addWidget(self.roll,1)
        self.melody_volume=RollVolumeControls(self);self.melody_body_layout.addWidget(self.melody_volume)
        ed.addWidget(body,1)
        # Keep a main-window time view even while both editors are floating.
        self.main_roll=PianoRoll(self.project,self.centralWidget());self.main_roll.main_timeline_state=True;self.main_roll.hide()
        for key in ('chords','navigator','velocity'):self.main_roll.set_panel(key,False)
        self.main_roll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.main_roll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.main_roll.selectionChanged.connect(self.selection_changed);self.main_roll.playheadChanged.connect(self.seek);self.main_roll.playRequested.connect(self.play_from)
        self.main_roll.contextRequested.connect(self.edit_context);self.main_roll.markerRequested.connect(self.edit_marker);self.main_roll.insertMeasureRequested.connect(self.insert_measure)
        self.main_roll.chordRequested.connect(self.edit_chord);self.main_roll.harmonyRequested.connect(self.open_harmony);self.main_roll.deleteChord.connect(self.delete_chord);self.main_roll.chordMoved.connect(self.move_chord)
        self.main_roll.chordSelected.connect(self.select_chord)
        self.navigator=TimelineNavigator(self.roll);self.timeline=Timeline(self.roll)
        self.compose_layout.setContentsMargins(6,4,6,4);self.compose_layout.setSpacing(3)
        shell=self.centralWidget();shell.layout().insertWidget(shell.layout().indexOf(self.stack),self.navigator);self.compose_layout.addWidget(self.timeline)
        self.tracks=QSplitter(Qt.Orientation.Vertical);self.tracks.setChildrenCollapsible(False);self.tracks.setHandleWidth(4);self.compose_layout.addWidget(self.tracks,1)
        self.compose_spacer=QWidget();self.compose_spacer.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Expanding);self.compose_layout.addWidget(self.compose_spacer);self.compose_spacer.hide()
        self.chord_lane=ChordLane(self.roll);self.chord_lane.structure=False;self.chord_lane.update_height()
        self.shared_scroll=QScrollBar(Qt.Orientation.Horizontal);self.shared_scroll.setFixedHeight(16);self.shared_scroll.setToolTip(tr('共享时间轴'));self.shared_scroll.valueChanged.connect(self.scroll_shared);self.compose_layout.addWidget(self.shared_scroll)
        watch_scrollbar(self.shared_scroll,lambda:self.cancel_follow(self.main_roll))
        self.mixer_sources=QWidget(self);self.mixer_sources.setLayout(bottom);self.mixer_sources.hide()
        self.audio_footer=RollVolumeControls(self);shell.layout().addWidget(self.audio_footer)
        from lingfeng.ui.harmony_window import HarmonyWindow
        self.harmony_window=HarmonyWindow(self)
        self.score_tools=FloatingPane(tr('制谱编辑器'),self,'score');body=QWidget();box=QVBoxLayout(body);box.setContentsMargins(2,2,2,2);box.setSpacing(2);self.score_tools.setWidget(body)
        self.score_shared_tools=QWidget();self.score_shared_layout=QVBoxLayout(self.score_shared_tools);self.score_shared_layout.setContentsMargins(0,0,0,0);box.addWidget(self.score_shared_tools)
        self.score_tabs=WorkspaceScoreTabs();self.score_roll_stack=self.score_tabs
        self.score_melody_page=QWidget();self.score_melody_layout=QVBoxLayout(self.score_melody_page);self.score_melody_layout.setContentsMargins(0,0,0,0)
        self.score_harmony_page=QWidget();self.score_harmony_layout=QVBoxLayout(self.score_harmony_page);self.score_harmony_layout.setContentsMargins(0,0,0,0)
        self.score_tabs.addTab(self.score_melody_page,tr('旋律卷帘'));self.score_tabs.addTab(self.score_harmony_page,tr('和弦卷帘'))
        # Retain the editor interface without exposing structure editing.
        self.logic_panel=LogicPanel(self);self.logic_panel.setParent(body);self.logic_panel.setEnabled(False);self.logic_panel.hide()
        from lingfeng.ui.lyric_panel import LYRIC_PANEL_KEYS, LyricsPanel
        self.lyric_panels={key:LyricsPanel(self,track) for track,key in enumerate(LYRIC_PANEL_KEYS)}
        self.lyric_panel=self.lyric_panels['lyrics'];box.addWidget(self.score_tabs)
        from lingfeng.ui.annotation_panel import AnnotationPanel
        self.annotation_panel=AnnotationPanel(self)
        self.score_pages=dict(melody=self.score_melody_page,harmony=self.score_harmony_page,**self.lyric_panels,annotations=self.annotation_panel)
        self.score_labels=dict(melody='旋律卷帘',harmony='和弦卷帘',annotations='标识')
        self.score_panel_state={key:dict(visible=False,floating=False) for key in self.score_pages}
        self.score_floats={key:FloatingPane(self.score_panel_title(key),self,'score_'+key) for key in self.score_pages}
        self.score_view_actions={}
        for key in self.score_pages:
            action=QAction(self.score_panel_title(key),self);action.setCheckable(True);action.setChecked(False)
            action.toggled.connect(lambda value,k=key:self.set_score_panel_visible(k,value));self.score_view_actions[key]=action
        self.score_footer=RollVolumeControls(self);box.addWidget(self.score_footer)
        self.score_tools.setMinimumHeight(100)
        self.score_float=IconButton('float');self.score_float.setToolTip(tr('悬浮当前选项卡'));self.score_float.setAccessibleName(tr('悬浮当前选项卡'));self.score_float.activated.connect(lambda:self.toggle_score_panel_floating(self.current_score_panel()))
        self.score_close=IconButton('close');self.score_close.setToolTip(tr('关闭当前选项卡'));self.score_close.setAccessibleName(tr('关闭当前选项卡'));self.score_close.activated.connect(lambda:self.set_score_panel_visible(self.current_score_panel(),False))
        corner=QWidget();corner_layout=QHBoxLayout(corner);corner_layout.setContentsMargins(0,0,0,0);corner_layout.setSpacing(2);corner_layout.addWidget(self.score_float);corner_layout.addWidget(self.score_close);self.score_tabs.setCornerWidget(corner)
        self.score_tabs.currentChanged.connect(self.mount_panels)
        self.score_splitter.splitterMoved.connect(self.remember_score_panel_height)
        self.visibility_button=QToolButton();self.visibility_button.setText(tr('显示'));self.visibility_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);menu=QMenu(self.visibility_button);self.visibility_actions={}
        self.melody_view_actions={}
        for key,label,visible in [('navigator','全局进度',True),('timeline','时间轴',True),('melody','旋律钢琴卷帘',True),('chords','和弦轨',True),('harmony','和弦钢琴卷帘',False),('volume','音量控制',True)]:
            a=QAction(tr(label),menu);a.setCheckable(True);a.setChecked(visible);a.toggled.connect(lambda value,k=key:self.visibility_changed(k));self.visibility_actions[key]=a
            if key=='melody':
                # Keep the shared editor's internal dock visibility for pane navigation.
                for track in (0,1):
                    track_action=menu.addAction(self.project.melody_name(track));track_action.setCheckable(True);track_action.setChecked(True)
                    track_action.toggled.connect(lambda shown,t=track:self.melody_visibility_changed(t,shown))
                    self.melody_view_actions[track]=track_action
            else:menu.addAction(a)
        self.refresh_melody_tabs()
        menu.addSeparator()
        menu.addAction(self.chord_lane.velocity_action)
        for label,controls in [('旋律卷帘',self.view_controls),('和弦卷帘',self.harmony_window.view_controls)]:
            sub=menu.addMenu(tr(label));sub.addAction(controls.panel_actions['velocity']);sub.addAction(controls.panel_actions['ruler'])
            if controls is self.harmony_window.view_controls:sub.addAction(self.harmony_window.recognition_action)
            controls.panel_actions['ruler'].toggled.connect(self.update_shared_views)
        self.visibility_button.setMenu(menu);self.compose_menu_actions=list(menu.actions())
        for r in (self.roll,self.harmony_window.roll,self.main_roll):
            r.set_panel('navigator',False);r.set_panel('chords',False)
            self.bind_workspace_roll(r)
        self.score_view.canvas.selectionChanged.connect(self.logic_panel.show_details)
        self.score_view.canvas.selectionChanged.connect(self.annotation_panel.refresh_selection)
        self.score_view.canvas.editorRequested.connect(self.open_score_roll)
        self.score_view.navigationRequested.connect(lambda:self.cancel_follow(self.score_view))
        for roll in (self.roll,self.harmony_window.roll):
            roll.horizontalScrollBar().rangeChanged.connect(self.update_shared_views)
        for control,roll in ((self.tool,self.roll),(self.grid,self.roll),(self.harmony_window.tool,self.harmony_window.roll),(self.harmony_window.grid,self.harmony_window.roll)):
            control.currentIndexChanged.connect(lambda *args,r=roll:self.sync_tools(r))
        self.length.currentIndexChanged.connect(lambda:self.sync_tools(self.roll));self.harmony_window.length.currentIndexChanged.connect(lambda:self.sync_tools(self.harmony_window.roll))
        self.score_tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.score_tabs.customContextMenuRequested.connect(self.score_editor_menu)
        self.score_view.canvas.playback_clock=lambda:self.transport.position() if self.transport.playing else self.playhead
        self.workspace_ready=True;self.mount_panels()
        for lane in (self.chord_lane,self.roll.lane,self.harmony_window.roll.lane):lane.aux_ruler_scale=self.chord_ruler_scale
        self.follow_playhead.toggled.connect(lambda value:self.sync_follow(value))
        for _,r,_,controls in self.view_panes():controls.follow.toggled.connect(lambda value,r=r:self.sync_follow(value,r))

    def bind_workspace_roll(self,roll):
        roll.sectionSelectionRequested.connect(self.select_section_contents)
        roll.elementSelection.connect(lambda kind:self.select_element(kind,roll))
        roll.notesSelectionChanged.connect(lambda:self.select_element('notes',roll) if roll.selected_ids else None)
        roll.has_chord_clipboard=self.chord_clipboard is not None
        roll.chord_clipboard=self.chord_clipboard
        roll.deleteMeasuresRequested.connect(self.delete_measures)
        roll.loop_range=self.loop_range;roll.loopRangeChanged.connect(self.set_loop_range)
        roll.navigationRequested.connect(lambda:self.cancel_follow(roll))
        roll.measureActivated.connect(lambda bar:self.locate_score_measure(bar,roll))
        roll.timeViewChanged.connect(lambda:self.sync_time_views(roll))
        roll.markerPropagationRequested.connect(self.propagate_marker)
        roll.chordCommand.connect(lambda command,payload:self.chord_command(command,payload,roll))
        roll.chordSelection.connect(lambda ids:self.chord_selection(ids,roll,getattr(roll,'chord_event_lane',None)))
        roll.chordHover.connect(lambda cid:self.chord_hover(cid,roll,getattr(roll,'chord_event_lane',None)))
        roll.chordAudition.connect(self.audition_chord)
        roll.chordAuditionReleased.connect(lambda:self.transport.end_audition(True))
        roll.chordAuditionHeld.connect(self.hold_chord)
        roll.viewChanged.connect(self.update_shared_views)
        roll.sectionRequested.connect(self.set_section)
        roll.playback_clock=self.transport.position

    def current_score_panel(self):
        return next((key for key,page in self.score_pages.items() if page is self.score_tabs.currentWidget()),None)

    def score_panel_title(self,key):
        return self.lyric_panels[key].title() if key in self.lyric_panels else tr(self.score_labels[key])

    def refresh_lyric_titles(self):
        for key,panel in self.lyric_panels.items():
            title=panel.title();action=self.score_view_actions[key]
            if title==action.text():continue
            action.setText(title)
            pane=self.score_floats[key];pane.setWindowTitle(title);pane.title_bar.caption.setText(title)
            index=self.score_tabs.indexOf(panel)
            if index>=0:self.score_tabs.setTabText(index,title)

    def remember_score_panel_height(self,*args):
        if self.workspace=='score' and self.score_tabs.count():
            blocked=self.dock_height.blockSignals(True);self.dock_height.setValue(self.score_tools.height());self.dock_height.blockSignals(blocked)

    def update_view_menu(self):
        menu=self.visibility_button.menu()
        for action in list(menu.actions()):menu.removeAction(action)
        for action in (self.compose_menu_actions if self.workspace=='compose' else self.score_view_actions.values()):menu.addAction(action)

    def set_score_panel_visible(self,key,visible):
        if key not in self.score_panel_state:return
        self.score_panel_state[key]['visible']=bool(visible);self.mount_panels()

    def toggle_score_panel_floating(self,key):
        if key not in self.score_panel_state:return
        state=self.score_panel_state[key];state['floating']=not state['floating'];state['visible']=True;self.mount_panels()
        self.show_score_panel(key)

    def show_score_panel(self,key):
        if key not in self.score_pages:return None
        self.set_score_panel_visible(key,True)
        pane=self.score_floats[key]
        if self.score_panel_state[key]['floating']:
            if pane.isMinimized():pane.showNormal()
            pane.raise_();pane.activateWindow()
        else:self.score_tabs.setCurrentWidget(self.score_pages[key])
        if key in self.lyric_panels:self.lyric_panels[key].open_editor()
        return pane if pane.isFloating() else self

    def mount_score_tabs(self,compose):
        selected=self.current_score_panel()
        blocked=self.score_tabs.blockSignals(True)
        try:
            for key,page in self.score_pages.items():
                state=self.score_panel_state[key];pane=self.score_floats[key]
                action=self.score_view_actions[key];was=action.blockSignals(True);action.setChecked(state['visible']);action.blockSignals(was)
                index=self.score_tabs.indexOf(page)
                if state['floating'] or not state['visible']:
                    if index>=0:self.score_tabs.removeTab(index)
                    if page.parentWidget() is not pane:pane.box.addWidget(page)
                    pane.setFloating(state['floating']);page.show()
                    pane.setVisible(not compose and state['visible'] and state['floating'])
                else:
                    pane.setFloating(False);pane.hide()
                    if index<0:
                        before=list(self.score_pages).index(key)
                        index=sum(self.score_tabs.indexOf(self.score_pages[k])>=0 for k in list(self.score_pages)[:before])
                        self.score_tabs.insertTab(index,page,self.score_panel_title(key))
            if selected and self.score_tabs.indexOf(self.score_pages[selected])>=0:self.score_tabs.setCurrentWidget(self.score_pages[selected])
        finally:self.score_tabs.blockSignals(blocked)
        self.score_tools.setVisible(not compose and self.score_tabs.count()>0)

    def score_editor_menu(self,pos):
        menu=QMenu(self.score_tabs)
        key=self.current_score_panel()
        if key:
            menu.addAction(tr('悬浮当前选项卡'),lambda:self.toggle_score_panel_floating(key))
            menu.addAction(tr('关闭当前选项卡'),lambda:self.set_score_panel_visible(key,False));menu.addSeparator()
        for key in self.score_pages:menu.addAction(self.score_panel_title(key),lambda k=key:self.show_score_panel(k))
        menu.exec(self.score_tabs.mapToGlobal(pos))

    def mount_panels(self,*args):
        if not getattr(self,'workspace_ready',False) or self.mounting:return
        self.mounting=True
        try:
            compose=self.workspace=='compose';show=lambda key:self.visibility_actions[key].isChecked()
            self.mount_score_tabs(compose);self.update_view_menu()
            self.mount_melody_tabs(compose)
            has_melody_tabs=any(self.melody_tabs.isTabVisible(track) for track in (0,1))
            dock_melody=show('melody') and has_melody_tabs
            for track,pane in self.melody_floats.items():
                pane.setVisible(compose and pane.isFloating() and self.melody_view_actions[track].isChecked())
            for roll in (self.roll,self.main_roll,self.harmony_window.roll):roll.score_mode=not compose
            for widget in (self.melody_window,self.harmony_window,self.chord_lane):
                if not isinstance(widget,FloatingPane) or not widget.isFloating():widget.hide()
            if compose:
                for widget in (self.melody_window,self.chord_lane,self.harmony_window):
                    if not isinstance(widget,FloatingPane) or not widget.isFloating():self.tracks.addWidget(widget)
                self.melody_window.setVisible(self.melody_window.floating_visible and has_melody_tabs if self.melody_window.isFloating() else dock_melody)
                self.harmony_window.setVisible(self.harmony_window.floating_visible if self.harmony_window.isFloating() else show('harmony'))
                self.chord_lane.setVisible(show('chords'))
                self.navigator.setVisible(show('navigator'));self.timeline.setVisible(show('timeline'));self.score_tools.hide()
                rolls_visible=(dock_melody and not self.melody_window.isFloating()) or (show('harmony') and not self.harmony_window.isFloating())
                self.compose_spacer.setVisible(not rolls_visible);self.compose_layout.setStretch(self.compose_layout.indexOf(self.tracks),1 if rolls_visible else 0)
                self.compose_layout.setAlignment(self.timeline,Qt.AlignmentFlag.AlignTop)
            else:
                if not self.score_tools.isFloating():self.score_splitter.addWidget(self.score_tools)
                self.score_melody_layout.addWidget(self.melody_window);self.score_harmony_layout.addWidget(self.harmony_window)
                self.melody_window.show();self.harmony_window.show();self.score_view.canvas.editing=True
            linked=self.rolls_linked()
            if compose and not self.melody_window.isFloating():self.compose_layout.insertWidget(0,self.melody_toolbar)
            elif not compose and not self.score_panel_state['melody']['floating']:self.score_shared_layout.addWidget(self.melody_toolbar)
            else:self.melody_body_layout.insertWidget(1,self.melody_toolbar)
            self.melody_toolbar.setVisible(
                (dock_melody or self.melody_window.isFloating() or show('harmony') and not self.harmony_window.isFloating()) if compose else
                (self.score_panel_state['melody']['floating'] or self.current_score_panel() in ('melody','harmony')))
            self.harmony_window.toolbar.setVisible(not linked or not compose and (self.score_panel_state['harmony']['floating'] or self.score_panel_state['melody']['floating']))
            self.harmony_window.header.setVisible(compose and not self.harmony_window.isFloating())
            self.melody_float.setVisible(compose)
            self.melody_hide.setVisible(compose);self.harmony_window.hide_button.setVisible(compose)
            self.navigator.setVisible(show('navigator'))
            self.shared_scroll.setVisible(compose and (show('timeline') or dock_melody and not self.melody_window.isFloating() or show('harmony') and not self.harmony_window.isFloating() or show('chords')))
            for pane,roll in ((self.melody_window,self.roll),(self.harmony_window,self.harmony_window.roll)):
                roll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff if compose and not pane.isFloating() else Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                roll.external_ruler=compose and not pane.isFloating();roll.set_panel('chords',compose and pane is self.melody_window and pane.isFloating() and self.floating_melody_chords);roll.update_ranges();roll.refresh()
            self.melody_transport.setVisible(self.melody_window.isFloating() if compose else self.score_panel_state['melody']['floating']);self.harmony_window.transport_controls.setVisible(self.harmony_window.isFloating() if compose else self.score_panel_state['harmony']['floating'])
            self.melody_volume.setVisible(self.melody_window.isFloating() if compose else self.score_panel_state['melody']['floating']);self.harmony_window.volume_controls.setVisible(self.harmony_window.isFloating() if compose else self.score_panel_state['harmony']['floating'])
            self.score_footer.setVisible(not compose and self.score_tools.isFloating())
            for footer in self.shared_footers():footer.set_mixer_visible(show('volume'))
            self.melody_options.setVisible(self.roll_pane(self.roll).isFloating())
            for pane,control in ((self.melody_window,self.melody_float),(self.harmony_window,self.harmony_window.float_button)):
                control.set_kind('dock' if (pane.isFloating() if compose else self.score_tools.isFloating()) else 'float')
            self.score_float.setVisible(self.score_tabs.count()>0)
            self.score_shared_tools.setVisible(not compose and not self.score_panel_state['melody']['floating'] and self.current_score_panel() in ('melody','harmony'))
        finally:self.mounting=False
        if not compose:
            for key,panel in self.lyric_panels.items():
                state=self.score_panel_state[key]
                if state['visible'] and (state['floating'] or self.current_score_panel()==key):panel.open_editor()
        self.sync_grid_views(self.main_roll);self.sync_time_views(self.main_roll);self.sync_tools(self.roll);self.sync_views(self.roll);self.update_shared_views()
        self.sync_follow(self.follow_playhead.isChecked())
        if self.transport.playing:self.follow_views(self.transport.position())
        if not compose:QTimer.singleShot(0,self,self.resize_score)

    def toggle_roll_floating(self,pane):
        if pane.key.startswith('melody_'):
            self.set_melody_floating(pane.track,False)
        elif pane.key.startswith('score_'):self.toggle_score_panel_floating(pane.key[6:])
        elif self.workspace=='score':self.toggle_score_panel_floating(pane.key)
        elif pane is self.melody_window and not pane.isFloating():
            self.set_melody_floating(self.roll.melody_track,True)
        else:pane.setFloating(not pane.isFloating())

    def set_melody_floating(self,track,floating,*,focus=True):
        pane=self.melody_floats.get(track)
        if pane is None:
            if not floating:return
            from lingfeng.ui.melody_window import MelodyWindow
            pane=MelodyWindow(self,track)
            self.melody_floats[track]=pane
            self.bind_melody_roll(pane.roll)
            self.bind_workspace_roll(pane.roll)
            self.register_chord_lane(pane.roll.lane)
            pane.roll.has_note_clipboard=self.note_clipboard is not None
            pane.roll.overview_harmony=self.harmony_window.roll.notes
        if floating==pane.isFloating():return
        source=self.roll if floating else pane.roll
        roll=pane.roll
        selected=set(source.selected_ids) if source.melody_track==track else set()
        selection_state=(selected,source.previous_duration,source.previous_note_id)
        if floating:
            if source.melody_track!=track:
                selection_state=self.melody_track_state.get(track,(set(),None,''))
            roll.selected_ids,roll.previous_duration,roll.previous_note_id=selection_state
            roll.selected_note=next(iter(roll.selected_ids),'')
            roll.selection=[list(bounds) for bounds in source.selection]
            pane.tool.setCurrentIndex(self.tool.currentIndex())
            pane.grid.setCurrentIndex(self.grid.currentIndex());pane.grid.set_triplet(self.grid.triplet)
            pane.length.setCurrentIndex(self.length.currentIndex());pane.length.set_triplet(self.length.triplet)
            pane.length.dotted_action.setChecked(self.length.dotted_action.isChecked())
            roll.zoom=source.zoom
            roll.set_row_height(source.row_height);pane.view_controls.height.setValue(source.row_height)
            roll.compact=source.compact;roll.pitch_range=source.pitch_range;roll.manual_pitch_range=source.manual_pitch_range
            roll.refresh()
            scroll=source.horizontalScrollBar().value()
            pitch=source.pitch_at(source.ruler_height+max(1,source.viewport().height()-source.ruler_height)/2)
        else:
            self.melody_track_state[track]=selection_state
        pane.setFloating(floating)
        if floating:
            roll.update_ranges()
            roll.horizontalScrollBar().setValue(scroll);roll.center_pitch(pitch)
            self.update_transport_buttons();self.show_cursor(self.playhead)
        else:
            self.melody_view_actions[track].setChecked(True)
            self.visibility_actions['melody'].setChecked(True)
            if self.roll.melody_track==track:
                self.roll.selected_ids,self.roll.previous_duration,self.roll.previous_note_id=selection_state
                self.roll.selected_note=next(iter(self.roll.selected_ids),'');self.roll.refresh_notes(notify=False)
            else:self.switch_melody_track(track)
        if focus and self.workspace=='compose':
            window=pane if floating else self
            window.raise_();window.activateWindow()
            (roll if floating else self.roll).setFocus()

    def visibility_changed(self,key):
        if key in ('melody','harmony'):
            checked=self.visibility_actions[key].isChecked()
            if checked and not getattr(self,'restoring_layout',False):
                if self.workspace!='compose':self.switch_workspace('compose')
                action=self.visibility_actions[key];blocked=action.blockSignals(True);action.setChecked(True);action.blockSignals(blocked)
                pane=self.melody_window if key=='melody' else self.harmony_window
                pane.setFloating(False)
            self.chord_layout_changed()
        else:self.mount_panels()

    def melody_visibility_changed(self,track,visible):
        if visible and self.workspace=='compose' and not getattr(self,'restoring_layout',False):
            pane=self.melody_floats.get(track)
            if not (pane and pane.isFloating()):
                if self.melody_window.isFloating():self.melody_window.floating_visible=True
                else:self.visibility_actions['melody'].setChecked(True)
                self.switch_melody_track(track)
        self.mount_panels()

    def show_roll_in_place(self,pane):
        """Reveal the roll in its current docked or floating location."""
        if self.workspace=='compose':
            if pane is self.melody_window:
                self.melody_view_actions[self.roll.melody_track].setChecked(True)
            elif pane.key.startswith('melody_'):
                self.melody_view_actions[pane.track].setChecked(True)
        if pane.isFloating():
            pane.floating_visible=True
            if pane.isMinimized():pane.showNormal()
            self.mount_panels()
        else:self.visibility_actions[pane.key].setChecked(True)

    def toggle_melody_lane(self,visible):
        self.floating_melody_chords=bool(visible)
        if self.workspace=='compose' and self.melody_window.isFloating():self.roll.set_panel('chords',visible)
        self.update_chord_highlight()

    def chord_layout_changed(self):
        if not getattr(self,'workspace_ready',False):return
        if self.workspace=='compose' and not getattr(self,'restoring_layout',False):
            action=self.visibility_actions['chords'];blocked=action.blockSignals(True)
            action.setChecked(not (self.visibility_actions['harmony'].isChecked() and not self.harmony_window.isFloating()))
            action.blockSignals(blocked)
            for lane in (self.chord_lane,*(r.lane for r in self.editing_rolls())):lane.highlight_hover=''
        self.mount_panels()

    def nearest_chord_lane(self,roll=None):
        pane=self.roll_pane(roll) if roll is not None else self.roll_pane(self.roll)
        if self.workspace=='compose' and pane.key.startswith('melody_'):
            return roll.lane if roll.panels['chords'] else None
        if self.workspace=='score':return self.harmony_window.roll.lane
        if self.melody_window.isFloating():return self.roll.lane if self.floating_melody_chords else None
        if self.visibility_actions['chords'].isChecked():return self.chord_lane
        if self.visibility_actions['harmony'].isChecked() and not self.harmony_window.isFloating():return self.harmony_window.roll.lane
        return None

    def update_chord_highlight(self):
        for roll in (self.roll,*(pane.roll for pane in self.melody_floats.values() if pane.isFloating())):
            lane=self.nearest_chord_lane(roll)
            highlights=lane.highlight_ids|({lane.highlight_hover} if lane.highlight_hover else set()) if lane else set()
            if highlights:highlights.intersection_update(c.id for c in self.project.chords)
            if getattr(roll,'chord_highlights',None)!=highlights:
                roll.chord_highlights=highlights;roll.refresh_notes()

    def set_timeline_sync(self,enabled,source):
        if not getattr(self,'workspace_ready',False):return
        for _,roll,check,controls in self.view_panes():
            if roll is not source:continue
            blocked=check.blockSignals(True);check.setChecked(enabled);check.blockSignals(blocked)
            if enabled:
                blocked=controls.follow.blockSignals(True);controls.follow.setChecked(self.follow_playhead.isChecked());controls.follow.blockSignals(blocked)
                self.sync_time_views(self.main_roll)
            break

    def sync_follow(self,value,source=None):
        if not getattr(self,'workspace_ready',False) or getattr(self,'syncing_follow',False):return
        if source is not None and not self.is_main_view(source) and not any(r is source and sync.isChecked() for _,r,sync,_ in self.view_panes()):return
        self.syncing_follow=True
        try:
            self.follow_playhead.setChecked(value)
            for _,roll,sync,controls in self.view_panes():
                if self.is_main_view(roll) or sync.isChecked():controls.follow.setChecked(value)
        finally:self.syncing_follow=False

    def view_panes(self):
        fixed=((self.melody_window,self.roll,self.melody_sync,self.melody_transport),
               (self.harmony_window,self.harmony_window.roll,self.harmony_window.sync,self.harmony_window.transport_controls))
        if self.workspace!='compose':return fixed
        return fixed+tuple((pane,pane.roll,pane.sync,pane.transport_controls)
                           for pane in self.melody_floats.values() if pane.isFloating())

    def editing_rolls(self):
        return (self.roll,self.main_roll,self.harmony_window.roll,*(p.roll for p in self.melody_floats.values()))

    def roll_controls(self,roll):
        if roll is self.harmony_window.roll:return self.harmony_window
        pane=self.melody_floats.get(roll.melody_track)
        return pane if pane is not None and pane.roll is roll else self

    def roll_pane(self,roll):
        controls=self.roll_controls(roll)
        if controls is not self and controls is not self.harmony_window:return controls
        key='melody' if roll is self.roll else 'harmony'
        if self.workspace=='score':return self.score_floats[key]
        return self.melody_window if key=='melody' else self.harmony_window

    def is_main_view(self,roll):
        return roll is self.main_roll or roll is self.score_view or any(r is roll and not self.roll_pane(r).isFloating() for _,r,_,_ in self.view_panes())

    def main_cursor_visible(self,tick):
        if self.workspace=='score':
            return (self.score_view.isVisible() and self.score_view.tick_visible(tick) or
                    any(self.is_main_view(r) and r.isVisible() and r.tick_visible(tick) for _,r,_,_ in self.view_panes()))
        if any(self.is_main_view(r) and r.isVisible() and r.tick_visible(tick) for _,r,_,_ in self.view_panes()):return True
        return (self.timeline.isVisible() or self.chord_lane.isVisible()) and self.main_roll.tick_visible(tick)

    def cancel_follow(self,source):
        if not getattr(self,'workspace_ready',False) or self.auto_follow or getattr(self,'restoring_layout',False):return
        tick=self.transport.position() if self.transport.playing else self.playhead
        main=self.is_main_view(source)
        if source is self.score_view:
            visible=source.isVisible() and source.bar_visible(tick)
        elif source in self.editing_rolls() and source is not self.main_roll:
            # A score elsewhere in the same window must not re-enable a roll
            # whose user has deliberately browsed beyond the playhead.
            visible=source.isVisible() and source.tick_visible(tick)
        else:visible=self.main_cursor_visible(tick) if main else source.isVisible() and source.tick_visible(tick)
        if visible:return
        linked=main or any(r is source and sync.isChecked() for _,r,sync,_ in self.view_panes())
        if linked:self.follow_playhead.setChecked(False)
        else:
            for _,roll,_,controls in self.view_panes():
                if roll is source:controls.follow.setChecked(False)

    def sync_time_views(self,source):
        if not getattr(self,'workspace_ready',False) or self.syncing_time:return
        main=self.is_main_view(source)
        if not main and not any(r is source and sync.isChecked() for _,r,sync,_ in self.view_panes()):
            self.update_shared_views();return
        self.syncing_time=True
        try:
            targets=[self.main_roll]+[r for pane,r,sync,_ in self.view_panes() if self.is_main_view(r) or sync.isChecked()]
            zoom=source.zoom;scroll=source.horizontalScrollBar().value()
            for target in targets:
                if target is source:continue
                bar=target.horizontalScrollBar();blocked=bar.blockSignals(True)
                try:
                    if target.zoom!=zoom:target.zoom=zoom;target.update_ranges()
                    bar.setValue(scroll)
                finally:bar.blockSignals(blocked)
                target.repaint_view()
        finally:self.syncing_time=False
        self.update_shared_views()

    def sync_grid_views(self,source):
        """The main page owns its grid, including while its rolls are hidden.

        An undocked roll keeps its local grid; docking or revealing a roll
        adopts the destination page's grid rather than replacing that page.
        """
        if not getattr(self,'workspace_ready',False) or getattr(self,'syncing_grid',False) or not self.is_main_view(source):return
        self.syncing_grid=True
        try:
            targets=[self.main_roll]+[r for _,r,_,_ in self.view_panes() if self.is_main_view(r)]
            for target in targets:
                target.grid=source.grid;target.grid_bars=source.grid_bars
                if target is not self.main_roll:
                    control=self.roll_controls(target).grid
                    index={8:8,4:9,2:10,1:11}.get(source.grid_bars)
                    triplet=False
                    if index is None:
                        index=next((i for i,v in enumerate(control.values[:8]) if v==source.grid),None)
                        if index is None:index=next((i for i,v in enumerate(control.values[:8]) if v*2//3==source.grid),control.currentIndex());triplet=True
                    blocked=control.blockSignals(True)
                    try:control.setCurrentIndex(index);control.set_triplet(triplet)
                    finally:control.blockSignals(blocked)
                target.refresh()
            self.score_view.canvas.grid=source.grid;self.score_view.canvas.grid_bars=source.grid_bars
        finally:self.syncing_grid=False

    def follow_views(self,tick):
        self.auto_follow=True
        try:
            if self.follow_playhead.isChecked():
                roll=self.docked_roll()
                if (self.workspace=='compose' or roll is not self.main_roll) and not roll.tick_visible(tick):roll.ensure_tick(tick)
                if self.workspace=='score' and not self.score_view.manual_navigation_active and not self.score_view.bar_visible(tick):self.score_view.locate_tick(tick)
            for _,roll,sync,controls in self.view_panes():
                pane=self.roll_pane(roll)
                if pane.isFloating() and pane.isVisible() and controls.follow.isChecked() and not roll.tick_visible(tick):roll.ensure_tick(tick)
        finally:self.auto_follow=False

    def audition_chord(self,cid):
        chord=next((c for c in self.project.chords if c.id==cid),None)
        if chord:
            pitches=chord.pitches if chord.recognized else sorted({n.pitch for n in chord.render_notes()})
            duration=self.project.measures[self.project.measure_at(chord.start)].ticks
            self.transport.begin_audition(pitches,True)
            self.transport.extend_audition(True,duration*60/(self.project.bpm*960))

    def hold_chord(self,cid):
        chord=next((c for c in self.project.chords if c.id==cid),None)
        if chord:self.transport.extend_audition(True,chord.duration*60/(self.project.bpm*960))

    def update_shared_views(self,*args):
        if not getattr(self,'workspace_ready',False):return
        if self.main_roll.width()!=self.timeline.width()+2:self.main_roll.resize(self.timeline.width()+2,200)
        if not self.syncing_scroll:
            bar=self.main_roll.horizontalScrollBar();self.shared_scroll.blockSignals(True);self.shared_scroll.setRange(bar.minimum(),bar.maximum());self.shared_scroll.setPageStep(max(1,self.timeline.width()-KEY_W));self.shared_scroll.setValue(bar.value());self.shared_scroll.blockSignals(False)
        primary=self.docked_roll();self.timeline.roll=primary;self.navigator.editor=primary;self.chord_lane.editor=primary
        self.navigator.update_height()
        if primary is not self.main_roll:
            self.main_roll.panels['ruler']=primary.panels['ruler']
        self.timeline.setFixedHeight(primary.bar_ruler_height+RULER_TIME_H)
        for widget in (self.timeline,self.navigator,self.chord_lane,self.harmony_window.top_lane):widget.update()
        for lane in (self.chord_lane,self.roll.lane,self.harmony_window.top_lane):lane.velocity_lane.update()
        self.update_chord_highlight()

    def rolls_linked(self):
        return getattr(self,'workspace_ready',False) and all(self.is_main_view(r) for r in (self.roll,self.harmony_window.roll))

    def docked_roll(self):
        if self.workspace=='score':
            key=self.current_score_panel()
            if key in ('melody','harmony'):
                roll=self.roll if key=='melody' else self.harmony_window.roll
                if self.is_main_view(roll):return roll
            return self.main_roll
        for pane,roll,_,_ in self.view_panes():
            if pane is self.melody_window and not any(self.melody_tabs.isTabVisible(track) for track in (0,1)):continue
            if not pane.isFloating() and self.visibility_actions[pane.key].isChecked():return roll
        return self.main_roll

    def scroll_shared(self,value):
        if self.syncing_scroll or not getattr(self,'workspace_ready',False):return
        self.syncing_scroll=True
        try:
            self.main_roll.horizontalScrollBar().setValue(value)
        finally:self.syncing_scroll=False
        self.update_shared_views()

    def harmony_selection_changed(self,ranges):
        self.selection_changed(ranges);self.update_shared_views()

    def sync_tools(self,source):
        if not self.rolls_linked() or self.syncing_controls:return
        self.syncing_controls=True
        try:
            source_controls=self if source is self.roll else self.harmony_window
            target_controls=self.harmony_window if source is self.roll else self
            target_controls.tool.setCurrentIndex(target_controls.tool.findData(source.tool))
            target_controls.length.setCurrentIndex(source_controls.length.currentIndex());target_controls.length.set_triplet(source_controls.length.triplet);target_controls.dotted.setChecked(source_controls.dotted.isChecked())
            target_controls.roll.tool=source.tool;target_controls.roll.duration=source.duration;target_controls.roll.duration_bars=source.duration_bars
        finally:self.syncing_controls=False

    def chord_selection_views(self,source=None):
        if self.workspace=='score':return (self.roll,self.harmony_window.roll,self.main_roll)
        for pane,r,_,_ in self.view_panes():
            if source is r and pane.isFloating():return (r,)
        return tuple([self.main_roll]+[r for pane,r,_,_ in self.view_panes() if not pane.isFloating()])

    def chord_source_lane(self,source):
        if source is self.harmony_window.roll:return source.lane
        if source is not None and source is not self.main_roll and source.role=='melody' and self.roll_pane(source).isFloating():return source.lane
        return self.chord_lane

    def chord_selection(self,ids,source=None,lane=None):
        if not getattr(self,'workspace_ready',False) or self.harmony_window is None:return
        ids=set(ids)
        session=getattr(self,'chord_move_session',None)
        if session and ids!=session.ids:self.clear_chord_move_session()
        if ids:self.select_element('chords',source)
        lane=lane or self.chord_source_lane(source)
        lane.highlight_ids=ids.copy()
        current=next(iter(ids)) if len(ids)==1 else ''
        anchor=current or self.roll.chord_anchor or self.harmony_window.roll.chord_anchor
        views=self.chord_selection_views(source)
        for r in views:
            r.chord_anchor=anchor
            if (r.selected_chords,r.selected_chord)!=(ids,current):
                r.selected_chords=ids.copy();r.selected_chord=current
                r.lane.update();r.lane.velocity_lane.update()
        if self.harmony_window.roll in views and self.harmony_window.current_id!=current:
            self.harmony_window.select_chord(current,False)
        lane.update();lane.velocity_lane.update()
        if self.chord_lane.editor in views:self.chord_lane.update();self.chord_lane.velocity_lane.update()
        self.update_chord_highlight()

    def select_element(self,kind,source=None):
        if not getattr(self,'workspace_ready',False) or getattr(self,'selecting_elements',False):return
        self.selecting_elements=True
        try:
            if kind!='chords' and getattr(self,'chord_move_session',None):self.clear_chord_move_session()
            chord_changed=False
            for r in self.editing_rolls():
                if kind=='chords' and (r.selected_ids or r.selected_note):
                    r.selected_ids.clear();r.selected_note='';r.refresh_note_selection(notify=False)
                elif kind!='chords' and (r.selected_chords or r.selected_chord or r.hovered_chord):
                    r.selected_chords.clear();r.selected_chord='';r.hovered_chord='';chord_changed=True
            if kind=='chords':
                for ids,_,_ in self.melody_track_state.values():ids.clear()
            if kind=='notes':
                for lane in (self.chord_lane,*(roll.lane for roll in self.editing_rolls())):
                    if chord_changed or lane.highlight_ids or lane.highlight_hover:
                        lane.highlight_ids.clear();lane.highlight_hover='';lane.update();lane.velocity_lane.update()
                self.update_chord_highlight()
            if source:source.edit_target=kind
        finally:self.selecting_elements=False

    def chord_hover(self,cid,source=None,lane=None):
        if not getattr(self,'workspace_ready',False) or self.harmony_window is None:return
        lane=lane or self.chord_source_lane(source);lane.highlight_hover=cid
        views=self.chord_selection_views(source)
        for r in views:
            if r.hovered_chord!=cid:r.hovered_chord=cid;r.lane.update()
        lane.update()
        if self.chord_lane.editor in views and lane is not self.chord_lane:self.chord_lane.update()
        self.update_chord_highlight()

    def chord_command(self,command,payload,source=None):
        from lingfeng.music.chord_operations import blank_chord, change_chords, split_chords, merge_chords, move_chords, ChordClipboard
        source=source or self.active_roll()
        if command=='quality_picker':
            from PySide6.QtWidgets import QDialog
            from lingfeng.ui.chord_settings_dialog import ChordQualityPickerDialog
            if len(payload)!=1:return
            chord=next((c for c in self.project.chords if c.id in payload),None)
            if chord is None or not chord.recognized or chord.recognition_disabled:return
            parent=source.window();dialog=ChordQualityPickerDialog(chord.root,chord.quality,parent)
            code=dialog.value() if dialog.exec()==QDialog.DialogCode.Accepted else None
            dialog.deleteLater()
            self.restore_dialog_origin(parent,source)
            if code is None:return
            command='quality:'+code
        if command=='recognition_name':
            from lingfeng.music.recognition import choose_chord_candidate
            cid,candidate=payload
            def choose(p):
                chord=next((c for c in p.chords if c.id==cid),None)
                if chord is not None:choose_chord_candidate(p,chord,candidate)
            self.mutate(tr('已采用和弦识别名称'),choose,source=source,score_spellings=True)
            return
        if command=='mark':
            from PySide6.QtWidgets import QDialog
            from lingfeng.ui.dialogs import ChordMarkerDialog
            from lingfeng.music.recognition import set_marker
            chord=next((c for c in self.project.chords if c.id==payload),None)
            if chord is None:return
            parent=source.window();dialog=ChordMarkerDialog(chord,self.project,parent)
            if dialog.exec()==QDialog.DialogCode.Accepted:
                value=dialog.value()
                self.mutate(tr('已标记和弦'),lambda p:set_marker(next(c for c in p.chords if c.id==payload),**value),source=source)
            self.restore_dialog_origin(parent,source);return
        if command.startswith('recognition:'):
            from lingfeng.music.recognition import set_recognition_disabled
            disabled=command.endswith(':1')
            def recognition(p):
                for chord in p.chords:
                    if chord.id in payload:set_recognition_disabled(chord,disabled,p)
            self.mutate(tr('已更新和弦识别设置'),recognition,source=source);return
        if command=='progression':self.apply_progression(payload,source);return
        if command=='capture_progression':self.capture_progression(payload);return
        if command=='search_progressions':self.search_progressions(payload,source);return
        if command=='split_at':
            from lingfeng.music.chord_operations import split_at_position
            result=set()
            if self.mutate(tr('已分割和弦'),lambda p:result.update(split_at_position(p,payload)),source=source):self.chord_selection(result,source)
            return
        if command.startswith('move:') or command=='drag_move':
            ids,delta,drop=(payload,int(command.split(':')[1]),None) if command.startswith('move:') else payload
            self.move_chord_selection(source,set(ids),delta,drop);return
        if command=='insert':
            tick,length=payload if isinstance(payload,tuple) else (payload,'auto')
            chord=blank_chord(self.project,tick,length)
            if chord and self.mutate(tr('已插入空白和弦'),lambda p:p.put_chord(chord),source=source):self.chord_selection({chord.id},source)
        elif command in ('copy','cut'):
            selected=[c for c in self.project.chords if c.id in payload]
            clipboard=ChordClipboard.capture(selected,self.project)
            if command=='cut':
                if clipboard is None:return
                ids={c.id for c in selected}
                def clear(p):
                    for chord in p.chords:
                        if chord.id not in ids:continue
                        # Keep every region and its rhythm settings. Removing
                        # regions would refill gaps at bar boundaries instead.
                        chord.notes=[];chord.recognized=False;chord.marked=False
                        chord.include_instrument_in_recognition=False
                        chord.instrument_symbol_preference=None
                if not self.mutate(tr('已剪切 {0} 个和弦；原位置保留 N.C.。',len(selected)),clear,source=source):return
            self.chord_clipboard=clipboard;self.clipboard_kind='chords'
            for r in self.editing_rolls():r.has_chord_clipboard=self.chord_clipboard is not None;r.chord_clipboard=self.chord_clipboard
            if command=='copy':self.status_message(tr('已复制 {0} 个和弦；粘贴时按时间顺序相邻排列。',len(payload)))
        elif command in ('paste','split','merge'):
            if command=='paste' and not self.chord_clipboard:return
            if command=='paste' and (not self.chord_clipboard.can_paste(self.project,payload) or payload==self.project.end):return
            result=set()
            def edit(p):
                result.update(self.chord_clipboard.paste(p,payload) if command=='paste' else (split_chords if command=='split' else merge_chords)(p,set(payload)))
            if self.mutate(tr('已更新所选和弦'),edit,source=source):self.chord_selection(result,source)
        elif command.startswith('velocity:'):
            value=max(1,min(127,int(command.split(':')[1])))
            def velocity(p):
                from lingfeng.music.chord_operations import set_chord_velocity
                for chord in p.chords:
                    if chord.id in payload:
                        set_chord_velocity(chord,value)
            self.mutate(tr('已更新和弦力度'),velocity,source=source)
        elif command=='audition':
            if payload:
                self.transport.begin_chords_audition([c for c in self.project.chords if c.id in payload],self.project.bpm)
                self.transport.end_audition(True)
        else:
            if self.mutate(tr('已更新所选和弦'),lambda p:change_chords(p,set(payload),command),source=source) and len(payload)==1 and command!='delete' and not command.startswith('recognition_source:'):
                self.audition_chord(next(iter(payload)));self.transport.end_audition(True)

    def clear_chord_move_session(self):
        self.chord_move_session=None
        if not getattr(self,'workspace_ready',False):return
        existing={c.id for c in self.project.chords}
        for r in self.editing_rolls():
            r.transient_chord_ids=set();r.selected_chords.intersection_update(existing)
            if r.selected_chord not in existing:r.selected_chord=''

    def chord_selection_extents(self,roll):
        session=getattr(self,'chord_move_session',None)
        if session and session.ids==roll.selected_chords:return session.extents()
        return [c for c in self.project.chords if c.id in roll.selected_chords]

    def move_chord_selection(self,source,ids,delta,drop=None):
        from lingfeng.music.chord_operations import ChordMoveSession
        from lingfeng.music.meter import region_at
        if not ids or not delta:return
        session=getattr(self,'chord_move_session',None)
        if not session or session.ids!=ids:
            try:session=ChordMoveSession.capture(self.project,ids)
            except ValueError as exc:self.status_message(str(exc));return
        bounds=session.bounds
        if drop is not None and 0<=drop<self.project.end:
            target=region_at(self.project,drop)
            if target[2]!=bounds[2]:self.status_message(tr('目标拍号与来源和弦不匹配。'));return
            bounds=target
        self.chord_move_session=session
        views=self.chord_selection_views(source)
        for r in views:r.transient_chord_ids=set(ids)
        if self.mutate(tr('已移动所选和弦'),lambda p:session.apply(p,delta,bounds),source=source,preserve_chord_move=True):
            session.delta+=delta;session.bounds=bounds
            for r in views:r.selected_chords=set(ids);r.refresh()
            if drop is None:source.ensure_events_visible(session.extents(),dx=delta)
            if not any(c.id in ids for c in self.project.chords):self.status_message(tr('所选和弦已移出边界；保持选择并反向移动可还原，取消选择后请撤销。'))

    def next_chord(self,roll):
        ordered=sorted(self.project.chords,key=lambda c:c.start)
        current=[i for i,c in enumerate(ordered) if c.id in roll.selected_chords]
        if not current:return
        chord=ordered[(max(current)+1)%len(ordered)]
        focus=QApplication.focusWidget();lane=focus if isinstance(focus,ChordLane) else self.chord_source_lane(roll)
        lane.selection_event({chord.id});roll.edit_target='chords';roll.ensure_tick(chord.start);self.update_shared_views()
        self.audition_chord(chord.id);self.transport.end_audition(True)

    def open_score_roll(self,role,tick):
        if role in self.lyric_panels:
            self.seek(self.roll.snap_time(tick));self.batch_lyrics(key=role)
            panel=self.lyric_panels[role]
            if self.workspace=='score' and not panel.dirty:panel.use_selection()
            return
        if role=='chords':
            chord=self.project.chord_at(tick);self.open_harmony(chord.id if chord else '',tick);return
        self.show_score_panel('harmony' if role=='chords' else 'melody')
        if role in ('melody','instrument'):self.switch_melody_track(int(role=='instrument'))
        roll=self.harmony_window.roll if role=='chords' else self.roll;roll.ensure_tick(tick)
        roll.setFocus()

    def switch_melody_track(self,track):
        roll=self.roll
        if track not in (0,1) or roll.melody_track==track:return
        if self.workspace=='compose':
            pane=self.melody_floats.get(track)
            if not self.melody_view_actions[track].isChecked() or (pane and pane.isFloating()):return
        self.transport.end_audition(role=self.melody_audio_role(),cancel=True)
        self.melody_track_state[roll.melody_track]=(set(roll.selected_ids),roll.previous_duration,roll.previous_note_id)
        roll.melody_track=track
        roll.notes=self.project.melody_notes(track)
        ids,roll.previous_duration,roll.previous_note_id=self.melody_track_state.get(track,(set(),None,''))
        roll.selected_ids=roll.expand_note_selection(ids) if ids else set()
        roll.selected_note=next(iter(roll.selected_ids),'')
        if roll.selected_ids:roll.edit_target='notes'
        blocked=self.melody_tabs.blockSignals(True)
        self.melody_tabs.setCurrentIndex(track)
        self.melody_tabs.blockSignals(blocked)
        roll.refresh_notes(notify=False)
        if self.midi_input.target!='chords':
            self.midi_input.reset()
            self.midi_input.target='instrument' if track else 'melody'

    def melody_roll_for(self,track,reveal=False):
        if reveal and self.workspace=='compose':self.melody_view_actions[track].setChecked(True)
        pane=self.melody_floats.get(track)
        if self.workspace=='compose' and pane is not None and pane.isFloating():
            if reveal:
                if pane.isMinimized():pane.showNormal()
                pane.show();pane.raise_();pane.activateWindow()
            return pane.roll
        if reveal:self.switch_melody_track(track)
        return self.roll

    def mount_melody_tabs(self,compose):
        available=[]
        blocked=self.melody_tabs.blockSignals(True)
        for track in (0,1):
            pane=self.melody_floats.get(track)
            visible=not compose or (self.melody_view_actions[track].isChecked() and not (pane and pane.isFloating()))
            self.melody_tabs.setTabVisible(track,visible)
            if visible:available.append(track)
        if self.roll.melody_track in available:self.melody_tabs.setCurrentIndex(self.roll.melody_track)
        self.melody_tabs.blockSignals(blocked)
        if available and self.roll.melody_track not in available:self.switch_melody_track(available[0])
        compose_title=self.melody_window.title_bar
        score_title=self.score_floats['melody'].title_bar
        title=self.melody_header
        if compose and self.melody_window.isFloating():title=compose_title
        elif not compose and self.score_panel_state['melody']['floating']:title=score_title
        if self.melody_tabs.parentWidget() is not title:
            alignment=Qt.AlignmentFlag.AlignBottom if title is self.melody_header else Qt.AlignmentFlag(0)
            title.layout().insertWidget(0,self.melody_tabs,0,alignment)
        show_tabs=len(available)>1
        self.melody_tabs.setVisible(show_tabs)
        self.melody_header.setVisible(title is self.melody_header)
        self.melody_header.update()
        self.refresh_melody_title()
        for floating in (compose_title,score_title):floating.caption.setVisible(title is not floating or not show_tabs)

    def refresh_melody_title(self):
        available=[track for track in (0,1) if self.melody_tabs.isTabVisible(track)]
        single=self.workspace=='compose' and not self.melody_window.isFloating() and len(available)==1
        self.melody_title.setText(self.project.melody_name(available[0]) if single else '')
        self.melody_title.setVisible(single)

    def refresh_melody_tabs(self):
        for track in (0,1):
            name=self.project.melody_name(track)
            self.melody_tabs.setTabText(track,name)
            self.melody_tabs.setTabToolTip(track,tr('{0} · 双击重命名',name))
            self.melody_view_actions[track].setText(name)
            if (pane:=self.melody_floats.get(track)) is not None:
                pane.setWindowTitle(name);pane.title_bar.caption.setText(name)
        self.refresh_melody_title()

    def melody_tab_menu(self,pos):
        track=self.melody_tabs.tabAt(pos)
        if track<0:return
        menu=QMenu(self.melody_tabs)
        menu.addAction(tr('重命名旋律轨…'),lambda:self.rename_melody_track(track))
        menu.exec(self.melody_tabs.mapToGlobal(pos))

    def rename_melody_track(self,track):
        if track not in (0,1):return
        name,accepted=QInputDialog.getText(self.melody_tabs.window(),tr('重命名旋律轨'),tr('轨道名称'),text=self.project.melody_name(track))
        name=name.strip()
        if accepted and name!=self.project.melody_name(track):
            names=self.project.melody_names.copy();names[track]=name
            self.mutate(tr('已重命名旋律轨'),lambda project:setattr(project,'melody_names',names),source=self.roll)

    def select_section_contents(self,start,end,target):
        starts=self.project.starts
        left,right=starts[start],starts[end]
        self.selection_changed([starts[i:i+2] for i in range(start,end)])
        if target=='bars':
            self.select_element('notes',self.active_roll())
            for roll in self.editing_rolls():
                roll.selected_ids.clear();roll.selected_note='';roll.edit_target='notes';roll.refresh_note_selection(notify=False)
            for ids,_,_ in self.melody_track_state.values():ids.clear()
            return
        if target=='chords':
            lane=self.harmony_window.roll.lane if self.workspace=='score' else self.chord_lane
            if self.workspace=='score':self.show_score_panel('harmony')
            else:self.visibility_actions['chords'].setChecked(True)
            lane.selection_event({c.id for c in self.project.chords if left<=c.start<right})
            lane.setFocus()
            return
        focus=self.active_roll() if target=='all_notes' else self.harmony_window.roll if target=='harmony' else self.roll
        if target in ('melody','instrument'):
            if self.workspace=='score':self.show_score_panel('melody')
            focus=self.melody_roll_for(int(target=='instrument'),reveal=True)
            if self.workspace=='compose':self.show_roll_in_place(self.roll_pane(focus))
        elif target=='harmony':
            if self.workspace=='score':self.show_score_panel('harmony')
            else:self.show_roll_in_place(self.harmony_window)
        self.select_element('notes',focus)
        # Notes sustained into the section are part of its audible contents.
        def note_ids(notes):
            return {n.id for n in notes if n.start<right and n.end>left}
        melody_views=[]
        for track,role in enumerate(('melody','instrument')):
            roll=self.melody_roll_for(track)
            ids=note_ids(self.project.melody_notes(track)) if target in (role,'all_notes') else set()
            if roll.melody_track==track:
                roll.selected_ids=ids
                melody_views.append(roll)
            else:
                _,duration,nid=self.melody_track_state.get(track,(set(),None,''))
                self.melody_track_state[track]=(ids,duration,nid)
        harmony=self.harmony_window.roll
        harmony.selected_ids=note_ids(harmony.notes) if target in ('harmony','all_notes') else set()
        for roll in (*melody_views,harmony):
            roll.edit_target='notes'
            roll.selected_note=next(iter(roll.selected_ids),'')
            roll.refresh_note_selection(notify=False)
        if target=='all_notes':
            # Prefer the current melody, but open a populated roll when that
            # track has no notes in this section (including hidden tabs).
            if not focus.selected_ids:
                track=next((track for track in (0,1) if note_ids(self.project.melody_notes(track))),None)
                if track is not None:focus=self.melody_roll_for(track,reveal=True)
                elif harmony.selected_ids:focus=harmony
            if focus.selected_ids:
                if self.workspace=='score':self.show_score_panel('harmony' if focus is harmony else 'melody')
                else:self.show_roll_in_place(self.roll_pane(focus))
        self.reveal_section_notes(focus,left,right)
        focus.setFocus()

    def reveal_section_notes(self,roll,left,right):
        """Reveal an audible part of the selection without moving a visible view."""
        notes=roll.selected_notes()
        if not notes:return
        top=roll.ruler_height;bottom=roll.viewport().height()
        edge=roll.viewport().width()
        candidates=[]
        for note in notes:
            # A sustained note can begin before this section. Locate its
            # selected section, rather than jumping back to its onset.
            x1=roll.x_at(max(left,note.start));x2=roll.x_at(min(right,note.end))
            y=roll.y_at(note.pitch)
            if note.pitch in roll.pitch_rows and x2>KEY_W and x1<edge and top<=y and y+roll.row_height<=bottom:return
            dx=min(0,x2-KEY_W) if x2<=KEY_W else max(0,x1-edge+1)
            dy=min(0,y-top) if y<top else max(0,y+roll.row_height-bottom)
            candidates.append((abs(dx)/max(1,edge-KEY_W)+abs(dy)/max(1,bottom-top),note,x1,x2,y))
        _,note,x1,x2,y=min(candidates,key=lambda item:item[0])
        if note.pitch not in roll.pitch_rows and roll.pitch_range is not None:
            # A manually restricted pitch range must include the selected note
            # for scrolling to expose it.
            low,high=roll.pitch_range
            roll.set_pitch_range(min(low,note.pitch),max(high,note.pitch))
            y=roll.y_at(note.pitch)
        horizontal=roll.horizontalScrollBar().value()
        vertical=roll.verticalScrollBar().value()
        if x2<=KEY_W or x1>=edge:
            horizontal+=round(x1-KEY_W-max(0,edge-KEY_W)/4)
        if y<top or y+roll.row_height>bottom:
            vertical+=round(y+roll.row_height/2-(top+bottom)/2)
        roll.pan_to(horizontal,vertical)

    def select_pasted_range(self,note_ids,chord_ids,source):
        if chord_ids:self.chord_selection(chord_ids,source)
        else:self.select_element('notes',source)
        for track,ids in enumerate(note_ids):
            roll=self.melody_roll_for(track)
            if roll.melody_track==track:
                roll.selected_ids=roll.expand_note_selection(ids) if ids else set()
                roll.selected_note=next(iter(roll.selected_ids),'')
                if roll.selected_ids:roll.edit_target='notes'
                roll.refresh_note_selection(notify=False)
            else:
                _,duration,nid=self.melody_track_state.get(track,(set(),None,''))
                self.melody_track_state[track]=(ids,duration,nid)
        harmony=self.harmony_window.roll
        harmony.selected_ids.clear();harmony.selected_note=''
        harmony.refresh_note_selection(notify=False)

    def enable_native_frame(self):
        from lingfeng.ui.windowing import enable_frame
        enable_frame(self)

    def resize_hit(self,point):
        from lingfeng.ui.windowing import resize_hit
        return resize_hit(self,point)

    def nativeEvent(self,eventType,message):
        from lingfeng.ui.windowing import native_frame_event
        return native_frame_event(self,message) or super().nativeEvent(eventType,message)

"""Compact workspace containers; all views share one project and transport."""
from PySide6.QtCore import Qt,QPointF,QPoint,QRectF,Signal,QTimer,QSize,QEvent
from PySide6.QtGui import QPainter,QPen,QFont,QColor,QShortcut,QKeySequence,QAction
from PySide6.QtWidgets import (QWidget,QFrame,QHBoxLayout,QVBoxLayout,QPushButton,QLabel,QToolButton,
    QMenu,QSplitter,QTabWidget,QStackedWidget,QComboBox,QSizePolicy,QApplication,QListWidget,QScrollArea,QScrollBar,QAbstractButton,QMenuBar,QCheckBox,QSlider)
from .i18n import tr
from .model import PPQ,pitch_name,merge_ranges
from .controls import SizeControl,IconButton
from .layout import FlowLayout
from .editor import PianoRoll,ChordLane,TimelineNavigator,KEY_W
from .theme import color
from .presentation import pair_candidate,add_compression,contiguous,annotation_allowed,active_compressions
from .painting import cached_layer,roll_view_key
from .timeline import TimelineGesture,RULER_TIME_H
from .navigation import watch_scrollbar
import time


class FloatingPane(QFrame):
    topLevelChanged=Signal(bool)
    def __init__(self,title,owner,key):
        super().__init__(owner);self.owner=owner;self.key=key;self.floating=False;self.floating_visible=False;self.body=None
        self.setWindowTitle(title);self.setObjectName('editorCard');self.box=QVBoxLayout(self);self.box.setContentsMargins(0,0,0,0);self.box.setSpacing(0)
        self.setWindowIcon(owner.windowIcon());self.title_bar=PaneTitleBar(self,title);self.box.addWidget(self.title_bar);self.title_bar.hide()
        # Floating panes are peer native windows, while Python keeps the shared
        # project owner. Dispose them even when they are currently parentless.
        owner.destroyed.connect(self.deleteLater)
    def setWidget(self,body):self.body=body;self.box.addWidget(body)
    def widget(self):return self.body
    def setAllowedAreas(self,*args):pass
    def isFloating(self):return self.floating
    def isModal(self):return False
    def setFloating(self,value):
        if self.floating==bool(value):return
        self.floating=bool(value);self.floating_visible=bool(value);self.hide()
        self.setWindowState(Qt.WindowState.WindowNoState)
        # A native owner forces its windows above it and hides them on minimize.
        # Taskbar grouping comes from the process AppUserModelID, not ownership.
        self.setParent(None if value else self.owner,(Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowMinMaxButtonsHint|Qt.WindowType.WindowCloseButtonHint) if value else Qt.WindowType.Widget)
        self.title_bar.setVisible(bool(value));self._native_frame=False
        if value:
            from .windowing import enable_frame
            enable_frame(self,taskbar=True)
        if value:self.resize(1000,560)
        if self.key in ('melody','harmony') and getattr(self.owner,'workspace_ready',False) and not getattr(self.owner,'switching_workspace',False):
            action=self.owner.visibility_actions[self.key];blocked=action.blockSignals(True)
            action.setChecked(not value);action.blockSignals(blocked)
        self.topLevelChanged.emit(value)
        if getattr(self.owner,'workspace_ready',False):self.owner.chord_layout_changed()
    def closeEvent(self,event):
        if self.key.startswith('score_'):
            self.owner.set_score_panel_visible(self.key[6:],False);event.ignore();return
        if self.key in ('melody','harmony') and self.isFloating():
            self.floating_visible=False;event.ignore();self.hide();self.owner.chord_layout_changed();return
        if self.key=='score':self.owner.edit_toggle.setChecked(False);self.owner.toggle_editor()
        else:self.owner.visibility_actions[self.key].setChecked(False)
        event.ignore();self.hide()

    def nativeEvent(self,eventType,message):
        from .windowing import native_frame_event
        return native_frame_event(self,message) or super().nativeEvent(eventType,message)

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type()==QEvent.Type.WindowStateChange and hasattr(self,'title_bar'):self.title_bar.update_maximize()


class PaneTitleBar(QWidget):
    def __init__(self,pane,title):
        super().__init__(pane);self.pane=pane;row=QHBoxLayout(self);row.setContentsMargins(8,2,2,2);row.setSpacing(2)
        label=QLabel(title);label.setStyleSheet('font-weight:600');row.addWidget(label);row.addStretch()
        self.dock=IconButton('dock');self.dock.activated.connect(lambda:pane.owner.toggle_roll_floating(pane));row.addWidget(self.dock)
        self.buttons=[]
        for kind,slot in [('minimize',pane.showMinimized),('maximize',self.maximize),('close',pane.close)]:
            button=IconButton(kind);button.setFixedSize(38,30);button.setObjectName('windowControl');button.activated.connect(slot);row.addWidget(button);self.buttons.append(button)
        self.dock.setFixedSize(38,30);self.dock.setObjectName('windowControl')
        self.minimize_button,self.maximize_button,self.close_button=self.buttons
    def maximize(self):
        self.pane.showNormal() if self.pane.isMaximized() else self.pane.showMaximized()
        self.update_maximize()
    def update_maximize(self):self.maximize_button.set_kind('restore' if self.pane.isMaximized() else 'maximize')
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.pane.windowHandle():self.pane.windowHandle().startSystemMove()
    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:self.maximize()


class TitleBar(QWidget):
    def __init__(self,owner,menu):
        super().__init__(owner);self.owner=owner;self.menu=menu;self.setFixedHeight(34)
        layout=QHBoxLayout(self);layout.setContentsMargins(5,0,0,0);layout.setSpacing(0)
        # Brand and commands share the same text renderer and baseline.
        font=QFont('Microsoft YaHei');font.setPixelSize(12);font.setBold(True);menu.setFont(font)
        self.brand=QAction('Lingfeng' if owner.language=='en' else '伶风',menu);self.brand.setFont(font);self.brand.setEnabled(False)
        menu.insertAction(menu.actions()[0],self.brand);menu.setFixedHeight(30);layout.addWidget(menu);layout.addStretch()
        self.window_buttons=[]
        for kind,slot in [('minimize',owner.showMinimized),('maximize',self.maximize),('close',owner.close)]:
            b=IconButton(kind);b.setFixedSize(38,30);b.setObjectName('windowControl');b.activated.connect(slot);layout.addWidget(b);self.window_buttons.append(b)
        owner.installEventFilter(self)
    def eventFilter(self,obj,event):
        if obj is self.owner and event.type()==QEvent.Type.WindowStateChange:self.window_buttons[1].set_kind('restore' if self.owner.isMaximized() else 'maximize')
        return super().eventFilter(obj,event)
    def maximize(self):self.owner.showNormal() if self.owner.isMaximized() else self.owner.showMaximized()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton and self.owner.windowHandle():self.owner.windowHandle().startSystemMove()
    def mouseDoubleClickEvent(self,event):self.maximize()


class CurrentStack(QStackedWidget):
    """Hidden chord controls must not impose their height on the melody tab."""
    def minimumSizeHint(self):
        return self.currentWidget().minimumSizeHint() if self.currentWidget() else QSize(100,100)
    def sizeHint(self):
        return self.currentWidget().sizeHint() if self.currentWidget() else QSize(400,240)


class RollTransport(QWidget):
    """Shared musical transport, with following local to this floating view."""
    def __init__(self,owner):
        super().__init__();row=QHBoxLayout(self);row.setContentsMargins(3,2,3,2);row.setSpacing(7);row.addStretch()
        self.play=IconButton('pause' if owner.transport.playing else 'play');self.play.activated.connect(owner.toggle_play);row.addWidget(self.play)
        self.replay=IconButton('replay');self.replay.activated.connect(owner.replay);self.replay.doubleActivated.connect(owner.return_to_start);row.addWidget(self.replay)
        self.loop=QCheckBox(tr('循环选区'));self.loop.setChecked(owner.loop.isChecked());self.loop.toggled.connect(owner.loop.setChecked);row.addWidget(self.loop)
        self.follow=QCheckBox(tr('跟随播放游标'));self.follow.setChecked(True);self.follow.setToolTip(tr('跟随此窗口的播放游标；同步时间轴时与主界面的跟随设置联动。'));row.addWidget(self.follow)
        self.bpm=SizeControl(owner.project.bpm,20,300);self.bpm.setSuffix(' BPM');self.bpm.setFixedWidth(108);self.bpm.valueChanged.connect(owner.set_bpm);row.addWidget(self.bpm)
        self.options=IconButton('options');self.options.setToolTip(tr('其它选项'));self.options.setAccessibleName(tr('其它选项'));self.options.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);self.options.setMenu(QMenu(self.options));row.addWidget(self.options)


class StatusHint(QLabel):
    """One-line, bounded hint; a long message never widens the window."""
    def __init__(self):
        super().__init__();self.message='';self.setMinimumWidth(0);self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
    def set_message(self,text):
        self.message=' '.join(str(text).split());self.message=self.message if len(self.message)<=80 else self.message[:79]+'…';self.fit()
    def fit(self):self.setText(self.fontMetrics().elidedText(self.message,Qt.TextElideMode.ElideRight,max(0,self.width())))
    def resizeEvent(self,event):super().resizeEvent(event);self.fit()


class RollVolumeControls(QWidget):
    """Shared footer: concise status and two synchronized track controls."""
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.sliders={};self.mutes={};self.labels={}
        row=QHBoxLayout(self);row.setContentsMargins(8,2,8,2);row.setSpacing(10)
        self.hint=StatusHint();row.addWidget(self.hint,1);self.groups=[]
        for key,title in [('melody','旋律'),('chords','和弦')]:
            group=QWidget();layout=QHBoxLayout(group);layout.setContentsMargins(0,0,0,0);layout.setSpacing(6)
            layout.addWidget(QLabel(tr(title)));mute=QPushButton(tr('静音'));mute.setCheckable(True);mute.setToolTip(tr('静音（试听状态，不改变导出 MIDI）'));layout.addWidget(mute)
            slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(0,127);slider.setFixedWidth(85);slider.setToolTip(tr('轨道音量 CC7，独立于音符力度'));layout.addWidget(slider)
            label=QLabel();label.setFixedWidth(27);layout.addWidget(label);row.addWidget(group);self.groups.append(group)
            self.sliders[key]=slider;self.mutes[key]=mute;self.labels[key]=label
            slider.valueChanged.connect(owner.volume_sliders[key].setValue)
            mute.toggled.connect(owner.mute_buttons[key].setChecked);mute.clicked.connect(owner.update_audio)
            owner.volume_sliders[key].valueChanged.connect(self.sync)
            owner.mute_buttons[key].toggled.connect(self.sync)
        owner.statusBar().messageChanged.connect(self.set_status);self.set_status(owner.statusBar().currentMessage());self.sync()

    def set_status(self,text):
        self.hint.set_message(text if self.owner.show_information else '')

    def set_mixer_visible(self,visible):
        for group in self.groups:group.setVisible(visible)

    def sync(self,*args):
        for key in self.sliders:
            slider=self.sliders[key];blocked=slider.blockSignals(True);slider.setValue(self.owner.volume_sliders[key].value());slider.blockSignals(blocked)
            self.labels[key].setText(str(slider.value()))
            mute=self.mutes[key];blocked=mute.blockSignals(True);mute.setChecked(self.owner.mute_buttons[key].isChecked());mute.blockSignals(blocked)


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
        cached_layer(self,p,(roll_view_key(e),self.offset()),lambda painter:e.paint_ruler(painter,self.width(),self.height(),self.x_at))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setClipRect(KEY_W,0,self.width()-KEY_W,self.height())
        if e.anchor_tick is not None:
            p.setPen(QPen(color('#426BAA'),1.2,Qt.PenStyle.DashLine));p.drawLine(QPointF(self.x_at(e.anchor_tick),0),QPointF(self.x_at(e.anchor_tick),self.height()))
        p.setPen(QPen(color('#D15F49'),2));p.drawLine(QPointF(self.x_at(e.visual_tick()),0),QPointF(self.x_at(e.visual_tick()),self.height()))
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


from .structure import LogicPanel


class WorkspaceMixin:
    def organize_workspace(self):
        self.workspace_ready=False;self.mounting=False;self.syncing_controls=False;self.syncing_scroll=False;self.syncing_time=False;self.auto_follow=False;self.compose_float_state=(False,False)
        self.statusBar().setSizeGripEnabled(False)
        self.statusBar().hide()
        ed=self.editor.layout();tools=ed.itemAt(0).layout();bottom=ed.takeAt(ed.count()-1).layout()
        bottom.removeWidget(self.view_controls);tools.addWidget(QLabel(tr('吸附')));tools.addWidget(self.grid);tools.addWidget(self.view_controls);tools.removeWidget(self.view_controls.options);self.view_controls.options.hide()
        tools.removeWidget(self.harmony_button);self.harmony_button.hide()
        ed.takeAt(0);self.melody_toolbar=QWidget();self.melody_toolbar.setLayout(tools);ed.insertWidget(0,self.melody_toolbar)
        self.melody_window=FloatingPane(tr('旋律钢琴卷帘'),self,'melody');self.melody_window.setWidget(self.editor)
        self.melody_header=QWidget();head=QHBoxLayout(self.melody_header);head.setContentsMargins(8,2,3,2);head.setSpacing(8)
        title=QLabel(tr('旋律钢琴卷帘'));title.setStyleSheet('font-weight:600');head.addWidget(title)
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
        self.melody_float=IconButton('float');self.melody_float.activated.connect(lambda:self.toggle_roll_floating(self.melody_window));head.addWidget(self.melody_float);ed.insertWidget(0,self.melody_header)
        self.melody_hide=IconButton('close');self.melody_hide.setToolTip(tr('隐藏旋律卷帘'));self.melody_hide.setAccessibleName(tr('隐藏旋律卷帘'));self.melody_hide.activated.connect(lambda:self.visibility_actions['melody'].setChecked(False));head.addWidget(self.melody_hide)
        ed.insertWidget(1,self.melody_transport)
        self.melody_volume=RollVolumeControls(self);ed.addWidget(self.melody_volume)
        # Keep a main-window time view even while both editors are floating.
        self.main_roll=PianoRoll(self.project,self.centralWidget());self.main_roll.main_timeline_state=True;self.main_roll.hide()
        for key in ('chords','navigator','velocity'):self.main_roll.set_panel(key,False)
        self.main_roll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);self.main_roll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.main_roll.selectionChanged.connect(self.selection_changed);self.main_roll.playheadChanged.connect(self.seek);self.main_roll.playRequested.connect(self.play_from)
        self.main_roll.contextRequested.connect(self.edit_context);self.main_roll.markerRequested.connect(self.edit_marker);self.main_roll.insertMeasureRequested.connect(self.insert_measure)
        self.main_roll.chordRequested.connect(self.edit_chord);self.main_roll.harmonyRequested.connect(self.open_harmony);self.main_roll.deleteChord.connect(self.delete_chord);self.main_roll.chordMoved.connect(self.move_chord)
        self.main_roll.chordSelected.connect(self.select_chord)
        self.navigator=TimelineNavigator(self.roll);self.navigator.setFixedHeight(38);self.timeline=Timeline(self.roll)
        self.compose_layout.setContentsMargins(6,4,6,4);self.compose_layout.setSpacing(3)
        shell=self.centralWidget();shell.layout().insertWidget(shell.layout().indexOf(self.stack),self.navigator);self.compose_layout.addWidget(self.timeline)
        self.tracks=QSplitter(Qt.Orientation.Vertical);self.tracks.setChildrenCollapsible(False);self.tracks.setHandleWidth(4);self.compose_layout.addWidget(self.tracks,1)
        self.compose_spacer=QWidget();self.compose_spacer.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Expanding);self.compose_layout.addWidget(self.compose_spacer);self.compose_spacer.hide()
        self.chord_lane=ChordLane(self.roll);self.chord_lane.structure=False;self.chord_lane.setFixedHeight(62)
        self.shared_scroll=QScrollBar(Qt.Orientation.Horizontal);self.shared_scroll.setFixedHeight(16);self.shared_scroll.setToolTip(tr('共享时间轴'));self.shared_scroll.valueChanged.connect(self.scroll_shared);self.compose_layout.addWidget(self.shared_scroll)
        watch_scrollbar(self.shared_scroll,lambda:self.cancel_follow(self.main_roll))
        self.mixer_sources=QWidget(self);self.mixer_sources.setLayout(bottom);self.mixer_sources.hide()
        self.audio_footer=RollVolumeControls(self);shell.layout().addWidget(self.audio_footer)
        from .harmony import HarmonyWindow
        self.harmony_window=HarmonyWindow(self)
        self.score_tools=FloatingPane(tr('制谱编辑器'),self,'score');body=QWidget();box=QVBoxLayout(body);box.setContentsMargins(2,2,2,2);box.setSpacing(2);self.score_tools.setWidget(body)
        self.score_shared_tools=QWidget();self.score_shared_layout=QVBoxLayout(self.score_shared_tools);self.score_shared_layout.setContentsMargins(0,0,0,0);box.addWidget(self.score_shared_tools)
        self.score_tabs=QTabWidget();self.score_roll_stack=self.score_tabs
        self.score_melody_page=QWidget();self.score_melody_layout=QVBoxLayout(self.score_melody_page);self.score_melody_layout.setContentsMargins(0,0,0,0)
        self.score_harmony_page=QWidget();self.score_harmony_layout=QVBoxLayout(self.score_harmony_page);self.score_harmony_layout.setContentsMargins(0,0,0,0)
        self.score_tabs.addTab(self.score_melody_page,tr('旋律卷帘'));self.score_tabs.addTab(self.score_harmony_page,tr('和弦卷帘'))
        self.logic_panel=LogicPanel(self);logic_scroll=QScrollArea();logic_scroll.setWidgetResizable(True);logic_scroll.setFrameShape(QFrame.Shape.NoFrame);logic_scroll.setWidget(self.logic_panel);logic_scroll.setMinimumHeight(80);
        from .lyricpanel import LyricsPanel
        self.lyric_panel=LyricsPanel(self);self.score_tabs.addTab(self.lyric_panel,tr('歌词'));self.score_tabs.addTab(logic_scroll,tr('结构逻辑'));box.addWidget(self.score_tabs)
        self.score_pages=dict(melody=self.score_melody_page,harmony=self.score_harmony_page,lyrics=self.lyric_panel,logic=logic_scroll)
        self.score_labels=dict(melody='旋律卷帘',harmony='和弦卷帘',lyrics='歌词',logic='结构逻辑')
        self.score_panel_state={key:dict(visible=True,floating=False) for key in self.score_pages}
        self.score_floats={key:FloatingPane(tr(self.score_labels[key]),self,'score_'+key) for key in self.score_pages}
        self.score_view_actions={}
        for key in self.score_pages:
            action=QAction(tr(self.score_labels[key]),self);action.setCheckable(True);action.setChecked(True)
            action.toggled.connect(lambda value,k=key:self.set_score_panel_visible(k,value));self.score_view_actions[key]=action
        self.score_footer=RollVolumeControls(self);box.addWidget(self.score_footer)
        self.score_tools.setMinimumHeight(100)
        self.score_float=IconButton('float');self.score_float.setToolTip(tr('悬浮当前选项卡'));self.score_float.setAccessibleName(tr('悬浮当前选项卡'));self.score_float.activated.connect(lambda:self.toggle_score_panel_floating(self.current_score_panel()))
        self.score_close=IconButton('close');self.score_close.setToolTip(tr('关闭当前选项卡'));self.score_close.setAccessibleName(tr('关闭当前选项卡'));self.score_close.activated.connect(lambda:self.set_score_panel_visible(self.current_score_panel(),False))
        corner=QWidget();corner_layout=QHBoxLayout(corner);corner_layout.setContentsMargins(0,0,0,0);corner_layout.setSpacing(2);corner_layout.addWidget(self.score_float);corner_layout.addWidget(self.score_close);self.score_tabs.setCornerWidget(corner)
        self.score_tabs.currentChanged.connect(self.mount_panels)
        self.score_splitter.splitterMoved.connect(self.remember_score_panel_height)
        self.visibility_button=QToolButton();self.visibility_button.setText(tr('显示'));self.visibility_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup);menu=QMenu(self.visibility_button);self.visibility_actions={}
        for key,label,visible in [('navigator','全局进度',True),('timeline','时间轴',True),('melody','旋律钢琴卷帘',True),('chords','和弦轨',True),('harmony','和弦钢琴卷帘',False),('volume','音量控制',True)]:
            a=menu.addAction(tr(label));a.setCheckable(True);a.setChecked(visible);a.toggled.connect(lambda value,k=key:self.visibility_changed(k));self.visibility_actions[key]=a
        menu.addSeparator()
        menu.addAction(self.chord_lane.velocity_action)
        for label,controls in [('旋律卷帘',self.view_controls),('和弦卷帘',self.harmony_window.view_controls)]:
            sub=menu.addMenu(tr(label));sub.addAction(controls.panel_actions['velocity']);sub.addAction(controls.panel_actions['ruler'])
            if controls is self.harmony_window.view_controls:sub.addAction(self.harmony_window.recognition_action)
            controls.panel_actions['ruler'].toggled.connect(self.update_shared_views)
        self.visibility_button.setMenu(menu);self.compose_menu_actions=list(menu.actions())
        for r in (self.roll,self.harmony_window.roll,self.main_roll):
            r.set_panel('navigator',False);r.set_panel('chords',False)
            r.elementSelection.connect(lambda kind,r=r:self.select_element(kind,r))
            r.notesSelectionChanged.connect(lambda r=r:self.select_element('notes',r) if r.selected_ids else None)
            r.has_chord_clipboard=self.chord_clipboard is not None
            r.chord_clipboard=self.chord_clipboard
            r.deleteMeasuresRequested.connect(self.delete_measures)
            r.loop_range=self.loop_range;r.loopRangeChanged.connect(self.set_loop_range)
            r.navigationRequested.connect(lambda r=r:self.cancel_follow(r))
            r.measureActivated.connect(lambda bar,r=r:self.locate_score_measure(bar,r))
            r.timeViewChanged.connect(lambda r=r:self.sync_time_views(r))
            r.markerPropagationRequested.connect(self.propagate_marker)
            r.chordCommand.connect(lambda command,payload,r=r:self.chord_command(command,payload,r));r.chordSelection.connect(lambda ids,r=r:self.chord_selection(ids,r,getattr(r,'chord_event_lane',None)));r.chordHover.connect(lambda cid,r=r:self.chord_hover(cid,r,getattr(r,'chord_event_lane',None)))
            r.chordAudition.connect(self.audition_chord);r.chordAuditionReleased.connect(lambda:self.transport.end_audition(True));r.chordAuditionHeld.connect(self.hold_chord)
            r.viewChanged.connect(self.update_shared_views)
        self.score_view.canvas.selectionChanged.connect(self.logic_panel.refresh)
        self.score_view.canvas.editorRequested.connect(self.open_score_roll)
        self.score_view.navigationRequested.connect(lambda:self.cancel_follow(self.score_view))
        for roll in (self.roll,self.harmony_window.roll):
            roll.horizontalScrollBar().rangeChanged.connect(self.update_shared_views)
        for control,roll in ((self.tool,self.roll),(self.grid,self.roll),(self.harmony_window.tool,self.harmony_window.roll),(self.harmony_window.grid,self.harmony_window.roll)):
            control.currentIndexChanged.connect(lambda *args,r=roll:self.sync_tools(r))
        self.length.currentIndexChanged.connect(lambda:self.sync_tools(self.roll));self.harmony_window.length.currentIndexChanged.connect(lambda:self.sync_tools(self.harmony_window.roll))
        self.roll.horizontalScrollBar().valueChanged.connect(self.update_shared_views)
        self.score_tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.score_tabs.customContextMenuRequested.connect(self.score_editor_menu)
        for r in (self.roll,self.main_roll,self.harmony_window.roll):
            r.sectionRequested.connect(self.set_section);r.playback_clock=self.transport.position
        self.score_view.canvas.playback_clock=lambda:self.transport.position() if self.transport.playing else self.playhead
        self.workspace_ready=True;self.mount_panels()
        for lane in (self.chord_lane,self.roll.lane,self.harmony_window.roll.lane):lane.aux_ruler_scale=self.chord_ruler_scale
        self.follow_playhead.toggled.connect(lambda value:self.sync_follow(value))
        for _,r,_,controls in self.view_panes():controls.follow.toggled.connect(lambda value,r=r:self.sync_follow(value,r))

    def current_score_panel(self):
        return next((key for key,page in self.score_pages.items() if page is self.score_tabs.currentWidget()),None)

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
        self.set_score_panel_visible(key,True)
        pane=self.score_floats[key]
        if self.score_panel_state[key]['floating']:
            if pane.isMinimized():pane.showNormal()
            pane.raise_();pane.activateWindow()
        else:self.score_tabs.setCurrentWidget(self.score_pages[key])
        if key=='lyrics':self.lyric_panel.open_editor()
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
                        self.score_tabs.insertTab(index,page,tr(self.score_labels[key]))
            if selected and self.score_tabs.indexOf(self.score_pages[selected])>=0:self.score_tabs.setCurrentWidget(self.score_pages[selected])
        finally:self.score_tabs.blockSignals(blocked)
        self.score_tools.setVisible(not compose and self.score_tabs.count()>0)

    def score_editor_menu(self,pos):
        menu=QMenu(self.score_tabs)
        key=self.current_score_panel()
        if key:
            menu.addAction(tr('悬浮当前选项卡'),lambda:self.toggle_score_panel_floating(key))
            menu.addAction(tr('关闭当前选项卡'),lambda:self.set_score_panel_visible(key,False));menu.addSeparator()
        for key,label in self.score_labels.items():menu.addAction(tr(label),lambda k=key:self.show_score_panel(k))
        menu.exec(self.score_tabs.mapToGlobal(pos))

    def mount_panels(self,*args):
        if not getattr(self,'workspace_ready',False) or self.mounting:return
        self.mounting=True
        try:
            compose=self.workspace=='compose';show=lambda key:self.visibility_actions[key].isChecked()
            self.mount_score_tabs(compose);self.update_view_menu()
            for roll in (self.roll,self.main_roll,self.harmony_window.roll):roll.score_mode=not compose
            for widget in (self.melody_window,self.harmony_window,self.chord_lane):
                if not isinstance(widget,FloatingPane) or not widget.isFloating():widget.hide()
            if compose:
                for widget in (self.melody_window,self.chord_lane,self.harmony_window):
                    if not isinstance(widget,FloatingPane) or not widget.isFloating():self.tracks.addWidget(widget)
                for pane in (self.melody_window,self.harmony_window):pane.setVisible(pane.floating_visible if pane.isFloating() else show(pane.key))
                self.chord_lane.setVisible(show('chords'))
                self.navigator.setVisible(show('navigator'));self.timeline.setVisible(show('timeline'));self.score_tools.hide()
                rolls_visible=(show('melody') and not self.melody_window.isFloating()) or (show('harmony') and not self.harmony_window.isFloating())
                self.compose_spacer.setVisible(not rolls_visible);self.compose_layout.setStretch(self.compose_layout.indexOf(self.tracks),1 if rolls_visible else 0)
                self.compose_layout.setAlignment(self.timeline,Qt.AlignmentFlag.AlignTop)
            else:
                if not self.score_tools.isFloating():self.score_splitter.addWidget(self.score_tools)
                self.score_melody_layout.addWidget(self.melody_window);self.score_harmony_layout.addWidget(self.harmony_window)
                self.melody_window.show();self.harmony_window.show();self.score_view.canvas.editing=True
            linked=self.rolls_linked()
            if compose and not self.melody_window.isFloating():self.compose_layout.insertWidget(0,self.melody_toolbar)
            elif not compose and not self.score_panel_state['melody']['floating']:self.score_shared_layout.addWidget(self.melody_toolbar)
            else:self.editor.layout().insertWidget(2,self.melody_toolbar)
            self.melody_toolbar.setVisible(compose or self.score_panel_state['melody']['floating'] or self.current_score_panel() in ('melody','harmony'))
            self.harmony_window.toolbar.setVisible(not linked or not compose and (self.score_panel_state['harmony']['floating'] or self.score_panel_state['melody']['floating']))
            self.harmony_window.header.setVisible(compose and not self.harmony_window.isFloating())
            self.melody_header.setVisible(compose and not self.melody_window.isFloating())
            self.melody_hide.setVisible(compose);self.harmony_window.hide_button.setVisible(compose)
            self.navigator.setVisible(show('navigator'))
            self.shared_scroll.setVisible(compose and (show('timeline') or show('melody') and not self.melody_window.isFloating() or show('harmony') and not self.harmony_window.isFloating() or show('chords')))
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
        if not compose and self.score_panel_state['lyrics']['visible'] and (self.score_panel_state['lyrics']['floating'] or self.current_score_panel()=='lyrics'):self.lyric_panel.open_editor()
        self.sync_grid_views(self.main_roll);self.sync_time_views(self.main_roll);self.sync_tools(self.roll);self.sync_views(self.roll);self.update_shared_views()
        self.sync_follow(self.follow_playhead.isChecked())
        if self.transport.playing:self.follow_views(self.transport.position())
        if not compose:QTimer.singleShot(0,self,self.resize_score)

    def toggle_roll_floating(self,pane):
        if pane.key.startswith('score_'):self.toggle_score_panel_floating(pane.key[6:])
        elif self.workspace=='score':self.toggle_score_panel_floating(pane.key)
        else:pane.setFloating(not pane.isFloating())

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

    def show_roll_in_place(self,pane):
        """Editing/navigation opens an existing float; only View explicitly docks."""
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
            for lane in (self.chord_lane,self.roll.lane,self.harmony_window.roll.lane):lane.highlight_hover=''
        self.mount_panels()

    def nearest_chord_lane(self):
        if self.workspace=='score':return self.harmony_window.roll.lane
        if self.melody_window.isFloating():return self.roll.lane if self.floating_melody_chords else None
        if self.visibility_actions['chords'].isChecked():return self.chord_lane
        if self.visibility_actions['harmony'].isChecked() and not self.harmony_window.isFloating():return self.harmony_window.roll.lane
        return None

    def update_chord_highlight(self):
        lane=self.nearest_chord_lane();valid={c.id for c in self.project.chords}
        highlights=(lane.highlight_ids|({lane.highlight_hover} if lane.highlight_hover else set()))&valid if lane else set()
        if getattr(self.roll,'chord_highlights',None)!=highlights:
            self.roll.chord_highlights=highlights;self.roll.refresh()

    def set_timeline_sync(self,enabled,source):
        if not getattr(self,'workspace_ready',False):return
        check=self.melody_sync if source is self.roll else self.harmony_window.sync
        check.blockSignals(True);check.setChecked(enabled);check.blockSignals(False)
        if enabled:
            for _,r,_,controls in self.view_panes():
                if r is source:
                    blocked=controls.follow.blockSignals(True);controls.follow.setChecked(self.follow_playhead.isChecked());controls.follow.blockSignals(blocked)
            self.sync_time_views(self.main_roll)

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
        return ((self.melody_window,self.roll,self.melody_sync,self.melody_transport),(self.harmony_window,self.harmony_window.roll,self.harmony_window.sync,self.harmony_window.transport_controls))

    def roll_pane(self,roll):
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
        elif source in (self.roll,self.harmony_window.roll):
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
        if not main and not any(r is source and sync.isChecked() for _,r,sync,_ in self.view_panes()):return
        self.syncing_time=True
        try:
            targets=[self.main_roll]+[r for pane,r,sync,_ in self.view_panes() if self.is_main_view(r) or sync.isChecked()]
            zoom=source.zoom;scroll=source.horizontalScrollBar().value()
            for target in targets:
                if target is source:continue
                bar=target.horizontalScrollBar();blocked=bar.blockSignals(True)
                try:target.zoom=zoom;target.update_ranges();bar.setValue(scroll)
                finally:bar.blockSignals(blocked)
                target.refresh()
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
                    control=self.grid if target is self.roll else self.harmony_window.grid
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
        if primary is not self.main_roll:
            self.main_roll.panels['ruler']=primary.panels['ruler']
        self.timeline.setFixedHeight(primary.bar_ruler_height+RULER_TIME_H)
        for widget in (self.timeline,self.navigator,self.chord_lane,self.harmony_window.top_lane):widget.update()
        for lane in (self.chord_lane,self.roll.lane,self.harmony_window.top_lane):lane.velocity_lane.update()
        self.update_chord_highlight()

    def rolls_linked(self):
        return getattr(self,'workspace_ready',False) and all(self.is_main_view(r) for _,r,_,_ in self.view_panes())

    def docked_roll(self):
        if self.workspace=='score':
            key=self.current_score_panel()
            if key in ('melody','harmony'):
                roll=self.roll if key=='melody' else self.harmony_window.roll
                if self.is_main_view(roll):return roll
            return self.main_roll
        for pane,roll,_,_ in self.view_panes():
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
        if source is self.roll and self.melody_window.isFloating():return source.lane
        return self.chord_lane

    def chord_selection(self,ids,source=None,lane=None):
        if not getattr(self,'workspace_ready',False) or self.harmony_window is None:return
        ids=set(ids)
        session=getattr(self,'chord_move_session',None)
        if session and ids!=session.ids:self.clear_chord_move_session()
        if ids:self.select_element('chords',source)
        lane=lane or self.chord_source_lane(source);lane.highlight_ids=ids.copy()
        anchor=next(iter(ids)) if len(ids)==1 else self.roll.chord_anchor or self.harmony_window.roll.chord_anchor
        views=self.chord_selection_views(source)
        for r in views:r.chord_anchor=anchor;r.selected_chords=ids.copy();r.selected_chord=next(iter(ids)) if len(ids)==1 else '';r.refresh()
        if self.harmony_window.roll in views:self.harmony_window.select_chord(next(iter(ids)) if len(ids)==1 else '',False)
        self.update_shared_views()

    def select_element(self,kind,source=None):
        if not getattr(self,'workspace_ready',False) or getattr(self,'selecting_elements',False):return
        self.selecting_elements=True
        try:
            if kind!='chords':self.clear_chord_move_session()
            for r in (self.roll,self.harmony_window.roll,self.main_roll):
                if kind=='chords':r.selected_ids.clear();r.selected_note=''
                else:r.selected_chords.clear();r.selected_chord='';r.hovered_chord=''
                r.refresh()
            if kind=='notes':
                for lane in (self.chord_lane,self.roll.lane,self.harmony_window.roll.lane):lane.highlight_ids.clear();lane.highlight_hover='';lane.update()
            if source:source.edit_target=kind
            self.update_chord_highlight()
        finally:self.selecting_elements=False

    def chord_hover(self,cid,source=None,lane=None):
        if not getattr(self,'workspace_ready',False) or self.harmony_window is None:return
        lane=lane or self.chord_source_lane(source);lane.highlight_hover=cid
        for r in self.chord_selection_views(source):r.hovered_chord=cid;r.refresh()
        self.update_shared_views()

    def chord_command(self,command,payload,source=None):
        from .chordops import blank_chord,change_chords,split_chords,merge_chords,move_chords,ChordClipboard
        source=source or self.active_roll()
        if command=='progression':self.apply_progression(payload,source);return
        if command=='capture_progression':self.capture_progression(payload);return
        if command=='search_progressions':self.search_progressions(payload,source);return
        if command=='split_at':
            from .chordops import split_at_position
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
        elif command=='copy':
            self.chord_clipboard=ChordClipboard.capture([c for c in self.project.chords if c.id in payload],self.project);self.clipboard_kind='chords'
            for r in (self.roll,self.harmony_window.roll,self.main_roll):r.has_chord_clipboard=self.chord_clipboard is not None;r.chord_clipboard=self.chord_clipboard
            self.status_message(tr('已复制 {0} 个和弦；粘贴时按时间顺序相邻排列。',len(payload)))
        elif command in ('paste','split','merge'):
            if command=='paste' and not self.chord_clipboard:return
            if command=='paste' and not self.chord_clipboard.can_paste(self.project,payload):self.status_message(tr('粘贴范围必须完整位于匹配的拍号区间内。'));return
            result=set()
            def edit(p):
                result.update(self.chord_clipboard.paste(p,payload) if command=='paste' else (split_chords if command=='split' else merge_chords)(p,set(payload)))
            if self.mutate(tr('已更新所选和弦'),edit,source=source):self.chord_selection(result,source)
        elif command.startswith('velocity:'):
            value=max(1,min(127,int(command.split(':')[1])))
            def velocity(p):
                for chord in p.chords:
                    if chord.id in payload:
                        chord.velocity=value
                        if chord.notes is not None:
                            for note in chord.notes:note.velocity=value
            self.mutate(tr('已更新和弦力度'),velocity,source=source)
        elif command=='audition':
            if payload:
                self.transport.begin_chords_audition([c for c in self.project.chords if c.id in payload],self.project.bpm)
                self.transport.end_audition(True)
        else:
            if self.mutate(tr('已更新所选和弦'),lambda p:change_chords(p,set(payload),command),source=source) and len(payload)==1 and command!='delete':
                self.audition_chord(next(iter(payload)));self.transport.end_audition(True)

    def clear_chord_move_session(self):
        self.chord_move_session=None
        if not getattr(self,'workspace_ready',False):return
        existing={c.id for c in self.project.chords}
        for r in (self.roll,self.harmony_window.roll,self.main_roll):
            r.transient_chord_ids=set();r.selected_chords.intersection_update(existing)
            if r.selected_chord not in existing:r.selected_chord=''

    def chord_selection_extents(self,roll):
        session=getattr(self,'chord_move_session',None)
        if session and session.ids==roll.selected_chords:return session.extents()
        return [c for c in self.project.chords if c.id in roll.selected_chords]

    def move_chord_selection(self,source,ids,delta,drop=None):
        from .chordops import ChordMoveSession
        from .meter import region_at
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
        if role=='lyrics':self.seek(self.roll.snap_time(tick));self.batch_lyrics();return
        if role=='chords':
            chord=self.project.chord_at(tick);self.open_harmony(chord.id if chord else '',tick);return
        self.show_score_panel('harmony' if role=='chords' else 'melody')
        roll=self.harmony_window.roll if role=='chords' else self.roll;roll.ensure_tick(tick)
        roll.setFocus()

    def enable_native_frame(self):
        if __import__('sys').platform!='win32' or QApplication.platformName()!='windows':return
        import ctypes
        from ctypes import wintypes
        user=ctypes.windll.user32;hwnd=wintypes.HWND(int(self.winId()))
        user.GetWindowLongW.argtypes=[wintypes.HWND,ctypes.c_int]
        user.SetWindowLongW.argtypes=[wintypes.HWND,ctypes.c_int,wintypes.LONG]
        # WS_THICKFRAME + WS_CAPTION retain Windows Snap and standard sizing.
        # WM_NCCALCSIZE below keeps their non-client decoration out of the UI.
        self._native_frame=True
        user.SetWindowLongW(hwnd,-16,user.GetWindowLongW(hwnd,-16)|0x00040000|0x00C00000)
        user.SetWindowPos(hwnd,None,0,0,0,0,0x0027)

    def resize_hit(self,point):
        """Only the outer frame resizes. Child controls always receive their clicks."""
        x,y=point.x(),point.y();edge=3
        if self.isMaximized() or not 0<=x<self.width() or not 0<=y<self.height():return 0
        child=self.childAt(point)
        while child and child is not self:
            if isinstance(child,(QAbstractButton,QMenuBar,QScrollBar,ChordLane)):return 0
            child=child.parentWidget()
        left,right,top,bottom=x<edge,x>=self.width()-edge,y<edge,y>=self.height()-edge
        return 13 if top and left else 14 if top and right else 16 if bottom and left else 17 if bottom and right else 10 if left else 11 if right else 12 if top else 15 if bottom else 0

    def nativeEvent(self,eventType,message):
        # Keep Windows edge resizing and Win+Left/Right tiling with a single title row.
        if __import__('sys').platform=='win32':
            import ctypes
            from ctypes import wintypes
            msg=wintypes.MSG.from_address(int(message))
            if msg.message==0x0083 and msg.wParam and getattr(self,'_native_frame',False):return True,0
            if msg.message==0x0084 and getattr(self,'_native_frame',False):
                # WM_NCHITTEST carries physical pixels; Qt widgets use DIPs.
                pos=wintypes.POINT(ctypes.c_short(msg.lParam&0xffff).value,ctypes.c_short((msg.lParam>>16)&0xffff).value)
                ctypes.windll.user32.ScreenToClient(wintypes.HWND(int(self.winId())),ctypes.byref(pos));ratio=self.devicePixelRatioF()
                point=QPoint(round(pos.x/ratio),round(pos.y/ratio))
                return True,self.resize_hit(point) or 1  # HTCLIENT, never the native caption.
        return super().nativeEvent(eventType,message)

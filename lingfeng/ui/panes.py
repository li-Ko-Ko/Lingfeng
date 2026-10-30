"""Reusable pane chrome and transport controls, independent of workspace wiring."""
from PySide6.QtCore import Qt, Signal, QEvent
from PySide6.QtGui import QFont, QAction
from PySide6.QtWidgets import (QWidget, QFrame, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QToolButton, QMenu, QSizePolicy, QCheckBox, QSlider)

from lingfeng.platform.i18n import tr
from lingfeng.ui.controls import SizeControl, IconButton


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
            from lingfeng.ui.windowing import enable_frame
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
        from lingfeng.ui.windowing import native_frame_event
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

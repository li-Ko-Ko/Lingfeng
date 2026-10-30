from .i18n import tr
"""Compact shared editing controls for the main and floating piano rolls."""
from PySide6.QtCore import Signal,Qt,QTimer,QPointF,QRectF
from PySide6.QtWidgets import QWidget,QHBoxLayout,QLabel,QComboBox,QToolButton,QMenu,QSpinBox,QDoubleSpinBox,QAbstractSpinBox
from PySide6.QtGui import QActionGroup,QPainter,QPen,QPolygonF
from PySide6.QtWidgets import QApplication
from .theme import color,is_dark


class IconButton(QToolButton):
    activated=Signal()
    doubleActivated=Signal()
    def __init__(self,kind,parent=None):
        super().__init__(parent);self.kind=kind;self.suppress_release=False
        self.setFixedSize(38,34);self.setText('');self.setIconSize(self.size())
        self.click_timer=QTimer(self);self.click_timer.setSingleShot(True)
        self.clicked.connect(self.dispatch);self.set_kind(kind)
    def set_kind(self,kind):
        self.kind=kind;label={'play':tr('播放（空格）'),'pause':tr('暂停（空格）'),'replay':tr('回放：返回播放起点并保持播放或暂停；双击返回曲首'),'options':tr('编辑器选项'),'float':tr('悬浮卷帘'),'dock':tr('停靠卷帘'),'minimize':tr('最小化'),'maximize':tr('最大化'),'restore':tr('还原'),'close':tr('关闭')}[kind]
        self.setToolTip(label);self.setAccessibleName(label);self.update()
    def dispatch(self):
        if self.suppress_release:self.suppress_release=False;return
        if self.kind!='replay':self.activated.emit();return
        if self.click_timer.isActive():self.click_timer.stop();self.doubleActivated.emit()
        else:self.click_timer.start(QApplication.doubleClickInterval());self.activated.emit()
    def mouseDoubleClickEvent(self,event):
        if self.kind=='replay' and event.button()==Qt.MouseButton.LeftButton:
            self.click_timer.stop();self.suppress_release=True;self.setDown(True);self.doubleActivated.emit();event.accept()
        else:super().mouseDoubleClickEvent(event)
    def paintEvent(self,event):
        super().paintEvent(event);p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        ink=color('#FFFFFF',False) if self.objectName()=='play' else color('#34465E')
        p.setPen(QPen(ink,1.8,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap,Qt.PenJoinStyle.RoundJoin));p.setBrush(ink)
        x,y=self.width()/2,self.height()/2
        if self.kind=='play':p.drawPolygon(QPolygonF([QPointF(x-4,y-7),QPointF(x+7,y),QPointF(x-4,y+7)]))
        elif self.kind=='pause':p.drawRoundedRect(QRectF(x-6,y-7,3,14),1,1);p.drawRoundedRect(QRectF(x+3,y-7,3,14),1,1)
        elif self.kind=='replay':
            p.drawRoundedRect(QRectF(x-8,y-7,2,14),.7,.7)
            p.drawPolygon(QPolygonF([QPointF(x+7,y-7),QPointF(x-3,y),QPointF(x+7,y+7)]))
        elif self.kind in ('float','dock'):
            p.setBrush(Qt.BrushStyle.NoBrush);p.drawRoundedRect(QRectF(x-8,y-7,14,14),1.5,1.5)
            if self.kind=='float':
                p.drawLine(QPointF(x-2,y+2),QPointF(x+9,y-9));p.drawLine(QPointF(x+3,y-9),QPointF(x+9,y-9));p.drawLine(QPointF(x+9,y-9),QPointF(x+9,y-3))
            else:
                p.drawLine(QPointF(x+9,y-9),QPointF(x-1,y+1));p.drawLine(QPointF(x-1,y-5),QPointF(x-1,y+1));p.drawLine(QPointF(x-1,y+1),QPointF(x+5,y+1))
        elif self.kind in ('minimize','maximize','restore','close'):
            p.setBrush(Qt.BrushStyle.NoBrush)
            if self.kind=='minimize':p.drawLine(QPointF(x-6,y),QPointF(x+6,y))
            elif self.kind=='maximize':p.drawRoundedRect(QRectF(x-6,y-6,12,12),1,1)
            elif self.kind=='restore':
                p.drawPolyline(QPolygonF([QPointF(x-3,y-5),QPointF(x-3,y-8),QPointF(x+8,y-8),QPointF(x+8,y+3),QPointF(x+5,y+3)]))
                p.drawRoundedRect(QRectF(x-7,y-4,11,11),1,1)
            else:
                p.drawLine(QPointF(x-5,y-5),QPointF(x+5,y+5));p.drawLine(QPointF(x-5,y+5),QPointF(x+5,y-5))
        else:
            for dy in (-6,0,6):p.drawEllipse(QPointF(x,y+dy),1.4,1.4)


class GridSelector(QToolButton):
    currentIndexChanged=Signal(int)
    VALUES=[3840,1920,960,480,240,120,60,30,30720,15360,7680,3840]
    LABELS=['1/1','1/2','1/4','1/8','1/16','1/32','1/64','1/128']
    def __init__(self,parent=None,duration=False):
        super().__init__(parent);self.index=13 if duration else 4;self.triplet=False;self.is_duration=duration
        self.labels=self.LABELS+[tr('8 小节'),tr('4 小节'),tr('2 小节'),tr('1 小节')]
        self.values=list(self.VALUES)
        if duration:self.labels += [tr('跟随网格'),tr('上一次时值')];self.values += [0,-1]
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QMenu(self);group=QActionGroup(self);group.setExclusive(True);self.actions=[None]*len(self.labels)
        order=([12,13] if duration else [])+[8,9,10,11]+list(range(8))
        for i in order:
            label=self.labels[i]
            action=menu.addAction(label);action.setCheckable(True);group.addAction(action)
            action.triggered.connect(lambda checked=False,index=i:self.setCurrentIndex(index));self.actions[i]=action
            if i in (13,11):menu.addSeparator()
        menu.addSeparator();self.dotted_action=menu.addAction(tr('附点'));self.dotted_action.setCheckable(True);self.dotted_action.setVisible(duration)
        self.dotted_action.toggled.connect(self.set_dotted)
        self.triplet_action=menu.addAction(tr('三连音'));self.triplet_action.setCheckable(True);self.triplet_action.toggled.connect(self.set_triplet)
        self.setMenu(menu);self.update_label();self.setToolTip(tr('音符时值：附点与三连音互斥，可跟随网格或使用上一次时值。') if duration else tr('吸附网格：同时控制卷帘纵线和时间轴的最小单位。'))
    @property
    def bars(self):return {8:8,9:4,10:2,11:1}.get(self.index,0)
    def currentData(self):
        value=self.values[self.index]
        return value*2//3 if self.triplet and value>0 else value*3//2 if self.dotted_action.isChecked() and value>0 else value
    def currentIndex(self):return self.index
    def setCurrentIndex(self,index):
        if not 0<=index<len(self.values):return
        self.index=index
        if self.bars or self.values[index]<=0:
            self.triplet=False;self.triplet_action.blockSignals(True);self.triplet_action.setChecked(False);self.triplet_action.blockSignals(False)
            self.dotted_action.blockSignals(True);self.dotted_action.setChecked(False);self.dotted_action.blockSignals(False)
        self.update_label();self.currentIndexChanged.emit(index)
    def findData(self,value):return next((i for i,v in enumerate(self.values) if v==value),-1)
    def set_triplet(self,enabled):
        self.triplet=bool(enabled) and not self.bars and self.values[self.index]>0
        self.triplet_action.blockSignals(True);self.triplet_action.setChecked(self.triplet);self.triplet_action.blockSignals(False)
        if self.triplet:self.dotted_action.blockSignals(True);self.dotted_action.setChecked(False);self.dotted_action.blockSignals(False)
        self.update_label();self.currentIndexChanged.emit(self.index)
    def set_dotted(self,enabled):
        if enabled:self.triplet=False;self.triplet_action.blockSignals(True);self.triplet_action.setChecked(False);self.triplet_action.blockSignals(False)
        self.update_label();self.currentIndexChanged.emit(self.index)
    def update_label(self):
        suffix=' · 3' if self.triplet else ' · .' if self.dotted_action.isChecked() else ''
        self.setText(self.labels[self.index]+suffix)
        for i,action in enumerate(self.actions):action.setChecked(i==self.index)
        enabled=not self.bars and self.values[self.index]>0;self.triplet_action.setEnabled(enabled);self.dotted_action.setEnabled(enabled)


class DurationSelector(GridSelector):
    def __init__(self,parent=None):super().__init__(parent,duration=True)


class SizeControl(QSpinBox):
    """A pixel control with explicit +/- buttons and the old selector interface."""
    currentIndexChanged=Signal(int)
    def __init__(self,value=22,minimum=10,maximum=80,parent=None):
        super().__init__(parent);self.setRange(minimum,maximum);self.setValue(value);self.setSuffix(' px');self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus);self.setFixedWidth(90)
        self.valueChanged.connect(self.currentIndexChanged)
    def currentData(self):return self.value()
    def findData(self,value):return value
    def setCurrentIndex(self,value):self.setValue(value)
    def paintEvent(self,event):
        super().paintEvent(event)
        # QSS can suppress the platform's PlusMinus glyphs. Draw explicit signs.
        p=QPainter(self);p.setPen(QPen(color('#66768B'),1.2));x=self.width()-8
        for y in (self.height()*.27,self.height()*.73):p.drawLine(QPointF(x-3,y),QPointF(x+3,y))
        y=self.height()*.27;p.drawLine(QPointF(x,y-3),QPointF(x,y+3))


class FontSizeControl(QDoubleSpinBox):
    """Usually integral sizes, with an honest sub-unit limit for dense scores."""
    currentIndexChanged=Signal(float)
    def __init__(self,parent=None):
        super().__init__(parent);self.setDecimals(4);self.setRange(.0001,26);self.setValue(15)
        self.setSingleStep(1);self.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus);self.setFixedWidth(90)
        self.valueChanged.connect(self.currentIndexChanged)
    def currentData(self):return self.value()
    def textFromValue(self,value):return f'{value:g}'
    def paintEvent(self,event):
        super().paintEvent(event)
        p=QPainter(self);p.setPen(QPen(color('#66768B'),1.2));x=self.width()-8
        for y in (self.height()*.27,self.height()*.73):p.drawLine(QPointF(x-3,y),QPointF(x+3,y))
        y=self.height()*.27;p.drawLine(QPointF(x,y-3),QPointF(x,y+3))


class RollViewControls(QWidget):
    def __init__(self,roll,parent=None):
        super().__init__(parent);self.roll=roll
        layout=QHBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(8)
        self.range=QComboBox();self.range.addItems([tr('全部 88 键'),tr('已用音高')]);self.range.currentIndexChanged.connect(lambda i:roll.set_compact(i==1));layout.addWidget(self.range)
        layout.addWidget(QLabel(tr('键高')));self.height=SizeControl(roll.row_height)
        self.height.currentIndexChanged.connect(roll.set_row_height);layout.addWidget(self.height)
        self.options=IconButton('options');self.options.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.menu=QMenu(self.options);self.visibility_menu=QMenu(tr('显示与隐藏'),self.menu);self.visibility_action=self.menu.addMenu(self.visibility_menu);menu=self.visibility_menu;self.panel_actions={}
        for key,label in [('velocity',tr('力度窗格')),('chords',tr('和弦轨')),('ruler',tr('标尺详细信息')),('navigator',tr('导航器'))]:
            action=menu.addAction(label);action.setCheckable(True);action.setChecked(roll.panels[key]);self.panel_actions[key]=action
            action.toggled.connect(lambda value,k=key:roll.set_panel(k,value))
        self.options.setMenu(self.menu)
        for label,delta in [('−',-12),('+',12)]:
            btn=QToolButton();btn.setText(label);btn.setToolTip(tr('以卷帘可视区中央为中心缩放时间轴'));btn.clicked.connect(lambda checked=False,d=delta:self.zoom(d));layout.addWidget(btn)
    def zoom(self,delta):
        self.roll.zoom_at(1.2**(delta/12));self.roll.navigationRequested.emit()

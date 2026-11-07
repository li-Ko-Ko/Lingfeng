"""Shared tab outline for the composition and score editors."""
from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QTabBar, QTabWidget

from lingfeng.ui.theme import (
    PANEL_BORDERS, PANEL_HOVER, PANEL_MUTED, PANEL_RAISED, PANEL_SURFACES, PANEL_TEXT, is_dark,
)


class WorkspaceTabBar(QTabBar):
    shoulder=10

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setExpanding(False)
        self.setDrawBase(False)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.setMouseTracking(True)

    def tabSizeHint(self,index):
        trailing=self.shoulder if index==self.count()-1 else 0
        return QSize(self.fontMetrics().horizontalAdvance(self.tabText(index))+28+trailing,34)

    def paint_rail_outside(self,painter,width):
        """Continue the rail beyond the tab bar in its parent widget."""
        rect=self.geometry()
        painter.setPen(QPen(QColor(PANEL_BORDERS[is_dark()])))
        if rect.left()>0:painter.drawLine(0,rect.bottom(),rect.left()-1,rect.bottom())
        painter.drawLine(rect.right()+1,rect.bottom(),width-1,rect.bottom())

    def paintEvent(self,event):
        dark=is_dark()
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        outline=QPen(QColor(PANEL_BORDERS[dark]))
        active=self.currentIndex()
        hovered=self.tabAt(self.mapFromGlobal(QCursor.pos())) if self.underMouse() else -1
        visible=[index for index in range(self.count()) if self.isTabVisible(index)]
        for index in visible:
            if index!=active:
                fill=PANEL_HOVER[dark] if index==hovered else PANEL_SURFACES[dark]
                self.draw_tab(painter,index,fill,PANEL_MUTED[dark],outline,False)

        # The selected tab's open bottom and shoulders cover the rail and its neighbors.
        painter.setPen(outline)
        painter.drawLine(QPointF(0,self.height()-.5),QPointF(self.width(),self.height()-.5))
        if active in visible:
            self.draw_tab(painter,active,PANEL_RAISED[dark],PANEL_TEXT[dark],outline,True)

    def draw_tab(self,painter,index,fill,text,outline,selected):
        rect=self.tabRect(index)
        left=max(.5,rect.left()+.5-(2 if selected else 0))
        if index==self.count()-1:
            rect.adjust(0,0,-self.shoulder,0)
        right=min(self.width()-.5,rect.right()+.5+(2 if selected else 0))
        if right<=left:return
        top=rect.top()+.5
        bottom=self.height()+.5 if selected else self.height()-.5
        radius=min(5,(right-left)/2)
        left_flare=min(self.shoulder,left-.5) if selected else 0
        right_flare=min(self.shoulder,self.width()-.5-right) if selected else 0
        path=QPainterPath(QPointF(left-left_flare,bottom))
        path.quadTo(left,bottom,left,bottom-left_flare)
        path.lineTo(left,top+radius)
        path.quadTo(left,top,left+radius,top)
        path.lineTo(right-radius,top)
        path.quadTo(right,top,right,top+radius)
        path.lineTo(right,bottom-right_flare)
        path.quadTo(right,bottom,right+right_flare,bottom)
        painter.fillPath(path,QColor(fill))
        painter.setPen(outline)
        painter.drawPath(path)
        painter.setPen(QColor(text))
        label=rect.adjusted(12,0,-12,0)
        caption=painter.fontMetrics().elidedText(self.tabText(index),self.elideMode(),label.width())
        painter.drawText(label,Qt.AlignmentFlag.AlignCenter,caption)

    def mouseMoveEvent(self,event):
        super().mouseMoveEvent(event)
        self.update()

    def leaveEvent(self,event):
        super().leaveEvent(event)
        self.update()


class WorkspaceScoreTabs(QTabWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setObjectName('workspaceScoreTabs')
        self.setTabBar(WorkspaceTabBar(self))
        self.currentChanged.connect(lambda _:self.update())

    def paintEvent(self,event):
        super().paintEvent(event)
        if self.count():
            painter=QPainter(self)
            self.tabBar().paint_rail_outside(painter,self.width())

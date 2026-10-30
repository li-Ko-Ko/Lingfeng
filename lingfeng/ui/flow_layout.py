"""Wrapping toolbars that remain usable in a Windows half-screen window."""
from PySide6.QtCore import Qt,QRect,QSize
from PySide6.QtWidgets import QLayout,QWidget,QWidgetItem,QSpacerItem,QSizePolicy


class FlowLayout(QLayout):
    def __init__(self,parent=None):
        super().__init__(parent);self.items=[];self.setSpacing(7)
    def addItem(self,item):self.items.append(item)
    def addLayout(self,layout):
        wrapper=QWidget();wrapper.setLayout(layout);self.addWidget(wrapper)
    def addStretch(self,stretch=1):self.addItem(QSpacerItem(0,0,QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Minimum))
    def addSpacing(self,size):self.addItem(QSpacerItem(size,0,QSizePolicy.Policy.Fixed,QSizePolicy.Policy.Minimum))
    def count(self):return len(self.items)
    def itemAt(self,index):return self.items[index] if 0<=index<len(self.items) else None
    def takeAt(self,index):return self.items.pop(index) if 0<=index<len(self.items) else None
    def expandingDirections(self):return Qt.Orientation.Horizontal
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):return self.arrange(QRect(0,0,width,0),True)
    def sizeHint(self):return self.minimumSize()
    def minimumSize(self):
        size=QSize()
        for item in self.items:
            if item.widget() and item.widget().isHidden():continue
            size=size.expandedTo(item.minimumSize())
        margins=self.contentsMargins();width=size.width()+margins.left()+margins.right()
        current=self.geometry().width() or (self.parentWidget().width() if self.parentWidget() else width)
        return QSize(width,self.arrange(QRect(0,0,max(width,current),0),True))
    def setGeometry(self,rect):
        super().setGeometry(rect);height=self.arrange(rect,False)
        if height!=getattr(self,'last_height',None):
            self.last_height=height
            if self.parentWidget():self.parentWidget().updateGeometry()
    def arrange(self,rect,test):
        m=self.contentsMargins();left=rect.x()+m.left();width=max(1,rect.width()-m.left()-m.right());y=rect.y()+m.top();spacing=self.spacing()
        rows=[];current=[];used=0
        for item in self.items:
            widget=item.widget()
            if widget and widget.isHidden():continue
            hint=item.sizeHint();w=min(width,max(item.minimumSize().width(),hint.width()))
            if widget and widget.sizePolicy().horizontalPolicy()==QSizePolicy.Policy.Ignored:w=min(width,120)
            if current and used+spacing+w>width:
                rows.append(current);current=[];used=0
            current.append((item,w));used+=w+(spacing if len(current)>1 else 0)
        if current:rows.append(current)
        for entries in rows:
            spare=max(0,width-sum(w for _,w in entries)-spacing*(len(entries)-1))
            stretch=[item for item,w in entries if item.spacerItem() and item.expandingDirections()&Qt.Orientation.Horizontal]
            x=left;prepared=[]
            for item,w in entries:
                if item in stretch:w+=spare//len(stretch)
                h=max(item.minimumSize().height(),item.heightForWidth(w) if item.hasHeightForWidth() else item.sizeHint().height());prepared.append((item,x,w,h))
                x+=w+spacing
            height=max((h for _,_,_,h in prepared),default=0)
            if not test:
                for item,x,w,h in prepared:item.setGeometry(QRect(x,y+(height-h)//2,w,h))
            y+=height+spacing
        return max(0,y-rect.y()-spacing+m.bottom())

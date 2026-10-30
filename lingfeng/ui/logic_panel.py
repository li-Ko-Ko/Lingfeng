"""Interactive drafts for display-only score structure."""
import copy
from lingfeng.music.model import uid
from lingfeng.platform.i18n import tr
from lingfeng.engraving.structure import KINDS, region_count, draft_candidate, apply_draft

from lingfeng.ui.flow_layout import FlowLayout

from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QComboBox,QPushButton,QListWidget,QListWidgetItem

from PySide6.QtCore import Qt

class LogicPanel(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.drafts=[];self.active=None;self.refreshing=False
        self.setObjectName('scoreLogic');self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground,True)
        layout=QVBoxLayout(self);layout.setContentsMargins(10,6,10,6);layout.setSpacing(6)
        intro=QLabel(tr('先创建符号，再在谱面框选小节或拍并记录区域。可建立多个独立结构；检查通过后应用。'));intro.setWordWrap(True);layout.addWidget(intro)
        row=FlowLayout();self.kind=QComboBox()
        for code,label in KINDS:self.kind.addItem(tr(label),code)
        row.addWidget(self.kind);create=QPushButton(tr('创建符号'));create.clicked.connect(self.create_draft);row.addWidget(create);layout.addLayout(row)
        self.items=QListWidget();self.items.setMaximumHeight(108);self.items.currentItemChanged.connect(self.select_item);layout.addWidget(self.items)
        row=FlowLayout();self.buttons=[];self.labels=[]
        for index,key in enumerate(('A','B','A′','C')):
            button=QPushButton(tr('记录区域 {0}',key));button.clicked.connect(lambda checked=False,i=index:self.capture(i));row.addWidget(button);self.buttons.append(button)
            label=QLabel();row.addWidget(label);self.labels.append(label)
        layout.addLayout(row);self.feedback=QLabel();self.feedback.setWordWrap(True);layout.addWidget(self.feedback)
        row=FlowLayout();self.apply=QPushButton(tr('检查并应用'));self.apply.clicked.connect(self.commit);row.addWidget(self.apply)
        self.remove_button=QPushButton(tr('删除选中符号'));self.remove_button.clicked.connect(self.remove);row.addWidget(self.remove_button);layout.addLayout(row);layout.addStretch();self.refresh()

    def export_state(self):return copy.deepcopy(dict(drafts=self.drafts,active=self.active))
    def restore_state(self,state):self.drafts=copy.deepcopy(state.get('drafts',[]));self.active=state.get('active');self.refresh()
    def reset(self):self.drafts=[];self.active=None;self.refresh()
    def current(self):return next((d for d in self.drafts if self.active==('draft',d['id'])),None)

    def create_draft(self):
        kind=self.kind.currentData();draft=dict(id=uid(),kind=kind,regions=[None]*region_count(kind));self.drafts.append(draft);self.active=('draft',draft['id']);self.refresh()

    def select_item(self,item,previous=None):
        if self.refreshing:return
        self.active=tuple(item.data(Qt.ItemDataRole.UserRole)) if item else None;self.show_details()

    def capture(self,index):
        draft=self.current()
        if not draft or index>=len(draft['regions']):return
        canvas=self.owner.score_view.canvas
        draft['regions'][index]=dict(bars=sorted(canvas.selected_bars) if canvas.selection_unit=='measure' else [],ranges=copy.deepcopy(canvas.selection_ranges()))
        self.refresh()

    def refresh(self):
        self.refreshing=True;self.items.clear();names=dict(KINDS);p=self.owner.project
        def entry(label,key):
            item=QListWidgetItem(label);item.setData(Qt.ItemDataRole.UserRole,key);self.items.addItem(item)
            if key==self.active:self.items.setCurrentItem(item)
        for d in self.drafts:entry(tr('待配置 · {0}',tr(names[d['kind']])),('draft',d['id']))
        from lingfeng.engraving.presentation import active_compressions
        valid=active_compressions(p)
        for i,item in enumerate(p.notation.get('compressions',[])):
            name=tr(names['jump_coda' if item['kind']=='coda' else item['kind']]);text=tr('{0} · 第 {1}–{2} 小节',name,item['start']+1,item['end'])
            if item not in valid:text+=' · '+tr('音乐已变更，压缩暂停')
            entry(text,('compressions',i))
        for i,item in enumerate(p.notation.get('symbols',[])):entry(tr('{0} · 第 {1} 小节',tr(names[item['kind']]),p.measure_at(item['start'])+1),('symbols',i))
        self.refreshing=False;self.show_details()

    def show_details(self):
        draft=self.current();count=region_count(draft['kind']) if draft else 0
        for index,(button,label) in enumerate(zip(self.buttons,self.labels)):
            button.setVisible(index<count);label.setVisible(index<count)
            region=draft['regions'][index] if draft and index<count else None
            text=tr('未选择')
            if region:
                bars=region['bars'];ranges=region['ranges']
                if bars:text=tr('第 {0}–{1} 小节',min(bars)+1,max(bars)+1)
                elif ranges:text=tr('{0} 个拍选区',len(ranges))
            label.setText(text)
        candidate,reason=draft_candidate(self.owner.project,draft) if draft else (None,tr('选择符号类型并点击“创建符号”。已应用的符号也可在谱面右键删除。'))
        self.apply.setEnabled(candidate is not None);self.feedback.setText(reason);self.remove_button.setEnabled(self.active is not None)

    def commit(self):
        draft=self.current()
        if not draft:return
        candidate,_=draft_candidate(self.owner.project,draft)
        if candidate is None:return
        result=[]
        if self.owner.mutate(tr('已应用谱面符号；播放与 MIDI 保持不变'),lambda p:result.append(apply_draft(p,draft))):
            self.drafts=[d for d in self.drafts if d['id']!=draft['id']];self.active=result[0];self.refresh()

    def remove(self):
        if not self.active:return
        collection,key=self.active
        if collection=='draft':self.drafts=[d for d in self.drafts if d['id']!=key]
        elif collection in ('symbols','compressions') and 0<=key<len(self.owner.project.notation.get(collection,[])):
            self.owner.score_command('remove_structure',dict(bars=[],ranges=[],key=(collection,key)))
        self.active=None;self.refresh()

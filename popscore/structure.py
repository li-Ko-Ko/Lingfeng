"""Symbol-first score structure drafts; performed music is never rewritten."""
import copy
from .model import uid
from .presentation import contiguous,pair_candidate,same_segment,annotation_allowed,add_annotation
from .i18n import tr
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QComboBox,QPushButton,QListWidget,QListWidgetItem
from .layout import FlowLayout

KINDS=[('repeat','反复记号'),('dc','D.C. al Fine'),('ds','D.S. al Fine'),('dc_nr','D.C. N/R al Fine'),('ds_nr','D.S. N/R al Fine'),('jump_coda','尾声跳转（A–B–A′–C）'),('barline','小节线'),('double_bar','双小节线'),('final_bar','结束线'),('segno','Segno（反复起点）'),('coda','Coda（尾声）'),('fine','Fine（结束）'),('fade','F.O.（渐弱结束）'),('rit','rit.（渐慢）'),('adlib','ad lib.（自由演奏）')]
REPEATS={'repeat','dc','ds','dc_nr','ds_nr','jump_coda'}


def region_count(kind):return 4 if kind=='jump_coda' else 2 if kind in REPEATS else 1


def draft_candidate(project,draft):
    """Return a verified presentation record or a user-facing reason."""
    kind=draft['kind'];regions=draft['regions']
    if len(regions)!=region_count(kind) or any(not r for r in regions):return None,tr('请先为此符号记录全部区域。')
    if kind in REPEATS:
        bars=[r.get('bars',[]) for r in regions]
        if any(not contiguous(b) or not all(0<=i<len(project.measures) for i in b) for b in bars):return None,tr('每个区域必须是连续的完整小节。')
        if any(max(a)+1!=min(b) for a,b in zip(bars,bars[1:])):return None,tr('区域必须按演奏顺序相邻，不能重叠或留空。')
        if kind=='jump_coda':
            a,b,c,d=(sorted(x) for x in bars)
            if len(a)!=len(c) or not same_segment(project,a[0],a[-1]+1,c[0],c[-1]+1):return None,tr('A 与 A′ 的音乐必须一致；歌词可以不同。')
            item=dict(kind='coda',start=a[0],first_end=a[-1]+1,hidden_start=c[0],hidden_end=c[-1]+1,end=d[-1]+1)
        else:
            item=pair_candidate(project,bars[0],bars[1],kind)
            if item is None:return None,tr('两区须等长且音乐一致；D.C. 从曲首开始，al Fine 须结束演奏。')
        if any(item['start']<x['end'] and x['start']<item['end'] for x in project.notation.get('compressions',[])):return None,tr('此区域已有反复逻辑，请先删除重叠符号。')
        return ('compressions',item),tr('检查通过，可应用到谱面；播放与 MIDI 保持不变。')
    ranges=regions[0].get('ranges',[])
    if len(ranges)!=1 or not annotation_allowed(project,kind,*ranges[0]):return None,tr('当前小节或拍选区不符合此符号的位置要求。')
    a,b=ranges[0];return ('symbols',dict(kind=kind,start=a,end=b)),tr('检查通过，可应用到谱面；播放与 MIDI 保持不变。')


def apply_draft(project,draft):
    candidate,reason=draft_candidate(project,draft)
    if candidate is None:raise ValueError(reason)
    collection,item=candidate
    if collection=='symbols':add_annotation(project,item['kind'],item['start'],item['end'])
    else:project.notation.setdefault(collection,[]).append(copy.deepcopy(item))
    return collection,project.notation[collection].index(item)


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
        from .presentation import active_compressions
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

"""Display-only score marks and phrase arcs, sharing the document undo history."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QPushButton,QListWidget,QListWidgetItem
from lingfeng.platform.i18n import tr
from lingfeng.engraving.presentation import ANNOTATION_LABELS, annotation_allowed, can_add_slur, slur_conflicts


class AnnotationPanel(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner
        box=QVBoxLayout(self);box.setContentsMargins(10,6,10,6)
        text=QLabel(tr('在谱面选择小节或拍后添加标识。连音弧可一次连接多个旋律音符；Ctrl 增选、Shift 连选或拖动框选。所有标识仅用于显示。'))
        text.setWordWrap(True);box.addWidget(text)
        row=QHBoxLayout();self.kind=QComboBox()
        for code,label in ANNOTATION_LABELS.items():self.kind.addItem(tr(label),code)
        self.kind.currentIndexChanged.connect(self.refresh);row.addWidget(self.kind)
        self.note_select=QPushButton(tr('选择音符'));self.note_select.clicked.connect(self.select_notes);row.addWidget(self.note_select)
        self.add_button=QPushButton(tr('添加标识'));self.add_button.clicked.connect(self.add);row.addWidget(self.add_button);box.addLayout(row)
        self.feedback=QLabel();box.addWidget(self.feedback)
        self.items=QListWidget();self.items.currentItemChanged.connect(self.selection_changed);box.addWidget(self.items)
        self.remove_button=QPushButton(tr('删除选中标识'));self.remove_button.clicked.connect(self.remove);box.addWidget(self.remove_button)
        self.refresh()

    def selected_notes(self):
        canvas=self.owner.score_view.canvas
        if canvas.selection_unit=='note':return set(canvas.selected_notes)
        ranges=canvas.selection_ranges()
        return {n.id for n in self.owner.project.notes if any(a<=n.start<b for a,b in ranges)}

    def select_notes(self):
        combo=self.owner.score_selection;combo.setCurrentIndex(combo.findData('note'))
        self.owner.score_view.canvas.setFocus()

    def refresh(self):
        if not hasattr(self,'items'):return
        selected=self.items.currentItem();current=selected.data(Qt.ItemDataRole.UserRole) if selected else None
        self.items.clear();p=self.owner.project
        for index,item in enumerate(p.notation.get('symbols',[])):
            label=tr(ANNOTATION_LABELS.get(item['kind'],item['kind']))
            entry=QListWidgetItem(tr('{0} · 第 {1} 小节',label,p.measure_at(min(item['start'],p.end-1))+1))
            entry.setData(Qt.ItemDataRole.UserRole,index);self.items.addItem(entry)
            if current==index:self.items.setCurrentItem(entry)
        self.refresh_selection()
        self.selection_changed()

    def refresh_selection(self):
        kind=self.kind.currentData();p=self.owner.project
        if kind=='slur':
            notes=self.selected_notes();count=len(notes)
            allowed=count>=2 and can_add_slur(p,notes)
            conflict=count>=2 and not allowed and slur_conflicts(p,dict(note_ids=notes))
        else:
            ranges=self.owner.score_view.canvas.selection_ranges()
            allowed=len(ranges)==1 and annotation_allowed(p,kind,*ranges[0]);conflict=False
        self.add_button.setEnabled(allowed)
        self.add_button.setToolTip(tr('歌词连音优先：所选连音弧与歌词 /- 连音冲突。') if conflict else '')
        self.note_select.setVisible(kind=='slur')
        self.feedback.setText(tr('已选 {0} 个旋律音符',count) if kind=='slur' else tr('请选择适用的连续小节或拍。'))

    def selection_changed(self,*args):
        if hasattr(self,'remove_button'):self.remove_button.setEnabled(self.items.currentItem() is not None)

    def add(self):
        kind=self.kind.currentData();canvas=self.owner.score_view.canvas
        payload=dict(bars=sorted(canvas.selected_bars),ranges=canvas.selection_ranges(),note_ids=sorted(self.selected_notes()))
        self.owner.score_command('slur' if kind=='slur' else 'symbol:'+kind,payload)

    def remove(self):
        item=self.items.currentItem()
        if item is None:return
        self.owner.score_command('remove_structure',dict(bars=[],ranges=[],key=('symbols',item.data(Qt.ItemDataRole.UserRole))))

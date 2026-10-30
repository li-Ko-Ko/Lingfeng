"""Progression library editing and audition-independent recipe dialogs."""
import copy
from lingfeng.platform.i18n import tr
from lingfeng.music.model import PATTERNS, PPQ, Chord
from lingfeng.music.progressions import tokens, resolve, progression_label, progression_key, preset_label, make_preset, presets, load_library, root_identity, matches_roots, targets, common_patterns, apply, capture, selection_root_query, search_recipe, DEFAULT_PRESETS

from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QComboBox,QLabel,QLineEdit,QCheckBox,
    QSpinBox,QDialogButtonBox,QPushButton,QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView)

from PySide6.QtCore import Qt

def tonic_selector(base,mode='Ionian'):
    """Modal degree labels, ordered chromatically from the anchor tonic."""
    from lingfeng.ui.theme import pitch_class_choices
    combo=QComboBox()
    for label,pc in pitch_class_choices(base,mode):combo.addItem(label,pc)
    combo.setToolTip(tr('1 对应起点小节主音。调内音保留调式音级，调外音遵循卷帘升降号偏好；按音高排列。'))
    return combo

class ProgressionEntryDialog(QDialog):
    """A recipe first, then an optional descriptive name; no name is music data."""
    def __init__(self,entry=None,parent=None):
        super().__init__(parent);self.setWindowTitle(tr('修改和弦进行' if entry else '添加和弦进行'));self.setMinimumWidth(480)
        layout=QVBoxLayout(self);form=QFormLayout();self.form=form;layout.addLayout(form)
        entry=entry or {};sequence=entry.get('sequence','');name=entry.get('name','')
        self.sequence=QLineEdit(progression_label(sequence) if sequence else '')
        self.sequence.setPlaceholderText('IV – iv – I');form.addRow(tr('罗马数字进行'),self.sequence)
        self.name=QLineEdit(name);self.name.setMaxLength(120);form.addRow(tr('名称（可选）'),self.name)
        self.auto_name=not name or bool(sequence and name==progression_label(sequence))
        hint=QLabel(tr('名称留空时使用罗马数字进行。支持 I/3（指定低音）、V/vi（副属）及 V/vi/#5（副属指定低音）。'))
        hint.setWordWrap(True);layout.addWidget(hint)
        self.error=QLabel();self.error.setWordWrap(True);layout.addWidget(self.error)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(self.buttons);self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject)
        self.name.textEdited.connect(self.name_edited);self.sequence.textChanged.connect(self.validate);self.validate()

    def name_edited(self,text):self.auto_name=not text.strip()
    def validate(self):
        try:
            entry=make_preset(self.sequence.text(),self.name.text())
            if self.auto_name:self.name.setText(progression_label(entry['sequence']))
            self.error.clear();valid=True
        except ValueError as exc:
            self.error.setText(str(exc) if self.sequence.text().strip() else tr('请输入罗马数字进行。'));valid=False
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(valid)
    def value(self):return make_preset(self.sequence.text(),self.name.text())
    def accept(self):
        try:self.value()
        except ValueError:self.validate();return
        super().accept()

class CaptureProgressionDialog(ProgressionEntryDialog):
    def __init__(self,project,ids,parent=None):
        text=capture(project,ids)
        super().__init__(dict(sequence=text),parent)
        self.setWindowTitle(tr('保存和弦进行'))
        start=min(c.start for c in project.chords if c.id in ids)
        context=project.context_at(start);self.tonic=tonic_selector(context.tonic,context.mode)
        self.form.insertRow(0,tr('主音'),self.tonic);self.sequence.setReadOnly(True)
        self.tonic.currentIndexChanged.connect(lambda:self.sequence.setText(progression_label(capture(project,ids,self.tonic.currentData()))))

class ProgressionManagerDialog(QDialog):
    def __init__(self,values,parent=None,query='',tonic=0,query_factory=None,mode='Ionian'):
        super().__init__(parent);self.setWindowTitle(tr('管理和弦进行'));self.resize(760,520);self.entries=presets(values)
        self.selection_query=query_factory
        box=QVBoxLayout(self);search=QHBoxLayout();box.addLayout(search)
        search.addWidget(QLabel(tr('主音')));self.tonic=tonic_selector(tonic,mode);search.addWidget(self.tonic)
        self.search_mode=QComboBox();self.search_mode.addItem(tr('按根音序列'), 'roots');self.search_mode.addItem(tr('按名称'),'name');search.addWidget(self.search_mode)
        self.search=QLineEdit();self.search.setClearButtonEnabled(True);search.addWidget(self.search,1)
        hint=QLabel(tr('输入罗马数字或实际和弦名（如 Gm C F）。所选和弦随主音重新换算；手输罗马数字保持相对关系。检索忽略性质与转位，可跳过中间和弦。'))
        hint.setWordWrap(True);box.addWidget(hint)
        self.table=QTableWidget(0,3);self.table.setHorizontalHeaderLabels([tr('名称'),tr('罗马数字进行'),tr('和弦名称（所选主音）')])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows);self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers);self.table.verticalHeader().hide();self.table.setWordWrap(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch);box.addWidget(self.table,1)
        self.info=QLabel();self.info.setWordWrap(True);box.addWidget(self.info)
        actions=QHBoxLayout();box.addLayout(actions)
        self.add_button=QPushButton(tr('添加…'));self.edit_button=QPushButton(tr('修改…'));self.remove_button=QPushButton(tr('删除'))
        for button in (self.add_button,self.edit_button,self.remove_button):actions.addWidget(button)
        actions.addStretch();self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);actions.addWidget(self.buttons)
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject)
        self.add_button.clicked.connect(self.add_entry);self.edit_button.clicked.connect(self.edit_entry);self.remove_button.clicked.connect(self.remove_entry)
        self.table.itemSelectionChanged.connect(self.update_actions);self.table.cellDoubleClicked.connect(lambda *args:self.edit_entry())
        self.search.textChanged.connect(self.filter_entries);self.search_mode.currentIndexChanged.connect(self.filter_entries)
        self.search.textEdited.connect(self.manual_query);self.tonic.currentIndexChanged.connect(self.change_tonic)
        self.search.setText(progression_label(query) if query else '');self.filter_entries()

    def manual_query(self,*args):self.selection_query=None
    def change_tonic(self):
        if self.selection_query and self.search_mode.currentData()=='roots':
            self.search.setText(progression_label(self.selection_query(self.tonic.currentData())))
        self.filter_entries()
    def current_index(self):
        item=self.table.item(self.table.currentRow(),0)
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None
    def filter_entries(self,*args,select=None):
        self.search.setPlaceholderText('I – IV – III / C F E' if self.search_mode.currentData()=='roots' else tr('输入名称关键词'))
        query=self.search.text().strip();indices=[];error=''
        try:
            if query and self.search_mode.currentData()=='roots':query=search_recipe(query,self.tonic.currentData())
            indices=[i for i,e in enumerate(self.entries) if (matches_roots(e['sequence'],query) if self.search_mode.currentData()=='roots' else query.casefold() in e['name'].casefold())]
        except ValueError as exc:error=str(exc)
        self.table.setRowCount(0)
        for row,index in enumerate(indices):
            entry=self.entries[index];self.table.insertRow(row)
            names=' – '.join(resolve(t,self.tonic.currentData()).name for t in tokens(entry['sequence']))
            for col,text in enumerate((entry['name'],progression_label(entry['sequence']),names)):
                item=QTableWidgetItem(text);item.setToolTip(text);item.setData(Qt.ItemDataRole.UserRole,index);self.table.setItem(row,col,item)
        self.info.setText(error or tr('显示 {0} / {1} 个和弦进行',len(indices),len(self.entries)))
        if indices:self.table.selectRow(indices.index(select) if select in indices else 0)
        self.update_actions()
    def update_actions(self):
        enabled=self.current_index() is not None;self.edit_button.setEnabled(enabled);self.remove_button.setEnabled(enabled and len(self.entries)>1)
    def store_entry(self,entry,index=None):
        self.selection_query=None
        if index is None:self.entries.append(entry)
        else:self.entries[index]=entry
        self.entries=presets(self.entries);self.search.clear();self.filter_entries(select=self.entries.index(entry))
    def add_entry(self):
        dialog=ProgressionEntryDialog(parent=self)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.store_entry(dialog.value())
    def edit_entry(self):
        index=self.current_index()
        if index is None:return
        dialog=ProgressionEntryDialog(self.entries[index],self)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.store_entry(dialog.value(),index)
    def remove_entry(self):
        index=self.current_index()
        if index is not None and len(self.entries)>1:self.entries.pop(index);self.filter_entries()
    def value(self):return copy.deepcopy(self.entries)

ProgressionSettingsDialog=ProgressionManagerDialog

class ProgressionDialog(QDialog):
    def __init__(self,project,cid,values,parent=None):
        super().__init__(parent);self.setWindowTitle(tr('应用和弦进行'));self.project=project;self.cid=cid
        self.setMinimumWidth(490);layout=QVBoxLayout(self);form=QFormLayout();layout.addLayout(form)
        self.preset=QComboBox()
        for entry in presets(values):self.preset.addItem(preset_label(entry),entry['sequence'])
        form.addRow(tr('预设'),self.preset)
        dest=targets(project,cid,1);context=project.context_at(dest[0].start if dest else 0)
        self.tonic=tonic_selector(context.tonic,context.mode)
        form.addRow(tr('主音'),self.tonic)
        self.sequence=QLineEdit(self.preset.currentData() or '',self);self.sequence.hide()
        self.roman=QLabel();self.roman.setWordWrap(True);self.roman.setTextFormat(Qt.TextFormat.PlainText);form.addRow(tr('罗马数字进行'),self.roman)
        self.resolved=QLabel();self.resolved.setWordWrap(True);self.resolved.setTextFormat(Qt.TextFormat.PlainText);form.addRow(tr('和弦名称（所选主音）'),self.resolved)
        self.preset.currentIndexChanged.connect(lambda:self.sequence.setText(self.preset.currentData() or ''))
        self.keep=QComboBox();self.keep.addItem(tr('保留已识别节奏型；其它使用下方节奏型'),True);self.keep.addItem(tr('全部使用下方节奏型'),False);form.addRow(tr('节奏型策略'),self.keep)
        self.pattern=QComboBox();form.addRow(tr('统一／备用节奏型'),self.pattern)
        self.velocity_check=QCheckBox(tr('统一力度'));self.velocity=QSpinBox();self.velocity.setRange(1,127);self.velocity.setValue(72);form.addRow(self.velocity_check,self.velocity)
        self.gate_check=QCheckBox(tr('统一发音长度'));self.gate=QSpinBox();self.gate.setRange(5,100);self.gate.setValue(90);self.gate.setSuffix('%');form.addRow(self.gate_check,self.gate)
        self.info=QLabel();self.info.setWordWrap(True);layout.addWidget(self.info)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(self.buttons);self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject)
        self.sequence.textChanged.connect(self.refresh);self.tonic.currentIndexChanged.connect(self.refresh);self.refresh()
    def refresh(self):
        try:
            seq=tokens(self.sequence.text());dest=targets(self.project,self.cid,len(seq));available=common_patterns(self.project,dest)
            self.roman.setText(progression_label(self.sequence.text()))
            from lingfeng.music.chord_operations import contextual_chord_name
            context=copy.copy(self.project.context_at(dest[0].start) if dest else self.project.context_at(0))
            if context.tonic%12!=self.tonic.currentData():context.mode='Ionian'
            context.tonic=48+self.tonic.currentData()
            self.resolved.setText(' – '.join(contextual_chord_name(self.project,resolve(token,context.tonic),context) for token in seq))
            old=self.pattern.currentData();self.pattern.clear()
            for key in available:self.pattern.addItem(tr(PATTERNS[key]),key)
            self.pattern.setCurrentIndex(max(0,self.pattern.findData(old)))
            self.info.setText(tr('将替换 {0} 个现有和弦；到工程末尾停止。全部按所选主音解释，区间和谱面调号不变。',len(dest)))
            self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(dest))
        except ValueError as exc:self.roman.clear();self.resolved.clear();self.info.setText(str(exc));self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
    def value(self):return dict(text=self.sequence.text(),tonic=self.tonic.currentData(),keep_rhythm=self.keep.currentData(),pattern=self.pattern.currentData(),velocity=self.velocity.value() if self.velocity_check.isChecked() else None,gate=self.gate.value()/100 if self.gate_check.isChecked() else None)

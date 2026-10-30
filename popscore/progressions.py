"""Tonic-independent Roman recipes, with an explicit tonic for each operation.

PyChord validates chord components and performs pitch-class transposition.
The progression grammar and editing policy are original Lingfeng code.
"""
import copy
import re
from .model import Chord,Note,MAJOR,QUALITIES,PATTERNS,PPQ,uid
from .i18n import tr
from .progression_catalog import HOOKTHEORY_RECIPES,CATALOG_VERSION

DEFAULT_PRESETS=[{'name':name,'sequence':sequence} for name,sequence,_ in HOOKTHEORY_RECIPES]+[
    {'name':'vi – IV – I – V','sequence':'vi IV I V'},
    {'name':'I – V – vi – iii – IV – I – IV – V','sequence':'I V vi iii IV I IV V'},
    {'name':'ii7 – V7 – Imaj7','sequence':'ii7 V7 Imaj7'},
    {'name':'IV – V – iii7 – vi','sequence':'IV V iii7 vi'},
    {'name':'I – IV – V','sequence':'I IV V'},
]
ROMANS=('I','II','III','IV','V','VI','VII')

def tokens(text):
    parts=[p.replace('add9','add2') for p in re.split(r'[\s,，;；|→–—-]+',text.strip()) if p]
    if not 1<=len(parts)<=128:raise ValueError(tr('和弦进行须包含 1–128 个罗马数字和弦。'))
    for token in parts:resolve(token,0)
    return parts

def resolve(token,tonic):
    from pychord import Chord as PyChord,QualityManager
    QualityManager().set_quality('add2',('1','2','3','5'))
    token=token.replace('♭','b').replace('♯','#')
    if token.count('/')>4:raise ValueError(tr('无效的罗马数字和弦：{0}',token))
    # A final numeric slash is a bass degree in the original key. It may follow
    # an applied chord: V/vi/#5 means E/G# when 1=C. V6 remains an added sixth.
    main,sep,tail=token.rpartition('/')
    bm=re.fullmatch(r'([b#]?)([1-7])',tail) if sep else None
    original_tonic=tonic
    body=main if bm else token
    base,secondary,target=body.partition('/')
    m=re.fullmatch(r'([b#]?)([ivIV]+)(.*)',base)
    if not m or m[2].upper() not in ROMANS:raise ValueError(tr('无效的罗马数字和弦：{0}',token))
    accidental,roman,suffix=m.groups()
    degree=ROMANS.index(roman.upper());root=(MAJOR[degree]+(-1 if accidental=='b' else 1 if accidental=='#' else 0))%12
    quality={'M7':'maj7','M9':'maj9','M':'','°':'dim','°7':'dim7','ø7':'m7b5','+':'aug','add9':'add2'}.get(suffix,suffix)
    if roman.islower() and quality in ('','7','6','9'):quality='m'+quality
    if roman.islower() and quality=='maj7':quality='mM7'
    if quality not in QUALITIES:raise ValueError(tr('无效的罗马数字和弦：{0}',token))
    bass_pc=(original_tonic+MAJOR[int(bm[2])-1]+(-1 if bm[1]=='b' else 1 if bm[1]=='#' else 0))%12 if bm else None
    if secondary:tonic=resolve(target,tonic).root%12
    pc=PyChord('C'+quality);pc.transpose((tonic+root)%12)
    actual=pc.components(visible=False)
    result=Chord(0,PPQ,48+(tonic+root)%12,quality,bass_pc)
    if set(p%12 for p in actual)!={p%12 for p in result.pitches if bass_pc is None or p%12!=bass_pc} and bass_pc is None:
        raise ValueError(tr('和弦音程不受支持：{0}',token))
    return result

def progression_label(text):
    return ' – '.join(tokens(text))


def progression_key(text):
    """Lexicographic musical degrees; equal prefixes put shorter recipes first."""
    result=[]
    for token in tokens(text):
        normalized=token.replace('♭','b').replace('♯','#')
        match=re.match(r'([b#]?)([ivIV]+)',normalized)
        chord=resolve(token,0)
        result.append((ROMANS.index(match[2].upper()),{'b':-1,'':0,'#':1}[match[1]],
                       tuple(QUALITIES).index(chord.quality),normalized.partition('/')[2]))
    return tuple(result)


def preset_label(entry):
    sequence=progression_label(entry['sequence'])
    return sequence if entry['name']==sequence else entry['name']+': '+sequence


def make_preset(sequence,name=''):
    parts=tokens(sequence);name=name.strip()[:120]
    if not name:name=' – '.join(parts)
    else:
        try:
            if tokens(name)==parts:name=' – '.join(parts)
        except ValueError:pass
    return dict(name=name,sequence=' '.join(parts))


def presets(values):
    if not isinstance(values,list):values=DEFAULT_PRESETS
    if not values:return []
    valid=[]
    for entry in values:
        try:
            if not isinstance(entry,dict) or not isinstance(entry.get('name',''),str) or not isinstance(entry.get('sequence'),str):continue
            valid.append(make_preset(entry['sequence'],entry.get('name','')))
        except (ValueError,KeyError,TypeError):continue
    return sorted(valid,key=lambda x:(progression_key(x['sequence']),x['name'].casefold())) if valid else presets(DEFAULT_PRESETS)


def load_library(values,version=0):
    """Add this catalogue once; retain custom names, edits and later deletions."""
    library=presets(None if values==[] and not (isinstance(version,int) and version>=CATALOG_VERSION) else values)
    if isinstance(version,int) and version>=CATALOG_VERSION:return library
    for name,sequence,_ in HOOKTHEORY_RECIPES:
        entry=make_preset(sequence,name)
        matches=[i for i,x in enumerate(library) if x['sequence']==entry['sequence']]
        anonymous=next((i for i in matches if library[i]['name']==progression_label(sequence)),None)
        if anonymous is not None:library[anonymous]=entry
        elif entry not in library:library.append(entry)
    return presets(library)


def root_identity(token):
    """Spelled root, not pitch class: #II and bIII remain distinct.

    Qualities and numeric bass slashes are ignored. Applied roots resolve to
    the original key, so V/vi matches III and viidim/vi matches #V.
    """
    normalized=token.replace('♭','b').replace('♯','#')
    main,sep,bass=normalized.rpartition('/')
    if sep and re.fullmatch(r'[b#]?[1-7]',bass):normalized=main
    base,sep,target=normalized.partition('/')
    match=re.match(r'([b#]?)([ivIV]+)',base)
    degree=ROMANS.index(match[2].upper());alter={'b':-1,'':0,'#':1}[match[1]]
    if not sep:return degree,alter
    td,ta=root_identity(target);pc=(MAJOR[degree]+alter+MAJOR[td]+ta)%12
    degree=(degree+td)%7;alter=(pc-MAJOR[degree]+6)%12-6
    return degree,alter


def matches_roots(sequence,query):
    if not query.strip():return True
    wanted=[root_identity(t) for t in tokens(query)];position=0
    for token in tokens(sequence):
        if root_identity(token)==wanted[position]:
            position+=1
            if position==len(wanted):return True
    return False

def targets(project,cid,count):
    ordered=sorted(project.chords,key=lambda c:c.start)
    index=next((i for i,c in enumerate(ordered) if c.id==cid),None)
    return [] if index is None else ordered[index:index+count]

def common_patterns(project,chords):
    from .rhythm import supports
    return [key for key in PATTERNS if all(supports(key,project,c.start) for c in chords)]

def apply(project,cid,text,keep_rhythm=True,pattern='block',velocity=None,gate=None,tonic=None):
    from .rhythm import analyze_performed,Rhythm,regenerate
    sequence=tokens(text);destinations=targets(project,cid,len(sequence))
    if not destinations:raise ValueError(tr('请选择起始和弦。'))
    tonic=project.context_at(destinations[0].start).tonic if tonic is None else tonic
    if pattern not in common_patterns(project,destinations):raise ValueError(tr('节奏型必须适用于所有目标拍号。'))
    ids=[]
    for old,token in zip(destinations,sequence):
        semantic=resolve(token,tonic)
        rhythm=analyze_performed(old,project) if keep_rhythm else None
        c=copy.deepcopy(old);c.root=semantic.root;c.quality=semantic.quality;c.bass=semantic.bass;c.recognized=True;c.custom_rhythm=False
        c.pattern=rhythm.pattern if rhythm else pattern;c.gate=gate if gate is not None else rhythm.gate if rhythm else old.gate
        if velocity is not None:c.velocity=velocity
        generated=regenerate(c,c.start,c.end,project,Rhythm(c.pattern,tuple(c.pitches),c.gate))
        if generated is None:raise ValueError(tr('无法生成该拍号的和弦节奏型。'))
        # Replacement terminates crossing events in this region, as any explicit chord edit does.
        project.put_chord(generated);ids.append(c.id)
    return ids

def capture(project,ids,tonic=None):
    """Keep qualities and explicit bass degrees, including inversions."""
    ordered=sorted((c for c in project.chords if c.id in ids),key=lambda c:c.start)
    if not ordered or any(not c.recognized or c.notes==[] for c in ordered):raise ValueError(tr('只有名称可识别的和弦可以加入和弦进行。'))
    context=project.context_at(ordered[0].start)
    tonic=context.tonic if tonic is None else tonic
    mode=context.mode if tonic%12==context.tonic%12 else 'Ionian'
    return ' '.join(c.roman(tonic,c.flat,mode).replace('♭','b').replace('♯','#') for c in ordered)


def selection_root_query(project,ids,tonic=None):
    """Chronological roots against one tonic; bass is never a root."""
    try:sequence=capture(project,ids,tonic)
    except ValueError:raise ValueError(tr('请选择名称可识别的和弦进行检索。')) from None
    result=[]
    for token in tokens(sequence):
        degree,alter=root_identity(token)
        result.append(('b'*(-alter) if alter<0 else '#' * alter)+ROMANS[degree])
    return ' '.join(result)


from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QComboBox,QLabel,QLineEdit,QCheckBox,
    QSpinBox,QDialogButtonBox,QPushButton,QTableWidget,QTableWidgetItem,QAbstractItemView,QHeaderView)


def tonic_selector(base,mode='Ionian'):
    """Modal degree labels, ordered chromatically from the anchor tonic."""
    from .theme import pitch_class_choices
    combo=QComboBox()
    for label,pc in pitch_class_choices(base,mode):combo.addItem(label,pc)
    combo.setToolTip(tr('1 对应起点小节主音。调内音保留调式音级，调外音遵循卷帘升降号偏好；按音高排列。'))
    return combo


def search_recipe(query,tonic):
    """Accept Roman relations or literal chord names interpreted at this tonic."""
    try:return ' '.join(tokens(query))
    except ValueError as roman_error:
        from pychord import Chord as PyChord
        parts=[p for p in re.split(r'[\s,，;；|→–—-]+',query.strip()) if p]
        if not 1<=len(parts)<=128:raise roman_error
        result=[]
        try:
            for part in parts:
                chord=PyChord(part.replace('♭','b').replace('♯','#'))
                root=PyChord(chord.root).components(visible=False)[0]
                result.append(Chord(0,PPQ,48+root).roman(tonic,flat='b' in chord.root).replace('♭','b').replace('♯','#'))
        except (ValueError,KeyError):raise roman_error from None
        return ' '.join(result)


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


# Preserve the import used by earlier integrations, with the new managed UI.
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
            from .chordops import contextual_chord_name
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


from .i18n import tr
import copy
from PySide6.QtWidgets import QDialog,QFormLayout,QComboBox,QSpinBox,QDoubleSpinBox,QLineEdit,QDialogButtonBox,QLabel,QVBoxLayout,QHBoxLayout,QPlainTextEdit,QCheckBox,QListWidget,QListWidgetItem,QAbstractItemView,QPushButton,QMessageBox
from .model import Note,Chord,PPQ,QUALITIES,PATTERNS,SHARP,MODES,pitch_name,degree_text


class MarkerDialog(QDialog):
    def __init__(self,project,index,parent=None,inserting=False,bars=None):
        super().__init__(parent);self.setWindowTitle(tr('插入小节') if inserting else tr('第 {0} 小节标记', index + 1))
        form=QFormLayout(self);form.setSpacing(12)
        from .controls import SizeControl
        self.count=None
        if inserting:
            self.count=SizeControl(1,1,max(1,1000-len(project.measures)));self.count.setSuffix('');form.addRow(tr('小节数量'),self.count)
        source=min(index,len(project.measures)-1);m=project.measures[source];c=project.context_at(project.starts[source])
        from .theme import roll_pitch_name,roll_degree_text
        self.tonic=QComboBox()
        for pitch in range(21,109):self.tonic.addItem(roll_degree_text(pitch,c.tonic,c.mode)+' · '+roll_pitch_name(pitch),pitch)
        self.tonic.setCurrentIndex(self.tonic.findData(c.tonic));form.addRow(tr('主音（1 =）'),self.tonic)
        self.mode=QComboBox()
        for mode in MODES:self.mode.addItem(mode,mode)
        self.mode.setCurrentIndex(self.mode.findData(c.mode));form.addRow(tr('调式'),self.mode)
        self.tonic.currentIndexChanged.connect(self.update_modes);self.update_modes()
        self.numerator=SizeControl(m.numerator,1,16);self.numerator.setSuffix('');form.addRow(tr('拍号 · 分子'),self.numerator)
        self.denominator=QComboBox()
        for d in (2,4,8,16):self.denominator.addItem(str(d),d)
        self.denominator.setCurrentIndex(self.denominator.findData(m.denominator));form.addRow(tr('拍号 · 分母'),self.denominator)
        bars=bars or [index]
        if not inserting:self.setWindowTitle(tr('设置所选小节拍号与调性'))
        text=tr('新小节独立标记；后方原有小节保留原标记。跨越插入点的音符和和弦分开，插入处留空。') if inserting else tr('应用到 {0} 个小节：{1}。未选小节保留原设置；相同标记只显示一次。改变拍号会顺延后续音乐。',len(bars),', '.join(str(i+1) for i in bars))
        info=QLabel(text);info.setWordWrap(True);form.addRow(info)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);form.addRow(buttons);self.setMinimumWidth(360)
        if inserting and len(project.measures)>=1000:
            buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False);info.setText(tr('插入后项目不能超过 1000 小节。'))

    def update_modes(self):
        from . import theme
        from .model import FLAT
        tonic=self.tonic.currentData();names=FLAT if theme.ACCIDENTAL_PREFERENCE=='flat' else SHARP
        for i in range(self.mode.count()):
            mode=self.mode.itemData(i)
            degrees='  '.join(degree_text(tonic+offset,tonic,unicode=False,mode=mode)+':'+names[(tonic+offset)%12] for offset in MODES[mode])
            self.mode.setItemText(i,mode+' · '+degrees)
        self.mode.setMinimumContentsLength(48)

    def value(self):return dict(tonic=self.tonic.currentData(),mode=self.mode.currentData(),numerator=self.numerator.value(),denominator=self.denominator.currentData())


from .sounddialog import SoundSettingsDialog


class NoteDialog(QDialog):
    def __init__(self,note,project,parent=None):
        super().__init__(parent);self.setWindowTitle(tr('音符属性'));self.note=copy.deepcopy(note)
        form=QFormLayout(self);form.setSpacing(14)
        self.pitch=QComboBox()
        for p in range(21,109):self.pitch.addItem(pitch_name(p),p)
        self.pitch.setCurrentIndex(self.pitch.findData(note.pitch));form.addRow(tr('音高'),self.pitch)
        self.duration=QComboBox()
        for label,value in [(tr('全音符'),3840),(tr('附点二分音符'),2880),(tr('二分音符'),1920),(tr('附点四分音符'),1440),(tr('四分音符'),960),(tr('附点八分音符'),720),(tr('四分音符三连音'),640),(tr('八分音符'),480),(tr('附点十六分音符'),360),(tr('八分音符三连音'),320),(tr('十六分音符'),240),(tr('附点三十二分音符'),180),(tr('十六分音符三连音'),160),(tr('三十二分音符'),120),(tr('六十四分音符'),60)]:self.duration.addItem(label,value)
        if self.duration.findData(note.duration)<0:self.duration.addItem(tr('自定义 · {0:g} 个四分音符', note.duration / PPQ),note.duration)
        self.duration.setCurrentIndex(self.duration.findData(note.duration));form.addRow(tr('时值'),self.duration)
        self.start=QSpinBox();self.start.setRange(0,project.end-1);self.start.setValue(note.start);self.start.setSingleStep(60);form.addRow(tr('起点（tick）'),self.start)
        self.velocity=QSpinBox();self.velocity.setRange(1,127);self.velocity.setValue(note.velocity);form.addRow(tr('力度'),self.velocity)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);form.addRow(self.buttons)
        self.setMinimumWidth(320)

    def value(self):
        self.note.pitch=self.pitch.currentData();self.note.start=self.start.value();self.note.duration=self.duration.currentData();self.note.velocity=self.velocity.value()
        return self.note


CHORD_EDIT_OPTION_KEYS=('quality','pattern','gate','velocity')

def chord_edit_defaults(options):
    """Drop retired root/bass/octave/regeneration memory on upgrade."""
    return {key:options[key] for key in CHORD_EDIT_OPTION_KEYS if key in options} if isinstance(options,dict) else {}


class ChordDialog(QDialog):
    def __init__(self,chord,project,parent=None,defaults=None):
        super().__init__(parent);self.setWindowTitle(tr('和弦'));self.chord=copy.deepcopy(chord);self.project=project
        form=QFormLayout(self);form.setSpacing(14)
        self.root=QComboBox()
        for pc,name in enumerate(SHARP):self.root.addItem(name,pc)
        tonic=project.context_at(chord.start).tonic%12
        self.root.setCurrentIndex(self.root.findData(tonic));form.addRow(tr('根音'),self.root)
        self.quality=QComboBox()
        from .chordops import quality_items
        for code,label in quality_items():self.quality.addItem(label,code)
        self.quality.setCurrentIndex(self.quality.findData(chord.quality));form.addRow(tr('和弦性质'),self.quality)
        self.bass=QComboBox()
        for pc,name in enumerate(SHARP):self.bass.addItem(name,pc)
        self.bass.setCurrentIndex(self.bass.findData(tonic));form.addRow(tr('指定低音 / 转位'),self.bass)
        self.bass.setToolTip(tr('改变根音时低音同步跟随；单独改变低音不会改变根音。'))
        self.start=QDoubleSpinBox();self.start.setRange(0,project.end/PPQ-.0625);self.start.setDecimals(4);self.start.setSingleStep(.25);self.start.setValue(chord.start/PPQ);self.start.setToolTip(tr('从项目起点 0 开始，以四分音符为单位。'));form.addRow(tr('起点（四分音符）'),self.start)
        self.start.valueChanged.connect(self.update_root_labels);self.update_root_labels()
        self.duration=QDoubleSpinBox();self.duration.setRange(.0625,project.end/PPQ);self.duration.setDecimals(4);self.duration.setSingleStep(.25);self.duration.setValue(chord.duration/PPQ);form.addRow(tr('时长（四分音符）'),self.duration)
        self.pattern=QComboBox()
        for code,label in PATTERNS.items():self.pattern.addItem(tr(label),code)
        from .rhythm import analyze_performed
        rhythm=analyze_performed(chord,project);self.recognized_rhythm=rhythm
        self.pattern.setCurrentIndex(self.pattern.findData(rhythm.pattern if rhythm else chord.pattern));form.addRow(tr('节奏型'),self.pattern)
        self.gate=QSpinBox();self.gate.setRange(5,100);self.gate.setValue(round((rhythm.gate if rhythm else chord.gate)*100));self.gate.setSuffix('%');form.addRow(tr('发音长度'),self.gate)
        self.velocity=QSpinBox();self.velocity.setRange(1,127);self.velocity.setValue(chord.velocity);form.addRow(tr('默认力度'),self.velocity)
        self.octave=QSpinBox();self.octave.setRange(-1,2);self.octave.setValue(chord.octave);form.addRow(tr('伴奏八度'),self.octave)
        self.regenerate=QCheckBox(tr('重新生成和弦'));self.regenerate.setChecked(True);form.addRow(self.regenerate)
        self.pattern.currentIndexChanged.connect(lambda:self.regenerate.setChecked(True))
        self.regenerate.toggled.connect(self.update_patterns)
        self.start.valueChanged.connect(self.update_patterns);self.update_patterns()
        if chord.notes is not None:
            label=QLabel(tr('默认重新生成完整和弦音。取消勾选且根音、性质不变时，保留实际音符编辑。'));label.setWordWrap(True);form.addRow(label)
        self.preview=QLabel();form.addRow(tr('级数 / 和弦名称'),self.preview)
        self.root.currentIndexChanged.connect(self.follow_root)
        for combo in [self.root,self.quality,self.bass,self.start,self.duration]:
            signal=combo.currentIndexChanged if isinstance(combo,QComboBox) else combo.valueChanged
            signal.connect(self.update_preview)
        if rhythm is not None and chord.recognized:self.root.currentIndexChanged.connect(lambda:self.regenerate.setChecked(True))
        self.apply_options(defaults)
        self.update_preview()
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);form.addRow(buttons);self.setMinimumWidth(340)

    def options(self):
        """Only these four confirmed controls carry over to the next edit."""
        return dict(quality=self.quality.currentData(),pattern=self.pattern.currentData(),
                    gate=self.gate.value(),velocity=self.velocity.value())

    def follow_root(self):
        self.bass.setCurrentIndex(self.bass.findData(self.root.currentData()))

    def apply_options(self,options):
        if not isinstance(options,dict):return
        for name in CHORD_EDIT_OPTION_KEYS:
            if name not in options:continue
            control=getattr(self,name);value=options[name];blocked=control.blockSignals(True)
            try:
                if isinstance(control,QComboBox):
                    if name=='quality' and value=='add9':value='add2'
                    index=control.findData(value)
                    if index>=0:control.setCurrentIndex(index)
                elif isinstance(control,QCheckBox):
                    if type(value) is bool:control.setChecked(value)
                elif type(value) is int and control.minimum()<=value<=control.maximum():control.setValue(value)
            finally:control.blockSignals(blocked)
        self.update_patterns()

    def value(self):
        from .chordops import change_root,change_quality,replace_bass
        chord=copy.deepcopy(self.chord)
        root=self.root.currentData();quality=self.quality.currentData();bass=self.bass.currentData()
        if bass==root:bass=None # Root-position bass keeps the existing project representation.
        rebuild=self.regenerate.isChecked() or (self.recognized_rhythm is not None and chord.recognized and (root!=chord.root%12 or quality!=chord.quality))
        if not rebuild:
            if root!=chord.root%12:change_root(chord,root,self.project,regenerate_notes=False)
            if quality!=chord.quality:change_quality(chord,quality,self.project,regenerate_notes=False)
            if bass!=chord.bass:replace_bass(chord,root if bass is None else bass,self.project)
        chord.root=48+root;chord.quality=quality;chord.bass=bass;chord.start=round(self.start.value()*PPQ);chord.duration=round(self.duration.value()*PPQ)
        chord.gate=self.gate.value()/100;chord.velocity=self.velocity.value();chord.octave=self.octave.value();chord.recognized=True
        if rebuild:chord.pattern=self.pattern.currentData();chord.notes=None;chord.custom_rhythm=False
        if chord.notes is not None:
            chord.notes=[n for n in chord.notes if n.start<chord.duration]
            for n in chord.notes:n.duration=min(n.duration,chord.duration-n.start)
        return chord

    def update_root_labels(self):
        from .theme import pitch_class_choices
        context=self.project.context_at(round(self.start.value()*PPQ))
        for combo in (self.root,self.bass):
            selected=combo.currentData();blocked=combo.blockSignals(True);combo.clear()
            for label,pc in pitch_class_choices(context.tonic,context.mode):combo.addItem(label,pc)
            combo.setCurrentIndex(combo.findData(selected));combo.blockSignals(blocked)

    def update_preview(self):
        from .chordops import roman_label,contextual_chord_name
        chord=self.value()
        self.preview.setText(roman_label(self.project,chord)+'   '+contextual_chord_name(self.project,chord))

    def update_patterns(self):
        from .rhythm import supports
        tick=round(self.start.value()*PPQ)
        for i in range(self.pattern.count()):self.pattern.model().item(i).setEnabled(supports(self.pattern.itemData(i),self.project,tick))
        if self.regenerate.isChecked() and not supports(self.pattern.currentData(),self.project,tick):self.pattern.setCurrentIndex(0)


class ChordPreferenceDialog(QDialog):
    def __init__(self,parent=None):
        from .chordops import quality_items
        from PySide6.QtCore import Qt
        super().__init__(parent);self.setWindowTitle(tr('和弦菜单偏好'));box=QVBoxLayout(self)
        info=QLabel(tr('拖动调整和弦性质顺序，也可使用上移、下移按钮。'));info.setWordWrap(True);box.addWidget(info)
        self.list=QListWidget();self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        for code,label in quality_items():
            item=QListWidgetItem(label);item.setData(Qt.ItemDataRole.UserRole,code);self.list.addItem(item)
        box.addWidget(self.list);row=QHBoxLayout()
        for label,delta in [('上移',-1),('下移',1)]:
            button=QPushButton(tr(label));button.clicked.connect(lambda checked=False,d=delta:self.move_item(d));row.addWidget(button)
        box.addLayout(row);buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);box.addWidget(buttons);self.resize(400,550)
    def move_item(self,delta):
        index=self.list.currentRow();target=index+delta
        if index>=0 and 0<=target<self.list.count():item=self.list.takeItem(index);self.list.insertItem(target,item);self.list.setCurrentRow(target)
    def value(self):
        from PySide6.QtCore import Qt
        return [self.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.list.count())]

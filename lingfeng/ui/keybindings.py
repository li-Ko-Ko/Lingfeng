"""Configurable editor commands, scoped to this application's editing windows."""
from PySide6.QtCore import QObject,QEvent,Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (QApplication,QDialog,QFormLayout,QKeySequenceEdit,QDialogButtonBox,
    QLabel,QPushButton,QLineEdit,QTextEdit,QPlainTextEdit,QAbstractSpinBox,QComboBox,QMenu,
    QVBoxLayout,QWidget,QScrollArea,QFrame,QMessageBox)
from lingfeng.platform.i18n import tr

COMMANDS={
    'new':('新建','Ctrl+N'),'open':('打开项目…','Ctrl+O'),
    'save':('保存','Ctrl+S'),'save_as':('另存为…','Ctrl+Shift+S'),
    'undo':('撤销','Ctrl+Z'),'redo':('重做','Ctrl+Y'),'redo_alt':('重做（备用快捷键）','Ctrl+Shift+Z'),
    'cut_selection':('剪切选区','Ctrl+X'),'copy_selection':('复制选区','Ctrl+C'),
    'paste_selection':('粘贴选区','Ctrl+V'),'select_all':('全选','Ctrl+A'),
    'up':('上移：音符半音／和弦根音半音','W'),'down':('下移：音符半音／和弦根音半音','S'),
    'scale_up':('音符／和弦调内上移一级','Alt+W'),'scale_down':('音符／和弦调内下移一级','Alt+S'),
    'scale_up_alt':('音符／和弦调内上移一级（备用快捷键）','Alt+Up'),'scale_down_alt':('音符／和弦调内下移一级（备用快捷键）','Alt+Down'),
    'octave_up':('音符上移八度','Ctrl+Up'),'octave_down':('音符下移八度','Ctrl+Down'),
    'left':('向左移动音符／和弦','A'),'right':('向右移动音符／和弦','D'),
    'view_left':('向左浏览时间轴','Left'),'view_right':('向右浏览时间轴','Right'),
    'toggle_tool':('切换智能／绘制工具','Q'),'switch_input':('切换旋律／和弦输入位置','E'),
    'grid_triplet':('切换吸附格点三连音','Shift+3'),
    'smart':('选择智能工具',''),'draw':('选择绘制工具',''),
    'play':('播放／暂停','Space'),'replay':('回到定位线','R'),
    'beginning':('返回曲首并暂停','Ctrl+Home'),
    'split':('二等分选区','Shift+S'),'merge':('合并选区','Alt+Shift+M'),
    'delete':('删除选区','Del'),'edit_chord':('编辑选中和弦','C'),
    'delete_alt':('删除选区（备用快捷键）','Backspace'),'next_chord':('选择下一个和弦','Tab'),
}
STANDARD={'Ctrl+Z':'undo','Ctrl+Y':'redo','Ctrl+Shift+Z':'redo','Ctrl+C':'copy_selection','Ctrl+X':'cut_selection','Ctrl+V':'paste_selection','Ctrl+A':'select_all','Ctrl+S':'save','Ctrl+Shift+S':'save_as'}
ALIASES={'redo_alt':'redo','delete_alt':'delete','scale_up_alt':'scale_up','scale_down_alt':'scale_down'}
GLOBAL_COMMANDS={'new','open','save','save_as','undo','redo','cut_selection','copy_selection','paste_selection','select_all'}
FIXED_KEYS={'Esc':'取消当前操作／清除选择','Return / Enter':'确认输入或对话框','Shift+Tab':'反向切换焦点','Alt+F4':'关闭当前窗口'}
RESERVED={'Esc','Backtab','Shift+Backtab','Shift+Tab','Return','Enter','Alt+F4'}


def canonical(text):return QKeySequence(text).toString(QKeySequence.SequenceFormat.PortableText)


def normalized(mapping):
    return {key:canonical(mapping.get(key,default)) for key,(label,default) in COMMANDS.items()}


def validate(mapping):
    used=set()
    for command,text in mapping.items():
        sequence=QKeySequence(text);text=canonical(text)
        if sequence.count()>1:raise ValueError(tr('快捷键只支持一组按键组合。'))
        if text in RESERVED:raise ValueError(tr('该快捷键保留给系统或输入控件：{0}',text))
        if text and text in used:raise ValueError(tr('快捷键重复：{0}',text))
        if text:used.add(text)


def load_bindings(mapping):
    try:
        mapping=dict(mapping) if isinstance(mapping,dict) else {}
        # Migrate only the old defaults; retain customized direct-tool bindings.
        if 'toggle_tool' not in mapping and mapping.get('smart')=='Q':mapping.pop('smart')
        if 'switch_input' not in mapping and mapping.get('draw')=='E':mapping.pop('draw')
        if mapping.get('replay')=='Home':mapping['replay']='R'
        result=normalized(mapping)
        # Explicit saved choices take priority over newly introduced defaults.
        used=set()
        for key in [k for k in mapping if k in result]+[k for k in result if k not in mapping]:
            if result[key] in used:result[key]=''
            elif result[key]:used.add(result[key])
        validate(result);return result
    except (ValueError,TypeError):return normalized({})


def binding_owner(widget):
    owner=widget
    while owner is not None and not hasattr(owner,'keybindings'):
        owner=getattr(owner,'owner',None) or owner.parentWidget()
    return owner


def shortcut_sequences(bindings,command):
    return [QKeySequence(bindings[key]) for key in (command,*(k for k,v in ALIASES.items() if v==command)) if bindings.get(key)]


def menu_shortcut(action,widget,command,popup=True):
    """Use Qt's aligned shortcut column, scoped to the popup rather than its editor."""
    owner=binding_owner(widget)
    bindings=owner.keybindings if owner is not None else normalized({})
    sequences=shortcut_sequences(bindings,command)
    action.setShortcuts(sequences);action.setShortcutContext(Qt.ShortcutContext.WidgetShortcut if popup else Qt.ShortcutContext.WindowShortcut)
    # An explicit tab keeps all alternate keys in Qt's aligned shortcut column.
    base=action.property('shortcutLabel') or action.text().split('\t')[0];action.setProperty('shortcutLabel',base)
    action.setText(base+('\t'+' / '.join(s.toString(QKeySequence.SequenceFormat.NativeText) for s in sequences) if len(sequences)>1 else ''))
    action.setShortcutVisibleInContextMenu(True);action.setProperty('shortcutCommand',command)
    action.setProperty('shortcutPopup',popup)
    return action


class EditorKeys(QObject):
    def __init__(self,owner):super().__init__(owner);self.owner=owner

    def eventFilter(self,obj,event):
        if event.type() not in (QEvent.Type.FocusIn,QEvent.Type.ShortcutOverride,QEvent.Type.KeyPress):return False
        w=self.owner
        if not getattr(w,'workspace_ready',False) or QApplication.activeModalWidget() or QApplication.activePopupWidget():return False
        focus=QApplication.focusWidget()
        window=focus.window() if focus else QApplication.activeWindow()
        if window not in (w,w.melody_window,w.harmony_window,w.score_tools,*w.score_floats.values()):return False
        if event.type()==QEvent.Type.FocusIn:
            surface=w.edit_surface(obj)
            if window is w and w.workspace=='compose' and surface in ('melody','harmony','chords','timeline'):w.last_main_surface=surface
            return False
        for target in (focus,obj):
            current=target
            while current:
                if isinstance(current,(QLineEdit,QTextEdit,QPlainTextEdit,QAbstractSpinBox,QComboBox,QKeySequenceEdit,QMenu)):return False
                current=current.parentWidget() if hasattr(current,'parentWidget') else None
        sequence=QKeySequence(event.keyCombination()).toString(QKeySequence.SequenceFormat.PortableText)
        command=next((key for key,value in w.keybindings.items() if value and value==sequence),None)
        if command=='next_chord':
            from lingfeng.ui.piano_roll import ChordLane
            roll=w.active_roll()
            if roll.edit_target=='chords' and roll.selected_chords and (isinstance(focus,ChordLane) or focus in (roll,roll.viewport())):
                event.accept()
                if event.type()==QEvent.Type.KeyPress:w.next_chord(roll)
                return True
            return False
        # Windows layouts may report the shifted glyph instead of the digit.
        if command is None and event.key()==Qt.Key.Key_NumberSign and event.modifiers()==Qt.KeyboardModifier.ShiftModifier:
            command=next((key for key,value in w.keybindings.items() if value=='Shift+3'),None)
        if command is None:return False
        command=ALIASES.get(command,command)
        event.accept()
        if event.type()==QEvent.Type.KeyPress:
            if command in GLOBAL_COMMANDS:
                if not event.isAutoRepeat():
                    if command=='save_as':w.save(True)
                    else:getattr(w,command)()
            elif not event.isAutoRepeat() or command in ('up','down','scale_up','scale_down','octave_up','octave_down','left','right','view_left','view_right'):w.editor_key_command(command)
        return True


class KeyBindingsDialog(QDialog):
    def __init__(self,mapping,parent=None):
        super().__init__(parent);self.setWindowTitle(tr('快捷键设置'));self.setMinimumWidth(430);self.resize(560,650);root=QVBoxLayout(self);self.fields={}
        info=QLabel(tr('点击输入框后按下快捷键；清空可禁用。文本输入时不触发编辑快捷键。'));info.setWordWrap(True);root.addWidget(info)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame);body=QWidget();form=QFormLayout(body);form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows);scroll.setWidget(body);root.addWidget(scroll,1)
        sections={'new':'文件','undo':'编辑','up':'移动','toggle_tool':'工具','play':'播放','split':'选区编辑'}
        mapping=load_bindings(mapping);self.previous=dict(mapping);self.resolving=False
        for key,(label,default) in COMMANDS.items():
            if key in sections:
                heading=QLabel(tr(sections[key]));heading.setStyleSheet('font-weight:600; margin-top:8px');form.addRow(heading)
            field=QKeySequenceEdit(QKeySequence(mapping[key]));field.setMaximumSequenceLength(1);field.setFinishingKeyCombinations([]);field.setClearButtonEnabled(True);self.fields[key]=field;form.addRow(tr(label),field)
            field.editingFinished.connect(lambda k=key:self.resolve_change(k))
        form.addRow(QLabel(tr('系统与输入控件（固定）')))
        for key,label in FIXED_KEYS.items():
            field=QLineEdit(key);field.setReadOnly(True);form.addRow(tr(label),field)
        self.error=QLabel();self.error.setWordWrap(True);root.addWidget(self.error)
        reset=QPushButton(tr('恢复默认快捷键'));reset.clicked.connect(self.reset);root.addWidget(reset)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
    def reset(self):
        self.previous=normalized({})
        for key,field in self.fields.items():field.setKeySequence(QKeySequence(self.previous[key]))
        self.error.clear()
    def value(self):return {key:field.keySequence().toString(QKeySequence.SequenceFormat.PortableText) for key,field in self.fields.items()}
    def accept(self):
        for key in self.fields:
            if not self.resolve_change(key):return
        try:validate(self.value())
        except ValueError as exc:self.error.setText(str(exc));return
        super().accept()

    def resolve_change(self,key):
        if self.resolving:return True
        self.resolving=True
        try:return self._resolve_change(key)
        finally:self.resolving=False

    def _resolve_change(self,key):
        value=self.fields[key].keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        if value==self.previous[key]:return True
        try:validate({key:value})
        except ValueError as exc:
            self.error.setText(str(exc));self.fields[key].setKeySequence(QKeySequence(self.previous[key]));return False
        conflicts=[other for other,text in self.value().items() if other!=key and value and text==value]
        if conflicts:
            names='、'.join(tr(COMMANDS[other][0]) for other in conflicts)
            message=tr('快捷键 {0} 已绑定到「{1}」。继续会清除这些功能的该快捷键，并将它绑定到「{2}」。是否继续？',value,names,tr(COMMANDS[key][0]))
            if QMessageBox.question(self,tr('替换快捷键绑定'),message,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:
                self.fields[key].setKeySequence(QKeySequence(self.previous[key]));return False
            for other in conflicts:
                self.fields[other].clear();self.previous[other]=''
        self.previous[key]=value;self.error.clear();return True

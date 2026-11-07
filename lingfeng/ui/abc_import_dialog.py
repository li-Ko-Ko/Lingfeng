from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout,
)

from lingfeng.music.model import PATTERNS
from lingfeng.platform.i18n import tr
from lingfeng.ui.controls import import_bar_control


class AbcImportDialog(QDialog):
    def __init__(self, project, data, parent=None, *, bar_index=0):
        super().__init__(parent)
        self.setWindowTitle(tr('导入 ABC'))
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        description = QLabel(tr('将 ABC 插入当前工程。后续小节顺延，跨插入点的音符与和弦会断开。'))
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        layout.addLayout(form)
        self.bar = import_bar_control(project,bar_index)
        form.addRow(tr('插入到第几小节'),self.bar)
        self.sources = {}
        defaults = data.defaults()
        for target, caption in (
            ('vocal', project.melody_name(0)),
            ('instrument', project.melody_name(1)),
            ('harmony', tr('和弦卷帘音符')),
            ('symbols', tr('和弦轨符号')),
        ):
            box = QComboBox()
            box.addItem(tr('不导入'), None)
            for voice in data.voices.values():
                count = len(voice.symbols if target == 'symbols' else voice.notes)
                if count or (target == 'harmony' and voice.id == defaults['harmony']):
                    name = voice.name if voice.name == voice.id else f'{voice.name} ({voice.id})'
                    label = '{0} · {1} 个和弦符号' if target == 'symbols' else '{0} · {1} 个音符'
                    box.addItem(tr(label, name, count), voice.id)
            box.setCurrentIndex(max(0, box.findData(defaults[target])))
            box.setEnabled(box.count() > 1)
            form.addRow(caption, box)
            self.sources[target] = box

        self.pattern = QComboBox()
        for pattern, label in PATTERNS.items():
            self.pattern.addItem(tr(label), pattern)
        form.addRow(tr('生成和弦的节奏型'), self.pattern)
        self.sections = QCheckBox(tr('导入段落标记'))
        self.sections.setChecked(True)
        layout.addWidget(self.sections)
        self.tempo = QCheckBox(tr('应用文件速度到整个工程：{0} BPM',data.bpm))
        layout.addWidget(self.tempo)

        details = QLabel(tr('保留写出的节奏与音高；反复记号按书写顺序导入。若指定和弦卷帘的音符来源，则保留其节奏；否则用和弦符号生成和弦。'))
        details.setWordWrap(True)
        layout.addWidget(details)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr('插入'))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty('localizedLabel','插入')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        for box in self.sources.values():
            box.currentIndexChanged.connect(self._update)
        self._update()

    def _update(self):
        self.pattern.setEnabled(bool(self.sources['symbols'].currentData()) and self.sources['harmony'].currentData() is None)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(any(box.currentData() for box in self.sources.values()))

    def value(self):
        return dict(
            ((target, box.currentData()) for target, box in self.sources.items()),
            sections=self.sections.isChecked(), pattern=self.pattern.currentData(),
        )

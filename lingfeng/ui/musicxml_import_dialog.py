"""Map MusicXML parts to the destination score and select an insertion bar."""

from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout

from lingfeng.platform.i18n import tr
from lingfeng.ui.controls import import_bar_control


class MusicXmlImportDialog(QDialog):
    def __init__(self, project, data, parent=None, *, bar_index=0):
        super().__init__(parent)
        self.setWindowTitle(tr('导入 MusicXML'))
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        description = QLabel(tr('按指定小节插入 MusicXML。可分别选择旋律、实际和弦音符及和弦符号的来源。'))
        description.setWordWrap(True)
        layout.addWidget(description)
        form = QFormLayout()
        layout.addLayout(form)
        self.bar = import_bar_control(project, bar_index)
        form.addRow(tr('插入到第几小节'), self.bar)
        self.sources = {}
        defaults = data.default_mapping()
        for role, label in (
            ('melody', project.melody_name(0)), ('instrument', project.melody_name(1)),
            ('chords', tr('和弦卷帘音符')), ('symbols', tr('和弦轨符号')),
        ):
            choices = QComboBox()
            choices.addItem(tr('不导入'), None)
            for identifier, part in data.parts.items():
                count = len(part.symbols if role == 'symbols' else part.notes)
                if count:
                    caption = '{0} · {1} 个和弦符号' if role == 'symbols' else '{0} · {1} 个音符'
                    choices.addItem(tr(caption, part.name, count), identifier)
            choices.setCurrentIndex(max(0, choices.findData(defaults.get(role))))
            choices.setEnabled(choices.count() > 1)
            self.sources[role] = choices
            form.addRow(label, choices)
        self.tempo = QCheckBox(tr('应用文件速度到整个工程：{0} BPM', data.bpm))
        layout.addWidget(self.tempo)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.confirm = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.confirm.setText(tr('插入'))
        self.confirm.setProperty('localizedLabel', '插入')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for choices in self.sources.values():
            choices.currentIndexChanged.connect(self.update_confirmation)
        self.update_confirmation()

    def update_confirmation(self):
        self.confirm.setEnabled(any(choices.currentData() is not None for choices in self.sources.values()))

    def mapping(self):
        return {role: choices.currentData() for role, choices in self.sources.items()}

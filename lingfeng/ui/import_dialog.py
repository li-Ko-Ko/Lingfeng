"""Map MIDI source tracks and choose the insertion bar."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QListWidget, QListWidgetItem, QTabWidget, QVBoxLayout)

from lingfeng.platform.i18n import tr
from lingfeng.ui.controls import import_bar_control


class MidiImportDialog(QDialog):
    def __init__(self, project, data, parent=None, *, bar_index=0):
        super().__init__(parent)
        self.data = data
        self.setWindowTitle(tr('导入 MIDI'))
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        description = QLabel(tr('为三个目标轨道选择 MIDI 来源。导入会插入小节，后续音乐整体顺延。'))
        description.setWordWrap(True)
        layout.addWidget(description)

        form = QFormLayout()
        layout.addLayout(form)
        self.bar = import_bar_control(project, bar_index)
        form.addRow(tr('插入到第几小节'), self.bar)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.sources = {}
        defaults = {role: set(indices) for role, indices in data.default_mapping().items()}
        for role, label in (('melody', project.melody_name(0)), ('instrument', project.melody_name(1)),
                            ('chords', tr('和弦卷帘音符'))):
            tracks = QListWidget()
            self.sources[role] = tracks
            self.tabs.addTab(tracks, label)
            for index, track in enumerate(data.tracks):
                if not track.notes:
                    continue
                item = QListWidgetItem(tr('{0} · {1} 个音符', track.name, len(track.notes)))
                item.setData(Qt.ItemDataRole.UserRole, index)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if index in defaults[role] else Qt.CheckState.Unchecked)
                tracks.addItem(item)

        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.meter = QCheckBox(tr('使用 MIDI 拍号'))
        self.meter.setEnabled(bool(data.meters))
        self.meter.setToolTip(tr('关闭时，插入的小节使用目标位置的拍号。'))
        layout.addWidget(self.meter)
        tempo = round(data.tempos[0][1]) if data.tempos else 120
        self.tempo = QCheckBox(tr('应用文件速度到整个工程：{0} BPM', tempo))
        layout.addWidget(self.tempo)
        info = QLabel(tr('MIDI 导入音高、起止和力度。工程音源保持原样。勾选速度时，首个 MIDI 速度应用到整个工程。'))
        info.setWordWrap(True)
        layout.addWidget(info)

        self.quant_grid = QComboBox()
        self.quant_grid.addItem(tr('保留原始时间'), 0)
        for label, ticks in [('1/4', 960), ('1/8', 480), ('1/16', 240), ('1/32', 120), ('1/64', 60),
                             ('1/8 T', 320), ('1/16 T', 160), ('1/32 T', 80), ('1/64 T', 40)]:
            self.quant_grid.addItem(label, ticks)
        self.quant_grid.setCurrentIndex(3)
        form.addRow(tr('导入量化格点'), self.quant_grid)
        self.protect_triplets = QCheckBox(tr('结合连续节奏识别三连音'))
        self.protect_triplets.setChecked(True)
        self.quant_grid.currentIndexChanged.connect(
            lambda index: self.protect_triplets.setEnabled(index in range(1, 6)))
        form.addRow(self.protect_triplets)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.confirm = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.confirm.setText(tr('插入'))
        self.confirm.setProperty('localizedLabel', '插入')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        for tracks in self.sources.values():
            tracks.itemChanged.connect(self.update_summary)
        self.update_summary()

    def mapping(self):
        return {role: [tracks.item(i).data(Qt.ItemDataRole.UserRole) for i in range(tracks.count())
                       if tracks.item(i).checkState() == Qt.CheckState.Checked]
                for role, tracks in self.sources.items()}

    def update_summary(self):
        counts = sum(len(self.data.tracks[i].notes) for tracks in self.mapping().values() for i in tracks)
        self.summary.setText(tr('选中 {0} 个音符用于插入。', counts))
        self.confirm.setEnabled(bool(counts))

    def value(self):
        return dict(bar_index=self.bar.value() - 1, mapping=self.mapping(), import_meter=self.meter.isChecked(),
                    import_tempo=self.tempo.isChecked(), quantization=dict(grid=self.quant_grid.currentData(),
                        protect_triplets=self.protect_triplets.isEnabled() and self.protect_triplets.isChecked()))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QListWidget,QListWidgetItem,QCheckBox,QDialogButtonBox,QComboBox,QHBoxLayout
from lingfeng.platform.i18n import tr
from lingfeng.music.model import PPQ


class MidiImportDialog(QDialog):
    def __init__(self,project,data,target,start,parent=None):
        super().__init__(parent);self.data=data;self.start=start
        self.setWindowTitle(tr('导入 MIDI 到旋律') if target=='melody' else tr('导入 MIDI 到和弦'));self.setMinimumWidth(460)
        box=QVBoxLayout(self);box.setSpacing(12)
        label=QLabel(tr('选择来源音轨。导入从当前播放游标开始，覆盖目标轨道的对应时间范围，可撤销。'));label.setWordWrap(True);box.addWidget(label)
        self.tracks=QListWidget();box.addWidget(self.tracks)
        usable=[i for i,t in enumerate(data.tracks) if t.notes]
        words=('melody','旋律') if target=='melody' else ('chord','harmony','和弦')
        preferred=[i for i in usable if any(word in data.tracks[i].name.lower() for word in words)] or usable[:1]
        for i in usable:
            track=data.tracks[i];item=QListWidgetItem(tr('{0} · {1} 个音符',track.name,len(track.notes)));item.setData(Qt.ItemDataRole.UserRole,i);item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable);item.setCheckState(Qt.CheckState.Checked if i in preferred else Qt.CheckState.Unchecked);self.tracks.addItem(item)
        self.summary=QLabel();self.summary.setWordWrap(True);box.addWidget(self.summary)
        self.meter=QCheckBox(tr('覆盖拍号（重建小节线，保留音符的绝对拍位置）'));self.meter.setEnabled(start in project.starts);box.addWidget(self.meter)
        self.meter.setToolTip(tr('覆盖拍号要求从小节开头导入；不勾选则保留现有拍号。'))
        tempo=round(data.tempos[0][1]) if data.tempos else 120
        self.tempo=QCheckBox(tr('覆盖工程速度：{0} BPM',tempo));box.addWidget(self.tempo)
        info=QLabel(tr('当前工程使用固定速度；导入速度取 MIDI 的首个速度，不导入后续速度变化。仅导入音高、起止和力度，保留工程歌词；音色和控制器保持工程设置。'));info.setWordWrap(True);box.addWidget(info)
        quant=QHBoxLayout();quant.addWidget(QLabel(tr('导入量化格点')))
        self.quant_grid=QComboBox()
        self.quant_grid.addItem(tr('保留原始时间'),0)
        for label,ticks in [('1/4',960),('1/8',480),('1/16',240),('1/32',120),('1/64',60),('1/8 T',320),('1/16 T',160),('1/32 T',80),('1/64 T',40)]:self.quant_grid.addItem(label,ticks)
        self.quant_grid.setCurrentIndex(3);quant.addWidget(self.quant_grid);box.addLayout(quant)
        self.protect_triplets=QCheckBox(tr('结合连续节奏识别三连音'));self.protect_triplets.setChecked(True);box.addWidget(self.protect_triplets)
        self.quant_grid.currentIndexChanged.connect(lambda:self.protect_triplets.setEnabled(self.quant_grid.currentIndex() in range(1,6)))
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr('确认覆盖并导入'));self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);box.addWidget(self.buttons)
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setProperty('localizedLabel','确认覆盖并导入')
        self.tracks.itemChanged.connect(self.update_summary);self.quant_grid.currentIndexChanged.connect(self.update_summary);self.protect_triplets.toggled.connect(self.update_summary);self.update_summary()

    def indices(self):return [self.tracks.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.tracks.count()) if self.tracks.item(i).checkState()==Qt.CheckState.Checked]

    def update_summary(self):
        from lingfeng.music.quantization import quantize_notes
        indices=self.indices();notes=quantize_notes(self.data.notes_for(indices),**self.quantization());end=self.start+max(self.data.end_for(indices),max((n.end for n in notes),default=0))
        self.summary.setText(tr('覆盖范围：第 {0:g} 拍至第 {1:g} 拍（末端不含），共 {2} 个音符。',self.start/PPQ+1,end/PPQ+1,len(self.data.notes_for(indices))))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(indices))

    def quantization(self):
        return dict(grid=self.quant_grid.currentData(),protect_triplets=self.protect_triplets.isEnabled() and self.protect_triplets.isChecked())

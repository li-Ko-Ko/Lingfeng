"""Format-specific export UI; PDF uses pages, audio/MIDI use musical ranges."""
import copy
import threading
from pathlib import Path
from PySide6.QtCore import QThread,Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QComboBox, QSpinBox, QLabel, QDialogButtonBox, QFileDialog, QProgressBar
from lingfeng.platform.i18n import tr
from lingfeng.audio.exporting import bounds, export_mp3

class AudioExportWorker(QThread):
    progress=Signal(int)
    def __init__(self,project,path,options,parent=None):
        super().__init__(parent);self.project=copy.deepcopy(project);self.path=path;self.options=options;self.cancel=threading.Event();self.error=None
    def run(self):
        try:export_mp3(self.project,self.path,cancel=self.cancel,progress=self.progress.emit,**self.options)
        except InterruptedError:self.error=tr('已取消导出')
        except Exception as exc:self.error=tr(str(exc))

class ExportDialog(QDialog):
    def __init__(self,owner,format,which='both'):
        super().__init__(owner);self.owner=owner;self.project=copy.deepcopy(owner.project);self.format=format;self.worker=None;self.closing=False
        if format=='pdf' and getattr(owner,'workspace',None)=='score' and owner.score_view.canvas.layout is not None:
            self.project=copy.deepcopy(owner.score_view.canvas.project)
        self.setWindowTitle(tr('导出 {0}',format.upper()));self.setMinimumWidth(480)
        box=QVBoxLayout(self);self.form=QFormLayout();box.addLayout(self.form)
        if format=='pdf':
            from lingfeng.engraving.notation import ScoreLayout
            pages=ScoreLayout(self.project).pages
            self.first=QSpinBox();self.first.setRange(1,pages)
            self.last=QSpinBox();self.last.setRange(1,pages);self.last.setValue(pages)
            self.form.addRow(tr('起始页'),self.first);self.form.addRow(tr('结束页'),self.last)
            self.info=QLabel(tr('按当前谱面分页导出，共 {0} 页。',pages))
            if getattr(owner,'workspace',None)=='score':self.info.setText(self.info.text()+'\n'+tr('音乐修改在重新切入制谱后同步。'))
        else:
            self.tracks=QComboBox()
            for label,value in [('旋律与和弦','both'),('仅旋律','melody'),('仅和弦','chords')]:self.tracks.addItem(tr(label),value)
            self.tracks.setCurrentIndex(self.tracks.findData(which));self.form.addRow(tr('导出内容'),self.tracks)
            self.range=QComboBox()
            for label,value in [('全部','all'),('按小节','bars'),('循环范围','loop')]:self.range.addItem(tr(label),value)
            self.range.model().item(2).setEnabled(owner.loop_range is not None)
            if self.project.sections():self.range.addItem(tr('按段落'),'section')
            self.form.addRow(tr('导出范围'),self.range)
            self.first=QSpinBox();self.first.setRange(1,len(self.project.measures))
            self.last=QSpinBox();self.last.setRange(1,len(self.project.measures));self.last.setValue(len(self.project.measures))
            self.form.addRow(tr('起始小节'),self.first);self.form.addRow(tr('结束小节'),self.last)
            self.section=QComboBox()
            for name,a,b in self.project.sections():self.section.addItem(f'{name} · {a+1}–{b}',(a,b))
            self.form.addRow(tr('段落'),self.section)
            self.info=QLabel()
            if format=='mp3':
                self.mode=QComboBox();self.mode.addItem(tr('所选合成音源 · 离线渲染'),'offline');self.mode.addItem(tr('Windows MIDI · 实时录制'),'windows');self.form.addRow(tr('音频方式'),self.mode)
                from lingfeng.audio.soundbanks import is_synth_source
                if all(not is_synth_source(self.project.audio[r]['device']) for r in ('melody','chords') if which in ('both',r)):self.mode.setCurrentIndex(1)
                self.mode.currentIndexChanged.connect(self.update_options)
                self.tracks.currentIndexChanged.connect(self.update_options)
                self.first.valueChanged.connect(self.update_options);self.last.valueChanged.connect(self.update_options)
                self.section.currentIndexChanged.connect(self.update_options)
            self.range.currentIndexChanged.connect(self.update_options)
        self.info.setWordWrap(True);box.addWidget(self.info)
        self.copyright=QLabel();self.copyright.setWordWrap(True);self.copyright.setVisible(format=='mp3');box.addWidget(self.copyright)
        self.progress=QProgressBar();self.progress.hide();box.addWidget(self.progress)
        self.status=QLabel();self.status.setWordWrap(True);box.addWidget(self.status)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel);box.addWidget(self.buttons)
        self.export_button=self.buttons.addButton(tr('导出…'),QDialogButtonBox.ButtonRole.AcceptRole)
        self.buttons.accepted.connect(self.export);self.buttons.rejected.connect(self.reject)
        self.update_options()

    def update_options(self):
        if self.format=='pdf':return
        kind=self.range.currentData()
        for field in (self.first,self.last):self.form.setRowVisible(field,kind=='bars')
        self.form.setRowVisible(self.section,kind=='section')
        if self.format=='mp3':
            self.info.setText(tr('实时录制默认 Windows MIDI 音源和系统输出，需要等待整段时长；同一输出设备上的其它声音也会录入。请先停止其它声音。') if self.mode.currentData()=='windows' else tr('使用工程所选的合成音源及预设离线渲染，与编辑试听一致。Windows MIDI 轨道请改用实时录制，或先在设置中选择合成音源。'))
            from lingfeng.audio.soundbanks import commercial_notice
            try:
                self.copyright.setText(commercial_notice(self.project,**self.options()))
                self.export_button.setEnabled(self.worker is None)
            except ValueError as exc:self.copyright.setText(str(exc));self.export_button.setEnabled(False)
        else:self.info.setText(tr('导出 Type 1 MIDI，所选范围从零开始；保留轨道音色、音量、速度、拍号与段落标识。'))

    def options(self):
        if self.format=='pdf':
            if self.first.value()>self.last.value():raise ValueError(tr('谱面页码范围无效。'))
            return dict(pages=range(self.first.value()-1,self.last.value()))
        start,end=bounds(self.project,self.range.currentData(),self.first.value(),self.last.value(),self.owner.loop_range,self.section.currentIndex())
        options=dict(which=self.tracks.currentData(),start=start,end=end)
        if self.format=='mp3':options['mode']=self.mode.currentData()
        return options

    def export(self):
        try:options=self.options()
        except ValueError as exc:self.status.setText(str(exc));return
        from lingfeng.platform.paths import safe_name
        suffix={'midi':'mid','mp3':'mp3','pdf':'pdf'}[self.format]
        path,_=QFileDialog.getSaveFileName(self,tr('导出 {0}',self.format.upper()),str(Path(self.owner.last_project_dir)/(safe_name(self.project.title)+'.'+suffix)),self.format.upper()+f' (*.{suffix})')
        if not path:return
        if Path(path).suffix.lower()!='.'+suffix:path+='.'+suffix
        self.output_path=path
        if self.format=='mp3':
            self.worker=AudioExportWorker(self.project,path,options,self);self.worker.progress.connect(self.progress.setValue);self.worker.finished.connect(self.finished_audio)
            self.export_button.setEnabled(False);self.progress.setValue(0);self.progress.show();self.status.setText(tr('正在导出…'));self.worker.start();return
        try:
            if self.format=='pdf':
                from lingfeng.engraving.notation import export_pdf
                export_pdf(self.project,path,**options)
            else:
                from lingfeng.audio.midi import export_midi
                export_midi(self.project,path,**options)
            self.status.setText(tr('已导出：{0}',path))
        except Exception as exc:self.status.setText(tr('导出失败：{0}',tr(str(exc))))

    def finished_audio(self):
        worker=self.worker;self.worker=None;self.export_button.setEnabled(True)
        self.status.setText(tr('导出失败：{0}',worker.error) if worker.error else tr('已导出：{0}\n音源许可说明：{0}.licenses.txt',self.output_path));worker.deleteLater()
        if self.closing:super().reject()

    def reject(self):
        if self.worker and self.worker.isRunning():self.closing=True;self.worker.cancel.set();self.status.setText(tr('正在取消…'));return
        super().reject()

    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():event.ignore();self.reject();return
        super().closeEvent(event)

"""Format-specific export UI. PDF uses pages and other formats use musical ranges."""
import copy
import threading
from pathlib import Path
from PySide6.QtCore import QThread,Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QComboBox, QSpinBox, QLabel, QDialogButtonBox, QFileDialog, QProgressBar
from lingfeng.platform.i18n import tr
from lingfeng.ui.track_picker import TrackPicker
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
        self.setWindowTitle(tr('导出 {0}','MusicXML' if format=='musicxml' else format.upper()));self.setMinimumWidth(480)
        box=QVBoxLayout(self);self.form=QFormLayout();box.addLayout(self.form)
        self.tracks=TrackPicker(self.project,which)
        if format=='pdf' and which=='both':
            for role,check in self.tracks.checks.items():
                check.setChecked(self.project.notation.get('show_'+role,True))
        self.form.addRow(tr('导出内容'),self.tracks)
        if format=='pdf':
            from lingfeng.engraving.notation import ScoreLayout
            from lingfeng.engraving.compatibility import melody_overlap
            self.unsupported_traditional=(self.project.notation['style']=='traditional'
                and melody_overlap(self.project,{'show_melody':'melody' in self.tracks.roles(),
                                                 'show_instrument':'instrument' in self.tracks.roles()}))
            pages=1 if self.unsupported_traditional else ScoreLayout(self.project).pages
            self.first=QSpinBox();self.first.setRange(1,pages)
            self.last=QSpinBox();self.last.setRange(1,pages);self.last.setValue(pages)
            self.form.addRow(tr('起始页'),self.first);self.form.addRow(tr('结束页'),self.last)
            self.info=QLabel(tr('按当前谱面分页导出，共 {0} 页。',pages))
            if getattr(owner,'workspace',None)=='score':self.info.setText(self.info.text()+'\n'+tr('音乐修改在重新切入制谱后同步。'))
        else:
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
                from lingfeng.audio.midi import export_tracks
                from lingfeng.audio.soundbanks import is_synth_source
                if all(not is_synth_source(self.project.audio_for(role)['device'])
                       for _,role,_ in export_tracks(self.project,which)):self.mode.setCurrentIndex(1)
                self.mode.currentIndexChanged.connect(self.update_options)
                self.first.valueChanged.connect(self.update_options);self.last.valueChanged.connect(self.update_options)
                self.section.currentIndexChanged.connect(self.update_options)
            self.range.currentIndexChanged.connect(self.update_options)
        self.info.setWordWrap(True);box.addWidget(self.info)
        self.copyright=QLabel();self.copyright.setWordWrap(True);self.copyright.setVisible(format=='mp3');box.addWidget(self.copyright)
        self.progress=QProgressBar();self.progress.hide();box.addWidget(self.progress)
        self.status=QLabel();self.status.setWordWrap(True);box.addWidget(self.status)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel);box.addWidget(self.buttons)
        self.export_button=self.buttons.addButton(tr('导出…'),QDialogButtonBox.ButtonRole.AcceptRole)
        if format=='pdf' and self.unsupported_traditional:
            self.info.setText(tr('传统简谱仅支持单声部旋律，请使用立体简谱或立体简谱 · 紧凑。'))
            self.first.setEnabled(False);self.last.setEnabled(False);self.export_button.setEnabled(False)
        self.buttons.accepted.connect(self.export);self.buttons.rejected.connect(self.reject)
        self.tracks.changed.connect(self.update_options)
        self.update_options()

    def update_options(self):
        roles=self.tracks.roles()
        self.export_button.setEnabled(bool(roles) and self.worker is None)
        if self.format=='pdf':
            from lingfeng.engraving.notation import ScoreLayout
            from lingfeng.engraving.compatibility import melody_overlap
            for role in self.tracks.checks:
                self.project.notation['show_'+role]=role in roles
            self.unsupported_traditional=self.project.notation['style']=='traditional' and melody_overlap(self.project)
            pages=1 if self.unsupported_traditional else ScoreLayout(self.project).pages
            all_pages=self.last.value()==self.last.maximum()
            self.first.setMaximum(pages);self.last.setMaximum(pages)
            if all_pages:self.last.setValue(pages)
            self.first.setEnabled(not self.unsupported_traditional);self.last.setEnabled(not self.unsupported_traditional)
            self.export_button.setEnabled(bool(roles) and not self.unsupported_traditional)
            self.info.setText(tr('传统简谱仅支持单声部旋律，请使用立体简谱或立体简谱 · 紧凑。')
                              if self.unsupported_traditional else tr('按当前谱面分页导出，共 {0} 页。',pages))
            return
        kind=self.range.currentData()
        for field in (self.first,self.last):self.form.setRowVisible(field,kind=='bars')
        self.form.setRowVisible(self.section,kind=='section')
        if self.format=='mp3' and roles:
            self.info.setText(tr('实时录制默认 Windows MIDI 音源和系统输出，需要等待整段时长；同一输出设备上的其它声音也会录入。请先停止其它声音。') if self.mode.currentData()=='windows' else tr('使用工程所选的合成音源及预设离线渲染，与编辑试听一致。Windows MIDI 轨道请改用实时录制，或先在设置中选择合成音源。'))
            from lingfeng.audio.soundbanks import commercial_notice
            try:
                self.copyright.setText(commercial_notice(self.project,**self.options()))
                self.export_button.setEnabled(self.worker is None)
            except ValueError as exc:self.copyright.setText(str(exc));self.export_button.setEnabled(False)
        elif self.format=='musicxml':
            self.info.setText(tr('导出 MusicXML 乐谱，可选择普通 .musicxml 或压缩 .mxl。'))
        else:self.info.setText(tr('导出 Type 1 MIDI，所选范围从零开始；保留轨道音色、音量、速度、拍号与段落标识。'))

    def options(self):
        if not self.tracks.roles():raise ValueError(tr('请选择至少一个导出轨道。'))
        if self.format=='pdf':
            if self.unsupported_traditional:raise ValueError(tr('传统简谱仅支持单声部旋律，请使用立体简谱或立体简谱 · 紧凑。'))
            if self.first.value()>self.last.value():raise ValueError(tr('谱面页码范围无效。'))
            return dict(pages=range(self.first.value()-1,self.last.value()))
        start,end=bounds(self.project,self.range.currentData(),self.first.value(),self.last.value(),self.owner.loop_range,self.section.currentIndex())
        options=dict(which=self.tracks.roles(),start=start,end=end)
        if self.format=='mp3':options['mode']=self.mode.currentData()
        return options

    def export(self):
        try:options=self.options()
        except ValueError as exc:self.status.setText(str(exc));return
        from lingfeng.platform.paths import safe_name
        suffix={'midi':'mid','mp3':'mp3','pdf':'pdf','musicxml':'musicxml'}[self.format]
        label='MusicXML' if self.format=='musicxml' else self.format.upper()
        filters=label+f' (*.{suffix})'
        compressed=tr('压缩 MusicXML (*.mxl)')
        if self.format=='musicxml':filters+=';;'+compressed
        path,selected_filter=QFileDialog.getSaveFileName(self,tr('导出 {0}',label),str(Path(self.owner.last_project_dir)/(safe_name(self.project.title)+'.'+suffix)),filters)
        if not path:return
        existing_suffix=Path(path).suffix.lower()
        if self.format=='musicxml':
            if selected_filter==compressed and existing_suffix=='.musicxml':path=str(Path(path).with_suffix('.mxl'))
            elif existing_suffix not in ('.musicxml','.xml','.mxl'):path+=('.mxl' if selected_filter==compressed else '.musicxml')
        elif existing_suffix!='.'+suffix:path+='.'+suffix
        self.output_path=path
        if self.format=='mp3':
            self.worker=AudioExportWorker(self.project,path,options,self);self.worker.progress.connect(self.progress.setValue);self.worker.finished.connect(self.finished_audio)
            self.export_button.setEnabled(False);self.progress.setValue(0);self.progress.show();self.status.setText(tr('正在导出…'));self.worker.start();return
        try:
            if self.format=='pdf':
                from lingfeng.engraving.notation import export_pdf
                export_pdf(self.project,path,**options)
            elif self.format=='musicxml':
                from lingfeng.music.musicxml_export import export_musicxml
                export_musicxml(self.project,path,**options)
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

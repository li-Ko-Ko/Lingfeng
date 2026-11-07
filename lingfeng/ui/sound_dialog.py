"""Sound sources, presets and explicit persistent folder scanning."""
from pathlib import Path
from PySide6.QtCore import QTimer,QUrl,Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog,QFormLayout,QComboBox,QLabel,QPushButton,QDialogButtonBox,QPlainTextEdit,QFileDialog,QMessageBox,QHBoxLayout,QTabWidget,QWidget,QDoubleSpinBox
from lingfeng.audio.events import AUDITION_CHANNELS, MAX_SOURCE_GAIN_DB, MIN_SOURCE_GAIN_DB, TRACK_ROLES, complete_track_values, source_gain_db
from lingfeng.music.model import MELODY_NAMES
from lingfeng.platform.i18n import tr
import lingfeng.audio.soundbanks as banks

class SoundSettingsDialog(QDialog):
    def __init__(self,settings,parent=None):
        super().__init__(parent);self.setWindowTitle(tr('音源与音色'));self.setMinimumWidth(540)
        self.fields={};self.gain_fields={};self.calibration_labels={};self.preview_buttons={};self.preview_router=None;self.settings=complete_track_values(settings)
        self.preview_timer=QTimer(self);self.preview_timer.setSingleShot(True);self.preview_timer.timeout.connect(self.stop_preview)
        form=QFormLayout(self);form.setSpacing(12)
        path=QLabel(str(banks.default_root()));path.setWordWrap(True);path.setTextInteractionFlags(path.textInteractionFlags()|Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow(tr('默认音源目录'),path)
        buttons=QHBoxLayout();open_button=QPushButton(tr('打开音源目录'));open_button.clicked.connect(self.open_directory);buttons.addWidget(open_button)
        add_button=QPushButton(tr('添加扫描目录…'));add_button.clicked.connect(self.add_directory);buttons.addWidget(add_button)
        self.scan_button=QPushButton(tr('重新扫描并保存'));self.scan_button.clicked.connect(self.scan);buttons.addWidget(self.scan_button);form.addRow(buttons)
        self.library_button=QPushButton(tr('下载／添加音源…'));self.library_button.clicked.connect(self.open_library);form.addRow(self.library_button)
        self.directories=QPlainTextEdit();self.directories.setMaximumHeight(65)
        self.directories.setPlaceholderText(tr('额外扫描目录，每行一个；可填音源包文件夹或其上级目录。'))
        self.directories.setPlainText('\n'.join(p for p in banks.registry()['roots'] if Path(p)!=banks.default_root()))
        form.addRow(tr('额外目录'),self.directories)
        self.track_tabs=QTabWidget();form.addRow(self.track_tabs)
        self.track_tabs.currentChanged.connect(self.stop_preview)
        project=getattr(parent,'project',None)
        melody_labels=[project.melody_name(track) if project else tr(name) for track,name in enumerate(MELODY_NAMES)]
        for key,label in (('melody',melody_labels[0]),('instrument',melody_labels[1]),('chords',tr('和弦轨'))):
            page=QWidget();track_form=QFormLayout(page)
            device=QComboBox();program=QComboBox();self.fields[key]=(device,program)
            device.currentIndexChanged.connect(lambda index,k=key:self.populate(k));device.currentIndexChanged.connect(self.stop_preview)
            program.currentIndexChanged.connect(self.stop_preview)
            track_form.addRow(tr('音源'),device);track_form.addRow(tr('音色'),program)
            calibration=QLabel('—');self.calibration_labels[key]=calibration
            calibration.setToolTip(tr('按音色测得的自动响度补偿，叠加在下方的轨道音源增益上。'))
            track_form.addRow(tr('预设响度补偿'),calibration)
            program.currentIndexChanged.connect(lambda index,k=key:self.update_calibration(k))
            gain=QDoubleSpinBox();self.gain_fields[key]=gain
            gain.setDecimals(1);gain.setRange(MIN_SOURCE_GAIN_DB,MAX_SOURCE_GAIN_DB);gain.setSingleStep(.5);gain.setSuffix(' dB')
            gain.setKeyboardTracking(False)
            gain.setToolTip(tr('调节合成音源的输出电平，独立于轨道音量（CC7）。适用于播放、试听和离线 MP3 导出。'))
            gain.valueChanged.connect(self.stop_preview);track_form.addRow(tr('音源增益'),gain)
            preview=QPushButton(tr('试听音色'));preview.clicked.connect(lambda checked=False,k=key:self.preview(k));track_form.addRow(preview);self.preview_buttons[key]=preview
            self.track_tabs.addTab(page,label)
        info=QLabel(tr('将完整音源文件夹复制到 synths 后点击重新扫描。扫描结果自动保存，下次启动直接读取。新音源需兼容伶风音源包格式；只复制 VST 插件不能加载。'))
        info.setWordWrap(True);form.addRow(info)
        self.notice=QLabel();self.notice.setWordWrap(True);form.addRow(self.notice)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject);form.addRow(self.buttons)
        self.reload(self.settings)

    def reload(self,settings):
        from lingfeng.audio.routing import midi_devices
        devices=midi_devices();packs=banks.installed_packs();missing=[]
        for key,(device,program) in self.fields.items():
            spec=settings[key];wanted=spec['device']
            if wanted in ('samples','builtin'):wanted=banks.DEFAULT_DEVICE
            device.blockSignals(True);device.clear()
            for item in packs:device.addItem(banks.pack_label(item),'synth:'+item['id'])
            if devices:device.addItem(tr('Windows 默认兼容音源'),'default')
            for _,name in devices:device.addItem(name,name)
            index=device.findData(wanted)
            if index<0:missing.append(str(wanted))
            device.setCurrentIndex(max(0,index));device.blockSignals(False);self.populate(key,spec['program'])
            self.gain_fields[key].setValue(source_gain_db(spec) if index>=0 and banks.is_synth_source(wanted) else 0)
            if program.findData(spec['program'])<0:missing.append(str(wanted)+' / '+str(spec['program']+1))
        lines=[tr('已缓存 {0} 个合成音源包、{1} 个预设。',len(packs),sum(len(p['presets']) for p in packs))]
        if missing:lines.append(tr('以下音源或音色不可用：{0}。确认后使用当前所选项。','、'.join(missing)))
        errors=banks.registry().get('errors',[])
        if errors:lines.append(tr('部分音源未加载：{0}','\n'.join(errors[:3])))
        self.notice.setText('\n'.join(lines));self.notice.setToolTip('\n'.join(errors));self.update_enabled()

    def populate(self,key,initial=None):
        device,combo=self.fields[key];previous=combo.currentData() if initial is None else initial;combo.clear()
        selected=device.currentData();is_synth=banks.is_synth_source(selected);gain=self.gain_fields[key]
        gain.setEnabled(is_synth)
        if is_synth:
            from lingfeng.platform.i18n import LANGUAGE
            p=banks.pack(selected)
            for item in p['presets']:
                number=item['program'];name=item['name_en' if LANGUAGE=='en' else 'name']
                combo.addItem(f'{number+1:02} · '+name,number)
                combo.setItemData(combo.count()-1,p['author']+' · '+p['license'],3)
        else:
            gain.setValue(0)
            if selected is not None:
                from lingfeng.audio.gm_instruments import label
                for number in range(128):combo.addItem(label(number),number)
        combo.setCurrentIndex(max(0,combo.findData(previous)));self.update_calibration(key);self.update_enabled()

    def update_calibration(self,key):
        device,program=self.fields[key];source=device.currentData();number=program.currentData()
        db=banks.preset_calibration_db(number,source) if banks.is_synth_source(source) and number is not None else None
        label='—'
        if db is not None:label=f'{db:+.1f} dB' if db else '0.0 dB'
        self.calibration_labels[key].setText(label)

    def update_enabled(self):
        for key,button in self.preview_buttons.items():button.setEnabled(self.fields[key][1].currentData() is not None)
        if hasattr(self,'buttons'):self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(all(p.currentData() is not None for d,p in self.fields.values()))

    def open_directory(self):
        try:banks.default_root().mkdir(parents=True,exist_ok=True);QDesktopServices.openUrl(QUrl.fromLocalFile(str(banks.default_root())))
        except OSError as exc:QMessageBox.warning(self,tr('音源与音色'),str(exc))

    def add_directory(self):
        folder=QFileDialog.getExistingDirectory(self,tr('选择音源目录'),str(banks.default_root()))
        if folder:
            current=self.directories.toPlainText().splitlines()
            if folder not in current:self.directories.setPlainText('\n'.join([*current,folder]).strip())

    def scan(self):
        self.stop_preview();settings=self.value()
        # Keep preferences if a previous scan found no devices.
        settings={k:v if v['program'] is not None else self.settings[k] for k,v in settings.items()}
        try:
            transport=getattr(self.parent(),'transport',None)
            if transport:transport.close()
            banks.rescan([p.strip() for p in self.directories.toPlainText().splitlines() if p.strip()])
            self.reload(settings)
        except (OSError,ValueError) as exc:QMessageBox.warning(self,tr('音源扫描失败'),str(exc))

    def open_library(self):
        from lingfeng.ui.sound_library import SoundLibraryDialog
        self.stop_preview()
        transport=getattr(self.parent(),'transport',None)
        if transport:transport.close()
        dialog=SoundLibraryDialog(self);dialog.installed.connect(lambda path:self.scan());dialog.exec()

    def value(self):
        settings={}
        for key,(device,program) in self.fields.items():
            selected=device.currentData();gain=self.gain_fields[key].value()
            spec=dict(device=selected,program=program.currentData())
            if gain and banks.is_synth_source(selected):spec['gain_db']=gain
            settings[key]=spec
        return settings

    def accept(self):
        try:banks.save_defaults(self.value())
        except OSError as exc:QMessageBox.warning(self,tr('无法保存音源设置'),str(exc));return
        super().accept()

    def stop_preview(self,*args):
        self.preview_timer.stop()
        if self.preview_router:self.preview_router.close();self.preview_router=None

    def preview(self,key):
        from lingfeng.audio.routing import MidiRouter
        from lingfeng.ui.audio_loading import AudioLoadingDialog,AudioLoadCancelled
        self.stop_preview()
        try:
            # WinMM GS allows one owner. Stopped playback can still hold its
            # handle; give the modal audition exclusive use until it closes.
            transport=getattr(self.parent(),'transport',None)
            if transport:transport.close()
            spec=self.value()[key];settings={role:dict(spec) for role in TRACK_ROLES}
            if banks.is_synth_source(spec['device']) and banks.pack(spec['device']).get('engine') in ('sfz','sf2'):
                self.preview_router=AudioLoadingDialog.open_router(settings,self)
            else:self.preview_router=MidiRouter(settings)
            for pitch in ((36,40,43) if spec['program'] in (32,33,43) else (60,64,67)):
                self.preview_router.send(0x90|AUDITION_CHANNELS[key],pitch,75)
            self.preview_timer.start(700)
        except AudioLoadCancelled:self.stop_preview()
        except Exception as exc:self.stop_preview();QMessageBox.warning(self,tr('音源与音色'),str(exc))

    def done(self,result):self.stop_preview();super().done(result)

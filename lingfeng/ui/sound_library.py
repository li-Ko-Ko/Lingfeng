"""Optional sound-pack downloads and local installation without blocking Qt."""
import threading
from pathlib import Path
from PySide6.QtCore import QThread,Signal,QUrl,Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QComboBox,QLabel,
    QPushButton,QDialogButtonBox,QFileDialog,QProgressBar,QHBoxLayout)
from lingfeng.platform import i18n
from lingfeng.platform.i18n import tr
from lingfeng.audio import soundbanks as banks
from lingfeng.audio.pack_install import install_archive,install_download,InstallCancelled
from lingfeng.audio.piano_catalog import DOWNLOADS


def size_label(count):
    return f'{count/1024**2:.1f} MiB' if count>=1024**2 else f'{count/1024:.1f} KiB'


class SoundInstallWorker(QThread):
    progress=Signal(int,int)

    def __init__(self,source,download=False,parent=None):
        super().__init__(parent)
        self.source=source;self.download=download;self.cancel=threading.Event()
        self.path=None;self.error=None;self.cancelled=False

    def run(self):
        try:
            install=install_download if self.download else install_archive
            self.path=install(self.source,cancel=self.cancel,progress=self.progress.emit)
        except InstallCancelled:self.cancelled=True
        except Exception as exc:self.error=exc


class SoundLibraryDialog(QDialog):
    installed=Signal(str)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('下载／添加音源'));self.setMinimumWidth(560)
        self.worker=None;self.closing=False;self.entries=tuple(DOWNLOADS)
        box=QVBoxLayout(self);box.setSpacing(12)
        introduction=QLabel(tr('大音源可按需下载，也可添加已下载的完整伶风音源 ZIP 包。'))
        introduction.setWordWrap(True);box.addWidget(introduction)
        form=QFormLayout();box.addLayout(form)
        self.choice=QComboBox();self.choice.currentIndexChanged.connect(self.show_entry)
        form.addRow(tr('可下载音源'),self.choice)
        self.description=QLabel();self.description.setWordWrap(True);self.description.setTextFormat(Qt.TextFormat.PlainText)
        form.addRow(self.description)
        self.size=QLabel();form.addRow(tr('下载大小'),self.size)
        self.license=QLabel();self.license.setWordWrap(True);self.license.setTextFormat(Qt.TextFormat.PlainText)
        form.addRow(tr('许可证'),self.license)
        self.source_button=QPushButton(tr('查看音源来源'));self.source_button.clicked.connect(self.open_source)
        form.addRow(self.source_button)
        self.download_button=QPushButton(tr('下载并添加'));self.download_button.clicked.connect(self.download)
        self.local_button=QPushButton(tr('从本地 ZIP 添加…'));self.local_button.clicked.connect(self.add_local)
        actions=QHBoxLayout();actions.addWidget(self.download_button);actions.addWidget(self.local_button);box.addLayout(actions)
        location=QLabel(tr('安装目录：{0}',banks.default_root()));location.setWordWrap(True)
        location.setTextFormat(Qt.TextFormat.PlainText);location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(location)
        self.progress=QProgressBar();self.progress.hide();box.addWidget(self.progress)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setTextFormat(Qt.TextFormat.PlainText);box.addWidget(self.status)
        self.buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setText(tr('关闭'))
        self.buttons.rejected.connect(self.reject)
        self.cancel_button=self.buttons.addButton(tr('取消'),QDialogButtonBox.ButtonRole.ActionRole)
        self.cancel_button.clicked.connect(self.cancel_install);self.cancel_button.hide();box.addWidget(self.buttons)
        self.refresh_entries()

    def entry(self):
        index=self.choice.currentIndex()
        return self.entries[index] if 0<=index<len(self.entries) else None

    @staticmethod
    def localized(entry,key):
        return entry.get(key+'_en',entry.get(key,'')) if i18n.LANGUAGE=='en' else entry.get(key,'')

    def refresh_entries(self):
        selected=self.choice.currentData();installed={p['id'] for p in banks.installed_packs()}
        self.choice.blockSignals(True);self.choice.clear()
        first_available=-1
        for index,entry in enumerate(self.entries):
            exists=entry['id'] in installed or (banks.default_root()/entry['id']).exists()
            name=self.localized(entry,'name')
            self.choice.addItem(tr('{0}（已安装）',name) if exists else name,entry['id'])
            self.choice.model().item(index).setEnabled(not exists)
            if not exists and first_available<0:first_available=index
        index=self.choice.findData(selected)
        if index<0 or not self.choice.model().item(index).isEnabled():index=first_available
        if index<0 and self.entries:index=0
        self.choice.setCurrentIndex(index);self.choice.blockSignals(False);self.show_entry()

    def show_entry(self,*args):
        entry=self.entry();busy=self.worker is not None
        self.description.setText(self.localized(entry,'description') if entry else tr('当前没有可下载的音源，可从本地 ZIP 添加。'))
        self.size.setText(size_label(entry.get('archive_bytes',0)) if entry else '—')
        self.license.setText(entry.get('license',entry.get('manifest',{}).get('license','')) if entry else '—')
        self.source_button.setEnabled(bool(self.source_url()) and not busy)
        available=entry is not None and self.choice.model().item(self.choice.currentIndex()).isEnabled()
        self.download_button.setEnabled(available and not busy)

    def source_url(self):
        entry=self.entry()
        if not entry:return ''
        url=entry.get('source_url') or entry.get('source') or entry.get('manifest',{}).get('source') or entry.get('url','')
        return url if QUrl(url).scheme() in ('https','http') else ''

    def open_source(self):
        if self.source_url():QDesktopServices.openUrl(QUrl(self.source_url()))

    def add_local(self):
        if self.worker is not None:return
        filename,_=QFileDialog.getOpenFileName(self,tr('选择音源 ZIP 包'),'',tr('ZIP 音源包 (*.zip)'))
        if filename:self.start_install(Path(filename))

    def download(self):
        if self.worker is None and self.download_button.isEnabled():self.start_install(dict(self.entry()),True)

    def start_install(self,source,download=False):
        if self.worker is not None:return
        self.closing=False;self.worker=SoundInstallWorker(source,download,self)
        self.worker.progress.connect(self.update_progress);self.worker.finished.connect(self.finished_install)
        self.choice.setEnabled(False);self.local_button.setEnabled(False)
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setEnabled(False)
        self.cancel_button.setEnabled(True);self.cancel_button.show();self.show_entry()
        self.progress.setRange(0,0);self.progress.show()
        self.status.setText(tr('正在下载音源…') if download else tr('正在添加音源…'))
        self.worker.start()

    def update_progress(self,done,total):
        if self.worker is None or self.worker.cancel.is_set():return
        if total>0:
            self.progress.setRange(0,1000);self.progress.setValue(min(1000,done*1000//total))
            self.status.setText(tr('正在下载：{0} / {1}',size_label(done),size_label(total)))
        else:
            self.progress.setRange(0,0);self.status.setText(tr('正在添加音源…'))

    def cancel_install(self):
        if self.worker is None:return
        self.worker.cancel.set();self.cancel_button.setEnabled(False);self.status.setText(tr('正在取消…'))

    def finished_install(self):
        worker=self.worker
        if worker is None:return
        worker.wait();self.worker=None
        self.choice.setEnabled(True);self.local_button.setEnabled(True)
        self.buttons.button(QDialogButtonBox.StandardButton.Close).setEnabled(True)
        self.cancel_button.hide();self.progress.hide()
        if worker.cancelled:self.status.setText(tr('已取消添加音源。'))
        elif worker.error:
            if isinstance(worker.error,PermissionError):
                self.status.setText(tr('无法写入音源目录：{0}\n请将伶风放到可写目录，或检查文件夹权限。',banks.default_root()))
            else:self.status.setText(tr('添加音源失败：{0}',str(worker.error)))
        else:
            self.status.setText(tr('音源已添加：{0}',worker.path));self.installed.emit(str(worker.path))
        worker.deleteLater();self.refresh_entries()
        if self.closing:super().reject()

    def reject(self):
        if self.worker is not None:
            self.closing=True;self.cancel_install();return
        super().reject()

    def closeEvent(self,event):
        if self.worker is not None:event.ignore();self.reject();return
        super().closeEvent(event)

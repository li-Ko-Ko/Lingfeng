"""Keep the GUI responsive while opening a sampled playback process."""
import copy
import threading
import time

from PySide6.QtCore import QThread,QTimer,Qt
from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout,QLabel,QProgressBar,QPushButton
from lingfeng.platform.i18n import tr
from lingfeng.audio.playback import ProcessRouter


class AudioLoadCancelled(RuntimeError):
    pass


class RouterLoader(QThread):
    def __init__(self,settings,parent=None):
        super().__init__(parent)
        self.settings=copy.deepcopy(settings);self.cancel=threading.Event()
        self.router=None;self.error=None;self.close_only=False

    def run(self):
        try:
            if self.close_only:
                try:self.router.close()
                finally:self.router=None
                return
            self.router=ProcessRouter(self.settings,cancel=self.cancel)
            if self.cancel.is_set():
                self.router.close();self.router=None
        except Exception as exc:self.error=exc


class AudioLoadingDialog(QDialog):
    def __init__(self,settings,parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('正在加载音源'));self.setMinimumWidth(420)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        layout=QVBoxLayout(self);layout.setSpacing(14)
        self.message=QLabel(tr('正在准备播放与试听。大型音源首次加载需要一些时间。'))
        self.message.setWordWrap(True);layout.addWidget(self.message)
        self.progress=QProgressBar();self.progress.setRange(0,0);layout.addWidget(self.progress)
        self.elapsed=QLabel();layout.addWidget(self.elapsed)
        self.cancel_button=QPushButton(tr('取消'));self.cancel_button.clicked.connect(self.reject)
        layout.addWidget(self.cancel_button)
        self.worker=RouterLoader(settings,self);self.worker.finished.connect(self.loaded)
        self.timer=QTimer(self);self.timer.setInterval(100);self.timer.timeout.connect(self.update_elapsed)
        self.started=0;self.complete=False

    def update_elapsed(self):
        self.elapsed.setText(tr('已等待 {0} 秒',int(time.monotonic()-self.started)))

    def loaded(self):
        self.worker.wait()
        if self.worker.cancel.is_set() and self.worker.router is not None:
            # Cancellation may arrive after run()'s final check but before this
            # queued slot. Process joins still belong on the worker thread.
            self.worker.close_only=True;self.worker.start();return
        self.complete=True;self.timer.stop()
        self.done(QDialog.DialogCode.Accepted if self.worker.router is not None else QDialog.DialogCode.Rejected)

    def reject(self):
        if not self.complete:
            self.worker.cancel.set();self.cancel_button.setEnabled(False)
            self.message.setText(tr('正在取消音源加载…'));return
        super().reject()

    def closeEvent(self,event):
        if not self.complete:event.ignore();self.reject();return
        super().closeEvent(event)

    @classmethod
    def open_router(cls,settings,parent=None):
        previous_window=QApplication.activeWindow();previous_focus=QApplication.focusWidget()
        if previous_window is None and previous_focus is not None:previous_window=previous_focus.window()
        if previous_window is None and parent is not None:previous_window=parent.window()
        dialog=cls(settings,parent);dialog.started=time.monotonic()
        dialog.update_elapsed();dialog.timer.start();dialog.worker.start()
        dialog.exec()
        try:
            if dialog.worker.cancel.is_set():raise AudioLoadCancelled(tr('音源加载已取消。'))
            if dialog.worker.error is not None:raise dialog.worker.error
            if dialog.worker.router is None:raise RuntimeError(tr('音频输出进程已停止。'))
            return dialog.worker.router
        finally:
            dialog.hide();dialog.setWindowModality(Qt.WindowModality.NonModal)
            # Auditions can open this dialog during a piano-roll key press.
            # Restore the editor so the following key/release stays in its lane.
            try:
                if previous_window is not None and previous_window.isVisible():
                    previous_window.raise_();previous_window.activateWindow()
                    QApplication.setActiveWindow(previous_window)
                    if previous_focus is not None and previous_focus.isVisible():
                        previous_focus.setFocus(Qt.FocusReason.OtherFocusReason)
            except RuntimeError:pass  # An application shutdown may delete it.
            dialog.deleteLater()

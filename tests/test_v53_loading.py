"""Sound initialization must paint, cancel and clean up without blocking Qt."""
import os
import threading
import time
import unittest
from unittest.mock import patch,MagicMock

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QTimer,QEventLoop
from PySide6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLineEdit
from lingfeng.ui.audio_loading import AudioLoadingDialog,AudioLoadCancelled
from lingfeng.audio.transport import Transport

APP=QApplication.instance() or QApplication([])
SETTINGS={role:dict(device='synth:piano-grand',program=0) for role in ('melody','chords')}


class LoadingTests(unittest.TestCase):
    def test_late_cancel_cleanup_stays_off_the_gui_thread(self):
        dialog=AudioLoadingDialog(SETTINGS);router=MagicMock()
        router.close.side_effect=lambda:time.sleep(.18)
        dialog.worker.router=router;dialog.worker.cancel.set();dialog.show()
        ticks=[];timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(True));timer.start()
        loop=QEventLoop();dialog.finished.connect(loop.quit);QTimer.singleShot(1500,loop.quit)
        start=time.monotonic();dialog.loaded()
        self.assertLess(time.monotonic()-start,.1)
        loop.exec();timer.stop()
        self.assertTrue(dialog.complete);self.assertIsNone(dialog.worker.router)
        self.assertGreaterEqual(len(ticks),3);router.close.assert_called_once()
        dialog.deleteLater();APP.processEvents()

    def test_loading_restores_editor_window_and_text_focus(self):
        window=QWidget();layout=QVBoxLayout(window);field=QLineEdit();layout.addWidget(field)
        window.show();window.activateWindow();QApplication.setActiveWindow(window);field.setFocus();APP.processEvents()
        router=MagicMock()
        try:
            with patch('lingfeng.ui.audio_loading.ProcessRouter',return_value=router):
                self.assertIs(AudioLoadingDialog.open_router(SETTINGS,window),router)
            self.assertIs(APP.activeWindow(),window);self.assertIs(APP.focusWidget(),field)
        finally:window.close();window.deleteLater();APP.processEvents()

    def test_waiting_gui_keeps_processing_events_and_returns_open_router(self):
        router=MagicMock();release=threading.Event();ticks=[]
        timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(time.monotonic()));timer.start()
        def factory(settings,cancel):
            while not release.wait(.01):
                if cancel.is_set():raise RuntimeError('cancelled')
            return router
        QTimer.singleShot(150,release.set)
        try:
            with patch('lingfeng.ui.audio_loading.ProcessRouter',side_effect=factory):
                actual=AudioLoadingDialog.open_router(SETTINGS)
        finally:timer.stop()
        self.assertIs(actual,router);self.assertGreaterEqual(len(ticks),3)
        router.close.assert_not_called()

    def test_escape_cancel_reaches_loader_and_returns_no_live_router(self):
        received=[]
        def factory(settings,cancel):
            self.assertTrue(cancel.wait(2));received.append(True)
            raise RuntimeError('cancelled by caller')
        def cancel_dialog():
            dialogs=[w for w in APP.topLevelWidgets() if isinstance(w,AudioLoadingDialog) and w.isVisible()]
            self.assertTrue(dialogs);dialogs[-1].reject()
        QTimer.singleShot(80,cancel_dialog)
        with patch('lingfeng.ui.audio_loading.ProcessRouter',side_effect=factory):
            with self.assertRaises(AudioLoadCancelled):AudioLoadingDialog.open_router(SETTINGS)
        self.assertEqual(received,[True])
        APP.processEvents()

    def test_close_during_load_waits_for_cleanup(self):
        router=MagicMock();started=threading.Event()
        def factory(settings,cancel):
            started.set();cancel.wait(2);return router
        def close_dialog():
            for widget in APP.topLevelWidgets():
                if isinstance(widget,AudioLoadingDialog) and widget.isVisible():widget.close()
        QTimer.singleShot(80,close_dialog)
        with patch('lingfeng.ui.audio_loading.ProcessRouter',side_effect=factory):
            with self.assertRaises(AudioLoadCancelled):AudioLoadingDialog.open_router(SETTINGS)
        self.assertTrue(started.is_set());router.close.assert_called_once()

    def test_device_error_is_preserved_and_worker_stops(self):
        with patch('lingfeng.ui.audio_loading.ProcessRouter',side_effect=RuntimeError('device unavailable')):
            with self.assertRaisesRegex(RuntimeError,'device unavailable'):
                AudioLoadingDialog.open_router(SETTINGS)
        APP.processEvents()

    def test_transport_uses_loading_callback_only_for_initial_open(self):
        transport=Transport();router=MagicMock();opener=MagicMock(return_value=router)
        transport.router_opener=opener
        try:
            transport.open();transport.open()
            opener.assert_called_once_with(transport.settings)
            self.assertIs(transport.synth,router)
            self.assertTrue(router.send.called)
        finally:transport.close()


if __name__=='__main__':unittest.main()

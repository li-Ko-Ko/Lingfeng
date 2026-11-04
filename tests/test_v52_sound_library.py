"""Offline GUI coverage for sound-pack installation, cancellation and reload."""
import hashlib
import json
import os
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock,patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QThread
from PySide6.QtTest import QSignalSpy,QTest
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QWidget
from lingfeng.platform import i18n
from lingfeng.ui.sound_dialog import SoundSettingsDialog
from lingfeng.ui.sound_library import SoundLibraryDialog,InstallCancelled

APP=QApplication.instance() or QApplication([])
ENTRY=dict(id='piano-test-download',name='可选大钢琴',name_en='Optional Grand',
    description='更细致的钢琴采样，按需安装。',description_en='Detailed piano samples, installed on demand.',
    archive_bytes=2*1024**2,url='https://example.invalid/piano.zip',
    manifest=dict(license='CC BY 3.0',source='https://example.invalid/piano'))


def wait_until(predicate,timeout=4):
    deadline=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>deadline:raise AssertionError('Qt condition timed out')
        # Let Python installer/import work run between GUI event batches.
        APP.processEvents();time.sleep(.005)
    APP.processEvents()


def fixture_archive(folder):
    binary=bytearray(128);binary[:2]=b'MZ';binary[60:64]=(64).to_bytes(4,'little');binary[64:70]=b'PE\0\0\x64\x86'
    manifest=dict(schema=1,abi=1,platform='windows-x64',id='local-piano-fixture',name='Local piano',
        name_en='Local piano',version='1',license='MIT',source='https://example.invalid/',author='Test',
        library='fixture.dll',license_file='LICENSE.txt',sha256=hashlib.sha256(binary).hexdigest(),
        presets=[dict(program=0,model=0,gain=1,name='Piano',name_en='Piano')])
    filename=folder/'local.zip'
    with zipfile.ZipFile(filename,'w') as archive:
        archive.writestr('fixture/synth.json',json.dumps(manifest))
        archive.writestr('fixture/fixture.dll',binary);archive.writestr('fixture/LICENSE.txt','MIT test fixture')
    return filename


class SoundLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(dir='tmp');self.addCleanup(self.temporary.cleanup)
        self.folder=Path(self.temporary.name).resolve();self.destination=self.folder/'synths';self.destination.mkdir()
        self.language=i18n.LANGUAGE;i18n.set_language('zh');self.addCleanup(i18n.set_language,self.language)
        for target,value in [('lingfeng.ui.sound_library.DOWNLOADS',(ENTRY,)),
                ('lingfeng.ui.sound_library.banks.default_root',lambda:self.destination),
                ('lingfeng.ui.sound_library.banks.installed_packs',lambda:[])]:
            replacement=patch(target,value);replacement.start();self.addCleanup(replacement.stop)

    def dialog(self):
        dialog=SoundLibraryDialog();dialog.show();APP.processEvents()
        def cleanup():
            if dialog.worker is not None:
                dialog.worker.cancel.set();dialog.worker.wait(4500);APP.processEvents()
            dialog.close();dialog.deleteLater();APP.processEvents()
        self.addCleanup(cleanup);return dialog

    def test_catalog_displays_size_license_bilingual_description_and_source(self):
        for language in ('zh','en'):
            i18n.set_language(language);dialog=self.dialog()
            self.assertEqual(dialog.choice.currentData(),ENTRY['id']);self.assertEqual(dialog.size.text(),'2.0 MiB')
            self.assertEqual(dialog.description.text(),ENTRY['description_en' if language=='en' else 'description'])
            self.assertEqual(dialog.license.text(),'CC BY 3.0');self.assertTrue(dialog.download_button.isEnabled())
            with patch('lingfeng.ui.sound_library.QDesktopServices.openUrl') as open_url:
                dialog.source_button.click();self.assertEqual(open_url.call_args.args[0].toString(),ENTRY['manifest']['source'])

    def test_installed_download_is_disabled_and_empty_catalog_allows_local_zip(self):
        (self.destination/ENTRY['id']).mkdir();dialog=self.dialog()
        self.assertFalse(dialog.choice.model().item(0).isEnabled());self.assertFalse(dialog.download_button.isEnabled())
        self.assertTrue(dialog.local_button.isEnabled());self.assertIn('已安装',dialog.choice.currentText())
        with patch('lingfeng.ui.sound_library.DOWNLOADS',()):empty=self.dialog()
        self.assertFalse(empty.download_button.isEnabled());self.assertTrue(empty.local_button.isEnabled())
        self.assertIn('本地 ZIP',empty.description.text())

    def test_local_fixture_installs_on_worker_and_emits_installed_path(self):
        filename=fixture_archive(self.folder);dialog=self.dialog();installed=QSignalSpy(dialog.installed)
        with patch('lingfeng.ui.sound_library.QFileDialog.getOpenFileName',return_value=(str(filename),'')):
            dialog.local_button.click();wait_until(lambda:dialog.worker is None)
        target=self.destination/'local-piano-fixture'
        self.assertTrue((target/'synth.json').is_file());self.assertEqual(installed.count(),1)
        self.assertEqual(installed.at(0),[str(target)]);self.assertIn(str(target),dialog.status.text())
        self.assertTrue(dialog.local_button.isEnabled());self.assertFalse(dialog.progress.isVisible())

    def test_download_progress_runs_off_gui_thread_and_cancel_restores_controls(self):
        entered=threading.Event();threads=[]
        def install(entry,*,cancel,progress):
            threads.append(QThread.currentThread());progress(1024**2,2*1024**2);entered.set()
            if not cancel.wait(3):raise RuntimeError('cancel not delivered')
            raise InstallCancelled()
        dialog=self.dialog();installed=QSignalSpy(dialog.installed)
        with patch('lingfeng.ui.sound_library.install_download',side_effect=install):
            dialog.download_button.click();wait_until(entered.is_set)
            wait_until(lambda:dialog.progress.maximum()==1000)
            self.assertNotEqual(threads[0],APP.thread());self.assertEqual(dialog.progress.value(),500)
            self.assertFalse(dialog.download_button.isEnabled());self.assertFalse(dialog.local_button.isEnabled())
            self.assertFalse(dialog.choice.isEnabled());self.assertTrue(dialog.cancel_button.isEnabled())
            dialog.cancel_button.click();wait_until(lambda:dialog.worker is None)
        self.assertEqual(installed.count(),0);self.assertTrue(dialog.isVisible());self.assertIn('已取消',dialog.status.text())
        self.assertTrue(dialog.download_button.isEnabled());self.assertTrue(dialog.local_button.isEnabled())

    def test_close_waits_for_cancelled_worker_before_destroying_dialog(self):
        entered=threading.Event();release=threading.Event()
        def install(source,*,cancel,progress):
            entered.set();cancel.wait(3);release.wait(3);raise InstallCancelled()
        dialog=self.dialog()
        with patch('lingfeng.ui.sound_library.install_archive',side_effect=install):
            dialog.start_install(self.folder/'unused.zip');wait_until(entered.is_set);worker=dialog.worker
            try:
                self.assertFalse(dialog.close());APP.processEvents()
                self.assertTrue(dialog.isVisible());self.assertTrue(worker.isRunning());self.assertTrue(worker.cancel.is_set())
                self.assertTrue(dialog.closing);self.assertFalse(dialog.cancel_button.isEnabled())
            finally:release.set()
            wait_until(lambda:dialog.worker is None)
        self.assertFalse(dialog.isVisible())

    def test_failed_install_preserves_existing_files_and_allows_retry(self):
        existing=self.destination/'keep.txt';existing.write_text('keep','utf-8');dialog=self.dialog()
        for error,expected in [(OSError('offline network'),'offline network'),(PermissionError('denied'),'无法写入音源目录')]:
            with self.subTest(error=type(error).__name__):
                with patch('lingfeng.ui.sound_library.install_archive',side_effect=error):
                    dialog.start_install(self.folder/'unused.zip');wait_until(lambda:dialog.worker is None)
                self.assertIn(expected,dialog.status.text());self.assertEqual(existing.read_text('utf-8'),'keep')
                self.assertTrue(dialog.local_button.isEnabled());self.assertTrue(dialog.download_button.isEnabled())
                self.assertTrue(dialog.buttons.button(QDialogButtonBox.StandardButton.Close).isEnabled())

    def test_success_refreshes_installed_download_without_a_second_download(self):
        def install(entry,*,cancel,progress):
            target=self.destination/entry['id'];target.mkdir();return target
        dialog=self.dialog();installed=QSignalSpy(dialog.installed)
        with patch('lingfeng.ui.sound_library.install_download',side_effect=install) as download:
            dialog.download_button.click();wait_until(lambda:dialog.worker is None)
            dialog.download_button.click();self.assertEqual(download.call_count,1)
        self.assertEqual(installed.count(),1);self.assertFalse(dialog.download_button.isEnabled())
        self.assertFalse(dialog.choice.model().item(0).isEnabled());self.assertTrue(dialog.local_button.isEnabled())

    def test_settings_wiring_stops_outputs_before_install_and_preserves_track_choices(self):
        owner=QWidget();owner.transport=MagicMock();events=[];preview=MagicMock()
        preview.close.side_effect=lambda:events.append('preview-close')
        owner.transport.close.side_effect=lambda:events.append('transport-close')
        settings={'melody':dict(device='synth:existing',program=1),'chords':dict(device='synth:existing',program=0)}
        packs=[dict(id='existing',name='Existing piano',author='Test',license='MIT',
            presets=[dict(program=n,name=f'Piano {n}',name_en=f'Piano {n}') for n in (0,1)])]
        registry=dict(roots=[str(self.destination)],errors=[])
        def rescan(roots):events.append('rescan')
        def install(source,*,cancel,progress):
            events.append('install');return self.destination/'added'
        def execute(library):
            library.start_install(self.folder/'fixture.zip');wait_until(lambda:library.worker is None);library.deleteLater();return 0
        with patch('lingfeng.audio.routing.midi_devices',return_value=[]), \
                patch('lingfeng.ui.sound_dialog.banks.installed_packs',return_value=packs), \
                patch('lingfeng.ui.sound_dialog.banks.registry',return_value=registry), \
                patch('lingfeng.ui.sound_dialog.banks.available_programs',return_value=[0,1]), \
                patch('lingfeng.ui.sound_dialog.banks.instrument_label',side_effect=lambda n,source:f'Piano {n}'), \
                patch('lingfeng.ui.sound_dialog.banks.pack',return_value=packs[0]), \
                patch('lingfeng.ui.sound_dialog.banks.pack_label',side_effect=lambda p:p['name']), \
                patch('lingfeng.ui.sound_dialog.banks.rescan',side_effect=rescan), \
                patch('lingfeng.ui.sound_library.install_archive',side_effect=install), \
                patch.object(SoundLibraryDialog,'exec',execute):
            dialog=SoundSettingsDialog(settings,owner);dialog.preview_router=preview
            try:
                dialog.library_button.click();self.assertEqual(dialog.value(),settings)
                self.assertLess(events.index('preview-close'),events.index('install'))
                self.assertLess(events.index('transport-close'),events.index('install'))
                self.assertLess(events.index('install'),events.index('rescan'))
                self.assertEqual(events[events.index('rescan')-1],'transport-close')
            finally:dialog.close();dialog.deleteLater();owner.deleteLater();APP.processEvents()


if __name__=='__main__':unittest.main()

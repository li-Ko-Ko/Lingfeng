"""Archive and network failures must not damage installed sound packs."""
import hashlib
import io
import json
from pathlib import Path
import stat
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

from lingfeng.audio import pack_install as installer

ROOT = Path(__file__).resolve().parents[1]


class Response(io.BytesIO):
    def __init__(self, content):
        super().__init__(content)
        self.headers = {'Content-Length': str(len(content))}

    def geturl(self):
        return 'https://example.org/verified.zip'


class PackInstallTests(unittest.TestCase):
    def setUp(self):
        (ROOT / 'tmp').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.destination = self.root / 'installed'
        binary = bytearray(128)
        binary[:2] = b'MZ'
        binary[60:64] = (64).to_bytes(4, 'little')
        binary[64:70] = b'PE\0\0\x64\x86'
        self.binary = bytes(binary)
        self.manifest = dict(schema=1, abi=1, platform='windows-x64', id='test-piano',
            name='测试钢琴', name_en='Test piano', version='0.52', license='CC0',
            source='https://example.org/piano', author='Test author', library='sfizz.dll',
            sha256=hashlib.sha256(self.binary).hexdigest(), license_file='LICENSE.txt',
            presets=[dict(program=0, model=0, gain=.3, name='钢琴', name_en='Piano')])

    def archive(self, entries, name='pack.zip'):
        path = self.root / name
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as archive:
            for key, value in entries:
                if isinstance(key, str) and '\\' in key:
                    raw_name = zipfile.ZipInfo(key)
                    raw_name.filename = key  # Keep a malformed ZIP name on Windows.
                    key = raw_name
                archive.writestr(key, value)
        return path

    def pack_entries(self, prefix='piano/'):
        return [(prefix+'synth.json', json.dumps(self.manifest)),
                (prefix+'sfizz.dll', self.binary), (prefix+'LICENSE.txt', 'CC0')]

    def assert_no_staging(self):
        if self.destination.exists():
            self.assertFalse(any(p.name.startswith('.') for p in self.destination.iterdir()))

    def test_complete_local_zip_is_validated_and_installed(self):
        with patch('lingfeng.audio.calibration.multiprocessing.get_context') as launch:
            path = installer.install_archive(self.archive(self.pack_entries()), self.destination)
        launch.assert_not_called()  # A self-declared library hash does not authorize a render.
        self.assertEqual(path, self.destination / 'test-piano')
        self.assertEqual((path / 'sfizz.dll').read_bytes(), self.binary)
        self.assertEqual(json.loads((path / 'calibration.json').read_text('utf-8')),
                         {'schema': 1, 'preset_gain_db': {}})
        self.assert_no_staging()

    def test_calibration_keeps_original_manifest_and_checksums(self):
        entries = self.pack_entries()
        manifest = entries[0][1]
        checksum = json.dumps({'synth.json': hashlib.sha256(manifest.encode()).hexdigest()})
        entries.append(('piano/files.sha256.json', checksum))
        with patch.object(installer, 'calibrate_pack', return_value={'0': 6.5}) as calibrate:
            path = installer.install_archive(self.archive(entries), self.destination)
        calibrate.assert_called_once()
        self.assertEqual((path / 'synth.json').read_text('utf-8'), manifest)
        self.assertEqual((path / 'files.sha256.json').read_text('utf-8'), checksum)
        self.assertEqual(json.loads((path / 'calibration.json').read_text('utf-8'))['preset_gain_db'], {'0': 6.5})
        self.assert_no_staging()

    def test_cancelling_calibration_does_not_commit(self):
        cancel = threading.Event()

        def cancel_probe(folder, data, cancel, progress):
            cancel.set()
            return {'0': 6.5}

        with patch.object(installer, 'calibrate_pack', side_effect=cancel_probe):
            with self.assertRaises(installer.InstallCancelled):
                installer.install_archive(self.archive(self.pack_entries()), self.destination, cancel)
        self.assertFalse((self.destination / 'test-piano').exists())
        self.assert_no_staging()

    def test_bad_checksum_never_creates_an_installed_pack(self):
        entries = self.pack_entries()
        entries[1] = ('piano/sfizz.dll', b'corrupted DLL')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            installer.install_archive(self.archive(entries), self.destination)
        self.assertFalse((self.destination / 'test-piano').exists())
        self.assert_no_staging()

    def test_path_traversal_windows_paths_and_symlinks_are_rejected(self):
        for name in ('../outside.txt', 'piano/../../outside.txt', '/absolute.txt',
                     'C:/outside.txt', 'piano\\outside.txt', 'piano/CON.txt', 'piano/name. '):
            with self.subTest(name=name):
                archive = self.archive([*self.pack_entries(), (name, b'bad')])
                with self.assertRaises(ValueError):
                    installer.install_archive(archive, self.destination)
                self.assertFalse((self.root / 'outside.txt').exists())
                self.assert_no_staging()
        link = zipfile.ZipInfo('piano/link')
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        with self.assertRaises(ValueError):
            installer.install_archive(self.archive([*self.pack_entries(), (link, '../outside')]), self.destination)

    def test_case_collisions_and_multiple_packs_are_rejected(self):
        with self.assertRaises(ValueError):
            installer.install_archive(self.archive([*self.pack_entries(), ('piano/license.TXT', 'other')]), self.destination)
        with self.assertRaises(ValueError):
            installer.install_archive(self.archive([*self.pack_entries(), *self.pack_entries('other/')]), self.destination)
        self.assert_no_staging()

    def test_existing_pack_is_preserved_and_cancellation_cleans_staging(self):
        archive = self.archive(self.pack_entries())
        target = installer.install_archive(archive, self.destination)
        sentinel = target / 'user-file.txt'
        sentinel.write_text('preserve me', 'utf-8')
        with self.assertRaises(ValueError):
            installer.install_archive(archive, self.destination)
        self.assertEqual(sentinel.read_text('utf-8'), 'preserve me')
        cancel = threading.Event(); cancel.set()
        with self.assertRaises(installer.InstallCancelled):
            installer.install_archive(archive, self.destination, cancel)
        self.assert_no_staging()

    def test_limits_are_checked_before_extraction(self):
        archive = self.archive(self.pack_entries())
        with patch.object(installer, 'MAX_EXTRACTED', 1), self.assertRaises(ValueError):
            installer.install_archive(archive, self.destination)
        self.assert_no_staging()

    def download_fixture(self):
        source = self.archive([
            ('upstream/AccurateSalamanderGrand-Z.sfz', '<region> lovel=2 sample=flac/note.flac'),
            ('upstream/flac/note.flac', b'audio test fixture'),
            ('upstream/README.orig.txt', 'Original sample license'),
            ('upstream/do-not-install.exe', b'executable'),
        ], 'upstream.zip').read_bytes()
        manifest = dict(self.manifest, engine='sfz', voices=256,
            presets=[dict(self.manifest['presets'][0], sfz='AccurateSalamanderGrand-Z.sfz')])
        entry = dict(id='test-piano', url='https://example.org/verified.zip',
            sha256=hashlib.sha256(source).hexdigest(), archive_bytes=len(source),
            archive_root='upstream', manifest=manifest, text_files={'LICENSE.txt': 'CC BY'})
        runtime = self.root / 'runtime-pack'; runtime.mkdir()
        (runtime / 'sfizz.dll').write_bytes(self.binary)
        (runtime / 'runtime').mkdir()
        (runtime / 'runtime/LICENSE-sfizz.txt').write_text('BSD-2-Clause', 'utf-8')
        return source, entry, dict(manifest, id='piano-electric', path=str(runtime))

    def test_verified_download_installs_only_curated_assets_and_runtime(self):
        source, entry, runtime = self.download_fixture()
        progress = []
        with patch.object(installer, 'urlopen', return_value=Response(source)), \
                patch.object(installer.banks, 'pack', return_value=runtime) as pack:
            target = installer.install_download(entry, self.destination, progress=lambda a,b: progress.append((a,b)))
            pack.assert_called_once_with('synth:piano-electric')
        self.assertTrue((target / 'flac/note.flac').is_file())
        self.assertIn('lovel=1', (target / 'AccurateSalamanderGrand-Z.sfz').read_text('utf-8'))
        self.assertTrue((target / 'runtime/LICENSE-sfizz.txt').is_file())
        self.assertFalse((target / 'do-not-install.exe').exists())
        self.assertIn((len(source), len(source)), progress)
        self.assert_no_staging()

    def test_verified_download_uses_legacy_small_runtime_when_greg_is_absent(self):
        source, entry, runtime = self.download_fixture()
        with patch.object(installer, 'urlopen', return_value=Response(source)), \
                patch.object(installer.banks, 'pack', side_effect=[ValueError('not installed'), dict(runtime, id='piano-small')]):
            target = installer.install_download(entry, self.destination)
        self.assertEqual((target / 'sfizz.dll').read_bytes(), self.binary)
        self.assert_no_staging()

    def test_download_hash_failure_and_cancel_leave_no_partial_pack(self):
        source, entry, runtime = self.download_fixture()
        entry['sha256'] = '0' * 64
        with patch.object(installer, 'urlopen', return_value=Response(source)), \
                patch.object(installer.banks, 'pack', return_value=runtime), self.assertRaises(ValueError):
            installer.install_download(entry, self.destination)
        self.assertFalse((self.destination / 'test-piano').exists())
        self.assert_no_staging()
        cancel = threading.Event()
        with patch.object(installer, 'urlopen', return_value=Response(source)), \
                patch.object(installer.banks, 'pack', return_value=runtime), self.assertRaises(installer.InstallCancelled):
            installer.install_download(entry, self.destination, cancel,
                progress=lambda a,b: cancel.set())
        self.assert_no_staging()

    def test_runtime_hash_mismatch_and_insecure_download_are_rejected(self):
        source, entry, runtime = self.download_fixture()
        entry['manifest']['sha256'] = '0' * 64
        with patch.object(installer.banks, 'pack', return_value=runtime), \
                patch.object(installer, 'urlopen') as request, self.assertRaises(ValueError):
            installer.install_download(entry, self.destination)
        request.assert_not_called()
        entry['url'] = 'http://example.org/insecure.zip'
        with self.assertRaises(ValueError):
            installer._download(entry, self.root / 'download.zip')


if __name__ == '__main__':
    unittest.main()

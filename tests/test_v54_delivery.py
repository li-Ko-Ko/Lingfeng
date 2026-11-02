"""Local standalone delivery is the default; archives require explicit intent."""
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from scripts import package_release as packaging
from scripts import release_policy as policy
from scripts import verify_release as verification

ROOT=Path(__file__).resolve().parents[1]


class StandaloneDeliveryTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'tmp').mkdir(exist_ok=True)
        temporary=tempfile.TemporaryDirectory(prefix='v54-delivery-',dir=ROOT/'tmp')
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)/'checkout';self.root.mkdir()
        self.version='0.54-test';self.folder=self.root/'dist'/self.version/'Lingfeng'
        for name in (*policy.SOURCE_ROOT_FILES,*policy.SOURCE_REQUIRED_FILES):self.write(name,b'fixture source\n')
        self.write('lingfeng/platform/en.json',b'{}')
        self.write('licenses/qt-6.9.2/manifest.json',b'[]')
        self.write('dist/'+self.version+'/Lingfeng/Lingfeng.exe',b'executable fixture')
        for name in ('lingfeng/platform/en.json','assets/lingfeng.ico'):
            self.write('dist/'+self.version+'/Lingfeng/_internal/'+name,(self.root/name).read_bytes())
        self.write('dist/'+self.version+'/Lingfeng/_internal/PySide6/Qt6Core.dll',b'Qt fixture')
        for ident in policy.APPROVED_PACKS:
            payload=('engine fixture '+ident).encode();self.write('synths/'+ident+'/engine.dll',payload)
            data=dict(id=ident,library='engine.dll',sha256=hashlib.sha256(payload).hexdigest(),presets=[dict(program=0,name='Piano')])
            self.write('synths/'+ident+'/synth.json',json.dumps(data).encode())
            self.write('synths/'+ident+'/LICENSE.txt',b'synth license fixture')
        self.old=self.root/'dist/Lingfeng-0.53.2-Windows-x64.zip';self.write(self.old.relative_to(self.root),b'old archive preserved')
        self.write(self.old.with_suffix('.zip.sha256').relative_to(self.root),b'old checksum preserved')
        self.old_bytes={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in (self.old,self.old.with_suffix('.zip.sha256'))}
        for module in (packaging,verification):
            self.enterContext(patch.object(module,'ROOT',self.root))
            self.enterContext(patch.object(module,'__version__',self.version))
        self.enterContext(patch.object(packaging,'SYNTH_ROOT',self.root/'synths'))
        self.validator=self.enterContext(patch.object(packaging,'_validate'))
        self.enterContext(patch.object(packaging.metadata,'distribution',return_value=SimpleNamespace(version='fixture',files=[])))
        self.enterContext(patch('sys.stdout',new_callable=io.StringIO))

    def write(self,name,data):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);return path

    def assert_old_archives_unchanged(self):
        for path,state in self.old_bytes.items():self.assertEqual((path.read_bytes(),path.stat().st_mtime_ns),state)

    def test_default_prepares_complete_folder_without_opening_any_archive(self):
        archive,checksum=packaging.archive_paths()
        archive.write_bytes(b'current archive also preserved');checksum.write_bytes(b'current checksum preserved')
        before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in (archive,checksum)}
        with patch.object(zipfile,'ZipFile',side_effect=AssertionError('Default delivery must not open a ZIP')):
            result=packaging.package();report=verification.verify()
        self.assertIsNone(result['archive']);self.assertIsNone(report['archive']);self.assertIsNone(report['sha256'])
        info=json.loads((self.folder/'build-info.json').read_text('utf-8'))
        self.assertEqual(info['delivery'],'local-standalone');self.assertFalse(info['archive_requested'])
        self.assertEqual(set(info['bundled_packs']),set(policy.APPROVED_PACKS));self.assertEqual(self.validator.call_count,4)
        for ident in policy.APPROVED_PACKS:self.assertTrue((self.folder/'synths'/ident/'LICENSE.txt').is_file())
        for name in ('CHANGELOG.md',):
            self.assertEqual((self.folder/name).read_bytes(),(self.root/name).read_bytes())
            self.assertEqual((self.folder/'source'/name).read_bytes(),(self.root/name).read_bytes())
        self.assertFalse((self.folder/'CHANGELOG_LOCAL.md').exists())
        self.assertFalse((self.folder/'source/CHANGELOG_LOCAL.md').exists())
        for path,state in before.items():self.assertEqual((path.read_bytes(),path.stat().st_mtime_ns),state)
        self.assert_old_archives_unchanged()

    def test_default_never_creates_zip_or_checksum_when_none_exist_for_version(self):
        packaging.package();archive,checksum=packaging.archive_paths()
        self.assertFalse(archive.exists());self.assertFalse(checksum.exists())
        self.assertEqual(set((self.root/'dist').glob('*.zip*')),set(self.old_bytes))
        self.assertEqual(verification.verify()['status'],'passed');self.assert_old_archives_unchanged()

    def test_explicit_archive_creates_only_main_zip_and_checks_it(self):
        self.write('dist/'+self.version+'/Lingfeng/synths/user-installed/engine.dll',b'user pack preserved locally')
        result=packaging.package(archive=True);archive,checksum=packaging.archive_paths()
        self.assertEqual(result['archive'],str(archive));self.assertTrue(checksum.is_file())
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),checksum.read_text('ascii').split()[0])
        self.assertTrue(json.loads((self.folder/'build-info.json').read_text('utf-8'))['archive_requested'])
        with zipfile.ZipFile(archive) as source:
            self.assertFalse(any('user-installed' in name for name in source.namelist()))
            self.assertTrue(all('Lingfeng/synths/'+ident+'/synth.json' in source.namelist() for ident in policy.APPROVED_PACKS))
        self.assertTrue((self.folder/'synths/user-installed/engine.dll').is_file())
        report=verification.verify(archive=True);self.assertEqual(report['status'],'passed')
        self.assertEqual(report['archive'],str(archive));self.assertGreater(report['archive_files'],0)
        self.assertEqual(set((self.root/'dist').glob('*.zip*')),set(self.old_bytes)|{archive,checksum})
        self.assert_old_archives_unchanged()

    def test_existing_archive_is_rejected_before_folder_is_repackaged(self):
        archive,_=packaging.archive_paths();archive.write_bytes(b'already generated archive')
        sentinel=self.write('dist/'+self.version+'/Lingfeng/Start-here.txt',b'original standalone')
        with self.assertRaisesRegex(FileExistsError,'Existing archive or checksum is preserved'):
            packaging.package(archive=True)
        self.assertEqual(archive.read_bytes(),b'already generated archive');self.assertEqual(sentinel.read_bytes(),b'original standalone')
        self.assertFalse((self.folder/'build-info.json').exists());self.assert_old_archives_unchanged()

    def test_existing_checksum_is_preserved_even_without_its_archive(self):
        archive,checksum=packaging.archive_paths();checksum.write_bytes(b'original checksum')
        with self.assertRaises(FileExistsError):packaging.package(archive=True)
        self.assertFalse(archive.exists());self.assertEqual(checksum.read_bytes(),b'original checksum')
        self.assert_old_archives_unchanged()

    def test_failed_archive_write_removes_only_its_new_partial_file(self):
        with patch.object(zipfile.ZipFile,'write',side_effect=OSError('simulated archive write failure')):
            with self.assertRaisesRegex(OSError,'simulated archive write failure'):packaging.package(archive=True)
        self.assertTrue((self.folder/'build-info.json').is_file())
        self.assertFalse(any(path.exists() for path in packaging.archive_paths()));self.assert_old_archives_unchanged()

    def test_archive_verification_is_opt_in_and_never_repairs_missing_files(self):
        packaging.package();archive,checksum=packaging.archive_paths()
        self.assertEqual(verification.verify()['status'],'passed')
        with self.assertRaises(FileNotFoundError):verification.verify(archive=True)
        self.assertFalse(archive.exists());self.assertFalse(checksum.exists());self.assert_old_archives_unchanged()


if __name__=='__main__':unittest.main()

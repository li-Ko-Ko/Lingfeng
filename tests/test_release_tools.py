"""Release inputs and checks must follow nested modules and isolated tests."""
import importlib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from scripts import release_policy as policy
from scripts import run_regression as regression
from scripts.verify_release import verify_runtime_resources

ROOT=Path(__file__).resolve().parent.parent


class SourceBundleTests(unittest.TestCase):
    def setUp(self):
        (ROOT/'tmp').mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'tmp');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'checkout';self.root.mkdir()
        self.dest=Path(self.temp.name)/'source'
        for name in (*policy.SOURCE_ROOT_FILES,*policy.SOURCE_REQUIRED_FILES):self.write(name,'root source')
        for name in ('lingfeng/__init__.py','lingfeng/music/model.py','lingfeng/platform/en.json',
                     'scripts/release_policy.py','tests/test_music.py','docs/HELP.md',
                     'assets/lingfeng.ico','licenses/audio-source/nested/LICENSE'):
            self.write(name,'reviewed source')
        for name in ('lingfeng/music/__pycache__/model.pyc','tests/legacy/smoke_v9.py',
                     'development/private.py','licenses/sfz-sources/obsolete.txt',
                     *policy.PRIVATE_SOURCE_FILES,
                     'scripts/private_notes.py','docs/private_notes.md'):
            self.write(name,'excluded')

    def write(self,name,value):
        path=self.root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value,'utf-8')

    def copy_bundle(self):
        for path in policy.source_files(self.root):
            dest=self.dest/path.relative_to(self.root);dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,dest)

    def test_nested_modules_resources_notices_and_public_help_are_rebuild_inputs(self):
        names={path.relative_to(self.root).as_posix() for path in policy.source_files(self.root)}
        for name in ('lingfeng/music/model.py','lingfeng/platform/en.json',
                     'docs/HELP.md','licenses/audio-source/nested/LICENSE'):
            self.assertIn(name,names)
        self.assertFalse(any('legacy' in name or '__pycache__' in name or 'development' in name or 'sfz-sources' in name for name in names))
        self.assertFalse(set(names)&set(policy.PRIVATE_SOURCE_FILES))
        self.assertNotIn('scripts/private_notes.py',names);self.assertNotIn('docs/private_notes.md',names)
        self.assertTrue(set(policy.PUBLIC_SCREENSHOTS)<=names)
        self.copy_bundle();self.assertEqual(set(policy.verify_source_tree(self.root,self.dest)),names)

    def test_featured_screenshots_are_explicitly_reviewed_and_capped_at_five(self):
        self.assertGreater(len(policy.PUBLIC_SCREENSHOTS),0)
        self.assertLessEqual(len(policy.PUBLIC_SCREENSHOTS),5)
        self.write('docs/screenshots/personal-project.png','unreviewed picture')
        names={path.relative_to(self.root).as_posix() for path in policy.source_files(self.root)}
        self.assertNotIn('docs/screenshots/personal-project.png',names)
        policy.verify_public_release_paths(policy.PUBLIC_SCREENSHOTS)
        with self.assertRaisesRegex(RuntimeError,'Unreviewed documentation'):
            policy.verify_public_release_paths(['docs/screenshots/personal-project.png'])

    def test_missing_nested_module_is_rejected(self):
        self.copy_bundle();(self.dest/'lingfeng/music/model.py').unlink()
        with self.assertRaisesRegex(RuntimeError,'missing=.*lingfeng/music/model.py'):
            policy.verify_source_tree(self.root,self.dest)

    def test_checkout_missing_entire_application_tree_is_rejected(self):
        self.copy_bundle()
        application=(self.root/'lingfeng').resolve()
        self.assertTrue(application.is_relative_to(self.root.resolve()))
        shutil.rmtree(application)
        with self.assertRaisesRegex(RuntimeError,'Required source inputs missing:.*lingfeng'):
            policy.verify_source_tree(self.root,self.dest)

    def test_empty_required_source_tree_is_rejected(self):
        # No native key file is removed here: an empty tree must fail even if
        # the mandatory-file policy is temporarily extended without this tree.
        with patch.object(policy,'SOURCE_TREES',dict(policy.SOURCE_TREES,empty_future_tree={'.py'})):
            with self.assertRaisesRegex(RuntimeError,'Required source tree is empty: empty_future_tree'):
                policy.source_files(self.root)

    def test_missing_public_help_is_rejected(self):
        (self.root/'docs/HELP.md').unlink()
        with self.assertRaisesRegex(RuntimeError,'Required source inputs missing:.*docs/HELP.md'):
            policy.source_files(self.root)

    def test_public_rebuild_does_not_require_local_maintenance_files(self):
        expected={path.relative_to(self.root).as_posix() for path in policy.source_files(self.root)}
        for name in policy.PRIVATE_SOURCE_FILES:(self.root/name).unlink()
        self.assertEqual({path.relative_to(self.root).as_posix() for path in policy.source_files(self.root)},expected)
        self.copy_bundle();policy.verify_source_tree(self.root,self.dest)

    def test_repository_candidates_and_git_tree_validation_exclude_private_records(self):
        for ident in policy.APPROVED_PACKS:
            self.write(f'synths/{ident}/synth.json','reviewed manifest')
            self.write(f'synths/{ident}/source/synth.cpp','reviewed source')
        self.write('synths/unreviewed/synth.json','user-installed pack')
        names={path.relative_to(self.root).as_posix() for path in policy.repository_files(self.root)}
        self.assertTrue(all(f'synths/{ident}/source/synth.cpp' in names for ident in policy.APPROVED_PACKS))
        self.assertNotIn('synths/unreviewed/synth.json',names)
        policy.verify_repository_paths(self.root,names)
        with self.assertRaisesRegex(RuntimeError,'Public repository inventory mismatch:.*ARCHITECTURE'):
            policy.verify_repository_paths(self.root,names|{'docs/ARCHITECTURE.md'})

    def test_repack_removes_only_known_distribution_copies(self):
        destination=self.root/'dist/0.51/Lingfeng';destination.mkdir(parents=True)
        copies=('source/docs/ARCHITECTURE.md','docs/INTERFACES.md',
                'source/scripts/audit_architecture.py','source/tests/test_architecture.py',
                'source/tests/legacy/smoke_old.py','source/launch.cmd',
                'examples/lingfeng-rap.mid',
                'licenses/qt-6.9.2/qtbase/src/widgets/doc/images/licensewizard-flow.png')
        for relative in copies:
            path=destination/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('private copy','utf-8')
        public=destination/'source/lingfeng/model.py';public.parent.mkdir(parents=True,exist_ok=True);public.write_text('public code','utf-8')
        unknown=destination/'docs/unknown-notes.md';unknown.write_text('unreviewed copy','utf-8')
        original=(self.root/'docs/ARCHITECTURE.md').read_bytes()
        removed=policy.prune_private_release_copies(self.root,destination)
        self.assertIn('source/docs/ARCHITECTURE.md',removed)
        self.assertTrue(all(not (destination/name).exists() for name in copies))
        self.assertEqual((self.root/'docs/ARCHITECTURE.md').read_bytes(),original)
        self.assertEqual(public.read_text('utf-8'),'public code');self.assertTrue(unknown.exists())
        with self.assertRaisesRegex(RuntimeError,'Unreviewed documentation in release'):
            policy.verify_public_release_paths(path.relative_to(destination) for path in destination.rglob('*') if path.is_file())

    def test_cleanup_cannot_target_checkout_or_dist_root(self):
        for target in (self.root,self.root/'docs',self.root/'dist'):
            with self.subTest(target=target),self.assertRaisesRegex(RuntimeError,'release folder inside dist'):
                policy.prune_private_release_copies(self.root,target)
        self.assertTrue((self.root/'docs/ARCHITECTURE.md').is_file())

    def test_release_path_audit_rejects_private_documents_and_tools(self):
        policy.verify_public_release_paths(['docs/HELP.md','source/docs/SOUNDBANKS.md','source/scripts/run_regression.py'])
        for name in policy.PRIVATE_SOURCE_FILES:
            with self.subTest(name=name),self.assertRaisesRegex(RuntimeError,'Local-only content in release'):
                policy.verify_public_release_paths(['source/'+name])
        with self.assertRaisesRegex(RuntimeError,'Local-only content in release'):
            policy.verify_public_release_paths(['_internal/docs/MAINTENANCE.md'])

    def test_changed_resource_and_stale_module_are_rejected(self):
        self.copy_bundle();resource=self.dest/'lingfeng/platform/en.json'
        resource.write_text('changed','utf-8')
        with self.assertRaisesRegex(RuntimeError,'Source mismatch: lingfeng/platform/en.json'):
            policy.verify_source_tree(self.root,self.dest)
        resource.write_text('reviewed source','utf-8')
        (self.dest/'lingfeng/retired.py').write_text('stale','utf-8')
        with self.assertRaisesRegex(RuntimeError,'extra=.*retired.py'):
            policy.verify_source_tree(self.root,self.dest)

    def test_importing_packager_does_not_start_a_build(self):
        with patch('sys.argv',['package_release.py','invalid-destination']):
            module=importlib.import_module('scripts.package_release')
            importlib.reload(module)
        self.assertTrue(callable(module.package))

    def test_frozen_resources_reject_mismatch_and_retired_package(self):
        for relative in ('lingfeng/platform/en.json','assets/lingfeng.ico'):
            target=self.dest/'_internal'/relative;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(self.root/relative,target)
        verify_runtime_resources(self.root,self.dest)
        resource=self.dest/'_internal/lingfeng/platform/en.json'
        resource.write_text('obsolete catalogue','utf-8')
        with self.assertRaisesRegex(AssertionError,'Frozen resource mismatch: lingfeng/platform/en.json'):
            verify_runtime_resources(self.root,self.dest)
        shutil.copy2(self.root/'lingfeng/platform/en.json',resource)
        (self.dest/'_internal/popscore').mkdir()
        with self.assertRaisesRegex(AssertionError,'Retired runtime package data'):
            verify_runtime_resources(self.root,self.dest)


class NoticeCollectionTests(unittest.TestCase):
    def test_license_named_images_are_excluded_without_losing_text_notices(self):
        with patch('urllib.request.urlopen',side_effect=AssertionError('Import must not fetch upstream files')):
            collector=importlib.import_module('scripts.collect_qt_notices')
            importlib.reload(collector)
        self.assertFalse(collector.is_notice_path('src/widgets/doc/images/licensewizard-flow.png'))
        self.assertFalse(collector.is_notice_path('LICENSES/license-diagram.svg'))
        self.assertFalse(collector.is_notice_text(b'\x89PNG\r\n\x1a\n\0binary'))
        self.assertTrue(collector.is_notice_path('sources/shiboken6/COPYING.libshiboken'))
        self.assertTrue(collector.is_notice_path('src/gui/vulkan/licenseheader.h.in'))
        self.assertTrue(collector.is_notice_text(b'SPDX-License-Identifier: MIT\nCopyright notice\n'))

    def test_collected_notice_manifest_matches_preserved_files(self):
        folder=ROOT/'licenses/qt-6.9.2'
        entries=json.loads((folder/'manifest.json').read_text('utf-8'))
        self.assertNotIn('qtbase/src/widgets/doc/images/licensewizard-flow.png',[entry['file'] for entry in entries])
        self.assertEqual(len(entries),len({entry['file'] for entry in entries}))
        for entry in entries:
            with self.subTest(file=entry['file']):
                target=(folder/entry['file']).resolve()
                self.assertTrue(target.is_relative_to(folder.resolve()))
                self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(),entry['sha256'])


class RegressionRunnerTests(unittest.TestCase):
    def test_current_and_previous_version_report_names(self):
        self.assertEqual(regression.version_tag('0.51'),'v51')
        self.assertEqual(regression.version_tag('0.50.2'),'v502')
        self.assertEqual(regression.version_tag('0.50.0'),'v50')

    def test_modules_receive_distinct_preferences_and_incomplete_report_is_running(self):
        (ROOT/'tmp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as folder:
            base=Path(folder);(base/'tests').mkdir()
            for name in ('test_one','test_two'):(base/'tests'/(name+'.py')).write_text('','utf-8')
            environments=[];statuses=[]
            def run_process(args,**kwargs):
                environments.append(kwargs['env'])
                report=base/'output'/f'{regression.version_tag(regression.__version__)}-tests.json'
                if report.exists():statuses.append(json.loads(report.read_text('utf-8'))['status'])
                kwargs['stdout'].write('Ran 1 test\nOK\n')
                return type('Result',(),{'returncode':0})()
            original=dict(os.environ);cwd=Path.cwd()
            with patch.object(regression,'ROOT',base),patch.object(regression.subprocess,'run',side_effect=run_process),patch('sys.stdout',new_callable=io.StringIO):
                self.assertEqual(regression.run(),0)
            self.assertEqual(statuses,['running'])
            self.assertNotEqual(environments[0]['LINGFENG_USER_DATA'],environments[1]['LINGFENG_USER_DATA'])
            for env in environments:self.assertTrue(Path(env['LINGFENG_USER_DATA']).is_relative_to(base/'tmp'))
            self.assertEqual(dict(os.environ),original);self.assertEqual(Path.cwd(),cwd)


if __name__=='__main__':unittest.main()

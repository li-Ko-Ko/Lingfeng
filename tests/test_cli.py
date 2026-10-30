"""The source and module launchers share argument handling and failure reports."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from lingfeng import __version__
from lingfeng.cli import main

ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def test_version_and_help_need_no_qt(self):
        # Isolated Python cannot import installed Qt or repository site packages.
        for args in (['--version'], ['--help']):
            code = "import runpy,sys;sys.path.insert(0,sys.argv.pop(1));runpy.run_module('lingfeng',run_name='__main__')"
            result = subprocess.run([sys.executable, '-I', '-S', '-X', 'utf8', '-c', code, str(ROOT), *args],
                                    capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(__version__ if '--version' in args else '--self-test', result.stdout)

    def test_invalid_or_conflicting_arguments_return_usage_error(self):
        for args in (['--self-test'], ['--associate', '--self-test', 'out'], ['song.lfs', '--associate'],
                     ['song.lfs', '--self-test', 'out'], ['--unknown']):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main(args)
            self.assertEqual(error.exception.code, 2)

    def test_project_path_with_spaces_is_forwarded_without_rewriting(self):
        with patch('lingfeng.ui.main_window.run', return_value=0) as run:
            self.assertEqual(main(['folder with spaces/song.lfs']), 0)
        run.assert_called_once_with('folder with spaces/song.lfs')

    def test_self_test_failure_writes_report_and_restores_callback_hook(self):
        previous = sys.excepthook
        (ROOT / 'tmp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as directory:
            with patch('lingfeng.diagnostics.self_test.self_test', side_effect=RuntimeError('acceptance failure')):
                self.assertEqual(main(['--self-test', directory]), 1)
            report = json.loads((Path(directory) / 'result.json').read_text('utf-8'))
            self.assertEqual(report['status'], 'failed')
            self.assertIn('acceptance failure', report['error'])
            self.assertTrue((Path(directory) / 'error.log').is_file())
        self.assertIs(sys.excepthook, previous)

    def test_qt_callback_failure_cannot_be_reported_as_success(self):
        (ROOT / 'tmp').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=ROOT / 'tmp') as directory:
            def callback_failure(folder):
                error = ValueError('callback failure')
                sys.excepthook(type(error), error, None)
                return 0

            with patch('lingfeng.diagnostics.self_test.self_test', callback_failure):
                self.assertEqual(main(['--self-test', directory]), 1)
            report = json.loads((Path(directory) / 'result.json').read_text('utf-8'))
            self.assertEqual(report['status'], 'failed')
            self.assertIn('callback failure', (Path(directory) / 'callback-errors.log').read_text('utf-8'))


if __name__ == '__main__':
    unittest.main()

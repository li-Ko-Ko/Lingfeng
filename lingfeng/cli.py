"""Desktop launch modes, kept separate from widgets and acceptance checks."""
import argparse
import json
import os
from pathlib import Path
import sys
import traceback

from lingfeng import __version__


def _self_test(folder):
    """Record synchronous and Qt callback failures in a machine-readable report."""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    folder = folder.resolve()
    folder.mkdir(parents=True, exist_ok=True)
    callback_errors = []

    def record_callback(kind, value, tb):
        callback_errors.append(''.join(traceback.format_exception(kind, value, tb)))
        (folder / 'callback-errors.log').write_text('\n'.join(callback_errors), encoding='utf-8')

    previous_hook = sys.excepthook
    sys.excepthook = record_callback
    try:
        from unittest.mock import patch
        from PySide6.QtWidgets import QMessageBox
        from lingfeng.diagnostics.self_test import self_test

        def fail_message(parent, title, message, *args, **kwargs):
            raise RuntimeError(f'{title}: {message}')

        with patch.object(QMessageBox, 'warning', fail_message), patch.object(QMessageBox, 'critical', fail_message):
            code = self_test(folder)
        if callback_errors:
            raise RuntimeError('\n'.join(callback_errors))
        return code
    except Exception:
        error = traceback.format_exc()
        (folder / 'error.log').write_text(error, encoding='utf-8')
        result = {'status': 'failed', 'error': error, 'frozen': bool(getattr(sys, 'frozen', False))}
        (folder / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return 1
    finally:
        sys.excepthook = previous_hook


def _associate():
    from PySide6.QtWidgets import QApplication, QMessageBox
    from lingfeng.platform.file_association import associate_project
    from lingfeng.platform.i18n import set_language, tr
    from lingfeng.platform.preferences import load_preferences
    from lingfeng.platform.paths import user_data_dir

    app = QApplication.instance() or QApplication([])
    app.setApplicationName('Lingfeng')
    set_language(load_preferences(user_data_dir()).get('language'))
    try:
        associate_project()
        QMessageBox.information(None, tr('工程文件类型'), tr('已为当前用户注册 .lfs 工程类型。\n如 Windows 保留了之前的默认应用，请在文件的“打开方式”中选择 Lingfeng.exe。'))
        return 0
    except Exception as exc:
        QMessageBox.warning(None, tr('注册失败'), tr(str(exc)))
        return 1


def main(argv=None):
    """Open an optional project, register .lfs, or run installed-app checks."""
    parser = argparse.ArgumentParser(prog='Lingfeng', description='伶风 Lingfeng — For Pop Music')
    parser.add_argument('project', nargs='?', help='Path to a Lingfeng .lfs or .leadsheet project (schema 5/6)')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--self-test', metavar='OUTPUT', type=Path, help='Run acceptance checks and write their results')
    mode.add_argument('--associate', action='store_true', help='Register this portable application for .lfs files')
    parser.add_argument('--version', action='version', version=f'Lingfeng {__version__}')
    args = parser.parse_args(argv)
    if args.project and (args.self_test is not None or args.associate):
        parser.error('a project path cannot be combined with --self-test or --associate')
    if args.self_test is not None:
        return _self_test(args.self_test)
    if args.associate:
        return _associate()
    try:
        from lingfeng.ui.main_window import run
        return run(args.project)
    except Exception as exc:
        from PySide6.QtWidgets import QApplication, QMessageBox
        from lingfeng.platform.i18n import tr
        app = QApplication.instance() or QApplication([])
        QMessageBox.critical(None, tr('无法打开伶风'), tr(str(exc)))
        return 1

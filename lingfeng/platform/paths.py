"""Shared installation, resource and user paths for source and portable builds.

Resources bundled by PyInstaller live under ``_MEIPASS``; installed synths
live beside the executable. Neither location owns mutable user preferences.
"""
import os
import sys
from pathlib import Path

from lingfeng.platform.i18n import tr


def source_root():
    """Root containing the Python package, including a release's source folder."""
    return Path(__file__).resolve().parents[2]


def resource_root():
    """Root of immutable assets in a checkout or a frozen application."""
    return Path(getattr(sys, '_MEIPASS', source_root()))


def application_root():
    """Installation root for user-installable synth packs."""
    root = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else source_root()
    if root.name == 'source' and (root.parent / 'synths').is_dir():
        return root.parent
    return root


def user_data_dir():
    """Use the explicit test override or Qt's existing per-user app directory."""
    if os.environ.get('LINGFENG_USER_DATA'):
        return Path(os.environ['LINGFENG_USER_DATA'])
    from PySide6.QtCore import QStandardPaths
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))


def documents_dir():
    from PySide6.QtCore import QStandardPaths
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation))


def safe_name(text):
    return ''.join('_' if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in text).strip(' .') or tr('未命名作品')

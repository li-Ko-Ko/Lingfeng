from pathlib import Path
import os
from PySide6.QtGui import QFontDatabase


def ensure_fonts():
    # Qt's offscreen backend on Windows does not enumerate system fonts.
    # Register local fonts explicitly so the renderer and PDF embed real glyphs.
    if 'Microsoft YaHei' in QFontDatabase.families():
        return
    for name in ('msyh.ttc','msyhbd.ttc','segoeui.ttf','seguisym.ttf'):
        path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))

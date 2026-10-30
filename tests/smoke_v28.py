"""Render the two rolls, bass menus and insertion dialog without desktop input."""
import os,sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Context,Chord,Note
from popscore.dialogs import MarkerDialog
from popscore.theme import apply_theme

app=QApplication([]);out=Path(__file__).resolve().parents[1]/'output/screenshots';out.mkdir(exist_ok=True,parents=True)
p=Project(title='长音符 · 跨调式音级');p.contexts=[Context(0,3840,48),Context(3840,7680,56,'Aeolian'),Context(7680,p.end,58,'Dorian')]
p.notes=[Note(480,9600,60),Note(1440,480,64),Note(2400,480,67)]
p.chords=[Chord(0,3840,quality='9'),Chord(3840,7680,quality='9')]
with patch.object(MainWindow,'save_preferences'):
    w=MainWindow(p);w.change_language('zh',False);w.show();w.resize(1280,930);w.timer.stop();w.autosave.stop()
    for b in w.mute_buttons.values():b.setChecked(True)
    w.open_harmony();w.roll.center_pitch(62);w.harmony_window.roll.center_pitch(52)
    w.roll.zoom=78;w.roll.update_ranges();w.sync_time_views(w.roll);w.note_degrees_action.setChecked(True)
    for dark in (True,False):
        apply_theme(dark);QTest.qWait(80);w.grab().save(str(out/f'lingfeng-v28-main-{"dark" if dark else "light"}.png'))
    for language in ('zh','en'):
        w.change_language(language,False);apply_theme(True);QTest.qWait(40)
        menu=w.chord_lane.context_menu(QPoint(round(w.chord_lane.x_at(240)),20))
        for key in ('bass_menu','inversion_menu'):
            sub=getattr(menu,key);sub.show();QTest.qWait(30);sub.grab().save(str(out/f'lingfeng-v28-{key}-{language}.png'));sub.hide()
        menu.deleteLater()
        dialog=MarkerDialog(w.project,1,w,True);dialog.count.setValue(4);dialog.show();QTest.qWait(30)
        dialog.grab().save(str(out/f'lingfeng-v28-insert-{language}.png'));dialog.close();dialog.deleteLater()
    w.melody_window.setFloating(True);w.roll.center_pitch(60);QTest.qWait(50)
    w.melody_window.grab().save(str(out/'lingfeng-v28-floating-en.png'))
    w.dirty=False;w.close();w.deleteLater();app.processEvents()
print('Saved 9 offscreen visual fixtures.')

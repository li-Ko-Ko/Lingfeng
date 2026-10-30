"""Offscreen visual review of the final controls and chord-note selection."""
import os,sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QLabel
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Measure,Context,Chord,Note
from popscore.chordops import chord_details
from popscore.theme import apply_theme
from popscore.notation import export_pdf

app=QApplication([]);root=Path(__file__).resolve().parents[1];out=root/'output/screenshots';out.mkdir(exist_ok=True,parents=True)
p=Project(title='拍号区间与跨调性和弦');p.measures=[Measure(),Measure(),Measure(3,4),Measure()]
p.contexts=[Context(0,3840),Context(3840,p.end,50,'Dorian')]
p.notes=[Note(t,480,k) for t,k in [(960,60),(1920,64),(2880,67),(3840,62),(4800,65),(5760,69),(7680,62),(8640,65)]]
p.put_chord(Chord(960,6720,octave=1));p.put_chord(Chord(7680,2880,50,'m',octave=1));p.validate()
with patch.object(MainWindow,'save_preferences'):
    w=MainWindow(p);w.change_language('zh',False);w.show();w.resize(1280,920);w.timer.stop();w.autosave.stop()
    for b in w.mute_buttons.values():b.setChecked(True)
    w.open_harmony();r=w.harmony_window.roll;r.center_pitch(60);w.roll.center_pitch(65)
    QTest.qWait(100)
    QTest.mouseClick(r.viewport(),Qt.MouseButton.LeftButton,pos=QPoint(round(r.x_at(1600)),round(r.y_at(60)+r.row_height/2)))
    assert len(r.selected_ids)==2
    for dark in (True,False):
        apply_theme(dark);QTest.qWait(70);w.grab().save(str(out/f'lingfeng-v27-main-{"dark" if dark else "light"}.png'))
    w.harmony_window.setFloating(True);w.harmony_window.show();r.center_pitch(60)
    for dark in (True,False):
        apply_theme(dark);QTest.qWait(70);w.harmony_window.grab().save(str(out/f'lingfeng-v27-floating-{"dark" if dark else "light"}.png'))
    tip=QLabel(chord_details(w.project,w.project.chords[0]));tip.setTextFormat(Qt.TextFormat.RichText);tip.setMargin(15);tip.adjustSize();tip.show();QTest.qWait(40)
    tip.grab().save(str(out/'lingfeng-v27-chord-details.png'));tip.close()
    pdf=root/'output/pdf/lingfeng-v27-meter.pdf';pdf.parent.mkdir(exist_ok=True);export_pdf(w.project,pdf)
    w.dirty=False;w.close();w.deleteLater();app.processEvents()
print('Visual fixtures saved; joined note selected in full; PDF exported.')

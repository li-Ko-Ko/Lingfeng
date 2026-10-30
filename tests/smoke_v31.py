"""Offscreen review of drag references, tonal spelling and bilingual guidance."""
import os,sys
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout,QLabel
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Chord,Note,Context
from popscore.theme import apply_theme
from popscore.helpview import HelpDialog
from popscore.dialogs import ChordDialog
from popscore.chordops import chord_details

app=QApplication([]);out=Path(__file__).resolve().parents[1]/'output/screenshots';out.mkdir(exist_ok=True,parents=True)
p=Project(title='选择与拖拽 · 和弦拼写');p.contexts=[Context(0,p.end,53,'Ionian')]
p.chords=[Chord(480,1920,58),Chord(3840,1920,62,'m',pattern='quarters'),Chord(7680,3840,48,'7')]
p.notes=[Note(480,1440,65),Note(2400,960,69),Note(3840,1440,67),Note(6720,2400,72)]
with patch.object(MainWindow,'save_preferences'):
    w=MainWindow(p);w.change_language('zh',False);w.show();w.resize(1280,900);w.timer.stop();w.autosave.stop()
    for button in w.mute_buttons.values():button.setChecked(True)
    r=w.roll;r.zoom=90;r.update_ranges();r.timeViewChanged.emit();r.center_pitch(68);r.tool='smart';app.processEvents()
    for dark in (True,False):
        apply_theme(dark);QTest.qWait(40);lane=w.chord_lane
        lane.selection_event({c.id for c in p.chords[:2]});pos=QPoint(round(lane.x_at(1440)),25)
        QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=pos);QTest.mouseMove(lane,pos+QPoint(135,0));app.processEvents()
        w.grab().save(str(out/f'lingfeng-v31-chord-ghost-{"dark" if dark else "light"}.png'))
        QTest.keyClick(lane,Qt.Key.Key_Escape);QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=pos+QPoint(135,0))
    apply_theme(True);w.select_element('notes',r);r.selected_ids={n.id for n in p.notes[:2]};r.refresh();app.processEvents()
    n=p.notes[0];pos=QPoint(round(r.x_at(n.start+480)),round(r.y_at(n.pitch)+r.row_height/2))
    QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=pos);QTest.mouseMove(r.viewport(),pos+QPoint(135,-r.row_height));app.processEvents()
    w.grab().save(str(out/'lingfeng-v31-note-ghost.png'))
    QTest.keyClick(r,Qt.Key.Key_Escape);QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=pos)
    for language in ('zh','en'):
        w.change_language(language,False);app.processEvents()
        dialog=ChordDialog(p.chords[0],p,w);dialog.show();QTest.qWait(30)
        dialog.grab().save(str(out/f'lingfeng-v31-chord-dialog-{language}.png'));dialog.close();dialog.deleteLater()
        tooltip=QDialog(w);box=QVBoxLayout(tooltip);label=QLabel(chord_details(p,p.chords[0]));label.setMargin(12);box.addWidget(label)
        tooltip.show();QTest.qWait(20);tooltip.grab().save(str(out/f'lingfeng-v31-chord-tones-{language}.png'));tooltip.close();tooltip.deleteLater()
        help=HelpDialog(w);help.list.setCurrentRow(next(i for i,page in enumerate(help.pages) if '预览' in page[0] or 'preview' in page[0].lower()));help.show();QTest.qWait(30)
        help.grab().save(str(out/f'lingfeng-v31-help-{language}.png'));help.close();help.deleteLater()
    w.dirty=False;w.close();w.deleteLater();app.processEvents()
print('Saved 9 offscreen visual fixtures.')

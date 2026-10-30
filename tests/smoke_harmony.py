"""Real Qt mouse interactions against our own application."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from popscore.app import MainWindow,STYLE
from popscore.model import Project,Chord,demo_project

app=QApplication.instance() or QApplication([]);app.setStyle('Fusion');app.setStyleSheet(STYLE)
# Turn unexpected validation dialogs into test failures instead of hanging.
def fail_dialog(*args):raise AssertionError(str(args[1:]))
QMessageBox.warning=fail_dialog
p=Project();p.chords=[Chord(480,7200,notes=[],recognized=False)]
w=MainWindow(p);w.show();app.processEvents();w.open_harmony(p.chords[0].id);w.harmony_window.setFloating(True);app.processEvents()
f=w.harmony_window;r=f.roll;r.center_pitch(64);app.processEvents()
assert f.isVisible() and not f.isModal()
# Polyphonic Draw adds three voices at the same free beat.
f.tool.setCurrentIndex(f.tool.findData('draw'))
for pitch in [60,64,67]:
    a=QPoint(round(r.x_at(960)+8),round(r.y_at(pitch)+10));b=QPoint(round(r.x_at(1920)),a.y())
    QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=a);QTest.qWait(310);QTest.mouseMove(r.viewport(),b)
    QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=b);app.processEvents()
assert len(w.project.harmony_notes())==3
assert w.project.chords[0].name=='C'
# The velocity panel edits the selected voice; other voices keep their velocity.
f.view_controls.panel_actions['velocity'].setChecked(True);app.processEvents()
n=w.project.harmony_notes()[-1];r.selected_note=n.id
a=QPoint(round(r.x_at(n.start)+4),40)
QTest.mousePress(r.velocity_lane,Qt.MouseButton.LeftButton,pos=a)
QTest.mouseRelease(r.velocity_lane,Qt.MouseButton.LeftButton,pos=a);app.processEvents()
assert next(n for n in w.project.harmony_notes() if n.id==r.selected_note).velocity<60
# Undo history is shared between windows.
count=len(w.undo_history);w.undo();assert len(w.undo_history)==count-1;w.redo()
# Draw inserts or deletes on click. Fill is no longer exposed.
assert f.tool.findData('fill')==-1
f.tool.setCurrentIndex(f.tool.findData('draw'))
r.center_pitch(66);app.processEvents()
pos=QPoint(round(r.x_at(2400)+3),round(r.y_at(72)+10))
QTest.mouseClick(r.viewport(),Qt.MouseButton.LeftButton,pos=pos);app.processEvents();assert len(w.project.harmony_notes())==4
QTest.qWait(app.doubleClickInterval()+120)
QTest.mouseClick(r.viewport(),Qt.MouseButton.LeftButton,pos=pos);app.processEvents();assert len(w.project.harmony_notes())==3
# Free-time chord movement is snapped to quarter beats, not measures.
app.processEvents();c=w.project.chords[0]
pos=QPoint(round(r.x_at(c.start)+30),r.ruler_height-12);target=QPoint(pos.x()+round(r.zoom/2),pos.y())
QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=pos);QTest.mouseMove(r.viewport(),target)
QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=target);app.processEvents()
assert w.project.chords[0].start==960
assert min(n.start for n in w.project.harmony_notes())==1440
# Shared horizontal origin and zoom; track volumes persist and undo together.
f.sync.setChecked(True);r.horizontalScrollBar().setValue(800);app.processEvents();assert w.roll.horizontalScrollBar().value()==800
w.volume_sliders['melody'].setValue(63);w.volume_sliders['chords'].setValue(37);w.commit_volume()
assert w.project.volumes=={'melody':63,'chords':37}
w.undo();assert w.project.volumes=={'melody':100,'chords':90}
# Pattern replaces performed notes, undo restores custom voicing.
w.chord_command('pattern:up',{w.project.chords[0].id})
assert w.project.chords[0].notes is None and w.project.chords[0].pattern=='up'
w.undo();assert w.project.chords[0].notes is not None
w.switch_workspace('score');app.processEvents();assert not f.isVisible()
# Capture both editors for inspection with a varied demo accompaniment.
w.dirty=False;w.replace_project(demo_project());w.switch_workspace('compose');w.roll.center_pitch(58)
w.open_harmony(w.project.chords[9].id);f.sync.setChecked(False);f.roll.ensure_tick(9*3840);f.roll.center_pitch(53);app.processEvents()
Path('output/screenshots').mkdir(parents=True,exist_ok=True)
f.grab().save('output/screenshots/harmony.png');w.grab().save('output/screenshots/compose-v4.png')
w.dirty=False;f.close();w.close();app.processEvents()
print('Harmony UI smoke passed: draw, polyphony, velocity, click delete, drag, undo, optional sync, volume, patterns.')

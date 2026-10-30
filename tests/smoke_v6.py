"""End-to-end selection, bilingual narrow layouts, docking and tied score regression."""
import os,copy
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QTimer,QRect
from PySide6.QtWidgets import QApplication,QMessageBox,QLabel,QPushButton,QComboBox,QWidget
from PySide6.QtGui import QImage,QPainter
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Note,Chord,demo_project
from popscore.notation import ScoreLayout,export_pdf
from popscore.dialogs import ChordDialog

app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
def fail(*args):raise AssertionError(str(args[1:]))
QMessageBox.warning=fail
p=Project();p.notes=[Note(i*480,480,pitch) for i,pitch in enumerate([48,50,53,52])]
w=MainWindow(p);w.show();QTest.qWait(50);w.roll.center_pitch(51)
w.mute_buttons['melody'].click();w.mute_buttons['chords'].click()
def point(tick,pitch):return QPoint(round(w.roll.x_at(tick)),round(w.roll.y_at(pitch)+10))
def drag(a,b):
    QTest.mousePress(w.roll.viewport(),Qt.MouseButton.LeftButton,pos=a);QTest.mouseMove(w.roll.viewport(),b);QTest.mouseRelease(w.roll.viewport(),Qt.MouseButton.LeftButton,pos=b);app.processEvents()
drag(point(0,55),point(2160,46));assert len(w.roll.selected_ids)==4
menu=w.roll.timeline_menu(point(960,54));copies=next(a.menu() for a in menu.actions() if a.text()=='复制音符')
next(a for a in copies.actions() if '时间反向' in a.text()).trigger();assert w.note_clipboard
target=point(3840,55);QTest.mouseClick(w.roll.viewport(),Qt.MouseButton.LeftButton,pos=target);app.processEvents()
w.roll.setFocus();QTest.keyClick(w.roll,Qt.Key.Key_V,Qt.KeyboardModifier.ControlModifier);app.processEvents()
assert [n.pitch for n in w.project.notes if n.start>=3840]==[52,53,50,48]
assert len(w.roll.selected_ids)==4
QTest.keyClick(w.roll,Qt.Key.Key_Up,Qt.KeyboardModifier.AltModifier);app.processEvents()
assert [n.pitch for n in w.project.notes if n.start>=3840]==[53,55,52,50]
w.undo();w.undo();assert len(w.project.notes)==4
# Resize a note into a same-pitch neighbor: one interval remains, then undo restores both.
w.project.notes=[Note(0,480,60),Note(480,480,60)];w.refresh();w.roll.center_pitch(60);app.processEvents()
drag(point(480,60)-QPoint(3,0),point(720,60));assert len(w.project.notes)==1 and w.project.notes[0].duration==960
w.undo();assert len(w.project.notes)==2
w.roll.selected_ids={n.id for n in w.project.notes};w.note_command(w.roll,'join');assert len(w.project.notes)==1
w.note_command(w.roll,'split');assert len(w.project.notes)==4
# A score blank-space paste targets its actual snapped time, without changing the key.
w.note_command(w.roll,'copy:direct');w.switch_workspace('score');app.processEvents()
before=len(w.project.notes);w.score_view.canvas.pasteRequested.emit(3840);app.processEvents();assert len(w.project.notes)==before+4
w.undo();w.switch_workspace('compose')
# Language changes preserve project, clipboard, selection, muted state and undo history.
snapshot=w.project.to_dict();history=len(w.undo_history);w.seek(960);w.change_language('en',False);QTest.qWait(50)
assert w.project.to_dict()==snapshot and len(w.undo_history)==history and w.note_clipboard
assert w.tool.currentText()=='Smart' and w.playhead==960 and w.tool.count()==2
assert all(b.isChecked() for b in w.mute_buttons.values())
w.dirty=False;w.replace_project(demo_project());w.set_theme('dark')
Path('output/screenshots').mkdir(parents=True,exist_ok=True)
w.resize(960,1000);QTest.qWait(80);w.roll.center_pitch(60);w.grab().save('output/screenshots/english-half-v6.png')
w.open_harmony(w.project.chords[0].id);QTest.qWait(80);f=w.harmony_window
assert any(f.roll.ruler_height<=f.roll.y_at(n.pitch)<f.roll.viewport().height() for n in f.current().render_notes())
assert not f.isFloating();f.setFloating(True);QTest.qWait(60);f.setFloating(False);QTest.qWait(100);assert not f.isFloating() and f.parentWidget() is w.tracks
assert w.roll.viewport().mapTo(w,QPoint(66,0)).x()==f.roll.viewport().mapTo(w,QPoint(66,0)).x()
w.grab().save('output/screenshots/english-docked-v6.png')
# At 640 pixels, shared controls stay outside the roll viewport.
for width in (960,720,640):
    w.resize(width,1000);QTest.qWait(100);assert w.width()==width,(width,w.size())
    rect=QRect(w.roll.mapTo(w,QPoint(0,0)),w.roll.size())
    for control in [w.tool,w.grid,w.length,w.view_controls,w.mute_buttons['melody'],w.mute_buttons['chords']]:
        control_rect=QRect(control.mapTo(w,QPoint(0,0)),control.size())
        assert not control_rect.intersects(rect),(width,control_rect,rect)
w.grab().save('output/screenshots/english-narrow-v6.png')
dialog=ChordDialog(w.project.chords[0],w.project,w);dialog.show();QTest.qWait(30)
assert dialog.quality.currentText()=='Major triad'
assert all(not any('\u4e00'<=c<='\u9fff' for c in label.text()) for label in dialog.findChildren(QLabel));dialog.close()
f.setFloating(True);QTest.qWait(80);assert f.isFloating();f.resize(720,650);QTest.qWait(60);f.grab().save('output/screenshots/chord-floating-v6.png')
w.change_language('zh',False);QTest.qWait(80);assert w.tool.currentText()=='智能工具'
w.resize(960,1000);w.harmony_window.setFloating(False);QTest.qWait(80)
assert any(w.roll.ruler_height<=w.roll.y_at(n.pitch)<w.roll.viewport().height() for n in w.project.notes)
assert any(w.harmony_window.roll.ruler_height<=w.harmony_window.roll.y_at(n.pitch)<w.harmony_window.roll.viewport().height() for n in w.harmony_window.current().render_notes())
w.grab().save('output/screenshots/chinese-docked-v6.png')
w.dirty=False;w.close();app.processEvents()
# Reproduce the attachment: a late bar-3 note continuing into bar 4.
repro=Project(title='跨小节延音线验证');repro.notation.update(style='traditional',per_line=4)
repro.notes=[Note(11040,720,57),Note(15120,480,55)];repro.chords=[Chord(i*3840,3840,48) for i in range(len(repro.measures))]
layout=ScoreLayout(repro);image=QImage(900,1273,QImage.Format.Format_RGB32);painter=QPainter(image);layout.draw(painter,0);painter.end()
assert [kind for nid,kind,_ in layout.tie_paths if nid==repro.notes[0].id]==['continuous']
image.save('output/screenshots/ties-fixed-v6.png');Path('output/pdf').mkdir(parents=True,exist_ok=True)
export_pdf(repro,'output/pdf/ties-fixed-v6.pdf');repro.save('examples/ties-regression.popscore')
print('v0.6 UI passed: marquee, transformed clipboard, paste, in-scale shift, union resize, join/split, language, 640/720/960 px layouts, docking, score paste, continuous ties.')

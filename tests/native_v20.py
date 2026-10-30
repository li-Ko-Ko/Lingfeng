"""Windows gestures for contextual keys, docking defaults and nearest-lane hover."""
import os,sys,json
os.environ['QT_QPA_PLATFORM']='windows'
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication,QMessageBox,QDialogButtonBox
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Note,Chord
from popscore.keybindings import normalized,KeyBindingsDialog
from popscore.recognition import chord_inversion

app=QApplication([]);app.setStyle('Fusion');errors=[]
def error_hook(typ,value,tb):errors.append(str(value));sys.__excepthook__(typ,value,tb)
sys.excepthook=error_hook
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
p=Project();p.title='调内和弦移动与窗口联动';p.notes=[Note(i*960,720,n) for i,n in enumerate((60,62,64,67,69,67,64,62))]
p.chords=[Chord(0,3840,48,'',4),Chord(3840,3840,55)]
w=MainWindow(p);w.change_language('zh',False);w.keybindings=normalized({});w.set_theme('dark');w.show()
area=app.primaryScreen().availableGeometry();w.resize(min(1240,area.width()-40),area.height()-60);w.timer.stop();w.autosave.stop()
for mute in w.mute_buttons.values():mute.setChecked(True)
QTest.qWait(50);r=w.roll;r.selected_ids={p.notes[0].id};r.setFocus();w.activateWindow();app.processEvents()
QTest.keyClick(r,Qt.Key.Key_W);assert w.project.notes[0].pitch==61
QTest.keyClick(r,Qt.Key.Key_S);assert w.project.notes[0].pitch==60
QTest.keyClick(r,Qt.Key.Key_W,Qt.KeyboardModifier.AltModifier);assert w.project.notes[0].pitch==62
main=w.chord_lane;point=QPoint(round(main.x_at(960)),25);QTest.mouseClick(main,Qt.MouseButton.LeftButton,pos=point);QTest.keyClick(main,Qt.Key.Key_W)
assert w.project.chords[0].name=='Dm/F' and chord_inversion(w.project.chords[0])==1
w.open_harmony(w.project.chords[0].id);QTest.qWait(50)
assert not w.visibility_actions['chords'].isChecked() and not main.isVisible() and w.harmony_window.top_lane.isVisible()
shots=Path('output/screenshots');shots.mkdir(exist_ok=True,parents=True)
w.roll.set_compact(True);w.sync_views(w.roll);QTest.qWait(30);w.grab().save(str(shots/'lingfeng-v20-docked.png'))
h=w.harmony_window.roll.lane;h.selection_event(set());main.selection_event(set());h.hover_event('');main.hover_event('')
point=QPoint(round(h.x_at(4800)),25);assert app.widgetAt(h.mapToGlobal(point)) is h
# Deliver a hover event through Qt; OS cursor warps may be suppressed in headless sessions.
app.sendEvent(h,QMouseEvent(QEvent.Type.MouseMove,QPointF(point),QPointF(h.mapToGlobal(point)),Qt.MouseButton.NoButton,Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier))
assert w.roll.chord_highlights=={w.project.chords[1].id}
w.visibility_actions['chords'].setChecked(True);QTest.qWait(20);assert main.isVisible() and not w.roll.chord_highlights
h.hover_event(w.project.chords[0].id);assert not w.roll.chord_highlights
main.hover_event(w.project.chords[1].id);assert w.roll.chord_highlights=={w.project.chords[1].id}
w.harmony_window.setFloating(True);w.melody_window.setFloating(True);QTest.qWait(40)
assert main.isVisible() and r.lane.isVisible() and h.isVisible() and not w.roll.chord_highlights
r.lane.hover_event(w.project.chords[0].id);h.hover_event(w.project.chords[1].id);assert w.roll.chord_highlights=={w.project.chords[0].id}
w.harmony_window.close();QTest.qWait(40);assert not w.harmony_window.isFloating() and w.harmony_window.isVisible() and not main.isVisible() and r.lane.isVisible()
w.melody_window.setFloating(False);QTest.qWait(30);assert not main.isVisible() and not r.lane.isVisible() and h.isVisible()
w.change_language('en',False);w.harmony_window.setFloating(True);w.harmony_window.resize(900,area.height()-100);QTest.qWait(30)
menu=w.harmony_window.roll.lane.context_menu(QPoint(round(w.harmony_window.roll.lane.x_at(960)),25));assert menu.move_menu.title()=='Move chord';assert menu.move_menu.actions()[0].isEnabled()
menu.move_menu.popup(w.harmony_window.mapToGlobal(QPoint(130,100)));QTest.qWait(30);menu.move_menu.grab().save(str(shots/'lingfeng-v20-chord-movement-en.png'));menu.close();menu.move_menu.close()
dialog=KeyBindingsDialog(w.keybindings,w);dialog.resize(560,min(650,area.height()-80));dialog.show();QTest.qWait(30)
buttons=dialog.findChild(QDialogButtonBox);assert dialog.rect().contains(buttons.mapTo(dialog,buttons.rect().center()))
dialog.grab().save(str(shots/'lingfeng-v20-shortcuts-en.png'));dialog.close()
report=dict(status='passed',dpi_scale=w.devicePixelRatioF(),note_semitones_and_scale_keys=True,chord_keys_preserve_inversion=True,docking_defaults=True,close_redocks_chord_roll=True,manual_dual_lane_override=True,nearest_lane_hover_only=True,one_default_lane_per_window=True,english_menus=True,scrollable_shortcuts=True,qt_callback_errors=errors)
assert not errors,errors
out=Path('output/native-v20');out.mkdir(exist_ok=True,parents=True);(out/'result.json').write_text(json.dumps(report,indent=2),'utf-8')
w.dirty=False;w.close();app.processEvents();assert not errors,errors;print(json.dumps(report))

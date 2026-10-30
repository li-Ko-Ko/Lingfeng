"""Native Windows verification of chord keys, bar-phase drags and menus."""
import os,sys,json,copy
os.environ['QT_QPA_PLATFORM']='windows'
from pathlib import Path
from PySide6.QtCore import Qt,QPoint,QPointF,QEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Chord,Note
from popscore.keybindings import normalized
from popscore.rhythm import analyze
from tests.music_reference import bar_events

app=QApplication([]);app.setStyle('Fusion');errors=[]
def error_hook(typ,value,tb):errors.append(str(value));sys.__excepthook__(typ,value,tb)
sys.excepthook=error_hook
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
sig=lambda notes:sorted((n.start,n.duration,n.pitch,n.velocity) for n in notes)
p=Project();p.title='小节节奏与根音快捷操作';p.chords=[Chord(0,3840,48,'',4),Chord(3840,3840,55)]
w=MainWindow(p);w.change_language('zh',False);w.keybindings=normalized({});w.set_theme('dark');w.show()
area=app.primaryScreen().availableGeometry();w.resize(min(1240,area.width()-40),area.height()-60);w.timer.stop();w.autosave.stop()
for mute in w.mute_buttons.values():mute.setChecked(True)
QTest.qWait(50);lane=w.chord_lane;pos=QPoint(round(lane.x_at(960)),25)
assert app.widgetAt(lane.mapToGlobal(pos)) is lane
w.activateWindow();QTest.mouseClick(lane,Qt.MouseButton.LeftButton,pos=pos);lane.setFocus();app.processEvents()
head=w.playhead;w.toggle_play();worker=w.transport.thread;clock=w.transport.start_time
QTest.keyClick(lane,Qt.Key.Key_W);assert w.project.chords[0].name=='C#'
QTest.keyClick(lane,Qt.Key.Key_S);assert w.project.chords[0].name=='C'
QTest.keyClick(lane,Qt.Key.Key_W,Qt.KeyboardModifier.AltModifier);assert w.project.chords[0].name=='Dm'
QTest.keyClick(lane,Qt.Key.Key_S,Qt.KeyboardModifier.AltModifier);assert w.project.chords[0].name=='C'
QTest.keyClick(lane,Qt.Key.Key_Tab);assert lane.editor.selected_chords=={w.project.chords[1].id}
QTest.keyClick(lane,Qt.Key.Key_Tab);assert lane.editor.selected_chords=={w.project.chords[0].id}
assert w.playhead==head and w.transport.thread is worker and w.transport.start_time==clock and w.transport.playing
w.stop();w.open_harmony(w.project.chords[0].id);w.harmony_window.setFloating(True);QTest.qWait(30)
floated=w.harmony_window.roll.lane;floated.setFocus();w.harmony_window.activateWindow();app.processEvents()
floated.selection_event({w.project.chords[0].id});floated.editor.edit_target='chords'
main_selection=set(w.main_roll.selected_chords);QTest.keyClick(floated,Qt.Key.Key_Tab)
assert floated.editor.selected_chords=={w.project.chords[1].id} and w.main_roll.selected_chords==main_selection
w.harmony_window.setFloating(False);QTest.qWait(30)

p=Project();p.put_chord(Chord(960,3840,48,'',4,pattern='up',velocity=73));w.replace_project(p)
w.open_harmony(p.chords[0].id);w.harmony_window.roll.grid=240;lane=w.harmony_window.roll.lane
for n in p.chords[0].notes:n.velocity=112
w.refresh();QTest.qWait(30)
def drag(start_tick,end_tick,hold=False):
    a=QPoint(round(lane.x_at(start_tick)),25);b=QPoint(round(lane.x_at(end_tick)),25)
    QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=a)
    if hold:QTest.qWait(300)
    app.sendEvent(lane,QMouseEvent(QEvent.Type.MouseMove,QPointF(b),QPointF(lane.mapToGlobal(b)),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier))
    QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=b);QTest.qWait(25)
drag(4790,5760,True);c=w.project.chords[0];assert (c.start,c.end)==(960,5760)
assert sig(c.render_notes())==bar_events(c,w.project,c.start,c.end) and {n.velocity for n in c.notes}=={73}
drag(970,1680,True);c=w.project.chords[0];assert (c.start,c.end)==(1680,5760)
assert sig(c.render_notes())==bar_events(c,w.project,c.start,c.end) and analyze(c,w.project).pattern=='up'
drag(2160,2640);c=w.project.chords[0];assert (c.start,c.end)==(2160,6240)
assert sig(c.render_notes())==bar_events(c,w.project,c.start,c.end)
w.undo();w.redo();assert sig(w.project.chords[0].render_notes())==bar_events(c,w.project,c.start,c.end)

p=Project();p.title='同一小节 · 四个和弦共用琶音型'
for i,(root,quality) in enumerate(((48,''),(53,''),(55,''),(57,'m'))):p.put_chord(Chord(i*960,960,root,quality,pattern='up'))
p.notes=[Note(i*480,400,n) for i,n in enumerate((60,64,65,69,67,71,69,72))]
w.replace_project(p);w.open_harmony(p.chords[0].id);w.roll.set_compact(True);w.harmony_window.roll.set_compact(True);QTest.qWait(30)
shots=Path('output/screenshots');shots.mkdir(exist_ok=True,parents=True)
w.grab().save(str(shots/'lingfeng-v21-bar-patterns-zh.png'))
w.change_language('en',False);w.harmony_window.setFloating(True);w.harmony_window.resize(min(900,area.width()-80),area.height()-100);QTest.qWait(40)
lane=w.harmony_window.roll.lane;lane.selection_event({p.chords[0].id});menu=lane.context_menu(QPoint(round(lane.x_at(480)),25))
assert menu.inversion_menu.title()=='Chord inversion' and all(not a.isCheckable() for a in menu.inversion_menu.actions())
assert menu.move_menu.actions()[0].text()=='Root up one semitone (root position)'
for submenu,name in ((menu.inversion_menu,'bass-en'),(menu.move_menu,'movement-en')):
    submenu.popup(w.harmony_window.mapToGlobal(QPoint(130,100)));QTest.qWait(30)
    submenu.grab().save(str(shots/f'lingfeng-v21-{name}.png'));submenu.close()
menu.close();assert not errors,errors
report=dict(status='passed',dpi_scale=w.devicePixelRatioF(),root_semitone_and_diatonic_keys=True,both_restore_root_bass=True,
    tab_wraps_without_seeking=True,floating_tab_isolated=True,live_edit_keeps_worker=True,mouse_edges_and_move_use_bar_phase=True,
    recognized_velocity_resets=True,undo_redo=True,english_bass_menu_not_checkable=True,qt_callback_errors=errors)
out=Path('output/native-v21');out.mkdir(exist_ok=True,parents=True);(out/'result.json').write_text(json.dumps(report,indent=2),'utf-8')
w.dirty=False;w.close();app.processEvents();assert not errors,errors;print(json.dumps(report))

"""Native context routing, shared harmony location and mixed-meter score layout."""
import os,sys,json,faulthandler
faulthandler.enable();faulthandler.dump_traceback_later(20)
os.environ['QT_QPA_PLATFORM']='windows'
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint,QPointF,QTimer
from PySide6.QtGui import QContextMenuEvent
from PySide6.QtWidgets import QApplication,QMessageBox,QMenu
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Note,Chord
from popscore.rhythm import analyze

app=QApplication([]);app.setStyle('Fusion');errors=[]
def error_hook(typ,value,tb):errors.append(str(value));sys.__excepthook__(typ,value,tb)
sys.excepthook=error_hook
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
p=Project();p.title='菜单与混合调性';p.set_markers([1],53,'Dorian',3,4);p.set_markers([2],50,'Ionian',4,4)
p.notes=[Note(p.starts[b]+i*480,400,60+(i%3)*2) for b in range(4) for i in range(3)]
for b in range(4):p.put_chord(Chord(p.starts[b],p.measures[b].ticks,48 if b%2==0 else 53,pattern='up'))
w=MainWindow(p);w.change_language('zh',False);w.set_theme('dark');w.show();area=app.primaryScreen().availableGeometry();w.resize(min(1250,area.width()-40),area.height()-60);w.timer.stop();w.autosave.stop()
for mute in w.mute_buttons.values():mute.setChecked(True)
print('native: window ready',flush=True)
QTest.qWait(50);w.activateWindow();r=w.roll;r.selected_ids={n.id for n in p.notes[:3]};r.refresh()
point=QPoint(round(w.timeline.x_at(480)),15);captured=[];print('native: timeline context',flush=True)
def close_popup():
    menu=app.activePopupWidget()
    if isinstance(menu,QMenu):captured.append([a.text() for a in menu.actions()]);menu.close()
closer=QTimer();closer.setInterval(50);closer.timeout.connect(close_popup);closer.start()
app.sendEvent(w.timeline,QContextMenuEvent(QContextMenuEvent.Reason.Mouse,point,w.timeline.mapToGlobal(point)));closer.stop()
print('native: context delivered',flush=True)
assert captured and not any('音符' in label or '和弦' in label for label in captured[0])
shots=Path('output/screenshots');shots.mkdir(parents=True,exist_ok=True)
timeline_menu=w.timeline.roll.timeline_menu(QPoint(round(w.timeline.roll.x_at(480)),15))
timeline_menu.popup(w.timeline.mapToGlobal(point));QTest.qWait(30);timeline_menu.grab().save(str(shots/'lingfeng-v22-timeline-zh.png'));timeline_menu.close()
lane=w.chord_lane;menu=lane.context_menu(QPoint(round(lane.x_at(480)),25))
assert not r.selected_ids and p.chords[0].id in lane.highlight_ids
menu.popup(lane.mapToGlobal(QPoint(round(lane.x_at(480)),25)));QTest.qWait(30)
assert p.chords[0].id in w.roll.chord_highlights
menu.grab().save(str(shots/'lingfeng-v22-chord-menu-zh.png'));menu.close()
lane.selection_event({c.id for c in p.chords[:2]});multi=lane.context_menu(QPoint(round(lane.x_at(480)),25))
assert [a.text() for a in menu.actions()]==[a.text() for a in multi.actions()]
assert not multi.root_menu.isEnabled();multi.custom_rhythm_action.trigger();assert all(c.custom_rhythm and analyze(c,p) is None for c in w.project.chords[:2])
w.open_harmony(p.chords[-1].id);w.harmony_window.setFloating(True);w.open_harmony(p.chords[-1].id);QTest.qWait(40)
assert w.harmony_window.roll.selected_chords=={p.chords[-1].id}
w.harmony_window.setFloating(False);w.switch_workspace('score');w.score_tabs.setCurrentIndex(2);head=w.playhead
w.open_score_roll('chords',p.chords[2].start);QTest.qWait(40);assert w.score_tabs.currentIndex()==1 and w.playhead==head
w.edit_toggle.setChecked(False);w.toggle_editor();QTest.qWait(30)
w.grab().save(str(shots/'lingfeng-v22-mixed-key-meter-zh.png'))
w.switch_workspace('compose');w.change_language('en',False);w.open_harmony(p.chords[0].id);QTest.qWait(25)
lane=w.harmony_window.roll.lane;lane.selection_event({c.id for c in w.project.chords[:2]});menu=lane.context_menu(QPoint(round(lane.x_at(480)),25))
assert any(a.text()=='Audition actual chords' and a.isEnabled() for a in menu.actions())
assert menu.custom_rhythm_action.isChecked() and not menu.root_menu.isEnabled()
menu.popup(lane.mapToGlobal(QPoint(100,20)));QTest.qWait(30);menu.grab().save(str(shots/'lingfeng-v22-multi-chord-en.png'));menu.close()
assert not errors,errors
report=dict(status='passed',dpi_scale=w.devicePixelRatioF(),native_timeline_context_isolated=True,right_click_persistent_highlight=True,
    note_chord_selection_exclusive=True,stable_single_multi_menu=True,custom_lock_action=True,existing_harmony_reused=True,score_chord_tab_and_position=True,
    english_menu=True,qt_callback_errors=errors)
out=Path('output/native-v22');out.mkdir(parents=True,exist_ok=True);(out/'result.json').write_text(json.dumps(report,indent=2),'utf-8')
faulthandler.cancel_dump_traceback_later();w.dirty=False;w.close();app.processEvents();assert not errors,errors;print(json.dumps(report))

"""Native high-DPI gestures for overwrite, lyric entry and rhythm refresh."""
import os,sys,json,time,copy
os.environ['QT_QPA_PLATFORM']='windows'
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox,QMenu
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Chord,Note
from popscore.rhythm import analyze
from popscore.lyrics import put,matching_issues

app=QApplication([]);app.setStyle('Fusion');errors=[]
def error_hook(typ,value,tb):
    errors.append(str(value));sys.__excepthook__(typ,value,tb)
sys.excepthook=error_hook
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
p=Project();p.title='覆盖编辑与节奏识别';p.bpm=84
p.notes=[Note(0,960,60,100),Note(960,1920,60,75),Note(0,2880,64,85)]
p.chords=[Chord(0,3840,48,'7',4,notes=[Note(0,3840,k,v) for k,v in [(40,70),(52,85),(55,90),(58,76),(60,88),(64,94)]])]
put(p,3000,'旧');assert matching_issues(p)
w=MainWindow(p);w.change_language('zh',False);w.set_theme('dark');w.show();w.resize(1100,800);w.timer.stop();w.autosave.stop()
for mute in w.mute_buttons.values():mute.setChecked(True)
r=w.roll;r.set_compact(False);r.tool='smart';r.grid=480;QTest.qWait(70);r.center_pitch(60);QTest.qWait(20)
w.seek(0);w.toggle_play();worker=w.transport.thread;clock=w.transport.start_time
a=QPoint(round(r.x_at(960)-3),round(r.y_at(60)+r.row_height/2));b=QPoint(round(r.x_at(1920)),a.y())
assert r.note_hit(QPointF(a)),(a,r.viewport().size(),r.y_at(60))
QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,pos=a);QTest.qWait(310);QTest.mouseMove(r.viewport(),b);QTest.qWait(20);QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,pos=b)
assert [(n.start,n.end) for n in w.project.notes if n.pitch==60]==[(0,1920),(1920,2880)],[(n.start,n.end,n.pitch) for n in w.project.notes]
assert w.transport.playing and w.transport.thread is worker and w.transport.start_time==clock
r.selected_ids={n.id for n in w.project.notes if n.start==0};w.note_command(r,'copy:direct')
menu=QMenu();r.selection_menu(menu,960);paste=next(a for a in menu.actions() if a.text()=='在此粘贴音符');assert paste.isEnabled();paste.trigger();w.project.validate()
assert {n.pitch for n in w.project.notes if n.start==960}=={60,64}
w.stop();w.open_harmony();w.harmony_window.setFloating(True);w.harmony_window.resize(880,650);r=w.harmony_window.roll;r.grid=480;QTest.qWait(70)
lane=r.lane;box,c=lane.boxes[0];a=QPoint(round(box.right()-2),25);b=QPoint(round(lane.x_at(1920)),25)
QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=a);QTest.qWait(310);QTest.mouseMove(lane,b)
assert analyze(lane.preview).pattern=='block'
t=time.perf_counter();QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=b);elapsed=(time.perf_counter()-t)*1000
assert w.project.chords[0].end==1920 and analyze(w.project.chords[0]).pattern=='block'
assert '持续柱式' in w.harmony_window.summary.toolTip()
w.chord_selection(set());w.chord_selection({c.id},r);assert not w.roll.selected_chords
shots=Path('output/screenshots');shots.mkdir(parents=True,exist_ok=True)
QTest.qWait(40);w.harmony_window.grab().save(str(shots/'lingfeng-v19-harmony-floating.png'))
box,c=lane.boxes[0];a=QPoint(round(box.right()-2),25);b=QPoint(round(lane.x_at(4800)),25)
QTest.mousePress(lane,Qt.MouseButton.LeftButton,pos=a);QTest.qWait(310);QTest.mouseMove(lane,b);QTest.mouseRelease(lane,Qt.MouseButton.LeftButton,pos=b)
assert all(n.start==0 and n.end==4800 for n in w.project.harmony_notes())
assert {n.pitch:n.velocity for n in w.project.harmony_notes()}=={40:70,52:85,55:90,58:76,60:88,64:94}
# Main lane resizing only changes the stored region, with no inferred-pattern fill.
main=w.chord_lane;old=copy.deepcopy(w.project.chords[0]);main.drag=('end',old,4800);main.move_to(QPointF(main.x_at(5760),25))
assert main.preview.end==5760 and all(n.end==4800 for n in main.preview.render_notes());main.drag=None;main.preview=None
w.harmony_window.setFloating(False);QTest.qWait(40);w.grab().save(str(shots/'lingfeng-v19-compose.png'))
QTest.mouseClick(w.score_button,Qt.MouseButton.LeftButton);assert w.workspace=='score' and matching_issues(w.project)
panel=w.lyric_panel;panel.start.setValue(1);panel.count.setValue(1);panel.text.setPlainText('太多歌词不能匹配');before=w.project.to_dict();panel.commit();assert before==w.project.to_dict() and not panel.check()
w.change_language('en',False);w.switch_workspace('compose');w.resize(700,850);QTest.qWait(50);w.grab().save(str(shots/'lingfeng-v19-compose-en-narrow.png'))
assert not errors,errors
report=dict(status='passed',dpi_scale=w.devicePixelRatioF(),real_edge_drag_overwrite=True,polyphonic_overlap_paste=True,immediate_shrink_recognition=True,chord_resize_release_ms=round(elapsed,1),custom_voicing_and_dynamics_preserved=True,score_entry_ignores_stale_lyrics=True,invalid_lyric_entry_rejected=True,live_edit_preserves_worker=True,qt_callback_errors=errors)
out=Path('output/native-v19');out.mkdir(parents=True,exist_ok=True);(out/'result.json').write_text(json.dumps(report,indent=2),'utf-8')
w.dirty=False;w.close();app.processEvents();assert not errors,errors;print(json.dumps(report))

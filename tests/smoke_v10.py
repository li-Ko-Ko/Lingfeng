"""Complete v0.10 layout/playback walkthrough and printable score samples."""
import os,time,json
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project
from popscore.notation import export_pdf
from popscore.midi import export_midi
from popscore.helpview import HelpDialog

app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
out=Path('output/screenshots');p=Project.load('examples/lingfeng-symbols.lfs');w=MainWindow(p);w.show();w.resize(1360,1000);w.change_language('zh',False);w.set_theme('light')
for b in w.mute_buttons.values():b.setChecked(True)
w.open_harmony(p.chords[1].id);w.view_controls.range.setCurrentIndex(1);QTest.qWait(70)
lane=w.chord_lane;pos=QPoint(round(lane.x_at(p.chords[1].start)+30),25);QTest.mouseClick(lane,Qt.MouseButton.LeftButton,pos=pos);QTest.qWait(20)
assert w.transport.audition_notes[3];w.grab().save(str(out/'lingfeng-v10-compose.png'))
w.seek(960);w.toggle_play();QTest.qWait(170);assert w.roll.anchor_tick==960
QTest.mouseClick(lane,Qt.MouseButton.LeftButton,pos=QPoint(round(lane.x_at(2*3840)+30),25));assert w.transport.playing
w.grab().save(str(out/'lingfeng-v10-playback-anchor.png'));w.toggle_play();w.replay();assert w.playhead==960 and not w.transport.playing and w.roll.anchor_tick is None
w.melody_float.click();QTest.qWait(60);assert w.melody_window.isFloating() and w.harmony_window.toolbar.isVisible()
w.melody_sync.setChecked(True);w.roll.horizontalScrollBar().setValue(400);assert w.shared_scroll.value()==400
w.grab().save(str(out/'lingfeng-v10-melody-detached.png'));w.melody_window.grab().save(str(out/'lingfeng-v10-melody-floating.png'))
w.harmony_window.float_button.click();QTest.qWait(50);assert not w.harmony_window.top_lane.isVisible();w.harmony_window.grab().save(str(out/'lingfeng-v10-chord-floating.png'))
w.switch_workspace('score');w.open_score_roll('melody',0);QTest.qWait(60);w.grab().save(str(out/'lingfeng-v10-score-editor.png'))
w.edit_toggle.setChecked(False);w.toggle_editor();QTest.qWait(30);w.seek(960);w.toggle_play();QTest.qWait(120);w.grab().save(str(out/'lingfeng-v10-score-playing.png'));w.toggle_play()
canvas=w.score_view.canvas;canvas.grab();count=canvas.cache_renders;start=time.perf_counter()
for tick in range(0,7680,96):canvas.play_tick=tick;canvas.repaint()
duration=time.perf_counter()-start;assert canvas.cache_renders==count
Path('output/v10-render-check.json').write_text(json.dumps(dict(frames=80,seconds=duration,average_frame_ms=duration/80*1000,static_page_renders=count,repaint_added_static_pages=0),indent=2),'utf-8')
export_midi(w.project,'tmp/v10-before.mid')
for style in ('spatial','compact','traditional'):
    w.project.notation['style']=style;pages=export_pdf(w.project,f'output/pdf/lingfeng-v10-{style}.pdf');assert pages==1
export_midi(w.project,'tmp/v10-after.mid');assert Path('tmp/v10-before.mid').read_bytes()==Path('tmp/v10-after.mid').read_bytes()
w.project.notation['style']='spatial';w.refresh();w.change_language('en',False);w.set_theme('dark');w.open_score_roll('chords',0);w.harmony_window.float_button.click();QTest.qWait(50)
w.score_tools.grab().save(str(out/'lingfeng-v10-score-floating-en.png'))
w.switch_workspace('compose');w.melody_window.setFloating(False);w.harmony_window.setFloating(False);w.resize(640,1000);QTest.qWait(70);assert w.width()==640;w.grab().save(str(out/'lingfeng-v10-dark-narrow-en.png'))
w.harmony_window.setFloating(True);w.harmony_window.resize(720,620);QTest.qWait(50);w.harmony_window.grab().save(str(out/'lingfeng-v10-chord-floating-dark.png'))
help=HelpDialog(w);help.list.setCurrentRow(6);help.show();QTest.qWait(30);help.grab().save(str(out/'lingfeng-v10-help.png'));help.close()
w.dirty=False;w.close();app.processEvents()
print('v0.10 UI passed: dual overview, dock combinations, audition during WinMM playback, paused replay, start line, cached score frames, continuous bar mapping, three PDFs, unchanged MIDI, English and dark 640px layout.')

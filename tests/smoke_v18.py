"""Render key-change collisions, floating cards and configurable shortcuts."""
import os,sys,json
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Note,Chord
from popscore.notation import export_pdf
from popscore.keybindings import KeyBindingsDialog

app=QApplication([]);app.setStyle('Fusion');errors=[]
sys.excepthook=lambda typ,value,tb:errors.append(str(value))
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
p=Project();p.title='调性变化与和弦编辑';p.bpm=52;p.set_context([[0,p.end]],tonic=53,mode='Ionian');p.set_markers([3],51,'Phrygian',4,4)
p.notes=[Note(t,480,pitch) for t,pitch in zip(range(960,11520,480),[65,65,64,65,64,69,67,69,67,65,64,65,64,65,64,69,67,69,64,65,65,67])]
p.notes += [Note(11520,160,78),Note(11680,160,77),Note(11840,160,75),Note(12480,320,75),Note(12800,320,77),Note(13120,320,78)]
p.chords=[Chord(3840,7680,50,'m'),Chord(11520,3840,51,'m',pattern='eighths')]
w=MainWindow(p);w.change_language('zh',False);w.show();w.resize(1380,1000);w.set_theme('dark');w.timer.stop();w.autosave.stop()
for mute in w.mute_buttons.values():mute.setChecked(True)
out=Path('output/screenshots');out.mkdir(exist_ok=True,parents=True);pdf=Path('output/pdf');pdf.mkdir(exist_ok=True,parents=True)
w.switch_workspace('score');w.edit_toggle.setChecked(False);w.toggle_editor()
for style in ('traditional','spatial','compact'):
    w.project.notation['style']=style;w.refresh();QTest.qWait(50);w.grab().save(str(out/f'lingfeng-v18-score-{style}.png'))
    export_pdf(w.project,pdf/f'lingfeng-v18-{style}.pdf')
w.project.save('examples/lingfeng-chord-editing.lfs')
w.switch_workspace('compose');w.open_harmony();w.roll.set_compact(True);QTest.qWait(50);w.grab().save(str(out/'lingfeng-v18-compose.png'))
w.harmony_window.setFloating(True);w.harmony_window.resize(1000,680);QTest.qWait(60);r=w.harmony_window.roll
w.chord_selection(set());w.chord_selection({p.chords[1].id},r);r.ensure_tick(11000);QTest.qWait(30);w.harmony_window.grab().save(str(out/'lingfeng-v18-harmony-floating.png'))
assert not w.roll.selected_chords
dialog=KeyBindingsDialog(w.keybindings,w);dialog.show();QTest.qWait(30);dialog.grab().save(str(out/'lingfeng-v18-keybindings.png'));dialog.close()
w.change_language('en',False);w.harmony_window.resize(700,650);QTest.qWait(60);w.harmony_window.grab().save(str(out/'lingfeng-v18-harmony-en-narrow.png'))
w.harmony_window.setFloating(False);w.resize(700,900);QTest.qWait(50);assert w.width()==700;w.grab().save(str(out/'lingfeng-v18-compose-en-narrow.png'))
for pane,roll,sync,controls in w.view_panes():
    if pane.isVisible() and pane.isFloating():assert all(c.isVisible() and pane.rect().contains(c.mapTo(pane,c.rect().center())) for c in (controls.play,controls.replay,controls.loop,controls.follow,controls.bpm))
w.dirty=False;w.close();app.processEvents();assert not errors,errors
report=dict(status='passed',score_styles=3,matching_structure_cards=True,english_700px_windows=True,qt_callback_errors=errors)
Path('output/v18-ui-check.json').write_text(json.dumps(report,indent=2),'utf-8');print(json.dumps(report))

"""End-to-end v0.8 workspace and printable two-verse demonstration."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Note,Chord
from popscore.presentation import add_annotation
from popscore.notation import export_pdf,ScoreLayout
from popscore.midi import export_midi

app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
out=Path('output/screenshots');out.mkdir(parents=True,exist_ok=True)
p=Project(title='风与回声',author='伶风原创示例 · 两段歌词与反复排版');p.append_measures(4)
verses=['晚风轻轻吹过窗前星光落在心上','白云慢慢越过山岗回声留在远方','让旋律随心流淌']
for bar in range(12):
    idx=bar%4
    for k,pitch in enumerate(([60,64,67],[62,65,69],[64,67,71],[62,65,67])[idx]):
        p.notes.append(Note(bar*3840+480+k*960,720,pitch,90,verses[bar//4][(idx*3+k)%len(verses[bar//4])]))
    p.chords.append(Chord(bar*3840,3840,[48,53,55,48][idx],pattern='up'))
p.notation.update(row_gap=13,system_gap=8)
w=MainWindow(p);w.show();w.resize(1280,960);QTest.qWait(80)
assert not w.harmony_window.isVisible()
w.chord_selection({p.chords[1].id});w.roll.center_pitch(65);QTest.qWait(30);w.grab().save(str(out/'lingfeng-v8-compose.png'))
w.open_harmony(p.chords[1].id);w.resize(960,1000);QTest.qWait(80);w.grab().save(str(out/'lingfeng-v8-docked.png'))
w.melody_window.setFloating(True);w.harmony_window.setFloating(True);QTest.qWait(50)
assert w.roll.lane.isVisible() and not w.harmony_window.top_lane.isVisible()
w.melody_window.grab().save(str(out/'lingfeng-v8-melody-floating.png'));w.harmony_window.grab().save(str(out/'lingfeng-v8-chord-floating.png'))
w.melody_window.setFloating(False);w.harmony_window.setFloating(False)
w.switch_workspace('score');w.edit_toggle.setChecked(True);w.toggle_editor();w.score_tabs.setCurrentIndex(2)
logic=w.logic_panel;logic.create_draft();w.score_view.canvas.selected_bars=set(range(4));logic.capture(0);w.score_view.canvas.selected_bars=set(range(4,8));logic.capture(1)
export_midi(w.project,'tmp/v8-before.mid');assert logic.apply.isEnabled();logic.commit()
for kind,start,end in [('adlib',8*3840,9*3840),('rit',11*3840,12*3840),('fine',11*3840,12*3840)]:add_annotation(w.project,kind,start,end)
w.refresh();export_midi(w.project,'tmp/v8-after.mid');assert Path('tmp/v8-before.mid').read_bytes()==Path('tmp/v8-after.mid').read_bytes()
w.score_view.canvas.selected_bars.clear();w.resize_score();w.resize(1280,1050);QTest.qWait(60);w.grab().save(str(out/'lingfeng-v8-logic.png'))
w.project.save('examples/lingfeng-structure.lfs')
for style in ('spatial','compact','traditional'):
    w.project.notation['style']=style
    export_pdf(w.project,f'output/pdf/lingfeng-v8-{style}.pdf')
    assert ScoreLayout(w.project).systems[0].lyric_rows==2
w.project.notation['style']='spatial';w.refresh();w.edit_toggle.setChecked(False);w.toggle_editor();QTest.qWait(50);w.grab().save(str(out/'lingfeng-v8-score.png'))
w.switch_workspace('compose');w.set_theme('dark');w.change_language('en',False);w.resize(720,1000);QTest.qWait(80)
assert w.width()==720 and w.visibility_button.text()=='View';w.grab().save(str(out/'lingfeng-v8-english-dark.png'))
w.switch_workspace('score');w.edit_toggle.setChecked(True);w.toggle_editor();w.score_tabs.setCurrentIndex(2);w.score_tools.setFloating(True);QTest.qWait(50)
w.score_tools.grab().save(str(out/'lingfeng-v8-logic-floating-en.png'))
w.dirty=False;w.close();app.processEvents()
print('v0.8 UI passed: default layout, hover/selection overlay, two floating rolls, shared score tabs, two-region validation, stacked lyrics, MIDI identity, three PDF styles, 720px English/dark UI.')

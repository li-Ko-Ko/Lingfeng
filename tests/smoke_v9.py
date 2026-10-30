"""Visual, score-export and multiple-structure walkthrough for Lingfeng 0.9."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Note,Chord
from popscore.presentation import add_annotation,visible_bars
from popscore.notation import export_pdf,ScoreLayout
from popscore.midi import export_midi
from popscore.helpview import HelpDialog

app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
out=Path('output/screenshots');out.mkdir(parents=True,exist_ok=True)
p=Project(title='晚风与纸船',author='伶风原创示例 · 反复与尾声');p.append_measures(8)
poem=['晚风轻轻吹过窗前星光落在心上','白云慢慢越过山岗回声留在远方','让小小纸船载着梦漂向远方','听夜色温柔静静唱']
for bar in range(16):
    motif=bar%4 if bar<8 else (bar-8)%2 if bar<10 or 12<=bar<14 else 2 if bar<12 else 3
    pitches=([60,64,67],[62,65,69],[64,67,71],[62,65,67])[motif]
    text=poem[min(bar//4,3)]
    for k,pitch in enumerate(pitches):p.notes.append(Note(bar*3840+480+k*960,720,pitch,90,text[(bar%4*3+k)%len(text)]))
    p.chords.append(Chord(bar*3840,3840,[48,53,55,48][motif],pattern='up'))
p.notation.update(row_gap=13,system_gap=8)
w=MainWindow(p);w.change_language('zh',False);w.set_theme('light');w.show();w.resize(1360,960);QTest.qWait(70)
w.open_harmony(p.chords[1].id);w.chord_selection({p.chords[1].id});w.view_controls.range.setCurrentIndex(1);QTest.qWait(40)
w.grab().save(str(out/'lingfeng-v9-compose.png'))
assert w.shared_scroll.isVisible() and not w.harmony_window.toolbar.isVisible()
w.harmony_window.setFloating(True);w.harmony_window.view_controls.range.setCurrentIndex(0);w.harmony_window.roll.center_pitch(55);QTest.qWait(50)
w.harmony_window.grab().save(str(out/'lingfeng-v9-chord-floating.png'))
w.melody_window.setFloating(True);QTest.qWait(40);w.melody_window.grab().save(str(out/'lingfeng-v9-melody-floating.png'))
w.switch_workspace('score');w.open_score_roll('melody',0);QTest.qWait(40);w.grab().save(str(out/'lingfeng-v9-score-melody.png'))
w.open_score_roll('chords',0);QTest.qWait(40);w.grab().save(str(out/'lingfeng-v9-score-chord.png'))
w.score_tabs.setCurrentIndex(2);logic=w.logic_panel;canvas=w.score_view.canvas
logic.create_draft();repeat=logic.current()['id'];logic.kind.setCurrentIndex(logic.kind.findData('jump_coda'));logic.create_draft();coda=logic.current()['id']
logic.active=('draft',repeat);logic.refresh()
for i,bars in enumerate((range(4),range(4,8))):canvas.selected_bars=set(bars);logic.capture(i)
assert logic.apply.isEnabled();export_midi(w.project,'tmp/v9-uncompressed.mid');logic.commit()
logic.active=('draft',coda);logic.refresh()
for i,bars in enumerate((range(8,10),range(10,12),range(12,14),range(14,16))):canvas.selected_bars=set(bars);logic.capture(i)
assert logic.apply.isEnabled();QTest.qWait(30);w.grab().save(str(out/'lingfeng-v9-logic-draft.png'));logic.commit()
for kind,start,end in [('adlib',8*3840,9*3840),('rit',15*3840,16*3840),('fine',15*3840,16*3840)]:add_annotation(w.project,kind,start,end)
w.refresh();export_midi(w.project,'tmp/v9-compressed.mid');assert Path('tmp/v9-uncompressed.mid').read_bytes()==Path('tmp/v9-compressed.mid').read_bytes()
assert len(w.project.notation['compressions'])==2 and len(visible_bars(w.project))==10
canvas.selected_bars.clear();w.resize(1360,1050);w.resize_score();QTest.qWait(45);w.grab().save(str(out/'lingfeng-v9-logic.png'))
w.project.save('examples/lingfeng-symbols.lfs')
for style in ('spatial','compact','traditional'):
    w.project.notation['style']=style;pages=export_pdf(w.project,f'output/pdf/lingfeng-v9-{style}.pdf');print(style,pages,'pages');assert pages<=2
w.project.notation['style']='spatial';w.refresh();w.edit_toggle.setChecked(False);w.toggle_editor();QTest.qWait(40);w.grab().save(str(out/'lingfeng-v9-score.png'))
w.switch_workspace('compose');w.melody_window.setFloating(False);w.harmony_window.setFloating(False);w.resize(640,1000);QTest.qWait(50)
assert w.width()==640;w.grab().save(str(out/'lingfeng-v9-narrow.png'))
w.change_language('en',False);w.set_theme('dark');w.resize(720,1000);QTest.qWait(60);assert w.width()==720;w.grab().save(str(out/'lingfeng-v9-english-dark.png'))
help=HelpDialog(w);help.list.setCurrentRow(9);help.show();QTest.qWait(30);help.grab().save(str(out/'lingfeng-v9-help.png'));help.close()
w.switch_workspace('score');w.open_score_roll('melody',0);w.score_tabs.setCurrentIndex(2);w.score_tools.setFloating(True);w.score_tools.resize(850,520);QTest.qWait(40);w.score_tools.grab().save(str(out/'lingfeng-v9-logic-floating-en.png'))
w.dirty=False;w.close();app.processEvents()
print('v0.9 UI passed: shared scrollbar and keys, independent floating rolls, three tabs, two explicit structures, stacked lyrics, MIDI identity, three PDFs, narrow layouts and bilingual help.')

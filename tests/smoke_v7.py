"""Lingfeng branding, score layout commands, color/help UI and portable format."""
import os,copy
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.helpview import HelpDialog,ColorSettingsDialog,ABOUT
from popscore.model import Project,Note,Chord,demo_project
from popscore.presentation import add_compression,apply_forced_row,add_annotation
from popscore.notation import export_pdf
from popscore.midi import export_midi
from popscore.theme import set_roll_palettes,roll_color

app=QApplication.instance() or QApplication([]);app.setStyle('Fusion')
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
out=Path('output/screenshots');out.mkdir(parents=True,exist_ok=True)
p=Project(title='伶风 · 反复与局部分行示例',author='原创排版示例 · MIDI 保留全部 16 小节');p.append_measures(8)
for i in range(16):
    base=[60,64,67,65][i%4]
    p.notes.extend([Note(i*3840+480,480,base,90,'风'),Note(i*3840+1920,960,base+2,86,'来')])
    p.chords.append(Chord(i*3840,3840,[48,53,55,48][i%4],pattern='quarters'))
w=MainWindow(p);w.show();w.resize(1100,1000);QTest.qWait(80)
assert '伶风' in w.windowTitle() and not w.roll.panels['velocity']
# Draw: single click deletes; dragging keeps the note and edits it.
w.tool.setCurrentIndex(w.tool.findData('draw'));w.roll.center_pitch(63);QTest.qWait(30)
n=w.project.notes[0];point=QPoint(round(w.roll.x_at(n.start)+12),round(w.roll.y_at(n.pitch)+10))
QTest.mouseClick(w.roll.viewport(),Qt.MouseButton.LeftButton,pos=point);app.processEvents();assert len(w.project.notes)==31
w.undo();assert len(w.project.notes)==32
# Exact direct copy preserves a chromatic note; transformed copy menu rejects it.
w.project.notes[0].pitch=61;w.refresh();w.roll.selected_ids={w.project.notes[0].id}
menu=w.roll.timeline_menu(QPoint(130,12));assert [a.isEnabled() for a in menu.copy_menu.actions()]==[True,False,False,False]
w.note_command(w.roll,'copy:direct');assert w.note_clipboard.paste(w.project,3840)[0].pitch==61
w.project.notes[0].pitch=60;w.refresh()
before=Path('tmp/lingfeng-before.mid');after=Path('tmp/lingfeng-after.mid');export_midi(w.project,before)
w.switch_workspace('score');QTest.qWait(80)
canvas=w.score_view.canvas;canvas.selected_bars=set(range(8))
w.score_command('compress:repeat',dict(bars=list(range(8)),ranges=[[0,8*3840]]));QTest.qWait(30)
assert [s.bars for s in w.score_view.canvas.layout.systems]==[list(range(4)),list(range(8,12)),list(range(12,16))]
w.score_command('force_row',dict(bars=list(range(8,16)),ranges=[[8*3840,16*3840]]));QTest.qWait(30)
assert [s.bars for s in w.score_view.canvas.layout.systems]==[list(range(4)),list(range(8,16))]
w.score_command('symbol:adlib',dict(bars=[8],ranges=[[8*3840,9*3840]]))
w.score_command('symbol:rit',dict(bars=[15],ranges=[[15*3840+1920,16*3840]]))
w.score_command('symbol:fine',dict(bars=[15],ranges=[[15*3840+1920,16*3840]]))
export_midi(w.project,after);assert before.read_bytes()==after.read_bytes()
w.score_view.canvas.selected_bars.clear();w.set_theme('light');QTest.qWait(80);w.grab().save(str(out/'lingfeng-v7-score.png'))
w.project.save('examples/lingfeng-layout.lfs');assert Project.load('examples/lingfeng-layout.lfs').to_dict()==w.project.to_dict()
export_pdf(w.project,'output/pdf/lingfeng-v7.pdf')
for style in ('compact','traditional','spatial'):
    w.score_style.setCurrentIndex(w.score_style.findData(style));QTest.qWait(20);assert len(w.score_view.canvas.layout.systems[1].bars)==8
help=HelpDialog(w);help.show();help.list.setCurrentRow(5);QTest.qWait(40);assert '#bbddd3' in help.browser.toHtml();help.grab().save(str(out/'lingfeng-v7-help.png'));help.close()
about=HelpDialog(w,True);about.show();QTest.qWait(40);assert ('lightweight' if w.language=='en' else '轻量级') in about.browser.toPlainText();about.grab().save(str(out/'lingfeng-v7-about.png'));about.close()
colors=ColorSettingsDialog(w);colors.show();QTest.qWait(20);colors.grab().save(str(out/'lingfeng-v7-colors.png'));colors.close()
set_roll_palettes({'dark':{'background':{'both':'#1f4941'},'note':{'both':'#9de5c8'}}});w.set_theme('dark');assert roll_color('both').name()=='#1f4941'
set_roll_palettes({});w.switch_workspace('compose');w.open_harmony(w.project.chords[0].id);w.harmony_window.setFloating(False);w.resize(960,1000);QTest.qWait(200)
assert w.harmony_window.roll.structure_boxes;w.grab().save(str(out/'lingfeng-v7-chords.png'))
w.switch_workspace('score');w.score_view.canvas.selected_bars={0,1};w.change_language('en',False);QTest.qWait(80)
assert w.score_view.canvas.selected_bars=={0,1};assert w.score_selection.currentText()=='Measure selection'
help=HelpDialog(w);help.list.setCurrentRow(next(i for i in range(help.list.count()) if help.list.item(i).text()=='Repeat compression and jumps'));help.show();QTest.qWait(30);assert 'MIDI' in help.browser.toPlainText();help.grab().save(str(out/'lingfeng-v7-help-en.png'));help.close()
w.dirty=False;w.close();app.processEvents()
demo_project().save('examples/demo.lfs')
print('v0.7 UI passed: Draw delete, chromatic restrictions, score compression/local systems, MIDI identity, LFS, help/About, custom palettes, structure frames and language-preserved selection.')

"""v0.14 UI, bar-based lyric guidance, live editing and uniform score fonts."""
import os,json,copy,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtTest import QTest
from popscore.app import MainWindow
from popscore.model import Project,Note,Chord
from popscore.notation import export_pdf
from popscore.lyrics import matching_issues,events
from popscore.midi import export_midi,event_list

app=QApplication([]);app.setStyle('Fusion')
def fail(*args):raise AssertionError(args[1:])
QMessageBox.warning=fail
out=Path('output/screenshots');out.mkdir(exist_ok=True,parents=True)
p=Project();p.title='风中的节奏';p.author='原创练习 · 小节范围与歌词起点'
for b in range(8):
    offsets=() if b==3 else (0,320,640,1920,2880) if b==2 else (0,960,1920)
    for i,t in enumerate(offsets):p.notes.append(Note(b*3840+t,320 if b==2 and t<960 else 480,(60,62,64,67,69)[i],86))
p.notes.append(Note(3840,480,72));p.chords=[Chord(b*3840,3840,48 if b%2==0 else 53,pattern='up' if b==1 else 'block') for b in range(8)]
w=MainWindow(p);w.show();w.resize(1380,1080);w.change_language('zh',False);w.set_theme('light');w.open_harmony()
for mute in w.mute_buttons.values():mute.setChecked(True)
QTest.qWait(50);w.grab().save(str(out/'lingfeng-v14-compose.png'));assert not w.lyrics_action.isVisible()
w.playhead=0;w.toggle_play();time.sleep(.04);worker=w.transport.thread;anchor=w.play_anchor
w.mutate('live melody edit',lambda p:setattr(p.notes[2],'velocity',90));w.undo();w.redo();assert w.transport.playing and w.transport.thread is worker and w.play_anchor==anchor
w.stop();w.seek(0);w.switch_workspace('score');w.batch_lyrics();w.resize_score()
panel=w.lyric_panel;panel.start.setValue(2);panel.count.setValue(4);panel.template();QTest.qWait(80)
assert panel.rhythm.topLevelItemCount()==4 and panel.text.toPlainText().count('&')==11 and not panel.apply.isEnabled()
w.grab().save(str(out/'lingfeng-v14-lyric-template.png'))
panel.text.setPlainText('风 _ 来 | be-fore the _ dawn | 我/64.爱/64你/64 | 一二三');assert panel.check();before=event_list(w.project);panel.commit();assert not matching_issues(w.project) and event_list(w.project)==before
QTest.qWait(60);w.grab().save(str(out/'lingfeng-v14-lyric-match.png'))
w.project.save('examples/lingfeng-lyric-bars.lfs');w.edit_toggle.setChecked(False);w.toggle_editor();w.resize_score();pages={}
export_midi(w.project,'output/v14-layout-before.mid')
for style in ('spatial','compact','traditional'):
    w.set_notation('style',style);QTest.qWait(40);w.grab().save(str(out/f'lingfeng-v14-{style}.png'))
    pages[style]=export_pdf(w.project,f'output/pdf/lingfeng-v14-{style}.pdf')
    layout=w.score_view.canvas.layout;assert all(0<size<=w.project.notation['font_size'] for glyph,size in layout.glyph_sizes)
w.set_notation('style','spatial');w.rowgap.setValue(8);QTest.qWait(40);w.grab().save(str(out/'lingfeng-v14-gap-8.png'))
w.rowgap.setValue(24);QTest.qWait(40);w.grab().save(str(out/'lingfeng-v14-gap-24.png'));assert w.score_view.canvas.layout.systems[0].row_gap==24
export_midi(w.project,'output/v14-layout-after.mid');assert Path('output/v14-layout-before.mid').read_bytes()==Path('output/v14-layout-after.mid').read_bytes()
w.change_language('en',False);w.set_theme('dark');w.resize(680,1000);w.edit_toggle.setChecked(True);w.toggle_editor();w.score_tabs.setCurrentIndex(3);w.resize_score();panel=w.lyric_panel;panel.section.setCurrentIndex(1);QTest.qWait(70)
w.grab().save(str(out/'lingfeng-v14-lyrics-narrow-en.png'));w.score_tools.setFloating(True);w.score_tools.resize(900,650);QTest.qWait(50);w.score_tools.grab().save(str(out/'lingfeng-v14-lyrics-floating-en.png'))
report=dict(status='passed',pdf_pages=pages,lyric_range=[2,5],template_onsets=11,rap_onsets=3,live_edit_thread_preserved=True,layout_does_not_change_midi=True)
Path('output/v14-ui-check.json').write_text(json.dumps(report,indent=2),'utf-8');w.dirty=False;w.close();app.processEvents();print(json.dumps(report))

"""Installed-application acceptance checks, also usable from a source checkout."""
from pathlib import Path
import copy
import json
import sys
from lingfeng.platform.paths import application_root, resource_root


def self_test(folder):
    """Run the installed binary, without a source checkout or an external Python."""
    from PySide6.QtWidgets import QApplication,QMessageBox
    from PySide6.QtCore import QTimer
    from lingfeng.ui.main_window import MainWindow, STYLE
    from lingfeng.music.model import Project, Chord, Note, Context, PPQ, FONT_SIZE_MAX, PATTERNS, demo_project
    from lingfeng.audio.midi import export_midi, export_daw_bundle
    from lingfeng.engraving.notation import export_pdf, ScoreLayout
    from lingfeng import __version__
    from lingfeng.music.recognition import recognize
    from lingfeng.platform.i18n import tr
    def menu_actions(menu):
        for action in menu.actions():
            yield action
            if action.menu():yield from menu_actions(action.menu())
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    app=QApplication.instance() or QApplication([]);app.setStyle('Fusion');app.setStyleSheet(STYLE)
    app.setApplicationName('Lingfeng')
    p=demo_project();p.volumes={'melody':84,'chords':68,'instrument':84}
    p.audio['melody']=dict(device='synth:piano-electric',program=5)
    c=p.chords[2];c.start+=480;c.duration-=480;c.pattern='up'
    p.validate();p.save(folder/'test.lfs');q=Project.load(folder/'test.lfs')
    assert q.to_dict()==p.to_dict()
    export_midi(q,folder/'test.mid');export_daw_bundle(q,folder/'test-DAW.zip')
    pages=export_pdf(q,folder/'test.pdf')
    assert recognize([52,55,60])[0].name=='C/E'
    window=MainWindow(q);window.save_preferences=lambda:None
    assert window.roll.row_height==window.harmony_window.roll.row_height==20
    assert window.length.currentData()==window.harmony_window.length.currentData()==-1
    assert window.roll.previous_duration is None and window.roll.note_duration(0)==240
    assert not window.visibility_actions['harmony'].isChecked();window.show();app.processEvents();window.roll.center_pitch(60)
    window.set_theme('light')
    window.open_harmony(c.id);app.processEvents();window.harmony_window.roll.center_pitch(53)
    assert window.shared_scroll.isVisible() and not window.roll.horizontalScrollBar().isVisible() and not window.harmony_window.roll.horizontalScrollBar().isVisible()
    window.shared_scroll.setValue(300);assert window.roll.horizontalScrollBar().value()==window.harmony_window.roll.horizontalScrollBar().value()
    window.shared_scroll.setValue(0)
    app.processEvents();window.grab().save(str(folder/'compose.png'));window.harmony_window.grab().save(str(folder/'harmony.png'))
    window.set_theme('dark');app.processEvents()
    assert window.play_button.text()==window.replay_button.text()==''
    assert (resource_root()/'assets'/'check.svg').is_file()
    assert not hasattr(window,'context_panel')
    window.grab().save(str(folder/'dark.png'));window.harmony_window.grab().save(str(folder/'dark-harmony.png'))
    window.switch_workspace('score');app.processEvents();window.grab().save(str(folder/'score.png'))
    assert window.score_tabs.count()==0 and not any(state['visible'] for state in window.score_panel_state.values())
    window.perline.setCurrentIndex(window.perline.findData(8));app.processEvents()
    assert all(len(s.bars)==8 for s in window.score_view.canvas.layout.systems)
    window.show_score_panel('melody');window.view_controls.range.setCurrentIndex(1)
    for key in ('chords','velocity','navigator'):window.view_controls.panel_actions[key].setChecked(False)
    window.system_gap.setValue(0);window.rowgap.setValue(8)
    window.resize_score()
    app.processEvents();window.grab().save(str(folder/'compact-editor.png'))
    layout=window.score_view.canvas.layout
    assert layout.systems[1].top==layout.systems[0].top+layout.systems[0].height
    window.play_anchor=3840;window.return_to_start();assert window.playhead==0 and not window.transport_active
    check=Project();check.add_note(Note(0,960,60));check.add_note(Note(0,960,64));check.insert_measure(0,3,4,53,'Dorian')
    check.set_marker(0,55,'Ionian',4,4);check.validate()
    assert check.marker_value(1)==(4,4,48,'Ionian')
    window.switch_workspace('compose');window.change_language('en',False);window.resize(720,1000)
    window.open_harmony();window.harmony_window.setFloating(False)
    from PySide6.QtCore import QEventLoop,QTimer
    settle=QEventLoop();QTimer.singleShot(100,settle.quit);settle.exec()
    assert window.width()==720 and window.tool.currentText()=='Smart' and window.tool.count()==2
    assert not window.harmony_window.isFloating()
    harmony=window.harmony_window
    assert any(harmony.roll.ruler_height<=harmony.roll.y_at(n.pitch)<harmony.roll.viewport().height() for n in harmony.current().render_notes())
    window.grab().save(str(folder/'english-docked.png'))
    from lingfeng.music.note_operations import NoteClipboard
    clip=NoteClipboard.capture([Note(0,480,48),Note(480,480,50),Note(960,480,53),Note(1440,480,52)],Project(),'retrograde')
    assert [n.pitch for n in clip.paste(Project(),3840)]==[52,53,50,48]
    from PySide6.QtGui import QImage,QPainter
    ties=Project();ties.notes=[Note(11040,720,57)];layout=ScoreLayout(ties)
    image=QImage(900,1273,QImage.Format.Format_RGB32);painter=QPainter(image);layout.draw(painter,0);painter.end()
    assert [kind for _,kind,_ in layout.tie_paths]==['continuous'];image.save(str(folder/'ties.png'))
    from lingfeng.ui.help_dialog import HelpDialog, ColorSettingsDialog
    from lingfeng.engraving.presentation import add_compression, apply_forced_row, add_annotation, visible_bars
    from lingfeng.ui.theme import set_roll_palettes, roll_color
    check=Project();check.notes=[Note(i*3840+480,960,60+i%4) for i in range(8)]
    export_midi(check,folder/'uncompressed.mid');add_compression(check,list(range(8)),'repeat');apply_forced_row(check,[0,1,2,3])
    export_midi(check,folder/'compressed.mid');assert (folder/'uncompressed.mid').read_bytes()==(folder/'compressed.mid').read_bytes()
    assert visible_bars(check)==[0,1,2,3];check.save(folder/'repeat.lfs');assert Project.load(folder/'repeat.lfs').to_dict()==check.to_dict()
    layout=ScoreLayout(check);image=QImage(900,1273,QImage.Format.Format_RGB32);painter=QPainter(image);layout.draw(painter,0);painter.end();image.save(str(folder/'repeat.png'))
    assert [kind for kind,_,_ in layout.symbol_marks]==['repeat_start','repeat_end']
    help=HelpDialog(window,True);help.show();app.processEvents();assert ('lightweight' if window.language=='en' else '轻量级') in help.browser.toPlainText();help.grab().save(str(folder/'about.png'));help.close()
    help=HelpDialog(window);help.list.setCurrentRow(5);help.show();app.processEvents();help.grab().save(str(folder/'color-help.png'));help.close()
    colors=ColorSettingsDialog(window);colors.show();app.processEvents();colors.close()
    set_roll_palettes({'dark':{'background':{'both':'#123456'}}});assert roll_color('both',dark=True).name()=='#123456';set_roll_palettes({})
    assert window.harmony_window.roll.lane.boxes
    from lingfeng.music.chord_operations import blank_chord
    from lingfeng.engraving.presentation import pair_candidate
    assert blank_chord(Project(),480).end==3840
    check=Project();check.notes=[Note(i*3840+480,960,60+i%4,lyric='a' if i<4 else 'b') for i in range(8)]
    assert pair_candidate(check,[0,1,2,3],[4,5,6,7])
    add_compression(check,list(range(8)),'repeat');layout=ScoreLayout(check)
    image=QImage(900,1273,QImage.Format.Format_RGB32);painter=QPainter(image);layout.draw(painter,0);painter.end()
    assert len(layout.lyric_positions)==8 and layout.systems[0].lyric_rows==2
    assert all(y>layout.systems[0].top+layout.systems[0].grid_bottom for _,_,_,y in layout.lyric_positions)
    window.melody_window.setFloating(True);window.harmony_window.setFloating(True);app.processEvents()
    assert window.roll.lane.isVisible() and window.harmony_window.top_lane.isVisible()
    assert window.melody_sync.isVisible() and window.melody_float.kind==window.harmony_window.float_button.kind=='dock'
    assert {item[0] for item in window.navigator.segments()}=={0}
    window.navigator.set_visible_tracks(['vocal','instrument','chords'])
    assert {item[0] for item in window.navigator.segments()}=={0,1}
    window.navigator.set_visible_tracks(window.navigator_tracks)
    window.play_anchor=480;window.playhead=2000;window.replay();assert window.playhead==480 and not window.transport.playing and window.roll.anchor_tick is None
    window.melody_window.setFloating(False);window.harmony_window.setFloating(False)
    window.switch_workspace('score');window.open_score_roll('chords',0);app.processEvents()
    assert window.score_tabs.currentWidget() is window.score_harmony_page
    assert window.score_tabs.count()==2
    window.tool.setCurrentIndex(window.tool.findData('draw'));assert window.harmony_window.roll.tool=='draw'
    from lingfeng.music.chord_operations import chord_details
    assert 'Actual bass' in chord_details(window.project,window.project.chords[0])
    window.replace_project(check);assert window.show_score_panel('logic') is None;app.processEvents()
    canvas=window.score_view.canvas;canvas.grab()
    from PySide6.QtCore import QPointF
    assert any(hit[2][0]=='compressions' for hit in canvas.layout.hit_symbols)
    assert 'logic' not in window.score_pages and not window.logic_panel.isVisible() and not window.logic_panel.isEnabled()
    logic=window.logic_panel;latent=logic.export_state();snapshot=copy.deepcopy(window.project.to_dict())
    logic.create_draft();logic.capture(0);logic.commit();logic.remove()
    assert logic.export_state()==latent and window.project.to_dict()==snapshot
    # Pure compatibility interfaces remain callable for saved/future structures.
    from lingfeng.engraving.structure import apply_draft
    compatible=copy.deepcopy(check);compatible.notation['compressions']=[]
    apply_draft(compatible,dict(id='acceptance',kind='repeat',regions=[dict(bars=list(range(4))),dict(bars=list(range(4,8)))]))
    assert visible_bars(compatible)==[0,1,2,3]
    assert export_midi(compatible,None)==export_midi(check,None)
    window.grab().save(str(folder/'structure-tabs.png'))
    canvas.grab();cached=canvas.cache_renders;canvas.play_tick=960;canvas.grab();assert canvas.cache_renders==cached
    a=canvas.layout.time_position(3839);b=canvas.layout.time_position(3840);assert abs(a[1]-b[1])<1
    window.length.setCurrentIndex(window.length.findData(480));window.length.set_triplet(True);window.grid.setCurrentIndex(window.grid.findData(240));window.grid.set_triplet(False)
    assert window.roll.duration==320 and window.roll.grid==240
    window.dotted.setChecked(True);assert not window.length.triplet and window.roll.duration==720
    window.length.setCurrentIndex(window.length.findData(-1));window.roll.previous_note_id='';window.roll.previous_duration=777;assert window.roll.note_duration(0)==777
    from lingfeng.audio.midi_import import read_midi, apply_midi
    midi=read_midi(folder/'test.mid');imported=Project();apply_midi(imported,midi,[i for i,t in enumerate(midi.tracks) if t.notes][:1],'melody',0)
    assert imported.notes
    empty=Project();empty.set_markers([1,3],53,'Dorian',3,4);assert empty.marker_value(2)==(4,4,48,'Ionian')
    empty.set_markers([1,2,3],53,'Dorian',3,4);assert not empty.marker_visible(2)
    from lingfeng.engraving.lyrics import events as lyric_events, put, apply_section, matching_issues
    from lingfeng.music.note_operations import split_notes, repartition_chord
    from lingfeng.music.quantization import quantize_notes
    from lingfeng.audio.midi_input import MidiInputDialog, WinMidiInput, devices
    assert [n.duration for n in split_notes([Note(17,80,60)])]==[40,40]
    assert [n.start for n in quantize_notes([Note(t,312,60) for t in (7,327,638)],240,True)]==[0,320,640]
    probe=Project();put(probe,0,'风');probe.chords=[Chord(0,3840,48),Chord(3840,3840,53)]
    repartition_chord(probe,probe.chords[0].id,0,4320)
    assert probe.chords[0].end==4320 and probe.chords[1].start==4320
    assert all(n.pitch%12 in probe.chords[0].pcs for n in probe.harmony_notes() if n.start<4320)
    window.replace_project(probe);window.midi_input.enabled=True;window.transport.monitor=lambda *args:None
    window.midi_input.receive(0x90,64,85,10);window.midi_input.receive(0x80,64,0,10.3)
    assert window.project.notes and lyric_events(window.project)[0]['text']=='风'
    apply_section(window.project,'我/64.爱/64你/64',2400);layout=ScoreLayout(window.project)
    assert any(f.ghost for system in layout.systems for fragments in system.fragments.values() for f in fragments)
    image=QImage(900,1273,QImage.Format.Format_RGB32);painter=QPainter(image);layout.draw(painter,0);painter.end();image.save(str(folder/'independent-lyrics.png'))
    window.project.save(folder/'input.lfs');assert lyric_events(Project.load(folder/'input.lfs'))==lyric_events(window.project)
    dialog=MidiInputDialog(window.midi_input,window);dialog.show();app.processEvents();dialog.grab().save(str(folder/'midi-input.png'));dialog.close()
    driver=WinMidiInput();driver.generation=3;driver.epoch=0;driver.queue.put((3,0x90|(60<<8)|(80<<16),10));assert list(driver.drain())==[(0x90,60,80,.01)];driver.close()
    assert not matching_issues(window.project)
    menu=window.title_bar.menu;rects=[menu.actionGeometry(a) for a in menu.actions()];assert len({(r.y(),r.height()) for r in rects})==1 and menu.font().bold()
    assert [(e['tick'],e['duration']) for e in lyric_events(window.project) if e.get('kind')=='rap']==[(2400,90),(2490,60),(2550,60)]
    assert not window.project.notation.get('show_scale_lines',False)
    assert layout.font_size==window.project.notation['font_size']
    assert layout.symbol_boxes and all(left<right and a<=b for start,end,left,right,a,b in layout.symbol_boxes)
    assert all(rect.isValid() for _,rect,_ in layout.hit_notes)
    from lingfeng.music.chord_operations import change_chords, quality_items
    c=window.project.chords[0];root=c.root;change_chords(window.project,{c.id},'inversion:1');assert c.root==root
    from lingfeng.music.model import QUALITIES
    change_chords(window.project,{c.id},'root:2');assert c.root%12==2 and len(quality_items())==len(QUALITIES)
    window.lyric_panel.new_section();window.lyric_panel.start.setValue(7);window.lyric_panel.text.setPlainText('星/16光/16');assert window.lyric_panel.check();window.lyric_panel.commit();assert not matching_issues(window.project)
    for mute in window.mute_buttons.values():mute.setChecked(True)
    window.playhead=0;window.toggle_play();window.seek(960);assert window.transport.playing and window.roll.anchor_tick==960
    worker=window.transport.thread;anchor=window.play_anchor
    window.mutate('live edit',lambda p:setattr(p.notes[0],'velocity',73));window.undo();window.redo()
    assert window.transport.playing and window.transport.thread is worker and window.play_anchor==anchor
    window.stop();window.seek(1920);assert not window.transport.playing
    assert not hasattr(__import__('lingfeng.ui.dialogs',fromlist=['NoteDialog']).NoteDialog(window.project.notes[0],window.project),'lyric')
    window.switch_workspace('score')
    for key in window.score_pages:window.set_score_panel_visible(key,False)
    app.processEvents()
    assert not hasattr(window,'score_height') and window.score_view.height()>=window.score_splitter.height()-4
    window.rowgap.setValue(8);assert window.score_view.canvas.layout.systems[0].row_gap==8
    layout=window.score_view.canvas.layout;image=QImage(900,1273,QImage.Format.Format_RGB32);painter=QPainter(image);layout.draw(painter,0);painter.end()
    assert all(0<size<=window.project.notation['font_size'] for glyph,size in layout.glyph_sizes)
    from lingfeng.engraving.lyrics import plan_range, apply_range
    bars=Project();bars.notes=[Note(3840,480,60),Note(3840,480,64),Note(4800,480,62)]
    assert len(plan_range(bars,'&&',1,1).events)==2 and plan_range(bars,'&&',1,1).issues
    assert not plan_range(bars,'风',1,1).issues and plan_range(bars,'我/1.',1,1).issues
    apply_range(bars,'风 _',1,1);assert not matching_issues(bars)
    from lingfeng.ui.piano_roll import KEY_W
    window.switch_workspace('compose');roll=window.roll;roll.horizontalScrollBar().setValue(300)
    x=KEY_W+(roll.viewport().width()-KEY_W)/2;tick=(x-KEY_W+roll.horizontalScrollBar().value())/roll.zoom*960
    roll.zoom_at(2,x);assert abs(roll.x_at(tick)-x)<=1
    roll.zoom_at(1000,x);assert roll.zoom==roll.MAX_ZOOM
    window.follow_playhead.setChecked(True);window.navigator.browse_to(window.navigator.width()/2);assert not window.follow_playhead.isChecked()
    window.switch_workspace('score');window.rowgap.setValue(8);font=window.score_view.canvas.layout.glyph_scale
    window.rowgap.setValue(24);assert window.score_view.canvas.layout.glyph_scale==font
    propagation=Project();propagation.set_markers([1],53,'Dorian',6,8);propagation.propagate_marker(1,'key');propagation.propagate_marker(1,'meter')
    assert all(propagation.marker_value(i)==(6,8,53,'Dorian') for i in range(1,len(propagation.measures)))
    # Verify the new interaction paths in the packaged binary as well.
    import time
    from PySide6.QtCore import Qt,QPoint
    from PySide6.QtGui import QWheelEvent
    probe=Project();probe.bpm=300;probe.notes=[Note(0,2880,60),Note(1200,240,67)];probe.chords=[Chord(0,3840,53)]
    probe.set_context([[0,probe.end]],tonic=53,mode='Dorian')
    window.switch_workspace('compose');window.replace_project(probe);window.open_harmony();app.processEvents()
    window.timer.stop();window.set_loop_range((0,960));window.seek(0);window.toggle_play()
    worker=window.transport.thread;clock=window.transport.start_time;anchor=window.play_anchor;head=window.playhead
    window.follow_playhead.setChecked(True);window.navigator.browse_to(window.navigator.width()*2/3)
    assert not window.follow_playhead.isChecked() and window.playhead==head and window.play_anchor==anchor
    assert window.transport.thread is worker and window.transport.start_time==clock
    window.loop.setChecked(False)
    deadline=time.perf_counter()+2
    while window.transport.position()<=1100 and time.perf_counter()<deadline:time.sleep(.005)
    assert window.transport.position()>1100 and window.transport.thread is worker and not window.transport.loop
    assert window.transport.start_time==clock and window.transport.end_tick==probe.end
    window.stop();window.seek(960);roll=window.roll;roll.horizontalScrollBar().setValue(300)
    x=300;offset=window.timeline.offset();tick=(x-offset-KEY_W+roll.horizontalScrollBar().value())/roll.zoom*960
    event=QWheelEvent(QPointF(x,16),QPointF(x,16),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.ControlModifier,Qt.ScrollPhase.NoScrollPhase,False)
    app.sendEvent(window.timeline,event)
    assert abs(window.timeline.x_at(tick)-x)<=1 and window.harmony_window.roll.zoom==roll.zoom
    head=window.playhead;roll.place_cursor(QPointF(KEY_W+50,roll.ruler_height+40));assert window.playhead==head
    roll.horizontalScrollBar().setValue(0);menu=roll.lane.context_menu(QPoint(round(roll.lane.x_at(1200)),20))
    assert menu.root_menu.actions()[0].text()=='1 · F' and menu.root_menu.actions()[1].text()=='#1 · F#'
    window.roll.zoom_at(78/window.roll.zoom);window.melody_window.setFloating(True);window.harmony_window.setFloating(True);app.processEvents()
    assert window.timeline.roll is window.main_roll and window.chord_lane.editor is window.main_roll
    window.melody_sync.setChecked(False);window.harmony_window.sync.setChecked(False)
    for _,_,_,controls in window.view_panes():
        assert all(c.isVisible() for c in (controls.play,controls.replay,controls.loop,controls.follow,controls.bpm))
        controls.follow.setChecked(True)
    before=[r.horizontalScrollBar().value() for r in (window.roll,window.harmony_window.roll)]
    window.shared_scroll.setValue(350)
    assert [r.horizontalScrollBar().value() for r in (window.roll,window.harmony_window.roll)]==before
    window.melody_sync.setChecked(True);window.roll.horizontalScrollBar().setValue(500)
    assert window.shared_scroll.value()==500 and window.harmony_window.roll.horizontalScrollBar().value()==before[1]
    window.follow_playhead.setChecked(False);window.melody_transport.follow.setChecked(True);window.harmony_window.transport_controls.follow.setChecked(False)
    window.follow_views(20000);assert window.shared_scroll.value()>500 and window.roll.horizontalScrollBar().value()==window.shared_scroll.value()
    from PySide6.QtWidgets import QAbstractSlider
    window.follow_playhead.setChecked(True);window.shared_scroll.triggerAction(QAbstractSlider.SliderAction.SliderSingleStepAdd)
    assert not window.follow_playhead.isChecked() and not window.melody_transport.follow.isChecked()
    roll=window.roll;roll.set_compact(False);roll.center_pitch(60);roll.set_row_height(35)
    assert abs(roll.y_at(60)+roll.row_height/2-(roll.ruler_height+(roll.viewport().height()-roll.ruler_height)/2))<=1
    # Exercise region overwrite and clipboard operations in the distributed runtime.
    from lingfeng.music.chord_operations import ChordClipboard, split_chords, merge_chords, pattern_template
    from lingfeng.ui.keybindings import normalized, validate
    probe=Project();probe.chords=[Chord(0,3840,pattern='up'),Chord(3840,3840,55)]
    probe.chords[0].materialize();assert pattern_template(probe.chords[0]).pattern=='up'
    repartition_chord(probe,probe.chords[0].id,0,4800);assert probe.chords[0].pattern=='up' and probe.chords[1].start==4800
    repartition_chord(probe,probe.chords[0].id,480,2880);assert len(probe.chords)==2 and not probe.chord_at(3000)
    clip=ChordClipboard.capture(probe.chords);ids=clip.paste(probe,10000);pasted=[c for c in probe.chords if c.id in ids];assert pasted[1].start==pasted[0].end
    probe=Project();probe.chords=[Chord(0,3840)];ids=split_chords(probe,{probe.chords[0].id});merge_chords(probe,ids);assert len([c for c in probe.chords if c.notes!=[]])==1
    window.replace_project(probe);window.chord_selection(set());window.chord_selection({probe.chords[0].id},window.harmony_window.roll)
    assert not window.roll.selected_chords and window.harmony_window.roll.selected_chords
    window.harmony_window.roll.anchor_tick=960;window.harmony_window.roll.cursor_tick=4800;assert window.harmony_window.roll.position_tick()==960
    validate(normalized({}));assert normalized({})['up']=='Up' and normalized({})['view_left']=='' and normalized({})['view_right']=='' and normalized({})['switch_input']=='E' and normalized({})['toggle_tool']=='Q'
    from lingfeng.music.rhythm import analyze as analyze_rhythm
    from lingfeng.music.note_operations import resize_chord
    probe=Project();probe.notes=[Note(0,960,60),Note(960,1920,60),Note(0,3840,64)]
    window.switch_workspace('compose')
    window.replace_project(probe);note=__import__('copy').deepcopy(probe.notes[0]);note.duration=1920
    window.roll.notesResized.emit([note])
    assert [(n.start,n.end) for n in window.project.notes if n.pitch==60]==[(0,1920),(1920,2880)]
    window.roll.selected_ids={n.id for n in window.project.notes if n.start==0};window.note_command(window.roll,'copy:direct');window.note_command(window.roll,'paste',960)
    assert {n.pitch for n in window.project.notes if n.start==960}=={60,64};window.project.validate()
    lyric_probe=copy.deepcopy(window.project);lyric_probe.notes=[n for n in lyric_probe.notes if n.pitch==60]
    window.replace_project(lyric_probe)
    put(window.project,3000,'旧');window.switch_workspace('compose');assert matching_issues(window.project)
    assert window.switch_workspace('score') and matching_issues(window.project)
    export_pdf(window.project,folder/'stale-lyrics.pdf')
    panel=window.lyric_panel;panel.start.setValue(1);panel.count.setValue(1);panel.text.setPlainText('这些歌词无法匹配');before=window.project.to_dict();panel.commit();assert window.project.to_dict()==before and not panel.check()
    chord=Chord(0,3840,48,'7',4,notes=[Note(0,3840,k,v) for k,v in [(40,70),(52,85),(55,90),(58,76),(60,88),(64,94)]])
    probe=Project();probe.chords=[chord];before=probe.to_dict();assert analyze_rhythm(chord).pattern=='block' and probe.to_dict()==before
    repartition_chord(probe,chord.id,0,1920);assert analyze_rhythm(probe.chords[0]).pattern=='block'
    repartition_chord(probe,chord.id,0,4800);assert {(n.start,n.end) for n in probe.harmony_notes()}=={(0,3840),(3840,4800)}
    assert {n.pitch:n.velocity for n in probe.harmony_notes()}=={pitch:chord.velocity for pitch in chord.pitches}
    probe.save(folder/'recognized-rhythm.lfs');assert analyze_rhythm(Project.load(folder/'recognized-rhythm.lfs').chords[0]).pattern=='block'
    window.switch_workspace('compose');window.melody_window.setFloating(False);window.harmony_window.setFloating(False)
    probe=Project();probe.notes=[Note(0,960,60)];probe.chords=[Chord(0,3840,48,'',4)];window.replace_project(probe)
    roll=window.roll;roll.selected_ids={probe.notes[0].id};roll.edit_target='notes'
    # Exercise the same command mapping used by customizable keyboard bindings.
    roll.setFocus();window.visibility_actions['melody'].setChecked(True);window.activateWindow();app.processEvents()
    window.editor_key_command('up');assert window.project.notes[0].pitch==61
    window.editor_key_command('down');window.editor_key_command('scale_up');assert window.project.notes[0].pitch==62
    from lingfeng.music.chord_operations import change_chords
    from lingfeng.music.recognition import chord_inversion
    change_chords(window.project,{probe.chords[0].id},'diatonic:1');assert window.project.chords[0].name=='Dm' and chord_inversion(window.project.chords[0])==0
    window.open_harmony();assert not window.visibility_actions['chords'].isChecked()
    window.visibility_actions['chords'].setChecked(True);window.refresh();assert window.visibility_actions['chords'].isChecked()
    window.harmony_window.setFloating(True);assert window.visibility_actions['chords'].isChecked()
    window.harmony_window.close();app.processEvents();assert window.harmony_window.isFloating() and not window.harmony_window.isVisible() and not window.visibility_actions['harmony'].isChecked()
    window.visibility_actions['harmony'].setChecked(True);assert not window.harmony_window.isFloating() and window.harmony_window.isVisible() and not window.visibility_actions['chords'].isChecked()
    cid=window.project.chords[0].id;window.harmony_window.roll.lane.hover_event(cid);assert window.roll.chord_highlights=={cid}
    window.visibility_actions['chords'].setChecked(True);assert not window.roll.chord_highlights
    window.melody_window.setFloating(True);window.roll.lane.hover_event(cid);assert window.roll.chord_highlights=={cid}
    window.visibility_actions['chords'].setChecked(False);assert window.roll.panels['chords']
    # Current chord editing contracts, exercised inside the packaged runtime.
    from PySide6.QtCore import QPoint
    window.melody_window.setFloating(False);window.harmony_window.setFloating(False)
    probe=Project();probe.chords=[Chord(0,3840,48,'',4),Chord(3840,3840,55)];window.replace_project(probe)
    window.visibility_actions['chords'].setChecked(True);lane=window.chord_lane;roll=lane.editor
    lane.selection_event({probe.chords[0].id});roll.edit_target='chords';head=window.playhead
    window.next_chord(roll);assert roll.selected_chords=={probe.chords[1].id} and window.playhead==head
    window.next_chord(roll);assert roll.selected_chords=={probe.chords[0].id}
    change_chords(probe,{probe.chords[0].id},'root_step:1');assert probe.chords[0].name=='C#' and probe.chords[0].bass is None
    change_chords(probe,{probe.chords[0].id},'root_step:-1');change_chords(probe,{probe.chords[0].id},'diatonic:1');assert probe.chords[0].name=='Dm'
    menu=lane.context_menu(QPoint(round(lane.x_at(960)),25));assert all(not a.isCheckable() for a in menu.inversion_menu.actions())
    probe=Project()
    for beat,(root,quality) in enumerate(((48,''),(53,''),(55,''),(57,'m'))):probe.put_chord(Chord(beat*960,960,root,quality,pattern='up'))
    assert [c.render_notes()[0].pitch for c in probe.chords]==[36,57,43,60]
    from lingfeng.music.chord_operations import move_chords
    c=Chord(480,3840,48,'',notes=[Note(113,431,60,71),Note(777,293,64,103),Note(1501,607,67,89)])
    probe.chords=[c];before=[(n.start,n.duration,n.pitch,n.velocity) for n in c.notes];move_chords(probe,{c.id},960)
    c=probe.chords[0];assert [(n.start,n.duration,n.pitch,n.velocity) for n in c.notes]==before
    repartition_chord(probe,c.id,1200,6000);assert [(n.start+1200,n.duration,n.pitch,n.velocity) for n in probe.chords[0].notes]==[(t+1440,d,p,v) for t,d,p,v in before]
    # Explicit Custom state is saved, and only pattern application unlocks it.
    probe=Project();probe.put_chord(Chord(0,3840,pattern='up'));c=probe.chords[0]
    change_chords(probe,{c.id},'custom:1');assert c.custom_rhythm and analyze_rhythm(c,probe) is None
    probe.save(folder/'custom-rhythm.lfs');probe=Project.load(folder/'custom-rhythm.lfs');c=probe.chords[0]
    assert c.custom_rhythm;change_chords(probe,{c.id},'custom:0');assert analyze_rhythm(c,probe).pattern=='up'
    change_chords(probe,{c.id},'transpose:12');assert c.custom_rhythm
    change_chords(probe,{c.id},'pattern:quarters');assert not c.custom_rhythm and analyze_rhythm(c,probe).pattern=='quarters'
    probe.notes=[Note(0,480,60)];probe.chords.append(Chord(3840,3840));window.replace_project(probe)
    r=window.roll;r.selected_ids={probe.notes[0].id};r.refresh();lane=window.chord_lane
    menu=lane.context_menu(QPoint(round(lane.x_at(480)),25));assert not r.selected_ids and r.selected_chords=={c.id}
    assert hasattr(menu,'recognition_names_menu')
    single=[a.text() for a in menu.actions() if a.menu() is not menu.recognition_names_menu]
    lane.selection_event({x.id for x in probe.chords});menu=lane.context_menu(QPoint(round(lane.x_at(480)),25))
    assert [a.text() for a in menu.actions()]==single and not menu.root_menu.isEnabled()
    r.selected_ids={probe.notes[0].id};r.refresh();assert not r.selected_chords
    timeline=r.timeline_menu(QPoint(round(r.x_at(480)),10));assert len([a for a in timeline.actions() if not a.isSeparator()])==9
    assert timeline.section_action.text()==tr('段落标识') and timeline.section_jump_action.text()==tr('跳转小节')
    assert timeline.section_selection_action.text()==tr('选中此段落')
    window.switch_workspace('score');window.show_score_panel('logic');head=window.playhead
    window.open_score_roll('chords',3840);app.processEvents();assert window.score_tabs.currentWidget() is window.score_harmony_page and window.playhead==head
    window.audition_chord(probe.chords[1].id);assert window.transport.audition_notes[3]==probe.chords[1].pitches
    assert window.transport.audition_holds[3][1]>=4*60/probe.bpm;window.transport.end_audition(True,True)
    window.transport.begin_chords_audition(probe.chords,probe.bpm);assert window.transport.audition_holds[3][1]==sum(c.duration for c in probe.chords)*60/(probe.bpm*960)
    window.transport.end_audition(True,True)
    probe.set_markers([1],53,'Dorian',5,4);export_pdf(probe,folder/'mixed-markers.pdf')
    # Uniform note overwrite and shared tool-window controls in the frozen runtime.
    window.switch_workspace('compose');probe=Project();probe.notes=[Note(0,3840,60,51),Note(4800,480,62,99)];probe.chords=[Chord(0,1920),Chord(1920,5760,55)]
    window.replace_project(probe);window.add_note(Note(960,480,60,111))
    assert [(n.start,n.duration) for n in window.project.notes if n.pitch==60]==[(0,960),(960,480),(1440,2400)]
    moved=copy.deepcopy(window.project.notes[-1]);moved.start=1920;moved.pitch=60;window.move_note(moved)
    assert any(n.start==2400 and n.end==3840 and n.velocity==51 for n in window.project.notes)
    window.open_harmony();app.processEvents();lane=window.harmony_window.roll.lane
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtCore import QPointF
    point=QPointF(300,20);zoom=lane.editor.zoom
    app.sendEvent(lane,QWheelEvent(point,QPointF(lane.mapToGlobal(point.toPoint())),QPoint(),QPoint(0,120),Qt.MouseButton.NoButton,Qt.KeyboardModifier.ShiftModifier,Qt.ScrollPhase.NoScrollPhase,False))
    assert window.roll.zoom==window.main_roll.zoom==window.harmony_window.roll.zoom==zoom*1.2
    from lingfeng.ui.theme import set_roll_coloring
    set_roll_coloring({'melody':{'match':False,'scale':False}});assert window.roll.category(60,0)=='other';set_roll_coloring({})
    window.melody_window.setFloating(True);window.harmony_window.setFloating(True);app.processEvents()
    assert window.melody_window.windowType()==Qt.WindowType.Window==window.harmony_window.windowType()
    window.follow_playhead.setChecked(False);window.melody_sync.setChecked(True);assert not window.melody_transport.follow.isChecked()
    window.melody_transport.follow.setChecked(True);assert window.follow_playhead.isChecked()
    window.melody_sync.setChecked(False);window.follow_playhead.setChecked(False);assert window.melody_transport.follow.isChecked()
    window.harmony_window.roll.lane.velocity_action.setChecked(True);assert window.harmony_window.roll.lane.velocity_visible
    assert window.melody_sync in window.melody_transport.options.menu().actions()
    window.melody_window.activateWindow();window.roll.setFocus();app.processEvents();window.tool.setCurrentIndex(window.tool.findData('smart'))
    window.editor_key_command('toggle_tool');assert window.roll.tool=='draw'
    window.editor_key_command('toggle_tool');assert window.roll.tool=='smart'
    from lingfeng.audio.midi_import import MidiData, MidiTrack, apply_midi
    legato=Project();notes=[Note(t,min(980,3840-t),pitch) for t in range(0,3840,960) for pitch in (48,52,55)]
    apply_midi(legato,MidiData([MidiTrack('Legato',notes,3840)],[],[]),[0],'chords',0)
    from lingfeng.music.rhythm import analyze
    assert len(legato.harmony_notes())==12 and analyze(legato.chords[0],legato).pattern!='block'
    window.melody_volume.sliders['chords'].setValue(57);assert window.project.volumes['chords']==57==window.harmony_window.volume_controls.sliders['chords'].value()
    window.melody_volume.mutes['melody'].click();assert window.mute_buttons['melody'].isChecked()==window.harmony_window.volume_controls.mutes['melody'].isChecked()
    window.melody_chords_action.setChecked(False);window.mount_panels();assert not window.roll.panels['chords']
    window.melody_window.setFloating(False);window.harmony_window.setFloating(False);app.processEvents()
    # Reparenting peer windows posts resize/layout events. Measure transport's
    # cache only after those independent layout changes have finished.
    settle=QEventLoop();QTimer.singleShot(75,settle.quit);settle.exec()
    window.show_cursor(0);app.processEvents();renders=window.roll.cache_renders
    for tick in range(100,1000,100):window.show_cursor(tick);app.processEvents()
    assert window.roll.cache_renders==renders
    # Exercise the same key-event route inside the frozen application.
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QKeyEvent
    window.project=demo_project();window.refresh();window.melody_window.setFloating(True);window.harmony_window.setFloating(True)
    assert window.melody_window.parentWidget() is None and window.harmony_window.parentWidget() is None
    window.harmony_window.activateWindow();r=window.harmony_window.roll;r.setFocus();app.processEvents()
    window.select_element('notes',r);r.selected_ids={r.notes[0].id};r.refresh()
    def key(widget,code):app.sendEvent(widget,QKeyEvent(QEvent.Type.KeyPress,code,Qt.KeyboardModifier.ControlModifier));app.processEvents()
    key(r,Qt.Key.Key_C);assert window.clipboard_kind=='notes' and window.note_clipboard
    before=window.project.to_dict();window.note_command(r,'chromatic:1')
    window.melody_window.activateWindow();window.roll.setFocus();app.processEvents();key(window.roll,Qt.Key.Key_Z)
    assert window.project.to_dict()==before and app.activeWindow() is window.harmony_window
    key(r,Qt.Key.Key_Y);assert window.project.to_dict()!=before
    window.switch_workspace('score');window.activateWindow();app.processEvents();gap=window.project.notation['row_gap'];window.note_font.setValue(20)
    accepted=min(20,window.note_font.maximum())
    assert window.note_font.isVisible() and window.project.notation['row_gap']==gap and window.project.notation['font_size']==accepted
    assert abs(window.score_view.canvas.layout.glyph_scale-accepted/15)<1e-7
    for language,word in [('zh','轻量级'),('en','lightweight')]:
        window.change_language(language,False);dialog=HelpDialog(window,True)
        assert word in dialog.browser.toPlainText() and all(term in dialog.browser.toPlainText() for term in ('MIT','Hooktheory','Cakewalk Next'));dialog.close();dialog.deleteLater()
    import lingfeng.ui.theme as theme
    music=window.project.to_dict();window.note_degrees_action.setChecked(False);app.processEvents()
    assert not theme.SHOW_NOTE_DEGREES and window.project.to_dict()==music
    window.switch_workspace('compose');window.melody_window.setFloating(False);window.melody_window.setFloating(True)
    assert not window.note_degrees_action.isChecked() and window.melody_window.parentWidget() is None
    window.note_degrees_action.setChecked(True)
    release_root=application_root()
    assert 'MIT License' in (release_root/'LICENSE').read_text('utf-8')
    from lingfeng.music.meter import moved_chord, regions
    from lingfeng.music.chord_operations import roman_label, chord_details
    from lingfeng.music.rhythm import supports
    mixed=Project();mixed.set_markers([1],50,'Dorian',3,4)
    c=Chord(3840,1920,pattern='up');mixed.put_chord(c);c=mixed.chords[0]
    assert moved_chord(mixed,c,0) is None
    cropped=moved_chord(mixed,c,6240);assert cropped.end==6720 and analyze(cropped,mixed).pattern=='up'
    assert not supports('bass_chord',mixed,c.start) and supports('up',mixed,c.start)
    sustain=Chord(0,6000);assert ' → ' in roman_label(mixed,sustain) and 'Dorian' in chord_details(mixed,sustain)
    before_notes=[(n.start,n.duration,n.pitch) for n in mixed.harmony_notes()]
    mixed.change_meter(0,5,4);assert [(n.start,n.duration,n.pitch) for n in mixed.harmony_notes()]==[(t+960,d,p) for t,d,p in before_notes]
    assert all(any(a<=c.start<c.end<=b for a,b,m in regions(mixed)) for c in mixed.chords)
    from lingfeng.ui.controls import IconButton
    assert all(isinstance(b,IconButton) for b in window.title_bar.window_buttons+window.harmony_window.title_bar.buttons)
    joined=Project();joined.chords=[Chord(0,3840,notes=[Note(960,2880,60,event_id="held")]),Chord(3840,3840,notes=[Note(0,3840,60,event_id="held")])]
    r=window.harmony_window.roll;r.set_project(joined)
    assert r.expand_note_selection({r.notes[0].id})=={n.id for n in r.notes}
    assert (release_root/'docs'/'THIRD_PARTY.md').is_file()
    assert (release_root/'licenses'/'qt-6.9.2'/'manifest.json').is_file()
    if getattr(sys,'frozen',False):assert not (release_root/'_internal'/'PySide6'/'opengl32sw.dll').exists()
    # New editing controls must also work from the portable executable.
    probe=Project();probe.contexts=[Context(0,3840,48),Context(3840,7680,56,'Aeolian'),Context(7680,probe.end,58,'Dorian')]
    probe.notes=[Note(0,9600,60)];probe.chords=[Chord(0,3840,quality='9')]
    window.switch_workspace('compose');window.replace_project(probe);window.melody_window.setFloating(False);window.open_harmony();app.processEvents()
    r=window.roll;assert r.note_degree_label(60,0,9600)=='1 (3, 2)'
    lane=window.chord_lane;menu=lane.context_menu(QPoint(round(lane.x_at(480)),20))
    assert len(menu.bass_menu.actions())==12 and len(menu.inversion_menu.actions())==5
    assert all(a.isEnabled() and not a.isCheckable() for a in menu.inversion_menu.actions())
    menu.inversion_menu.actions()[4].trigger();assert window.project.chords[0].bass==2
    menu.bass_menu.actions()[1].trigger();assert window.project.chords[0].bass==1
    track=window.roll.melody_track
    window.melody_hide.activated.emit()
    assert not window.melody_view_actions[track].isChecked() and window.melody_view_actions[1-track].isChecked()
    assert window.melody_tabs.isHidden() and window.melody_window.isVisible()
    window.melody_view_actions[track].setChecked(True)
    window.harmony_window.hide_button.activated.emit();assert not window.visibility_actions['harmony'].isChecked()
    from lingfeng.ui.dialogs import MarkerDialog
    dialog=MarkerDialog(window.project,1,window,True);dialog.count.setValue(3);assert dialog.count.value()==3;dialog.close()
    original=window.project.end;window.project.insert_measures(1,3);assert window.project.end==original+11520;window.refresh()
    r=window.roll;r.center_pitch(60);r.selected_ids={n.id for n in r.notes};window.note_command(r,'chromatic:-24')
    assert r.y_at(36)+r.row_height<=r.viewport().height()
    # Chord pastes accept different meters; moved selections still crop/recover.
    from lingfeng.music.chord_operations import ChordMoveSession
    from lingfeng.music.bar_operations import delete_bars
    from lingfeng.music.rhythm import label as pattern_label
    probe=Project();probe.set_markers([1],50,'Dorian',3,4);probe.chords=[Chord(3840,960)]
    clip=ChordClipboard.capture(probe.chords,probe);assert clip.can_paste(probe,0)
    selection=ChordMoveSession.capture(probe,{probe.chords[0].id});selection.apply(probe,-1920);selection.delta=-1920;assert not probe.chords
    selection.apply(probe,1920);assert probe.chords[0].start==3840 and probe.chords[0].duration==960
    probe.chords[0].custom_rhythm=True;assert pattern_label(probe.chords[0],probe)==tr('自定义（锁定）')
    probe.notes=[Note(3000,5000,60)];delete_bars(probe,[1]);assert [(n.start,n.duration) for n in probe.notes]==[(3000,840),(3840,1280)]
    window.replace_project(probe);menu=window.roll.timeline_menu(QPoint(round(window.roll.x_at(480)),10));assert any(a.text()==tr('删除所选小节…') for a in menu.actions())
    # Editor navigation and shared grid keyboard controls in the shipped app.
    from lingfeng.ui.keybindings import load_bindings
    from lingfeng.music.chord_operations import can_apply_pattern, change_chords
    from PySide6.QtGui import QMouseEvent
    def editor_key(code,modifiers=Qt.KeyboardModifier.NoModifier):
        app.sendEvent(lane,QKeyEvent(QEvent.Type.KeyPress,code,modifiers));app.processEvents()
    def mouse(kind,pos,button,buttons):
        app.sendEvent(lane,QMouseEvent(kind,QPointF(pos),QPointF(lane.mapToGlobal(pos)),button,buttons,Qt.KeyboardModifier.NoModifier));app.processEvents()
    window.keybindings=load_bindings({});window.switch_workspace('compose')
    window.melody_window.setFloating(False);window.harmony_window.setFloating(False)
    window.visibility_actions['melody'].setChecked(True);window.visibility_actions['chords'].setChecked(True)
    probe=Project();probe.chords=[Chord(0,960),Chord(1920,960,50,'m')];window.replace_project(probe);app.processEvents()
    lane=window.chord_lane;r=lane.editor;window.activateWindow();lane.setFocus();lane.selection_event({c.id for c in probe.chords});app.processEvents()
    before=window.project.to_dict();head=window.playhead;scroll=r.horizontalScrollBar().value()
    positions=[c.start for c in probe.chords]
    editor_key(Qt.Key.Key_Right);assert [c.start for c in window.project.chords if c.id in r.selected_chords]==[t+r.grid for t in positions] and window.playhead==head
    editor_key(Qt.Key.Key_Left);assert [c.start for c in window.project.chords if c.id in r.selected_chords]==positions and r.horizontalScrollBar().value()==scroll
    window.grid.setCurrentIndex(4);duration=window.length.currentData()
    editor_key(Qt.Key.Key_3,Qt.KeyboardModifier.ShiftModifier);assert window.grid.triplet and window.harmony_window.grid.triplet and window.length.currentData()==duration
    editor_key(Qt.Key.Key_3,Qt.KeyboardModifier.ShiftModifier);assert not window.grid.triplet
    selected=[c for c in window.project.chords if c.id in r.selected_chords]
    ids={c.id for c in selected};assert can_apply_pattern(window.project,selected,'up')
    change_chords(window.project,ids,'pattern:up');assert all(analyze(c,window.project).pattern=='up' for c in selected)
    window.project.chords=[];window.refresh();app.processEvents();lane=window.chord_lane;before=lane.grab().toImage()
    mouse(QEvent.Type.MouseButtonPress,QPoint(180,20),Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton)
    mouse(QEvent.Type.MouseMove,QPoint(lane.width()-2,40),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton);assert lane.marquee is not None
    scroll=lane.editor.horizontalScrollBar().value()
    mouse_buttons=QApplication.mouseButtons
    try:
        QApplication.mouseButtons=staticmethod(lambda:Qt.MouseButton.LeftButton)
        lane.scroll_drag_edge()
    finally:QApplication.mouseButtons=mouse_buttons
    assert lane.editor.horizontalScrollBar().value()>scroll
    mouse(QEvent.Type.MouseButtonRelease,QPoint(lane.width()-2,40),Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton);assert lane.marquee is None and not lane.edge_timer.isActive()
    lane.editor.horizontalScrollBar().setValue(scroll);app.processEvents();assert lane.grab().toImage()==before
    # Selection narrows on click; a group drag previews without mutating MIDI.
    probe=Project();probe.notes=[Note(480,960,60),Note(2400,960,64)];probe.chords=[Chord(480,960),Chord(2400,960,50,'m')]
    window.replace_project(probe);window.visibility_actions['chords'].setChecked(True);app.processEvents()
    lane=window.chord_lane;r=lane.editor;lane.selection_event({c.id for c in probe.chords});app.processEvents()
    pos=QPoint(round(lane.x_at(960)),25)
    mouse(QEvent.Type.MouseButtonPress,pos,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton)
    mouse(QEvent.Type.MouseButtonRelease,pos,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)
    assert r.selected_chords=={probe.chords[0].id}
    lane.selection_event({c.id for c in probe.chords});before=window.project.to_dict()
    mouse(QEvent.Type.MouseButtonPress,pos,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton)
    mouse(QEvent.Type.MouseMove,pos+QPoint(round(r.zoom),0),Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton)
    assert len(lane.previews)==2 and len(lane.drag_originals)==2 and window.project.to_dict()==before
    editor_key(Qt.Key.Key_Escape)
    mouse(QEvent.Type.MouseButtonRelease,pos,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)
    assert not lane.previews and window.project.to_dict()==before
    # An extended left card must cover the right card, including its text.
    from PySide6.QtGui import QImage,QPainter
    r.zoom=100;r.horizontalScrollBar().setValue(0);r.update_ranges()
    overlay=copy.deepcopy(probe.chords[0]);overlay.duration=2880
    lane.preview=overlay;lane.previews={overlay.id:overlay};r.selected_chords={overlay.id}
    def chord_image():
        image=QImage(lane.width(),lane.height(),QImage.Format.Format_ARGB32_Premultiplied);image.fill(Qt.GlobalColor.transparent)
        painter=QPainter(image)
        try:lane.paint_content(painter)
        finally:painter.end()
        return image
    actual=chord_image();left=round(lane.x_at(2400))+5;right=round(lane.x_at(3360))-5
    assert lane.chord_hit(QPointF(lane.x_at(2800),25))[1].id==overlay.id
    saved=probe.chords
    try:probe.chords=saved[:1];reference=chord_image()
    finally:probe.chords=saved
    assert actual.copy(left,9,right-left,44)==reference.copy(left,9,right-left,44)
    lane.preview=None;lane.previews={};r.refresh()
    from lingfeng.music.chord_operations import contextual_chord_name, chord_details
    probe=Project();probe.contexts=[Context(0,probe.end,53,'Ionian')]
    c=Chord(960,1920,62,'m',pattern='quarters');probe.put_chord(c);c=probe.chords[0]
    change_chords(probe,{c.id},'quality:m7');assert analyze(c,probe).pattern=='quarters' and c.quality=='m7'
    bb=Chord(0,1920,58);assert contextual_chord_name(probe,bb)=='Bb'
    cm=Chord(0,1920,48,'m');assert 'Eb' in chord_details(Project(),cm) and '♭3' in chord_details(Project(),cm)
    from lingfeng.ui.dialogs import ChordDialog
    dialog=ChordDialog(bb,probe,window);assert dialog.root.itemText(0)=='1 · F' and dialog.root.itemText(dialog.root.findData(10))=='4 · A#';dialog.close();dialog.deleteLater()
    from lingfeng.engraving.notation import fragments_for_bar
    probe=Project();probe.notes=[Note(2,118,60)];before=probe.to_dict()
    fragments=[f for f in fragments_for_bar(probe,0) if f.note]
    assert len(fragments)==1 and not fragments[0].continuation and not fragments[0].continues and probe.to_dict()==before
    # The upper bar editor and lower loop/position ruler share no selection state.
    probe=Project();probe.notes=[Note(0,960,60),Note(960,960,60)];probe.chords=[Chord(0,1920)]
    window.replace_project(probe);window.switch_workspace('compose');window.melody_window.setFloating(False);window.harmony_window.setFloating(False)
    window.visibility_actions['melody'].setChecked(True);window.visibility_actions['chords'].setChecked(True);app.processEvents()
    r=window.roll;r.zoom=120;r.update_ranges();r.timeViewChanged.emit();r.center_pitch(60);r.horizontalScrollBar().setValue(0);app.processEvents()
    def pointer(surface,kind,point,button,buttons):
        event=QMouseEvent(kind,QPointF(point),QPointF(surface.mapToGlobal(point)),button,buttons,Qt.KeyboardModifier.NoModifier)
        app.sendEvent(surface,event)
    def gesture(surface,a,b,button=Qt.MouseButton.LeftButton):
        pointer(surface,QEvent.Type.MouseButtonPress,a,button,button)
        if a!=b:pointer(surface,QEvent.Type.MouseMove,b,Qt.MouseButton.NoButton,button)
        pointer(surface,QEvent.Type.MouseButtonRelease,b,button,Qt.MouseButton.NoButton);app.processEvents()
    timeline=window.timeline;y=timeline.roll.bar_ruler_height+15
    a=QPoint(round(timeline.x_at(960)),y);b=QPoint(round(timeline.x_at(2500)),y)
    gesture(timeline,a,b);assert window.loop_range==(960,2640) and window.loop.isChecked() and window.play_anchor==0
    for roll in (window.main_roll,window.roll,window.harmony_window.roll):assert roll.loop_range==window.loop_range
    gesture(timeline,QPoint(round(timeline.x_at(4000)),12),QPoint(round(timeline.x_at(4000)),12))
    assert window.roll.selection==[[3840,7680]] and window.loop_range==(960,2640) and window.play_anchor==0
    window.loop.setChecked(False);window.loop.setChecked(True);assert window.loop_range is None and not window.loop_active()
    gesture(timeline,a,b,Qt.MouseButton.RightButton);assert window.loop_range is None
    gap=QPoint(round(r.x_at(960)),round(r.y_at(60)+r.row_height/2));before=window.project.to_dict();gesture(r.viewport(),gap,gap)
    assert window.play_anchor==960 and window.project.to_dict()==before
    scroll=r.horizontalScrollBar().value();vertical=r.verticalScrollBar().value();gesture(r.viewport(),QPoint(500,180),QPoint(420,150),Qt.MouseButton.MiddleButton)
    assert r.horizontalScrollBar().value()==scroll+80 and r.verticalScrollBar().value()==vertical+30 and window.project.to_dict()==before
    window.status_message('Shared footer '*20)
    for footer in window.shared_footers():assert len(footer.hint.message)<=80
    window.switch_workspace('score');assert window.audio_footer.isVisible()
    from lingfeng.engraving.notation import is_chord_tone
    probe=Project();probe.chords=[Chord(0,960,58,notes=[Note(0,864,46)],pattern='bass_chord')]
    before=probe.to_dict();assert not is_chord_tone(probe,62,0) and not is_chord_tone(probe,65,320) and is_chord_tone(probe,58,0) and probe.to_dict()==before
    from lingfeng.ui.dialogs import ChordDialog
    from lingfeng.music.rhythm import analyze_performed
    assert analyze_performed(probe.chords[0],probe).pattern=='quarters'
    dialog=ChordDialog(probe.chords[0],probe);assert dialog.regenerate.isChecked() and dialog.pattern.currentData()=='quarters'
    rebuilt=dialog.value();probe.put_chord(rebuilt);dialog.deleteLater()
    assert {n.pitch%12 for n in probe.chords[0].render_notes()}=={10,2,5} and is_chord_tone(probe,62,320)
    window.switch_workspace('compose');window.open_harmony();window.grid.setCurrentIndex(6);window.grid.set_triplet(True)
    assert all(roll.grid==40 for roll in (window.main_roll,window.roll,window.harmony_window.roll))
    window.harmony_window.setFloating(True);window.set_timeline_sync(False,window.harmony_window.roll);window.harmony_window.grid.setCurrentIndex(7);window.harmony_window.grid.set_triplet(False)
    assert window.main_roll.grid==40 and window.harmony_window.roll.grid==30
    window.harmony_window.setFloating(False);assert window.harmony_window.roll.grid==40
    window.change_chord_ruler(.5);assert all(lane.aux_ruler_scale==.5 for lane in (window.chord_lane,window.roll.lane,window.harmony_window.top_lane))
    assert window.main_roll.grid==40
    window.melody_window.setFloating(True);app.processEvents();roll=window.roll;lane=roll.lane
    assert roll.viewport().mapToGlobal(QPoint()).x()+roll.x_at(960)==lane.mapToGlobal(QPoint()).x()+lane.x_at(960)
    from lingfeng.ui.piano_roll import PianoRoll
    from lingfeng.ui.theme import color
    from PySide6.QtGui import QImage,QPainter
    probe=Project();probe.chords=[Chord(0,960),Chord(960,960)]
    boundary_roll=PianoRoll(probe);boundary_roll.zoom=100;boundary_roll.selected_chords={c.id for c in probe.chords}
    boundary_lane=boundary_roll.lane;boundary_lane.setFixedSize(600,62)
    image=QImage(750,78,QImage.Format.Format_ARGB32_Premultiplied);image.setDevicePixelRatio(1.25);painter=QPainter(image)
    try:boundary_lane.paint_content(painter)
    finally:painter.end()
    assert image.pixelColor(int(boundary_lane.x_at(960)*1.25),30)==color('#FAFBFD')
    boundary_roll.deleteLater()
    # 0.34 runtime dependencies and soft chord-region boundaries.
    from lingfeng.music.chord_operations import split_at_position
    from lingfeng.music.progressions import apply as apply_progression, capture as capture_progression
    from lingfeng.audio.exporting import bounds, export_mp3
    from lingfeng.ui.export_dialog import ExportDialog
    import soundcard  # Loads the packaged WASAPI CFFI header, without recording.
    probe=Project();probe.fill_chord_gaps();assert len(probe.chords)==8 and not probe.harmony_notes()
    probe.measures[0].section='verse';probe.measures[2].section='verse'
    assert probe.sections()[:2]==[('verse',0,2),('verse',2,8)] and bounds(probe,'section',section=0)==(0,7680)
    probe.overwrite_harmony(Note(3000,6000,60,85));assert [(n.start,n.duration) for n in probe.harmony_notes()]==[(3000,6000)]
    probe.save(folder/'continuous.lfs');assert [(n.start,n.duration) for n in Project.load(folder/'continuous.lfs').harmony_notes()]==[(3000,6000)]
    split_at_position(probe,3400);assert [(n.start,n.duration) for n in probe.harmony_notes()]==[(3000,400),(3400,5600)]
    probe=Project();probe.fill_chord_gaps();ids=apply_progression(probe,probe.chords[0].id,'I V vi IV',False,'quarters',81)
    assert capture_progression(probe,set(ids))=='I V vi IV'
    # This acceptance check verifies STK's export credits even when new
    # projects prefer the separately bundled sampled piano pack.
    from lingfeng.audio.soundbanks import DEFAULT_DEVICE
    probe.audio={role:dict(device=DEFAULT_DEVICE,program=program) for role,program in (('melody',1),('chords',0),('instrument',1))}
    export_mp3(probe,folder/'offline.mp3',end=960);assert (folder/'offline.mp3').stat().st_size>10000
    export_midi(probe,folder/'range.mid','chords',960,1920)
    window.replace_project(probe)
    for format in ('pdf','midi','mp3'):
        dialog=ExportDialog(window,format)
        assert ('pages' in dialog.options())==(format=='pdf')
        if format=='mp3':assert dialog.mode.count()==2
        dialog.deleteLater()
    # 0.35: the six modal degree sequences, compact hints and dialog ownership.
    from lingfeng.music.model import MODES, spelling, Measure
    from lingfeng.ui.theme import set_accidental_preference
    from lingfeng.ui.progression_dialogs import ProgressionDialog
    from lingfeng.music.progressions import DEFAULT_PRESETS
    from lingfeng.ui.dialogs import MarkerDialog
    from lingfeng.music.rhythm import analyze, analyze_performed, label as rhythm_label
    from lingfeng.music.chord_operations import chord_details
    for mode,offsets in MODES.items():
        for flat in (False,True):assert [spelling(48+o,48,flat,mode)[0] for o in offsets]==list(range(1,8))
    probe.contexts[0].tonic=53
    dialog=ProgressionDialog(probe,probe.chords[0].id,DEFAULT_PRESETS)
    dialog.preset.setCurrentIndex(dialog.preset.findData('I V vi IV'))
    assert dialog.resolved.text()=='F – C – Dm – Bb' and dialog.roman.text()=='I – V – vi – IV';dialog.deleteLater()
    set_accidental_preference('flat');dialog=MarkerDialog(probe,0)
    assert 'Db4' in dialog.tonic.itemText(dialog.tonic.findData(61)) and ':Gb' in dialog.mode.itemText(dialog.mode.findData('Phrygian'))
    assert dialog.value()['mode']=='Ionian';dialog.deleteLater();set_accidental_preference('sharp')
    unknown=Chord(0,960,notes=[Note(0,960,60),Note(0,960,61)],recognized=False)
    assert analyze(unknown,probe) is None and analyze_performed(unknown,probe) is None and rhythm_label(unknown,probe)==tr('未知节奏型')
    hint=chord_details(probe,Chord(0,3840,53,'maj7'),compact=True)
    assert all(item in hint for item in ('1: F','3: A','5: C','7: E')) and 'F4' not in hint
    assert Measure(section='VERSE').section=='verse'
    r=window.harmony_window.roll;window.switch_workspace('compose');window.visibility_actions['harmony'].setChecked(True);window.harmony_window.setFloating(True);window.harmony_window.activateWindow();r.setFocus();app.processEvents()
    parent,origin=window.edit_dialog_origin();assert parent is window.harmony_window and origin is r
    # 0.36: View controls the main page; navigation retains existing floats.
    for pane in (window.melody_window,window.harmony_window):
        pane.setFloating(True);assert not window.visibility_actions[pane.key].isChecked() and pane.isVisible()
        pane.close();app.processEvents();window.mount_panels();assert not pane.isVisible()
        window.show_roll_in_place(pane);assert pane.isFloating() and pane.isVisible() and not window.visibility_actions[pane.key].isChecked()
        window.visibility_actions[pane.key].setChecked(True);assert not pane.isFloating() and pane.isVisible()
    from lingfeng.music.progressions import presets, progression_label
    assert progression_label('I-IV-V')=='I – IV – V'
    entries=presets([dict(name=s,sequence=s) for s in ('I IV vi','I IV V vi IV I V','I IV V')])
    assert [e['name'] for e in entries]==['I – IV – V','I – IV – V – vi – IV – I – V','I – IV – vi']
    # 0.37: searchable, editable library and complete named public recipes.
    from lingfeng.ui.progression_dialogs import ProgressionManagerDialog, ProgressionEntryDialog
    from lingfeng.music.progressions import make_preset, matches_roots, load_library, resolve, tokens
    from lingfeng.music.progression_catalog import HOOKTHEORY_RECIPES, CATALOG_VERSION
    assert len(HOOKTHEORY_RECIPES)==21
    assert [len(tokens(s)) for _,s,_ in HOOKTHEORY_RECIPES]==[4,5,4,4,4,4,5,4,4,4,3,3,4,3,3,3,3,3,4,3,5]
    for _,sequence,_ in HOOKTHEORY_RECIPES:
        for token in tokens(sequence):assert resolve(token,0).pitches
    assert resolve('V/vi/#5',0).bass==8 and resolve('vi7/5',0).bass==7
    assert matches_roots('I V IV ii iii','I-IV-III') and not matches_roots('I IV #III','I-IV-III')
    entry=ProgressionEntryDialog();entry.sequence.setText('IV-iv-I');assert entry.value()==make_preset('IV iv I')
    entry.name.setText('Cadencing in style');assert entry.value()['name']=='Cadencing in style';entry.deleteLater()
    manager=ProgressionManagerDialog([make_preset('I V IV iii','one'),make_preset('I IV #III','two')])
    manager.search.setText('I-IV-III');assert manager.table.rowCount()==1 and manager.table.item(0,0).text()=='one'
    manager.store_entry(make_preset('IV iv I','Cadence'));assert len(manager.value())==3
    manager.show();app.processEvents();manager.grab().save(str(folder/'progression-manager.png'));manager.close();manager.deleteLater()
    saved=[make_preset('I IV','My phrase')];assert load_library(saved,CATALOG_VERSION)==saved
    probe=Project();probe.chords=[Chord(0,3840)];dialog=ProgressionDialog(probe,probe.chords[0].id,[make_preset('IV iv I','Cadencing in style')])
    assert dialog.preset.currentText()=='Cadencing in style: IV – iv – I' and dialog.roman.text()=='IV – iv – I' and dialog.resolved.text()=='F – Fm – C';dialog.deleteLater()
    # 0.38: selected chord roots open the manager; saved bass survives application.
    from lingfeng.music.progressions import selection_root_query
    from PySide6.QtWidgets import QDialog
    from PySide6.QtCore import QPoint
    probe=Project();probe.chords=[Chord(0,3840,48,'',4),Chord(3840,3840,55),Chord(7680,3840,53,'maj7',9)]
    selected={probe.chords[0].id,probe.chords[2].id};recipe=capture_progression(probe,selected)
    assert recipe=='I/3 IVmaj7/6' and selection_root_query(probe,selected)=='I IV'
    manager=ProgressionManagerDialog([make_preset(recipe),make_preset('I #IV')],query='I IV')
    assert manager.table.rowCount()==1 and manager.table.item(0,1).text()=='I/3 – IVmaj7/6';manager.deleteLater()
    window.replace_project(probe);window.harmony_window.setFloating(True);r=window.harmony_window.roll
    r.lane.selection_event(selected);menu=r.lane.context_menu(QPoint(round(r.lane.x_at(100)),25))
    action=next(a for a in menu_actions(menu) if a.text()==tr('检索和弦进行…'));assert action.isEnabled()
    observed=[];original_exec=ProgressionManagerDialog.exec
    def inspect_search(dialog):
        observed.append((dialog.search.text(),dialog.parentWidget()));return QDialog.DialogCode.Rejected
    try:ProgressionManagerDialog.exec=inspect_search;action.trigger()
    finally:ProgressionManagerDialog.exec=original_exec
    assert observed==[('I – IV',window.harmony_window)];menu.deleteLater()
    target=Project();target.fill_chord_gaps();result_ids=apply_progression(target,target.chords[0].id,recipe,False,'block')
    assert [min(n.pitch for n in c.render_notes())%12 for c in target.chords if c.id in result_ids]==[4,9]
    from lingfeng.music.model import Measure
    probe=Project();probe.measures[0]=Measure(section='chorus');probe.measures[2]=Measure(section='CHORUS')
    assert Project.from_dict(probe.to_dict()).sections()==[('chorus',0,2),('chorus',2,8)]
    for quality,pcs in [('mM7',{0,3,7,11}),('add2',{0,2,4,7})]:
        c=Chord(0,PPQ,48,quality);probe.chords=[c]
        assert c.pcs==pcs and any(x.quality==quality and x.root==0 for x in recognize(c.pitches))
        assert resolve(capture_progression(probe,{c.id}),0).quality==quality
    legacy=probe.to_dict();legacy['chords'][0]['quality']='add9'
    for key in ('recognition_disabled','marked'):legacy['chords'][0].pop(key,None)
    migrated=Project.from_dict(legacy).chords[0]
    assert migrated.quality=='add2' and migrated.notes is None and migrated.pitches==[36,48,50,52,55]
    probe.contexts=[Context(0,probe.end,53)]
    defaults=dict(root=7,quality='mM7',bass=11,pattern='quarters',gate=70,velocity=82,octave=1)
    dialog=ChordDialog(Chord(3840,1920,notes=[],recognized=False),probe,defaults=defaults)
    assert dialog.root.itemText(0)=='1 · F' and dialog.options()==defaults
    assert (dialog.value().start,dialog.value().duration)==(3840,1920)
    dialog.close();dialog.deleteLater()
    from lingfeng.music.rhythm import ALTERNATING, regenerate, supports
    for denominator in (2,4,8,16):
        probe=Project();probe.measures=[Measure(4,denominator)];probe.contexts=[Context(0,probe.end)]
        beat=PPQ*4//denominator
        for pattern in ALTERNATING:
            c=regenerate(Chord(0,probe.end,48,'add2',pattern=pattern,gate=.75),0,probe.end,probe)
            assert [(n.start,n.pitch,n.duration) for n in c.notes if n.pitch<48]==[(i*beat,36 if i%2==0 else 43,round(.75*beat)) for i in range(4)]
            assert analyze(c,probe).pattern==pattern
            onset=beat//2 if pattern=='alternating_offbeat' else 0
            assert {n.pitch for n in c.notes if n.start==onset and n.pitch>=48}=={48,50,52,55}
        probe.measures=[Measure(3,denominator)]
        assert all(not supports(pattern,probe,0) for pattern in ALTERNATING)
    probe=Project();probe.notes=[Note(0,960,60,83),Note(960,480,64,71)];window.replace_project(probe)
    r=window.roll;r.edit_target='notes';r.selected_ids={n.id for n in r.notes}
    from PySide6.QtWidgets import QMenu
    menu=QMenu();r.selection_menu(menu,0);next(a for a in menu_actions(menu) if a.data()=='octave_up').trigger()
    assert [(n.pitch,n.velocity,n.start,n.duration) for n in window.project.notes]==[(72,83,0,960),(76,71,960,480)]
    window.undo();assert [n.pitch for n in window.project.notes]==[60,64];menu.deleteLater()
    # 0.40.1: a single registry drives menus, settings and conflict transfers.
    from lingfeng.ui.keybindings import COMMANDS, STANDARD, KeyBindingsDialog, normalized, load_bindings, validate
    from PySide6.QtGui import QKeySequence,QAction
    from PySide6.QtWidgets import QMessageBox
    bindings=normalized({});validate(bindings)
    dialog=KeyBindingsDialog(bindings,window)
    assert set(dialog.fields)==set(COMMANDS) and set(STANDARD.values())<=set(dialog.fields)
    dialog.fields['split'].setKeySequence(QKeySequence('Ctrl+S'))
    original_question=QMessageBox.question
    try:
        QMessageBox.question=lambda *args:QMessageBox.StandardButton.No
        assert not dialog.resolve_change('split') and dialog.value()==bindings
        dialog.fields['split'].setKeySequence(QKeySequence('Ctrl+S'))
        QMessageBox.question=lambda *args:QMessageBox.StandardButton.Yes
        assert dialog.resolve_change('split') and dialog.value()['save']=='' and dialog.value()['split']=='Ctrl+S'
    finally:QMessageBox.question=original_question
    reassigned=dialog.value();validate(reassigned);assert load_bindings(reassigned)==reassigned
    dialog.close();dialog.deleteLater();window.keybindings=reassigned;window.update_shortcuts()
    assert next(a for a in window.findChildren(QAction) if a.property('shortcutCommand')=='save').shortcut().isEmpty()
    menu=QMenu();r.selection_menu(menu,0)
    assert next(a for a in menu_actions(menu) if a.property('shortcutCommand')=='split').shortcut().toString()=='Ctrl+S'
    delete=next(a for a in menu_actions(menu) if a.property('shortcutCommand')=='delete')
    assert [s.toString() for s in delete.shortcuts()]==['Del','Backspace'] and 'Backspace' in delete.text()
    menu.deleteLater();window.keybindings=bindings
    window.replace_project(Project());window.length.setCurrentIndex(window.length.findData(-1));window.grid.setCurrentIndex(window.grid.findData(240));window.grid.set_triplet(False)
    r=window.roll;assert r.note_duration(0)==240 and r.previous_duration is None
    note=Note(0,720,60);window.add_note(note);assert r.note_duration(2000)==720
    window.grid.setCurrentIndex(window.grid.findData(120));assert r.note_duration(2000)==720 and r.duration==-1
    window.mutate('duration tracking',lambda p:setattr(p.notes[0],'duration',960));assert r.note_duration(2000)==960
    window.undo();assert r.note_duration(2000)==720
    c=resolve('I7b5',0);assert c.pitches==[36,48,52,54,58]
    assert recognize(c.pitches,preferred=(0,'7b5'))[0].quality=='7b5'
    probe=Project();probe.chords=[c];assert capture_progression(probe,{c.id})=='I7b5'
    assert Project.from_dict(probe.to_dict()).chords[0].quality=='7b5'
    # Score width follows density, with one global font and linear spatial time.
    from lingfeng.audio.synthesis import SynthEngine
    from lingfeng.audio.soundbanks import available_programs, credits_text, DEFAULT_DEVICE, GENERALUSER_GS_DEVICE, pack
    PROGRAMS=available_programs(DEFAULT_DEVICE)
    from lingfeng.ui.dialogs import SoundSettingsDialog
    import numpy as np
    probe=Project();probe.notes=[Note(0,960,60)]+[Note(3840+i*120,120,60+i%5) for i in range(32)]
    probe.notation['font_size']=12
    fitted=ScoreLayout(probe);system=fitted.systems[0]
    assert system.bar_widths[1]>system.bar_widths[0] and system.bar_scales[0]==system.bar_scales[1]<=.8
    for bar,width in zip(system.bars,system.bar_widths):
        points,positions,*_=fitted.bar_map(system,bar,0,width)
        assert all(abs(x-width*(t-probe.starts[bar])/probe.measures[bar].ticks)<1e-7 for t,x in zip(points,positions))
    samples=[]
    for program in PROGRAMS:
        engine=SynthEngine(DEFAULT_DEVICE);engine.send(0xc0,program);engine.send(0x90,60,90);data=engine.render(4096)
        assert np.isfinite(data).all() and np.max(abs(data))>.001;samples.append(data)
        engine.stop();engine.render(512);assert not engine.render(512).any();engine.close()
    assert all(not np.allclose(a,b) for a,b in zip(samples,samples[1:]))
    probe.audio['melody']=dict(device=DEFAULT_DEVICE,program=1)
    probe.save(folder/'builtin.lfs');assert Project.load(folder/'builtin.lfs').audio==probe.audio
    dialog=SoundSettingsDialog(probe.audio);device,program=dialog.fields['melody']
    assert device.currentData()==DEFAULT_DEVICE and program.currentData()==1
    assert [program.itemData(i) for i in range(program.count())]==list(PROGRAMS)
    dialog.reject();dialog.deleteLater()
    credits=(folder/'offline.mp3.licenses.txt').read_text('utf-8')
    assert 'STK' in credits and 'Perry R. Cook' in credits and 'Source:' in credits
    assert len(pack(DEFAULT_DEVICE)['presets'])==16
    # 0.44: shipped packs, GM labels and tonicized recipes in the actual runtime.
    from lingfeng.audio.soundbanks import installed_packs, rescan
    from lingfeng.audio.gm_instruments import NAMES
    from lingfeng.ui.progression_dialogs import CaptureProgressionDialog
    from lingfeng.music.progressions import search_recipe
    rescan();shipped=[pack('synth:'+ident) for ident in ('stk-essentials','stk-colors','stk-acoustic')]
    assert sum(len(p['presets']) for p in shipped)==38 and len(NAMES)==128
    for info in shipped:
        for item in info['presets']:
            engine=SynthEngine('synth:'+info['id']);engine.send(0xc0,item['program']);engine.send(0x90,60,85)
            data=engine.render(8192);assert np.isfinite(data).all() and abs(data).max()>1e-5 and abs(data).max()<.951
            engine.send(0x80,60);engine.render(8192);assert not engine.render(512).any();engine.close()
    engine=SynthEngine(channel_devices={1:'synth:stk-essentials'},offline=True)
    try:
        engine.send(0xc1,49)
        for pitch in (48,55,64):engine.send(0x91,pitch,88)
        strings=engine.render(16384)
        assert np.isfinite(strings).all() and .001<abs(strings[-4096:]).max()<.95
    finally:engine.close()
    probe=Project();probe.chords=[Chord(i*3840,3840,r,q) for i,(r,q) in enumerate([(55,'m'),(48,''),(53,'')])]
    ids={c.id for c in probe.chords};dialog=CaptureProgressionDialog(probe,ids)
    assert dialog.value()['sequence']=='v I IV';dialog.tonic.setCurrentIndex(5)
    assert dialog.value()['sequence']=='ii V I' and set(dialog.value())=={'name','sequence'}
    dialog.reject();dialog.deleteLater()
    dialog=ProgressionDialog(probe,probe.chords[0].id,[make_preset('ii V I')]);dialog.tonic.setCurrentIndex(5)
    assert dialog.resolved.text()=='Gm – C – F';apply_progression(probe,probe.chords[0].id,**dialog.value())
    assert [c.root%12 for c in probe.chords]==[7,0,5] and search_recipe('Gm C F',5)=='II V I'
    dialog.reject();dialog.deleteLater()
    # 0.44.1 display and editing defaults, exercised in the frozen GUI too.
    for mode,preference,wanted in [('Aeolian','sharp','1 #1 2 b3 3 4 #4 5 b6 6 b7 7'),
                                   ('Lydian','flat','1 b2 2 b3 3 4 #4 5 b6 6 b7 7')]:
        set_accidental_preference(preference)
        probe=Project();probe.contexts=[Context(0,probe.end,48,mode)];probe.chords=[Chord(0,3840,55,'m',10)]
        legacy=dict(root=8,bass=11,quality='m7',pattern='quarters',gate=70,velocity=82,octave=2,regenerate=False)
        edit=ChordDialog(probe.chords[0],probe,defaults=legacy)
        capture=CaptureProgressionDialog(probe,{probe.chords[0].id})
        apply_dialog=ProgressionDialog(probe,probe.chords[0].id,[make_preset('ii V I')])
        manager=ProgressionManagerDialog([make_preset('ii V I')],tonic=48,mode=mode)
        for combo in (edit.root,edit.bass,capture.tonic,apply_dialog.tonic,manager.tonic):
            assert [combo.itemText(i).split(' · ')[0] for i in range(12)]==wanted.split()
        assert edit.root.currentData()==7 and edit.bass.currentData()==10 and edit.bass.findData(None)==-1
        assert edit.options()==dict(root=7,quality='m',bass=10,pattern='block',gate=90,velocity=72,octave=0)
        assert edit.regenerate.isChecked() and edit.octave.value()==0
        edit.root.setCurrentIndex(edit.root.findData(5));assert edit.bass.currentData()==5
        edit.bass.setCurrentIndex(edit.bass.findData(9));assert edit.root.currentData()==5 and edit.value().bass==9
        edit.root.setCurrentIndex(edit.root.findData(7));assert edit.bass.currentData()==7 and edit.value().bass is None
        for d in (edit,capture,apply_dialog,manager):d.reject();d.deleteLater()
    set_accidental_preference('sharp')
    # 0.45: score-wide fitting, symbol columns and proportional forced rows.
    from lingfeng.engraving.presentation import apply_forced_row
    probe=Project();probe.notes=[Note(0,240,60),Note(240,720,61),Note(960,1920,64),Note(2880,960,65)]
    probe.notation.update(style='traditional',per_line=1)
    fitted=ScoreLayout(probe);system=fitted.systems[0]
    slots=fitted.engraving_slots(0,system.fragments[0]);assert slots==[0,240,960,1920,2880,3840]
    points,positions,*_=fitted.bar_map(system,0,0,system.bar_widths[0])
    cell=fitted.traditional_cell_width(0);gap=system.beat_gap
    side=system.bar_side_gap
    expected=(side,side+cell,side+2*cell+gap,side+3*cell+2*gap,side+4*cell+3*gap)
    assert all(abs(fitted.traditional_cell(0,t,points,positions)[0]-wanted)<1e-7 for t,wanted in zip(slots[:-1],expected))
    assert abs(fitted.traditional_cell(0,slots[-2],points,positions)[1]+side-system.bar_widths[0])<1e-7
    probe.notation.update(per_line=4,font_size=4);apply_forced_row(probe,list(range(6)))
    for style in ('traditional','spatial','compact'):
        probe.notation['style']=style;fitted=ScoreLayout(probe)
        factor=min(1,fitted.reference_unit_count/fitted.systems[0].unit_count) if style=='traditional' else 2/3
        assert all(abs(v-fitted.glyph_scale*factor)<1e-7 for v in fitted.systems[0].bar_scales.values())
        assert all(v==fitted.glyph_scale for s in fitted.systems[1:] for v in s.bar_scales.values())
    assert Project.from_dict(probe.to_dict()).notation['forced_row_fonts']==[[0,6,4]]
    # 0.46: music is engraved at entry; view navigation never rebuilds it.
    from PySide6.QtCore import QRectF
    window.switch_workspace('compose');window.replace_project(Project())
    assert window.score_view.canvas.layout is None
    window.project.notes=[Note(b*3840,960,60+b%3) for b in range(8)]
    window.refresh();assert window.score_view.canvas.layout is None
    window.switch_workspace('score');canvas=window.score_view.canvas;original=canvas.layout
    window.project.notes[0].pitch=70;window.refresh()
    assert canvas.layout is original and canvas.project.notes[0].pitch==60
    window.note_font.setValue(5);assert canvas.project.notes[0].pitch==60
    window.switch_workspace('compose');window.switch_workspace('score')
    assert canvas.project.notes[0].pitch==70
    for key in window.score_pages:window.set_score_panel_visible(key,False)
    app.processEvents()
    view=window.score_view;view.set_zoom(2);assert view.zoom_mode=='manual'
    view.locate_bar(7);app.processEvents();rect=view.bar_rect(7)
    assert rect.intersects(QRectF(view.horizontalScrollBar().value(),view.verticalScrollBar().value(),view.viewport().width(),view.viewport().height()))
    view.viewport().repaint()
    assert all(crop.width()<=view.viewport().width()+97 and crop.height()<=view.viewport().height()+97 for pixmap,crop in canvas.page_cache.values())
    view.fit_zoom('width');app.processEvents()
    assert abs(canvas.scale-(view.viewport().width()-48)/900)<.002
    window.grab().save(str(folder/'score-navigation.png'))
    window.project.notes[0].pitch=72;window.refresh()
    pdf=ExportDialog(window,'pdf');midi=ExportDialog(window,'midi')
    assert pdf.project.notes[0].pitch==70 and midi.project.notes[0].pitch==72
    pdf.reject();midi.reject();pdf.deleteLater();midi.deleteLater()
    # 0.47: compact rows and the isolated 32nd-pair display rule never edit MIDI.
    from lingfeng.engraving.notation import fragment_style
    probe=Project();probe.chords=[];probe.notes=[Note(0,720,60),Note(720,120,62),Note(840,120,64),Note(960,2880,65)]
    before=probe.to_dict();export_midi(probe,folder/'short-pair-before.mid')
    for style in ('spatial','compact','traditional'):
        probe.notation.update(style=style,circles=False,lyrics=False,per_line=1,font_size=15)
        fitted=ScoreLayout(probe);system=fitted.systems[0];parts=system.fragments[0]
        assert [fragment_style(f)[:2] for f in parts[:3]]==[(1,False),(3,False),(3,False)]
        expected=Project.from_dict(probe.to_dict());expected.notes[0].duration=480;expected.notes[1].start=480;expected.notes[1].duration=240;expected.notes[2].start=720;expected.notes[2].duration=240
        assert fitted.width_cache==ScoreLayout(expected).width_cache
        export_pdf(probe,folder/f'short-pair-{style}.pdf')
        export_midi(probe,folder/'short-pair-after.mid')
        assert (folder/'short-pair-before.mid').read_bytes()==(folder/'short-pair-after.mid').read_bytes()
    assert [(n['start'],n['duration']) for n in probe.to_dict()['notes']]==[(n['start'],n['duration']) for n in before['notes']]
    assert system.left==52 and abs(sum(system.bar_widths)-796)<1e-7 and system.height<100
    line_top,line_bottom=fitted.barline_bounds(system)
    baseline=system.top+system.note_baseline
    assert abs(line_top-(baseline-18*system.symbol_scale))<1e-7
    assert line_bottom>=baseline+(system.underline_offset+8+.5)*system.symbol_scale-1e-7
    assert line_bottom<system.top+system.grid_bottom
    window.switch_workspace('compose');cached=canvas.layout;cursor=canvas.play_tick
    window.show_cursor(120);window.refresh();assert canvas.suspended and canvas.layout is cached and canvas.play_tick==cursor
    # 0.53.1: the displayed font is the requested font, beyond advisory limits.
    probe.notation.update(font_size=26,font_layout_version=45,per_line=4)
    window.replace_project(probe);window.switch_workspace('score');canvas=window.score_view.canvas
    cap=canvas.layout.font_limit
    assert window.note_font.maximum()==FONT_SIZE_MAX and f'{cap:g}' in window.font_limit_label.text()
    window.note_font.setValue(30)
    assert window.note_font.value()==window.project.notation['font_size']==canvas.project.notation['font_size']==30
    assert abs(canvas.layout.glyph_scale*15-30)<1e-7
    window.note_font.setValue(min(30,cap))
    canvas=window.score_view.canvas
    assert all(s.left==52 and abs(s.left+sum(s.bar_widths)-848)<1e-7 for s in canvas.layout.systems)
    assert all(len(s.bars)<=4 for s in canvas.layout.systems)
    window.grab().save(str(folder/'score-font-limit.png'))
    export_pdf(canvas.project,folder/'justified-traditional.pdf')
    # 0.49: partial entry, invisible skip tokens and rap over existing MIDI.
    from lingfeng.audio.midi import event_list as midi_events
    probe=Project();probe.notes=[Note(i*480,480,60+i,80) for i in range(8)]
    probe.notation.update(style='traditional',font_size=12,font_layout_version=45)
    original_midi=midi_events(probe);window.replace_project(probe);window.show_score_panel('lyrics')
    panel=window.lyric_panel;panel.start.setValue(1);panel.count.setValue(1);panel.text.setPlainText(r'\x{我是一个rapper}*唱')
    assert panel.check();panel.commit();assert len(lyric_events(window.project))==7
    assert midi_events(window.project)==original_midi
    for style in ('traditional','spatial','compact'):
        rendered=copy.deepcopy(window.project);rendered.notation['style']=style;layout=ScoreLayout(rendered)
        image=QImage(900,1273,QImage.Format.Format_RGB32);image.fill(0xffffffff)
        painter=QPainter(image);layout.draw(painter,0);painter.end();image.save(str(folder/f'rap-{style}.png'))
        assert len([x for x in layout.unpitched_positions if x[1]=='x'])==5
        assert len(layout.lyric_positions)==6
    export_pdf(window.score_view.canvas.project,folder/'rap-lyrics.pdf')
    window.undo();assert not any(f.ghost for s in window.score_view.canvas.layout.systems for fs in s.fragments.values() for f in fs)
    window.redo();assert midi_events(window.project)==original_midi
    # 0.49.1: every distinct MIDI start, including a start under a sustained note.
    from lingfeng.engraving.lyrics import apply_range, melody_onsets
    probe=Project();probe.notes=[Note(0,5760,60),Note(0,480,64),Note(480,240,67),Note(960,240,69),Note(3840,480,62),Note(4320,480,65)]
    original_midi=midi_events(probe)
    assert melody_onsets(probe,0,3840)==[0,480,960]
    apply_range(probe,'长/s/x{音} | 新词',0,2)
    assert midi_events(probe)==original_midi
    # The onset backend still supports simultaneous sources; the active Score
    # editor now requires a single voice while retaining the same lyric ticks.
    probe.notes=[n for n in probe.notes if n.pitch!=60];original_midi=midi_events(probe)
    window.replace_project(probe);window.show_score_panel('lyrics');panel=window.lyric_panel
    window.score_view.canvas.selected_bars={0,1};panel.use_selection()
    assert panel.text.toPlainText()=='长*\\x{音}\n新词' and panel.check()
    assert [panel.rhythm.topLevelItem(i).text(3) for i in range(2)]==['3/3','2/2']
    panel.count.setValue(1);assert panel.text.toPlainText()==r'长*\x{音}'
    outside=[e for e in lyric_events(window.project) if e['tick']>=3840]
    panel.text.setPlainText('改/s/x{音}');panel.commit()
    assert [e for e in lyric_events(window.project) if e['tick']>=3840]==outside
    assert midi_events(window.project)==original_midi
    window.undo();assert panel.text.toPlainText()==r'长*\x{音}'
    window.redo();assert panel.text.toPlainText()==r'改*\x{音}'
    window.score_view.canvas.selected_bars={0,1};panel.use_selection();app.processEvents()
    window.grab().save(str(folder/'lyric-range-autofill.png'))
    # 0.49.2: valid example labels, mixed text and tightly fitted symbols.
    from lingfeng.music.model import SECTIONS, Measure
    from lingfeng.engraving.lyrics import range_source, tokenize
    assert [(i,m.section) for i,m in enumerate(demo_project().measures) if m.section]==[(0,'verse'),(8,'chorus')]
    assert all(not m.section or m.section in SECTIONS for m in demo_project().measures)
    mixed="我love你，I'm ready一起sing"
    assert len(tokenize(mixed))==8
    assert [t.text for t in tokenize('“don’t stop”唱‘中文’')]==['“don’t','stop”','唱','‘中','文’']
    probe=Project();probe.measures=[Measure() for _ in range(4)];probe.contexts=[Context(0,probe.end)]
    probe.notes=[Note(i*480,480,60) for i in range(32)]
    probe.notation.update(style='traditional',font_size=26,font_layout_version=45)
    original_midi=midi_events(probe);apply_range(probe,mixed,0,1)
    loaded,valid=range_source(probe,0,1);assert valid and "I'm" in loaded
    for style in ('traditional','spatial','compact'):
        rendered=copy.deepcopy(probe);rendered.notation['style']=style
        rendered.notation['font_size']=ScoreLayout(rendered).font_limit;layout=ScoreLayout(rendered)
        # 0.52 allocates equal widths to these equally dense bars, so the
        # lyric-heavy bar no longer receives the old glyph-weighted extra width.
        # Verify the envelope and the actual fitted result, not the old cap.
        system=layout.systems[0]
        assert layout.glyph_extents(system.fragments[0][0])==(7,7)
        if style!='traditional':assert all(abs(width-system.bar_widths[0])<1e-7 for width in system.bar_widths)
        assert layout.font_size==layout.font_limit
        image=QImage(900,1273,QImage.Format.Format_RGB32);image.fill(0xffffffff)
        painter=QPainter(image);layout.draw(painter,0);painter.end();image.save(str(folder/f'mixed-spacing-{style}.png'))
        if style!='traditional':assert all(system.left-1e-6<=left<=right<=848+1e-6 for _,_,left,right,a,b in layout.symbol_boxes)
    window.replace_project(probe);window.change_language('zh',False);window.resize(1280,1000);window.show_score_panel('lyrics')
    panel=window.lyric_panel;window.score_view.canvas.selected_bars={0};panel.use_selection()
    assert panel.text.toPlainText()==loaded and panel.check();panel.commit()
    assert midi_events(window.project)==original_midi
    app.processEvents();window.score_splitter.setSizes([400,400]);app.processEvents()
    window.grab().save(str(folder/'mixed-lyrics-editor.png'))
    export_pdf(window.score_view.canvas.project,folder/'mixed-lyrics.pdf')
    # 0.49.3: direct first opening, compact multiline rap and explicit skips.
    example_root=application_root()
    probe=Project.load(example_root/'examples/lingfeng-rap.lfs');original_midi=midi_events(probe)
    window.replace_project(probe);window.show_score_panel('lyrics');panel=window.lyric_panel
    assert panel.text.toPlainText().startswith('先唱旋律，**跟上') and panel.check()
    panel.count.setValue(4)
    expected='先唱旋律，**跟上\n\\x{我们跟着节奏走吧\nLet us rap in English now**}\n回到旋律，唱完这句。'
    assert panel.text.toPlainText()==expected and panel.check()
    panel.commit();assert panel.text.toPlainText()==expected and midi_events(window.project)==original_midi
    assert len(tokenize('我，爱。你,hello world!/s/s'))==7
    window.toggle_score_panel_floating('lyrics');assert panel.text.toPlainText()==expected
    window.toggle_score_panel_floating('lyrics');app.processEvents();window.score_splitter.setSizes([400,400]);app.processEvents()
    window.grab().save(str(folder/'rap-example-editor.png'))
    export_pdf(window.score_view.canvas.project,folder/'rap-example.pdf')
    # 0.49.4: row entries use a descending half-curve; lyric /- adds slurs.
    probe=demo_project();original_midi=export_midi(probe,None)
    for style in ('traditional','spatial','compact'):
        probe.notation.update(style=style,per_line=4,font_size=12);layout=ScoreLayout(probe)
        image=QImage(900,1273,QImage.Format.Format_RGB32);image.fill(0xffffffff)
        painter=QPainter(image);layout.draw(painter,0);painter.end()
        incoming=[path for _,kind,path in layout.tie_paths if kind=='incoming'];assert incoming
        for path in incoming:
            a,b=path.pointAtPercent(0),path.pointAtPercent(1)
            assert path.elementCount()==4 and b.x()>a.x() and b.y()>a.y()
            points=[path.pointAtPercent(i/20) for i in range(21)]
            assert all(q.x()>p.x() and q.y()>=p.y() for p,q in zip(points,points[1:]))
            middle=path.pointAtPercent(.5)
            assert middle.y()<a.y()+(b.y()-a.y())*(middle.x()-a.x())/(b.x()-a.x())
        assert all(path.elementCount()==4 for _,kind,path in layout.tie_paths if kind!='incoming')
        system=next(s for s in layout.systems if s.bars[0]==8)
        image=QImage(900,round((system.height+30)*2),QImage.Format.Format_RGB32);image.fill(0xff18212b)
        painter=QPainter(image);painter.scale(2,2);painter.translate(40-system.left,15-system.top)
        layout.dark=True;layout.draw_system(painter,system);painter.end();image.save(str(folder/f'incoming-{style}.png'))
        export_pdf(probe,folder/f'tie-entry-{style}.pdf')
    assert export_midi(probe,None)==original_midi
    probe=Project.load(example_root/'examples'/'lingfeng-melisma.lfs')
    window.replace_project(probe);window.batch_lyrics();panel=window.lyric_panel
    panel.start.setValue(1);panel.count.setValue(1);panel.text.setPlainText('我/s/s');panel.commit()
    plain_midi=export_midi(window.project,None)
    panel.text.setPlainText('我/-/-');assert panel.check();panel.commit()
    for style in ('traditional','spatial','compact'):
        window.project.notation['style']=style;layout=ScoreLayout(window.project)
        image=QImage(900,1273,QImage.Format.Format_RGB32);image.fill(0xffffffff)
        painter=QPainter(image);layout.draw(painter,0);painter.end()
        assert [(a,b,k) for a,b,k,_ in layout.melisma_paths if b<3840]==[(0,480,'continuous'),(480,960,'continuous')]
        assert export_midi(window.project,None)==plain_midi
    window.undo();assert panel.text.toPlainText()=='我**'
    window.redo();assert panel.text.toPlainText()=='我__'
    window.replace_project(probe);window.batch_lyrics();panel.count.setValue(4);assert panel.check()
    app.processEvents();window.grab().save(str(folder/'melisma-example-editor.png'))
    for style in ('traditional','spatial','compact'):
        probe.notation['style']=style;layout=ScoreLayout(probe)
        image=QImage(900,1273,QImage.Format.Format_RGB32);image.fill(0xffffffff)
        painter=QPainter(image);layout.draw(painter,0);painter.end();image.save(str(folder/f'melisma-{style}.png'))
        assert len(layout.melisma_paths)==6
        export_pdf(probe,folder/f'melisma-{style}.pdf')
    # 0.50: exercise the production process route in the frozen executable too.
    from lingfeng.audio.playback import ProcessRouter
    probe=Project();probe.notes=[Note(0,3840,60)];window.replace_project(probe)
    for mute in window.mute_buttons.values():mute.setChecked(True)
    window.playhead=0;window.toggle_play()
    backend=window.transport.synth;worker=window.transport.thread;epoch=window.transport.start_time
    assert isinstance(backend,ProcessRouter) and backend.process.is_alive()
    window.mutate('0.50 live revision',lambda p:setattr(p.notes[0],'velocity',72))
    window.undo();window.redo()
    assert window.transport.synth is backend and window.transport.thread is worker
    assert window.transport.start_time==epoch and window.transport.playing
    window.stop()
    from lingfeng.platform.preferences import atomic_json, load_preferences, save_preferences, read_object
    from lingfeng.music.progression_catalog import CATALOG_VERSION
    from lingfeng.music.progressions import load_library
    prefdir=folder/'upgrade-probe';prefpath=prefdir/'preferences.json'
    original=dict(language='en',theme='dark',progression_presets=[],progression_catalog_version=CATALOG_VERSION,future_setting={'keep':True})
    atomic_json(prefpath,original)
    saved=save_preferences(prefdir,{},load_preferences(prefdir))
    assert saved['app_version']==__version__ and saved['future_setting']=={'keep':True}
    assert read_object(prefdir/f'preferences.pre-{__version__}.json')==original
    assert load_library(saved['progression_presets'],saved['progression_catalog_version'])==[]
    for language in ('zh','en'):
        window.change_language(language,False)
        help=HelpDialog(window);help.show();app.processEvents()
        from lingfeng.platform.help_content import HELP_CATEGORIES
        assert help.category.count()==len(HELP_CATEGORIES)+1
        help.search.setText('personal settings');app.processEvents()
        assert help.list.currentRow()>=0
        help.grab().save(str(folder/f'help-upgrade-{language}.png'))
        help.search.setText('zz-no-match-0.50');assert help.list.currentRow()==-1
        help.close()
    # 0.50.1: metadata is live even while score music remains a snapshot.
    window.switch_workspace('compose');window.melody_window.setFloating(False);window.harmony_window.setFloating(False)
    window.score_tools.setFloating(False);window.replace_project(Project())
    window.project.notes=[Note(0,480,60)];window.switch_workspace('score');app.processEvents()
    original_title=window.project.title
    window.mutate('0.50.1 title',lambda p:(setattr(p,'title','0.50.1 Live title'),setattr(p,'author','Lingfeng')))
    assert window.score_view.canvas.project.title=='0.50.1 Live title'
    assert window.score_view.canvas.layout.project.author=='Lingfeng'
    window.undo();assert window.score_view.canvas.project.title==original_title
    window.redo();assert window.score_view.canvas.project.title=='0.50.1 Live title'
    window.grab().save(str(folder/'v501-live-title.png'))
    export_pdf(window.score_view.canvas.project,folder/'v501-live-title.pdf')
    edit_action=next(a for a in window.title_bar.menu.actions() if a.text()==tr('编辑'));edit_menu=edit_action.menu()
    assert not any(a.text()==tr('小节段落名…') for a in edit_menu.actions())
    window.switch_workspace('compose');window.open_harmony();app.processEvents()
    window.playhead=3*PPQ;window.show_cursor(window.playhead);window.follow_playhead.setChecked(True)
    window.roll.horizontalScrollBar().setValue(20);window.roll.navigationRequested.emit()
    assert window.follow_playhead.isChecked()
    before=window.roll.horizontalScrollBar().value();window.follow_views(window.playhead)
    assert window.roll.horizontalScrollBar().value()==before
    window.roll.horizontalScrollBar().setValue(window.roll.horizontalScrollBar().maximum());window.roll.navigationRequested.emit()
    assert not window.follow_playhead.isChecked()
    window.switch_workspace('score');window.show_score_panel('harmony');app.processEvents()
    window.playhead=window.project.end-960;window.follow_playhead.setChecked(True);window.follow_views(window.playhead)
    assert window.docked_roll() is window.harmony_window.roll and window.harmony_window.roll.tick_visible(window.playhead)
    assert window.score_view.bar_visible(window.playhead)
    assert window.melody_transport.follow.isChecked()==window.harmony_window.transport_controls.follow.isChecked()
    window.grab().save(str(folder/'v501-follow-harmony-tab.png'))
    window.toggle_score_panel_floating('harmony');app.processEvents()
    assert window.roll_pane(window.harmony_window.roll) is window.score_floats['harmony']
    assert not window.is_main_view(window.harmony_window.roll)
    window.harmony_window.sync.setChecked(False);window.follow_playhead.setChecked(False)
    window.harmony_window.transport_controls.follow.setChecked(True)
    window.harmony_window.roll.horizontalScrollBar().setValue(0);window.follow_views(window.playhead)
    assert not window.follow_playhead.isChecked() and window.harmony_window.roll.tick_visible(window.playhead)
    window.score_floats['harmony'].grab().save(str(folder/'v501-score-floating-follow.png'))
    window.show_score_panel('melody');window.toggle_score_panel_floating('melody');app.processEvents()
    assert window.melody_options.isVisible() and window.melody_sync in window.melody_options.menu().actions()
    # 0.50.2: each manually browsed surface owns its cancellation decision.
    from lingfeng.music.model import Measure
    for key in ('melody','harmony'):
        if window.score_panel_state[key]['floating']:window.toggle_score_panel_floating(key)
    window.switch_workspace('compose')
    probe=Project(measures=[Measure() for _ in range(40)],contexts=[Context(0,40*3840)])
    probe.notes=[Note(i*3840,480,72+i%5) for i in range(40)]
    window.replace_project(probe);window.switch_workspace('score');window.show_score_panel('harmony');app.processEvents()
    tick=3*PPQ;window.playhead=tick;window.show_cursor(tick);window.score_view.locate_tick(tick)
    roll=window.harmony_window.roll;roll.horizontalScrollBar().setValue(0)
    window.follow_playhead.setChecked(True);bar=window.score_view.verticalScrollBar()
    bar.setSliderDown(True)
    before=bar.value();window.follow_views(tick);assert bar.value()==before
    bar.setSliderPosition(bar.maximum());bar.setSliderDown(False)
    assert not window.follow_playhead.isChecked() and roll.tick_visible(tick)
    before=bar.value();window.follow_views(tick);assert bar.value()==before
    window.grab().save(str(folder/'v502-score-drag-cancels.png'))
    window.score_view.locate_tick(tick);assert window.score_view.bar_visible(tick)
    window.follow_playhead.setChecked(True)
    roll.horizontalScrollBar().setValue(round(tick/PPQ*roll.zoom)+40);roll.navigationRequested.emit()
    assert not window.follow_playhead.isChecked() and not roll.tick_visible(tick)
    before=roll.horizontalScrollBar().value();window.follow_views(tick)
    assert roll.horizontalScrollBar().value()==before
    window.grab().save(str(folder/'v502-roll-drag-cancels.png'))
    # Equal-length bars preserve the 0.52 example. The busiest beat determines
    # per-beat width; total bar allocation also includes its actual beat count.
    density=Project(measures=[Measure(),Measure()],contexts=[Context(0,8*PPQ)])
    density.title='0.52 density 4 : 2';density.chords=[];density.notes=[]
    density.notation.update(per_line=2,font_size=15,circles=False,lyrics=False)
    for bar,counts in enumerate(((1,2,3,4),(2,2,2,2))):
        for beat,count in enumerate(counts):
            density.notes.extend(Note(bar*4*PPQ+beat*PPQ+i*PPQ//count,PPQ//count,60+i%5) for i in range(count))
    export_midi(density,folder/'v52-density-before.mid');density_midi=midi_events(density)
    for style in ('spatial','compact'):
        density.notation['style']=style;state=copy.deepcopy(density.to_dict());fitted=ScoreLayout(density)
        system=fitted.systems[0];assert abs(system.bar_widths[0]/system.bar_widths[1]-2)<1e-9
        assert abs(sum(system.bar_widths)-(900-52-system.left))<1e-7
        assert fitted.font_size==density.notation['font_size']
        image=QImage(900,1273,QImage.Format.Format_RGB32);image.fill(0xffffffff)
        painter=QPainter(image);fitted.draw(painter,0);painter.end();image.save(str(folder/f'v52-density-{style}.png'))
        assert density.to_dict()==state and midi_events(density)==density_midi
    export_midi(density,folder/'v52-density-after.mid')
    assert (folder/'v52-density-before.mid').read_bytes()==(folder/'v52-density-after.mid').read_bytes()
    # 0.53: equal density in 2/4 and 4/4 means equal beat width and 1:2 bars.
    mixed=Project(measures=[Measure(2,4),Measure(4,4)])
    mixed.contexts=[Context(0,mixed.end)];mixed.chords=[]
    mixed.notes=[Note(t,PPQ//2,60+(t//(PPQ//2))%2*2) for t in range(0,mixed.end,PPQ//2)]
    mixed.notation.update(per_line=2,font_size=15,circles=False,lyrics=False)
    mixed_midi=midi_events(mixed);export_midi(mixed,folder/'v53-mixed-before.mid')
    for style in ('spatial','compact'):
        mixed.notation['style']=style;state=copy.deepcopy(mixed.to_dict());fitted=ScoreLayout(mixed);system=fitted.systems[0]
        assert abs(system.bar_widths[0]/system.bar_widths[1]-.5)<1e-9
        assert abs(system.bar_widths[0]/2-system.bar_widths[1]/4)<1e-7
        spans=[]
        for bar,width in zip(system.bars,system.bar_widths):
            points,positions,*_=fitted.bar_map(system,bar,0,width)
            edges=[fitted.interpolate(points,positions,t) for t in range(mixed.starts[bar],mixed.starts[bar+1]+1,PPQ)]
            spans.extend(b-a for a,b in zip(edges,edges[1:]))
        assert all(abs(span-spans[0])<1e-7 for span in spans)
        image=QImage(900,1273,QImage.Format.Format_RGB32);image.fill(0xffffffff)
        painter=QPainter(image);fitted.draw(painter,0);painter.end();image.save(str(folder/f'v53-mixed-{style}.png'))
        assert mixed.to_dict()==state and midi_events(mixed)==mixed_midi
    export_midi(mixed,folder/'v53-mixed-after.mid')
    assert (folder/'v53-mixed-before.mid').read_bytes()==(folder/'v53-mixed-after.mid').read_bytes()
    # 0.53.1: each traditional beat owns its columns, with one small row gap.
    traditional=Project(measures=[Measure(),Measure(),Measure()])
    traditional.contexts=[Context(0,traditional.end)];traditional.chords=[];traditional.notes=[]
    patterns=((1,2,3,4),(2,2,2,2),(1,1,1,1))
    traditional.notation.update(style='traditional',per_line=2,font_size=15,lyrics=False)
    for bar,counts in enumerate(patterns):
        for beat,count in enumerate(counts):
            traditional.notes.extend(Note(bar*4*PPQ+beat*PPQ+i*PPQ//count,PPQ//count,60+i%4) for i in range(count))
    original_music=midi_events(traditional);fitted=ScoreLayout(traditional);system=fitted.systems[0]
    groups=[];x=system.left
    for bar,width in zip(system.bars,system.bar_widths):
        points,positions,*_=fitted.bar_map(system,bar,x,width)
        for beat,count in enumerate(patterns[bar]):
            cells=[fitted.traditional_cell(bar,bar*4*PPQ+beat*PPQ+i*PPQ//count,points,positions) for i in range(count)]
            assert all(abs((b-a)-system.cell_width)<1e-7 for a,b in cells)
            assert all(abs(b[0]-a[1])<1e-7 for a,b in zip(cells,cells[1:]))
            groups.append((cells[0][0],cells[-1][1]))
        assert abs(groups[-1][1]+system.bar_side_gap-(x+width))<1e-7
        x+=width
    assert all(abs(b[0]-a[1]-system.beat_gap)<1e-7 for a,b in zip(groups,groups[1:]))
    assert abs(groups[-1][1]+system.bar_side_gap-848)<1e-7
    export_pdf(traditional,folder/'v531-traditional-beats.pdf')
    numeric_copy=copy.deepcopy(traditional)
    numeric_copy.notation['font_size']=ScoreLayout(numeric_copy).recommended_font_size
    numeric_fit=ScoreLayout(numeric_copy);heaviest=max(numeric_fit.systems,key=lambda s:s.unit_count)
    assert isinstance(numeric_copy.notation['font_size'],int)
    assert heaviest.bar_side_gap>=heaviest.cell_width-1e-7
    assert numeric_fit.recommended_font_size<=numeric_fit.max_font_size<numeric_fit.recommended_font_size+1
    assert abs(numeric_fit.cell_width-20.95*numeric_fit.font_size/15)<1e-7
    assert len({round(s.cell_width,8) for s in numeric_fit.systems})==1
    assert all(abs(sum(s.bar_widths)-796)<1e-6 and abs(s.beat_gap-2*s.bar_side_gap)<1e-7 for s in numeric_fit.systems)
    reference=max(s.unit_count for s in fitted.systems)
    apply_forced_row(traditional,[0,1,2]);merged_layout=ScoreLayout(traditional);merged=merged_layout.systems[0]
    ratio=min(1,reference/merged.unit_count)
    assert merged_layout.reference_source=='baseline' and merged_layout.reference_unit_count==reference
    assert abs(merged.symbol_scale-ratio)<1e-7 and abs(merged.forced_font_ratio-ratio)<1e-7
    assert abs(merged.cell_width-system.cell_width*ratio)<1e-7 and merged.layout_scale==1
    assert abs(merged.beat_gap-2*merged.bar_side_gap)<1e-7
    assert midi_events(traditional)==original_music
    # 0.54.1: all traditional rhythm lines follow the row's lowest octave dots.
    aligned=Project(measures=[Measure()]);aligned.contexts=[Context(0,aligned.end)]
    aligned.notes=[Note(0,120,48),Note(240,240,36),Note(720,240,24),Note(960,240,60)];aligned.chords=[]
    aligned.notation.update(style='traditional',per_line=1,font_size=15,circles=False,lyrics=False)
    aligned_before=copy.deepcopy(aligned.to_dict());aligned_events=midi_events(aligned)
    level=ScoreLayout(aligned);row=level.systems[0];rhythm_ys=[]
    class RhythmPainter(QPainter):
        def drawLine(self,*args):
            if len(args)==2 and all(isinstance(point,QPointF) for point in args):
                a,b=args
                if abs(a.y()-b.y())<1e-7 and abs(abs(b.x()-a.x())-11)<1e-7:
                    rhythm_ys.append(self.worldTransform().map(a).y())
            return super().drawLine(*args)
    image=QImage(900,1273,QImage.Format.Format_RGB32);image.fill(0xffffffff);painter=RhythmPainter(image)
    try:level.draw(painter,0)
    finally:painter.end()
    image.save(str(folder/'v541-aligned-rhythm.png'))
    expected={round(row.top+row.note_baseline+(19+4*k)*row.symbol_scale,6) for k in range(3)}
    assert row.lower_octave_dots==2 and row.underline_offset==19
    assert len(rhythm_ys)==15 and {round(y,6) for y in rhythm_ys}==expected
    assert row.top+row.grid_bottom>max(rhythm_ys)+.5*row.symbol_scale
    assert aligned.to_dict()==aligned_before and midi_events(aligned)==aligned_events
    # 0.54.3: apply the symbol-budget font, never shrink the whole row.
    oversized=Project(measures=[Measure() for _ in range(4)])
    oversized.contexts=[Context(0,oversized.end)];oversized.chords=[]
    oversized.notes=[Note(t,120,48+(t//120)%8) for t in range(0,oversized.end,120)]
    oversized.notation.update(style='traditional',per_line=4,font_size=26,circles=True,lyrics=False)
    oversized_before=copy.deepcopy(oversized.to_dict());oversized_midi=export_midi(oversized,None)
    manual=ScoreLayout(oversized)
    assert manual.font_size==26 and manual.systems[0].layout_scale==1
    oversized.notation['font_size']=manual.recommended_font_size
    paper=ScoreLayout(oversized)
    assert paper.font_size==manual.recommended_font_size and paper.systems[0].bars==list(range(4))
    assert paper.systems[0].layout_scale==1
    image=QImage(900,1273,QImage.Format.Format_RGB32);image.fill(0xffffffff)
    painter=QPainter(image)
    try:paper.draw(painter,0)
    finally:painter.end()
    image.save(str(folder/'v543-budget-font.png'))
    for system in paper.systems:
        rect=paper.system_page_rect(system)
        assert rect.left()>=52-1e-6 and rect.right()<=848+1e-6
        assert rect.bottom()<=1203+1e-6
    assert all(52-1e-6<=rect.left()<=rect.right()<=848+1e-6 for _,rect,_ in paper.hit_bars)
    export_pdf(oversized,folder/'v543-budget-font.pdf')
    oversized_before['notation']['font_size']=manual.recommended_font_size
    assert oversized.to_dict()==oversized_before and export_midi(oversized,None)==oversized_midi
    # A middle triplet attack crosses the beat but remains one source group.
    triplets=Project(measures=[Measure()]);triplets.contexts=[Context(0,triplets.end)];triplets.chords=[]
    triplets.notes=[Note(480+i*320,320,pitch) for i,pitch in enumerate((50,52,53))]
    triplets.notation.update(per_line=1,font_size=15,circles=True,lyrics=False)
    triplet_midi=export_midi(triplets,None)
    class TripletPainter(QPainter):
        def drawText(self,*args):
            if len(args)==2 and isinstance(args[0],QPointF) and args[1]=='3' and self.font().pixelSize()==11:
                triplet_labels.append(self.worldTransform().map(args[0]))
            return super().drawText(*args)
    for style in ('traditional','spatial','compact'):
        triplets.notation['style']=style;tuplet=ScoreLayout(triplets);triplet_labels=[]
        image=QImage(900,1273,QImage.Format.Format_RGB32);image.fill(0xffffffff);painter=TripletPainter(image)
        try:tuplet.draw(painter,0)
        finally:painter.end()
        image.save(str(folder/f'v542-source-triplet-{style}.png'))
        assert len([f for s in tuplet.systems for fs in s.fragments.values() for f in fs if f.note and f.note.id==triplets.notes[1].id])==2
        assert len(triplet_labels)==1
        assert export_midi(triplets,None)==triplet_midi
    # 0.53.2: short legato tails stay on one row; cross-beat spelling uses ties.
    beat_song=Project(measures=[Measure() for _ in range(4)])
    beat_song.contexts=[Context(0,beat_song.end)];beat_song.chords=[]
    overlap_a=Note(0,320,60);overlap_b=Note(240,720,57)
    crossing=Note(4*PPQ+720,480,62);sustain=Note(8*PPQ,3*PPQ,64)
    dotted_crossing=Note(12*PPQ+480,720,65)
    beat_song.notes=[overlap_a,overlap_b,crossing,sustain,dotted_crossing]
    beat_song.notation.update(style='traditional',per_line=4,font_size=15,circles=False,lyrics=False)
    original=copy.deepcopy(beat_song.to_dict());original_events=midi_events(beat_song)
    export_midi(beat_song,folder/'v532-before.mid')
    engraved=ScoreLayout(beat_song);assert set(engraved.systems[0].voices.values())=={0}
    split=[f for f in engraved.systems[0].fragments[1] if f.note]
    assert [(f.start,f.duration) for f in split]==[(4*PPQ+720,240),(5*PPQ,240)]
    assert all(f.note is crossing for f in split) and split[0].continues and split[1].continuation
    whole=[f for f in engraved.systems[0].fragments[2] if f.note]
    assert len(whole)==1 and whole[0].duration==3*PPQ and fragment_style(whole[0])==(0,False,False,2)
    assert all(not fragment_style(f)[1] or (f.start//PPQ)==((f.end-1)//PPQ)
               for parts in engraved.systems[0].fragments.values() for f in parts if f.note)
    tie_ids=set()
    for page in range(engraved.pages):
        image=QImage(900,1273,QImage.Format.Format_RGB32);image.fill(0xffffffff)
        painter=QPainter(image);engraved.draw(painter,page);painter.end()
        image.save(str(folder/f'v532-beat-ties-{page}.png'));tie_ids.update(nid for nid,_,_ in engraved.tie_paths)
    assert {crossing.id,dotted_crossing.id}<=tie_ids and sustain.id not in tie_ids
    try:export_pdf(beat_song,folder/'v532-traditional-polyphonic-rejected.pdf')
    except ValueError as exc:assert str(exc)=='传统简谱仅支持单声部旋律，请使用立体简谱或立体简谱 · 紧凑。'
    else:raise AssertionError('Traditional polyphonic PDF export must be rejected')
    assert not (folder/'v532-traditional-polyphonic-rejected.pdf').exists()
    printable=copy.deepcopy(beat_song);printable.notation['style']='spatial'
    export_pdf(printable,folder/'v532-beat-ties.pdf');export_midi(beat_song,folder/'v532-after.mid')
    assert (folder/'v532-before.mid').read_bytes()==(folder/'v532-after.mid').read_bytes()
    assert beat_song.to_dict()==original and midi_events(beat_song)==original_events
    for style in ('spatial','compact'):
        same_music=copy.deepcopy(beat_song);same_music.notation['style']=style;universal=ScoreLayout(same_music)
        split=[f for f in universal.systems[0].fragments[1] if f.note]
        assert [(f.start,f.duration) for f in split]==[(4*PPQ+720,240),(5*PPQ,240)]
        whole=[f for f in universal.systems[0].fragments[2] if f.note]
        assert len(whole)==1 and fragment_style(whole[0])==(0,False,False,2)
        image=QImage(900,1273,QImage.Format.Format_RGB32);image.fill(0xffffffff)
        painter=QPainter(image);universal.draw(painter,0);painter.end();image.save(str(folder/f'v54-beat-ties-{style}.png'))
        assert {crossing.id,dotted_crossing.id}<={nid for nid,_,_ in universal.tie_paths}
        assert midi_events(same_music)==original_events
    layered=copy.deepcopy(beat_song);layered.notes=[Note(0,PPQ,60),Note(0,PPQ,64)]
    assert len(set(ScoreLayout(layered).systems[0].voices.values()))==2
    # Verify the primary General MIDI bank and exercise the bundled renderers.
    electric=pack('synth:piano-electric')
    fresh=Project()
    assert fresh.audio=={role:dict(device=GENERALUSER_GS_DEVICE,program=0) for role in ('melody','chords','instrument')}
    gm=pack(GENERALUSER_GS_DEVICE)
    assert len(gm['presets'])==128
    assert all(item.get('bank',0)==0 and item['model']==item['program'] for item in gm['presets'])
    notice=(Path(gm['path'])/'GeneralUser-GS-LICENSE.txt').read_text('utf-8').strip()
    assert notice in credits_text(Project(notes=[Note(0,960,60)]),'melody',0,960,'offline')
    piano_peaks={}
    for device,renderer,programs,probes in (
            ('synth:piano-electric','sfz',{2,5,6},(2,5,6)),
            (GENERALUSER_GS_DEVICE,'sf2',set(range(128)),(0,1,2,24,40,73)),
            ('synth:pfsynth','native',{0},(0,))):
        assert pack(device).get('engine','native')==renderer and set(available_programs(device))==programs
        engine=SynthEngine(device,offline=True)
        try:
            for program in probes:
                engine.send(0xc0,program)
                peaks=[]
                for note in ((21,60,108) if device=='synth:pfsynth' else (60,)):
                    engine.send(0x90,note,96);data=engine.render(16384)
                    peak=float(abs(data).max());assert np.isfinite(data).all() and 1e-5<peak<=.950001
                    peaks.append(peak)
                    engine.stop();assert not engine.render(512).any()
                piano_peaks[f'{device}:{program}']=max(peaks)
        finally:engine.close()
    from lingfeng.audio.piano_catalog import DOWNLOADS
    from lingfeng.ui.sound_library import SoundLibraryDialog
    assert DOWNLOADS
    grand=next(entry for entry in DOWNLOADS if entry['id']=='piano-grand')
    assert grand['sha256']=='92cca7681e487976932cc9f143333ac5f4cac5c6a24fb377853a1077a15aa0fc'
    assert grand['archive_bytes']==190560219 and '/8432465f1fea83016635836c9850ac2b6398ffd3' in grand['url']
    assert grand['manifest']['sha256']==electric['sha256']
    from urllib.parse import urlsplit
    import lingfeng.audio.soundbanks as banks
    measured={}
    if getattr(sys,'frozen',False):
        from lingfeng.audio.calibration import calibrate_pack
        for name,data,programs in (('greg',electric,{2,5,6}),('generaluser',gm,{0,24,40,73}),
                                   ('pfsynth',pack('synth:pfsynth'),{0})):
            sample=dict(data,presets=[item for item in data['presets'] if item['program'] in programs])
            gains=calibrate_pack(Path(data['path']),sample)
            assert set(gains)=={str(program) for program in programs}
            for program,db in gains.items():
                shipped=banks.preset_calibration_db(int(program),'synth:'+data['id'])
                assert shipped is not None and abs(db-shipped)<=.3
            measured[name]=gains
    assert len({entry['id'] for entry in DOWNLOADS})==len(DOWNLOADS)
    for entry in DOWNLOADS:
        assets=entry.get('assets') or [entry]
        assert 0<entry['archive_bytes']<=1024**3
        if entry.get('assets'):assert entry['archive_bytes']==sum(asset['archive_bytes'] for asset in assets)
        for asset in assets:
            address=urlsplit(asset['url']);digest=asset['sha256']
            assert address.scheme=='https' and address.hostname and not address.hostname.endswith('.invalid')
            assert len(digest)==64 and all(c in '0123456789abcdef' for c in digest) and 0<asset['archive_bytes']<=1024**3
        assert entry['manifest']['id']==entry['id']
        banks._validate(entry['manifest'],Path(electric['path']),verify_files=False)
        assert all(entry.get(key) for key in ('name','name_en','description','description_en'))
    language_before=window.language
    for language in ('zh','en'):
        window.change_language(language,False);dialog=SoundLibraryDialog(window);received=[]
        dialog.installed.connect(received.append);dialog.show();app.processEvents()
        assert dialog.worker is None and dialog.choice.count()==len(DOWNLOADS) and dialog.local_button.isEnabled()
        grand_index=dialog.choice.findData(grand['id']);assert grand_index>=0;dialog.choice.setCurrentIndex(grand_index)
        assert dialog.description.text()==grand['description_en' if language=='en' else 'description']
        assert 'CC-BY-3.0' in dialog.license.text() and dialog.source_url().startswith('https://')
        assert '181.7 MiB'==dialog.size.text()
        dialog.installed.emit(str(Path(electric['path'])));assert received==[str(Path(electric['path']))]
        dialog.grab().save(str(folder/f'v52-sound-library-{language}.png'));dialog.close();dialog.deleteLater()
    window.change_language(language_before,False)
    # Exercise the actual modal loading UI with a delayed, cancellable local
    # substitute. This never opens a device or downloads/loads optional banks.
    import threading
    from time import monotonic
    from unittest.mock import patch
    from lingfeng.ui.audio_loading import AudioLoadingDialog,AudioLoadCancelled
    class AcceptanceRouter:
        closed=False
        def close(self):self.closed=True
    router=AcceptanceRouter();release=threading.Event();loading_ticks=[];painted=[];loader_threads=[]
    def delayed_router(settings,cancel):
        loader_threads.append(threading.current_thread() is not threading.main_thread())
        deadline=monotonic()+5
        while not release.wait(.01):
            if cancel.is_set():raise RuntimeError('acceptance loader cancelled')
            if monotonic()>=deadline:raise RuntimeError('acceptance loading GUI timed out')
        return router
    def capture_loading():
        dialogs=[widget for widget in app.topLevelWidgets() if isinstance(widget,AudioLoadingDialog) and widget.isVisible()]
        if dialogs:
            current=dialogs[-1]
            if current.progress.isVisible() and current.progress.maximum()==0:
                current.grab().save(str(folder/'v53-audio-loading.png'))
                painted.append(True)
    def loading_tick():
        loading_ticks.append(True)
        if not painted:capture_loading()
        if len(loading_ticks)>=3 and painted:release.set()
    heartbeat=QTimer();heartbeat.setInterval(10);heartbeat.timeout.connect(loading_tick);heartbeat.start()
    try:
        with patch('lingfeng.ui.audio_loading.ProcessRouter',side_effect=delayed_router):
            opened=AudioLoadingDialog.open_router(fresh.audio,window)
    finally:heartbeat.stop()
    assert opened is router and not router.closed and len(loading_ticks)>=3 and painted==[True] and loader_threads==[True]
    router.close();assert router.closed
    cancelled=[];cancel_ui=[]
    def cancelled_router(settings,cancel):
        assert cancel.wait(2);cancelled.append(True);raise RuntimeError('acceptance loader cancelled')
    def cancel_loading():
        dialogs=[widget for widget in app.topLevelWidgets() if isinstance(widget,AudioLoadingDialog) and widget.isVisible()]
        if dialogs:
            current=dialogs[-1];current.reject();cancel_ui.append(not current.cancel_button.isEnabled())
    QTimer.singleShot(60,cancel_loading)
    with patch('lingfeng.ui.audio_loading.ProcessRouter',side_effect=cancelled_router):
        try:AudioLoadingDialog.open_router(fresh.audio,window)
        except AudioLoadCancelled:pass
        else:raise AssertionError('Audio loading cancellation was ignored')
    assert cancelled==[True] and cancel_ui==[True]
    app.processEvents()
    # Polyphonic melodies can be scored; traditional notation stays selectable
    # and reports incompatible selected tracks without changing the document.
    from lingfeng.music.onsets import group_onsets,overlap_conflicts
    window.switch_workspace('compose');blocking=Project();blocking.notes=[Note(0,961,60),Note(960,960,64)]
    window.replace_project(blocking);notes_before=copy.deepcopy(window.project.notes);events_before=midi_events(window.project)
    assert window.switch_workspace('score') and window.workspace=='score'
    traditional=window.score_style.findData('traditional')
    assert window.score_style.model().item(traditional).isEnabled()
    before=copy.deepcopy(window.project.to_dict());history=len(window.undo_history)
    with patch('lingfeng.ui.score_compatibility_dialog.show_traditional_compatibility') as compatibility_report:
        window.set_notation('style','traditional')
        compatibility_report.assert_called_once_with(window,window.project)
    assert window.project.to_dict()==before and len(window.undo_history)==history
    for style in ('spatial','compact'):
        window.set_notation('style',style)
        assert export_pdf(window.score_view.canvas.project,folder/f'v563-polyphonic-{style}.pdf')>0
        app.processEvents();window.grab().save(str(folder/f'v563-polyphonic-{style}.png'))
    assert window.project.notes==notes_before and midi_events(window.project)==events_before
    assert len(group_onsets(blocking.notes))==2 and overlap_conflicts(blocking.notes)[0].end==961
    window.mutate('acceptance correct overlap',lambda p:setattr(p.notes[0],'duration',960))
    assert window.score_style.model().item(traditional).isEnabled()
    window.set_notation('style','traditional')
    assert window.project.notation['style']=='traditional' and window.score_view.canvas.project.notes[0].duration==960
    window.set_notation('style','spatial')
    assert window.switch_workspace('score') and set(window.score_pages)=={'melody','harmony','lyrics','instrument_lyrics','annotations'}
    # 0.56: creation preferences and display-only symbols in the installed app.
    from lingfeng.platform import chord_preferences
    from lingfeng.music.recognition import set_marker, set_recognition_disabled
    from lingfeng.music.rhythm import analyze
    from lingfeng.ui.dialogs import ChordMarkerDialog
    from lingfeng.ui.chord_settings_dialog import ChordSettingsDialog
    saved_preferences=chord_preferences.settings_dict()
    chord_preferences.set_preferences(dict(default_velocities=dict(melody=43,harmony=99),quick_chord_qualities=['m7','','7']))
    probe=Project();probe.chords=[Chord(0,1920)];marked=probe.chords[0]
    actual=midi_events(probe);set_marker(marked,50,'m7',5)
    assert marked.marked and marked.recognition_disabled and marked.name=='Dm7/F'
    assert marked.highlight_pcs=={0,2,5,9}
    assert probe.category(64,0)=='scale' and probe.category(62,0)=='both'
    assert not is_chord_tone(probe,64,0) and is_chord_tone(probe,62,0) and is_chord_tone(probe,65,0)
    for style in ('spatial','compact','traditional'):
        circle_probe=copy.deepcopy(probe)
        circle_probe.notes=[Note(0,240,64),Note(240,240,62),Note(480,240,65)]
        circle_probe.notation.update(style=style,circles=True,lyrics=False)
        events=midi_events(circle_probe);circle_layout=ScoreLayout(circle_probe)
        pieces=[f for system in circle_layout.systems for parts in system.fragments.values() for f in parts if f.note]
        assert [is_chord_tone(circle_probe,f.pitch,f.start) for f in pieces]==[False,True,True]
        assert circle_layout.glyph_extents(pieces[0])==(7,7) and circle_layout.glyph_extents(pieces[1])==(11,11)
        assert export_pdf(circle_probe,folder/f'v564-marked-circles-{style}.pdf')>0 and midi_events(circle_probe)==events
    marked_roll=PianoRoll(probe);marked_roll.selected_chords={marked.id}
    assert marked_roll.category(64,0)=='scale' and marked_roll.category(62,0)=='both'
    assert marked_roll.project.chords[0].highlight_pcs=={0,2,5,9}
    assert analyze(marked,probe) is None and midi_events(probe)==actual
    assert Project.from_dict(probe.to_dict()).to_dict()==probe.to_dict()
    marker_dialog=ChordMarkerDialog(marked,probe)
    marker_dialog.show();app.processEvents();marker_dialog.grab().save(str(folder/'v56-mark-chord.png'))
    marker_dialog.close();marker_dialog.deleteLater()
    set_recognition_disabled(marked,False,probe)
    assert not marked.marked and not marked.recognition_disabled and marked.name=='C'
    assert probe.category(64,0)=='both' and marked_roll.category(64,0)=='both'
    assert is_chord_tone(probe,64,0) and not is_chord_tone(probe,62,0)
    marked_roll.close();marked_roll.deleteLater()
    assert midi_events(probe)==actual
    edit=ChordDialog(marked,probe,defaults=dict(velocity=12))
    assert edit.velocity.value()==marked.velocity and edit.options()['velocity']==marked.velocity
    assert [edit.quality.itemData(i) for i in range(edit.quality.count())]==['m7','','7']
    edit.velocity.setValue(21);confirmed=edit.options();edit.close();edit.deleteLater()
    edit=ChordDialog(marked,probe,defaults=confirmed);assert edit.velocity.value()==marked.velocity
    edit.close();edit.deleteLater()
    settings=ChordSettingsDialog();assert settings.preview.rowCount()==len(QUALITIES)
    settings.show();app.processEvents();settings.grab().save(str(folder/'v56-chord-settings.png'))
    settings.tabs.setCurrentIndex(1);app.processEvents();settings.grab().save(str(folder/'v56-chord-reference.png'))
    settings.close();settings.deleteLater();chord_preferences.set_preferences(saved_preferences)
    # Note dynamics, unified chord velocities, note ranges and score annotations.
    from lingfeng.music.chord_operations import set_chord_velocity
    from lingfeng.music.note_operations import join_notes
    chord_preferences.set_preferences(dict(default_velocities=dict(melody=49,harmony=83)))
    probe=Project();probe.notes=[Note(0,480,60,11),Note(960,480,64,22),Note(1920,480,67,33)]
    probe.chords=[Chord(0,3840,pattern='quarters')];window.replace_project(probe)
    c=window.project.chords[0];original_events=midi_events(window.project)
    set_chord_velocity(c,37)
    assert {n.velocity for n in c.render_notes()}=={37}
    assert [(t,on,ch,p) for t,on,ch,p,v in midi_events(window.project)]==[(t,on,ch,p) for t,on,ch,p,v in original_events]
    assert Project.from_dict(window.project.to_dict()).chords[0].velocity==37
    assert 'bass_velocity' not in window.project.to_dict()['chords'][0]
    assert window.harmony_window.roll.creation_velocity(120)==37
    assert window.harmony_window.roll.creation_velocity(c.end)==83
    r=window.roll;r.selected_ids={n.id for n in r.notes};menu=r.note_menu(QPoint(round(r.x_at(120)),r.ruler_height+10),preserve=True)
    menu.velocity_menu.default_action.trigger();assert {n.velocity for n in window.project.notes}=={49}
    menu.close();menu.deleteLater();window.undo();assert [n.velocity for n in window.project.notes]==[11,22,33]
    joined=join_notes([Note(0,960,60,83),Note(960,960,60,71)])
    assert len(joined)==1 and joined[0].start==0 and joined[0].end==1920
    actual=midi_events(window.project);r.set_pitch_range(48,72)
    assert r.pitches==list(range(72,47,-1)) and midi_events(window.project)==actual
    r.set_compact(False)
    for key in window.score_pages:window.set_score_panel_visible(key,False)
    window.switch_workspace('compose');window.switch_workspace('score');assert window.score_tabs.count()==0
    window.show_score_panel('annotations');canvas=window.score_view.canvas
    canvas.set_selection_unit('note');canvas.selected_notes={n.id for n in window.project.notes}
    window.annotation_panel.kind.setCurrentIndex(window.annotation_panel.kind.findData('slur'));window.annotation_panel.refresh()
    window.annotation_panel.add_button.click();assert len(window.project.notation['symbols'])==1
    assert window.project.notation['symbols'][0]['kind']=='slur' and midi_events(window.project)==actual
    canvas.grab();assert canvas.layout.manual_slur_paths
    window.grab().save(str(folder/'v561-annotations.png'))
    state=copy.deepcopy(window.score_panel_state);window.switch_workspace('compose');window.switch_workspace('score')
    assert window.score_panel_state==state and window.score_tabs.count()==1
    window.undo();assert not window.project.notation.get('symbols');window.redo();assert len(window.project.notation['symbols'])==1
    chord_preferences.set_preferences(saved_preferences)
    # 0.56.2: the real QAction toggle resumes marked chords, and common commands
    # remain directly reachable under every saved menu order/grouping.
    from lingfeng.platform import context_menu_preferences
    from lingfeng.ui.context_menu_settings_dialog import ContextMenuSettingsDialog
    saved_menus=context_menu_preferences.settings_dict();context_menu_preferences.load_preferences({})
    probe=Project();probe.chords=[Chord(0,3840),Chord(3840,3840,55)]
    window.replace_project(probe);window.switch_workspace('compose')
    cid=window.project.chords[0].id;actual=midi_events(window.project)
    window.mutate('acceptance manual mark',lambda p:set_marker(p.chords[0],54,'m7',2),source=window.roll)
    r=window.roll;menu=r.lane.context_menu(QPoint(round(r.lane.x_at(120)),18));assert menu.recognition_action.isChecked()
    menu.recognition_action.trigger();assert not window.project.chords[0].marked and not window.project.chords[0].recognition_disabled
    assert window.project.chords[0].name=='C' and midi_events(window.project)==actual
    window.undo();assert window.project.chords[0].marked;window.redo();assert not window.project.chords[0].marked
    menu.close();menu.deleteLater()
    menu=r.lane.context_menu(QPoint(round(r.lane.x_at(120)),18))
    direct={a.text().split('\t',1)[0] for a in menu.actions()}
    assert {tr(label) for label in ('复制所选和弦','在此和弦开头覆盖粘贴','在定位线处粘贴和弦','二等分和弦','合并相邻和弦')}<=direct
    menu.close();menu.deleteLater()
    preferences=ContextMenuSettingsDialog();assert len(preferences.value()['context_menu_layout']['chord'])==11
    preferences.show();app.processEvents();preferences.grab().save(str(folder/'v562-menu-settings.png'))
    preferences.close();preferences.deleteLater()
    window.mutate('acceptance manual appearance',lambda p:set_marker(p.chords[1],50,'m7',5),source=r)
    app.processEvents();window.chord_lane.grab().save(str(folder/'v562-marked-chords.png'))
    assert window.project.chords[1].marked and midi_events(window.project)==actual
    assert all('底五交替' in PATTERNS[code] for code in ('alternating_quarters','alternating_eighths','alternating_offbeat'))
    context_menu_preferences.set_preferences(saved_menus)
    # Beat-local ties prefer the offbeat; display circles follow manual labels.
    from lingfeng.engraving.notation import beat_rhythm_parts
    assert beat_rhythm_parts(3000,840,0,PPQ)==[(3000,360),(3360,480)]
    assert beat_rhythm_parts(3000,960,0,PPQ)==[(3000,360),(3360,480),(3840,120)]
    for duration in (840,960):
        syncopation=Project(measures=[Measure(),Measure()])
        syncopation.contexts=[Context(0,syncopation.end)]
        source=Note(3000,duration,65);syncopation.notes=[source]
        syncopation.chords=[Chord(0,syncopation.end,notes=[Note(0,syncopation.end,p)for p in (48,52,55)])]
        set_marker(syncopation.chords[0],2,'m7',6)
        expected=[(3000,360),(3360,480)]+([(3840,120)]if duration==960 else [])
        for style in ('spatial','compact','traditional'):
            syncopation.notation.update(style=style,per_line=1,circles=True,lyrics=False)
            before=copy.deepcopy(syncopation.to_dict());events=midi_events(syncopation)
            engraved=ScoreLayout(syncopation)
            pieces=[f for system in engraved.systems for parts in system.fragments.values()for f in parts if f.note]
            assert [(f.start,f.duration)for f in pieces]==expected and all(f.note is source for f in pieces)
            assert all(is_chord_tone(syncopation,f.pitch,f.start)for f in pieces)
            ties=set()
            for page in range(engraved.pages):
                image=QImage(900,1273,QImage.Format.Format_RGB32);image.fill(0xffffffff)
                painter=QPainter(image);engraved.draw(painter,page);painter.end()
                image.save(str(folder/f'v564-offbeat-{duration}-{style}-{page}.png'))
                ties.update((nid,kind)for nid,kind,_ in engraved.tie_paths)
            assert (source.id,'continuous')in ties
            if duration==960:assert {(source.id,'incoming'),(source.id,'outgoing')}<=ties
            assert export_pdf(syncopation,folder/f'v564-offbeat-{duration}-{style}.pdf')>0
            assert syncopation.to_dict()==before and midi_events(syncopation)==events
    # 0.56.5: full local-bar bass, full denominator beats, and exact independent copies.
    probe=Project(measures=[Measure(3,8),Measure(3,8)]);probe.contexts=[Context(0,probe.end)]
    probe.put_chord(Chord(0,probe.end,pattern='sustained_bass_beats',gate=.5))
    assert [(n.start,n.duration) for n in probe.harmony_notes() if n.pitch==36]==[(0,1440),(1440,1440)]
    assert [(n.start,n.duration) for n in probe.harmony_notes() if n.pitch==48]==[(t,480) for t in range(0,2880,480)]
    assert analyze(probe.chords[0],probe).pattern=='sustained_bass_beats'
    probe=Project();probe.chords=[Chord(0,960),Chord(960,960)]
    probe.set_harmony_notes([Note(0,1920,53,79),Note(0,960,60,89),Note(960,960,64,91)])
    for chord in probe.chords[:2]:set_marker(chord,53,'maj7',None)
    copied=ChordClipboard.capture(probe.chords[:2],probe);expected=[[(n.start,n.duration,n.pitch,n.velocity) for n in c.notes] for c in probe.chords[:2]]
    ids=copied.paste(probe,1920);pasted=[c for c in probe.chords if c.id in ids]
    assert [[(n.start,n.duration,n.pitch,n.velocity) for n in c.notes] for c in pasted]==expected
    assert [(n.start,n.duration) for n in probe.harmony_notes() if n.pitch==53]==[(0,1920),(1920,1920)]
    probe.validate()
    migrated=load_bindings({'up':'W','left':'A','view_left':'Left','play':'Up'})
    assert migrated['up']=='Up' and migrated['left']=='Left' and migrated['view_left']=='' and migrated['play']==''
    # 0.56.6: permissive cropped pastes and separately managed, lyric-first slurs.
    probe=Project(measures=[Measure(),Measure(3,4),Measure(3,4)]);probe.contexts=[Context(0,probe.end)]
    source=Chord(0,6000,root=53,notes=[Note(0,6000,53,79),Note(240,240,60,91)])
    copied=ChordClipboard.capture([source]);ids=copied.paste(probe,3000)
    pasted=next(c for c in probe.chords if c.id in ids)
    assert pasted.start==3000 and pasted.end==3840 and pasted.notes[0].duration==840
    assert copied.can_paste(probe,probe.end) and copied.paste(probe,probe.end)==set()
    ids=copied.paste(probe,probe.end-50);assert next(c for c in probe.chords if c.id in ids).duration==50
    probe.validate()
    from lingfeng.engraving.lyrics import delete_range
    from lingfeng.engraving.presentation import add_slur
    probe=Project();probe.notes=[Note(0,480,60),Note(480,480,62)]
    apply_range(probe,'我/-',0,1);before=probe.to_dict()
    try:add_slur(probe,[n.id for n in probe.notes])
    except ValueError:pass
    else:raise AssertionError('Lyric slurs must prevent conflicting manual slurs')
    assert probe.to_dict()==before and not probe.notation.get('symbols')
    probe=Project();probe.notes=[Note(0,480,60),Note(480,480,62)]
    add_slur(probe,[n.id for n in probe.notes]);symbols=copy.deepcopy(probe.notation['symbols'])
    apply_range(probe,'我/-',0,1)
    layout=ScoreLayout(probe);image=QImage(900,1273,QImage.Format.Format_RGB32);image.fill(0xffffffff)
    painter=QPainter(image);layout.draw(painter,0);painter.end()
    assert layout.melisma_paths and not layout.manual_slur_paths and probe.notation['symbols']==symbols
    delete_range(probe,0,1);layout=ScoreLayout(probe)
    painter=QPainter(image);layout.draw(painter,0);painter.end()
    assert not layout.melisma_paths and layout.manual_slur_paths and probe.notation['symbols']==symbols
    probe=Project(measures=[Measure() for _ in range(4)]);probe.contexts=[Context(0,probe.end)]
    probe.notes=[Note(0,240,60),Note(11520,240,62)];apply_range(probe,'我/-',0,4)
    for style in ('traditional','spatial','compact'):
        probe.notation.update(style=style,per_line=1);layout=ScoreLayout(probe);kinds=[]
        for page in range(layout.pages):
            painter=QPainter(image);layout.draw(painter,page);painter.end();kinds.extend(kind for _,_,kind,_ in layout.melisma_paths)
        assert kinds==['outgoing','through','through','incoming']
    # 0.57: section destinations and a user-wide rhythm inference switch.
    from lingfeng.platform import rhythm_preferences
    from lingfeng.music.rhythm import analyze_performed, label as rhythm_label, extend
    from unittest.mock import patch
    probe=Project();probe.measures[0].section='Intro';probe.measures[3].section='Verse';probe.measures[5].section='Verse'
    probe.put_chord(Chord(0,3840,pattern='quarters'))
    match=analyze(probe.chords[0],probe);snapshot=probe.to_dict()
    original_enabled=rhythm_preferences.enabled()
    try:
        rhythm_preferences.set_enabled(False)
        with patch('lingfeng.music.rhythm._recognize',side_effect=AssertionError('Disabled rhythm detector ran')),patch('lingfeng.music.rhythm._recognize_bar',side_effect=AssertionError('Disabled bar rhythm detector ran')):
            assert analyze(probe.chords[0],probe) is None and analyze_performed(probe.chords[0],probe) is None
            assert rhythm_label(probe.chords[0],probe)==''
            assert regenerate(probe.chords[0],0,6000,probe,match) is None and extend(probe.chords[0],0,6000,match) is None
        assert probe.to_dict()==snapshot
    finally:rhythm_preferences.set_enabled(original_enabled)
    assert analyze(probe.chords[0],probe).pattern=='quarters'
    window.replace_project(probe);menu=window.main_roll.timeline_menu(QPoint(KEY_W+1,10))
    assert [a.data() for a in menu.section_jump_menu.actions()]==[0,3,5]
    assert [a.text() for a in menu.section_jump_menu.actions()]==[tr('{0} · 第 {1} 小节',name,bar+1) for name,bar in [('intro',0),('verse',3),('verse',5)]]
    selection=copy.deepcopy(window.main_roll.selection);snapshot=probe.to_dict()
    menu.section_jump_menu.actions()[1].trigger()
    assert window.playhead==probe.starts[3] and window.main_roll.selection==selection and probe.to_dict()==snapshot
    menu.deleteLater()
    # 0.57.1: camera updates do not rebuild music; undo retains shared records.
    from lingfeng.ui.history import HistoryState
    history_project=Project();history_project.notes=[Note(0,480,60)]
    first=HistoryState(history_project.to_dict(),None)
    history_project.bpm+=1;second=HistoryState(history_project.to_dict(),None,first)
    assert second['notes'] is first['notes'] and second['measures'] is first['measures']
    restored=Project.from_dict(second);restored.notes[0].pitch=72
    assert first['notes'][0]['pitch']==second['notes'][0]['pitch']==60
    window.switch_workspace('compose');window.melody_window.setFloating(False);window.harmony_window.setFloating(False)
    window.open_harmony();app.processEvents();r=window.roll
    r.pan_to(160,400);r.viewport().repaint();window.navigator.repaint()
    allocations=r.layer_allocations;overview_renders=window.navigator.cache_renders
    snapshot=window.project.to_dict();selection=copy.deepcopy(r.selection)
    with patch.object(window.project,'harmony_notes',side_effect=AssertionError('Camera rebuilt harmony MIDI')),patch.object(r,'update_ranges',side_effect=AssertionError('Camera rebuilt pitch range')):
        r.pan_to(240,420);app.processEvents();r.viewport().repaint();window.navigator.repaint()
    assert r.horizontalScrollBar().value()==240 and r.verticalScrollBar().value()==420
    assert r.layer_allocations==allocations and window.navigator.cache_renders==overview_renders
    assert window.project.to_dict()==snapshot and r.selection==selection
    # 0.58: the instrument roll can contribute pitches across chord boundaries.
    probe=Project(measures=[Measure(),Measure()],contexts=[Context(0,7680)],
                  chords=[Chord(0,1920),Chord(1920,1920),Chord(3840,3840)],
                  instrument_notes=[Note(1440,2400,71)])
    window.replace_project(probe);setting=window.instrument_recognition_action;original=setting.isChecked()
    setting.setChecked(False);snapshot=window.project.to_dict();actual=midi_events(window.project)
    assert [c.name for c in window.project.chords]==['C','C','C']
    setting.setChecked(True)
    assert [c.name for c in window.project.chords]==['Cmaj7','Cmaj7','C']
    assert window.project.to_dict()==snapshot and midi_events(window.project)==actual
    lane=window.chord_lane;lane.editor.selected_chords={c.id for c in window.project.chords[:2]}
    menu=lane.context_menu(QPoint(round(lane.x_at(100)),18),preserve=True)
    choices={a.data():a for a in menu.recognition_source_menu.actions()}
    assert choices['default'].isChecked()
    choices['0'].trigger()
    assert [c.name for c in window.project.chords]==['C','C','C'] and midi_events(window.project)==actual
    window.undo();assert [c.name for c in window.project.chords]==['Cmaj7','Cmaj7','C']
    setting.setChecked(original);menu.deleteLater()
    from lingfeng.music.abc_export import write_abc
    from lingfeng.music.abc_import import read_abc, project_from_abc
    probe=Project(notes=[Note(0,480,60)],instrument_notes=[Note(480,480,67)],chords=[Chord(0,3840)])
    data=probe.to_dict();data['measures'][0]['section']='Link'
    probe=Project.from_dict(data);assert probe.measures[0].section=='interlude'
    abc_path=folder/'v581-sheetsage2.abc'
    write_abc(probe,abc_path,sheetsage=True)
    abc=read_abc(abc_path);restored=project_from_abc(abc,**abc.defaults())
    assert restored.measures[0].section=='interlude'
    for track in (0,1):
        assert [(n.start,n.duration,n.pitch) for n in restored.melody_notes(track)]==[(n.start,n.duration,n.pitch) for n in probe.melody_notes(track)]
    window.replace_project(restored)
    assert [window.melody_tabs.tabText(track) for track in (0,1)]==[restored.melody_name(track) for track in (0,1)]
    assert set(window.audio_footer.sliders)=={'melody','instrument','chords'}
    from lingfeng.ui.section_progression_dialog import section_progressions
    before_insert=window.project.to_dict()
    assert window.insert_import(probe,1,False,tr('已插入 ABC'))
    assert len(window.project.measures)==len(restored.measures)+len(probe.measures)
    assert window.playhead==window.project.starts[1]
    assert [row.first_bar for row in section_progressions(window.project)][:2]==[0,1]
    window.undo();assert window.project.to_dict()==before_insert
    window.switch_melody_track(0)
    source_note=window.project.notes[0]
    window.roll.selected_ids={source_note.id}
    window.note_command(window.roll,'cut')
    assert not window.project.notes
    window.switch_melody_track(1)
    window.note_command(window.roll,'paste',1440)
    assert [(note.start,note.pitch) for note in window.roll.selected_notes()]==[(1440,source_note.pitch)]
    from lingfeng.music.musicxml_export import export_musicxml
    from lingfeng.music.musicxml_import import read_musicxml, project_from_musicxml
    xml_path=folder/'v59-roundtrip.mxl'
    export_musicxml(probe,xml_path)
    xml=read_musicxml(xml_path)
    restored=project_from_musicxml(xml,xml.default_mapping())
    for actual, expected in ((restored.notes,probe.notes),(restored.instrument_notes,probe.instrument_notes),
                             (restored.harmony_notes(),probe.harmony_notes())):
        assert sorted((n.start,n.duration,n.pitch) for n in actual)==sorted((n.start,n.duration,n.pitch) for n in expected)
    assert [(c.start,c.end,c.name) for c in restored.chords if not c.empty]==[(c.start,c.end,c.name) for c in probe.chords]
    window.dirty=False;window.close();app.processEvents()
    report={'status':'passed','version':__version__,'frozen':bool(getattr(sys,'frozen',False)),
            'python':sys.version.split()[0],'pdf_pages':pages,'melody_notes':len(q.notes),
            'harmony_notes':len(q.harmony_notes()),'checks':['project v5 roundtrip','patterns','recognition','MIDI','sound program','DAW bundle','PDF','two windows','8-bar score','compact folded editor','polyphony','marker inheritance','measure insertion','dark theme','icon transport','zero system gap','automatic top-aligned score','return to beginning','English catalog','720px layout','docked chord editor','retrograde clipboard','continuous ties','Lingfeng About and help','LFS','repeat compression preserves MIDI','local systems','custom palettes','chord structure frames','v0.11 workspace','both rolls floating','shared score tabs','two-region repeat validation','stacked lyrics below grid','empty chord insertion','single bottom scrollbar','shared roll settings','three score tabs','actual bass tooltip','symbol hit delete restores score','symbol-first validation','multiple structure drafts','dual-track overview','unified float/dock controls','melody sync option','paused replay stays paused','cached score playback','continuous barline time mapping','independent duration and snap','exclusive dotted and triplet','previous note duration','MIDI track import','disjoint bar broadcast','suppressed duplicate markers','binary 64th triplet split','triplet-aware import quantization','structure preserves MIDI coverage','MIDI input device enumeration','synthetic keyboard recording','independent lyrics roundtrip','orphan lyric x rendering','WinMM callback decoding'],'midi_input_devices':devices(),'physical_keyboard_tested':False}
    report['checks']+=['SheetSage2 dual melody ABC roundtrip','legacy Link migration to native Interlude','three track mixer controls']
    report['checks']+=['ABC bar insertion and undo','section progression previews follow inserted sections']
    report['checks']+=['cut and paste across melody tabs selects the new note']
    report['checks']+=['compressed MusicXML retains all three tracks and chord symbols','light chord strings synthesize a sustained chord']
    report['checks']=[item.replace('symbol hit delete restores score','saved structure remains visible with editor disabled').replace('symbol-first validation','retained structure backend validation').replace('multiple structure drafts','inactive structure editor preserves latent state').replace('orphan lyric x rendering','explicit rap x rendering') for item in report['checks']]+['one menu font and baseline','unique lyric onset validation','dotted rap duration','lyrics tab confirmation','centered unpitched rhythm','optional scale lines','glyphs fit time slots','root and inversion shortcuts','19 chord qualities','seek preserves playback state']
    report['checks']+=['edit undo redo preserve playback worker','composition has no lyric property','collapsed automatic score area','exact pitch spacing','uniform note rest rap fonts','bar onset template','bounded lyric coverage','rap range overflow validation']
    report['checks']+=['pointer anchored zoom to 2048','navigation outside the visible cursor disables following','independent pitch gap and font','propagate key and full meter']
    report['checks']+=['navigation preserves playback clock and anchor','live loop cancellation continues beyond selection','timeline wheel shares anchored zoom','note bodies do not seek','chord root degrees use chord-start key']
    report['checks']+=['independent main time view with both rolls floating','complete transport in both floating rolls','individual bidirectional main timeline links','per-window automatic following','manual scrollbar leaving the cursor disables affected following','key height keeps central pitch']
    report['checks']=[item.replace('structure preserves MIDI coverage','structure overwrite preserves uncovered neighbors') for item in report['checks']]
    report['checks']+=['shared chord cards with local floating selection','pattern recognition and extension','structure shrink deletes vacated notes','packed chord clipboard','chord split and merge','fixed positioning line insertion','configurable editor keys']
    report['checks']+=['note resize overwrites intersections without union','polyphonic overlap paste','score and PDF ignore stale lyric matching','lyric entry still validates onset coverage','immediate pattern recognition after shrink and extension','recognition preserves actual voicing and dynamics','recognized rhythm roundtrip']
    report['checks']+=['contextual semitone and scale-step keys','diatonic chord movement restores root-position bass','one default chord lane per window','manual chord lane override survives refresh','closing floating chord roll hides it; View docks it','nearest chord lane controls melody highlight','floating melody retains independent chord lane']
    report['checks']+=['Tab cycles chords without seeking','root semitone command preserves quality and restores bass','bass replacement has no persistent check state','adjacent one-beat chords use full-bar rhythm phase','known patterns rebuild default note attributes','custom patterns retain note metadata on move and resize']
    report['checks']+=['explicit Custom pattern flag roundtrip','fixed transposition locks actual MIDI','applying pattern clears Custom lock','exclusive note and chord selection','stable single and multiple chord menus','timeline menu contains only bar commands','reuse and locate score chord tab without seeking','one-bar block audition','sequential actual chord audition','mixed key and meter PDF export']
    report['checks']+=['new note overwrite preserves outside pieces','moved note overwrite splits destination','chord lane Shift-wheel shares zoom','independent roll coloring switches','owned app windows','shared floating mixer volumes and mutes','floating melody lane toggle survives mounting','transport frames reuse static piano roll layer']
    report['checks']+=['timeline sync binds and unbinds following','optional chord velocity lane','sync action in other options','Q tool toggle','legato MIDI import preserves rearticulation']
    report['checks']+=['frozen floating copy shortcut','undo activates originating window','redo restores edit','visible score font toolbar independent of pitch gap','localized lightweight computer-friendly About']
    report['checks']=[check.replace('owned app windows','peer app windows') for check in report['checks']]
    report['checks']+=['parentless peer editor windows','global note-degree preference preserves music','bilingual composition DAW inspiration and MIT notices','application MIT license included']
    report['checks']+=['chord movement stays in source meter region','named pattern crop at meter boundary','pattern meter compatibility','cross-key Roman labels and multiline chord tooltip','longer bar inserts silence without stretching chords','shared vector window buttons','joined chord fragments select together','pinned upstream license inventory and audit','unused software OpenGL library omitted']
    report['checks']+=['ordered cross-mode note degrees','twelve bass replacements','ninth chord fourth inversion','docked roll hide buttons','quantity in bar insertion','selected-note movement keeps visible pitch']
    report['checks']+=['clipboard carries source meter','whole cropped chord can return while selected','locked versus unrecognized pattern labels','bar deletion cuts crossing notes','delete bars in timeline menu']
    report['checks']+=['arrow keys browse without music edits or seeking','Shift+3 toggles shared snap triplets only','batch patterns for same-meter recognized chords','chord marquee scrolls at viewport edge','empty marquee repaints on release']
    report['checks']+=['plain chord click narrows multiple selection','group drag previews preserve MIDI until release','recognized quarter-block rhythm survives quality edit','scale-spelled chord names and quality-spelled chromatic tones','numbered sharp-only chord dialog root choices','tiny notation artifacts do not create ties or change MIDI']
    report['checks']+=['chord preview overlays neighbor cards and text with matching hit priority']
    report['checks']+=['separate bar and time-ruler bands','ruler drag sets loop without seeking','shared loop independent of bar selection','loop cancellation clears bounds permanently','lower ruler ignores right drag','narrow note gaps position without editing','two-axis middle-button piano-roll pan','bounded shared footer in score mode','chord-tone circles reflect performed MIDI only']
    report['checks']+=['actual fragment rhythm before regeneration','regenerate chord checked by default','gated bass fragment becomes complete quarter block','docked page grid broadcasts both ways','floating grid does not replace main grid','redocking inherits page grid','auxiliary chord ruler never changes snapping','floating lane position alignment']
    report['checks']+=['adjacent highlighted chord borders keep a clear gutter at fractional DPI']
    report['checks']=[check.replace('project v5 roundtrip','project v6 roundtrip').replace('joined chord fragments select together','continuous event fragments select together') for check in report['checks']]
    report['checks']+=['silent NC bar coverage','repeated section names remain separate','section export bounds','continuous MIDI across chord regions','continuous event project roundtrip','explicit split cuts only requested onset','PyChord Roman progression generation','chronological progression capture','offline MP3 encoded in runtime','range MIDI export','format-specific PDF versus music ranges','both audio export choices','packaged SoundCard header loads']
    report['checks']+=['six unique modal degree sequences in both accidental preferences','starting-key letter chord progression preview','marker choices use accidentals and modal degrees','unknown chord cannot claim known rhythm','compact root-relative unique chord tones','title-case section migration','floating edit dialog origin remains local']
    report['checks']+=['floating rolls uncheck main View without hiding','closed floats stay hidden on layout refresh','editing navigation reuses floating windows','View reclaims both rolls to main page','ASCII progression separators normalized','degree order and shorter-prefix progression sorting']
    report['checks']+=['21 complete public progression recipes','all catalogue chords validated with PyChord','applied chord with explicit bass','root subsequence preserves accidentals','optional name defaults to Roman progression','manager search and local edits','catalogue upgrade respects subsequent edits','named preset with separate Roman and letter previews']
    report['checks']+=['selected roots ignore quality bass and unselected gaps','prefilled manager retains inversion recipes','chord context search stays in originating floating window','captured inversions regenerate their bass']
    report['checks']=[item.replace('19 chord qualities','20 chord qualities') for item in report['checks']]
    report['checks']+=['Chorus migration and repeated sections','mM7 and add2 generation recognition and recipes','generated legacy add9 uses close position','onset-key root order begins at one','remembered controls exclude target time range']
    report['checks']+=['alternating bass follows meter denominator','three upper-chord rhythms and pattern recognition','odd meter rejection','octave note menu preserves timing velocity and undo']
    report['checks']+=['complete shortcut settings registry','conflict confirm transfers and cancel restores','cleared binding persists without default resurrection','menus show current and alternate shortcuts']
    report['checks']=[item.replace('20 chord qualities','21 chord qualities') for item in report['checks']]
    report['checks']+=['last duration is default with temporary grid fallback','duration follows actual edits and undo','7b5 components and preferred recognition','7b5 progression and project roundtrip']
    report['checks']+=['default 20 pixel piano keys','variable measure widths and linear spatial time grid','score-wide proportional symbol fitting','16 native synthesis presets and stop','synth pack settings and project roundtrip','actual export attribution sidecar','synth licenses and complete preset catalog']
    report['checks']+=['38 bundled calibrated synthesis presets and releases','128 distinct GM instrument names','chromatic tonic selector anchored at first chord','capture tonicization preserves Roman-only recipes','apply selected tonic and preview agree','literal chord query resolves against selected tonic']
    report['checks']+=['modal degree labels shared by root bass and three progression dialogs','scale tones retain modal accidentals in both preferences','chord editor starts with key tonic and matching bass','only quality pattern and gate remembered; velocity uses saved default','root changes move bass without reverse coupling','root bass stores no redundant slash']
    report['checks']+=['traditional notes and dashes use equal columns within beats','forced-row font ratio follows global size','unmerged systems share global font','forced-row original measure count roundtrip']
    report['checks']+=['traditional meter-beat whitespace','deferred score layout in compose','music snapshot refresh at score entry','engraving controls preserve frozen music','page zoom and width fit','measure visibility on both axes','viewport-sized bitmap cache','PDF snapshot with current MIDI export']
    report['checks']+=['isolated 32nd pair spacing in all score styles','three underlines with removed companion dot','display-only timing preserves MIDI bytes','traditional justified row width and compact height','short traditional measure lines','compose suspends cached score work']
    report['checks']+=['traditional rows reach both page margins','each traditional beat owns its visible columns without trailing beat space','visible advisory font limit can be exceeded','requested font matches project snapshot and rendering','font choices preserve measures per line']
    report['checks']+=['traditional row-wide common cells and uniform gaps across barlines','forced rows scale beat gaps with saved font ratio','traditional beat spacing preserves music and PDF']
    report['checks']+=['traditional short legato tails retain one melody row while true polyphony retains lanes','cross-beat syncopations and dotted values split into tied source fragments','aligned three-beat sustains retain extension dashes without augmentation dots','beat spelling preserves source notes lyric bindings and MIDI bytes on screen and PDF']
    report['checks']+=['polyphonic melody enters spatial and compact Score without rewriting music','polyphonic spatial and compact scores export PDF','traditional style remains selectable and reports incompatible selected melody tracks','corrected adjacent source notes retain all four active editor panels','retired structure editor is inactive while pure compatibility APIs preserve stored notation','traditional global numeric cells and barline-side gaps retain the two-to-one gap ratio']
    report['checks']+=['numeric recommended font fills the heaviest row while sparse rows keep the same digit cells','spatial and compact cross-beat ties and integral sustain dashes preserve source music']
    report['checks']+=['traditional integer recommendation and circle-outline unit reserve remain consistent','actual traditional first second and third rhythm strokes align below the row lowest octave dots']
    report['checks']+=['symbol-budget recommended font fits A4 without whole-row transforms or MIDI changes','cross-beat triplets render one source-group bracket label in all three score styles']
    report['checks']+=['forced traditional fonts bind to nonforced or unmerged-baseline visible-unit budgets']
    report['checks']=[item.replace('busiest-beat 4:2 measure widths in all engraving styles','busiest-beat 4:2 measure widths in spatial and compact styles').replace('equal-density beats allocate 1:2 measure widths in all styles','equal-density beats allocate 1:2 measure widths in spatial and compact styles').replace('forced rows scale beat gaps with saved font ratio','forced traditional rows retain global cells and two-to-one gap units').replace('traditional short legato tails retain one melody row while true polyphony retains lanes','compatibility renderer retains legato/polyphony lanes while traditional UI requires monophony') for item in report['checks']]
    report['checks']+=['partial lyric ranges and invisible hyphen skips','rap groups replace existing digits in all score styles','rap preserves MIDI notes and supports undo redo']
    report['checks']+=['unique MIDI lyric starts inside sustains','range selection autofills saved lyric assignments','range edits preserve outside lyrics and MIDI','range autofill follows undo redo']
    report['checks']+=['demo uses selectable Verse Chorus labels','adjacent Chinese English contractions and quotes','mixed lyric range autofill preserves MIDI','tight symbol envelopes retain safe common fonts and density-based widths in all styles']
    report['checks']+=['first lyric opening loads existing text','one line per bar with compact Han and English word spaces','continuous rap groups span bars','slash skips and punctuation consume correct slots','packaged rap example retains MIDI notes']
    report['checks']+=['row-entry continuation uses a descending half-curve in all styles','full in-row and outgoing tie arches retained','screen and PDF tie changes preserve MIDI bytes','slash-s skips without a slur','successive slash-hyphens connect adjacent notes on screen and PDF only','lyric melisma undo redo and example roundtrip']
    report['checks']+=['process-owned playback schedule survives live edit undo redo','versioned preferences preserve unknown fields and upgrade backup','explicitly empty progression library survives upgrade','categorized bilingual help and cross-language search','help no-results state']
    report['checks']+=['live score title author undo redo and PDF','section command retained on timeline only','visible cursor browsing keeps follow without snapping back','offscreen browsing cancels shared follow','score selected chord tab follows main cursor','score floating roll follows independently']
    report['checks']+=['floating score melody exposes its timeline sync menu']
    report['checks']+=['score scrollbar owns camera while held','score measure leaving viewport cancels even with visible roll cursor','score browsing does not snap back after release','roll browsing ignores visible score and does not pin cursor at left edge']
    report['checks']+=['busiest-beat 4:2 measure widths in all engraving styles','density layout preserves MIDI bytes and global glyph safety','bundled Greg Sullivan, GeneralUser GS and PFSynth presets render finite audible bounded audio and stop','fresh projects prefer the GeneralUser GS grand piano','GeneralUser GS exposes all 128 bank-0 programs and exports retain the upstream license','optional grand download pinned by revision size and SHA-256','bilingual sound-library UI and installed signal without network']
    report['checks']+=['2/4 and 4/4 equal-density beats allocate 1:2 measure widths in all styles','mixed-meter width correction preserves MIDI bytes','every optional catalog entry has pinned HTTPS metadata and a valid manifest without requiring bank installation','sound loading paints and processes GUI events before returning the ready router','sound loading cancel reaches its worker and waits for cleanup']
    report['checks']+=['independent melody and chord default velocities','chord editor uses creation history or the current chord','selected ordered quick qualities','complete chord quality and degree preview','manual Roman and letter annotations preserve MIDI performance','disabled chords bypass chord and pattern recognition','resuming recognition removes annotations','recognition and annotation project roundtrip']
    report['checks']+=['first Score entry closes every tab','Score tabs preserve later visibility','cross-region adjacent notes merge as one sustained event','note velocity menus use saved defaults','unified generated chord velocity','common chord velocity project roundtrip','harmony creation follows chord velocity with blank-region default fallback','custom inclusive piano-roll pitch range preserves MIDI','annotation panel adds one multi-note slur without MIDI edits','manual slur renders in score','score annotation undo redo and persistent panel state']
    report['checks']+=['marked chord symbols drive melody-roll matching and selected pitch-class highlights without MIDI changes']
    report['checks']+=['manual chord labels guide score circles and glyph reserve in all three styles and PDF without MIDI changes','resuming recognition restores performed-tone circles']
    report['checks']+=['offbeat-first beat-local ties and cross-bar continuations retain source IDs circles and MIDI in all three score styles and PDF']
    report['checks']=[item.replace('three score tabs','four score panels initially hidden') for item in report['checks']]
    report['checks']+=['marked chords resume recognition via actual QAction trigger','recognition checkbox preserves MIDI and supports undo redo','marked chord appearance differs from automatic chords','copy paste split and merge stay at menu root','context-menu ordering and optional advanced grouping','context-menu settings offer all retained blocks','alternating bass labels consistently use 底五交替']
    report['piano_sample_peaks']=piano_peaks
    if measured:
        for name,gains in measured.items():report[f'{name}_loudness_compensation_db']=gains
        report['checks'].append('frozen calibration worker reproduces sampled Greg, GeneralUser GS and PFSynth preset gains')
    report['checks']+=['full-bar bass and full denominator-beat upper chords','copied actual voicing dynamics and timing are exact','copied cross-region sustains retain independent rearticulations','fixed movement arrows migrate old preferences and leave camera keys blank']
    report['checks']+=['different-meter chord pastes crop at destination boundaries','project-end chord pastes crop or safely do nothing','lyric slurs block conflicting new manual arcs and silently hide existing ones without deleting data']
    report['checks']+=['automatic lyric slurs continue across intervening rest rows in all three score styles']
    report['checks']+=['global rhythm switch bypasses both detectors and cached inferred rebuilds without changing music','reenabling rhythm recognition restores existing inference','section jump menu retains repeated names and exact measure destinations','section navigation preserves music and time selection']
    report['checks']+=['unchanged undo records share storage without changing restored music','middle-pan camera path bypasses MIDI and pitch-range rebuilding','camera frames reuse pixel allocations and overview music','camera navigation preserves music and selections']
    report['checks']+=['section selection menu is present on the bar ruler','Melody 2 chord recognition respects overlapping ranges and preserves performed MIDI','chord recognition source can be overridden for multiple chords and undone']
    (folder/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0

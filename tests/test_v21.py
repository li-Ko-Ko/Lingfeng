"""Root shortcuts, momentary bass replacement and bar-phased chord patterns."""
import os,copy,sys,unittest,tempfile
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPoint
from PySide6.QtWidgets import QApplication,QLineEdit
from PySide6.QtTest import QTest
from popscore.model import Project,Chord,Note,PATTERNS,MODES
from popscore.chordops import change_chords,move_chords,invert_chord,can_move_diatonic
from popscore.operations import repartition_chord,resize_chord
from popscore.rhythm import analyze,regenerate
from popscore.app import MainWindow
from popscore.keybindings import normalized
from tests.music_reference import bar_events as reference

APP=QApplication.instance() or QApplication([])
def signature(notes):return sorted((n.start,n.duration,n.pitch,n.velocity) for n in notes)
class MusicTests(unittest.TestCase):
    def test_root_and_diatonic_commands_keep_cropped_arpeggio_without_invented_bass(self):
        for command in ('root_step:1','diatonic:1','inversion:0','inversion:2'):
            p=Project();p.put_chord(Chord(480,480,48,'',4,pattern='up'))
            c=p.chords[0];self.assertEqual([n.pitch for n in c.notes],[48])
            change_chords(p,{c.id},command);c=p.chords[0]
            expected=49 if command=='root_step:1' else 50 if command=='diatonic:1' else 48
            self.assertEqual([n.pitch for n in c.notes],[expected]);self.assertEqual(analyze(c,p).pattern,'up')
    def test_changing_pattern_and_bounds_together_honors_new_pattern(self):
        p=Project();p.put_chord(Chord(0,3840,pattern='up'));c=copy.deepcopy(p.chords[0])
        c.start=960;c.duration=4800;c.pattern='offbeat';c.notes=None;p.put_chord(c)
        self.assertEqual(analyze(p.chords[0],p).pattern,'offbeat')
        self.assertEqual(signature(p.harmony_notes()),reference(c,p,960,5760))
    def test_root_step_preserves_quality_rhythm_timing_velocity_and_resets_bass(self):
        for command in ('root_step:1','root:1'):
            p=Project();c=Chord(480,3840,48,'7',4,pattern='up',gate=.71,velocity=88,octave=1);p.chords=[c]
            change_chords(p,{c.id},command);result=p.chords[0]
            self.assertEqual((result.root%12,result.quality,result.bass),(1,'7',None))
            for key in ('id','start','duration','pattern','gate','velocity','octave'):self.assertEqual(getattr(result,key),getattr(c,key))
    def test_bass_replacement_does_not_add_upper_notes_or_modify_their_events(self):
        c=Chord(0,3840,48,'',4,notes=[Note(0,960,52,71),Note(0,2400,55,82),Note(0,3840,60,93)])
        ids=[n.id for n in c.notes];top=copy.deepcopy(c.notes[1:]);invert_chord(c,0)
        self.assertEqual(c.notes[0].pitch,48);self.assertEqual(c.notes[1:],top);self.assertEqual([n.id for n in c.notes],ids);self.assertIsNone(c.bass)
        invert_chord(c,2);self.assertEqual(c.notes[0].pitch,43);self.assertEqual(c.notes[1:],top)
    def test_diatonic_changes_quality_and_restores_root_position(self):
        p=Project();c=Chord(0,3840,48,'',4);p.chords=[c];change_chords(p,{c.id},'diatonic:1')
        self.assertEqual((p.chords[0].name,p.chords[0].bass),('Dm',None))
        change_chords(p,{c.id},'diatonic:-1');self.assertEqual(p.chords[0].name,'C')
        p.chords=[Chord(0,3840,48,'7',4)];self.assertFalse(can_move_diatonic(p,p.chords,1));before=p.to_dict()
        with self.assertRaises(ValueError):change_chords(p,{p.chords[0].id},'diatonic:1')
        self.assertEqual(before,p.to_dict());change_chords(p,{p.chords[0].id},'root_step:1');self.assertEqual(p.chords[0].name,'C#7')
    def test_every_pattern_crops_full_bars_at_both_edges_and_mixed_meters(self):
        for pattern in PATTERNS:
            for mixed in (False,True):
                p=Project()
                if mixed:p.set_markers([0],48,'Ionian',3,4);p.set_markers([1],48,'Ionian',6,8)
                c=Chord(0,3840,48,'7',4,pattern=pattern,gate=.73,velocity=83)
                for a,b in ((960,2880),(1200,6240),(2880,7680)):
                    with self.subTest(pattern=pattern,mixed=mixed,a=a,b=b):
                        from popscore.rhythm import supports
                        from popscore.meter import region_at
                        result=regenerate(c,a,b,p)
                        if not supports(pattern,p,c.start) or not supports(pattern,p,a):
                            self.assertIsNone(result);continue
                        stop=min(b,region_at(p,a)[1])
                        self.assertEqual(signature(result.render_notes()),reference(c,p,a,stop));self.assertEqual(analyze(result,p).pattern,pattern)
                        self.assertEqual((result.name,result.pattern,result.gate,result.velocity),(c.name,pattern,.73,83))
    def test_four_adjacent_chords_take_different_positions_in_same_bar(self):
        p=Project();p.chords=[Chord(i*960,960,root,quality,pattern='up') for i,(root,quality) in enumerate(((48,''),(53,''),(55,''),(57,'m')))]
        for c in list(p.chords):change_chords(p,{c.id},'pattern:up')
        for c in p.chords:self.assertEqual(signature(c.render_notes()),reference(c,p,c.start,c.end))
        self.assertEqual([c.notes[0].pitch for c in p.chords],[36,57,43,60])
    def test_moving_and_resizing_named_pattern_resets_note_metadata_only(self):
        p=Project();c=Chord(0,3840,48,'7',4,pattern='quarters',velocity=79);c.materialize()
        for n in c.notes:n.velocity=110;n.flat=True
        p.chords=[c];move_chords(p,{c.id},1200);result=p.chords[0]
        self.assertEqual(signature(result.render_notes()),reference(c,p,1200,5040));self.assertTrue(all(n.velocity==79 and not n.flat for n in result.notes))
        repartition_chord(p,c.id,1680,7000);result=p.chords[0]
        self.assertEqual(signature(result.render_notes()),reference(c,p,1680,7000));self.assertEqual(result.name,c.name)
    def test_custom_rhythm_moves_without_reset_and_resize_preserves_uncovered_events(self):
        p=Project();c=Chord(960,3840,notes=[Note(113,431,48,71),Note(728,997,52,83),Note(1801,514,55,102)])
        self.assertIsNone(analyze(c,p));p.chords=[c];before=copy.deepcopy(c.notes);move_chords(p,{c.id},480)
        self.assertEqual(p.chords[0].notes,before);repartition_chord(p,c.id,1200,6000)
        self.assertEqual(signature(p.chords[0].render_notes()),[(1440+n.start,n.duration,n.pitch,n.velocity) for n in before])
    def test_empty_offbeat_crop_still_remembers_name_pattern_and_can_expand(self):
        p=Project();c=Chord(0,3840,48,'',4,pattern='offbeat');p.chords=[c]
        repartition_chord(p,c.id,0,240);self.assertEqual(p.chords[0].notes,[]);self.assertEqual(analyze(p.chords[0],p).pattern,'offbeat')
        repartition_chord(p,c.id,960,2880);self.assertEqual(signature(p.harmony_notes()),reference(c,p,960,2880))
    def test_old_project_stays_unchanged_until_edit_and_new_events_roundtrip(self):
        p=Project();c=Chord(960,3840,pattern='up');p.chords=[c];before=signature(p.harmony_notes());loaded=Project.from_dict(p.to_dict())
        self.assertEqual(signature(loaded.harmony_notes()),before);move_chords(loaded,{c.id},240)
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            path=Path(folder)/'bar-pattern.lfs';loaded.save(path);again=Project.load(path)
        self.assertEqual(signature(again.harmony_notes()),reference(c,p,1200,5040));self.assertEqual(analyze(again.chords[0],again).pattern,'up')

class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.errors=[];self.hook=patch.object(sys,'excepthook',lambda typ,value,tb:self.errors.append(str(value)));self.hook.start()
        self.warning=patch('popscore.app.QMessageBox.warning',side_effect=AssertionError('Unexpected warning'));self.warning.start()
        p=Project();p.chords=[Chord(0,3840,48,'',4),Chord(4800,1920,55),Chord(7680,3840,57,'m')];p.notes=[Note(0,960,60)]
        self.w=MainWindow(p);self.w.change_language('zh',False);self.w.keybindings=normalized({});self.w.show();self.w.resize(1150,850);self.w.timer.stop();self.w.autosave.stop()
        for b in self.w.mute_buttons.values():b.setChecked(True)
        QTest.qWait(20)
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.warning.stop();self.hook.stop();self.assertFalse(self.errors)
    def select(self,lane,cid):
        lane.editor.edit_target='chords';lane.selection_event({cid});lane.window().activateWindow();lane.setFocus();APP.processEvents()
    def test_tab_cycles_chords_including_floating_lane_without_seeking_or_editing(self):
        w=self.w;lane=w.chord_lane;ids=[c.id for c in w.project.chords];self.select(lane,ids[0]);before=w.project.to_dict();head=w.playhead
        for target in (ids[1],ids[2],ids[0]):QTest.keyClick(lane,Qt.Key.Key_Tab);self.assertEqual(lane.editor.selected_chords,{target})
        self.assertEqual(w.project.to_dict(),before);self.assertEqual(w.playhead,head)
        w.open_harmony();w.harmony_window.setFloating(True);QTest.qWait(20);lane=w.harmony_window.roll.lane;self.select(lane,ids[1]);main_selection=set(w.roll.selected_chords)
        QTest.keyClick(lane,Qt.Key.Key_Tab);self.assertEqual(lane.editor.selected_chords,{ids[2]});self.assertEqual(w.roll.selected_chords,main_selection)
        field=QLineEdit(w.harmony_window);field.show();field.setFocus();APP.processEvents();QTest.keyClick(field,Qt.Key.Key_Tab);self.assertEqual(lane.editor.selected_chords,{ids[2]})
    def test_root_and_scale_keys_are_distinct_and_bass_actions_are_not_checkable(self):
        w=self.w;lane=w.chord_lane;c=w.project.chords[0];self.select(lane,c.id)
        QTest.keyClick(lane,Qt.Key.Key_W);self.assertEqual(w.project.chords[0].name,'C#')
        QTest.keyClick(lane,Qt.Key.Key_S);self.assertEqual(w.project.chords[0].name,'C')
        QTest.keyClick(lane,Qt.Key.Key_W,Qt.KeyboardModifier.AltModifier);self.assertEqual(w.project.chords[0].name,'Dm')
        menu=lane.context_menu(QPoint(round(lane.x_at(960)),25));self.assertFalse(any(a.isCheckable() for a in menu.inversion_menu.actions()))
        menu.inversion_menu.actions()[1].trigger();self.assertEqual(w.project.chords[0].name,'Dm/F')
        QTest.keyClick(lane,Qt.Key.Key_S,Qt.KeyboardModifier.AltModifier);self.assertEqual(w.project.chords[0].name,'C')
    def test_live_move_resize_and_undo_keep_worker_and_bar_phase(self):
        w=self.w;c=w.project.chords[0];c.pattern='up';w.refresh();w.toggle_play();worker=w.transport.thread;clock=w.transport.start_time
        w.chord_command('move:1200',{c.id},w.roll);self.assertEqual(signature(next(x for x in w.project.chords if x.id==c.id).render_notes()),reference(c,w.project,1200,5040))
        w.change_chord_structure(resize_chord(next(x for x in w.project.chords if x.id==c.id),1680,6240,project=w.project));self.assertEqual(signature(next(x for x in w.project.chords if x.id==c.id).render_notes()),reference(c,w.project,1680,6240))
        w.undo();w.redo();self.assertIs(w.transport.thread,worker);self.assertEqual(w.transport.start_time,clock);self.assertTrue(w.transport.playing)

if __name__=='__main__':unittest.main()

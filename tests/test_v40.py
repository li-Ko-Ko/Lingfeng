"""Close-position add2, octave note edits and meter-aware alternating bass."""
import copy,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QLineEdit,QMenu
from popscore.app import MainWindow
from popscore.model import Project,Chord,Note,Context,Measure,PPQ,QUALITIES
from popscore.rhythm import ALTERNATING,Rhythm,regenerate,analyze,analyze_performed,supports
from popscore.chordops import change_chords,can_apply_pattern
from popscore.dialogs import ChordDialog
from popscore.keybindings import load_bindings,validate
from popscore.progressions import resolve,apply
from popscore.midi import export_midi
from popscore.meter import moved_chord,rescan_chord

APP=QApplication.instance() or QApplication([])

def project(n=4,d=4,bars=2):
    p=Project();p.measures=[Measure(n,d) for _ in range(bars)];p.contexts=[Context(0,p.end)];return p

def events(c):return sorted((n.start,n.duration,n.pitch,n.velocity) for n in c.render_notes())

def expected(pattern,n,d,bars=1,gate=.75):
    """Independent explicit score: C bass alternates C2/G2; upper C3 D3 E3 G3."""
    beat=3840//d;length=n*beat;result=[]
    for bar in range(bars):
        for i in range(n):result.append((bar*length+i*beat,round(beat*gate),36 if i%2==0 else 43,79))
        if pattern=='alternating_offbeat':onsets=range(beat//2,length,beat);unit=beat//2
        else:unit=960 if pattern=='alternating_quarters' else 480;onsets=range(0,length,unit)
        for t in onsets:
            for pitch in (48,50,52,55):result.append((bar*length+t,min(length-t,round(unit*gate)),pitch,79))
    return sorted(result)

class Add2Tests(unittest.TestCase):
    def test_default_and_pychord_degrees_are_close_position(self):
        c=resolve('Iadd2',0)
        from pychord import Chord as PyChord
        self.assertEqual(PyChord('Cadd2').components(visible=False),[0,2,4,7])
        self.assertEqual(c.pitches,[36,48,50,52,55])
        for root in range(12):
            p=project();c=Chord(0,3840,48+root,'add2');p.put_chord(c)
            self.assertEqual([n.pitch for n in p.chords[0].render_notes()],[36+root,48+root,50+root,52+root,55+root])

    def test_old_generated_add9_loads_dense_but_explicit_voicing_is_kept(self):
        p=project();p.chords=[Chord(0,3840,quality='add2')];data=p.to_dict();data['chords'][0]['quality']='add9'
        c=Project.from_dict(data).chords[0];self.assertIsNone(c.notes);self.assertEqual(c.pitches,[36,48,50,52,55])
        data['chords'][0]['notes']=[vars(Note(0,3840,p)) for p in (36,48,52,55,62)]
        c=Project.from_dict(data).chords[0];self.assertEqual([n.pitch for n in c.notes],[36,48,52,55,62])

    def test_reapplying_quality_or_pattern_and_dialog_remove_old_voicing(self):
        for action in ('quality:add2','pattern:block','dialog'):
            p=project();c=Chord(0,3840,quality='add2',notes=[Note(0,3840,p) for p in (36,48,52,55,62)]);p.chords=[c]
            if action=='dialog':
                d=ChordDialog(c,p);p.put_chord(d.value());d.deleteLater()
            else:change_chords(p,{c.id},action)
            self.assertEqual([n.pitch for n in p.chords[0].render_notes()],[36,48,50,52,55],action)

class RhythmTests(unittest.TestCase):
    def test_three_patterns_in_all_even_meters_match_independent_reference(self):
        for n in range(2,17,2):
            for d in (2,4,8,16):
                for pattern in ALTERNATING:
                    with self.subTest(n=n,d=d,pattern=pattern):
                        p=project(n,d);c=Chord(0,p.end,48,'add2',pattern=pattern,gate=.75,velocity=79)
                        p.put_chord(c);c=p.chords[0]
                        self.assertEqual(events(c),expected(pattern,n,d,2));p.validate()
                        self.assertEqual(analyze(c,p).pattern,pattern)
                        self.assertEqual(analyze_performed(c,p).pattern,pattern)

    def test_all_qualities_keep_complete_upper_chord_and_recognition(self):
        for quality in QUALITIES:
            for pattern in ALTERNATING:
                p=project();c=Chord(0,3840,48,quality,pattern=pattern);p.put_chord(c);c=p.chords[0]
                rescan_chord(p,c);self.assertTrue(c.recognized,(quality,pattern));self.assertEqual(c.quality,quality)
                expected_upper=set(c.pitches[1:]);onset=480 if pattern=='alternating_offbeat' else 0
                self.assertEqual({n.pitch for n in c.notes if n.start==onset and n.pitch>=48},expected_upper)
                self.assertEqual(analyze(c,p).pattern,pattern)

    def test_regeneration_resets_each_bar_and_crops_from_real_phase(self):
        p=project(4,8)
        for pattern in ALTERNATING:
            c=Chord(600,2500,48,'add2',pattern=pattern,gate=.75,velocity=79)
            actual=regenerate(c,c.start,c.end,p)
            reference=[]
            for t,d,pitch,v in expected(pattern,4,8,2):
                left=max(600,t);right=min(3100,t+d)
                if left<right:reference.append((left,right-left,pitch,v))
            self.assertEqual(events(actual),sorted(reference));self.assertEqual(analyze(actual,p).pattern,pattern)

    def test_odd_meters_disabled_in_menu_metadata_and_dialog(self):
        for n,d in ((3,4),(3,8),(5,2),(7,16)):
            p=project(n,d);c=Chord(0,p.end);p.chords=[c]
            dialog=ChordDialog(c,p)
            for pattern in ALTERNATING:
                self.assertFalse(supports(pattern,p,0));self.assertFalse(can_apply_pattern(p,[c],pattern))
                self.assertFalse(dialog.pattern.model().item(dialog.pattern.findData(pattern)).isEnabled())
                before=p.to_dict()
                with self.assertRaises(ValueError):change_chords(p,{c.id},'pattern:'+pattern)
                self.assertEqual(p.to_dict(),before)
            dialog.deleteLater()

    def test_equal_length_different_denominators_have_different_bass_pulses(self):
        p=project(2,4);q=project(4,8)
        for pattern in ALTERNATING:
            a=regenerate(Chord(0,1920,pattern=pattern),0,1920,p)
            b=regenerate(Chord(0,1920,pattern=pattern),0,1920,q)
            self.assertEqual([(n.start,n.pitch) for n in a.notes if n.pitch<48],[(0,36),(960,43)])
            self.assertEqual([(n.start,n.pitch) for n in b.notes if n.pitch<48],[(0,36),(480,43),(960,36),(1440,43)])

    def test_edits_progression_move_and_roundtrip_keep_pattern(self):
        for pattern in ALTERNATING:
            p=project(4,8,bars=4);p.put_chord(Chord(0,1920,pattern=pattern))
            c=p.chords[0];change_chords(p,{c.id},'quality:add2');c=p.chords[0]
            self.assertEqual(analyze(c,p).pattern,pattern)
            change_chords(p,{c.id},'root:5');self.assertEqual(analyze(c,p).pattern,pattern)
            moved=moved_chord(p,c,1920);self.assertEqual(analyze(moved,p).pattern,pattern)
            apply(p,c.id,'ImM7',keep_rhythm=True);self.assertEqual(analyze(p.chords[0],p).pattern,pattern)
            self.assertEqual(events(Project.from_dict(p.to_dict()).chords[0]),events(p.chords[0]))
            with tempfile.TemporaryDirectory(dir='tmp') as folder:
                from popscore.midi_import import read_midi
                path=Path(folder)/'pattern.mid';export_midi(p,path,which='chords')
                notes=[n for track in read_midi(path).tracks for n in track.notes]
                self.assertEqual(sorted((n.start,n.duration,n.pitch,n.velocity) for n in notes),events(p.chords[0]))

    def test_inferred_gate_uses_bass_and_upper_units(self):
        for d in (2,8,16):
            p=project(4,d)
            for pattern in ALTERNATING:
                c=regenerate(Chord(0,p.end,pattern=pattern,gate=.6),0,p.end,p);c.gate=.9
                actual=analyze(c,p);self.assertIsNotNone(actual);self.assertAlmostEqual(actual.gate,.6)

class OctaveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='tmp');self.paths=patch('popscore.app.user_data_dir',return_value=Path(self.temp.name));self.paths.start()
        self.w=MainWindow(project());self.w.timer.stop();self.w.autosave.stop();self.w.change_language('zh',False);self.w.show()
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.paths.stop();self.temp.cleanup()
    def select(self,role):
        w=self.w;p=project();p.notes=[Note(0,480,60,83),Note(960,240,64,72)]
        p.chords=[Chord(0,p.end,notes=[Note(0,480,60,81),Note(960,240,64,73)])];w.replace_project(p)
        r=w.roll if role=='melody' else w.harmony_window.roll
        pane=w.melody_window if role=='melody' else w.harmony_window
        w.show_roll_in_place(pane);r.edit_target='notes';r.selected_ids={n.id for n in r.notes}
        pane.window().activateWindow();r.setFocus();APP.processEvents();return r,pane
    def test_menu_moves_both_rolls_and_undo_preserves_time_velocity(self):
        for role in ('melody','harmony'):
            r,_=self.select(role);before=[(n.start,n.duration,n.pitch,n.velocity) for n in r.notes]
            menu=QMenu();r.selection_menu(menu,0);action=next(a for a in menu.actions() if a.data()=='octave_up')
            self.assertEqual(action.shortcut().toString(),'Ctrl+Up');action.trigger()
            self.assertEqual([(n.start,n.duration,n.pitch,n.velocity) for n in r.notes],[(t,d,p+12,v) for t,d,p,v in before])
            self.w.undo();self.assertEqual([(n.start,n.duration,n.pitch,n.velocity) for n in r.notes],before);menu.deleteLater()
    def test_actual_keys_work_in_docked_and_floating_rolls(self):
        for role in ('melody','harmony'):
            for floating in (False,True):
                r,pane=self.select(role);pane.setFloating(floating);pane.show();pane.window().activateWindow();r.setFocus();APP.processEvents()
                QTest.keyClick(r,Qt.Key.Key_Up,Qt.KeyboardModifier.ControlModifier)
                self.assertEqual([n.pitch for n in r.notes],[72,76],(role,floating))
                QTest.keyClick(r,Qt.Key.Key_Down,Qt.KeyboardModifier.ControlModifier)
                self.assertEqual([n.pitch for n in r.notes],[60,64])
    def test_custom_binding_shows_in_floating_menu_and_old_conflicts_survive(self):
        bindings=load_bindings({'up':'Ctrl+Up'});validate(bindings)
        self.assertEqual(bindings['up'],'Ctrl+Up');self.assertEqual(bindings['octave_up'],'')
        r,pane=self.select('harmony');pane.setFloating(True);self.w.keybindings['octave_up']='Alt+Up';self.w.keybindings['scale_up_alt']=''
        menu=QMenu();r.selection_menu(menu,0)
        self.assertEqual(next(a for a in menu.actions() if a.data()=='octave_up').shortcut().toString(),'Alt+Up');menu.deleteLater()
        pane.show();pane.activateWindow();r.setFocus();APP.processEvents();QTest.keyClick(r,Qt.Key.Key_Up,Qt.KeyboardModifier.AltModifier)
        self.assertEqual([n.pitch for n in r.notes],[72,76])
    def test_out_of_range_is_atomic_and_menu_is_disabled(self):
        r,_=self.select('melody');self.w.project.notes[1].pitch=108;self.w.refresh();before=self.w.project.to_dict()
        menu=QMenu();r.selection_menu(menu,0)
        self.assertFalse(next(a for a in menu.actions() if a.data()=='octave_up').isEnabled());menu.deleteLater()
        with patch('popscore.app.QMessageBox.warning') as warning:self.w.note_command(r,'chromatic:12');warning.assert_called_once()
        self.assertEqual(self.w.project.to_dict(),before)
    def test_text_input_and_chord_selection_do_not_transpose_notes(self):
        r,_=self.select('melody');before=self.w.project.to_dict()
        edit=QLineEdit(self.w);edit.show();edit.setFocus();APP.processEvents()
        QTest.keyClick(edit,Qt.Key.Key_Up,Qt.KeyboardModifier.ControlModifier);self.assertEqual(self.w.project.to_dict(),before)
        r.edit_target='chords';r.selected_chords={self.w.project.chords[0].id};r.setFocus();APP.processEvents()
        self.w.editor_key_command('octave_up');self.assertEqual(self.w.project.to_dict(),before);edit.deleteLater()

if __name__=='__main__':unittest.main()

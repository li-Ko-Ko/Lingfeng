"""Context-aware pitch movement and one default chord lane per window."""
import os,copy,sys,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMenu,QLineEdit
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from lingfeng.ui.main_window import MainWindow
from lingfeng.music.model import Project, Chord, Note, MODES, QUALITIES, PATTERNS
from lingfeng.music.recognition import recognize, chord_inversion
from lingfeng.music.chord_operations import diatonic_chord, can_move_diatonic, change_chords
from lingfeng.ui.keybindings import normalized, load_bindings

APP=QApplication.instance() or QApplication([])

class MusicTests(unittest.TestCase):
    def test_recognizes_root_position_and_each_inversion(self):
        for quality in ('','m','7','maj7','m7','m7b5','dim','9','maj9'):
            for i,interval in enumerate(QUALITIES[quality]):
                chord=Chord(0,3840,48,quality,None if i==0 else interval%12)
                self.assertEqual(chord_inversion(chord),i)
                result=next(c for c in recognize(chord.pitches) if c.root==0 and c.quality==quality)
                self.assertEqual(result.inversion,i)
        self.assertIsNone(chord_inversion(Chord(0,3840,48,'',1)))

    def test_I_to_ii_resets_bass_and_preserves_other_custom_attributes(self):
        p=Project();c=Chord(480,3840,48,'',4,pattern='quarters',gate=.72,velocity=77,octave=1,flat=True,
            notes=[Note(t,d,k,v,flat=True) for t,d,k,v in [(0,240,52,70),(240,480,60,83),(0,960,67,90),(960,480,72,66),(1200,720,64,101)]])
        before=copy.deepcopy(c);moved=diatonic_chord(c,p.context_at(0),1)
        self.assertEqual((moved.root%12,moved.quality,moved.bass,chord_inversion(moved)),(2,'m',None,0))
        for key in ('id','start','duration','pattern','gate','velocity','octave','flat'):self.assertEqual(getattr(moved,key),getattr(c,key))
        self.assertEqual([(n.id,n.start,n.duration,n.velocity,n.flat) for n in moved.notes],[(n.id,n.start,n.duration,n.velocity,n.flat) for n in c.notes])
        self.assertEqual([n.pitch for n in moved.notes],[50,62,69,74,65]);self.assertEqual(c,before)
        returned=diatonic_chord(moved,p.context_at(0),-1);self.assertEqual(returned.name,'C');self.assertEqual([n.pitch for n in returned.notes],[48,60,67,72,64])

    def test_all_modes_diatonic_triads_and_sevenths_restore_root_bass(self):
        for mode,scale in MODES.items():
            p=Project();p.set_context([[0,p.end]],tonic=48,mode=mode)
            for degree in range(7):
                for count in (3,4):
                    intervals=tuple((scale[(degree+2*i)%7]+12*((degree+2*i)//7)-scale[degree]) for i in range(count))
                    quality=next(q for q,tones in QUALITIES.items() if set(tones)==set(intervals))
                    for inversion in range(count):
                        root=48+scale[degree];c=Chord(0,3840,root,quality,None if inversion==0 else (root+intervals[inversion])%12)
                        for delta in (-1,1):
                            with self.subTest(mode=mode,degree=degree,count=count,inversion=inversion,delta=delta):
                                moved=diatonic_chord(c,p.context_at(0),delta)
                                self.assertEqual(chord_inversion(moved),0)
                                self.assertEqual(moved.root%12,scale[(degree+delta)%7])
                                self.assertTrue(all((n.pitch-48)%12 in scale for n in moved.render_notes()))

    def test_patterns_and_atomic_rejection(self):
        p=Project()
        for pattern in PATTERNS:
            c=Chord(0,7680,48,'',4,pattern=pattern,gate=.77)
            moved=diatonic_chord(c,p.context_at(0),1)
            self.assertEqual([(n.start,n.duration,n.velocity) for n in moved.render_notes()],[(n.start,n.duration,n.velocity) for n in c.render_notes()])
            self.assertEqual(moved.pattern,pattern)
        bad=[Chord(0,3840,48,'7'),Chord(0,3840,49),Chord(0,3840,notes=[],recognized=False),Chord(0,3840,48,'',1)]
        for c in bad:self.assertFalse(can_move_diatonic(p,[c],1))
        p.chords=[Chord(0,3840),bad[0]];before=p.to_dict()
        with self.assertRaises(ValueError):change_chords(p,{c.id for c in p.chords},'diatonic:1')
        self.assertEqual(p.to_dict(),before)

    def test_each_chord_uses_local_key_and_limits_pitch(self):
        p=Project();p.set_markers([1],50,'Ionian',4,4);p.chords=[Chord(0,3840),Chord(3840,3840,50)]
        change_chords(p,{c.id for c in p.chords},'diatonic:1');self.assertEqual([(c.root%12,c.quality) for c in p.chords],[(2,'m'),(4,'m')])
        p.validate();p.chords=[Chord(0,3840,notes=[Note(0,3840,k) for k in (100,103,108)])]
        self.assertFalse(can_move_diatonic(p,p.chords,1))

    def test_short_generated_arpeggio_and_silent_offbeat_restore_root_bass(self):
        p=Project()
        for pattern in ('up','down','offbeat'):
            c=Chord(0,240,48,'',4,pattern=pattern)
            moved=diatonic_chord(c,p.context_at(0),1)
            self.assertIsNone(moved.notes);self.assertEqual(moved.name,'Dm');self.assertIsNone(moved.bass)
            returned=diatonic_chord(moved,p.context_at(0),-1);self.assertEqual(returned.name,'C');self.assertEqual(returned.pattern,c.pattern)

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.errors=[];self.hook=patch.object(sys,'excepthook',lambda typ,value,tb:self.errors.append(str(value)));self.hook.start()
        self.warning=patch('lingfeng.ui.main_window.QMessageBox.warning',side_effect=AssertionError('Unexpected warning'));self.warning.start()
        p=Project();p.notes=[Note(960,480,60)];p.chords=[Chord(0,3840,48,'',4),Chord(3840,3840,55)]
        self.w=MainWindow(p);self.w.change_language('zh',False);self.w.keybindings=normalized({});self.w.show();self.w.resize(1200,850);self.w.timer.stop();self.w.autosave.stop()
        for b in self.w.mute_buttons.values():b.setChecked(True)
        QTest.qWait(30)
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.hook.stop();self.warning.stop();self.assertFalse(self.errors)
    def test_w_s_semitones_alt_w_s_diatonic_menu_and_text_focus(self):
        w=self.w;r=w.roll;r.selected_ids={w.project.notes[0].id};r.setFocus();w.activateWindow();APP.processEvents()
        QTest.keyClick(r,Qt.Key.Key_W);self.assertEqual(w.project.notes[0].pitch,61)
        QTest.keyClick(r,Qt.Key.Key_S);self.assertEqual(w.project.notes[0].pitch,60)
        QTest.keyClick(r,Qt.Key.Key_W,Qt.KeyboardModifier.AltModifier);self.assertEqual(w.project.notes[0].pitch,62)
        menu=QMenu();r.selection_menu(menu,0);next(a for a in menu.actions() if a.text()=='降低半音').trigger();self.assertEqual(w.project.notes[0].pitch,61)
        next(a for a in menu.actions() if a.text().split('\t')[0]=='调内下移一级').trigger();self.assertEqual(w.project.notes[0].pitch,60)
        field=QLineEdit(w);field.show();field.setFocus();APP.processEvents();QTest.keyClicks(field,'ws');self.assertEqual(field.text(),'ws');self.assertEqual(w.project.notes[0].pitch,60)
        self.assertEqual(load_bindings({'up':'I'})['scale_up'],'Alt+W')
        migrated=load_bindings({'up':'Alt+W','left':'J'});self.assertEqual(migrated['up'],'Alt+W');self.assertEqual(migrated['left'],'J');self.assertEqual(migrated['scale_up'],'')
    def test_chord_keys_menu_and_live_undo(self):
        w=self.w;c=w.project.chords[0];lane=w.chord_lane;r=lane.editor;lane.selection_event({c.id});r.edit_target='chords';w.activateWindow();lane.setFocus();APP.processEvents()
        w.toggle_play();worker=w.transport.thread;clock=w.transport.start_time
        QTest.keyClick(lane,Qt.Key.Key_W);self.assertEqual((w.project.chords[0].name,chord_inversion(w.project.chords[0])),('C#',0))
        self.assertIs(w.transport.thread,worker);self.assertEqual(w.transport.start_time,clock)
        w.undo();self.assertEqual(w.project.chords[0].name,'C/E');w.redo();self.assertEqual(w.project.chords[0].name,'C#');w.stop()
        menu=lane.context_menu(QPoint(round(lane.x_at(960)),25));self.assertTrue(menu.move_menu.actions()[0].isEnabled())
        next(a for a in menu.move_menu.actions() if a.text()=='根音降低半音（恢复原位）').trigger();self.assertEqual(w.project.chords[0].name,'C')
        w.project.chords[0].quality='7';w.project.chords[0].notes=None;w.refresh();menu=lane.context_menu(QPoint(round(lane.x_at(960)),25));self.assertFalse(next(a for a in menu.move_menu.actions() if a.text().split('\t')[0]=='调内上移一级').isEnabled());self.assertTrue(menu.move_menu.actions()[0].isEnabled())
    def test_layout_defaults_manual_override_close_redock_and_language(self):
        w=self.w;show=lambda key:w.visibility_actions[key].isChecked()
        self.assertTrue(show('chords'));w.open_harmony();self.assertFalse(show('chords'));self.assertTrue(show('harmony'))
        w.visibility_actions['chords'].setChecked(True);w.refresh();w.mount_panels();self.assertTrue(show('chords'))
        w.change_language('en',False);self.assertTrue(show('chords'))
        w.harmony_window.setFloating(True);self.assertTrue(show('chords'))
        w.harmony_window.close();QTest.qWait(20);self.assertTrue(w.harmony_window.isFloating());self.assertFalse(show('harmony'));self.assertTrue(show('chords'));self.assertFalse(w.harmony_window.isVisible())
        w.visibility_actions['harmony'].setChecked(True);self.assertFalse(w.harmony_window.isFloating());self.assertTrue(show('harmony'));self.assertFalse(show('chords'));self.assertTrue(w.harmony_window.isVisible())
        w.harmony_window.setFloating(True);w.melody_window.setFloating(True);self.assertTrue(show('chords'));self.assertTrue(w.roll.panels['chords'])
        w.visibility_actions['chords'].setChecked(False);self.assertTrue(w.roll.panels['chords'])
        w.melody_window.setFloating(False);self.assertTrue(show('chords'))
        w.harmony_window.setFloating(False);self.assertFalse(show('chords'))
        w.visibility_actions['harmony'].setChecked(False);self.assertTrue(show('chords'))
    def test_only_nearest_lane_controls_melody_highlight(self):
        w=self.w;c,d=w.project.chords;main=w.chord_lane;h=w.harmony_window.roll.lane;m=w.roll.lane
        main.hover_event(c.id);self.assertEqual(w.roll.chord_highlights,{c.id})
        w.open_harmony();h.hover_event(d.id);self.assertEqual(w.roll.chord_highlights,{d.id})
        main.hover_event(c.id);self.assertEqual(w.roll.chord_highlights,{d.id})
        w.visibility_actions['chords'].setChecked(True);self.assertEqual(w.roll.chord_highlights,{c.id})
        h.selection_event({d.id});self.assertEqual(w.roll.chord_highlights,{c.id})
        w.melody_window.setFloating(True);main.hover_event(c.id);h.hover_event(d.id);self.assertFalse(w.roll.chord_highlights)
        m.hover_event(c.id);self.assertEqual(w.roll.chord_highlights,{c.id})
        w.harmony_window.setFloating(True);h.hover_event(d.id);self.assertFalse(w.roll.chord_highlights)
        m.selection_event({c.id});self.assertEqual(w.roll.chord_highlights,{c.id});self.assertNotEqual(w.main_roll.selected_chords,{c.id})
        m.hover_event('');self.assertEqual(w.roll.chord_highlights,{c.id})

if __name__=='__main__':unittest.main()

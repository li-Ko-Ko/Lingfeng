"""Modal degree identity, compact chord hints and local modal editing."""
import copy,os,re,unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import Qt,QPoint,QPointF
from PySide6.QtGui import QImage,QPainter
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QDialog
from lingfeng.music.model import Project, Chord, Note, Context, Measure, MODES, MAJOR, SECTIONS, spelling, degree_text
from lingfeng.music.chord_operations import chord_details, roman_label
from lingfeng.music.rhythm import analyze, analyze_performed, label
from lingfeng.music.progressions import DEFAULT_PRESETS; from lingfeng.ui.progression_dialogs import ProgressionDialog
from lingfeng.ui.dialogs import MarkerDialog, ChordDialog
from lingfeng.ui.piano_roll import PianoRoll, KEY_W
from lingfeng.ui.main_window import MainWindow
from lingfeng.engraving.notation import ScoreLayout, PAPER_W, PAPER_H
from lingfeng.ui.fonts import ensure_fonts
import lingfeng.ui.theme as theme
APP=QApplication.instance() or QApplication([]);ensure_fonts()

def plain(html):
    return re.sub('<[^>]+>',' ',html).replace('&nbsp;',' ')

class MusicalTests(unittest.TestCase):
    def test_every_mode_has_each_degree_once_for_both_preferences_and_all_tonics(self):
        for mode,offsets in MODES.items():
            for tonic in range(48,60):
                for flat in (False,True):
                    values=[spelling(tonic+o,tonic,flat,mode) for o in offsets]
                    self.assertEqual([x[0] for x in values],list(range(1,8)))
                    self.assertEqual([x[1] for x in values],[o-MAJOR[i] for i,o in enumerate(offsets)])
                    self.assertEqual(degree_text(tonic+6,tonic,flat,False,'Lydian'),'#4')
        self.assertEqual(degree_text(51,48,False,False,'Aeolian'),'b3')
        self.assertEqual(degree_text(49,48,True,False,'Ionian'),'b2')

    def test_unknown_chord_never_advertises_a_known_rhythm(self):
        p=Project()
        for notes in (None,[Note(0,960,60),Note(0,960,61)],[]):
            c=Chord(0,960,notes=notes,recognized=False)
            self.assertIsNone(analyze(c,p));self.assertIsNone(analyze_performed(c,p));self.assertEqual(label(c,p),'未知节奏型')
            c.custom_rhythm=True;self.assertEqual(label(c,p),'未知节奏型')
        c=Chord(0,960,recognized=True,custom_rhythm=True);self.assertEqual(label(c,p),'自定义（锁定）')

    def test_recognized_hint_uses_chord_degrees_and_no_octaves_or_duplicates(self):
        p=Project();c=Chord(0,3840,53,'maj7');text=plain(chord_details(p,c,compact=True))
        for value in ('1: F','3: A','5: C','7: E'):self.assertEqual(text.count(value),1)
        self.assertNotIn('F4',text);self.assertNotIn('4: F',text)
        c=Chord(0,3840,48,'m9');text=plain(chord_details(p,c,compact=True))
        for value in ('b3: Eb','b7: Bb','9: D'):self.assertIn(value,text)

    def test_unknown_hint_is_low_to_high_unique_pitch_classes(self):
        p=Project();c=Chord(0,960,notes=[Note(0,960,48),Note(0,960,59),Note(0,960,60)],recognized=False)
        text=chord_details(p,c,compact=True)
        self.assertIn('C &nbsp; B',text);self.assertNotIn('1: C',text);self.assertNotIn('C4',text)

    def test_score_hint_preserves_actual_octaves_and_modal_contexts(self):
        p=Project();p.contexts=[Context(0,960,48,'Ionian'),Context(960,p.end,48,'Lydian')]
        c=Chord(0,1920,54,'dim');full=chord_details(p,c);compact=chord_details(p,c,compact=True)
        self.assertIn('F#',full);self.assertIn('Lydian',full);self.assertIn('♯iv',roman_label(p,c,True))
        self.assertIn(' = ',full);self.assertNotIn('F#4',compact)

    def test_section_migration_is_title_case_without_combining_equal_neighbors(self):
        p=Project();p.measures[0]=Measure(section='verse');p.measures[1]=Measure(section='VERSE')
        q=Project.from_dict(p.to_dict());self.assertEqual(q.sections()[:2],[('Verse',0,1),('Verse',1,8)])
        self.assertTrue(all(s[0].isupper() and s[1:].islower() for s in SECTIONS))
        self.assertEqual(Measure(section='A · 主题').section,'A · 主题')

class InterfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prefs=patch.object(MainWindow,'save_preferences');cls.prefs.start()
        cls.w=MainWindow(Project());cls.w.change_language('zh',False);cls.w.resize(1100,850);cls.w.show();cls.w.timer.stop();cls.w.autosave.stop()
    @classmethod
    def tearDownClass(cls):
        cls.w.dirty=False;cls.w.close();cls.w.deleteLater();APP.processEvents();cls.prefs.stop()
    def setUp(self):
        w=self.w;w.replace_project(Project());w.switch_workspace('compose');w.melody_window.setFloating(False);w.harmony_window.setFloating(False)
        w.visibility_actions['melody'].setChecked(True);w.visibility_actions['harmony'].setChecked(False);theme.set_accidental_preference('sharp');APP.processEvents()
    def test_progression_displays_names_in_starting_key_without_repeated_roman_field(self):
        p=Project();p.contexts=[Context(0,p.end,53)];p.chords=[Chord(0,3840,53)]
        d=ProgressionDialog(p,p.chords[0].id,DEFAULT_PRESETS);d.show();APP.processEvents()
        d.preset.setCurrentIndex(d.preset.findData('I V vi IV'));self.assertEqual(d.resolved.text(),'F – C – Dm – Bb');self.assertFalse(d.sequence.isVisible())
        d.preset.setCurrentIndex(d.preset.findData('ii7 V7 Imaj7'));self.assertEqual(d.resolved.text(),'Gm7 – C7 – Fmaj7');d.close();d.deleteLater()
    def test_marker_choices_use_preference_and_keep_mode_value_separate(self):
        p=Project();p.contexts[0].mode='Lydian';theme.set_accidental_preference('flat')
        d=MarkerDialog(p,0)
        self.assertIn('Db4',d.tonic.itemText(d.tonic.findData(61)))
        self.assertIn('#4:Gb',d.mode.itemText(d.mode.findData('Lydian')))
        self.assertEqual(d.value()['mode'],'Lydian')
        d.tonic.setCurrentIndex(d.tonic.findData(53));d.mode.setCurrentIndex(d.mode.findData('Aeolian'))
        self.assertIn('b3:Ab',d.mode.currentText());self.assertEqual(d.value()['tonic'],53);d.deleteLater()
    def test_roll_and_score_keep_lydian_sharp_four_under_flat_preference(self):
        p=Project();p.contexts[0].mode='Lydian';p.notes=[Note(0,960,54,flat=True)]
        self.w.replace_project(p);theme.set_accidental_preference('flat')
        self.assertEqual(self.w.roll.note_degree_label(54,0,960),'♯4')
        layout=ScoreLayout(p);img=QImage(PAPER_W,PAPER_H,QImage.Format.Format_ARGB32);painter=QPainter(img);layout.draw(painter,0);painter.end()
        self.assertIn('4',[s[0] for s in layout.glyph_sizes]);self.assertNotIn('5',[s[0] for s in layout.glyph_sizes if s[0]!='0'])
    def test_draw_cannot_marquee_left_right_modifiers_or_grid_line(self):
        r=self.w.roll;r.tool='draw';r.zoom=200;r.update_ranges();r.center_pitch(60);APP.processEvents()
        for button in (Qt.MouseButton.LeftButton,Qt.MouseButton.RightButton):
            for modifier in (Qt.KeyboardModifier.NoModifier,Qt.KeyboardModifier.ControlModifier,Qt.KeyboardModifier.ShiftModifier):
                pos=QPoint(round(r.x_at(960)),round(r.y_at(60)+r.row_height/2))
                QTest.mousePress(r.viewport(),button,modifier,pos);r.begin_marquee();QTest.mouseMove(r.viewport(),pos+QPoint(45,25))
                self.assertIsNone(r.marquee);self.assertTrue(r.drag is None or r.drag[0]!='marquee')
                QTest.mouseRelease(r.viewport(),button,modifier,pos+QPoint(45,25))
                if getattr(r,'active_menu',None):r.active_menu.close()
        r.tool='smart';QTest.mousePress(r.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,pos);r.begin_marquee()
        self.assertIsNotNone(r.marquee);QTest.mouseRelease(r.viewport(),Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier,pos)
    def test_floating_chord_and_marker_dialogs_stay_with_origin_and_history(self):
        w=self.w;w.project.chords=[Chord(0,3840)];w.refresh();w.visibility_actions['harmony'].setChecked(True);w.harmony_window.setFloating(True)
        r=w.harmony_window.roll;w.harmony_window.show();w.harmony_window.activateWindow();r.setFocus();APP.processEvents()
        parents=[]
        def accept_chord(d):parents.append(d.parentWidget());d.quality.setCurrentIndex(d.quality.findData('m'));return QDialog.DialogCode.Accepted
        with patch.object(ChordDialog,'exec',accept_chord),patch.object(w.transport,'audition'):
            r.chordRequested.emit(w.project.chords[0].id,0)
        self.assertIs(parents[-1],w.harmony_window);self.assertEqual(w.undo_history[-1].location['surface'],'harmony')
        self.assertIs(APP.activeWindow(),w.harmony_window)
        def accept_marker(d):parents.append(d.parentWidget());d.mode.setCurrentIndex(d.mode.findData('Lydian'));return QDialog.DialogCode.Accepted
        with patch.object(MarkerDialog,'exec',accept_marker):r.contextRequested.emit([[0,3840]])
        self.assertIs(parents[-1],w.harmony_window);self.assertEqual(w.project.context_at(0).mode,'Lydian')
        self.assertIs(APP.activeWindow(),w.harmony_window);self.assertEqual(w.undo_history[-1].location['surface'],'harmony')
        with patch.object(MarkerDialog,'exec',return_value=QDialog.DialogCode.Rejected):r.contextRequested.emit([[0,3840]])
        self.assertIs(APP.activeWindow(),w.harmony_window)

if __name__=='__main__':unittest.main()

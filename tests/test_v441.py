"""One modal display policy and four-field chord-edit memory."""
import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPoint,QEvent
from PySide6.QtWidgets import QApplication,QDialog
from lingfeng.music.model import Project, Chord, Context, MODES, Note
import lingfeng.ui.theme as theme
from lingfeng.ui.dialogs import ChordDialog, chord_edit_defaults
from lingfeng.ui.progression_dialogs import CaptureProgressionDialog, ProgressionDialog, ProgressionManagerDialog
from lingfeng.ui.piano_roll import PianoRoll
from lingfeng.ui.main_window import MainWindow
APP=QApplication.instance() or QApplication([])

EXPECTED={
 'Ionian':('1 #1 2 #2 3 4 #4 5 #5 6 #6 7','1 b2 2 b3 3 4 b5 5 b6 6 b7 7'),
 'Dorian':('1 #1 2 b3 3 4 #4 5 #5 6 b7 7','1 b2 2 b3 3 4 b5 5 b6 6 b7 7'),
 'Phrygian':('1 b2 2 b3 3 4 #4 5 b6 6 b7 7','1 b2 2 b3 3 4 b5 5 b6 6 b7 7'),
 'Lydian':('1 #1 2 #2 3 4 #4 5 #5 6 #6 7','1 b2 2 b3 3 4 #4 5 b6 6 b7 7'),
 'Mixolydian':('1 #1 2 #2 3 4 #4 5 #5 6 b7 7','1 b2 2 b3 3 4 b5 5 b6 6 b7 7'),
 'Aeolian':('1 #1 2 b3 3 4 #4 5 b6 6 b7 7','1 b2 2 b3 3 4 b5 5 b6 6 b7 7'),
}
RECIPE=[dict(name='Cadence',sequence='ii V I')]

def project(tonic=48,mode='Aeolian'):
    p=Project();p.contexts=[Context(0,p.end,tonic,mode)];p.chords=[Chord(0,3840,55,'m',bass=10)]
    return p

def labels(combo):return [combo.itemText(i).split(' · ')[0] for i in range(combo.count())]
def ascii_degree(text):return text.replace('♯','#').replace('♭','b')

class ModalTests(unittest.TestCase):
    def tearDown(self):theme.set_accidental_preference('sharp');APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    def test_all_four_surfaces_match_approved_tables_in_all_keys(self):
        self.assertEqual(set(EXPECTED),set(MODES))
        for mode,expected in EXPECTED.items():
            for pref in ('sharp','flat'):
                theme.set_accidental_preference(pref);wanted=expected[pref=='flat'].split()
                for tonic in range(48,60):
                    with self.subTest(mode=mode,preference=pref,tonic=tonic):
                        p=project(tonic,mode);c=p.chords[0];ids={c.id}
                        edit=ChordDialog(c,p);capture=CaptureProgressionDialog(p,ids);apply=ProgressionDialog(p,c.id,RECIPE)
                        search=ProgressionManagerDialog(RECIPE,tonic=tonic,mode=mode)
                        try:
                            for combo in (edit.root,edit.bass,capture.tonic,apply.tonic,search.tonic):
                                self.assertEqual(labels(combo),wanted)
                                self.assertEqual([combo.itemData(i) for i in range(12)],[(tonic+i)%12 for i in range(12)])
                            actual=[ascii_degree(PianoRoll.note_degree_label(type('Roll',(),{'project':p})(),tonic+i,0,960)) for i in range(12)]
                            self.assertEqual(actual,wanted)
                            self.assertEqual(edit.root.currentIndex(),0);self.assertEqual(edit.bass.currentIndex(),0)
                        finally:
                            for d in (edit,capture,apply,search):d.close();d.deleteLater()
                    APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    def test_anchor_mode_is_retained_when_selecting_another_tonic(self):
        p=project();d=CaptureProgressionDialog(p,{p.chords[0].id})
        try:
            d.tonic.setCurrentIndex(d.tonic.findData(5));self.assertEqual(d.tonic.currentText(),'4 · F')
            self.assertEqual(labels(d.tonic),EXPECTED['Aeolian'][0].split())
        finally:d.close();d.deleteLater()
    def test_chord_root_bass_memory_and_one_way_binding(self):
        p=project(50,'Dorian');c=p.chords[0];c.octave=2;before=copy.deepcopy(c)
        legacy=dict(root=8,bass=11,quality='mM7',pattern='quarters',gate=65,velocity=83,octave=-1,regenerate=False)
        d=ChordDialog(c,p,defaults=legacy)
        try:
            self.assertEqual(d.options(),dict(quality='mM7',pattern='quarters',gate=65,velocity=83))
            self.assertEqual((d.root.currentData(),d.bass.currentData()),(2,2))
            self.assertEqual(d.octave.value(),2);self.assertTrue(d.regenerate.isChecked());self.assertIsNone(d.value().bass)
            self.assertEqual(d.bass.count(),12);self.assertEqual(d.bass.findData(None),-1)
            for root,bass in ((7,11),(5,8),(2,9)):
                d.root.setCurrentIndex(d.root.findData(root));self.assertEqual(d.bass.currentData(),root)
                d.bass.setCurrentIndex(d.bass.findData(bass));self.assertEqual(d.root.currentData(),root)
                self.assertEqual(d.value().bass,bass)
            d.quality.setCurrentIndex(d.quality.findData('7'));self.assertEqual(d.bass.currentData(),9)
            d.root.setCurrentIndex(d.root.findData(0));self.assertEqual(d.bass.currentData(),0);self.assertIsNone(d.value().bass)
            d.reject();self.assertEqual(c,before)
        finally:d.close();d.deleteLater()
    def test_start_reorders_labels_and_preserves_current_explicit_pitches(self):
        p=project();p.contexts=[Context(0,3840,48,'Aeolian'),Context(3840,p.end,53,'Lydian')]
        d=ChordDialog(p.chords[0],p)
        try:
            d.root.setCurrentIndex(d.root.findData(11));d.bass.setCurrentIndex(d.bass.findData(6));d.start.setValue(4)
            self.assertEqual(d.root.itemText(0),'1 · F');self.assertEqual(labels(d.root),EXPECTED['Lydian'][0].split())
            self.assertEqual((d.root.currentData(),d.bass.currentData()),(11,6))
        finally:d.close();d.deleteLater()
    def test_only_four_fields_survive_preferences_migration(self):
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            path=Path(folder);legacy=dict(root=8,bass=11,quality='m7',pattern='up',gate=60,velocity=75,octave=2,regenerate=False)
            (path/'preferences.json').write_text(json.dumps(dict(chord_edit_options=legacy)),'utf-8')
            with patch('lingfeng.ui.main_window.user_data_dir',return_value=path):
                w=MainWindow(project());w.timer.stop();w.autosave.stop()
                try:
                    expected=dict(quality='m7',pattern='up',gate=60,velocity=75)
                    self.assertEqual(w.chord_edit_options,expected);w.save_preferences()
                    self.assertEqual(json.loads((path/'preferences.json').read_text('utf-8'))['chord_edit_options'],expected)
                finally:w.dirty=False;w.close();w.deleteLater()
            APP.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.assertEqual(chord_edit_defaults(None),{})
    def test_context_menus_and_search_use_anchor_mode_and_global_preference(self):
        p=project(53,'Aeolian')
        with patch.object(MainWindow,'save_preferences'):
            w=MainWindow(p);w.timer.stop();w.autosave.stop();w.change_language('zh',False)
            try:
                for preference in ('sharp','flat'):
                    theme.set_accidental_preference(preference);wanted=EXPECTED['Aeolian'][preference=='flat'].split()
                    for roll in (w.roll,w.harmony_window.roll):
                        menu=roll.lane.context_menu(QPoint(round(roll.lane.x_at(100)),18))
                        try:
                            for sub in (menu.root_menu,menu.bass_menu):
                                self.assertEqual([a.text().split(' · ')[0] for a in sub.actions()],wanted)
                                self.assertEqual([a.data() for a in sub.actions()],[(5+i)%12 for i in range(12)])
                        finally:menu.deleteLater()
                    def inspect(d):
                        self.assertEqual(labels(d.tonic),wanted);return QDialog.DialogCode.Rejected
                    with patch.object(ProgressionManagerDialog,'exec',inspect):
                        w.progression_settings();w.search_progressions({p.chords[0].id},w.roll)
            finally:w.dirty=False;w.close();w.deleteLater()

if __name__=='__main__':unittest.main()

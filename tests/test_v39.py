"""Chord defaults, onset-key ordering and compatible quality migration."""
import copy,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication,QDialog
from lingfeng.ui.main_window import MainWindow
from lingfeng.music.model import Project, Chord, Context, Measure, Note, MODES, PATTERNS, QUALITIES, PPQ
from lingfeng.ui.dialogs import ChordDialog
from lingfeng.music.chord_operations import quality_items, set_quality_order, chord_details, contextual_chord_name
from lingfeng.music.progressions import capture, resolve, make_preset, apply
from lingfeng.music.recognition import recognize
from lingfeng.platform.i18n import set_language

APP=QApplication.instance() or QApplication([])

def events(c):return [(n.start,n.duration,n.pitch,n.velocity,n.id) for n in c.render_notes()]

class QualityTests(unittest.TestCase):
    def tearDown(self):set_quality_order([]);set_language('zh')

    def test_new_qualities_generate_recognize_and_spell(self):
        p=Project()
        for quality,intervals,labels in [('mM7',(0,3,7,11),('1: C','b3: Eb','5: G','7: B')),
                                         ('add2',(0,2,4,7),('1: C','2: D','3: E','5: G'))]:
            c=Chord(0,PPQ,48,quality)
            self.assertEqual(QUALITIES[quality],intervals)
            self.assertEqual(c.pcs,set(intervals))
            self.assertIn((0,quality),[(x.root,x.quality) for x in recognize(c.pitches)])
            hint=chord_details(p,c,compact=True)
            for label in labels:self.assertIn(label,hint)
            self.assertEqual(contextual_chord_name(p,c),'C'+quality)
        self.assertEqual(Chord(0,PPQ,48,'maj9').pcs,{0,2,4,7,11})
        self.assertNotIn('add9',QUALITIES)

    def test_progression_capture_apply_and_inversions(self):
        for quality in ('mM7','add2'):
            for tonic in range(12):
                for bass in (None,*QUALITIES[quality]):
                    p=Project();p.contexts=[Context(0,p.end,48+tonic)]
                    c=Chord(0,PPQ,48+tonic,quality,None if bass is None else (tonic+bass)%12);p.chords=[c]
                    recipe=capture(p,{c.id});actual=resolve(recipe,tonic)
                    self.assertEqual((actual.quality,actual.bass,actual.root),(c.quality,c.bass,c.root))
                    apply(p,c.id,recipe,keep_rhythm=False)
                    self.assertEqual(p.chords[0].pcs,c.pcs);p.validate()
        self.assertEqual(Chord(0,PPQ,48,'mM7').roman(48),'iM7')
        self.assertEqual(resolve('ImM7',0).quality,'mM7')

    def test_legacy_generated_add9_uses_close_position_in_all_patterns(self):
        for pattern in PATTERNS:
            for bass in (None,2,4):
                with self.subTest(pattern=pattern,bass=bass):
                    p=Project();c=Chord(480,3*PPQ,48,'add2',bass,pattern=pattern,gate=.7,velocity=83,octave=1)
                    p.chords=[c];data=p.to_dict();data['chords'][0]['quality']='add9'
                    expected=events(c)
                    q=Project.from_dict(data);actual=q.chords[0]
                    self.assertEqual(actual.quality,'add2');self.assertEqual(events(actual),expected)
                    self.assertEqual(events(Project.from_dict(q.to_dict()).chords[0]),expected)
                    self.assertEqual(data['chords'][0]['quality'],'add9')

    def test_legacy_explicit_notes_preserve_registers_and_metadata(self):
        p=Project();p.chords=[Chord(240,PPQ,notes=[Note(0,200,62,87,event_id='shared')],custom_rhythm=True)]
        data=p.to_dict();data['chords'][0]['quality']='add9'
        q=Project.from_dict(data)
        self.assertEqual(q.chords[0].notes,p.chords[0].notes)
        self.assertTrue(q.chords[0].custom_rhythm)

    def test_saved_quality_order_and_recipes_migrate(self):
        set_quality_order(['m7','add9','add2','mM7'])
        self.assertEqual([q for q,_ in quality_items()][:3],['m7','add2','mM7'])
        self.assertEqual(make_preset('Iadd9 V7')['sequence'],'Iadd2 V7')
        self.assertEqual(resolve('Iadd9',0).quality,'add2')
        set_language('en');labels=dict(quality_items())
        self.assertIn('Minor major seventh',labels['mM7']);self.assertIn('Added second',labels['add2'])

    def test_chorus_roundtrip_and_repeated_sections(self):
        p=Project();p.measures[0]=Measure(section='chorus');p.measures[2]=Measure(section='CHORUS')
        q=Project.from_dict(p.to_dict());self.assertEqual(q.sections(),[('Chorus',0,2),('Chorus',2,8)])
        with tempfile.TemporaryDirectory(dir='tmp') as folder:
            path=Path(folder)/'chorus.lfs';q.save(path);self.assertEqual(Project.load(path).sections(),q.sections())

class DialogTests(unittest.TestCase):
    def test_roots_start_at_one_in_every_key_and_mode(self):
        for tonic in range(12):
            for mode in MODES:
                p=Project();p.contexts=[Context(0,p.end,48+tonic,mode)];d=ChordDialog(Chord(0,PPQ,58,bass=4),p)
                try:
                    self.assertEqual(d.root.itemData(0),tonic);self.assertTrue(d.root.itemText(0).startswith('1 · '))
                    self.assertEqual([d.root.itemData(i) for i in range(12)],[(tonic+i)%12 for i in range(12)])
                    self.assertEqual(d.root.currentData(),tonic);self.assertEqual(d.bass.currentData(),tonic)
                finally:d.close();d.deleteLater()

    def test_moving_start_reorders_without_changing_chord_or_regenerate(self):
        p=Project();p.contexts=[Context(0,3840,53),Context(3840,p.end,50,'Dorian')]
        d=ChordDialog(Chord(0,PPQ,58,bass=4),p)
        try:
            d.root.setCurrentIndex(d.root.findData(10));d.bass.setCurrentIndex(d.bass.findData(4))
            d.regenerate.setChecked(False);d.start.setValue(4)
            self.assertEqual(d.root.itemText(0),'1 · D');self.assertEqual(d.root.currentData(),10)
            self.assertEqual(d.bass.currentData(),4);self.assertFalse(d.regenerate.isChecked())
        finally:d.close();d.deleteLater()

    def test_defaults_do_not_copy_target_time_id_or_notes(self):
        p=Project();c=Chord(3840,2*PPQ,notes=[Note(0,480,60)],custom_rhythm=True);before=copy.deepcopy(c)
        opts=dict(root=7,quality='mM7',bass=11,pattern='up',gate=65,velocity=81,octave=1,regenerate=False,start=0,duration=1)
        d=ChordDialog(c,p,defaults=opts)
        try:
            for key,value in d.options().items():self.assertEqual(value,opts[key],key)
            result=d.value();self.assertEqual((result.id,result.start,result.duration),(c.id,c.start,c.duration))
            self.assertEqual(c,before)
        finally:d.close();d.deleteLater()

    def test_unsupported_remembered_pattern_falls_back(self):
        p=Project();p.change_meter(0,3,4)
        d=ChordDialog(Chord(0,PPQ),p,defaults=dict(pattern='bass_chord',regenerate=True))
        try:self.assertEqual(d.pattern.currentData(),'block')
        finally:d.close();d.deleteLater()

    def test_invalid_preferences_are_ignored(self):
        d=ChordDialog(Chord(0,PPQ),Project(),defaults=dict(root='bad',quality='bad',velocity='loud',gate=500,regenerate='no'))
        try:
            self.assertEqual(d.root.currentData(),0);self.assertEqual(d.velocity.value(),72)
            self.assertEqual(d.gate.value(),90);self.assertTrue(d.regenerate.isChecked())
        finally:d.close();d.deleteLater()

class ApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir='tmp');self.folder=Path(self.temp.name)
        self.paths=patch('lingfeng.ui.main_window.user_data_dir',return_value=self.folder);self.paths.start()
        self.w=MainWindow(Project());self.w.timer.stop();self.w.autosave.stop();self.w.change_language('zh',False)
    def tearDown(self):
        self.w.dirty=False;self.w.close();self.w.deleteLater();APP.processEvents();self.paths.stop();self.temp.cleanup()
    def edit(self,index,callback):
        c=self.w.project.chords[index]
        with patch.object(ChordDialog,'exec',callback),patch.object(self.w.transport,'audition'):
            self.w.edit_chord(c.id,c.start)

    def test_confirmed_options_follow_different_chords_cancel_and_restart(self):
        opts=dict(quality='mM7',pattern='quarters',gate=70,velocity=82)
        def accept(d):d.apply_options(opts);return QDialog.DialogCode.Accepted
        self.edit(0,accept);self.assertEqual(self.w.chord_edit_options,opts)
        target=copy.deepcopy(self.w.project.chords[1]);before=self.w.project.to_dict();history=len(self.w.undo_history)
        def cancel(d):
            self.assertEqual(d.options(),opts)
            self.assertEqual((d.value().start,d.value().duration),(target.start,target.duration))
            d.quality.setCurrentIndex(d.quality.findData('add2'));return QDialog.DialogCode.Rejected
        self.edit(1,cancel)
        self.assertEqual(self.w.chord_edit_options,opts);self.assertEqual(self.w.project.to_dict(),before)
        self.assertEqual(len(self.w.undo_history),history)
        self.assertEqual(json.loads((self.folder/'preferences.json').read_text('utf-8'))['chord_edit_options'],opts)
        second=MainWindow(Project());second.timer.stop();second.autosave.stop()
        try:self.assertEqual(second.chord_edit_options,opts)
        finally:second.dirty=False;second.close();second.deleteLater()

    def test_failed_edit_does_not_replace_defaults(self):
        self.w.chord_edit_options={'quality':'m7'}
        with patch.object(self.w,'mutate',return_value=False):
            self.edit(0,lambda d:QDialog.DialogCode.Accepted)
        self.assertEqual(self.w.chord_edit_options,{'quality':'m7'})

    def test_menus_include_chorus_and_order_roots_by_chord_start(self):
        w=self.w;p=w.project;p.contexts=[Context(0,p.end,53)];p.chords[0]=Chord(0,3840,53);w.refresh()
        for r in (w.roll,w.harmony_window.roll):
            menu=r.lane.context_menu(QPoint(round(r.lane.x_at(100)),18))
            self.assertEqual(menu.root_menu.actions()[0].text(),'1 · F');self.assertTrue(menu.root_menu.actions()[0].isChecked())
            labels=[a.text() for a in menu.quality_menu.actions()]
            self.assertTrue(any(x.startswith('mM7') for x in labels));self.assertTrue(any(x.startswith('add2') for x in labels))
            self.assertFalse(any('add9' in x for x in labels));menu.deleteLater()
            menu=r.timeline_menu(QPoint(round(r.x_at(100)),10))
            section=next(a.menu() for a in menu.actions() if a.text()=='段落标识')
            self.assertIn('Chorus',[a.text() for a in section.actions()]);menu.deleteLater()

if __name__=='__main__':unittest.main()

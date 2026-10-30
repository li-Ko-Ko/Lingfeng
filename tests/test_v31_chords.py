"""Chord property edits retain rhythmic intent; names follow written harmony."""
import copy,os,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from lingfeng.music.model import Project, Chord, Context, Note, PPQ, PATTERNS, QUALITIES, MODES, pitch_name
from lingfeng.music.chord_operations import change_chords, chord_details, contextual_chord_name, chord_pitch_name, chord_degree_text
from lingfeng.music.chord_spelling import scale_tones, NATURALS, Tone
from lingfeng.ui.dialogs import ChordDialog
from lingfeng.music.rhythm import analyze, regenerate, Rhythm
from tests.music_reference import bar_events

APP=QApplication.instance() or QApplication([])

def events(chord):return sorted((n.start,n.duration,n.pitch,n.velocity) for n in chord.render_notes())


class QualityTests(unittest.TestCase):
    def test_two_beat_vi_to_vi7_keeps_quarter_blocks_and_all_other_properties(self):
        for materialized in (False,True):
            with self.subTest(materialized=materialized):
                p=Project();c=Chord(PPQ,2*PPQ,57,'m',pattern='quarters',gate=.75,velocity=83,octave=1,flat=True)
                if materialized:c.materialize()
                original=copy.deepcopy(c);p.chords=[c]
                change_chords(p,{c.id},'quality:m7')
                self.assertEqual(c.quality,'m7');self.assertEqual(analyze(c,p).pattern,'quarters')
                self.assertEqual(events(c),bar_events(c,p,c.start,c.end))
                self.assertEqual({n.start for n in c.render_notes()},{PPQ,2*PPQ})
                for onset in (PPQ,2*PPQ):self.assertEqual({n.pitch%12 for n in c.render_notes() if n.start==onset},{9,0,4,7})
                for field in ('start','duration','root','bass','id','flat','gate','velocity','octave','custom_rhythm'):
                    self.assertEqual(getattr(c,field),getattr(original,field),field)

    def test_every_named_pattern_uses_full_bar_phase_with_new_quality(self):
        for pattern in PATTERNS:
            with self.subTest(pattern=pattern):
                p=Project();base=Chord(300,6500,57,'m',bass=0,pattern=pattern,gate=.8,velocity=77)
                c=regenerate(base,base.start,base.end,p,Rhythm(pattern,tuple(base.pitches),base.gate));p.chords=[c]
                self.assertEqual(analyze(c,p).pattern,pattern)
                change_chords(p,{c.id},'quality:m9')
                self.assertEqual((c.pattern,c.bass,c.gate,c.velocity), (pattern,None,.8,77))
                self.assertEqual(analyze(c,p).pattern,pattern)
                self.assertEqual(events(c),bar_events(c,p,c.start,c.end));p.validate()

    def test_custom_rhythm_keeps_event_timing_and_lock(self):
        for locked in (False,True):
            with self.subTest(locked=locked):
                p=Project();c=Chord(480,3000,notes=[Note(120,350,60,90),Note(740,460,64,71),Note(990,710,67,101)],custom_rhythm=locked);p.chords=[c]
                before=[(n.start,n.duration,n.velocity,n.id) for n in c.notes]
                change_chords(p,{c.id},'quality:m')
                self.assertEqual([(n.start,n.duration,n.velocity,n.id) for n in c.notes],before)
                self.assertEqual([n.pitch for n in c.notes],[60,63,67]);self.assertEqual(c.custom_rhythm,locked)
                self.assertIsNone(analyze(c,p))

    def test_dialog_quality_edit_regenerates_by_default(self):
        p=Project();c=Chord(PPQ,2*PPQ,57,'m',pattern='quarters',gate=.75);c.materialize();before=copy.deepcopy(c)
        dialog=ChordDialog(c,p)
        try:
            self.assertTrue(dialog.regenerate.isChecked())
            dialog.quality.setCurrentIndex(dialog.quality.findData('m7'));result=dialog.value()
            self.assertEqual(analyze(result,p).pattern,'quarters')
            self.assertEqual(events(result),bar_events(result,p,result.start,result.end))
            self.assertEqual(c,before)
        finally:dialog.deleteLater()

    def test_custom_quality_edit_preserves_explicit_bass_and_upper_voice_octaves(self):
        for locked in (False,True):
            with self.subTest(locked=locked):
                p=Project();c=Chord(0,1920,48,'',bass=4,custom_rhythm=locked,
                    notes=[Note(0,1500,40,101),Note(0,320,48,82),Note(130,290,52,70),Note(710,570,55,87)])
                p.chords=[c];before={n.id:copy.deepcopy(n) for n in c.notes}
                change_chords(p,{c.id},'quality:m')
                self.assertEqual((c.bass,min(n.pitch for n in c.notes)),(None,36))
                self.assertEqual([n.pitch for n in c.notes],[36,48,51,55])
                for note in c.notes:
                    old=before[note.id]
                    self.assertEqual((note.start,note.duration,note.velocity),(old.start,old.duration,old.velocity))
                self.assertEqual(contextual_chord_name(p,c),'Cm')
        c=Chord(0,1920,48,'7',bass=10,custom_rhythm=True,
            notes=[Note(0,1500,46),Note(0,320,60),Note(130,290,64),Note(710,570,67),Note(950,310,70)])
        p.chords=[c];change_chords(p,{c.id},'quality:')
        self.assertEqual([n.pitch for n in c.notes],[48,60,64,67]);self.assertIsNone(c.bass)

    def test_root_change_then_quality_edit_keeps_actual_low_register(self):
        p=Project();c=Chord(0,2*PPQ,pattern='quarters');c.materialize();p.chords=[c]
        change_chords(p,{c.id},'root:11')
        self.assertEqual(sorted({n.pitch for n in c.notes}),[47,59,63,66])
        change_chords(p,{c.id},'quality:m7')
        self.assertEqual(sorted({n.pitch for n in c.notes}),[47,59,62,66,69])
        self.assertEqual(analyze(c,p).pattern,'quarters');self.assertEqual(c.octave,0)
        self.assertEqual({n.start for n in c.notes},{0,PPQ})

    def test_named_quality_edit_preserves_spread_voicing_and_explicit_bass(self):
        p=Project();c=Chord(0,2*PPQ,48,'maj9',bass=4,pattern='quarters',
            notes=[Note(t,864,p) for t in (0,PPQ) for p in (40,60,64,67,71,74)])
        p.chords=[c];change_chords(p,{c.id},'quality:add2')
        self.assertEqual(sorted({n.pitch for n in c.notes}),[36,48,50,52,55])
        self.assertIsNone(c.bass);self.assertEqual(analyze(c,p).pattern,'quarters')
        change_chords(p,{c.id},'quality:m7')
        self.assertEqual(sorted({n.pitch for n in c.notes}),[36,48,51,55,58])
        self.assertIsNone(c.bass);self.assertEqual(analyze(c,p).pattern,'quarters')

    def test_standard_voicings_still_match_default_for_every_quality_pair(self):
        from lingfeng.music.chord_operations import quality_voicing
        for old in QUALITIES:
            for new in QUALITIES:
                for bass in (None,4,10):
                    with self.subTest(old=old,new=new,bass=bass):
                        c=Chord(0,PPQ,48,old,bass=bass)
                        expected=Chord(0,PPQ,48,new,bass=bass).pitches
                        self.assertEqual(quality_voicing(c,new,c.pitches),tuple(expected))


class SpellingTests(unittest.TestCase):
    def test_f_major_root_and_chord_tones_use_bb_without_touching_roll_or_midi(self):
        p=Project();p.contexts=[Context(0,p.end,53,'Ionian')];c=Chord(0,2*PPQ,58,bass=0);p.chords=[c]
        before=p.to_dict()
        self.assertEqual(contextual_chord_name(p,c),'Bb/C')
        self.assertEqual(chord_pitch_name(p,c,58),'Bb3');self.assertEqual(chord_degree_text(p,c,58),'4')
        self.assertIn('4 = Bb3',chord_details(p,c));self.assertNotIn('A#',chord_details(p,c))
        self.assertEqual(pitch_name(58),'A#3');self.assertEqual(p.to_dict(),before)

    def test_chromatic_chord_intervals_determine_flat_or_sharp_spelling(self):
        p=Project()
        for quality,pitch,name,degree in [('m',63,'Eb4','b3'),('dim',66,'Gb4','b5'),('aug',68,'G#4','#5'),('m7',70,'Bb4','b7')]:
            with self.subTest(quality=quality):
                c=Chord(0,PPQ,48,quality)
                self.assertEqual(chord_pitch_name(p,c,pitch),name)
                self.assertEqual(chord_degree_text(p,c,pitch,unicode=False),degree)
        details=chord_details(p,Chord(0,PPQ,48,'m'))
        self.assertIn('♭3 = Eb3',details);self.assertNotIn('♯2',details)

    def test_cross_mode_hover_spells_each_context_separately(self):
        p=Project();p.contexts=[Context(0,3840),Context(3840,p.end,50,'Dorian')];c=Chord(0,7680)
        details=chord_details(p,c)
        self.assertIn('1 = C3',details);self.assertIn('♭7 = C3',details)
        self.assertIn('Dorian',details);self.assertEqual(details.count('实际低音'),2)

    def test_all_modes_have_each_scale_letter_once_and_correct_pitch_classes(self):
        for tonic in range(12):
            for mode,intervals in MODES.items():
                with self.subTest(tonic=tonic,mode=mode):
                    tones=scale_tones(tonic,mode)
                    self.assertEqual(len({t.letter for t in tones}),7)
                    self.assertEqual(tuple((NATURALS[t.letter]+t.alteration)%12 for t in tones),tuple((tonic+i)%12 for i in intervals))
        self.assertEqual([t.name for t in scale_tones(5,'Ionian')],['F','G','A','Bb','C','D','E'])
        self.assertEqual([t.name for t in scale_tones(7,'Ionian')],['G','A','B','C','D','E','F#'])

    def test_enharmonic_written_octaves_and_flat_fallback(self):
        self.assertEqual(Tone(6,1).pitch_name(60),'B#3');self.assertEqual(Tone(0,-1).pitch_name(59),'Cb4')
        p=Project();c=Chord(0,PPQ,49,'m',flat=True)
        self.assertEqual(contextual_chord_name(p,c),'Dbm')
        self.assertEqual(chord_pitch_name(p,c,61),'Db4')


class RootPickerTests(unittest.TestCase):
    def test_root_numbers_follow_chord_start_and_remain_sharp(self):
        p=Project();p.contexts=[Context(0,3840),Context(3840,p.end,53,'Ionian')];c=Chord(3840,PPQ,58)
        dialog=ChordDialog(c,p)
        try:
            self.assertEqual(dialog.root.currentData(),5)
            dialog.root.setCurrentIndex(dialog.root.findData(10))
            self.assertEqual(dialog.root.currentData(),10);self.assertEqual(dialog.root.currentText(),'4 · A#')
            self.assertEqual(dialog.root.itemText(1),'#1 · F#')
            self.assertIn('Bb',dialog.preview.text())
            dialog.start.setValue(0)
            self.assertEqual(dialog.root.currentData(),10);self.assertEqual(dialog.root.currentText(),'#6 · A#')
            self.assertEqual(dialog.value().root,58)
        finally:dialog.deleteLater()


if __name__=='__main__':unittest.main()

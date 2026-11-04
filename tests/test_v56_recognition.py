"""Independent chord/rhythm recognition switches and MIDI-neutral chord markers."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from lingfeng.audio.midi import event_list
from lingfeng.music.model import Chord, Note, Project, QUALITIES
from lingfeng.music.chord_operations import (
    can_apply_pattern, can_merge_chords, can_move_diatonic, change_chords,
    compact_chord_details, contextual_chord_name, merge_chords, move_chords, roman_label, split_at_position,
)
from lingfeng.music.meter import rescan_chord
from lingfeng.music.note_operations import resize_chord
from lingfeng.music.recognition import recognize, set_marker, set_recognition_disabled, update_symbol
from lingfeng.music.rhythm import ALTERNATING, Rhythm, analyze, analyze_performed, extend, regenerate


def events(chord):
    return [(n.id,n.event_id,n.start,n.duration,n.pitch,n.velocity) for n in chord.render_notes()]


class RecognitionSwitchTests(unittest.TestCase):
    def project(self,**kwargs):
        project=Project();chord=Chord(0,3840,pattern='quarters',gate=.8,**kwargs)
        project.chords=[chord]
        return project,chord

    def test_disable_materializes_without_changing_performance_or_note_identity(self):
        project,chord=self.project()
        before=events(chord);midi=event_list(project)
        set_recognition_disabled(chord,True,project)
        self.assertEqual(events(chord),before)
        self.assertEqual(event_list(project),midi)
        self.assertTrue(chord.recognition_disabled)
        self.assertFalse(chord.recognized)
        self.assertFalse(chord.marked)
        self.assertFalse(chord.custom_rhythm)
        self.assertIsNotNone(chord.notes)
        self.assertEqual(chord.name,'未识别')
        self.assertEqual(chord.roman(48),'?')
        project.validate()

    def test_disabling_chord_recognition_blocks_every_pattern_rebuild_entry(self):
        project,chord=self.project()
        set_marker(chord,54,'aug',11)
        explicit=Rhythm('eighths',tuple(chord.pitches),.9)
        self.assertIsNone(analyze(chord,project))
        self.assertIsNone(analyze_performed(chord,project))
        self.assertIsNone(regenerate(chord,0,7680,project,explicit))
        self.assertIsNone(extend(chord,0,7680,explicit))
        before=copy.deepcopy(chord)
        update_symbol(chord,recognize([48,52,55]))
        self.assertEqual(chord,before)

    def test_rhythm_switch_does_not_disable_chord_recognition(self):
        project,chord=self.project()
        change_chords(project,{chord.id},'custom:1')
        self.assertTrue(chord.custom_rhythm)
        self.assertFalse(chord.recognition_disabled)
        self.assertIsNone(analyze(chord,project))
        for note in chord.notes:
            if note.pitch%12==4:note.pitch-=1
        rescan_chord(project,chord)
        self.assertTrue(chord.recognized)
        self.assertEqual(chord.name,'Cm')
        self.assertTrue(chord.custom_rhythm)

    def test_resume_removes_marker_and_uses_actual_midi_without_marker_preference(self):
        project,chord=self.project()
        chord.notes=[Note(0,3840,pitch,velocity=50+i) for i,pitch in enumerate((48,52,55,57))]
        before=events(chord)
        set_marker(chord,57,'m7',0)
        self.assertEqual(chord.name,'Am7/C')
        set_recognition_disabled(chord,False,project)
        self.assertFalse(chord.marked)
        self.assertFalse(chord.recognition_disabled)
        self.assertTrue(chord.recognized)
        self.assertEqual(chord.name,'C6')
        self.assertEqual(events(chord),before)
        self.assertEqual(analyze(chord,project).pattern,'block')

    def test_resume_retains_independent_rhythm_disable_preference(self):
        for rhythm_disabled in (False,True):
            with self.subTest(rhythm_disabled=rhythm_disabled):
                project,chord=self.project(custom_rhythm=rhythm_disabled)
                before=events(chord)
                set_recognition_disabled(chord,True,project)
                self.assertIsNone(analyze(chord,project))
                set_recognition_disabled(chord,False,project)
                self.assertEqual(chord.custom_rhythm,rhythm_disabled)
                self.assertEqual(analyze(chord,project) is None,rhythm_disabled)
                self.assertEqual(events(chord),before)

    def test_resume_on_an_already_enabled_generated_chord_keeps_its_actual_voicing(self):
        project,chord=self.project(root=57,quality='m7',bass=0)
        before=events(chord)
        set_recognition_disabled(chord,False,project)
        self.assertEqual(events(chord),before)
        self.assertEqual(chord.name,'C6')

    def test_disabled_rescan_never_calls_chord_or_rhythm_recognizers(self):
        project,chord=self.project()
        set_marker(chord,54,'aug',11)
        chord.notes[0].pitch=41
        before=copy.deepcopy(chord)
        with patch('lingfeng.music.recognition.recognize',side_effect=AssertionError('recognition disabled')):
            with patch('lingfeng.music.rhythm.analyze',side_effect=AssertionError('rhythm disabled')):
                self.assertIs(rescan_chord(project,chord),chord)
        self.assertEqual(chord,before)

    def test_batch_switches_preserve_independent_markers_and_clear_them_on_resume(self):
        project,chord=self.project()
        other=Chord(3840,3840,50,'m',custom_rhythm=True)
        project.chords.append(other)
        before=event_list(project)
        set_marker(chord,54,'aug',11)
        change_chords(project,{chord.id,other.id},'recognition:1')
        self.assertTrue(chord.marked)
        self.assertTrue(all(c.recognition_disabled for c in project.chords))
        change_chords(project,{chord.id,other.id},'recognition:0')
        self.assertTrue(all(not c.recognition_disabled and not c.marked for c in project.chords))
        self.assertFalse(chord.custom_rhythm)
        self.assertTrue(other.custom_rhythm)
        self.assertEqual(event_list(project),before)


class ChordMarkerTests(unittest.TestCase):
    project=RecognitionSwitchTests.project

    def test_marker_changes_only_display_fields_for_generated_chords(self):
        project,chord=self.project(velocity=83)
        before=events(chord);midi=event_list(project)
        set_marker(chord,54,'aug',11)
        self.assertEqual(events(chord),before)
        self.assertEqual(event_list(project),midi)
        self.assertEqual(chord.name,'F#aug/B')
        self.assertEqual(chord.roman(48),'♯IV+/7')
        self.assertEqual(contextual_chord_name(project,chord),'F#aug/B')
        self.assertEqual(roman_label(project,chord),'♯IV+/7')
        self.assertTrue(chord.marked and chord.recognition_disabled and chord.recognized)
        project.validate()

    def test_explicit_notes_and_shared_event_identities_are_preserved_exactly(self):
        project,chord=self.project()
        chord.notes=[Note(37,800,61,31,id='part-one',event_id='crossing'),Note(960,1500,68,115,id='part-two')]
        chord.notes[0].lyric='keep';chord.notes[0].flat=True
        before=copy.deepcopy(chord.notes);midi=event_list(project)
        set_marker(chord,2,'m7',5)
        self.assertEqual(chord.notes,before)
        self.assertEqual(event_list(project),midi)
        project.rescan_harmony()
        self.assertEqual(chord.notes,before)
        self.assertEqual(chord.name,'Dm7/F')
        details=compact_chord_details(project,chord)
        self.assertIn('C#',details)
        self.assertIn('G#',details)

    def test_blank_region_can_be_marked_without_generating_notes(self):
        project,chord=self.project(notes=[],recognized=False)
        set_marker(chord,0,'maj7',4)
        self.assertEqual(chord.render_notes(),[])
        self.assertEqual(chord.name,'Cmaj7/E')
        self.assertEqual(chord.roman(48),'Imaj7/3')
        self.assertEqual(contextual_chord_name(project,chord),'Cmaj7/E')
        set_recognition_disabled(chord,False,project)
        self.assertFalse(chord.marked)
        self.assertEqual(chord.name,'N.C.')

    def test_manual_note_edits_keep_marker_and_plain_disabled_regions_unrecognized(self):
        project,chord=self.project()
        other=Chord(3840,3840,50,'m')
        project.chords.append(other)
        set_marker(chord,54,'aug',11)
        set_recognition_disabled(other,True,project)
        project.edit_harmony(Note(480,240,61,115))
        self.assertEqual(chord.name,'F#aug/B')
        self.assertFalse(other.recognized)
        self.assertTrue(chord.marked and chord.recognition_disabled)
        self.assertIn((480,240,61,115),[(n.start,n.duration,n.pitch,n.velocity) for n in project.harmony_notes()])
        self.assertIsNone(analyze(chord,project))
        self.assertIsNone(analyze(other,project))
        project.validate()

    def test_move_resize_split_and_meter_changes_keep_marker_without_filling_notes(self):
        project,chord=self.project()
        set_marker(chord,54,'aug',11)
        before=events(chord)
        resized=resize_chord(chord,0,7680,project=project)
        self.assertEqual(events(resized),before)
        self.assertTrue(resized.marked and resized.recognition_disabled)
        move_chords(project,{chord.id},480)
        moved=next(c for c in project.chords if c.id==chord.id)
        self.assertEqual([(n.start-480,n.duration,n.pitch,n.velocity) for n in moved.render_notes()],[(t,d,p,v) for _,_,t,d,p,v in before])
        split_ids=split_at_position(project,2400)
        self.assertTrue(all(c.marked and c.recognition_disabled for c in project.chords if c.id in split_ids))
        project.change_meter(0,5,4)
        self.assertTrue(all(c.name=='F#aug/B' for c in project.chords if c.id in split_ids))
        project.validate()

    def test_transposition_edits_notes_but_keeps_manual_label_fixed(self):
        project,chord=self.project()
        set_marker(chord,54,'aug',11)
        before=events(chord)
        change_chords(project,{chord.id},'transpose:12')
        self.assertEqual(chord.name,'F#aug/B')
        self.assertEqual(events(chord),[(nid,eid,t,d,p+12,v) for nid,eid,t,d,p,v in before])
        self.assertTrue(chord.marked and chord.recognition_disabled)
        project.rescan_harmony()
        self.assertEqual(chord.name,'F#aug/B')

    def test_semantic_transforms_do_not_use_manual_label_as_actual_midi(self):
        project,chord=self.project()
        other=Chord(3840,3840);project.chords.append(other)
        set_marker(chord,0,'',None)
        self.assertFalse(can_apply_pattern(project,[chord],'quarters'))
        self.assertFalse(can_move_diatonic(project,[chord],1))
        self.assertFalse(can_merge_chords([chord,other],project))
        before=project.to_dict()
        for command in ('root:4','quality:m','bass:7','inversion:1'):
            change_chords(project,{chord.id},command)
            self.assertEqual(project.to_dict(),before)
        for command in ('root_step:1','pattern:quarters','diatonic:1'):
            with self.subTest(command=command),self.assertRaises(ValueError):change_chords(project,{chord.id},command)
        with self.assertRaises(ValueError):merge_chords(project,{chord.id,other.id})
        self.assertEqual(project.to_dict(),before)

    def test_native_roundtrip_and_legacy_defaults(self):
        project,chord=self.project(custom_rhythm=True)
        set_marker(chord,54,'aug',11)
        root=Path(__file__).resolve().parents[1]/'tmp'
        with tempfile.TemporaryDirectory(dir=root) as directory:
            path=Path(directory)/'annotation.lfs';project.save(path)
            restored=Project.load(path)
            self.assertEqual(restored.to_dict(),project.to_dict())
            restored.rescan_harmony()
            self.assertEqual(restored.chords[0].name,'F#aug/B')
        legacy=Project().to_dict();legacy['chords']=[Chord(0,3840).__dict__.copy()]
        legacy['chords'][0].pop('recognition_disabled');legacy['chords'][0].pop('marked')
        restored=Project.from_dict(legacy)
        self.assertFalse(restored.chords[0].recognition_disabled or restored.chords[0].marked)

    def test_invalid_marker_rejected_before_materializing_or_changing_chord(self):
        _,chord=self.project()
        before=copy.deepcopy(chord)
        for args in ((True,'',None),(0,'unsupported-quality',None),(0,'',12),(0,'',True)):
            with self.subTest(args=args),self.assertRaises(ValueError):set_marker(chord,*args)
            self.assertEqual(chord,before)

    def test_invalid_persisted_marker_states_are_rejected(self):
        for kwargs in (dict(marked=True),dict(marked=True,recognition_disabled=True,recognized=False,notes=[]),dict(recognition_disabled=True)):
            with self.subTest(kwargs=kwargs):
                project=Project();project.chords=[Chord(0,3840,**kwargs)]
                with self.assertRaises(ValueError):project.validate()


class ExpandedAlternatingTests(unittest.TestCase):
    def test_every_quality_keeps_its_supplied_tones_symbol_and_alternating_pattern(self):
        for quality in QUALITIES:
            for pattern in ALTERNATING:
                with self.subTest(quality=quality,pattern=pattern):
                    project=Project();chord=Chord(0,3840,quality=quality,pattern=pattern)
                    allowed={pitch%12 for pitch in chord.pitches}
                    project.put_chord(chord);chord=project.chords[0]
                    before=events(chord)
                    self.assertEqual({note.pitch%12 for note in chord.render_notes()},allowed)
                    rescan_chord(project,chord)
                    self.assertEqual(chord.quality,quality)
                    self.assertTrue(chord.recognized)
                    self.assertEqual(analyze(chord,project).pattern,pattern)
                    self.assertEqual(events(chord),before)

    def test_omitted_fifth_repeats_root_bass_instead_of_inserting_natural_fifth(self):
        for quality in ('no5','omit5','m(no5)','m(omit5)'):
            for pattern in ALTERNATING:
                with self.subTest(quality=quality,pattern=pattern):
                    chord=Chord(0,3840,quality=quality,pattern=pattern)
                    bass=[note.pitch for note in chord.render_notes() if note.pitch<48]
                    self.assertEqual(bass,[36]*4)
                    self.assertNotIn(7,{note.pitch%12 for note in chord.render_notes()})


if __name__=='__main__':unittest.main()

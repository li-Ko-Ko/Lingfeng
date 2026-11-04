"""Global rhythm recognition pauses inference without changing performed music."""
import copy
import unittest
from unittest.mock import patch

from lingfeng.music.chord_operations import change_chords, merge_chords, split_chords
from lingfeng.music.meter import moved_chord, rescan_chord
from lingfeng.music.model import Chord, Context, Measure, Note, PPQ, Project
from lingfeng.music.note_operations import resize_chord, repartition_chord
from lingfeng.music.progressions import apply
from lingfeng.music.rhythm import Rhythm, analyze, analyze_performed, extend, label, regenerate
from lingfeng.platform import rhythm_preferences


def events(chord):
    return sorted((n.start,n.duration,n.pitch,n.velocity) for n in chord.render_notes())


def project(numerator=4,denominator=4,bars=4):
    p=Project(measures=[Measure(numerator,denominator) for _ in range(bars)])
    p.contexts=[Context(0,p.end)]
    return p


class GlobalRhythmTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(rhythm_preferences.set_enabled,rhythm_preferences.enabled())
        rhythm_preferences.set_enabled(True)

    def generated(self,pattern='up'):
        p=project()
        p.put_chord(Chord(0,4*PPQ,pattern=pattern,velocity=83))
        return p,p.chords[0]

    def pause(self):
        rhythm_preferences.set_enabled(False)
        # Even warmed recognition caches must not be consulted while paused.
        for name in ('_recognize','_recognize_bar'):
            guard=patch('lingfeng.music.rhythm.'+name,side_effect=AssertionError('rhythm inference ran while disabled'))
            guard.start();self.addCleanup(guard.stop)

    def test_old_and_invalid_settings_default_to_enabled(self):
        for value in (None,{}, {'rhythm_recognition':None},{'rhythm_recognition':0},{'rhythm_recognition':'false'}):
            rhythm_preferences.load_preferences(value)
            self.assertTrue(rhythm_preferences.enabled())
        rhythm_preferences.load_preferences({'rhythm_recognition':False})
        self.assertFalse(rhythm_preferences.enabled())
        self.assertEqual(rhythm_preferences.settings_dict(),{'rhythm_recognition':False})

    def test_all_analysis_and_labels_stop_without_mutating_music_or_flags(self):
        p,c=self.generated()
        self.assertEqual(analyze(c,p).pattern,'up')
        self.assertEqual(analyze_performed(c,p).pattern,'up')
        c.notes[0].event_id='preserved-event'
        before=copy.deepcopy(p.to_dict())
        self.pause()
        for flags in ({},{'custom_rhythm':True},{'recognition_disabled':True},{'recognized':False}):
            sample=copy.deepcopy(c)
            for name,value in flags.items():setattr(sample,name,value)
            self.assertIsNone(analyze(sample,p))
            self.assertIsNone(analyze_performed(sample,p))
            self.assertEqual(label(sample,p),'')
        self.assertEqual(p.to_dict(),before)

    def test_cached_matches_cannot_rebuild_after_global_switch_is_disabled(self):
        p,c=self.generated()
        match=analyze(c,p)
        self.pause()
        self.assertIsNone(regenerate(c,120,6000,p,match))
        self.assertIsNone(extend(c,120,6000,match))
        self.assertIsNone(regenerate(Chord(0,3840,pattern='up'),0,3840,p))

    def test_root_and_quality_edits_keep_performed_timing_dynamics_and_identity(self):
        p,c=self.generated('quarters')
        for index,note in enumerate(c.notes):
            note.velocity=45+index
            note.event_id='event-'+str(index)
        before=sorted((n.id,n.event_id,n.start,n.duration,n.velocity) for n in c.notes)
        self.pause()
        change_chords(p,{c.id},'root_step:5')
        c=p.chords[0]
        change_chords(p,{c.id},'quality:m')
        self.assertEqual(sorted((n.id,n.event_id,n.start,n.duration,n.velocity) for n in c.notes),before)
        self.assertFalse(c.custom_rhythm)
        self.assertFalse(c.recognition_disabled)
        p.validate()

    def test_move_translates_actual_notes_instead_of_rephasing_on_bar_grid(self):
        p,c=self.generated('quarters')
        before=events(c)
        self.pause()
        moved=moved_chord(p,c,120)
        p.put_chord(moved)
        self.assertEqual(events(p.chords[0]),[(t+120,d,pitch,v) for t,d,pitch,v in before])
        self.assertEqual(p.chords[0].pattern,'quarters')
        p.validate()

    def test_resize_preserves_notes_and_leaves_extended_space_silent(self):
        p,c=self.generated('quarters')
        before=events(c)
        self.pause()
        enlarged=resize_chord(c,0,6000,project=p)
        self.assertEqual(events(enlarged),before)
        cropped=resize_chord(c,120,2800,project=p)
        expected=[(max(120,t),min(2800,t+d)-max(120,t),pitch,v)
                  for t,d,pitch,v in before if t<2800 and t+d>120]
        self.assertEqual(events(cropped),expected)

    def test_legacy_compact_resize_materializes_before_changing_time(self):
        p=project()
        c=Chord(120,3840,pattern='quarters')
        before=events(c)
        self.pause()
        enlarged=resize_chord(c,0,6000,project=p)
        self.assertIsNotNone(enlarged.notes)
        self.assertEqual(events(enlarged),before)
        self.assertIsNone(c.notes)

    def test_legacy_compact_semantic_edits_match_edits_of_the_same_performed_midi(self):
        self.pause()
        for pattern in ('up','alternating_offbeat','sustained_bass_beats'):
            for command in ('root:5','quality:7','bass:4','inversion:1','diatonic:1'):
                with self.subTest(pattern=pattern,command=command):
                    p=project();c=Chord(120,3000,pattern=pattern,velocity=77)
                    p.chords=[c]
                    reference=copy.deepcopy(p);reference.chords[0].materialize()
                    change_chords(p,{c.id},command)
                    change_chords(reference,{c.id},command)
                    self.assertIsNotNone(p.chords[0].notes)
                    self.assertEqual(events(p.chords[0]),events(reference.chords[0]))
                    self.assertFalse(p.chords[0].custom_rhythm)
                    p.validate();reference.validate()

    def test_noop_compact_edits_and_structure_commands_keep_representation(self):
        self.pause()
        for command in ('root:0','quality:','bass:0','inversion:0','diatonic:0'):
            with self.subTest(command=command):
                p=project();c=Chord(0,3840,pattern='up');p.chords=[c]
                before=copy.deepcopy(p.to_dict())
                change_chords(p,{c.id},command)
                self.assertEqual(p.to_dict(),before)
                self.assertIsNone(p.chords[0].notes)
        p=project();c=Chord(0,3840,pattern='up');p.chords=[c]
        before=copy.deepcopy(p.to_dict())
        resized=resize_chord(c,c.start,c.end,project=p)
        self.assertIsNone(resized.notes)
        self.assertEqual(events(resized),events(c))
        repartition_chord(p,c.id,c.start,c.end)
        self.assertEqual(p.to_dict(),before)

    def test_compact_repartition_crops_existing_midi_and_does_not_fill_extension(self):
        p=project();c=Chord(120,3000,pattern='up');p.chords=[c]
        before=events(c)
        self.pause()
        repartition_chord(p,c.id,600,5000)
        changed=next(x for x in p.chords if x.id==c.id)
        expected=sorted((max(600,t),t+d-max(600,t),pitch,v)
                        for t,d,pitch,v in before if t+d>600)
        self.assertEqual(events(changed),expected)
        self.assertTrue(all(n.end<=3120 for n in changed.render_notes()))
        p.validate()

    def test_split_merge_and_meter_change_do_not_reinfer_texture(self):
        p,c=self.generated('quarters')
        before=events(c)
        self.pause()
        ids=split_chords(p,{c.id})
        self.assertEqual(len(ids),2)
        merged=merge_chords(p,ids)
        self.assertEqual(len(merged),1)
        c=next(c for c in p.chords if c.id in merged)
        self.assertEqual(events(c),before)
        # A deliberately stale hint survives scans while chord naming remains on.
        c.pattern='down'
        rescan_chord(p,c)
        self.assertEqual(c.pattern,'down')
        p.change_meter(0,3,4,allow_trim=True)
        self.assertEqual(p.chords[0].pattern,'down')
        p.validate()

    def test_chord_name_recognition_remains_available_when_rhythm_is_paused(self):
        p=project()
        c=Chord(0,3840,notes=[Note(0,3840,pitch,72) for pitch in (38,50,53,57)],recognized=False)
        self.pause()
        rescan_chord(p,c)
        self.assertTrue(c.recognized)
        self.assertEqual(c.root%12,2)
        self.assertEqual(c.quality,'m')

    def test_new_explicit_patterns_keep_local_bar_and_denominator_beats(self):
        p=project(3,8,bars=3)
        self.pause()
        c=Chord(120,3000,pattern='sustained_bass_beats',velocity=76)
        p.put_chord(c);c=p.chords[0]
        self.assertTrue(c.bar_aligned)
        expected=[]
        for origin in p.starts[:-1]:
            voices=[(origin,1440,c.pitches[0])]
            voices.extend((origin+i*480,480,pitch) for i in range(3) for pitch in c.pitches[1:])
            for t,d,pitch in voices:
                a,b=max(c.start,t),min(c.end,t+d)
                if a<b:expected.append((a,b-a,pitch,76))
        self.assertEqual(events(c),sorted(expected))
        p.validate()

    def test_pattern_and_progression_commands_synthesize_explicit_choice_without_inference(self):
        p,c=self.generated('up')
        self.pause()
        change_chords(p,{c.id},'pattern:quarters')
        self.assertEqual(c.pattern,'quarters')
        self.assertEqual(sorted({n.start for n in c.notes}),[0,960,1920,2880])
        apply(p,c.id,'Vm7',keep_rhythm=True,pattern='eighths')
        c=p.chords[0]
        self.assertEqual(c.pattern,'eighths')
        self.assertEqual(sorted({n.start for n in c.notes}),list(range(0,3840,480)))
        self.assertEqual(c.root%12,7)
        self.assertEqual(c.quality,'m7')
        p.validate()

    def test_reenabling_restores_recognition_and_keeps_individual_locks(self):
        p,c=self.generated('up')
        snapshot=copy.deepcopy(p.to_dict())
        rhythm_preferences.set_enabled(False)
        self.assertIsNone(analyze(c,p))
        self.assertEqual(Project.from_dict(p.to_dict()).to_dict(),snapshot)
        rhythm_preferences.set_enabled(True)
        self.assertEqual(analyze(c,p).pattern,'up')
        c.custom_rhythm=True
        rhythm_preferences.set_enabled(False);rhythm_preferences.set_enabled(True)
        self.assertIsNone(analyze(c,p))
        self.assertTrue(c.custom_rhythm)


if __name__=='__main__':unittest.main()

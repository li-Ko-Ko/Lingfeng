"""Unified chord dynamics, legacy project migration and cross-region note joins."""
import copy
import os
from pathlib import Path
import tempfile
import unittest

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication

from lingfeng.audio.midi import event_list
from lingfeng.music.model import Chord, Context, Measure, Note, PATTERNS, Project
from lingfeng.music.chord_operations import change_chords, set_chord_velocity
from lingfeng.music.note_operations import can_join, join_notes
from lingfeng.music.recognition import set_marker, set_recognition_disabled
from lingfeng.music.rhythm import ALTERNATING, analyze, extend, regenerate
from lingfeng.platform import chord_preferences as preferences
from lingfeng.platform.preferences import load_preferences, save_preferences
from lingfeng.ui.velocity_dialog import DynamicsSettingsDialog

APP=QApplication.instance() or QApplication([])
ROOT=Path(__file__).resolve().parents[1]


def geometry(chord):
    return [(n.id,n.event_id,n.start,n.duration,n.pitch) for n in chord.render_notes()]


class ChordDynamicsTests(unittest.TestCase):
    def test_all_generated_patterns_use_one_velocity_and_keep_geometry_when_changed(self):
        for pattern in PATTERNS:
            with self.subTest(pattern=pattern):
                chord=Chord(0,3840,pattern=pattern,velocity=91)
                before=geometry(chord)
                self.assertEqual({n.velocity for n in chord.render_notes()},{91})
                set_chord_velocity(chord,47)
                self.assertIsNone(chord.notes)
                self.assertEqual(geometry(chord),before)
                self.assertEqual({n.velocity for n in chord.render_notes()},{47})

    def test_regeneration_and_extending_use_common_dynamics(self):
        for pattern in PATTERNS:
            with self.subTest(pattern=pattern):
                project=Project();chord=Chord(0,3840,pattern=pattern,velocity=93)
                generated=regenerate(chord,0,7680,project)
                self.assertIsNotNone(generated)
                self.assertEqual(analyze(generated,project).pattern,pattern)
                self.assertEqual({n.velocity for n in generated.notes},{93})
                self.assertEqual({n.velocity for n in extend(chord,0,7680).render_notes()},{93})

    def test_common_edit_preserves_explicit_note_identity_time_and_custom_rhythm(self):
        chord=Chord(300,3840,notes=[Note(0,1200,60,81),Note(0,1200,64,94),Note(0,1200,67,103),
                                 Note(1920,900,60,77),Note(1920,900,64,95),Note(1920,900,67,102)],custom_rhythm=True)
        before=geometry(chord)
        set_chord_velocity(chord,48)
        self.assertEqual(geometry(chord),before)
        self.assertEqual({n.velocity for n in chord.notes},{48})
        self.assertEqual(chord.velocity,48)
        self.assertTrue(chord.custom_rhythm)

    def test_all_alternating_voices_and_meters_share_the_same_dynamics(self):
        for denominator in (2,4,8,16):
            for pattern in ALTERNATING:
                with self.subTest(denominator=denominator,pattern=pattern):
                    project=Project(measures=[Measure(4,denominator)])
                    project.contexts=[Context(0,project.end)]
                    chord=regenerate(Chord(0,project.end,bass=2,pattern=pattern,velocity=99),0,project.end,project)
                    project.chords=[chord];before=geometry(chord)
                    set_chord_velocity(chord,52)
                    self.assertEqual(geometry(chord),before)
                    self.assertEqual({n.velocity for n in chord.notes},{52})
                    self.assertEqual(analyze(chord,project).pattern,pattern)
                    project.validate()

    def test_cropped_patterns_change_every_performed_voice(self):
        project=Project()
        for pattern in PATTERNS:
            with self.subTest(pattern=pattern):
                chord=regenerate(Chord(0,3840,pattern=pattern,velocity=94),300,3100,project)
                before=geometry(chord);set_chord_velocity(chord,51)
                self.assertEqual(geometry(chord),before)
                self.assertEqual({n.velocity for n in chord.notes},{51})

    def test_unknown_marked_empty_and_disabled_chords_allow_common_edits(self):
        unknown=Chord(0,3840,notes=[Note(0,3840,60),Note(0,3840,61)],recognized=False)
        marked=Chord(0,3840);set_marker(marked,54,'aug',11)
        disabled=Chord(0,3840);set_recognition_disabled(disabled,True)
        empty=Chord(0,3840,notes=[],recognized=False)
        for chord in (unknown,marked,disabled,empty):
            with self.subTest(chord=chord):
                before=geometry(chord);set_chord_velocity(chord,73)
                self.assertEqual(geometry(chord),before)
                self.assertEqual({n.velocity for n in chord.render_notes()}-{73},set())
                self.assertEqual(chord.velocity,73)

    def test_root_quality_and_pattern_rebuilds_keep_common_velocity(self):
        project=Project();project.put_chord(Chord(0,3840,pattern='quarters',velocity=94))
        for command in ('quality:m7','root:5','pattern:alternating_eighths'):
            chord=project.chords[0];change_chords(project,{chord.id},command)
            self.assertEqual({n.velocity for n in project.chords[0].notes},{94})

    def test_old_generated_bass_override_migrates_to_explicit_notes_without_midi_changes(self):
        for pattern in PATTERNS:
            with self.subTest(pattern=pattern):
                project=Project();project.chords=[Chord(0,3840,pattern=pattern,velocity=94)]
                old=project.to_dict();old['chords'][0]['bass_velocity']=47
                expected=copy.deepcopy(project);chord=expected.chords[0];chord.materialize()
                for note in chord.notes:
                    if note.pitch<48:note.velocity=47
                restored=Project.from_dict(old)
                self.assertEqual(event_list(restored),event_list(expected))
                self.assertEqual(geometry(restored.chords[0]),geometry(chord))
                self.assertNotIn('bass_velocity',restored.to_dict()['chords'][0])
                again=Project.from_dict(restored.to_dict())
                self.assertEqual(event_list(again),event_list(expected))
                rebuilt=regenerate(restored.chords[0],0,3840,restored)
                self.assertEqual({n.velocity for n in rebuilt.notes},{94})

    def test_old_explicit_bass_metadata_is_discarded_while_note_dynamics_roundtrip(self):
        project=Project();chord=Chord(0,3840,pattern='quarters',velocity=94)
        chord.materialize();project.chords=[chord]
        for note in chord.notes:
            if note.pitch==36:note.velocity=47
        old=project.to_dict();old['chords'][0]['bass_velocity']=47
        restored=Project.from_dict(old);self.assertEqual(event_list(restored),event_list(project))
        self.assertNotIn('bass_velocity',restored.to_dict()['chords'][0])
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
            path=Path(directory)/'dynamics.lfs';restored.save(path)
            self.assertEqual(event_list(Project.load(path)),event_list(project))

    def test_old_slash_and_omitted_fifth_alternating_chords_preserve_actual_bass_pitches(self):
        for quality,bass,octave,lower in (('',2,0,{38,43}),('no5',None,0,{36}),('',2,1,{50,55})):
            for pattern in ALTERNATING:
                with self.subTest(quality=quality,bass=bass,octave=octave,pattern=pattern):
                    project=Project();project.chords=[Chord(0,3840,quality=quality,bass=bass,octave=octave,pattern=pattern,velocity=94)]
                    old=project.to_dict();old['chords'][0]['bass_velocity']=47
                    chord=Project.from_dict(old).chords[0]
                    self.assertEqual({n.pitch for n in chord.notes if n.velocity==47},lower)
                    self.assertTrue(all(n.velocity==(47 if n.pitch in lower else 94) for n in chord.notes))
                    self.assertEqual(geometry(chord),geometry(project.chords[0]))

    def test_legacy_null_override_does_not_materialize_generated_notes(self):
        project=Project();project.chords=[Chord(0,3840,velocity=91)]
        old=project.to_dict();old['chords'][0]['bass_velocity']=None
        restored=Project.from_dict(old)
        self.assertIsNone(restored.chords[0].notes)
        self.assertEqual(restored.to_dict(),project.to_dict())

    def test_old_add9_alias_is_normalized_before_legacy_bass_materialization(self):
        for legacy_bass in (None,47):
            with self.subTest(legacy_bass=legacy_bass):
                project=Project();project.chords=[Chord(0,3840,quality='add9',velocity=94)]
                old=project.to_dict();entry=old['chords'][0]
                entry.pop('recognition_disabled');entry.pop('marked');entry['bass_velocity']=legacy_bass
                restored=Project.from_dict(old).chords[0]
                self.assertEqual(restored.quality,'add2')
                self.assertEqual({n.pitch for n in restored.render_notes()},{36,48,50,52,55})
                self.assertTrue(all(n.velocity==(47 if legacy_bass and n.pitch==36 else 94) for n in restored.render_notes()))

    def test_invalid_velocity_and_legacy_bass_values_are_rejected_before_mutation(self):
        for value in (True,0,128,'80',2.5):
            with self.subTest(value=value):
                chord=Chord(0,3840);before=copy.deepcopy(chord)
                with self.assertRaises(ValueError):set_chord_velocity(chord,value)
                self.assertEqual(chord,before)
                project=Project();project.chords=[chord];old=project.to_dict()
                old['chords'][0]['bass_velocity']=value
                with self.assertRaises(ValueError):Project.from_dict(old)


class ChordPreferenceTests(unittest.TestCase):
    def setUp(self):
        self.before=preferences.settings_dict()
        self.addCleanup(preferences.set_preferences,self.before)
        preferences.load_preferences({})

    def test_old_bass_default_is_dropped_and_current_defaults_are_preserved(self):
        for old_bass in (True,0,128,'61',57,None):
            with self.subTest(old_bass=old_bass):
                preferences.load_preferences({'default_velocities':{'melody':41,'harmony':109,'bass':old_bass}})
                self.assertEqual(preferences.settings_dict()['default_velocities'],{'melody':41,'instrument':41,'harmony':109})

    def test_settings_confirm_and_cancel_save_independent_track_defaults(self):
        dialog=DynamicsSettingsDialog([48,72,96],{});self.addCleanup(dialog.close)
        dialog.melody_velocity.setValue(53);dialog.instrument_velocity.setValue(61);dialog.chord_velocity.setValue(104)
        self.assertEqual(preferences.default_velocity('harmony'),72)
        values=dialog.value();dialog.reject()
        self.assertEqual(preferences.default_velocity('harmony'),72)
        preferences.set_preferences(values)
        self.assertEqual(preferences.settings_dict()['default_velocities'],{'melody':53,'instrument':61,'harmony':104})
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as directory:
            save_preferences(directory,preferences.settings_dict())
            preferences.load_preferences(load_preferences(directory))
            self.assertEqual(preferences.settings_dict()['default_velocities'],{'melody':53,'instrument':61,'harmony':104})


class CrossRegionJoinTests(unittest.TestCase):
    def test_joining_adjacent_notes_retains_regions_and_produces_one_midi_onset(self):
        project=Project()
        project.chords=[Chord(0,960,notes=[Note(0,960,60,81)]),Chord(960,960,notes=[Note(0,960,60,96)])]
        regions=[(c.id,c.start,c.duration) for c in project.chords]
        selected=project.harmony_notes()
        self.assertTrue(can_join(selected))
        joined=join_notes(selected)
        project.set_harmony_notes(joined)
        self.assertEqual([(c.id,c.start,c.duration) for c in project.chords[:2]],regions)
        actual=project.harmony_notes()
        self.assertEqual([(n.start,n.duration,n.pitch,n.velocity) for n in actual],[(0,1920,60,81)])
        self.assertEqual([c.notes[0].event_id for c in project.chords[:2]],[joined[0].id]*2)
        self.assertEqual([e for e in event_list(project) if e[1]==1],[(0,1,1,60,81)])
        project.validate()


if __name__=='__main__':unittest.main()

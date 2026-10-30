"""Playback deadlines remain independent of editor work and Python's GIL."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from popscore.playback import PlaybackSchedule, ProcessRouter, window_events


class FileRouter:
    """Spawn-safe output probe: records actual child dispatch timestamps."""
    def __init__(self, settings):
        self.path = Path(settings['log'])
        self.file = self.path.open('w', encoding='utf-8')

    def send(self, status, a=0, b=0):
        self.file.write(json.dumps((time.perf_counter(), status, a, b)) + '\n')
        self.file.flush()

    def close(self):
        self.file.close()
        self.path.with_suffix('.closed').write_text('closed', encoding='utf-8')


class BrokenRouter:
    def __init__(self, settings):
        raise RuntimeError('output unavailable')


class FailingNoteRouter(FileRouter):
    def send(self, status, a=0, b=0):
        if status & 0xf0 == 0x90:
            raise RuntimeError('device disconnected')
        super().send(status, a, b)


class MissingPackOnProgramRouter(FileRouter):
    def send(self, status, a=0, b=0):
        if status & 0xf0 == 0xc0:
            from popscore.soundbanks import pack
            pack('synth:no-such-pack')
        super().send(status, a, b)


def language_probe_synthesis_worker(*args):
    """Run the real pipe protocol in a real child without requiring hardware."""
    from unittest.mock import MagicMock, patch
    from popscore.synthesis import _synthesis_worker

    class Engine:
        def __init__(self, **kwargs):
            pass
        def send(self, status, program=0, velocity=0):
            if status & 0xf0 == 0xc0 and program == 127:
                from popscore.soundbanks import pack
                pack('synth:no-such-pack')
        def close(self):
            pass

    player = MagicMock()
    player.buffersize = player.currentpadding = 4096
    player.deviceperiod = (.01, .003)
    with patch('popscore.synthesis.SynthEngine', Engine), patch('popscore.exporting._com_apartment'), patch('soundcard.default_speaker') as speaker:
        speaker.return_value.player.return_value.__enter__.return_value = player
        _synthesis_worker(*args)


class Probe:
    def __init__(self):
        self.now = 0
        self.events = []

    def send(self, *event):
        self.events.append(event)


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.probe = Probe()
        self.schedule = PlaybackSchedule(self.probe, lambda: self.probe.now)

    def test_revision_keeps_sustains_and_releases_only_deleted_notes(self):
        s, p = self.schedule, self.probe
        s.play([(0, 1, 0, 60, 80), (100, 0, 0, 60, 0)], .01, 0, 200, False, 0)
        s.advance()
        p.events.clear()
        p.now = .25
        s.revise(sorted([(0, 1, 0, 60, 80), (100, 0, 0, 60, 0),
                         (50, 1, 1, 67, 90), (75, 0, 1, 67, 0)]), .01, 200, False, 0)
        self.assertFalse(p.events)
        self.assertEqual(s.epoch, 0)
        p.now = .5
        s.advance()
        self.assertEqual(p.events, [(0x91, 67, 90)])
        s.revise([(50, 1, 1, 67, 90), (75, 0, 1, 67, 0)], .01, 200, False, 0)
        self.assertEqual(p.events[-1], (0x80, 60))

    def test_tempo_and_loop_changes_keep_position_and_song_continuation(self):
        s, p = self.schedule, self.probe
        events = [(0, 1, 0, 60, 80), (150, 0, 0, 60, 0)]
        s.play(events, .01, 0, 100, True, 0)
        s.advance()
        p.now = .25
        s.revise(events, .005, 200, False, 0)
        self.assertEqual(s.position(), 25)
        p.now = .5
        self.assertEqual(s.position(), 75)
        s.advance()
        self.assertTrue(s.playing)
        self.assertFalse(s.loop)
        self.assertEqual(p.events[-1], (0x90, 60, 80))

    def test_loop_clock_does_not_accumulate_late_wakeup_drift(self):
        s, p = self.schedule, self.probe
        s.play([(0, 1, 0, 60, 80)], .01, 0, 100, True, 0)
        for now in (1.007, 2.011, 3.006):
            p.now = now
            s.advance()
            self.assertEqual(s.epoch, int(now))
            s.advance()
        self.assertAlmostEqual(s.position(), .6)
        p.now = 6.01
        s.advance()
        self.assertEqual(s.epoch, 6)

    def test_recording_replaces_next_loop_without_replaying_current_take(self):
        s, p = self.schedule, self.probe
        s.play([(0, 1, 0, 60, 80)], .01, 0, 100, True, 0)
        s.advance()
        p.events.clear()
        s.refresh_recording([(0, 1, 0, 67, 90)])
        s.advance()
        self.assertFalse(p.events)
        p.now = 1
        s.advance()
        s.advance()
        self.assertEqual(p.events[-1], (0x90, 67, 90))

    def test_left_edge_note_off_does_not_restart_old_sustain(self):
        events = [(0, 1, 0, 60, 80), (100, 0, 0, 60, 0),
                  (100, 1, 0, 60, 90), (200, 0, 0, 60, 0)]
        self.assertEqual(window_events(events, 100, 200), events[1:3])
        self.assertEqual(window_events(events, 50, 100), [(50, 1, 0, 60, 80)])


class ProcessTests(unittest.TestCase):
    def test_midi_deadlines_continue_while_gui_process_holds_gil(self):
        with tempfile.TemporaryDirectory(dir='tmp') as directory:
            path = Path(directory).resolve() / 'events.jsonl'
            router = ProcessRouter({'log': str(path)}, FileRouter)
            process = router.process
            try:
                # Six onsets and releases fall wholly within a deliberate
                # editor-process GIL stall, longer than an audio buffer.
                events = []
                for i in range(6):
                    events.extend([(30 + i * 40, 1, 0, 60 + i, 80),
                                   (50 + i * 40, 0, 0, 60 + i, 0)])
                state = router.play_schedule(sorted(events), .001, 0, 500, False, 0)
                epoch = state[3]
                interval = sys.getswitchinterval()
                try:
                    sys.setswitchinterval(1)
                    deadline = time.perf_counter() + .32
                    while time.perf_counter() < deadline:
                        pass
                finally:
                    sys.setswitchinterval(interval)
                router.stop_schedule()
                recorded = [json.loads(line) for line in path.read_text('utf-8').splitlines()]
                notes = [e for e in recorded if e[1] & 0xf0 in (0x80, 0x90)]
                self.assertEqual(len(notes), len(events))
                for actual, expected in zip(notes, sorted(events)):
                    tick, on, channel, pitch, velocity = expected
                    self.assertEqual(actual[1:], [(0x90 if on else 0x80) | channel, pitch, velocity])
                    self.assertLess(abs(actual[0] - epoch - tick * .001), .08)
            finally:
                router.close()
            self.assertTrue(path.with_suffix('.closed').exists())
            self.assertIsNone(router.process)
            self.assertTrue(process._closed)

    def test_startup_device_error_releases_process(self):
        with self.assertRaisesRegex(RuntimeError, 'output unavailable'):
            ProcessRouter({}, BrokenRouter)

    def test_transport_revises_worker_and_preserves_audition_channels_on_stop(self):
        from popscore.audio import Transport
        from popscore.model import Project, Note
        with tempfile.TemporaryDirectory(dir='tmp') as directory:
            path = Path(directory).resolve() / 'events.jsonl'
            router = ProcessRouter({'log': str(path)}, FileRouter)
            t = Transport()
            t.synth = router
            p = Project()
            p.audio = t.settings
            p.bpm = 300
            p.notes = [Note(0, 3840, 60)]
            try:
                t.play(p)
                epoch = t.start_time
                p.notes.append(Note(1920, 120, 64))
                t.revise(p)
                # A synchronization reply follows the revision on the pipe.
                router.send(0xc2, 0)
                self.assertEqual(t.start_time, epoch)
                self.assertTrue(t.playing)
                before = len(path.read_text('utf-8').splitlines())
                t.stop(preserve_auditions=True)
                self.assertFalse(router.clock_state()[0])
                recorded = [json.loads(line) for line in path.read_text('utf-8').splitlines()]
                self.assertFalse(any(e[1] == 0xb2 and e[2] == 123 for e in recorded[before:]))
            finally:
                t.close()


class ProcessLanguageTests(unittest.TestCase):
    message = '合成音源“{0}”未安装或已更改，请复制音源文件夹后在设置中重新扫描。'

    def setUp(self):
        from popscore import i18n
        self.language = i18n.LANGUAGE

    def tearDown(self):
        from popscore.i18n import set_language
        set_language(self.language)

    def test_playback_spawn_formats_missing_pack_in_ui_language(self):
        from popscore.i18n import set_language, tr
        set_language('en')
        settings = {key: dict(device='synth:no-such-pack', program=0) for key in ('melody', 'chords')}
        with self.assertRaises(RuntimeError) as caught:
            ProcessRouter(settings)
        self.assertEqual(str(caught.exception), tr(self.message, 'synth:no-such-pack'))
        self.assertNotIn('未安装', str(caught.exception))

    def test_native_spawn_formats_missing_pack_in_ui_language(self):
        from popscore.i18n import set_language, tr
        from popscore.synthesis import NativeSynth
        set_language('en')
        with self.assertRaises(RuntimeError) as caught:
            NativeSynth({0: 'synth:no-such-pack'}, {0: 0})
        self.assertEqual(str(caught.exception), tr(self.message, 'synth:no-such-pack'))

    def test_open_playback_worker_uses_language_of_each_command(self):
        from popscore.i18n import set_language, tr
        for initial, changed in (('zh', 'en'), ('en', 'zh')):
            with self.subTest(initial=initial, changed=changed), tempfile.TemporaryDirectory(dir='tmp') as directory:
                set_language(initial)
                router = ProcessRouter({'log': str(Path(directory).resolve() / 'events.jsonl')}, MissingPackOnProgramRouter)
                try:
                    set_language(changed)
                    with self.assertRaises(RuntimeError) as caught:
                        router.send(0xc0, 127)
                    self.assertEqual(str(caught.exception), tr(self.message, 'synth:no-such-pack'))
                finally:
                    router.close()

    def test_open_native_worker_uses_language_of_each_command(self):
        from unittest.mock import patch
        from popscore.i18n import set_language, tr
        from popscore.synthesis import NativeSynth
        for initial, changed in (('zh', 'en'), ('en', 'zh')):
            with self.subTest(initial=initial, changed=changed):
                set_language(initial)
                with patch('popscore.synthesis._synthesis_worker', language_probe_synthesis_worker):
                    native = NativeSynth({0: 'synth:probe'}, {0: 1})
                try:
                    set_language(changed)
                    with self.assertRaises(RuntimeError) as caught:
                        native.send(0xc0, 127)
                    self.assertEqual(str(caught.exception), tr(self.message, 'synth:no-such-pack'))
                finally:
                    native.close()

    def test_device_failure_can_stop_close_and_reopen_without_stuck_worker(self):
        from popscore.audio import Transport
        from popscore.model import Project, Note
        with tempfile.TemporaryDirectory(dir='tmp') as directory:
            path = Path(directory).resolve() / 'events.jsonl'
            t = Transport()
            router = ProcessRouter({'log': str(path)}, FailingNoteRouter)
            t.synth = router
            p = Project()
            p.audio = t.settings
            p.notes = [Note(0, 960, 60)]
            try:
                t.play(p)
                limit = time.perf_counter() + 2
                while not router.failure and time.perf_counter() < limit:
                    time.sleep(.005)
                self.assertEqual(router.failure, 'device disconnected')
                t.stop()
                self.assertFalse(t.playing)
                self.assertIsNone(t.synth)
                self.assertIsNone(router.process)
                self.assertTrue(path.with_suffix('.closed').exists())
                # Device selection is retained, so another output can be opened.
                t.synth = ProcessRouter({'log': str(path)}, FileRouter)
                t.play(p)
                self.assertTrue(t.playing)
            finally:
                t.close()


if __name__ == '__main__':
    unittest.main()

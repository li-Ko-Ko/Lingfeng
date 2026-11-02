"""Sample pack containment, preference migration and actual sfizz rendering."""
import copy
import hashlib
import json
import os
import shutil
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import numpy as np

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import lingfeng.audio.soundbanks as banks
from lingfeng.audio.exporting import offline_pcm
from lingfeng.audio.synthesis import SynthEngine, RATE
from lingfeng.music.model import Project, Note

ROOT = Path(__file__).resolve().parents[1]
DLL = banks.default_root() / 'piano-small/sfizz.dll'


class SamplePackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'tmp')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.folder = self.base / 'synths/piano-small'
        self.folder.mkdir(parents=True)
        for name, value in [('default_root', self.base / 'synths'), ('cache_path', self.base / 'index.json')]:
            item = patch.object(banks, name, return_value=value)
            item.start(); self.addCleanup(item.stop)
        banks._state = None
        self.addCleanup(setattr, banks, '_state', None)
        self.addCleanup(self.unload_library)
        # Only use the distributed runtime; public tests need no local archives.
        shutil.copy2(DLL, self.folder / 'sfizz.dll')
        (self.folder / 'LICENSE.txt').write_text('Test waveform generated mathematically; sfizz BSD-2-Clause.', 'utf-8')
        signal = (np.sin(np.arange(RATE) * (2 * np.pi * 440 / RATE)) * 8192).astype('<i2')
        with wave.open(str(self.folder / 'tone.wav'), 'wb') as file:
            file.setnchannels(1); file.setsampwidth(2); file.setframerate(RATE); file.writeframes(signal.tobytes())
        (self.folder / 'piano.sfz').write_text('<region> sample=tone.wav pitch_keycenter=60 loop_mode=loop_continuous loop_start=0 loop_end=44099 ampeg_release=0.03', 'utf-8')
        self.manifest = dict(schema=1, abi=1, platform='windows-x64', id='piano-small', engine='sfz',
            name='测试钢琴', name_en='Test piano', version='test', license='Test waveform / BSD-2-Clause engine',
            license_file='LICENSE.txt', author='Lingfeng test', source='https://sfz.tools/sfizz/',
            library='sfizz.dll', sha256=hashlib.sha256((self.folder / 'sfizz.dll').read_bytes()).hexdigest(), voices=256,
            presets=[dict(program=p, model=0, name='测试', name_en='Test', gain=1, sfz='piano.sfz') for p in (0, 1, 4)])
        self.write_manifest()
        self.assertFalse(banks.rescan()['errors'])

    def unload_library(self):
        # The production host intentionally retains DLLs for its lifetime.
        # Release only this fixture's library after all engine cleanups, so
        # Windows can remove its isolated temporary pack directory.
        import _ctypes
        from lingfeng.audio.synthesis import _libraries, _library_lock
        with _library_lock:
            for key in list(_libraries):
                if Path(key[0]).is_relative_to(self.base):
                    lib = _libraries.pop(key)
                    _ctypes.FreeLibrary(lib._handle)

    def write_manifest(self):
        (self.folder / 'synth.json').write_text(json.dumps(self.manifest), 'utf-8')

    def engine(self):
        engine = SynthEngine('synth:piano-small', offline=True)
        engine.send(0xc0, 0)
        self.addCleanup(engine.close)
        return engine

    def test_new_projects_prefer_small_pack_but_saved_choices_survive(self):
        expected = {'melody': dict(device='synth:piano-small', program=1), 'chords': dict(device='synth:piano-small', program=0)}
        self.assertEqual(banks.default_audio(), expected)
        saved = {role: dict(device='default', program=5) for role in ('melody', 'chords')}
        banks.save_defaults(saved); banks._state = None
        self.assertEqual(banks.default_audio(), saved)
        self.assertEqual(Project().audio, saved)

    def test_native_pack_remains_fallback_without_sample_pack(self):
        self.manifest['id'] = 'test-piano'; self.write_manifest()
        shutil.copytree(DLL.parent.parent / 'stk-essentials', self.base / 'synths/stk-essentials')
        banks.rescan()
        self.assertEqual(banks.default_audio()['melody'], dict(device=banks.DEFAULT_DEVICE, program=1))

    def test_in_place_upgrade_rescans_new_bundled_packs_once_and_keeps_settings(self):
        from lingfeng import __version__
        extra=self.base/'extra';extra.mkdir()
        state=banks.registry()
        state['roots'].append(str(extra))
        saved={role:dict(device='default',program=5) for role in ('melody','chords')}
        state.update(app_version='0.51',packs={},defaults=saved)
        banks._write(state);banks._state=None
        with patch.object(banks,'rescan',wraps=banks.rescan) as scan:
            upgraded=banks.registry()
            scan.assert_called_once()
        self.assertEqual(upgraded['app_version'],__version__)
        self.assertIn('piano-small',upgraded['packs'])
        self.assertIn(str(extra),upgraded['roots'])
        self.assertEqual(banks.default_audio(),saved)
        banks._state=None
        with patch.object(banks,'rescan',side_effect=AssertionError('Upgrade must scan only once')):
            self.assertEqual(banks.default_audio(),saved)

    def test_manifest_and_mapping_paths_cannot_escape_pack(self):
        outside = self.base / 'outside.wav'; shutil.copy2(self.folder / 'tone.wav', outside)
        original = (self.folder / 'piano.sfz').read_text('utf-8')
        for sample in ('../../outside.wav', str(outside), 'tone.wav:stream'):
            with self.subTest(sample=sample):
                (self.folder / 'piano.sfz').write_text('<region> sample=' + sample, 'utf-8')
                self.assertFalse(banks.rescan()['packs'])
        (self.folder / 'piano.sfz').write_text(original, 'utf-8')
        for field, value in [('sfz', '../outside.sfz'), ('sfz', 'C:outside.sfz')]:
            self.manifest['presets'][0][field] = value; self.write_manifest()
            self.assertFalse(banks.rescan()['packs'])

    def test_includes_default_paths_and_macros_are_checked(self):
        (self.folder / 'maps').mkdir()
        (self.folder / 'maps/region.sfz').write_text('<region> sample=$WAVE', 'utf-8')
        (self.folder / 'piano.sfz').write_text('#define $WAVE tone.wav\n#include "maps/region.sfz"', 'utf-8')
        self.assertFalse(banks.rescan()['errors'])
        (self.folder / 'maps/region.sfz').write_text('#include "../piano.sfz"', 'utf-8')
        self.assertFalse(banks.rescan()['packs'])
        (self.folder / 'piano.sfz').write_text('<control> default_path=../../\n<region> sample=tone.wav', 'utf-8')
        self.assertFalse(banks.rescan()['packs'])

    def test_cached_library_paths_are_validated_and_changed_mapping_is_rechecked_before_play(self):
        state = json.loads((self.base / 'index.json').read_text('utf-8'))
        state['packs']['piano-small']['library'] = '../outside.dll'
        (self.base / 'index.json').write_text(json.dumps(state), 'utf-8'); banks._state = None
        self.assertEqual(banks.registry()['packs']['piano-small']['library'], 'sfizz.dll')
        (self.folder / 'piano.sfz').write_text('<region> sample=../../outside.wav', 'utf-8')
        with self.assertRaises(ValueError): self.engine()

    def test_actual_render_edge_keys_and_large_polyphony(self):
        engine = self.engine(); voice = engine.channels[0]
        self.assertEqual(voice.api.sfizz_get_num_voices(voice.handle), 256)
        for key in (21, 36, 60, 84, 108):
            engine.stop(); engine.send(0x90, key, 100); data = engine.render(4096)
            self.assertTrue(np.isfinite(data).all()); self.assertGreater(float(abs(data).max()), 1e-4)
        engine.stop(); self.assertFalse(engine.render(512).any())

    def test_sample_and_native_channels_mix_and_stop_independently(self):
        shutil.copytree(DLL.parent.parent / 'stk-essentials', self.base / 'synths/stk-essentials')
        banks.rescan()
        engine = SynthEngine(channel_devices={0: 'synth:piano-small', 1: banks.DEFAULT_DEVICE}, offline=True)
        self.addCleanup(engine.close)
        engine.send(0xc0, 0); engine.send(0xc1, 40)
        engine.send(0x90, 60, 100); engine.send(0x91, 67, 100)
        self.assertGreater(float(abs(engine.render(4096)).max()), .01)
        engine.send(0xb0, 120, 0)
        self.assertGreater(float(abs(engine.render(4096)).max()), 1e-4)
        engine.stop(); self.assertFalse(engine.render(512).any())

    def test_sustain_volume_expression_pan_and_pitch_bend(self):
        engine = self.engine(); engine.send(0x90, 60, 100); engine.render(512)
        engine.send(0xb0, 64, 127); engine.send(0x80, 60)
        self.assertGreater(float(abs(engine.render(8192)).max()), .01)
        engine.send(0xb0, 7, 0); self.assertFalse(engine.render(512).any())
        engine.send(0xb0, 7, 100); engine.send(0xb0, 11, 0); self.assertFalse(engine.render(512).any())
        engine.send(0xb0, 11, 127); engine.send(0xb0, 10, 0)
        data = engine.render(512); self.assertTrue(data[:, 0].any()); self.assertFalse(data[:, 1].any())
        engine.send(0xb0, 10, 127)
        data = engine.render(512); self.assertFalse(data[:, 0].any()); self.assertTrue(data[:, 1].any())
        engine.send(0xb0, 64, 0); engine.render(16384); self.assertLess(float(abs(engine.render(512)).max()), 1e-5)
        engine.stop(); engine.send(0xb0, 10, 64); engine.send(0xe0, 127, 127); engine.send(0x90, 60, 100)
        data = engine.render(32768)[:, 0]
        frequency = np.fft.rfftfreq(len(data), 1 / RATE)[np.argmax(abs(np.fft.rfft(data)))]
        self.assertAlmostEqual(frequency, 493.88, delta=4)

    def test_offline_export_has_sample_exact_note_timing_and_credits(self):
        project = Project(); project.notes = [Note(960, 240, 60, 100)]
        project.audio = {role: dict(device='synth:piano-small', program=0) for role in ('melody', 'chords')}
        before = copy.deepcopy(project.to_dict())
        pcm = np.frombuffer(b''.join(offline_pcm(project, 'melody', 0, 1920, threading.Event(), lambda n: None)), '<i2').reshape(-1, 2)
        onset = round(60 / project.bpm * RATE)
        self.assertFalse(pcm[:onset].any()); self.assertTrue(pcm[onset:onset + 512].any())
        self.assertTrue(np.isfinite(pcm).all()); self.assertEqual(before, project.to_dict())
        self.assertIn('piano-small', banks.credits_text(project, 'melody', 0, 1920, 'offline'))


if __name__ == '__main__': unittest.main()

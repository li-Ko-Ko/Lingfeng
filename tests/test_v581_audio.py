"""Independent devices, programs and levels for the three musical tracks."""
import os
import time
import unittest
from unittest.mock import Mock, call, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from lingfeng.audio import calibration
from lingfeng.audio.events import ROUTED_CHANNELS
from lingfeng.audio.routing import MidiRouter
from lingfeng.audio.transport import Transport
from lingfeng.music.model import Project
from lingfeng.ui.sound_dialog import SoundSettingsDialog


APP = QApplication.instance() or QApplication([])


def settings():
    return {'melody': dict(device='Voice', program=1),
            'chords': dict(device='Harmony', program=0),
            'instrument': dict(device='Lead', program=40)}


def calibration_settings():
    return {'melody': dict(device='synth:fixture', program=0, gain_db=3),
            'chords': dict(device='synth:fixture', program=1, gain_db=-2),
            'instrument': dict(device='synth:fixture', program=2)}


def calibration_pack():
    return dict(id='fixture', name='Fixture', name_en='Fixture', path='synths/fixture',
                engine='native', author='Test', license='MIT',
                preset_gain_db={'0': 2, '1': -1, '2': 4},
                presets=[dict(program=i, name=f'Preset {i}', name_en=f'Preset {i}') for i in range(3)])


class ThreeTrackAudioTests(unittest.TestCase):
    def test_new_project_levels_put_melodies_ahead_of_harmony(self):
        self.assertEqual(Project().volumes, dict(melody=100, instrument=84, chords=76))

    def test_old_project_copies_previous_melody_device_and_level(self):
        data = Project().to_dict()
        data['audio'] = dict(melody=dict(device='samples', program=24), chords=dict(device='default', program=0))
        data['volumes'] = dict(melody=71, chords=32)
        project = Project.from_dict(data)
        self.assertEqual(project.audio['instrument'], dict(device='synth:stk-essentials', program=24))
        self.assertIsNot(project.audio['melody'], project.audio['instrument'])
        self.assertEqual(project.volumes, dict(melody=71, chords=32, instrument=71))
        project.audio['instrument'] = dict(device='Lead', program=40)
        project.volumes['instrument'] = 23
        restored = Project.from_dict(project.to_dict())
        self.assertEqual(restored.audio, project.audio)
        self.assertEqual(restored.volumes, dict(melody=71, chords=32, instrument=23))
        self.assertNotIn('instrument', data['audio'])

    def test_router_uses_each_roles_device_on_all_its_channels(self):
        outputs = {index: Mock() for index in range(3)}
        devices = [(0, 'Voice'), (1, 'Harmony'), (2, 'Lead')]
        with patch('lingfeng.audio.routing.midi_devices', return_value=devices), \
             patch('lingfeng.audio.routing.Synth', side_effect=outputs.__getitem__):
            router = MidiRouter(settings())
            try:
                self.assertEqual({channel: router.routes[channel] for channel in (6, 7, 8)},
                                 {channel: outputs[2] for channel in (6, 7, 8)})
                for channel in ROUTED_CHANNELS['instrument']:
                    outputs[2].send.assert_any_call(0xc0 | channel, 40, 0)
                self.assertIs(router.routes[0], outputs[0])
                self.assertIs(router.routes[1], outputs[1])
            finally:
                router.close()

    def test_level_and_preview_controls_follow_the_instrument_role(self):
        transport = Transport()
        transport.settings = settings()
        transport.synth = Mock()
        output = transport.synth
        self.addCleanup(transport.close)
        transport.set_volumes(dict(melody=72, chords=52, instrument=0))
        self.assertIn(call(0xb0, 7, 72), output.send.call_args_list)
        self.assertIn(call(0xb1, 7, 52), output.send.call_args_list)
        for channel in (6, 7, 8):
            self.assertIn(call(0xb0 | channel, 7, 0), output.send.call_args_list)
        changed = settings()
        changed['instrument']['program'] = 52
        output.reset_mock()
        transport.configure(changed)
        self.assertEqual(output.send.call_args_list, [call(0xc0 | channel, 52) for channel in (6, 7, 8)])
        transport.begin_audition([65], role='instrument')
        transport.end_audition(role='instrument', cancel=True)
        transport.monitor(67, 83, 'instrument')
        transport.monitor(67, 0, 'instrument')
        for message in (call(0x97, 65, 80), call(0x87, 65), call(0x98, 67, 83), call(0x88, 67, 0)):
            self.assertIn(message, output.send.call_args_list)

    def test_source_gain_updates_native_preview_and_playback_channels_only(self):
        config=settings()
        config['melody']['gain_db']=7
        config['instrument']=dict(device='synth:stk-essentials',program=1,gain_db=-4.5)
        devices=[(0,'Voice'),(1,'Harmony')]
        with patch('lingfeng.audio.routing.midi_devices', return_value=devices), \
             patch('lingfeng.audio.routing.Synth') as windows, \
             patch('lingfeng.audio.synthesis.NativeSynth') as native:
            router=MidiRouter(config)
            transport=Transport()
            transport.settings=config
            transport.synth=router
            self.addCleanup(transport.close)
            native.return_value.set_source_gains.assert_called_once_with({6:-4.5,7:-4.5,8:-4.5})
            native.return_value.reset_mock()
            windows.return_value.reset_mock()
            changed={**config,'instrument':dict(device='synth:stk-essentials',program=1)}
            transport.configure(changed)
            self.assertIs(transport.synth,router)
            native.return_value.set_source_gains.assert_called_once_with({6:0,7:0,8:0})
            native.return_value.send.assert_not_called()
            windows.return_value.send.assert_not_called()

    def test_sound_settings_show_named_tracks_with_separate_preview(self):
        owner = QWidget()
        self.addCleanup(owner.deleteLater)
        owner.project = Project(audio=settings(), melody_names=['Singer', 'Lead synth'])
        devices = [(0, 'Voice'), (1, 'Harmony'), (2, 'Lead')]
        with patch('lingfeng.audio.routing.midi_devices', return_value=devices), \
             patch('lingfeng.ui.sound_dialog.banks.installed_packs', return_value=[]), \
             patch('lingfeng.audio.routing.MidiRouter') as router:
            dialog = SoundSettingsDialog(owner.project.audio, owner)
            try:
                self.assertEqual(dialog.track_tabs.tabText(0), 'Singer')
                self.assertEqual(dialog.track_tabs.tabText(1), 'Lead synth')
                self.assertEqual(dialog.value(), settings())
                dialog.preview('instrument')
                router.return_value.send.assert_any_call(0x97, 60, 75)
            finally:
                dialog.reject()

    def test_calibration_increases_only_the_quieter_tracks_and_reports_the_cap(self):
        config = calibration_settings()
        with patch('lingfeng.audio.soundbanks.pack', return_value=calibration_pack()), \
             patch.object(calibration, '_runtime_files', return_value={'fixture.dll': 'fixture-hash'}), \
             patch.object(calibration, '_probe_presets', return_value={0: -24, 1: -26, 2: -60}):
            gains, skipped, capped = calibration.calibrate_tracks(config)
        # The loudest track measures -19 dBFS after its existing +5 dB. The
        # harmony needs another 10 dB. The lead cannot reach -19 within +24 dB.
        self.assertEqual(gains, dict(melody=3, chords=8, instrument=24))
        self.assertEqual(skipped, {})
        self.assertEqual(capped, ('instrument',))
        self.assertEqual(config, calibration_settings())

    def test_calibration_needs_two_measurable_tracks_to_change_gains(self):
        config = calibration_settings()
        config['chords'] = dict(device='default', program=0)
        with patch('lingfeng.audio.soundbanks.pack', return_value=calibration_pack()), \
             patch.object(calibration, '_runtime_files', return_value={'fixture.dll': 'fixture-hash'}), \
             patch.object(calibration, '_probe_presets', return_value={0: -24, 2: None}):
            gains, skipped, capped = calibration.calibrate_tracks(config)
        self.assertEqual(gains, {})
        self.assertEqual(skipped, dict(chords='unsupported', instrument='silent'))
        self.assertEqual(capped, ())

    def test_track_calibration_admits_only_the_pinned_pfsynth_runtime(self):
        digest = '362c7e9a931fa48286aa84e3270fcb0f18d15c716f4b1dedaa503d55ceade7d1'
        library = 'lingfeng-pfsynth.dll'
        pfsynth = dict(calibration_pack(), path='synths/pfsynth', library=library, sha256=digest)
        packs = {'synth:pfsynth': pfsynth, 'synth:other': dict(pfsynth, sha256='0' * 64)}
        config = {'melody': dict(device='synth:pfsynth', program=0),
                  'chords': dict(device='synth:pfsynth', program=0, gain_db=-6),
                  'instrument': dict(device='synth:other', program=0)}
        with patch('lingfeng.audio.soundbanks.pack', side_effect=packs.__getitem__), \
             patch.object(calibration, '_probe_presets', return_value={0: -30}) as probe:
            gains, skipped, capped = calibration.calibrate_tracks(config)
        probe.assert_called_once()
        self.assertEqual(probe.call_args.args[2], {library: digest})
        self.assertEqual(gains, dict(melody=0, chords=0))
        self.assertEqual(skipped, dict(instrument='untrusted'))
        self.assertEqual(capped, ())

    def test_calibration_does_not_keep_boosting_unchanged_measurements(self):
        config = calibration_settings()
        with patch('lingfeng.audio.soundbanks.pack', return_value=calibration_pack()), \
             patch.object(calibration, '_runtime_files', return_value={'fixture.dll': 'fixture-hash'}), \
             patch.object(calibration, '_probe_presets', return_value={0: -24, 1: -16.06, 2: -23.12}):
            first, _, _ = calibration.calibrate_tracks(config)
            for role, gain in first.items():
                config[role]['gain_db'] = gain
            repeated, _, _ = calibration.calibrate_tracks(config)
        self.assertEqual(first, dict(melody=3, chords=-2, instrument=.1))
        self.assertEqual(repeated, first)

    def test_calibration_fills_editable_gains_and_audition_uses_current_values(self):
        config = calibration_settings()
        fixture = calibration_pack()
        result = dict(melody=3, chords=8, instrument=12), {}, ()
        with patch('lingfeng.audio.routing.midi_devices', return_value=[]), \
             patch('lingfeng.audio.routing.MidiRouter') as router, \
             patch('lingfeng.ui.sound_dialog.banks.installed_packs', return_value=[fixture]), \
             patch('lingfeng.ui.sound_dialog.banks.registry', return_value=dict(roots=[], errors=[])), \
             patch('lingfeng.ui.sound_dialog.banks.pack', return_value=fixture), \
             patch.object(calibration, 'calibrate_tracks', return_value=result) as auto_calibrate, \
             patch('lingfeng.ui.sound_dialog.banks.save_defaults') as save:
            dialog = SoundSettingsDialog(config)
            try:
                self.assertTrue(dialog.calibration_button.isEnabled())
                dialog.calibration_button.click()
                deadline = time.monotonic() + 5
                while dialog.calibration_worker is not None and time.monotonic() < deadline:
                    QTest.qWait(10)
                self.assertIsNone(dialog.calibration_worker)
                auto_calibrate.assert_called_once()
                self.assertEqual(auto_calibrate.call_args.args[0], config)
                self.assertEqual({k: v['gain_db'] for k, v in dialog.value().items()}, result[0])
                self.assertEqual(config, calibration_settings())
                save.assert_not_called()

                gain = dialog.gain_fields['instrument']
                self.assertTrue(gain.isEnabled())
                gain.lineEdit().setText(gain.locale().toString(5.5, 'f', 1) + gain.suffix())
                self.assertEqual(gain.value(), 12)
                dialog.preview('instrument')
                expected = dict(device='synth:fixture', program=2, gain_db=5.5)
                self.assertEqual(router.call_args.args[0], {role: expected for role in ROUTED_CHANNELS})
                router.return_value.send.assert_any_call(0xB7, 7, 100)
                router.return_value.send.assert_any_call(0x97, 60, 75)
            finally:
                dialog.reject()
                dialog.deleteLater()
                APP.processEvents()

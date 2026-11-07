"""Independent devices, programs and levels for the three musical tracks."""
import os
import unittest
from unittest.mock import Mock, call, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QWidget

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

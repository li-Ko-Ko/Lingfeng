"""Device-independent MIDI event windows and owned-channel silence policy."""
from copy import copy

from lingfeng.platform.i18n import tr

TRACK_ROLES = ('melody', 'chords', 'instrument')
DEFAULT_VOLUMES = {'melody': 100, 'chords': 76, 'instrument': 84}
MIN_SOURCE_GAIN_DB = -24
MAX_SOURCE_GAIN_DB = 24
INSTRUMENT_CHANNEL = 6
ROUTED_CHANNELS = {'melody': (0, 2, 4), 'chords': (1, 3, 5), 'instrument': (INSTRUMENT_CHANNEL, 7, 8)}
PLAYBACK_CHANNELS = tuple(channels[0] for channels in ROUTED_CHANNELS.values())
AUDITION_CHANNELS = {role: channels[1] for role, channels in ROUTED_CHANNELS.items()}
MONITOR_CHANNELS = {role: channels[2] for role, channels in ROUTED_CHANNELS.items()}
PREVIEW_CHANNELS = tuple(channel for channels in ROUTED_CHANNELS.values() for channel in channels[1:])


def source_gain_db(spec):
    """Read the optional per-track gain for synthesized audio."""
    value = spec.get('gain_db', 0)
    if type(value) not in (int, float) or not MIN_SOURCE_GAIN_DB <= value <= MAX_SOURCE_GAIN_DB:
        raise ValueError(tr('音源增益必须是 -24 至 +24 dB 的数字。'))
    return value


def complete_track_values(values):
    """Carry forward the shared melody setting in projects with two roles."""
    if isinstance(values, dict) and values.keys() == {'melody', 'chords'}:
        return {**values, 'instrument': copy(values['melody'])}
    return values


def silence_channels(output, channels):
    """Stop only owned channels, including sustain-held voices on WinMM.

    All Notes Off alone respects the sustain pedal and release envelopes.
    Keep program, volume and other channels intact when pausing a transport.
    """
    for channel in channels:
        for controller in (64, 120, 123):
            output.send(0xb0 | channel, controller, 0)


def window_events(events, start, end):
    active = {}
    for tick, on, channel, pitch, velocity in events:
        if tick >= start:
            break
        if on:
            active[channel, pitch] = velocity
        else:
            active.pop((channel, pitch), None)
    # An off at the left edge must not briefly restart a finished sustain.
    for tick, on, channel, pitch, _ in events:
        if tick > start:
            break
        if tick == start and not on:
            active.pop((channel, pitch), None)
    result = [(start, 1, ch, pitch, vel) for (ch, pitch), vel in active.items()]
    result.extend(e for e in events if start <= e[0] < end)
    return sorted(result)

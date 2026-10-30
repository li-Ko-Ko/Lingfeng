"""Device-independent MIDI event windows and owned-channel silence policy."""


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

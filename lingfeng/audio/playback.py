"""Process-owned MIDI scheduling, independent of the editor's Python/GIL.

Only immutable MIDI schedules cross the pipe. The child owns device handles;
the shared clock contains numbers, never a Project or a Qt widget.
"""
import multiprocessing
import threading
import time

from lingfeng.platform.i18n import tr
import lingfeng.platform.i18n as i18n


from lingfeng.audio.events import silence_channels, window_events


class PlaybackSchedule:
    """Device-independent clock, shared by native and external MIDI routes."""
    def __init__(self, output, clock=time.perf_counter):
        self.output = output
        self.clock = clock
        self.playing = False
        self.active = {}
        self.events = []
        self.index = 0
        self.start = self.end = self.loop_start = 0
        self.epoch = 0
        self.seconds = 1
        self.loop = False

    def position(self, now=None):
        if now is None:
            now = self.clock()
        return self.start + (now - self.epoch) / self.seconds

    def stop(self):
        silence_channels(self.output, (0, 1))
        self.active.clear()
        self.playing = False

    def play(self, events, seconds, start, end, loop, loop_start):
        self.stop()
        self.seconds, self.start, self.end = seconds, start, end
        self.loop, self.loop_start = loop, loop_start
        self.events = window_events(events, start, end)
        self.loop_events = window_events(events, loop_start, end)
        self.index = 0
        self.epoch = self.clock()
        self.playing = True

    def revise(self, events, seconds, end, loop, loop_start):
        if not self.playing:
            return
        now = self.clock()
        tick = self.position(now)
        desired = {}
        for t, on, ch, pitch, velocity in events:
            if t > tick:
                break
            if on:
                desired[ch, pitch] = velocity
            else:
                desired.pop((ch, pitch), None)
        if tick >= end:
            desired.clear()
        # Keep unchanged sustains sounding, and release removed notes only.
        for ch, pitch in self.active.keys() - desired.keys():
            self.output.send(0x80 | ch, pitch)
        for ch, pitch in desired.keys() - self.active.keys():
            self.output.send(0x90 | ch, pitch, desired[ch, pitch])
        self.active = desired
        if seconds != self.seconds:
            self.start, self.epoch, self.seconds = tick, now, seconds
        self.end, self.loop, self.loop_start = end, loop, loop_start
        self.loop_events = window_events(events, loop_start, end)
        self.events = [e for e in events if tick < e[0] < end]
        self.index = 0

    def refresh_recording(self, events):
        if self.playing:
            self.loop_events = window_events(events, self.loop_start, self.end)

    def advance(self):
        """Dispatch due events; return a bounded wait until the next deadline."""
        if not self.playing:
            return .01
        now = self.clock()
        tick = self.position(now)
        while self.index < len(self.events) and self.events[self.index][0] <= tick:
            _, on, ch, pitch, velocity = self.events[self.index]
            self.output.send((0x90 if on else 0x80) | ch, pitch, velocity)
            if on:
                self.active[ch, pitch] = velocity
            else:
                self.active.pop((ch, pitch), None)
            self.index += 1
        if tick >= self.end:
            loop = self.loop
            self.stop()
            if not loop:
                return .01
            # Anchor to the actual boundary, avoiding cumulative loop drift.
            boundary = self.epoch + (self.end - self.start) * self.seconds
            duration = (self.end - self.loop_start) * self.seconds
            if duration <= 0:
                return .01
            boundary += max(0, int((now - boundary) / duration)) * duration
            self.start, self.epoch = self.loop_start, boundary
            self.events, self.index, self.playing = self.loop_events, 0, True
            return 0
        next_tick = self.events[self.index][0] if self.index < len(self.events) else self.end
        return min(.01, max(0, self.epoch + (next_tick - self.start) * self.seconds - self.clock()))

    def snapshot(self):
        return (float(self.playing), self.start, self.end, self.epoch, self.seconds,
                float(self.loop), self.loop_start)


def _playback_worker(connection, state, settings, router_factory=None, language='zh'):
    """Own device routing and all event deadlines until the pipe closes."""
    from lingfeng.audio.routing import MidiRouter
    output = schedule = None
    try:
        i18n.set_language(language)
        output = router_factory(settings) if router_factory else MidiRouter(settings,native_thread=True)
        schedule = PlaybackSchedule(output)
        connection.send(('ready', None))
        while True:
            wait = schedule.advance()
            with state.get_lock():
                state[:] = schedule.snapshot()
            if not connection.poll(wait):
                continue
            # A command storm must still leave time for note-off deadlines.
            command, token, args, language = connection.recv()
            i18n.set_language(language)
            if command == 'close':
                return
            if command == 'midi':
                output.send(*args)
            elif command == 'play':
                schedule.play(*args)
            elif command == 'revise':
                schedule.revise(*args)
            elif command == 'recording':
                schedule.refresh_recording(*args)
            elif command == 'stop':
                schedule.stop()
            else:
                raise ValueError('Unknown playback command')
            with state.get_lock():
                state[:] = schedule.snapshot()
            if token is not None:
                connection.send(('reply', (token, schedule.snapshot())))
    except (EOFError, BrokenPipeError):
        pass
    except Exception as exc:
        try:
            connection.send(('error', str(exc)))
        except (EOFError, BrokenPipeError, OSError):
            pass
    finally:
        with state.get_lock():
            state[0] = 0
        if output is not None:
            output.close()
        connection.close()


class ProcessRouter:
    """IPC facade for playback, auditions, MIDI monitoring and live controls."""
    def __init__(self, settings, router_factory=None):
        context = multiprocessing.get_context('spawn')
        self.state = context.Array('d', [0, 0, 0, 0, 1, 0, 0])
        self.lock = threading.RLock()
        self.pending = {}
        self.sequence = 0
        self.failure = None
        self.process = self.connection = None
        self.reader = None
        parent, child = context.Pipe()
        self.connection = parent
        try:
            # All audio work is isolated from the GUI. Native rendering uses a
            # local thread here; a daemon child cannot outlive a crashed GUI.
            self.process = context.Process(target=_playback_worker,
                args=(child, self.state, settings, router_factory,i18n.LANGUAGE), daemon=True, name='LingfengPlayback')
            self.process.start()
            child.close()
            if not parent.poll(15):
                raise RuntimeError(tr('打开合成音源超时，请检查默认音频输出设备。'))
            kind, message = parent.recv()
            if kind == 'error':
                raise RuntimeError(message)
            if kind != 'ready':
                raise RuntimeError('Unexpected playback worker response')
            self.reader = threading.Thread(target=self._listen, daemon=True, name='LingfengPlaybackReplies')
            self.reader.start()
        except Exception:
            child.close()
            self.close()
            raise

    def _listen(self):
        try:
            while True:
                kind, message = self.connection.recv()
                with self.lock:
                    if kind == 'error':
                        self.failure = message
                        break
                    token, value = message
                    reply = self.pending.get(token)
                    if reply is not None:
                        reply[1].append(value)
                        reply[0].set()
        except (EOFError, OSError, TypeError):
            pass
        finally:
            with self.lock:
                if self.failure is None:
                    self.failure = tr('音频输出进程已停止。')
                for event, _ in self.pending.values():
                    event.set()

    def _submit(self, command, args=(), wait=False):
        with self.lock:
            if self.failure:
                raise RuntimeError(self.failure)
            if self.connection is None or not self.process.is_alive():
                raise RuntimeError(tr('音频输出进程已停止。'))
            token = None
            if wait:
                self.sequence += 1
                token = self.sequence
                event, values = threading.Event(), []
                self.pending[token] = (event, values)
            try:
                self.connection.send((command, token, args,i18n.LANGUAGE))
            except (EOFError, BrokenPipeError, OSError) as exc:
                self.pending.pop(token, None)
                raise RuntimeError(tr('音频输出进程已停止。')) from exc
        if wait:
            try:
                if not event.wait(15):
                    raise RuntimeError(tr('打开合成音源超时，请检查默认音频输出设备。'))
                if not values:
                    raise RuntimeError(self.failure or tr('音频输出进程已停止。'))
                return values[0]
            finally:
                with self.lock:
                    self.pending.pop(token, None)

    def send(self, status, a=0, b=0):
        # Program changes retain synchronous validation before settings commit.
        self._submit('midi', (status, a, b), wait=status & 0xf0 == 0xc0)

    def play_schedule(self, *args):
        return self._submit('play', args, wait=True)

    def revise_schedule(self, *args):
        self._submit('revise', args)

    def refresh_recording(self, events):
        self._submit('recording', (events,))

    def stop_schedule(self):
        self._submit('stop', wait=True)

    def clock_state(self):
        with self.state.get_lock():
            return tuple(self.state[:])

    def close(self):
        connection, process = self.connection, self.process
        if connection is not None:
            try:
                with self.lock:
                    connection.send(('close', None, (),i18n.LANGUAGE))
            except (EOFError, BrokenPipeError, OSError):
                pass
        if process is not None:
            if process.pid is not None:
                process.join(timeout=3)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=2)
            process.close()
        if connection is not None:
            connection.close()
        if self.reader is not None and self.reader is not threading.current_thread():
            self.reader.join(timeout=1)
        self.process = self.connection = None

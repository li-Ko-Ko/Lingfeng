"""GUI transport proxy, auditions and in-memory output adapter support."""
import copy
import threading
import time

from PySide6.QtCore import QObject, Signal, QTimer


from lingfeng.music.model import PPQ
from lingfeng.audio.midi import event_list
from lingfeng.audio.playback import ProcessRouter, ProcessRouter as _ProcessRouter
from lingfeng.audio.events import window_events, silence_channels


class Transport(QObject):
    finished = Signal()
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.synth = None
        self.thread = None
        self.cancel = threading.Event()
        self.wake=threading.Event();self.revision_lock=threading.Lock();self.pending_revision=None
        self.schedule_signature=None;self.end_follows_project=True
        self.requested_bounds=(False,0,None)
        self.playing = False
        self.start_tick = 0
        self.end_tick = 0
        self.start_time = 0
        self.seconds_per_tick = 60 / 100 / PPQ
        self.loop = False;self.loop_events=[];self.loop_start=0;self.play_tracks=(True,True)
        self.volumes = {'melody':100,'chords':90}
        from lingfeng.audio.soundbanks import default_audio
        self.settings=default_audio()
        self.finished.connect(self._finished)
        self.audition_generations={};self.audition_notes={};self.audition_holds={}

    def open(self):
        if self.synth is None:
            self.synth = ProcessRouter(self.settings)
            self._volume_signature=None
            self.set_volumes(self.volumes)

    def configure(self,settings):
        if settings==self.settings:return
        if all(settings[k]['device']==self.settings[k]['device'] for k in ('melody','chords')):
            try:
                if self.synth:
                    for key,channels in [('melody',(0,2,4)),('chords',(1,3,5))]:
                        for channel in channels:self.synth.send(0xC0|channel,settings[key]['program'])
            except Exception:
                self.close();raise
            self.settings=copy.deepcopy(settings)
            return
        self.close()
        self.settings=copy.deepcopy(settings)

    def set_volumes(self, volumes):
        self.volumes=dict(volumes)
        if self.synth:
            signature=(id(self.synth),tuple(sorted(self.volumes.items())))
            if signature==getattr(self,'_volume_signature',None):return
            for channel,key in [(0,'melody'),(1,'chords'),(2,'melody'),(3,'chords'),(4,'melody'),(5,'chords')]:
                self.synth.send(0xB0|channel,7,self.volumes[key])
            self._volume_signature=signature

    def audition(self,pitches,harmony=False,allow_during_playback=False):
        self.begin_audition(pitches,harmony,allow_during_playback)
        self.end_audition(harmony)

    def begin_audition(self,pitches,harmony=False,allow_during_playback=True):
        if self.playing and not allow_during_playback:return
        try:
            self.cancel_auditions();self.open();ch=3 if harmony else 2
            self.audition_generations[ch]=self.audition_generations.get(ch,0)+1
            self._audition_off(ch,self.audition_notes.get(ch,[]))
            self.audition_notes[ch]=sorted(set(pitches))
            self.audition_holds[ch]=[time.monotonic(),.65,True]
            for pitch in self.audition_notes[ch]:self.synth.send(0x90|ch,pitch,80)
        except Exception as exc:self.error.emit(str(exc))

    def cancel_auditions(self):
        for channel in (2,3):
            self.audition_generations[channel]=self.audition_generations.get(channel,0)+1
            self._audition_off(channel,self.audition_notes.pop(channel,[]))
        self.audition_holds.clear()

    def begin_chord_audition(self,chord,bpm):
        """Preview the actual performed events, including rests and velocities."""
        self.begin_chords_audition([chord],bpm)

    def begin_chords_audition(self,chords,bpm):
        """Preview selected regions consecutively, in their timeline order."""
        self.cancel_auditions()
        try:
            self.open();ch=3;generation=self.audition_generations[ch]
            self.audition_notes[ch]=[]
            self.audition_holds[ch]=[time.monotonic(),sum(c.duration for c in chords)*60/(bpm*PPQ),True]
            events=[];offset=0
            for chord in sorted(chords,key=lambda c:c.start):
                for note in chord.render_notes():
                    events.extend(((offset+note.start-chord.start,1,note.pitch,note.velocity),(offset+note.end-chord.start,0,note.pitch,0)))
                offset+=chord.duration
            counts={}
            def dispatch(on,pitch,velocity):
                if self.audition_generations.get(ch)!=generation or ch not in self.audition_notes or not self.synth:return
                counts[pitch]=max(0,counts.get(pitch,0)+(1 if on else -1))
                if on:
                    self.synth.send(0x93,pitch,velocity)
                    if pitch not in self.audition_notes[ch]:self.audition_notes[ch].append(pitch)
                elif not counts[pitch]:
                    self.synth.send(0x83,pitch)
                    if pitch in self.audition_notes[ch]:self.audition_notes[ch].remove(pitch)
            for tick,on,pitch,velocity in sorted(events):
                ms=round(tick*60000/(bpm*PPQ))
                if ms==0:dispatch(on,pitch,velocity)
                else:QTimer.singleShot(ms,self,lambda o=on,p=pitch,v=velocity:dispatch(o,p,v))
        except Exception as exc:self.error.emit(str(exc))

    def extend_audition(self,harmony,seconds):
        state=self.audition_holds.get(3 if harmony else 2)
        if state and state[2]:state[1]=max(state[1],seconds)

    def end_audition(self,harmony=False,cancel=False):
        ch=3 if harmony else 2;state=self.audition_holds.get(ch)
        if not state:return
        state[2]=False;generation=self.audition_generations[ch]
        remaining=0 if cancel else max(0,state[1]-(time.monotonic()-state[0]))
        def finish():
            if generation==self.audition_generations.get(ch):
                self._audition_off(ch,self.audition_notes.pop(ch,[]));self.audition_holds.pop(ch,None)
        if remaining:QTimer.singleShot(max(1,round(remaining*1000)),self,finish)
        else:finish()

    def monitor(self,pitch,velocity,harmony=False):
        try:
            self.open();self.synth.send((0x90 if velocity else 0x80)|(5 if harmony else 4),pitch,velocity)
        except Exception as exc:self.error.emit(str(exc))

    def stop_playback_notes(self):
        if self.synth:
            silence_channels(self.synth,(0,1))

    def _audition_off(self, channel, pitches):
        if self.synth:
            for p in pitches:
                self.synth.send(0x80 | channel, p)

    def play(self, project, start=0, end=None, loop=False, melody=True, harmony=True,volumes=None,loop_start=None):
        self.stop()
        self.configure(project.audio)
        self.set_volumes(project.volumes if volumes is None else volumes)
        self.open()
        self.cancel.clear()
        self.wake.clear();self.pending_revision=None
        self.start_tick, self.end_tick = start, end or project.end
        self.end_follows_project=not loop and (end is None or end==project.end)
        self.seconds_per_tick = 60 / project.bpm / PPQ
        self.loop, self.playing = loop, True
        all_events = event_list(project, melody, harmony)
        events=self.window_events(all_events,start,self.end_tick)
        loop_start=start if loop_start is None else loop_start
        loop_events=self.window_events(all_events,loop_start,self.end_tick)
        self.loop_events=loop_events;self.loop_start=loop_start;self.play_tracks=(melody,harmony)
        self.requested_bounds=(loop,loop_start,None if self.end_follows_project else self.end_tick)
        self.schedule_signature=(tuple(all_events),self.seconds_per_tick,self.end_tick,loop,loop_start)
        self.start_time = time.perf_counter()
        if isinstance(self.synth,_ProcessRouter):
            self.synth.play_schedule(all_events,self.seconds_per_tick,start,self.end_tick,loop,loop_start)
            self._sync_process_clock()
            target,args=self._watch_process,()
        else:
            # In-memory output adapters remain useful for deterministic tests.
            target,args=self._run,(events,)
        self.thread = threading.Thread(target=target, args=args, daemon=True, name='LingfengAudio')
        self.thread.start()

    def refresh_recording(self,project):
        # Replace the next loop atomically. The current take is heard via monitor.
        if self.playing:
            events=event_list(project,*self.play_tracks)
            if isinstance(self.synth,_ProcessRouter):self.synth.refresh_recording(events)
            else:self.loop_events=self.window_events(events,self.loop_start,self.end_tick)

    def revise(self,project):
        """Swap future events in the existing worker without stopping its clock."""
        if not self.playing:return
        events=event_list(project,*self.play_tracks)
        loop,loop_start,bound=self.requested_bounds
        end=project.end if bound is None else min(bound,project.end)
        loop_start=max(0,min(loop_start,end-1))
        seconds=60/project.bpm/PPQ;signature=(tuple(events),seconds,end,loop,loop_start)
        if signature==self.schedule_signature:return
        if isinstance(self.synth,_ProcessRouter):
            self.synth.revise_schedule(events,seconds,end,loop,loop_start)
            self.schedule_signature=signature
            return
        with self.revision_lock:
            self.pending_revision=(events,seconds,end,loop,loop_start);self.schedule_signature=signature;self.wake.set()

    def set_loop(self,project,enabled,start=0,end=None):
        """Update the current schedule in place; disabling continues to song end."""
        if not self.playing:return
        end=project.end if end is None else min(project.end,end)
        start=max(0,min(start,end-1))
        # Never jump backwards just because Loop was checked after its end.
        enabled=bool(enabled) and self.position()<end
        self.requested_bounds=(enabled,start if enabled else 0,end if enabled else None)
        self.end_follows_project=not enabled
        self.revise(project)

    @staticmethod
    def window_events(events,start,end):
        return window_events(events,start,end)

    def _sync_process_clock(self,synth=None):
        state=(self.synth if synth is None else synth).clock_state()
        _,self.start_tick,self.end_tick,self.start_time,self.seconds_per_tick,loop,self.loop_start=state
        self.loop=bool(loop)
        return bool(state[0])

    def _watch_process(self):
        """Observe completion only; this thread never sends scheduled notes."""
        synth=self.synth
        try:
            while not self.cancel.wait(.005):
                if synth.failure:raise RuntimeError(synth.failure)
                if not self._sync_process_clock(synth):break
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    def _run(self, events):
        active={};index=0
        try:
            while not self.cancel.is_set():
                with self.revision_lock:
                    revision=self.pending_revision;self.pending_revision=None;self.wake.clear()
                if self.cancel.is_set():break
                now=time.perf_counter();tick=self.start_tick+(now-self.start_time)/self.seconds_per_tick
                if revision is not None:
                    all_events,seconds,end,loop,loop_start=revision;desired={}
                    for t,on,ch,pitch,velocity in all_events:
                        if t>tick:break
                        if on:desired[ch,pitch]=velocity
                        else:desired.pop((ch,pitch),None)
                    if tick>=end:desired={}
                    for ch,pitch in active.keys()-desired.keys():self.synth.send(0x80|ch,pitch)
                    for ch,pitch in desired.keys()-active.keys():self.synth.send(0x90|ch,pitch,desired[ch,pitch])
                    active=desired
                    if seconds!=self.seconds_per_tick:self.start_tick=tick;self.start_time=now;self.seconds_per_tick=seconds
                    self.end_tick=end;self.loop=loop;self.loop_start=loop_start
                    self.loop_events=self.window_events(all_events,loop_start,end)
                    events=[e for e in all_events if tick<e[0]<end];index=0
                while index<len(events) and events[index][0]<=tick:
                    _,on,ch,pitch,velocity=events[index]
                    self.synth.send((0x90 if on else 0x80)|ch,pitch,velocity)
                    if on:active[ch,pitch]=velocity
                    else:active.pop((ch,pitch),None)
                    index+=1
                if tick>=self.end_tick:
                    with self.revision_lock:
                        # A queued loop change wins over wrapping at the old boundary.
                        if self.pending_revision is not None:continue
                        self.stop_playback_notes();active.clear()
                        if not self.loop:break
                        self.start_tick=self.loop_start;self.start_time=now;events=self.loop_events;index=0
                    continue
                next_tick=events[index][0] if index<len(events) else self.end_tick
                self.wake.wait(max(0,self.start_time+(next_tick-self.start_tick)*self.seconds_per_tick-time.perf_counter()))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            if self.synth:
                self.stop_playback_notes()
            self.finished.emit()

    def position(self):
        if not self.playing:
            return self.start_tick
        if isinstance(self.synth,_ProcessRouter):self._sync_process_clock()
        return int(min(self.end_tick, self.start_tick + (time.perf_counter()-self.start_time)/self.seconds_per_tick))

    def stop(self,preserve_auditions=False):
        self.cancel.set()
        self.wake.set()
        if isinstance(self.synth,_ProcessRouter):
            try:self.synth.stop_schedule()
            except RuntimeError:
                # A failed worker has released its device in its finally block;
                # stopping/closing the UI must still finish and allow reopening.
                synth=self.synth;self.synth=None;synth.close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
        self.thread = None
        self.playing = False
        self.stop_playback_notes()
        if not preserve_auditions:
            for ch in (2,3):
                self.audition_generations[ch]=self.audition_generations.get(ch,0)+1
            self.audition_holds.clear();self.audition_notes.clear()
            if self.synth:
                silence_channels(self.synth,(2,3,4,5))

    def _finished(self):
        if not self.thread or not self.thread.is_alive():
            self.playing = False

    def close(self):
        try:self.stop()
        except (RuntimeError,OSError):pass # A failed backend must still release its device.
        finally:
            synth=self.synth;self.synth=None
            self.audition_holds.clear();self.audition_notes.clear()
            if synth:synth.close()

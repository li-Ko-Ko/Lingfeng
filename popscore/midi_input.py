"""WinMM MIDI input. Driver callbacks only enqueue; Qt owns recording and audio."""
import copy
from bisect import bisect_left,bisect_right
import ctypes
import queue
import sys
import time
from PySide6.QtCore import QObject,QTimer
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,QCheckBox,QPushButton,QDialogButtonBox,QApplication
from .i18n import tr
from .model import Note,Chord,uid
from .quantization import nearest


class InputCaps(ctypes.Structure):
    _fields_=[('mid',ctypes.c_ushort),('pid',ctypes.c_ushort),('version',ctypes.c_uint),('name',ctypes.c_wchar*32),('support',ctypes.c_uint)]


def devices():
    if sys.platform!='win32':return []
    api=ctypes.WinDLL('winmm');api.midiInGetDevCapsW.argtypes=[ctypes.c_size_t,ctypes.POINTER(InputCaps),ctypes.c_uint]
    result=[]
    for i in range(api.midiInGetNumDevs()):
        caps=InputCaps()
        if not api.midiInGetDevCapsW(i,ctypes.byref(caps),ctypes.sizeof(caps)):result.append((i,caps.name))
    return result


class WinMidiInput:
    def __init__(self):
        self.queue=queue.SimpleQueue();self.handle=ctypes.c_void_p();self.generation=0;self.callback=None

    def open(self,index):
        self.close();self.api=ctypes.WinDLL('winmm');self.generation+=1;generation=self.generation
        prototype=ctypes.WINFUNCTYPE(None,ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_size_t,ctypes.c_size_t)
        def received(handle,message,instance,packed,stamp):
            if message in (0x3C3,0x3CC):self.queue.put((generation,packed,stamp))
        self.callback=prototype(received)
        self.api.midiInOpen.argtypes=[ctypes.POINTER(ctypes.c_void_p),ctypes.c_uint,prototype,ctypes.c_size_t,ctypes.c_uint]
        for name in ('midiInStart','midiInStop','midiInReset','midiInClose'):getattr(self.api,name).argtypes=[ctypes.c_void_p]
        rc=self.api.midiInOpen(ctypes.byref(self.handle),index,self.callback,0,0x30000)
        if rc:raise RuntimeError(tr('无法打开 MIDI 输入设备（错误码 {0}）。',rc))
        self.epoch=time.perf_counter();rc=self.api.midiInStart(self.handle)
        if rc:self.close();raise RuntimeError(tr('无法启动 MIDI 输入设备（错误码 {0}）。',rc))

    def close(self):
        self.generation+=1
        if self.handle.value:
            self.api.midiInStop(self.handle);self.api.midiInReset(self.handle);self.api.midiInClose(self.handle);self.handle=ctypes.c_void_p()
        self.callback=None
        while not self.queue.empty():self.queue.get()

    def drain(self):
        while not self.queue.empty():
            generation,packed,stamp=self.queue.get()
            if generation==self.generation:yield packed&255,(packed>>8)&127,(packed>>16)&127,self.epoch+stamp/1000


def commit_notes(project,notes,target):
    """Preserve lyrics; chord input is split into existing structural regions."""
    from .lyrics import detach
    from .midi_import import _extend
    detach(project);_extend(project,max(n.end for n in notes))
    if target=='melody':
        for n in notes:project.add_note(n,overwrite=True)
        project.notes.sort(key=lambda n:(n.start,n.pitch));return
    for n in notes:project.overwrite_harmony(n)
    project.chords.sort(key=lambda c:c.start)


class MidiInputController(QObject):
    def __init__(self,owner):
        super().__init__(owner);self.owner=owner;self.backend=WinMidiInput();self.enabled=False;self.device_name='';self.target='melody'
        self.held={};self.pending=[];self.pedal=set();self.released=set();self.step_tick=None
        self.timer=QTimer(self);self.timer.setInterval(10);self.timer.timeout.connect(self.poll)

    def configure(self,index,name,target,enabled):
        self.close();self.target=target
        if enabled:
            self.backend.open(index);self.device_name=name;self.enabled=True;self.timer.start()

    def poll(self):
        for status,a,b,stamp in self.backend.drain():
            if QApplication.activeModalWidget() is None:self.receive(status,a,b,stamp)
            else:self.reset()

    def receive(self,status,pitch,velocity,stamp=None):
        if not self.enabled:return
        stamp=time.perf_counter() if stamp is None else stamp;kind=status&240;channel=status&15;key=(channel,pitch)
        if kind==0xB0:
            if pitch==64:
                if velocity>=64:self.pedal.add(channel)
                else:
                    self.pedal.discard(channel)
                    for held in list(self.released):
                        if held[0]==channel:self.finish(held,stamp)
            elif pitch in (120,123):self.reset()
            return
        if kind not in (0x80,0x90) or not 21<=pitch<=108:return
        if kind==0x90 and velocity:
            if key in self.held:self.finish(key,stamp)
            owner=self.owner;roll=owner.roll if self.target=='melody' else owner.harmony_window.roll
            live=owner.transport.playing;step=roll.grid
            from .timing import grid_points
            points=grid_points(owner.project,step,roll.grid_bars)
            if not live:
                if self.step_tick is None:
                    self.step_tick=roll.snap_time(owner.playhead);self.step_epoch=stamp;self.group_stamp=stamp;self.group_tick=self.step_tick
                # A small chord-onset window accepts human simultaneity. Held
                # keys / sustain must not collapse a later legato onset into it.
                window=min(.08,step*60/(owner.project.bpm*960)*.5)
                if stamp-self.group_stamp>window+1e-6:
                    elapsed=round((stamp-self.step_epoch)*owner.project.bpm*960/60)
                    after=next((t for t in points if t>self.group_tick),self.group_tick+step)
                    self.group_tick=max(after,roll.snap_time(self.step_tick+elapsed))
                    self.group_stamp=stamp
                tick=self.group_tick
            else:tick=owner.transport.start_tick+round((stamp-owner.transport.start_time)/owner.transport.seconds_per_tick)
            tick=max(0,tick);start=roll.snap_time(tick) if tick<=owner.project.end else nearest(tick,step,owner.project.end)
            origin=owner.project.starts[owner.project.measure_at(start)]
            self.held[key]=dict(points=points,bar_length=owner.project.measures[-1].ticks,bars=roll.grid_bars,start=start,raw_start=tick,stamp=stamp,step=step,origin=origin,velocity=velocity,live=live,target=self.target,bpm=owner.project.bpm)
            owner.transport.monitor(pitch,velocity,self.target=='chords')
        elif key in self.held:
            if channel in self.pedal:self.released.add(key)
            else:self.finish(key,stamp)

    def finish(self,key,stamp):
        state=self.held.pop(key,None);self.released.discard(key)
        if state is None:return
        channel,pitch=key;owner=self.owner
        owner.transport.monitor(pitch,0,state['target']=='chords')
        elapsed=max(0,stamp-state['stamp'])*state['bpm']*960/60
        points=state['points'];raw_end=state['raw_start']+elapsed
        while points[-1]<=max(raw_end,state['start']):
            last=points[-1];end=last+state['bar_length']*max(1,state['bars'])
            points.extend([end] if state['bars'] else list(range(last+state['step'],end,state['step']))+[end])
        index=bisect_left(points,raw_end);end=min(points[max(0,index-1):index+1],key=lambda t:(abs(t-raw_end),-t))
        duration=max(points[bisect_right(points,state['start'])],end)-state['start']
        note=Note(state['start'],duration,pitch,state['velocity'])
        if state['live']:
            owner.mutate(tr('已录入 MIDI 音符'),lambda p:commit_notes(p,[note],state['target']),keep_playing=True,recording=True,source='harmony' if state['target']=='chords' else 'melody')
        else:
            self.pending.append((note,state['target']))
            if not self.held:
                pending=self.pending;self.pending=[];self.step_tick=None
                def op(p):
                    for target in ('melody','chords'):
                        notes=[n for n,t in pending if t==target]
                        if notes:commit_notes(p,notes,target)
                if owner.mutate(tr('已录入 MIDI 音符'),op,source='harmony' if state['target']=='chords' else 'melody'):
                    owner.playhead=min(owner.project.end-1,max(n.end for n,t in pending));owner.show_cursor(owner.playhead)

    def reset(self):
        for (_,pitch),state in self.held.items():self.owner.transport.monitor(pitch,0,state['target']=='chords')
        self.held.clear();self.pending=[];self.step_tick=None;self.pedal.clear();self.released.clear()

    def close(self):
        self.reset();self.enabled=False;self.backend.close();self.timer.stop()


class MidiInputDialog(QDialog):
    def __init__(self,controller,parent=None):
        super().__init__(parent);self.setWindowTitle(tr('MIDI 键盘输入'));self.setMinimumWidth(440)
        box=QVBoxLayout(self);box.setSpacing(12)
        info=QLabel(tr('暂停时逐步录入：同时按键形成和弦，连奏保留先后起点，松开全部琴键后前进；播放时实时录入。起点和时值吸附目标卷帘的当前格点。E 可切换录入轨道，原有歌词保留。'));info.setWordWrap(True);box.addWidget(info)
        row=QHBoxLayout();self.device=QComboBox();row.addWidget(self.device,1);refresh=QPushButton(tr('刷新设备'));row.addWidget(refresh);box.addLayout(row)
        def update():
            self.device.clear()
            for i,name in devices():self.device.addItem(name,i)
            if not self.device.count():self.device.addItem(tr('未检测到 MIDI 输入设备'),None)
            at=self.device.findText(controller.device_name)
            if at>=0:self.device.setCurrentIndex(at)
        refresh.clicked.connect(update);update()
        self.target=QComboBox();self.target.addItem(tr('旋律'),'melody');self.target.addItem(tr('和弦'),'chords');self.target.setCurrentIndex(self.target.findData(controller.target));row=QHBoxLayout();row.addWidget(QLabel(tr('录入轨道')));row.addWidget(self.target,1);box.addLayout(row)
        self.enabled=QCheckBox(tr('启用 MIDI 键盘录入'));self.enabled.setChecked(controller.enabled);box.addWidget(self.enabled)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);box.addWidget(buttons)

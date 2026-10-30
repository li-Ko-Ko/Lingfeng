"""Export selection and audio rendering. Never modify the source project."""
import copy
import math
import os
import threading
import time
from pathlib import Path
from lingfeng.audio.com_runtime import com_apartment as _com_apartment
from lingfeng.music.note_operations import window_notes
from lingfeng.music.model import PPQ
from lingfeng.platform.i18n import tr

RATE=44100

def bounds(project,kind='all',first=1,last=None,loop=None,section=0):
    if kind=='all':return 0,project.end
    if kind=='bars':
        last=len(project.measures) if last is None else last
        if not 1<=first<=last<=len(project.measures):raise ValueError(tr('小节范围无效。'))
        return project.starts[first-1],project.starts[last]
    if kind=='loop':
        if not loop or not 0<=loop[0]<loop[1]<=project.end:raise ValueError(tr('请先在时间尺设置循环范围。'))
        return tuple(loop)
    if kind=='section':
        entries=project.sections()
        if not 0<=section<len(entries):raise ValueError(tr('请选择有效的段落。'))
        _,a,b=entries[section];return project.starts[a],project.starts[b]
    raise ValueError(tr('导出范围无效。'))


def audio_notes(project,which,start,end):
    notes=[]
    seconds=60/project.bpm/PPQ
    for role,source in (('melody',project.notes),('chords',project.harmony_notes())):
        if which not in ('both',role):continue
        for n in window_notes(source,start,end):notes.append((n.start*seconds,n.end*seconds,n.pitch,n.velocity/127*project.volumes[role]/127,role))
    return sorted(notes)

def offline_pcm(project,which,start,end,cancel,progress,block=4096):
    """Render frame-exact MIDI using the same selected synth packs as editing."""
    import numpy as np
    from lingfeng.audio.synthesis import SynthEngine, BLOCK
    from lingfeng.audio.soundbanks import export_instruments
    export_instruments(project,which,start,end)  # Reject unsupported voices before writing audio.
    seconds=60/project.bpm/PPQ;events=[];engine=SynthEngine(channel_devices={i:project.audio[role]['device'] for i,role in enumerate(('melody','chords'))})
    try:
        for channel,(role,source) in enumerate((('melody',project.notes),('chords',project.harmony_notes()))):
            notes=window_notes(source,start,end) if which in ('both',role) else []
            if not notes:continue
            if cancel.is_set():raise InterruptedError()
            engine.send(0xc0|channel,project.audio[role]['program']);engine.send(0xb0|channel,7,project.volumes[role])
            for n in notes:
                events.extend([(round(n.start*seconds*RATE),1,channel,n.pitch,n.velocity),
                               (round(n.end*seconds*RATE),0,channel,n.pitch,0)])
        events.sort();index=0;frames=math.ceil(((end-start)*seconds+(3 if events else 0))*RATE)
        pending=[];pending_frames=0
        for frame in range(0,frames,BLOCK):
            if cancel.is_set():raise InterruptedError()
            count=min(BLOCK,frames-frame)
            while index<len(events) and events[index][0]<frame+count:
                at,on,ch,pitch,velocity=events[index];engine.send((0x90 if on else 0x80)|ch,pitch,velocity,delay=max(0,at-frame));index+=1
            pending.append((engine.render(count)*32767).astype('<i2').tobytes());pending_frames+=count
            if pending_frames>=block or frame+count==frames:
                progress(min(99,round((frame+count)/frames*100)));yield b''.join(pending);pending=[];pending_frames=0
    finally:engine.close()


def realtime_pcm(project,which,start,end,cancel,progress):
    with _com_apartment():
        yield from _capture_pcm(project,which,start,end,cancel,progress)


def _capture_pcm(project,which,start,end,cancel,progress):
    """Capture only the chosen output's loopback, never a microphone.

    Other applications using this output are audible in the recording. The UI
    explains this before the user starts. MIDI scheduling has its own clock.
    """
    import numpy as np
    import soundcard as sc
    from lingfeng.audio.routing import MidiRouter
    from lingfeng.audio.midi import event_list
    from lingfeng.audio.transport import Transport
    speaker=sc.default_speaker()
    if speaker is None:raise RuntimeError(tr('没有可用于录制的默认音频输出设备。'))
    capture=sc.get_microphone(speaker.id,include_loopback=True)
    if not capture.isloopback:raise RuntimeError(tr('无法打开系统输出回录设备。'))
    settings={role:dict(value,device='default') for role,value in project.audio.items()}
    router=MidiRouter(settings)
    for channel,role in ((0,'melody'),(1,'chords')):router.send(0xB0|channel,7,project.volumes[role])
    seconds=60/project.bpm/PPQ;duration=(end-start)*seconds
    events=Transport.window_events(event_list(project,which in ('both','melody'),which in ('both','chords')),start,end)
    stop=threading.Event();errors=[];worker=None
    def play(origin):
        try:
            for tick,on,ch,pitch,velocity in events:
                wait=origin+(tick-start)*seconds-time.perf_counter()
                if stop.wait(max(0,wait)):return
                if cancel.is_set():return
                router.send((0x90 if on else 0x80)|ch,pitch,velocity)
            stop.wait(max(0,origin+duration-time.perf_counter()))
        except Exception as exc:errors.append(exc)
        finally:router.stop()
    try:
        # WASAPI needs both channels; mono loopback has platform-specific issues.
        with capture.recorder(samplerate=RATE,channels=2,blocksize=512) as recorder:
            recorder.record(numframes=512)
            origin=time.perf_counter();worker=threading.Thread(target=play,args=(origin,),daemon=True);worker.start()
            frames=math.ceil((duration+.7)*RATE);done=0
            while done<frames:
                if cancel.is_set():raise InterruptedError()
                if errors:raise errors[0]
                count=min(1024,frames-done);data=recorder.record(numframes=count)
                done+=len(data);progress(min(99,round(done/frames*100)))
                yield (np.clip(data,-1,1)*32767).astype('<i2').tobytes()
    finally:
        stop.set()
        if worker:worker.join(timeout=2)
        router.close()

def export_mp3(project,path,which='both',start=0,end=None,mode='offline',cancel=None,progress=lambda value:None):
    import lameenc
    end=project.end if end is None else end
    if which not in ('both','melody','chords') or not 0<=start<end<=project.end:raise ValueError(tr('导出范围无效。'))
    if mode not in ('offline','windows'):raise ValueError(tr('无效的音频渲染方式。'))
    cancel=cancel or threading.Event();target=Path(path);temp=target.with_name(target.name+'.part')
    encoder=lameenc.Encoder();encoder.set_bit_rate(192);encoder.set_in_sample_rate(RATE);encoder.set_channels(2);encoder.set_quality(2)
    render=realtime_pcm if mode=='windows' else offline_pcm
    from lingfeng.audio.soundbanks import credits_text
    credits=credits_text(project,which,start,end,mode)
    notice=target.with_name(target.name+'.licenses.txt');notice_temp=notice.with_name(notice.name+'.part')
    try:
        with temp.open('wb') as file:
            for pcm in render(project,which,start,end,cancel,progress):file.write(encoder.encode(pcm))
            file.write(encoder.flush())
        if cancel.is_set():raise InterruptedError()
        notice_temp.write_text(credits,encoding='utf-8')
        old_notice=notice.read_bytes() if notice.exists() else None
        os.replace(notice_temp,notice)
        try:os.replace(temp,target)
        except OSError:
            if old_notice is None:notice.unlink()
            else:
                notice_temp.write_bytes(old_notice);os.replace(notice_temp,notice)
            raise
        progress(100)
    finally:
        if temp.exists():temp.unlink()
        if notice_temp.exists():notice_temp.unlink()

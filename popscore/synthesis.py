"""Native synthesis-pack host shared by real-time playback and audio export."""
import ctypes as C
import hashlib,multiprocessing,threading,time
from pathlib import Path
import numpy as np
from .i18n import tr
from . import i18n
from .soundbanks import DEFAULT_DEVICE,instrument,pack

RATE=44100
BLOCK=256
_libraries={}
_library_lock=threading.RLock()

def write_output(player,data):
    """SoundCard 0.4.5 WASAPI adapter: release only frames actually written.

    Upstream _Player.play requests/releases all available frames even when its
    input is shorter. A short synth block can therefore expose unwritten memory.
    Keep the upstream stream/COM lifetime but submit exact-sized buffers here.
    """
    from soundcard.mediafoundation import _ffi
    offset=0
    while offset<len(data):
        count=min(len(data)-offset,player._render_available_frames())
        if count<=0:time.sleep(.001);continue
        chunk=np.ascontiguousarray(data[offset:offset+count],dtype=np.float32)
        buffer=player._render_buffer(count)
        _ffi.memmove(buffer[0],chunk.tobytes(),chunk.nbytes)
        player._render_release(count);offset+=count

def library(device):
    info=pack(device);path=(Path(info['path'])/info['library']).resolve()
    with _library_lock:
        key=(str(path),info['sha256'])
        if key in _libraries:return _libraries[key]
        if any(p==str(path) for p,h in _libraries):raise RuntimeError(tr('音源已更新，请重启程序后使用新版本。'))
        if hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:raise ValueError(tr('音源文件已更改，请重新扫描。'))
        lib=C.CDLL(str(path));P=C.c_void_p;I=C.c_int
        signatures={'abi':([],I),'error':([],C.c_char_p),'create':([I,I,I],P),'free':([P],None),'control':([P,I,C.c_double],I),'event':([P,I,I,I],I),'render':([P,C.POINTER(C.c_float),I],I)}
        for name,(args,result) in signatures.items():
            func=getattr(lib,'lf_'+name);func.argtypes=args;func.restype=result
        if lib.lf_abi()!=1:raise ValueError(tr('音源接口版本不兼容。'))
        if hasattr(lib,'lf_tone'):lib.lf_tone.argtypes=[P,C.c_double];lib.lf_tone.restype=I
        _libraries[key]=lib;return lib

class SynthVoice:
    def __init__(self,program,device=DEFAULT_DEVICE):
        self.handle=None;self.api=library(device);item=instrument(program,device);self.gain=item['gain']
        with _library_lock:self.handle=self.api.lf_create(RATE,item['model'],32)
        if not self.handle:raise RuntimeError((self.api.lf_error() or b'Cannot create synth').decode('utf-8','replace'))
        try:
            if 'cutoff_hz' in item:
                if not hasattr(self.api,'lf_tone'):raise ValueError(tr('音源不支持预设的音色滤波设置，请更新完整音源包。'))
                self.check(self.api.lf_tone(self.handle,item['cutoff_hz']))
            for cc,value in item.get('controls',{}).items():self.check(self.api.lf_control(self.handle,int(cc),value))
        except Exception:self.close();raise
    def check(self,code):
        if code:raise RuntimeError((self.api.lf_error() or b'Synthesis failed').decode('utf-8','replace'))
    def send(self,status,a=0,b=0):self.check(self.api.lf_event(self.handle,status,a,b))
    def render(self,count):
        data=np.empty((count,2),dtype=np.float32);self.check(self.api.lf_render(self.handle,data.ctypes.data_as(C.POINTER(C.c_float)),count));data*=self.gain;return data
    def close(self):
        if self.handle:
            with _library_lock:self.api.lf_free(self.handle)
            self.handle=None
    def __del__(self):self.close()

class SynthEngine:
    """Independent channel voices with frame-exact scheduled events for export."""
    def __init__(self,device=DEFAULT_DEVICE,channel_devices=None):
        self.device=device;self.channel_devices=channel_devices or {};self.channels={};self.programs={};self.events=[];self.sequence=0;self.volumes={};self.limiter_gain=1.0
    def send(self,status,a=0,b=0,delay=0):
        if not all(type(v) is int for v in (status,a,b,delay)) or not 0<=a<=127 or not 0<=b<=127 or delay<0:raise ValueError('Invalid MIDI event')
        if delay:self.sequence+=1;self.events.append((delay,self.sequence,status,a,b));return
        ch=status&15;kind=status&0xf0
        if kind==0xc0:
            if self.programs.get(ch)==a:return
            new=SynthVoice(a,self.channel_devices.get(ch,self.device));old=self.channels.get(ch)
            self.channels[ch]=new;self.programs[ch]=a;new.send(0xb0,7,self.volumes.get(ch,100))
            if old:old.close()
            return
        if kind==0xb0 and a==7:self.volumes[ch]=b
        if ch not in self.channels:
            if kind==0x90 and b:self.send(0xc0|ch,0)
            else:return
        self.channels[ch].send(status,a,b)
    def render(self,count):
        if not 0<=count<=65536:raise ValueError('Invalid render size')
        out=np.zeros((count,2),dtype=np.float32);cursor=0;future=[]
        def fill(end):
            nonlocal cursor
            if end>cursor:
                for voice in self.channels.values():out[cursor:end]+=voice.render(end-cursor)
                cursor=end
        for at,seq,status,a,b in sorted(self.events):
            if at>=count:future.append((at-count,seq,status,a,b));continue
            fill(at);self.send(status,a,b)
        self.events=future;fill(count)
        if count:
            # Linked stereo peak limiter: linear below the ceiling, immediate
            # overload protection, 250 ms recovery. Its state is frame-based,
            # so splitting export blocks does not change the rendered waveform.
            peak=np.max(np.abs(out),axis=1).astype(np.float64)
            required=.95/np.maximum(.95,peak);ramp=np.arange(count,dtype=np.float64)/(RATE*.25)
            gain=np.minimum(np.minimum.accumulate(required-ramp)+ramp,self.limiter_gain+ramp+1/(RATE*.25))
            np.minimum(gain,1,out=gain);out*=gain[:,None];self.limiter_gain=float(gain[-1])
        return out
    def stop(self):
        self.events.clear();self.limiter_gain=1.0
        for voice in self.channels.values():voice.send(0xb0,120,0)
    def close(self):
        for voice in self.channels.values():voice.close()
        self.channels.clear();self.programs.clear();self.events.clear()
    def __del__(self):self.close()

def _synthesis_worker(connection,channel_devices,programs,language=None):
    """Own the synth and WASAPI stream outside the GUI's Python/GIL process."""
    from .exporting import _com_apartment
    if language is not None:i18n.set_language(language)
    engine=SynthEngine(channel_devices=channel_devices)
    try:
        for ch,program in programs.items():engine.send(0xc0|ch,program)
        with _com_apartment():
            import soundcard as sc
            speaker=sc.default_speaker()
            if speaker is None:raise RuntimeError(tr('没有可用的默认音频输出设备。'))
            with speaker.player(samplerate=RATE,channels=2,blocksize=BLOCK) as player:
                # A bounded 40 ms reservoir tolerates scheduling jitter. Refill
                # in full blocks, never tiny fragments as padding fluctuates.
                target=min(player.buffersize,max(4*BLOCK,round(RATE*.04),round(3*RATE*player.deviceperiod[0])))
                block=min(BLOCK,target)
                connection.send(('ready',None))
                while True:
                    for _ in range(256):
                        if not connection.poll():break
                        packet=connection.recv();command,args=packet[:2]
                        if len(packet)>2:i18n.set_language(packet[2])
                        if command=='close':return
                        if command=='stop':engine.stop()
                        elif command=='midi':
                            engine.send(*args)
                            if args[0]&0xf0==0xc0:connection.send(('program',None))
                    missing=max(0,target-player.currentpadding)
                    if missing<block:
                        connection.poll(.001);continue
                    write_output(player,engine.render(block))
    except (EOFError,BrokenPipeError):pass
    except Exception as exc:
        try:connection.send(('error',str(exc)))
        except (EOFError,BrokenPipeError,OSError):pass
    finally:
        engine.close();connection.close()


class NativeSynth:
    """Small IPC facade; GUI painting cannot starve the audio renderer's GIL."""
    def __init__(self,channel_devices,programs,threaded=False):
        self.lock=threading.RLock();self.failure=None;self.process=None;self.connection=None
        self.threaded=threaded
        self.programs=dict(programs)
        context=multiprocessing.get_context('spawn')
        parent,child=context.Pipe();self.connection=parent
        started=False
        try:
            factory=threading.Thread if threaded else context.Process
            self.process=factory(target=_synthesis_worker,args=(child,channel_devices,programs,i18n.LANGUAGE),daemon=True,name='LingfengSynthesis')
            self.process.start()
            started=True
            if not threaded:child.close()
            self._reply('ready',10)
        except Exception:
            # In threaded mode the worker owns this exact Connection object.
            # Closing it here races its error/finally path and can replace the
            # useful startup error with WinError 6 (invalid handle).
            if not threaded or not started:child.close()
            self.close();raise

    def _reply(self,expected,timeout):
        if not self.connection.poll(timeout):raise RuntimeError(tr('打开合成音源超时，请检查默认音频输出设备。'))
        try:kind,message=self.connection.recv()
        except (EOFError,OSError) as exc:raise RuntimeError(tr('音频输出进程已停止。')) from exc
        if kind=='error':self.failure=message;raise RuntimeError(message)
        if kind!=expected:raise RuntimeError('Unexpected audio worker response')

    def send(self,status,a=0,b=0):
        with self.lock:
            if self.failure:raise RuntimeError(self.failure)
            if self.connection is None or not self.process.is_alive():raise RuntimeError(tr('音频输出进程已停止。'))
            if self.connection.poll():self._reply('error',0)
            program=status&0xf0==0xc0
            if program and self.programs.get(status&15)==a:return
            try:self.connection.send(('midi',(status,a,b),i18n.LANGUAGE))
            except (BrokenPipeError,EOFError,OSError) as exc:raise RuntimeError(tr('音频输出进程已停止。')) from exc
            if program:self._reply('program',10);self.programs[status&15]=a

    def stop(self):
        with self.lock:
            if self.connection is not None:
                try:self.connection.send(('stop',(),i18n.LANGUAGE))
                except (BrokenPipeError,EOFError,OSError):pass

    def close(self):
        with self.lock:
            if self.connection is not None:
                try:self.connection.send(('close',(),i18n.LANGUAGE))
                except (BrokenPipeError,EOFError,OSError):pass
            if self.process is not None:
                if self.threaded:
                    self.process.join(timeout=2)
                elif self.process.pid is not None:
                    self.process.join(timeout=2)
                    if self.process.is_alive():self.process.terminate();self.process.join(timeout=2)
                if not self.threaded:self.process.close()
                self.process=None
            if self.connection is not None:self.connection.close();self.connection=None

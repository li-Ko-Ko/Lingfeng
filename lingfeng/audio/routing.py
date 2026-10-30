"""Device ownership and channel routing for WinMM and installed synth packs.

The playback process and settings preview own separate routers. GUI transport
control stays in transport.py; no Qt widgets or projects belong to this module.
"""
import ctypes
import sys
import threading

from lingfeng.platform.i18n import tr
from lingfeng.audio.events import silence_channels


def midi_devices():
    """Enumerate installed WinMM outputs; default remains the MIDI mapper."""
    if sys.platform!='win32':return []
    class Caps(ctypes.Structure):
        _fields_=[('mid',ctypes.c_ushort),('pid',ctypes.c_ushort),('version',ctypes.c_uint),
                  ('name',ctypes.c_wchar*32),('technology',ctypes.c_ushort),('voices',ctypes.c_ushort),
                  ('notes',ctypes.c_ushort),('channel_mask',ctypes.c_ushort),('support',ctypes.c_uint)]
    api=ctypes.WinDLL('winmm');api.midiOutGetDevCapsW.argtypes=[ctypes.c_size_t,ctypes.POINTER(Caps),ctypes.c_uint]
    result=[]
    for index in range(api.midiOutGetNumDevs()):
        caps=Caps()
        if api.midiOutGetDevCapsW(index,ctypes.byref(caps),ctypes.sizeof(caps))==0:result.append((index,caps.name))
    return result


def default_midi_device():
    """Resolve the mapper alias without opening a second exclusive device."""
    if sys.platform!='win32':return -1
    api=ctypes.WinDLL('winmm')
    api.midiOutMessage.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_size_t]
    device=ctypes.c_uint(0xffffffff);flags=ctypes.c_uint()
    # MIDI_MAPPER is UINT(-1), zero-extended to a pointer on Win64.
    rc=api.midiOutMessage(ctypes.c_void_p(0xffffffff),0x2015,ctypes.addressof(device),ctypes.addressof(flags))
    return device.value if rc==0 and device.value!=0xffffffff else -1


class Synth:
    def __init__(self,device_id=-1):
        self.handle = ctypes.c_void_p()
        self.lock = threading.RLock()
        if sys.platform != 'win32':
            raise RuntimeError(tr('本demo的播放使用Windows MIDI合成器；其他系统仍可编辑和导出。'))
        self.api = ctypes.WinDLL('winmm')
        self.api.midiOutOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint, ctypes.c_size_t, ctypes.c_size_t, ctypes.c_uint]
        self.api.midiOutShortMsg.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.api.midiOutReset.argtypes = [ctypes.c_void_p]
        self.api.midiOutClose.argtypes = [ctypes.c_void_p]
        rc = self.api.midiOutOpen(ctypes.byref(self.handle), device_id & 0xFFFFFFFF, 0, 0, 0)
        if rc:
            if rc==4:raise RuntimeError(tr('Windows MIDI 音源正在被占用（错误码 4）。请关闭其它程序的 MIDI 播放后重试。'))
            raise RuntimeError(tr('无法打开Windows MIDI音源（错误码{0}）。请检查音频设备。', rc))

    def send(self, status, a=0, b=0):
        with self.lock:
            if self.handle.value:
                rc=self.api.midiOutShortMsg(self.handle, status | (a << 8) | (b << 16))
                if rc:
                    raise RuntimeError(tr('MIDI输出失败（错误码{0}）', rc))

    def stop(self):
        with self.lock:
            if self.handle.value:
                self.api.midiOutReset(self.handle)

    def close(self):
        with self.lock:
            if self.handle.value:
                self.api.midiOutReset(self.handle)
                self.api.midiOutClose(self.handle)
                self.handle.value = None


class MidiRouter:
    def __init__(self,settings,native_thread=False):
        self.outputs={};self.routes={}
        from lingfeng.audio.soundbanks import is_synth_source, DEFAULT_DEVICE
        available={name:index for index,name in midi_devices()}
        default=default_midi_device() if any(s['device']=='default' for s in settings.values()) else -1
        try:
            native_devices={};native_programs={}
            for key,channels in [('melody',(0,2,4)),('chords',(1,3,5))]:
                spec=settings[key];device=spec['device']
                if device in ('samples','builtin'):device=DEFAULT_DEVICE
                if is_synth_source(device):
                    for channel in channels:native_devices[channel]=device;native_programs[channel]=spec['program']
            if native_devices:
                from lingfeng.audio.synthesis import NativeSynth
                self.outputs['native']=NativeSynth(native_devices,native_programs,threaded=True) if native_thread else NativeSynth(native_devices,native_programs)
            for key,channels in [('melody',(0,2,4)),('chords',(1,3,5))]:
                spec=settings[key];device=spec['device']
                if device in ('samples','builtin'):device=DEFAULT_DEVICE
                if device!='default' and not is_synth_source(device) and device not in available:
                    raise RuntimeError(tr('音源“{0}”不可用，请在音源设置中选择 Windows 默认兼容音源。', device))
                index='native' if is_synth_source(device) else default if device=='default' else available[device]
                if index not in self.outputs:
                    self.outputs[index]=Synth(index)
                for channel in channels:
                    self.routes[channel]=self.outputs[index]
                    if index!='native':
                        # GS/other WinMM outputs can retain controller state
                        # from an earlier client. Start our channels clean;
                        # preserve the selected program and normal FX timbre.
                        self.send(0xb0|channel,121,0)
                        silence_channels(self,(channel,))
                        self.send(0xe0|channel,0,64)
                    self.send(0xC0|channel,spec['program'])
        except Exception:
            self.close();raise

    def send(self,status,a=0,b=0):self.routes[status&15].send(status,a,b)
    def stop(self):
        for output in self.outputs.values():output.stop()
    def close(self):
        outputs=list(self.outputs.values());self.outputs.clear();self.routes.clear()
        for output in outputs:output.close()

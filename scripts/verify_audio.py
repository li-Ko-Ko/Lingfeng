"""Exercise every installed preset, then optionally verify actual Windows output.

Run with --loopback when no other application is playing audio. Numeric checks
detect silence, clipping, unstable output and stuck notes; they do not rate tone.
Reports and short audition WAVs are written to output/audio-verification/.
"""
import argparse,json,os,sys,time,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
os.environ.setdefault('LINGFENG_SYNTH_CACHE',str(ROOT/'tmp/audio-verification-index.json'))
import numpy as np
from lingfeng import __version__
import lingfeng.audio.soundbanks as banks
from lingfeng.audio.synthesis import SynthEngine, RATE, BLOCK

OUT=ROOT/'output/audio-verification';OUT.mkdir(parents=True,exist_ok=True)

def write_wave(path,data):
    with wave.open(str(path),'wb') as f:
        f.setparams((2,2,RATE,0,'NONE','not compressed'))
        f.writeframes((np.clip(data,-1,1)*32767).astype('<i2').tobytes())

def offline(report):
    for pack in banks.installed_packs():
        demo=[]
        for preset in pack['presets']:
            device='synth:'+pack['id'];program=preset['program'];engine=SynthEngine(device)
            row=dict(device=device,program=program,name=preset['name_en'],silent=[],peak=0,long_notes=[])
            try:
                start=time.perf_counter();engine.send(0xc0,program);row['prepare_ms']=(time.perf_counter()-start)*1000
                # Every piano key; velocity extremes additionally at five anchors.
                for key in range(21,109):
                    for velocity in ((1,40,90,127) if key in (21,36,60,84,108) else (90,)):
                        engine.stop();engine.send(0x90,key,velocity);data=engine.render(16384)
                        assert np.isfinite(data).all(),(device,program,key,'nonfinite')
                        peak=float(abs(data).max());row['peak']=max(row['peak'],peak)
                        if peak<1e-9:row['silent'].append([key,velocity])
                        assert peak<.951,(device,program,key,'peak')
                        engine.send(0x80,key);engine.render(8192)
                        assert not engine.render(512).any(),(device,program,key,'stuck note')
                        report['note_cases']+=1
                for key in (36,60,84):
                    engine.stop();engine.send(0x90,key,127)
                    data=np.concatenate([engine.render(22050) for _ in range(16)])
                    assert np.isfinite(data).all()
                    spectrum=abs(np.fft.rfft(data[-32768:,0]))**2
                    frequencies=np.fft.rfftfreq(32768,1/RATE)
                    row['long_notes'].append(dict(key=key,peak=float(abs(data).max()),
                        end_rms=float(np.sqrt(np.mean(data[-22050:]**2))),dc=float(abs(data[-22050:].mean())),
                        high_frequency_fraction=float(spectrum[frequencies>8000].sum()/max(1e-30,spectrum.sum()))))
                    engine.send(0x80,key);engine.render(8192);assert not engine.render(512).any()
                engine.stop();engine.send(0x90,60,85);sample=engine.render(22050)
                engine.send(0x80,60);tail=engine.render(8192);demo.extend([sample,tail,np.zeros((4410,2),np.float32)])
                # Repeated keys, sustain, stealing and pitch bend at full velocity.
                engine.stop();engine.send(0xb0,64,127)
                for i in range(48):
                    engine.send(0x90,36+i,127);engine.render(128);engine.send(0x80,36+i)
                engine.send(0xe0,127,127);data=engine.render(8192)
                assert np.isfinite(data).all() and abs(data).max()<.951
                engine.send(0xb0,64,0);engine.render(8192);assert not engine.render(512).any()
                row['status']='passed' if not row['silent'] else 'silent-notes'
            finally:engine.close()
            report['presets'].append(row);save(report)
            print(device,program,row['status'],row['silent'],flush=True)
        write_wave(OUT/(pack['id']+'.wav'),np.concatenate(demo))
    # All six playback/audition channels active together: 48 concurrent notes.
    for device,program in [('synth:stk-essentials',1),('synth:stk-essentials',40),('synth:stk-acoustic',52)]:
        engine=SynthEngine(device)
        try:
            for ch in range(6):
                engine.send(0xc0|ch,program)
                for key in (48,52,55,60,64,67,72,76):engine.send(0x90|ch,key,90)
            timings=[]
            for _ in range(300):
                start=time.perf_counter();data=engine.render(BLOCK);timings.append((time.perf_counter()-start)*1000)
                assert np.isfinite(data).all() and abs(data).max()<.951
            report['performance'].append(dict(device=device,program=program,voices=48,p95_ms=float(np.percentile(timings,95)),budget_ms=BLOCK/RATE*1000))
        finally:engine.close()

def live(report):
    from lingfeng.audio.routing import MidiRouter, midi_devices
    from lingfeng.audio.exporting import _com_apartment
    sources=[('synth:'+p['id'],p['presets'][0]['program']) for p in banks.installed_packs()]
    if midi_devices():sources.extend([('default',1),*[(name,1) for _,name in midi_devices()]])
    # Every pair, including mapper + its named physical device in either role.
    for left in sources:
        for right in sources:
            router=MidiRouter(dict(melody=dict(device=left[0],program=left[1]),chords=dict(device=right[0],program=right[1])))
            try:
                router.send(0x90,60,50);router.send(0x91,64,50);time.sleep(.04);router.stop()
            finally:router.close()
            report['switch_pairs'].append([left[0],right[0]])
    with _com_apartment():
        import soundcard as sc
        speaker=sc.default_speaker();mic=sc.get_microphone(speaker.id,include_loopback=True)
        for device,_ in sources:
            # The default alias and named output share one device; test all GM
            # programs once and the explicit named alias in the switching matrix.
            if device not in ('default',) and not banks.is_synth_source(device):continue
            programs=banks.available_programs(device) if banks.is_synth_source(device) else range(128)
            first=next(iter(programs));router=MidiRouter({k:dict(device=device,program=first) for k in ('melody','chords')})
            try:
                with mic.recorder(samplerate=RATE,channels=2,blocksize=512) as capture:
                    capture.record(numframes=22050)
                    for program in programs:
                        router.stop();capture.record(numframes=11025);router.send(0xc0,program)
                        key=48 if 32<=program<=43 else 60
                        router.send(0x90,key,85);data=capture.record(numframes=22050)
                        router.send(0x80,key);tail=capture.record(numframes=22050)
                        row=dict(device=device,program=program,peak=float(abs(data).max()),rms=float(np.sqrt(np.mean(data**2))),tail_rms=float(np.sqrt(np.mean(tail[-2048:]**2))))
                        assert np.isfinite(data).all() and row['peak']>1e-6,(device,program,'inaudible device')
                        report['loopback'].append(row);save(report)
                        print('loopback',device,program,flush=True)
            finally:router.close()

def save(report):
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--loopback',action='store_true');parser.add_argument('--live-only',action='store_true');args=parser.parse_args()
    banks.rescan();report=dict(version=__version__,status='running',note_cases=0,presets=[],performance=[],switch_pairs=[],loopback=[])
    if args.live_only:report=json.loads((OUT/'report.json').read_text('utf-8'));report['loopback']=[];report['switch_pairs']=[]
    try:
        if not args.live_only:offline(report)
        if args.loopback or args.live_only:live(report)
        report['status']='passed' if not any(p['silent'] for p in report['presets']) else 'failed'
    except Exception as exc:report['status']='failed';report['error']=repr(exc);raise
    finally:save(report)

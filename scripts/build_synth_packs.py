"""Build separate STK synth packs. Requires official STK 5.0.1 and Zig 0.14.1.

Source inputs stay under development/synth-candidates, outside every release.
Only used STK classes and two mathematical oscillator tables are compiled.
No recorded instrument samples or filesystem access are needed at runtime.
"""
import argparse,hashlib,json,os,re,shutil,struct,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from popscore import __version__

def build():
    parser=argparse.ArgumentParser();parser.add_argument('--zig',type=Path);parser.add_argument('--stk',type=Path)
    args=parser.parse_args()
    stk=args.stk or next((ROOT/'development/synth-candidates/stk').glob('*/include')).parent
    zig=args.zig or next((ROOT/'development/toolchains').glob('zig-*/zig.exe'))
    dest=ROOT/'build/stk-pack';dest.mkdir(parents=True,exist_ok=True)
    classes=set();pending=['Rhodey','Wurley','BeeThree','TubeBell','Plucked','StifKarp','Bowed','Brass','Clarinet','Flute','Saxofony','BandedWG','Sitar','BlowHole','BlowBotl','Recorder','PercFlut','FMVoices']
    while pending:
        name=pending.pop()
        if name in classes:continue
        classes.add(name)
        for folder,suffix in [('include','.h'),('src','.cpp')]:
            file=stk/folder/(name+suffix)
            if not file.exists():continue
            text=file.read_text('utf-8');(dest/file.name).write_text(text,'utf-8')
            pending.extend(n for n in re.findall(r'#include "([\w]+)\.h"',text) if (stk/'include'/(n+'.h')).exists())
    # STK uses FileLoop for FM oscillators. Embed its two original, synthetic
    # single-cycle waveforms; remove loading of recorded/raw files altogether.
    tables=[]
    for name in ('sinewave','fwavblnk'):
        raw=(stk/'rawwaves'/(name+'.raw')).read_bytes();values=struct.unpack('>'+str(len(raw)//2)+'h',raw)
        tables.append('static const short '+name+'[] = {'+','.join(map(str,values))+'};')
    (dest/'oscillators.h').write_text('// STK mathematical oscillator tables, under the STK license.\n'+'\n'.join(tables),'utf-8')
    path=dest/'FileLoop.cpp';text=path.read_text('utf-8');start=text.index('  // Call close()');end=text.index('\nvoid FileLoop :: setRate',start)
    text=text[:start]+'''  const bool sine = fileName.find("sinewave.raw") != std::string::npos;
  const short *wave = sine ? sinewave : fwavblnk;
  fileSize_ = sine ? sizeof(sinewave)/sizeof(short) : sizeof(fwavblnk)/sizeof(short);
  chunking_=false;data_.resize(fileSize_+1,1);lastFrame_.resize(1,1);
  double peak=1;for(unsigned i=0;i<fileSize_;++i)peak=std::max(peak,std::abs(double(wave[i])));
  for(unsigned i=0;i<fileSize_;++i)data_[i]=wave[i]/peak;
  data_[fileSize_]=data_[0];setRate(1);reset();
}
''' + text[end:]
    text=text.replace('#include <cmath>','#include <cmath>\n#include <algorithm>\n#include "oscillators.h"');path.write_text(text,'utf-8')
    # Per-instance PRNG: reproducible rendering, no global rand()/srand() races
    # between real-time playback and an offline export running concurrently.
    path=dest/'Noise.h';text=path.read_text('utf-8').replace('protected:\n','protected:\n  unsigned int state_=0x9e3779b9u;\n  StkFloat nextNoise(){state_^=state_<<13;state_^=state_>>17;state_^=state_<<5;return double(state_)/2147483648.0-1.0;}\n')
    text=text.replace('(StkFloat) ( 2.0 * rand() / (RAND_MAX + 1.0) - 1.0 )','nextNoise()');path.write_text(text,'utf-8')
    path=dest/'Noise.cpp';text=path.read_text('utf-8');a=text.index('  if ( seed == 0 )');b=text.index('\n}',a);text=text[:a]+'  state_ = seed ? seed : 0x9e3779b9u;'+text[b:];path.write_text(text,'utf-8')
    # Sitar continuously moves its fractional delay. A moving all-pass delay
    # can grow spuriously at integer boundaries; linear interpolation is
    # bounded and keeps the same plucked-string model without feedback spikes.
    path=dest/'Sitar.h';path.write_text(path.read_text('utf-8').replace('DelayA','DelayL'),'utf-8')
    shutil.copy2(ROOT/'native/stk_pack.cpp',dest/'stk_pack.cpp')
    dll=dest/'lingfeng-stk.dll'
    command=[str(zig.resolve()),'c++','-target','x86_64-windows-gnu','-O2','-DNDEBUG','-D_USE_MATH_DEFINES','-D__LITTLE_ENDIAN__','-std=c++17','-shared','-static','-I'+str(dest),'-o',str(dll),*[str(p) for p in dest.glob('*.cpp')]]
    response=dest/'compile.rsp';response.write_text(' '.join('"'+x.replace('\\','/')+'"' for x in command[2:]),'utf-8')
    env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(ROOT/'build/zig-cache'),TEMP=str(ROOT/'tmp'),TMP=str(ROOT/'tmp'))
    subprocess.run([command[0],'c++','@'+str(response)],check=True,cwd=ROOT,env=env)
    # Preset IDs are GM-compatible for MIDI/DAW export, not a claim of realism.
    core=[
        (0,'柔和 FM 键盘','Soft FM keys',0,{2:24,4:45},.27),
        (1,'明亮 FM 键盘','Bright FM keys',0,{2:85,4:85},.23),
        (2,'清脆电键盘','Crisp electric keys',1,{2:60,4:30},.23),
        (4,'Rhodey 电钢琴','Rhodey electric piano',0,{},.25),
        (5,'Wurley 电钢琴','Wurley electric piano',1,{},.25),
        (24,'柔和拨弦','Soft plucked string',2,{},.33),
        (25,'明亮钢弦','Bright stiff string',3,{4:32,11:70,1:30},.22),
        (26,'短音拨弦','Short plucked string',3,{4:80,11:25,1:10},.25),
        (32,'拨弦低音','Plucked bass',2,{},.42),
        (33,'电贝斯模型','Stiff string bass',3,{4:45,11:50,1:3},.35),
        (40,'明亮弓弦','Bright bowed string',4,{2:80,4:45,1:0},.3),
        (41,'柔和弓弦','Soft bowed string',4,{2:65,4:85,1:0},.28),
        (42,'大提琴模型','Cello model',4,{2:70,4:65,1:0},.34),
        (43,'弓弦低音','Bowed bass',4,{2:80,4:90,1:0},.34),
        (48,'弦乐铺底','Bowed string pad',4,{2:72,4:55,1:6},.25)]
    extra=[(11,'敲击条','Struck bar',11,{16:1},.54),(14,'管钟','Tubular bell',6,{},.2),
           (16,'拉杆风琴模型','Drawbar organ model',5,{},.18),(19,'柔和风琴','Soft organ',5,{2:20,4:25},.2),
           (56,'铜管模型','Brass model',7,{1:0},.18),(65,'萨克斯模型','Saxophone model',10,{1:0},.22),
           (71,'单簧管模型','Clarinet model',8,{1:0,4:0},.25),(73,'长笛模型','Flute model',9,{1:0,4:0},.4)]
    acoustic=[
        (8,'柔和钟琴键盘','Soft bell keys',6,{2:20,4:20,1:0},.18),
        (12,'木质敲击键盘','Wooden mallet keys',11,{16:0,2:0,1:90},.70),
        (52,'元音合唱模型','Vowel choir model',17,{2:50,4:1,1:0},.20),
        (53,'柔和元音模型','Soft vowel model',17,{2:35,4:9,1:0},.20),
        (71,'音孔单簧管','Tone-hole clarinet',13,{2:64,4:0,11:127,1:0},.26),
        (74,'竖笛模型','Recorder model',15,{2:64,4:0,16:32,1:0},.12),
        (75,'FM 排箫模型','FM pan flute model',16,{2:30,4:20,1:0},.23),
        (76,'吹瓶模型','Blown bottle model',14,{4:0,1:0},.25),
        (104,'西塔琴模型','Sitar model',12,{},.42),
        (105,'班卓拨弦模型','Banjo pluck model',3,{4:80,11:35,1:5},.27),
        (106,'三味线拨弦模型','Shamisen pluck model',3,{4:100,11:30,1:10},.28),
        (107,'筝拨弦模型','Koto pluck model',3,{4:30,11:90,1:4},.30),
        (112,'玻璃钟模型','Glass bell model',11,{16:2,2:0,1:100},1.20),
        (113,'颂钵模型','Singing bowl model',11,{16:3,2:0,1:95},.55)]
    for ident,label,en_label,rows in [('stk-essentials','STK · 键盘与弦乐','STK Essentials',core),('stk-colors','STK · 风琴与管乐','STK Colors',extra),('stk-acoustic','STK · 扩展乐器','STK Acoustic Models',acoustic)]:
        pack=ROOT/'synths'/ident;pack.mkdir(parents=True,exist_ok=True)
        shutil.copy2(dll,pack/dll.name);shutil.copy2(stk/'LICENSE',pack/'LICENSE-STK.txt');shutil.copy2(ROOT/'LICENSE',pack/'LICENSE-Lingfeng.txt')
        for relative in ('LICENSE','lib/libcxx/LICENSE.TXT','lib/libcxxabi/LICENSE.TXT','lib/libunwind/LICENSE.TXT','lib/libc/mingw/COPYING'):
            notice=pack/'licenses'/'zig-runtime'/relative;notice.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(zig.parent/relative,notice)
        presets=[dict(program=p,name=cn,name_en=en,model=m,controls=c,gain=g,cutoff_hz=5000 if m in (4,7,10,13,15,17) else 6500) for p,cn,en,m,c,g in rows]
        data=dict(schema=1,id=ident,name=label,name_en=en_label,version=__version__,abi=1,platform='windows-x64',library=dll.name,sha256=hashlib.sha256(dll.read_bytes()).hexdigest(),license='STK permissive license',license_file='LICENSE-STK.txt',source='https://github.com/thestk/stk/tree/5.0.1',author='Perry R. Cook, Gary P. Scavone and STK contributors',presets=presets)
        (pack/'synth.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),'utf-8')
        (pack/'README.txt').write_text('将整个 '+ident+' 文件夹放入 Lingfeng.exe 同级的 synths 目录，然后在 设置 → 音源与音色 点击“重新扫描并保存”。\nCopy this folder into synths next to Lingfeng.exe, then rescan in sound settings.\nSTK 5.0.1 native algorithms; no recorded instrument samples. FM uses two embedded single-cycle mathematical oscillator tables.\nOriginal STK terms in LICENSE-STK.txt; the host/bridge/preset files use MIT.\n','utf-8')
        src=pack/'source';src.mkdir(exist_ok=True)
        for file in dest.iterdir():
            if file.suffix in ('.h','.cpp'):shutil.copy2(file,src/file.name)
        shutil.copy2(ROOT/'native/stk_pack.cpp',src/'stk_pack.cpp')
        (src/'BUILD.txt').write_text('Zig 0.14.1, PowerShell from this source folder:\n$inputs = (Get-ChildItem -Filter *.cpp).FullName\nzig c++ -target x86_64-windows-gnu -O2 -DNDEBUG -D_USE_MATH_DEFINES -D__LITTLE_ENDIAN__ -std=c++17 -shared -static -I. -o ../lingfeng-stk.dll $inputs\nUpdate synth.json sha256 after rebuilding.\nModifications: embedded STK oscillator cycles; instance-local xorshift noise; stable linear Sitar delay; MIT MIDI voice pool, tone filtering and velocity calibration.\nC++/compiler runtime notices: ../licenses/zig-runtime/. Toolchain: https://ziglang.org/download/0.14.1/\n','utf-8')
        print(ident,dll.stat().st_size,len(presets))

if __name__=='__main__':build()

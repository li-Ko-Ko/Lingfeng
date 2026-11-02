"""Build Lingfeng's free piano packs from hash-pinned upstream assets.

python scripts/build_piano_packs.py --download --pack all
python scripts/build_piano_packs.py --download --pack upgrades --zip
Only --download accesses the network. Inputs are cached in output/piano-sources/.
Python standard library only; no sample re-encoding or build-time audio dependency.
The optional grand and 0.53 electric/GM collections remain separate downloads.
The upgrades selection preserves the original 0.52 small/grand artifacts.
"""
import argparse,hashlib,json,re,shutil,stat,sys,tarfile,time,urllib.parse,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
VERSION='0.52'
UPGRADE_VERSION='0.53'
DISCORD_REF='7a9c478fe331f94f246d33332f0adedb25bbbe27'
GREG_REF='8c3e581acda3594b553948ff0222d4f84a698376'
KW_REF='570f6c60ed2eff67accad3b85d5b452e57a3ad28'
GRAND_REF='8432465f1fea83016635836c9850ac2b6398ffd3'
SFIZZ_HASH='aa4bfa4ad9a57cfbb3c832a50be14bfe5aeaf7a36ffcdf0178547abe8719e653'
ARCHIVES={
 'kw':dict(file='kw.zip',url='https://codeload.github.com/freepats/upright-piano-KW/zip/'+KW_REF,sha256='4ed71b20eb63758c3c7c458bcf61b977ea918cad4cb0a99bc61f56ce10f9240a',root='upright-piano-KW-'+KW_REF),
 'greg':dict(file='greg.zip',url='https://codeload.github.com/sfzinstruments/GregSullivan.E-Pianos/zip/'+GREG_REF,sha256='c36a5c9092688b9419d7d3ab330d9b317856c3752c3696bdc7e0b65dd4d79bdf',root='GregSullivan.E-Pianos-'+GREG_REF),
 'grand':dict(file='grand.zip',url='https://codeload.github.com/jlearman/zynthian-salamander-grand/zip/'+GRAND_REF,sha256='92cca7681e487976932cc9f143333ac5f4cac5c6a24fb377853a1077a15aa0fc',root='zynthian-salamander-grand-'+GRAND_REF,archive_bytes=190560219),
 'sfizz':dict(file='sfizz-win64.zip',url='https://github.com/sfztools/sfizz/releases/download/1.2.3/sfizz-1.2.3-win64.zip',sha256='7431cbe9b7f2e71a9ff4b12fbbe82c766dbf75b1eedecca627e7506cb06a9fcc'),
 'sfizz-source':dict(file='sfizz-1.2.3.tar.gz',url='https://github.com/sfztools/sfizz/releases/download/1.2.3/sfizz-1.2.3.tar.gz',sha256='a9339eac7620d7f0f6b44bdfe860680fab73e66efad4b5f15b21198dd9436822')}
RAW_INPUTS=[{"path":"Discord GM/Melodic/005-Electric Piano 1.sfz","git_sha1":"283b7351fee7f6d626ef837eb61bcf19c72d2b58","size":2240},{"path":"Discord GM/Melodic/005-Electric Piano 1/A_029__F1_3.wav","git_sha1":"94d930dd4d597cd46838bd85f043f02dc3c2cd46","size":460916},{"path":"Discord GM/Melodic/005-Electric Piano 1/A_035__B1_3.wav","git_sha1":"eac72f97ecdb99e2295f7825f69b0030ea72b358","size":405658},{"path":"Discord GM/Melodic/005-Electric Piano 1/A_040__E2_3.wav","git_sha1":"a49d7fc78057b11767fab319af6de9f8003faee2","size":567926},{"path":"Discord GM/Melodic/005-Electric Piano 1/A_045__A2_3.wav","git_sha1":"988a870272800028801bc12000a5561c21b2e057","size":597638},{"path":"Discord GM/Melodic/005-Electric Piano 1/A_050__D3_3.wav","git_sha1":"3b8d5678bb104eebbebfca6bd4e8405a4696356c","size":513604},{"path":"Discord GM/Melodic/005-Electric Piano 1/A_055__G3_3.wav","git_sha1":"d79df0b407396859b5e41fadde5c026f44d71bf5","size":545332},{"path":"Discord GM/Melodic/005-Electric Piano 1/A_059__B3_3.wav","git_sha1":"b6fe92670a9c191cda6f6919c1e7f4193e8cb3f2","size":450466},{"path":"Discord GM/Melodic/005-Electric Piano 1/A_062__D4_3.wav","git_sha1":"db0e12a900de793ad7154c11de17106b82ab5afe","size":566168},{"path":"Discord GM/Melodic/005-Electric Piano 1/A_065__F4_3.wav","git_sha1":"138073651e3c9fad1ab11df13604f3c7b353f056","size":500578},{"path":"Discord GM/Melodic/005-Electric Piano 1/A_071__B4_4.wav","git_sha1":"175dfd30ad2bdc561896afc2c9f4b369ddf13a10","size":415082},{"path":"Discord GM/Melodic/005-Electric Piano 1/A_076__E5_4.wav","git_sha1":"ec3219e84d1c90fc848a365d71dd476b0e825d8b","size":283322},{"path":"Discord GM/Melodic/005-Electric Piano 1/A_081__A5_4.wav","git_sha1":"dec3fe48989e2a4919ac3e25246ea820401449e7","size":352990},{"path":"Discord GM/Melodic/005-Electric Piano 1/A_086__D6_4.wav","git_sha1":"64364d58bcebe6167eec79b549f45dc44ce74741","size":325258},{"path":"Discord GM/Melodic/005-Electric Piano 1/A_091__G6_4.wav","git_sha1":"dbf7c1e7df7321b42d1479f570893ad3e4f5a708","size":141148},{"path":"Discord GM/Melodic/005-Electric Piano 1/A_096__C7_4.wav","git_sha1":"d6c8fce9c86c24ebc660f1cb4b21bcd784355214","size":61232}]
CCBY_HASH='e6bc9e9c474700b708f568bac9e5a8a9bcb2b1dad53442f5ba449fcb848b8e76'
CCBY_URL='https://raw.githubusercontent.com/creativecommons/cc-legal-tools-data/main/legacy/legalcode/by_3.0.txt'

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,text):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
def write_json(path,value):write(path,json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def copy(source,target):
 target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
def get(url,path,expected,download,git_blob=False):
 def valid(p):
  if not p.is_file():return False
  data=p.read_bytes()
  value=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest() if git_blob else hashlib.sha256(data).hexdigest()
  return value==expected
 if valid(path):return path
 if not download:raise ValueError('Missing or changed input: '+str(path)+'; use --download to fetch verified upstream assets')
 path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.part')
 try:
  for attempt in range(3):
   try:
    request=urllib.request.Request(url,headers={'User-Agent':'Lingfeng reproducible piano pack builder'})
    with urllib.request.urlopen(request,timeout=45) as src,temp.open('wb') as out:
     while chunk:=src.read(1024*1024):out.write(chunk)
    if not valid(temp):raise ValueError('Source checksum mismatch: '+url)
    temp.replace(path);return path
   except OSError:
    if attempt==2:raise
    time.sleep(attempt+1)
 finally:
  if temp.exists():temp.unlink()
def archive(cache,name,download):
 entry=ARCHIVES[name];return get(entry['url'],cache/entry['file'],entry['sha256'],download)
def zip_files(path,prefix,dest,accept=lambda n:True):
 with zipfile.ZipFile(path) as z:
  for info in z.infolist():
   if info.is_dir() or not info.filename.startswith(prefix+'/'):continue
   relative=info.filename[len(prefix)+1:]
   if not accept(relative):continue
   target=(dest/relative).resolve()
   if not target.is_relative_to(dest.resolve()) or stat.S_ISLNK(info.external_attr>>16):raise ValueError('Unsafe ZIP member')
   target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(info))
def runtime(cache,dest,download):
 source=cache/ARCHIVES['sfizz-source']['file']
 # Reuse the already verified source shipped with a previous pack or checkout.
 if not source.exists():
  for candidate in (ROOT/'synths/piano-small/runtime/sfizz-1.2.3.tar.gz',ROOT/'licenses/sfizz-1.2.3/sfizz-1.2.3.tar.gz'):
   if candidate.is_file() and digest(candidate)==ARCHIVES['sfizz-source']['sha256']:copy(candidate,source);break
 source=archive(cache,'sfizz-source',download)
 binary=archive(cache,'sfizz',download)
 with zipfile.ZipFile(binary) as z:(dest/'sfizz.dll').write_bytes(z.read('bin/Release/sfizz.dll'))
 if digest(dest/'sfizz.dll')!=SFIZZ_HASH:raise ValueError('sfizz DLL checksum mismatch')
 rt=dest/'runtime';rt.mkdir(exist_ok=True);copy(source,rt/source.name)
 with tarfile.open(source) as t:
  for item in t.getmembers():
   if not item.isfile():continue
   relative=Path(item.name).relative_to('sfizz-1.2.3')
   if any(x in relative.name.casefold() for x in ('license','copying','copyright','authors')):
    target=(rt/'notices'/relative).resolve()
   elif relative.as_posix() in ('external/st_audiofile/thirdparty/dr_libs/dr_flac.h','external/st_audiofile/thirdparty/dr_libs/dr_wav.h','external/st_audiofile/thirdparty/stb_vorbis/stb_vorbis.c'):
    target=(rt/'notices'/relative).with_name(relative.name+'.notice-source').resolve()
   else:continue
   if not target.is_relative_to(rt.resolve()):raise ValueError('Unsafe runtime source member')
   target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(t.extractfile(item).read())
 write(rt/'SOURCE.txt','Unmodified official sfizz 1.2.3 Windows x64 library.\n'+ARCHIVES['sfizz']['url']+'\nDLL SHA256: '+SFIZZ_HASH+'\nSource: '+ARCHIVES['sfizz-source']['url']+'\nSource SHA256: '+ARCHIVES['sfizz-source']['sha256']+'\nThe complete upstream source archive and dependency notices are included.\nSome notices cover source-only tools; no plugins or XMMS WavPack plugin are shipped.\nUpstream repository was archived on 2026-06-21.\n')
 license_input=cache/'CC-BY-3.0.txt'
 if not license_input.exists():
  candidate=ROOT/'licenses/sfz-sources/CC-BY-3.0.txt'
  if candidate.exists() and digest(candidate)==CCBY_HASH:copy(candidate,license_input)
 get(CCBY_URL,license_input,CCBY_HASH,download);copy(license_input,rt/'CC-BY-3.0.txt')
def manifest(ident,presets,license,author,source,voices):
 return dict(schema=1,id=ident,name='轻量钢琴与电钢琴' if ident=='piano-small' else 'Salamander 音乐会钢琴',name_en='Piano & Electric Essentials' if ident=='piano-small' else 'Salamander Concert Grand',version=VERSION,abi=1,platform='windows-x64',engine='sfz',library='sfizz.dll',sha256=SFIZZ_HASH,license=license,license_file='LICENSE-SAMPLES.txt',source=source,author=author,voices=voices,presets=presets)
def preset(program,name,en,path,gain=0.5,**extra):
 return dict(program=program,name=name,name_en=en,model=0,sfz=path,gain=gain,**extra)
def finish(dest,data,sources,notes):
 write_json(dest/'synth.json',data);write_json(dest/'source.json',dict(schema=1,pack=data['id'],version=data['version'],inputs=sources,modifications=notes))
 files={f.relative_to(dest).as_posix():digest(f) for f in sorted(dest.rglob('*')) if f.is_file() and f.name!='files.sha256.json'}
 write_json(dest/'files.sha256.json',files)
 print(data['id'],sum(p.stat().st_size for p in dest.rglob('*') if p.is_file()),'bytes',len(data['presets']),'presets',flush=True)
def small(cache,dest,download):
 dest.mkdir(parents=True,exist_ok=True);runtime(cache,dest,download)
 kw=archive(cache,'kw',download);kwdir=dest/'acoustic'
 zip_files(kw,ARCHIVES['kw']['root'],kwdir,lambda n:n.startswith('samples/') or n in ('UprightPianoKW-20220221.sfz','LICENSE','README.md'))
 original=kwdir/'UprightPianoKW-20220221.sfz'
 write(kwdir/'bright.sfz',original.read_text('utf-8').replace('<global>','// Lingfeng bright variation: +3 dB broad EQ at 2.8 kHz.\n<global>\neq1_freq=2800 eq1_bw=2 eq1_gain=3',1))
 greg=archive(cache,'greg',download);gregdir=dest/'electric'
 zip_files(greg,ARCHIVES['greg']['root'],gregdir,lambda n:n.startswith(('CP80/','Pianet T/','Wurlitzer EP200/')) or n in ('LICENSE','README.md'))
 for folder in ('CP80','Pianet T','Wurlitzer EP200'):
  f=gregdir/folder/(folder+'.sfz');text=f.read_text('utf-8')
  lows=[int(x) for x in re.findall(r'\blokey=(\d+)',text)];highs=[int(x) for x in re.findall(r'\bhikey=(\d+)',text)]
  text=re.sub(r'\blokey='+str(min(lows))+r'\b','lokey=21',text);text=re.sub(r'\bhikey='+str(max(highs))+r'\b','hikey=108',text)
  text=re.sub(r'(?:group_label|region_label)=[^\s]+','',text)
  write(f,'// Lingfeng: edge ranges extended to MIDI21-108; ARIA labels removed.\n'+text)
 rhodes=dest/'rhodes';rhodes.mkdir(exist_ok=True)
 raw_sources=[]
 for item in RAW_INPUTS:
  url='https://raw.githubusercontent.com/sfzinstruments/Discord-SFZ-GM-Bank/'+DISCORD_REF+'/'+urllib.parse.quote(item['path'],safe='/')
  src=get(url,cache/'discord'/item['path'],item['git_sha1'],download,git_blob=True)
  # Keep the upstream folder name because the unmodified SFZ refers to it.
  target=rhodes/Path(item['path']).name if item['path'].endswith('.sfz') else rhodes/'005-Electric Piano 1'/Path(item['path']).name
  copy(src,target);raw_sources.append(dict(url=url,sha256=digest(src),git_sha1=item['git_sha1'],bytes=src.stat().st_size))
  if target.suffix=='.sfz':
   text=target.read_text('utf-8').replace('ampeg_sustain=0','// Lingfeng: make the intended global envelope explicit for sfizz.\n<global> ampeg_sustain=0',1)
   write(target,text)
 copy(kwdir/'LICENSE',rhodes/'CC0-1.0.txt')
 rows=[preset(0,'Kawai 原声钢琴','Kawai acoustic piano','acoustic/UprightPianoKW-20220221.sfz',0.55,license='CC0-1.0',author='Gonzalo, Roberto / FreePats'),preset(1,'明亮原声钢琴','Bright acoustic piano','acoustic/bright.sfz',0.5,license='CC0-1.0',author='Gonzalo, Roberto / FreePats; Lingfeng bright variation'),preset(2,'CP80 电大钢琴','CP80 electric grand','electric/CP80/CP80.sfz',0.45,license='CC-BY-3.0',author='Greg Sullivan; SFZ mapping by kinwie'),preset(4,'Rhodes 电钢琴','Rhodes electric piano','rhodes/005-Electric Piano 1.sfz',0.5,license='CC0-1.0',author='Jeff Learman'),preset(5,'Wurlitzer 电钢琴','Wurlitzer electric piano','electric/Wurlitzer EP200/Wurlitzer EP200.sfz',0.5,license='CC-BY-3.0',author='Greg Sullivan; SFZ mapping by kinwie'),preset(6,'Pianet T 电键盘','Pianet T electric keys','electric/Pianet T/Pianet T.sfz',0.6,license='CC-BY-3.0',author='Greg Sullivan; SFZ mapping by kinwie')]
 data=manifest('piano-small',rows,'CC0-1.0; CC-BY-3.0; sfizz BSD-2-Clause','Gonzalo and Roberto / FreePats; Greg Sullivan; kinwie (SFZ mapping); Jeff Learman','https://github.com/freepats/upright-piano-KW ; https://github.com/sfzinstruments/GregSullivan.E-Pianos ; https://github.com/sfzinstruments/Discord-SFZ-GM-Bank',128)
 write(dest/'LICENSE-SAMPLES.txt','Free sample sources / 免费音色许可\n\nAcoustic piano: Upright Piano KW (2022-02-21), Gonzalo and Roberto / FreePats. CC0-1.0; acoustic/LICENSE.\nElectric grand, Wurlitzer EP200 and Pianet T: Greg Sullivan, SFZ conversion by kinwie. CC BY 3.0; electric/LICENSE and runtime/CC-BY-3.0.txt.\nRhodes: Jeff Learman, Discord GM separately released CC0 jRhodes subset. See its original SFZ license header and rhodes/CC0-1.0.txt. This does not license the full jRhodes3c/d sample libraries.\nEngine: sfizz 1.2.3, BSD-2-Clause and dependency notices in runtime/notices/.\nRedistribution and commercial use are permitted under each applicable license. Preserve credits and license texts and identify modifications.\nSources and exact revisions: source.json. Lingfeng applies playback gain, adds a bright acoustic variation, extends electric-piano edge zones to the 88-key range, removes cosmetic ARIA labels, and adds an explicit Rhodes global envelope header. Audio samples are unchanged.\nOriginal music and other input material retain their own rights.\n')
 write(dest/'README.txt','将整个 piano-small 文件夹复制到 Lingfeng.exe 同级 synths/，在设置→音源与音色重新扫描。\nCopy the complete piano-small folder into synths beside Lingfeng.exe, then rescan in Settings.\nSix presets: natural and bright Kawai acoustic piano, Yamaha CP80, Rhodes, Wurlitzer EP200 and Pianet T.\nThe acoustic bank retains its two velocity layers. Rhodes is a compact single-velocity CC0 GM version. Large concert-grand samples are an optional separate pack.\nReproduce: python scripts/build_piano_packs.py --download --pack small\nSource pins, modifications and output hashes are in source.json and files.sha256.json.\n')
 notes=['All audio samples copied unmodified.','KW bright variation adds +3 dB broad EQ at 2.8 kHz.','Greg electric-piano edge zones extended to MIDI21-108; cosmetic ARIA labels removed.','Rhodes global envelope header made explicit so sfizz applies the original ampeg_sustain=0 setting.','Preset linear gain calibrated separately; Rhodes uses the separately CC0 licensed single-velocity GM subset.']
 finish(dest,data,[ARCHIVES['kw'],ARCHIVES['greg'],dict(source='Discord-SFZ-GM-Bank',revision=DISCORD_REF,files=raw_sources),ARCHIVES['sfizz'],ARCHIVES['sfizz-source']],notes)
 return data
def grand(cache,dest,download):
 dest.mkdir(parents=True,exist_ok=True);runtime(cache,dest,download);entry=ARCHIVES['grand'];source=archive(cache,'grand',download)
 zip_files(source,entry['root'],dest,lambda n:n.startswith('flac/') or n in ('AccurateSalamanderGrand-Z.sfz','README.orig.txt','README.cyamauch.txt','README.md'))
 mapping=dest/'AccurateSalamanderGrand-Z.sfz'
 write(mapping,'// Lingfeng: lowest velocity region extended from MIDI velocity2 to1.\n'+re.sub(r'\blovel=2\b','lovel=1',mapping.read_text('utf-8')))
 data=manifest('piano-grand',[preset(0,'Salamander 音乐会钢琴','Salamander concert grand','AccurateSalamanderGrand-Z.sfz',0.5,license='CC-BY-3.0',author='Alexander Holm; Chisato Yamauchi; Jeff Learman')],'CC-BY-3.0 (samples); CC0-1.0 (SFZ); sfizz BSD-2-Clause','Alexander Holm; Chisato Yamauchi (remastering); Jeff Learman (compact SFZ/FLAC adaptation)','https://github.com/jlearman/zynthian-salamander-grand/tree/'+GRAND_REF,256)
 write(dest/'LICENSE-SAMPLES.txt','Accurate Salamander Grand for Zynthian / 精简音乐会钢琴\n\nOriginal Salamander Grand Piano samples: Alexander Holm. Accurate-Salamander remastering: Chisato Yamauchi. Compact FLAC/SFZ adaptation: Jeff Learman.\nAudio samples: Creative Commons Attribution 3.0, https://creativecommons.org/licenses/by/3.0/ ; full text runtime/CC-BY-3.0.txt. SFZ mapping: CC0.\nThe upstream README.md explicitly states there are no restrictions or requirements for music made using this sampleset. Preserve attribution for redistribution of the samples themselves.\nSee the original README.orig.txt, README.cyamauch.txt and README.md for provenance, processing and original credits.\nLingfeng keeps audio samples unchanged, extends the lowest SFZ velocity region from MIDI velocity2 to1, adds pack metadata and sets playback gain.\nThe unmodified sfizz 1.2.3 runtime is covered by BSD-2-Clause plus dependency notices. Complete source and notices: runtime/.\n')
 write(dest/'README.txt','可选高品质原声钢琴音源，不包含在轻量安装包中。\nOptional high-quality acoustic grand pack, distributed separately from the lightweight application.\nCopy the complete piano-grand folder into synths beside Lingfeng.exe, then rescan and select Salamander Concert Grand.\nSixteen velocity layers, compact lossless FLAC samples; the original three README files describe tuning, half-pedaling and MIDI controls.\nReproduce: python scripts/build_piano_packs.py --download --pack grand\n')
 finish(dest,data,[entry,ARCHIVES['sfizz'],ARCHIVES['sfizz-source']],['Audio samples unchanged. Lowest SFZ velocity region extended from MIDI velocity2 to1 for audible playback at every supported note-on velocity. Lingfeng adds metadata and linear playback gain.'])
 text_files={p.name:p.read_text('utf-8') for p in dest.iterdir() if p.is_file() and p.name in ('LICENSE-SAMPLES.txt','README.txt','source.json','files.sha256.json')}
 return dict(id='piano-grand',name=data['name'],name_en=data['name_en'],url=entry['url'],sha256=entry['sha256'],archive_bytes=entry['archive_bytes'],archive_root=entry['root'],manifest=data,text_files=text_files)
UPGRADE_ASSETS={
 'fluid-r3':dict(file='fluid-r3.tar.gz',url='https://deb.debian.org/debian/pool/main/f/fluid-soundfont/fluid-soundfont_3.1.orig.tar.gz',sha256='2621acaa1c78e4abdb24bdd163230cc577e61276936d6aa6e3180582142f0343',archive_bytes=134835922,format='tar'),
 'fluidsynth':dict(file='fluidsynth-win64.zip',url='https://github.com/FluidSynth/fluidsynth/releases/download/v2.6.1/fluidsynth-v2.6.1-win10-x64-cpp11.zip',sha256='fab7a2e4b85675b66970f97a39bbc239729c5e0f237198b5922a6a73cbc8677c',archive_bytes=2727529,format='zip'),
 'fluidsynth-source':dict(file='fluidsynth-source.zip',url='https://codeload.github.com/FluidSynth/fluidsynth/zip/refs/tags/v2.6.1',sha256='0965a1132bf2dd20135687bee8b2034c110664b4b561fbacc9d515a92cad6031',archive_bytes=2501921,format='file',target='runtime/fluidsynth-2.6.1-source.zip'),
 'sndfile-source':dict(file='sndfile-source.tar.xz',url='https://github.com/libsndfile/libsndfile/releases/download/1.2.2/libsndfile-1.2.2.tar.xz',sha256='3799ca9924d3125038880367bf1468e53a1b7e3686a934f098b7e1d286cdb80e',archive_bytes=730760,format='file',target='runtime/libsndfile-1.2.2-source.tar.xz'),
 'mpg123-source':dict(file='mpg123-1.31.3.tar.bz2',url='https://www.mpg123.de/download/mpg123-1.31.3.tar.bz2',sha256='1ca77d3a69a5ff845b7a0536f783fee554e1041139a6b978f6afe14f5814ad1a',archive_bytes=1094474,format='file',target='runtime/mpg123-1.31.3-source.tar.bz2'),
 'lame-source':dict(file='lame-3.100.tar.gz',url='https://downloads.sourceforge.net/project/lame/lame/3.100/lame-3.100.tar.gz',sha256='ddfe36cab873794038ae2c1210557ad34857a4b6bdc515785d1da9e175b1da1e',archive_bytes=1524133,format='file',target='runtime/lame-3.100-source.tar.gz')}
UPGRADE_NOTICES=(
 ('ogg-COPYING.txt','https://raw.githubusercontent.com/xiph/ogg/v1.3.5/COPYING','40b96ef8f651ddb335766f7321eea7a0ea93cc4bcdab312a699d55efab576e52'),
 ('vorbis-COPYING.txt','https://raw.githubusercontent.com/xiph/vorbis/v1.3.7/COPYING','928871c8731c91b86071704394566350cc3aa4e4ed4dccdcb9fc9847d0463294'),
 ('flac-COPYING.Xiph.txt','https://raw.githubusercontent.com/xiph/flac/1.4.2/COPYING.Xiph','9cc3a24d4a4f95c9268198471993bbfb9a33179de9fd6866c16cafe3323d2e78'),
 ('opus-COPYING.txt','https://raw.githubusercontent.com/xiph/opus/v1.4/COPYING','9559c10646c282671e23b5cd23d9c9ae4c3b69424c4060f68614bb93f6747140'),
 ('vcpkg-mpg123-fix-m1-build.patch','https://raw.githubusercontent.com/microsoft/vcpkg/2023.04.15/ports/mpg123/fix-m1-build.patch','940da2564c97f455ef6a1584db5b39e52f7eb698c4a0bca69da8f90828cabcf9'),
 ('vcpkg-mpg123-fix-modulejack.patch','https://raw.githubusercontent.com/microsoft/vcpkg/2023.04.15/ports/mpg123/fix-modulejack.patch','4518011667c6820ad0deb1654ec70f426a651b515b662da83d62a5681cb9996d'),
 ('vcpkg-mpg123-vcpkg.json','https://raw.githubusercontent.com/microsoft/vcpkg/2023.04.15/ports/mpg123/vcpkg.json','ce654a7b0daecfc22f5c3078d2e31475f39c9331248e3be6e54d8046c7dae748'))

def upgrade_entry(dest,data,assets,runtime_id=None):
 # Files obtained from upstream archives are extracted explicitly; all local
 # curation, notices and metadata are trusted UTF-8 replacements in the catalog.
 upstream={path for asset in assets for path in asset.get('file_map',{}).values()}
 upstream.update(asset['target'] for asset in assets if asset.get('format')=='file')
 texts={p.relative_to(dest).as_posix():p.read_text('utf-8') for p in dest.rglob('*') if p.is_file() and p.relative_to(dest).as_posix() not in upstream and p.name not in ('sfizz.dll','synth.json') and not (runtime_id and p.is_relative_to(dest/'runtime'))}
 # Curated SFZ files replace originals after archive extraction.
 texts.update({p.relative_to(dest).as_posix():p.read_text('utf-8') for p in dest.rglob('*.sfz')})
 entry=dict(id=data['id'],name=data['name'],name_en=data['name_en'],manifest=data,assets=assets,archive_bytes=sum(a['archive_bytes'] for a in assets),text_files=texts)
 if runtime_id:entry['runtime_id']=runtime_id
 return entry

def electric(cache,dest,download):
 dest.mkdir(parents=True,exist_ok=True);runtime(cache,dest,download)
 path=archive(cache,'greg',download);prefix=ARCHIVES['greg']['root']
 zip_files(path,prefix,dest/'electric',lambda n:n.startswith(('CP80/','Pianet T/','Wurlitzer EP200/')) or n in ('LICENSE','README.md'))
 for folder in ('CP80','Pianet T','Wurlitzer EP200'):
  p=dest/'electric'/folder/(folder+'.sfz');text=p.read_text('utf-8')
  lows=[int(n) for n in re.findall(r'\blokey=(\d+)',text)];highs=[int(n) for n in re.findall(r'\bhikey=(\d+)',text)]
  text=re.sub(r'\blokey='+str(min(lows))+r'\b','lokey=21',text);text=re.sub(r'\bhikey='+str(max(highs))+r'\b','hikey=108',text);text=re.sub(r'(?:group_label|region_label)=[^\s]+','',text)
  write(p,'// Lingfeng: edge ranges extended to MIDI21-108; ARIA labels removed.\n'+text)
 rows=[preset(2,'CP80 电大钢琴','CP80 electric grand','electric/CP80/CP80.sfz',.45),preset(5,'Wurlitzer 电钢琴','Wurlitzer electric piano','electric/Wurlitzer EP200/Wurlitzer EP200.sfz',.5),preset(6,'Pianet T 电键盘','Pianet T electric keys','electric/Pianet T/Pianet T.sfz',.6)]
 data=manifest('piano-electric',rows,'CC-BY-3.0; sfizz BSD-2-Clause','Greg Sullivan (samples); kinwie (SFZ mapping)','https://github.com/sfzinstruments/GregSullivan.E-Pianos/tree/'+GREG_REF,128)
 data.update(version=UPGRADE_VERSION,name='Greg Sullivan 电钢琴',name_en='Greg Sullivan E-Pianos')
 write(dest/'LICENSE-SAMPLES.txt','Greg Sullivan E-Pianos: Yamaha CP80, Wurlitzer EP200 and Hohner Pianet T.\nSamples by Greg Sullivan; SFZ mapping by kinwie. CC BY 3.0; full text electric/LICENSE and runtime/CC-BY-3.0.txt.\nLingfeng extends edge zones to MIDI21-108, removes cosmetic ARIA labels and adjusts gain. Audio samples are unchanged.\nThe same three recordings are already included in Piano & Electric Essentials. This separate collection is an alternative installation, not a higher-detail resampling.\nEngine: unmodified sfizz 1.2.3, BSD-2-Clause plus runtime/notices/.\n')
 write(dest/'README.txt','可选 Greg Sullivan 电钢琴合集：CP80、Wurlitzer、Pianet T。\nOptional Greg Sullivan electric piano collection: CP80, Wurlitzer, Pianet T.\nThese are the same recordings included in piano-small. Keep piano-small for acoustic piano and Rhodes.\nCopy this complete folder into synths and rescan. Reproduce: python scripts/build_piano_packs.py --pack electric --download\n')
 finish(dest,data,[ARCHIVES['greg'],ARCHIVES['sfizz'],ARCHIVES['sfizz-source']],['Audio samples unchanged; electric edge ranges extended to MIDI21-108; cosmetic ARIA labels removed; host gain calibrated.'])
 mapping={}
 with zipfile.ZipFile(path) as z:
  for item in z.infolist():
   if item.is_dir() or not item.filename.startswith(prefix+'/'):continue
   rel=item.filename[len(prefix)+1:]
   if rel.startswith(('CP80/','Pianet T/','Wurlitzer EP200/')) or rel in ('LICENSE','README.md'):mapping[item.filename]='electric/'+rel
 asset=dict(url=ARCHIVES['greg']['url'],sha256=ARCHIVES['greg']['sha256'],archive_bytes=path.stat().st_size,format='zip',file_map=mapping)
 return upgrade_entry(dest,data,[asset],runtime_id='piano-small')

def gm(cache,dest,download):
 sys.path.insert(0,str(ROOT));from lingfeng.audio.gm_instruments import NAMES
 dest.mkdir(parents=True,exist_ok=True);assets=[]
 for key,value in UPGRADE_ASSETS.items():
  p=cache/value['file']
  if key=='lame-source' and not p.exists():
   candidate=ROOT/'licenses/audio-source/lame-3.100.tar.gz'
   if candidate.exists() and digest(candidate)==value['sha256']:copy(candidate,p)
  get(value['url'],p,value['sha256'],download)
  entry={k:v for k,v in value.items() if k!='file'}
  if value['format']=='file':copy(p,dest/value['target'])
  elif key=='fluid-r3':
   entry['file_map']={f'fluid-soundfont-3.1/{n}':n for n in ('FluidR3_GM.sf2','COPYING','README')}
   with tarfile.open(p) as t:
    for source,target in entry['file_map'].items():(dest/target).write_bytes(t.extractfile(source).read())
  elif key=='fluidsynth':
   entry['file_map']={f'fluidsynth-v2.6.1-win10-x64-cpp11/bin/{n}':'bin/'+n for n in ('libfluidsynth-3.dll','sndfile.dll')}
   with zipfile.ZipFile(p) as z:
    for source,target in entry['file_map'].items():
     out=dest/target;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(z.read(source))
  assets.append(entry)
 # Include complete corresponding LGPL sources plus individual readable notices.
 with zipfile.ZipFile(cache/'fluidsynth-source.zip') as z:
  for source,target in [('fluidsynth-2.6.1/LICENSE','runtime/notices/FluidSynth-LICENSE.txt'),('fluidsynth-2.6.1/AUTHORS','runtime/notices/FluidSynth-AUTHORS.txt'),('fluidsynth-2.6.1/.github/workflows/windows.yml','runtime/build/fluidsynth-windows.yml')]:write(dest/target,z.read(source).decode('utf-8'))
 for filename,prefix,names in [('sndfile-source.tar.xz','libsndfile-1.2.2',('COPYING','AUTHORS','src/GSM610/COPYRIGHT')),('mpg123-1.31.3.tar.bz2','mpg123-1.31.3',('COPYING',)),('lame-3.100.tar.gz','lame-3.100',('COPYING','LICENSE'))]:
  with tarfile.open(cache/filename) as t:
   for name in names:write(dest/'runtime/notices'/prefix/(name.replace('/','-')+'.txt'),t.extractfile(prefix+'/'+name).read().decode('utf-8',errors='replace'))
 notice_inputs=[]
 for name,url,expected in UPGRADE_NOTICES:
  p=get(url,cache/name,expected,download);copy(p,dest/'runtime/notices'/name);notice_inputs.append(dict(url=url,sha256=expected))
 hashes={p.relative_to(dest).as_posix():digest(p) for p in (dest/'bin').glob('*.dll')}
 rows=[dict(program=i,name=cn,name_en=en,model=i,sf2='FluidR3_GM.sf2',bank=0,gain=.65) for i,(cn,en) in enumerate(NAMES)]
 data=dict(schema=1,id='keyboard-gm',name='FluidR3 全乐器音源',name_en='FluidR3 General MIDI',version=UPGRADE_VERSION,abi=1,platform='windows-x64',engine='sf2',library='bin/libfluidsynth-3.dll',sha256=hashes['bin/libfluidsynth-3.dll'],library_hashes=hashes,license='MIT (soundfont); LGPL-2.1-or-later (FluidSynth/libsndfile and MPEG codecs); BSD codec notices',license_file='LICENSE-SAMPLES.txt',source=UPGRADE_ASSETS['fluid-r3']['url'],author='Frank Wen; Toby Smithe; FluidSynth and libsndfile contributors',voices=256,presets=rows)
 write(dest/'LICENSE-SAMPLES.txt','FluidR3 General MIDI optional sound pack\n\nSoundfont: FluidR3 3.1 by Frank Wen (2000-2002, 2008), with 2008 contributions by Toby Smithe, under MIT. Original COPYING and README are retained. All 128 General MIDI melodic programs are provided; audio samples and soundfont parameters are unchanged.\nRenderer: FluidSynth 2.6.1 and libsndfile 1.2.2, LGPL-2.1-or-later. Statically linked MPEG codecs include mpg123 1.31.3 (LGPL-2.1-or-later) and LAME 3.100 (LGPL-2.0-or-later). BSD-style codec notices for Ogg, Vorbis, FLAC and Opus are included.\nComplete corresponding LGPL source archives and readable notices are in runtime/. The upstream Windows workflow records the official binary build. The mpg123 source SHA512 matches the vcpkg source archive identifier embedded in sndfile.dll; source patch inputs are included.\nThe DLL files remain separate and replaceable. Compatible modified libraries may replace them; reverse engineering for debugging such modifications is not prohibited. No audio/MIDI device driver, SDL3 runtime or command-line executable is distributed or started.\nLingfeng adds manifest, host-side gain, no-reverb/no-chorus settings and these notices. This pack does not affect ownership of the musical composition or other material played through it.\n')
 write(dest/'README.txt','可选 FluidR3 全乐器音源：128 个 GM 旋律音色，涵盖钢琴、电钢琴、风琴、吉他、贝斯、弦乐、管乐、合成器和音效。\nOptional FluidR3 soundfont: all 128 GM melodic programs, including acoustic/electric pianos, organs, guitars, basses, strings, winds, synths and effects.\nCopy this whole folder into synths, rescan, then choose FluidR3 General MIDI for either track. The lightweight application and its existing piano packs remain usable without this download.\nSoundfont samples are unchanged; FluidSynth effects are disabled for predictable mixing and prompt stop. Source archives, notices and replacement terms: runtime/ and LICENSE-SAMPLES.txt.\nReproduce: python scripts/build_piano_packs.py --pack gm --download\n')
 finish(dest,data,[*assets,*notice_inputs],['Soundfont and runtime DLLs unchanged. Only 128 bank0 melodic presets are exposed; built-in drum presets remain in the original SF2 but are not presented as a separate drum track. Host gain and disabled reverb/chorus apply equally to playback and export.'])
 return upgrade_entry(dest,data,assets)

def pack_zip(dest,output):
 output.parent.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for p in sorted(dest.rglob('*')):
   if p.is_file():
    info=zipfile.ZipInfo(dest.name+'/'+p.relative_to(dest).as_posix(),date_time=(2026,11,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,p.read_bytes(),compresslevel=6)
 checksum=digest(output)
 write(output.with_name(output.name+'.sha256'),checksum+'  '+output.name+'\n')
 return dict(path=str(output),bytes=output.stat().st_size,sha256=checksum)
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--download',action='store_true');parser.add_argument('--pack',choices=('small','grand','all','electric','gm','upgrades'),default='all');parser.add_argument('--cache',type=Path,default=ROOT/'output/piano-sources');parser.add_argument('--output',type=Path,default=ROOT/'synths');parser.add_argument('--zip',action='store_true');args=parser.parse_args()
 args.cache.mkdir(parents=True,exist_ok=True);args.output.mkdir(parents=True,exist_ok=True);result=dict(version=VERSION,archives=ARCHIVES)
 if args.pack in ('electric','gm','upgrades'):
  selected=('electric','gm') if args.pack=='upgrades' else (args.pack,);entries=[]
  for key in selected:entries.append((electric if key=='electric' else gm)(args.cache,args.output/('piano-electric' if key=='electric' else 'keyboard-gm'),args.download))
  result=dict(version=UPGRADE_VERSION,catalog_entries=entries)
  if args.zip:result['zips']=[pack_zip(args.output/e['id'],ROOT/'dist'/('Lingfeng-'+e['id']+'-'+UPGRADE_VERSION+'-Windows-x64.zip')) for e in entries]
  write_json(ROOT/'output/v53-sound-pack-sources.json',result);return
 if args.pack in ('small','all'):result['small_manifest']=small(args.cache,args.output/'piano-small',args.download)
 if args.pack in ('grand','all'):result['catalog_entry']=grand(args.cache,args.output/'piano-grand',args.download)
 if args.zip:result['zips']=[pack_zip(args.output/('piano-'+p),ROOT/'dist'/('Lingfeng-piano-'+p+'-'+VERSION+'-Windows-x64.zip')) for p in (('small','grand') if args.pack=='all' else (args.pack,))]
 write_json(ROOT/'output/piano-pack-sources.json',result)
if __name__=='__main__':main()


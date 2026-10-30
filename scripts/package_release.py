"""Prepare a portable release with licenses, source, examples and a checksum."""
from pathlib import Path
import argparse
import hashlib
import importlib.metadata as metadata
import json
import shutil
import sys
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from lingfeng import __version__
from scripts.release_policy import (APPROVED_PACKS,bundle_synths,source_files,verify_source_tree,
                                   prune_private_release_copies,verify_public_release_paths)
from lingfeng.audio.soundbanks import _validate

ROOT=Path(__file__).resolve().parent.parent
SYNTH_ROOT=ROOT/'synths'
if not SYNTH_ROOT.is_dir() and ROOT.name=='source':SYNTH_ROOT=ROOT.parent/'synths'
def copy_file(source,dest):
    dest.parent.mkdir(parents=True,exist_ok=True)
    # A running portable synth can hold an unchanged DLL open. Repacking the
    # same release need not overwrite identical bytes or disturb that process.
    if dest.is_file() and source.stat().st_size==dest.stat().st_size and source.read_bytes()==dest.read_bytes():return
    shutil.copy2(source,dest)


def package(destination=None):
    DEST=Path(destination).resolve() if destination is not None else ROOT/'dist'/__version__/'Lingfeng'
    if not DEST.is_relative_to((ROOT/'dist').resolve()):raise RuntimeError('Release destination must be inside dist.')
    if not (DEST/'Lingfeng.exe').exists():raise RuntimeError('Build Lingfeng.exe first.')
    prune_private_release_copies(ROOT,DEST)

    # The application uses QWidget/QPainter raster rendering, not OpenGL. PySide's
    # hook collects this optional Mesa/LLVM fallback anyway; do not redistribute it.
    optional_gl=DEST/'_internal'/'PySide6'/'opengl32sw.dll'
    if optional_gl.is_file():optional_gl.unlink()

    # Keep documentation and examples available without entering the source folder.
    for file in source_files(ROOT):
        relative=file.relative_to(ROOT)
        copy_file(file,DEST/'source'/relative)
        if relative.parts[0] in ('docs','examples') or str(relative) in ('README.md','CONTRIBUTING.md','CHANGELOG.md','LICENSE'):
            copy_file(file,DEST/relative)
    verify_source_tree(ROOT,DEST/'source')

    versions={}
    for name in ['PySide6_Essentials','shiboken6','pyinstaller','pychord','SoundCard','lameenc','numpy','cffi','pycparser']:
        dist=metadata.distribution(name);versions[name]=dist.version
        for file in dist.files or []:
            if any(word in str(file).lower() for word in ['license','copying','copyright']):
                src=Path(dist.locate_file(file))
                if src.is_file():
                    # Preserve nested license names without writing outside the license directory.
                    relative=Path(*[part for part in file.parts if part not in ('.','..')])
                    copy_file(src,DEST/'licenses'/name/relative)
    for path in source_files(ROOT):
        relative=path.relative_to(ROOT)
        if relative.parts[0]=='licenses':copy_file(path,DEST/relative)
    # Only reviewed source-tree packs participate; never absorb user-installed DLLs.
    pack_files=[SYNTH_ROOT/ident/'synth.json' for ident in APPROVED_PACKS]
    for manifest in pack_files:_validate(json.loads(manifest.read_text('utf-8')),manifest.parent.resolve())
    core_bytes=sum(p.stat().st_size for p in DEST.rglob('*') if p.is_file() and p.relative_to(DEST).parts[0]!='synths')
    synth_bytes=sum(p.stat().st_size for manifest in pack_files for p in manifest.parent.rglob('*') if p.is_file())
    bundled=list(APPROVED_PACKS) if bundle_synths(core_bytes,synth_bytes) else []
    for ident in bundled:
        for path in (SYNTH_ROOT/ident).rglob('*'):
            if path.is_file():copy_file(path,DEST/'synths'/ident/path.relative_to(SYNTH_ROOT/ident))
    (DEST/'synths').mkdir(exist_ok=True)
    copy_file(ROOT/'docs/SOUNDBANKS.md',DEST/'synths/README.md')
    if (DEST/'sounds').exists() or list((DEST/'_internal').rglob('sfizz.dll')):
        raise RuntimeError('Retired sampler assets in release')
    if (DEST/'development').exists() or (DEST/'source/development').exists():
        raise RuntimeError('Local-only candidates must not be shipped')
    (DEST/'build-info.json').write_text(json.dumps({'version':__version__,'python':sys.version,'dependencies':versions,'synthesis_abi':1,'synths_bundled':bool(bundled),'bundled_packs':bundled,'core_bytes':core_bytes,'synth_bytes':synth_bytes,'size_basis':'unpacked files, including sources and licenses'},indent=2),encoding='utf-8')
    (DEST/'Register-project-type.cmd').write_text('@echo off\r\nstart "" "%~dp0Lingfeng.exe" --associate\r\n',encoding='ascii')
    installation=('已附带全部轻量合成音源，解压即可使用。' if bundled else '音源总大小超过程序本体，另行提供音源 ZIP；将音源文件夹复制到 synths/ 后重新扫描。')
    (DEST/'Start-here.txt').write_text(f"""伶风 Lingfeng {__version__}

完整解压后运行 Lingfeng.exe，保留 _internal 和 synths。
{installation}
新增音源：复制完整文件夹到 synths，进入 设置 → 音源与音色 → 重新扫描并保存。
扫描结果和默认选择自动保存，下次启动直接读取；也可以添加其它扫描目录。
合成音源的编辑试听与离线 MP3 使用同一算法；导出保留商用版权提示。
Windows 实时录制会录入同一设备上的其它声音。
source/ 提供程序源码；每个音源包内含源码和许可。详见 docs/SOUNDBANKS.md。
分级中英文帮助见 docs/HELP.md。升级解压到新目录后会沿用用户偏好与和弦进行。
旧目录内自行添加的音源请复制到新版 synths/；额外扫描目录与音色默认值会迁移。

Extract the entire ZIP and keep _internal and synths. Lightweight synth packs
are included when their total unpacked size does not exceed the application.
Larger synth collections ship separately. Copy additional complete packs into
synths/, then use Settings > Sound sources and instruments > Rescan and save.
See docs/HELP.md for the categorized bilingual manual. User preferences,
progressions, extra scan folders and sound defaults carry over to new releases.
Copy custom packs from the old installation's synths/ into the new one.
""",encoding='utf-8')

    notice_root=DEST/'licenses'/'qt-6.9.2'
    notices=json.loads((notice_root/'manifest.json').read_text('utf-8'))
    for notice in notices:
        if hashlib.sha256((notice_root/notice['file']).read_bytes()).hexdigest()!=notice['sha256']:
            raise RuntimeError('Upstream license checksum mismatch: '+notice['file'])
    native=[]
    allowed_qt={'Qt6Core.dll','Qt6Gui.dll','Qt6Widgets.dll','Qt6Network.dll','Qt6Svg.dll'}
    for path in sorted((DEST/'_internal').rglob('*')):
        if path.suffix.lower() not in ('.dll','.pyd'):continue
        if path.name.startswith('Qt6') and path.name not in allowed_qt:raise RuntimeError('Review newly bundled Qt module license: '+path.name)
        if path.name=='opengl32sw.dll':raise RuntimeError('Unused software OpenGL library was bundled')
        native.append({'file':str(path.relative_to(DEST)).replace('\\','/'),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (DEST/'license-inventory.json').write_text(json.dumps({'version':__version__,'application_license':'MIT','qt_notice_files':len(notices),'qt_modules':sorted(allowed_qt),'software_opengl_bundled':False,'review':'docs/THIRD_PARTY.md','soundbanks':'docs/SOUNDBANKS.md','native_files':native},indent=2),'utf-8')
    out=ROOT/'dist'/f'Lingfeng-{__version__}-Windows-x64.zip'
    verify_public_release_paths(path.relative_to(DEST) for path in DEST.rglob('*') if path.is_file())
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
        for path in sorted(DEST.rglob('*')):
            relative=path.relative_to(DEST)
            # Repackaging an installation must not absorb user-installed engines.
            if relative.parts[0]=='synths' and relative!=Path('synths/README.md') and (len(relative.parts)<2 or relative.parts[1] not in bundled):continue
            if path.is_file():archive.write(path,Path('Lingfeng')/relative)
    with out.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
    out.with_suffix('.zip.sha256').write_text(f'{digest}  {out.name}\n',encoding='ascii')
    print(f'Release: {out}\nSize: {out.stat().st_size/1024/1024:.1f} MiB\nSHA256: {digest}')

    # Each ZIP extracts to one folder, ready to copy into the application's synths/.
    for pack in pack_files:
        data=json.loads(pack.read_text('utf-8'));folder=pack.parent
        if data['id'] in bundled:continue
        lib=folder/data['library']
        if hashlib.sha256(lib.read_bytes()).hexdigest()!=data['sha256']:raise RuntimeError('Synth checksum mismatch')
        archive=ROOT/'dist'/f"Lingfeng-{data['id']}-{__version__}-Windows-x64.zip"
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for file in sorted(folder.rglob('*')):
                if file.is_file():z.write(file,Path(folder.name)/file.relative_to(folder))
        digest=hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n','ascii')
        print(f'Synth pack: {archive} ({archive.stat().st_size/1024:.1f} KiB)')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',nargs='?',type=Path)
    args=parser.parse_args()
    package(args.destination)

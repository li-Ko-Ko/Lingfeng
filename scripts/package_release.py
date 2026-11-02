"""Prepare a local standalone folder; create an archive only with --archive."""
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
from scripts.release_policy import (APPROVED_PACKS,source_files,verify_source_tree,
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


def archive_paths():
    archive=ROOT/'dist'/f'Lingfeng-{__version__}-Windows-x64.zip'
    return archive,archive.with_suffix('.zip.sha256')


def require_new_archive():
    paths=archive_paths()
    for path in paths:
        if path.exists():raise FileExistsError('Existing archive or checksum is preserved: '+str(path))
    return paths


def create_archive(destination,bundled):
    """Create new files exclusively, preserving every existing archive."""
    out,sidecar=require_new_archive();created_archive=created_sidecar=False
    try:
        with zipfile.ZipFile(out,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            created_archive=True
            for path in sorted(destination.rglob('*')):
                relative=path.relative_to(destination)
                if relative.parts[0]=='synths' and relative!=Path('synths/README.md') and (len(relative.parts)<2 or relative.parts[1] not in bundled):continue
                if path.is_file():archive.write(path,Path('Lingfeng')/relative)
        with out.open('rb') as stream:digest=hashlib.file_digest(stream,'sha256').hexdigest()
        with sidecar.open('x',encoding='ascii') as stream:
            created_sidecar=True;stream.write(f'{digest}  {out.name}\n')
    except BaseException:
        if created_sidecar:sidecar.unlink()
        if created_archive:out.unlink()
        raise
    return out,digest


def package(destination=None,*,archive=False):
    DEST=Path(destination).resolve() if destination is not None else ROOT/'dist'/__version__/'Lingfeng'
    if not DEST.is_relative_to((ROOT/'dist').resolve()):raise RuntimeError('Release destination must be inside dist.')
    if not (DEST/'Lingfeng.exe').exists():raise RuntimeError('Build Lingfeng.exe first.')
    if archive:require_new_archive()
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
    bundled=list(APPROVED_PACKS)
    for ident in bundled:
        for path in (SYNTH_ROOT/ident).rglob('*'):
            if path.is_file():copy_file(path,DEST/'synths'/ident/path.relative_to(SYNTH_ROOT/ident))
    (DEST/'synths').mkdir(exist_ok=True)
    copy_file(ROOT/'docs/SOUNDBANKS.md',DEST/'synths/README.md')
    if (DEST/'sounds').exists() or list((DEST/'_internal').rglob('sfizz.dll')):
        raise RuntimeError('Retired sampler assets in release')
    if (DEST/'development').exists() or (DEST/'source/development').exists():
        raise RuntimeError('Local-only candidates must not be shipped')
    (DEST/'build-info.json').write_text(json.dumps({'version':__version__,'delivery':'archive' if archive else 'local-standalone','archive_requested':bool(archive),'python':sys.version,'dependencies':versions,'synthesis_abi':1,'synths_bundled':bool(bundled),'bundled_packs':bundled,'core_bytes':core_bytes,'synth_bytes':synth_bytes,'size_basis':'unpacked files, including sources and licenses'},indent=2),encoding='utf-8')
    (DEST/'Register-project-type.cmd').write_text('@echo off\r\nstart "" "%~dp0Lingfeng.exe" --associate\r\n',encoding='ascii')
    installation='已附带全部轻量合成音源，可直接运行。'
    (DEST/'Start-here.txt').write_text(f"""伶风 Lingfeng {__version__}

运行本文件夹中的 Lingfeng.exe，保留 _internal 和 synths。
{installation}
新增音源：复制完整文件夹到 synths，进入 设置 → 音源与音色 → 重新扫描并保存。
扫描结果和默认选择自动保存，下次启动直接读取；也可以添加其它扫描目录。
已附带免费小型钢琴与电钢琴。大钢琴：设置 → 音源与音色 → 下载／添加音源。
也可从本地完整音源 ZIP 添加，下载支持进度、取消和校验。
音源的编辑试听与离线 MP3 使用同一引擎；导出保留音源许可说明。
Windows 实时录制会录入同一设备上的其它声音。
source/ 提供程序源码；每个音源包内含源码和许可。详见 docs/SOUNDBANKS.md。
分级中英文帮助见 docs/HELP.md。升级解压到新目录后会沿用用户偏好与和弦进行。
旧目录内自行添加的音源请复制到新版 synths/；额外扫描目录与音色默认值会迁移。

Run Lingfeng.exe in this folder and keep _internal and synths. The approved
lightweight synth packs, source files and license notices are included.
The free small piano and electric pianos are included. Download the optional
grand or add a local pack ZIP in Settings > Sound sources and instruments >
Download / add sounds. Downloads show progress and verify checksums. You can
also copy complete folders into synths/ and use Rescan and save.
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
    verify_public_release_paths(path.relative_to(DEST) for path in DEST.rglob('*') if path.is_file())
    report=dict(folder=str(DEST),archive=None,sha256=None,bundled_packs=bundled)
    print(f'Standalone: {DEST}')
    if archive:
        out,digest=create_archive(DEST,bundled);report.update(archive=str(out),sha256=digest)
        print(f'Archive: {out}\nSize: {out.stat().st_size/1024/1024:.1f} MiB\nSHA256: {digest}')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',nargs='?',type=Path)
    parser.add_argument('--archive',action='store_true',help='Explicitly create a new ZIP and checksum; never overwrite existing files.')
    args=parser.parse_args()
    package(args.destination,archive=args.archive)

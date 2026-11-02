"""Cancellable, verified downloads and transactional installation of sound packs."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tarfile
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import zipfile

from lingfeng.platform.i18n import tr
from lingfeng.audio import soundbanks as banks

MAX_ARCHIVE = 1024 * 1024 * 1024
MAX_EXTRACTED = 2 * MAX_ARCHIVE
MAX_FILES = 20000


class InstallCancelled(Exception):
    pass


def _check_cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise InstallCancelled()


def _member_name(info):
    name = info.filename
    path = PurePosixPath(name)
    if (not name or '\\' in info.orig_filename or '\\' in name or ':' in name or '\x00' in name or
            path.is_absolute() or any(p in ('.', '..') or p.rstrip(' .') != p for p in path.parts) or
            stat.S_ISLNK(info.external_attr >> 16)):
        raise ValueError(tr('音源压缩包包含不安全的路径。'))
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *('COM'+str(i) for i in range(1, 10)),
                *('LPT'+str(i) for i in range(1, 10))}
    if any(p.split('.')[0].upper() in reserved for p in path.parts):
        raise ValueError(tr('音源压缩包包含不安全的路径。'))
    return path


def _extract(archive, folder, cancel=None, select=None):
    """Check the entire ZIP before extracting any selected regular files."""
    with zipfile.ZipFile(archive) as source:
        entries = source.infolist()
        if len(entries) > MAX_FILES or sum(i.file_size for i in entries) > MAX_EXTRACTED:
            raise ValueError(tr('音源压缩包超过允许的大小。'))
        names = set()
        for entry in entries:
            name = _member_name(entry)
            key = str(name).casefold()
            if key in names:
                raise ValueError(tr('音源压缩包包含重复的路径。'))
            names.add(key)
        for entry in entries:
            _check_cancel(cancel)
            name = _member_name(entry)
            if entry.is_dir():
                continue
            relative = select(name) if select else name
            if relative is None:
                continue
            destination = folder.joinpath(*relative.parts)
            if not destination.resolve().is_relative_to(folder.resolve()):
                raise ValueError(tr('音源压缩包包含不安全的路径。'))
            destination.parent.mkdir(parents=True, exist_ok=True)
            with source.open(entry) as reader, destination.open('wb') as writer:
                while chunk := reader.read(256 * 1024):
                    _check_cancel(cancel)
                    writer.write(chunk)


def _commit(folder, destination, cancel=None):
    _check_cancel(cancel)
    manifest = folder / 'synth.json'
    if not manifest.is_file() or manifest.stat().st_size > 256000:
        raise ValueError(tr('音源包缺少有效的 synth.json。'))
    data = banks._validate(json.loads(manifest.read_text('utf-8')), folder.resolve())
    hashes = folder / 'files.sha256.json'
    if hashes.is_file():
        if hashes.stat().st_size > 4 * 1024 * 1024:
            raise ValueError(tr('音源文件校验清单无效。'))
        expected = json.loads(hashes.read_text('utf-8'))
        if not isinstance(expected, dict) or len(expected) > MAX_FILES:
            raise ValueError(tr('音源文件校验清单无效。'))
        for relative, digest in expected.items():
            _check_cancel(cancel)
            path = banks._inside(folder.resolve(), relative)
            with path.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != digest:
                raise ValueError(tr('音源文件校验失败：{0}', relative))
    target = destination / data['id']
    if target.exists():
        raise ValueError(tr('音源“{0}”已经存在，请保留原音源或关闭程序后移走旧文件夹。', data['id']))
    _check_cancel(cancel)
    os.replace(folder, target)
    return target


def install_archive(archive, destination=None, cancel=None, progress=None):
    """Install a local, complete Lingfeng sound-pack ZIP without overwriting packs."""
    destination = Path(destination or banks.default_root()).resolve()
    archive = Path(archive)
    if archive.stat().st_size > MAX_ARCHIVE:
        raise ValueError(tr('音源压缩包超过允许的大小。'))
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.install-', dir=destination) as temporary:
        stage = Path(temporary) / 'contents'
        stage.mkdir()
        if progress:
            progress(0, 0)
        _extract(archive, stage, cancel)
        manifests = list(stage.glob('synth.json')) + list(stage.glob('*/synth.json'))
        if len(manifests) != 1:
            raise ValueError(tr('请选择只包含一个完整伶风音源包的 ZIP。'))
        return _commit(manifests[0].parent, destination, cancel)


def _download(entry, filename, cancel=None, progress=None):
    _check_cancel(cancel)
    url = entry['url']
    if urlsplit(url).scheme != 'https':
        raise ValueError(tr('音源下载必须使用 HTTPS。'))
    digest = hashlib.sha256()
    expected = entry['archive_bytes']
    if not 0 < expected <= MAX_ARCHIVE:
        raise ValueError(tr('音源压缩包超过允许的大小。'))
    request = Request(url, headers={'User-Agent': 'Lingfeng sound-pack downloader'})
    with urlopen(request, timeout=20) as source, filename.open('wb') as target:
        if urlsplit(source.geturl()).scheme != 'https':
            raise ValueError(tr('音源下载必须使用 HTTPS。'))
        length = source.headers.get('Content-Length')
        if length is not None and int(length) > MAX_ARCHIVE:
            raise ValueError(tr('音源压缩包超过允许的大小。'))
        count = 0
        while chunk := source.read(256 * 1024):
            _check_cancel(cancel)
            count += len(chunk)
            if count > expected:
                raise ValueError(tr('下载文件的大小与音源目录不一致。'))
            target.write(chunk)
            digest.update(chunk)
            if progress:
                progress(count, expected)
    _check_cancel(cancel)
    if count != expected or digest.hexdigest() != entry['sha256']:
        raise ValueError(tr('音源下载校验失败，请重新下载。'))


def install_download(entry, destination=None, cancel=None, progress=None):
    """Build an optional SFZ pack from a pinned, hash-verified upstream archive."""
    if entry.get('assets'):
        return install_multi_download(entry,destination,cancel,progress)
    destination = Path(destination or banks.default_root()).resolve()
    if (destination / entry['id']).exists():
        raise ValueError(tr('音源“{0}”已经存在，请保留原音源或关闭程序后移走旧文件夹。', entry['id']))
    runtime = banks.pack('synth:piano-small')
    runtime_root = Path(runtime['path'])
    library = banks._inside(runtime_root, runtime['library'])
    manifest = copy.deepcopy(entry['manifest'])
    if (runtime.get('engine') != 'sfz' or
            hashlib.sha256(library.read_bytes()).hexdigest() != manifest['sha256']):
        raise ValueError(tr('请先安装本版本附带的小型钢琴音源，再添加大钢琴音源。'))
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.download-', dir=destination) as temporary:
        temporary = Path(temporary)
        archive = temporary / 'source.zip'
        _download(entry, archive, cancel, progress)
        if progress:
            progress(0, 0)
        folder = temporary / 'pack'
        folder.mkdir()
        prefix = entry['archive_root']

        def select(path):
            if not path.parts or path.parts[0] != prefix:
                return None
            relative = PurePosixPath(*path.parts[1:])
            if relative.name in ('README.md', 'README.orig.txt', 'README.cyamauch.txt') and len(relative.parts) == 1:
                return relative
            if str(relative) == 'AccurateSalamanderGrand-Z.sfz':
                return relative
            if len(relative.parts) == 2 and relative.parts[0] == 'flac' and relative.suffix.lower() == '.flac':
                return relative
            return None

        _extract(archive, folder, cancel, select)
        mapping = folder / 'AccurateSalamanderGrand-Z.sfz'
        mapping.write_text('// Lingfeng: lowest velocity region extended from MIDI velocity2 to1.\n' +
                           re.sub(r'\blovel=2\b', 'lovel=1', mapping.read_text('utf-8')),
                           encoding='utf-8', newline='\n')
        _check_cancel(cancel)
        shutil.copy2(library, folder / manifest['library'])
        if (runtime_root / 'runtime').is_dir():
            shutil.copytree(runtime_root / 'runtime', folder / 'runtime')
        for name, content in entry.get('text_files', {}).items():
            path = folder / name
            if not path.resolve().is_relative_to(folder.resolve()):
                raise ValueError('Invalid catalog notice path')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8', newline='\n')
        (folder / 'synth.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n', encoding='utf-8', newline='\n')
        return _commit(folder, destination, cancel)


def _mapped_asset(archive,folder,asset,cancel):
    """Extract only catalog-reviewed regular files from a verified ZIP/TAR."""
    mapping=asset.get('file_map',{})
    destinations={}
    for name,target in mapping.items():
        checked=_member_name(zipfile.ZipInfo(target))
        key=str(checked).casefold()
        if key in destinations:raise ValueError(tr('音源压缩包包含重复的路径。'))
        destinations[key]=name
    seen=set()

    def copy_file(name,reader):
        target=mapping[name]
        checked=_member_name(zipfile.ZipInfo(target))
        path=folder.joinpath(*checked.parts)
        if not path.resolve().is_relative_to(folder.resolve()):
            raise ValueError(tr('音源压缩包包含不安全的路径。'))
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('wb') as writer:
            while chunk:=reader.read(256*1024):
                _check_cancel(cancel);writer.write(chunk)
        seen.add(name)

    if asset['format']=='file':
        target=_member_name(zipfile.ZipInfo(asset['target']))
        path=folder.joinpath(*target.parts);path.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(archive,path);return
    if asset['format']=='zip':
        with zipfile.ZipFile(archive) as source:
            entries=source.infolist()
            if len(entries)>MAX_FILES or sum(i.file_size for i in entries)>MAX_EXTRACTED:
                raise ValueError(tr('音源压缩包超过允许的大小。'))
            for item in entries:
                _check_cancel(cancel);_member_name(item)
                if item.filename not in mapping:continue
                if item.is_dir() or item.filename in seen:raise ValueError(tr('音源压缩包包含重复的路径。'))
                with source.open(item) as reader:copy_file(item.filename,reader)
    elif asset['format']=='tar':
        with tarfile.open(archive,'r:*') as source:
            entries=source.getmembers()
            if len(entries)>MAX_FILES or sum(i.size for i in entries)>MAX_EXTRACTED:
                raise ValueError(tr('音源压缩包超过允许的大小。'))
            for item in entries:
                _check_cancel(cancel)
                if item.name not in mapping:continue
                _member_name(zipfile.ZipInfo(item.name))
                if not item.isfile() or item.name in seen:
                    raise ValueError(tr('音源压缩包包含不安全的路径。'))
                with source.extractfile(item) as reader:copy_file(item.name,reader)
    else:raise ValueError('Unsupported catalog archive format')
    if seen!=set(mapping):raise ValueError(tr('下载的音源缺少目录中指定的文件。'))


def install_multi_download(entry,destination=None,cancel=None,progress=None):
    destination=Path(destination or banks.default_root()).resolve()
    if (destination/entry['id']).exists():
        raise ValueError(tr('音源“{0}”已经存在，请保留原音源或关闭程序后移走旧文件夹。',entry['id']))
    manifest=copy.deepcopy(entry['manifest']);runtime=None
    if entry.get('runtime_id'):
        runtime=banks.pack('synth:'+entry['runtime_id'])
        library=banks._inside(Path(runtime['path']),runtime['library'])
        if hashlib.sha256(library.read_bytes()).hexdigest()!=manifest['sha256']:
            raise ValueError(tr('请先安装本版本附带的小型钢琴音源，再添加大钢琴音源。'))
    total=sum(asset['archive_bytes'] for asset in entry['assets'])
    if total>MAX_ARCHIVE:raise ValueError(tr('音源压缩包超过允许的大小。'))
    destination.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.download-',dir=destination) as temporary:
        temporary=Path(temporary);folder=temporary/'pack';folder.mkdir();offset=0
        for index,asset in enumerate(entry['assets']):
            archive=temporary/(str(index)+'.download')
            def report(done,size):
                if progress:progress(offset+done,total)
            _download(asset,archive,cancel,report)
            _mapped_asset(archive,folder,asset,cancel);offset+=asset['archive_bytes']
        if progress:progress(0,0)
        if runtime:
            library=banks._inside(Path(runtime['path']),runtime['library'])
            target=folder/manifest['library'];target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(library,target)
            if (Path(runtime['path'])/'runtime').is_dir():
                shutil.copytree(Path(runtime['path'])/'runtime',folder/'runtime',dirs_exist_ok=True)
        for name,content in entry.get('text_files',{}).items():
            checked=_member_name(zipfile.ZipInfo(name));path=folder.joinpath(*checked.parts)
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(content,encoding='utf-8',newline='\n')
        (folder/'synth.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
        return _commit(folder,destination,cancel)

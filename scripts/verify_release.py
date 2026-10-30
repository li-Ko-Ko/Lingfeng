"""Check a packaged release against its archive, source and approved synths."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from popscore import __version__
from scripts.release_policy import APPROVED_PACKS


def verify():
    folder=ROOT/'dist'/__version__/'Lingfeng'
    archive=ROOT/'dist'/f'Lingfeng-{__version__}-Windows-x64.zip'
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    assert archive.with_suffix('.zip.sha256').read_text('ascii').split()[0]==digest
    info=json.loads((folder/'build-info.json').read_text('utf-8'))
    assert info['version']==__version__
    assert (folder/'Lingfeng.exe').is_file() and (folder/'docs/HELP.md').is_file()
    source_files=[]
    for file in (folder/'source').rglob('*'):
        if not file.is_file():continue
        relative=file.relative_to(folder/'source')
        current=ROOT/relative
        assert current.is_file(),str(relative)
        assert current.read_bytes()==file.read_bytes(),'Source mismatch: '+str(relative)
        source_files.append(relative.as_posix())
    for file in (ROOT/'popscore').glob('*.py'):
        assert file.relative_to(ROOT).as_posix() in source_files
    packs=[]
    for ident in info['bundled_packs']:
        assert ident in APPROVED_PACKS
        data=json.loads((folder/'synths'/ident/'synth.json').read_text('utf-8'))
        actual=hashlib.sha256((folder/'synths'/ident/data['library']).read_bytes()).hexdigest()
        assert actual==data['sha256']
        packs.append(dict(id=ident,presets=len(data['presets']),sha256=actual))
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        members=z.namelist()
        for member in members:
            path=Path(member)
            assert path.parts[0]=='Lingfeng' and '..' not in path.parts
            assert not set(path.parts)&{'development','__pycache__','.git','.venv-build','.build-deps'}
            assert path.name not in ('preferences.json','user-settings.json')
            relative=Path(*path.parts[1:])
            assert (folder/relative).read_bytes()==z.read(member),'Archive mismatch: '+member
        assert len(members)==sum(f.is_file() for f in folder.rglob('*'))
    return dict(status='passed',version=__version__,archive=str(archive),bytes=archive.stat().st_size,
                sha256=digest,archive_files=len(members),source_files=len(source_files),
                bundled_packs=packs,checks=['ZIP CRC','SHA-256 sidecar','archive file contents',
                'release source matches workspace','all application modules included',
                'synth binary checksums','excluded local development and user data','categorized help included'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();report=verify()
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

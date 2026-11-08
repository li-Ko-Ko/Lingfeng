"""Check a standalone folder; inspect its ZIP only with --archive."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from lingfeng import __version__
from lingfeng.audio.calibration import CALIBRATION_FILE
from lingfeng.audio.soundbanks import _load_calibration
from scripts.release_policy import APPROVED_PACKS,verify_source_tree,verify_public_release_paths


def verify_runtime_resources(root,folder):
    """External PyInstaller data must match the source used for this release."""
    root,folder=Path(root),Path(folder)
    for relative in ('lingfeng/platform/en.json','assets/lingfeng.ico'):
        target=folder/'_internal'/relative
        assert target.is_file(),'Missing frozen resource: '+relative
        assert target.read_bytes()==(root/relative).read_bytes(),'Frozen resource mismatch: '+relative
    assert not (folder/'_internal/popscore').exists(),'Retired runtime package data was bundled'


def verify_archive(folder,archive,bundled):
    """Validate an explicitly requested archive without changing either file."""
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    assert archive.with_suffix('.zip.sha256').read_text('ascii').split()[0]==digest
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        members=z.namelist()
        verify_public_release_paths(Path(*Path(member).parts[1:]) for member in members)
        for member in members:
            path=Path(member)
            assert path.parts[0]=='Lingfeng' and '..' not in path.parts
            assert not set(path.parts)&{'development','__pycache__','.git','.venv-build','.build-deps'}
            assert path.name not in ('preferences.json','user-settings.json')
            relative=Path(*path.parts[1:])
            assert (folder/relative).read_bytes()==z.read(member),'Archive mismatch: '+member
        assert len(members)==len(set(members)),'Duplicate ZIP members'
        expected={str(Path('Lingfeng')/file.relative_to(folder)).replace('\\','/')
                  for file in folder.rglob('*') if file.is_file() and
                  (file.relative_to(folder).parts[0]!='synths' or
                   file.relative_to(folder)==Path('synths/README.md') or
                   file.relative_to(folder).parts[1] in bundled)}
        assert set(members)==expected,'Archive inventory differs from reviewed release payload'
    return dict(archive=str(archive),bytes=archive.stat().st_size,sha256=digest,archive_files=len(members))


def verify(destination=None,*,archive=False):
    folder=Path(destination).resolve() if destination is not None else ROOT/'dist'/__version__/'Lingfeng'
    info=json.loads((folder/'build-info.json').read_text('utf-8'))
    assert info['version']==__version__
    assert sorted(info['bundled_packs'])==sorted(APPROVED_PACKS),'Standalone must include the default sound packs'
    assert (folder/'Lingfeng.exe').is_file() and (folder/'docs/HELP.md').is_file()
    verify_runtime_resources(ROOT,folder)
    verify_public_release_paths(path.relative_to(folder) for path in folder.rglob('*') if path.is_file())
    source_files=verify_source_tree(ROOT,folder/'source')
    packs=[]
    for ident in info['bundled_packs']:
        assert ident in APPROVED_PACKS
        data=json.loads((folder/'synths'/ident/'synth.json').read_text('utf-8'))
        actual=hashlib.sha256((folder/'synths'/ident/data['library']).read_bytes()).hexdigest()
        assert actual==data['sha256']
        checksums=folder/'synths'/ident/'files.sha256.json';asset_count=0
        if checksums.is_file():
            from lingfeng.audio.soundbanks import _inside,_validate
            pack_root=(folder/'synths'/ident).resolve()
            _validate(data,pack_root)
            for relative,expected_hash in json.loads(checksums.read_text('utf-8')).items():
                asset=_inside(pack_root,relative)
                with asset.open('rb') as stream:asset_hash=hashlib.file_digest(stream,'sha256').hexdigest()
                assert asset_hash==expected_hash,'Sound asset checksum mismatch: '+relative
                asset_count+=1
        pack_root=(folder/'synths'/ident).resolve()
        assert (pack_root/CALIBRATION_FILE).is_file(),'Bundled preset calibration is missing: '+ident
        gains=_load_calibration(pack_root,data)
        packs.append(dict(id=ident,presets=len(data['presets']),sha256=actual,verified_assets=asset_count,calibrated_presets=len(gains)))
    report=dict(status='passed',version=__version__,folder=str(folder),archive=None,
                bytes=sum(path.stat().st_size for path in folder.rglob('*') if path.is_file()),
                sha256=None,archive_files=0,source_files=len(source_files),
                bundled_packs=packs,checks=['standalone source matches workspace','all application modules included',
                'frozen catalog and icon match source','synth binary and sampled-asset checksums',
                'Greg, STK, GeneralUser GS and PFSynth included in the bundled inventory','preset loudness calibration files',
                'excluded local development and user data','excluded local design and maintenance records','categorized help included'])
    if archive:
        report.update(verify_archive(folder,ROOT/'dist'/f'Lingfeng-{__version__}-Windows-x64.zip',info['bundled_packs']))
        report['checks']+=['ZIP CRC','SHA-256 sidecar','archive file contents']
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination',nargs='?',type=Path)
    parser.add_argument('--archive',action='store_true',help='Also verify the existing version ZIP and checksum.')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();report=verify(args.destination,archive=args.archive)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

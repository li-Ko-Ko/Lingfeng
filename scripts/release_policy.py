"""Public rebuild inputs shared by repository publication and packaging.

Runtime code, build inputs, maintained regressions, public help and third-party
notices are public. Local design notes and maintenance records stay local.
"""
from pathlib import Path
import shutil

APPROVED_PACKS=('stk-essentials','stk-colors','stk-acoustic')
SOURCE_ROOT_FILES=('README.md','CONTRIBUTING.md','CHANGELOG.md','LICENSE',
                   'main.py','requirements.txt','requirements-build.txt','build.ps1',
                   '.gitignore','.gitattributes')
SOURCE_TREES={
    'lingfeng':{'.py','.json'}, 'scripts':{'.py'}, 'tests':{'.py'},
    'docs':{'.md','.json','.png'}, 'assets':{'.ico','.svg','.png'},
    'native':{'.cpp','.h'}, 'examples':{'.lfs','.mid'}, 'licenses':None,
}
PUBLIC_DOCS=(
    'docs/FORMAT.md','docs/HELP.md','docs/PROGRESSIONS.md',
    'docs/SOUNDBANKS.md','docs/THIRD_PARTY.md',
)
PUBLIC_SCREENSHOTS=(
    'docs/screenshots/compose.png','docs/screenshots/spatial-score.png',
    'docs/screenshots/lyrics-rap.png','docs/screenshots/progression-library.png',
)
PUBLIC_SCRIPTS=(
    'scripts/audit_text.py','scripts/build_synth_packs.py','scripts/collect_qt_notices.py',
    'scripts/export_help.py','scripts/package_release.py',
    'scripts/release_policy.py','scripts/run_regression.py','scripts/verify_audio.py',
    'scripts/verify_release.py',
)
PRIVATE_SOURCE_FILES=(
    'docs/ARCHITECTURE.md','docs/INTERFACES.md','docs/MAINTENANCE.md',
    'docs/BASELINE_VALIDATION.md','docs/module_inventory.json',
    'scripts/audit_architecture.py','tests/test_architecture.py',
    'docs/LICENSE_AUDIT.md','docs/REFERENCES.md','launch.cmd','start.ps1',
    'scripts/make_icon.py','examples/lingfeng-rap.mid',
    'licenses/qt-6.9.2/qtbase/src/widgets/doc/images/licensewizard-flow.png',
)
PRIVATE_SOURCE_TREES=('development','tests/legacy')
SOURCE_REQUIRED_FILES=(
    'lingfeng/__init__.py','lingfeng/__main__.py','lingfeng/cli.py','lingfeng/platform/en.json',
    *PUBLIC_SCRIPTS,'tests/__init__.py','tests/test_music.py','tests/test_release_tools.py',
    *PUBLIC_DOCS,*PUBLIC_SCREENSHOTS,
    'assets/lingfeng.ico','assets/check.svg','native/stk_pack.cpp','examples/demo.lfs','examples/demo.mid',
    'licenses/audio-source/README.md','licenses/qt-6.9.2/manifest.json',
)


def is_private_source_path(relative):
    """Recognize local-only records even inside a stale distribution copy."""
    path=Path(relative)
    if path.as_posix() in PRIVATE_SOURCE_FILES:return True
    return any(path==Path(folder) or Path(folder) in path.parents for folder in PRIVATE_SOURCE_TREES)


def _included(relative,suffixes):
    parts=relative.parts;folder=parts[0]
    if '__pycache__' in parts or any(part.startswith('.') for part in parts):return False
    if is_private_source_path(relative):return False
    if folder=='docs':return relative.as_posix() in (*PUBLIC_DOCS,*PUBLIC_SCREENSHOTS)
    if folder=='scripts':return relative.as_posix() in PUBLIC_SCRIPTS
    if folder=='tests':return len(parts)==2 and (relative.name in ('__init__.py','music_reference.py') or relative.name.startswith('test_') and relative.suffix=='.py')
    if folder=='assets':return relative.as_posix() in ('assets/lingfeng.ico','assets/check.svg')
    if folder=='native':return relative.as_posix()=='native/stk_pack.cpp'
    if folder=='lingfeng' and relative.suffix=='.json':return relative.as_posix()=='lingfeng/platform/en.json'
    if folder=='licenses':
        if len(parts)==2:return relative.name in ('GPL-3.0-only.txt','LGPL-3.0-only.txt','PYTHON.txt','Qt-GPL-exception-1.0.txt','mpdecimal-COPYRIGHT.txt')
        return parts[1] in ('audio-source','qt-6.9.2','runtime')
    return suffixes is None or relative.suffix.lower() in suffixes


def source_files(root):
    """Return all reviewed rebuild inputs, including nested packages/resources."""
    root=Path(root)
    missing=[name for name in (*SOURCE_ROOT_FILES,*SOURCE_REQUIRED_FILES) if not (root/name).is_file()]
    if missing:raise RuntimeError('Required source inputs missing: '+', '.join(missing))
    result=[root/name for name in SOURCE_ROOT_FILES]
    for folder,suffixes in SOURCE_TREES.items():
        tree=[]
        for path in (root/folder).rglob('*'):
            if not path.is_file():continue
            if _included(path.relative_to(root),suffixes):tree.append(path)
        if not tree:raise RuntimeError('Required source tree is empty: '+folder)
        result.extend(tree)
    return sorted(result,key=lambda path:path.relative_to(root).as_posix())


def repository_files(root):
    """Exact public repository candidates: rebuild inputs plus approved packs."""
    root=Path(root)
    files=source_files(root)
    for ident in APPROVED_PACKS:
        folder=root/'synths'/ident
        if not (folder/'synth.json').is_file():raise RuntimeError('Approved synth manifest missing: '+ident)
        files.extend(path for path in folder.rglob('*') if path.is_file() and
                     '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyo') and
                     not any(part.startswith('.') for part in path.relative_to(folder).parts))
    return sorted(files,key=lambda path:path.relative_to(root).as_posix())


def verify_repository_paths(root,paths):
    """Reject any missing or extra GitHub tree member before publication."""
    expected={path.relative_to(root).as_posix() for path in repository_files(root)}
    actual={Path(path).as_posix() for path in paths}
    if actual!=expected:
        raise RuntimeError(f'Public repository inventory mismatch: missing={sorted(expected-actual)}, extra={sorted(actual-expected)}')
    return sorted(actual)


def prune_private_release_copies(root,destination):
    """Remove only known private distribution copies, keeping local originals."""
    root,destination=Path(root).resolve(),Path(destination).resolve()
    dist=(root/'dist').resolve()
    if not dist.is_relative_to(root) or destination==dist or not destination.is_relative_to(dist):
        raise RuntimeError('Private-copy cleanup destination must be a release folder inside dist')
    candidates=[destination/'source'/name for name in PRIVATE_SOURCE_FILES]
    candidates.extend(destination/name for name in PRIVATE_SOURCE_FILES)
    candidates.extend(destination/base/name for base in ('','source') for name in PRIVATE_SOURCE_TREES)
    removed=[]
    # Validate every final target before deleting any of them.
    for target in candidates:
        if not target.resolve().is_relative_to(destination):raise RuntimeError('Private-copy target escaped release: '+str(target))
    for target in candidates:
        if not target.exists():continue
        if target.is_dir():shutil.rmtree(target)
        else:target.unlink()
        removed.append(target.relative_to(destination).as_posix())
    return removed


def verify_public_release_paths(paths):
    """Reject local records in top-level documentation or bundled sources."""
    for item in paths:
        path=Path(item)
        if path.parts and path.parts[0]=='source':path=Path(*path.parts[1:])
        # PyInstaller data collection must not hide local notes below _internal.
        if path.parts and path.parts[0]=='_internal':path=Path(*path.parts[1:])
        if is_private_source_path(path):raise RuntimeError('Local-only content in release: '+str(item))
        if path.parts and path.parts[0]=='docs' and path.as_posix() not in (*PUBLIC_DOCS,*PUBLIC_SCREENSHOTS):
            raise RuntimeError('Unreviewed documentation in release: '+str(item))


def verify_source_tree(root,packaged):
    """Reject missing, stale or changed rebuild inputs, not just changed Python."""
    root,packaged=Path(root),Path(packaged)
    expected={path.relative_to(root).as_posix():path for path in source_files(root)}
    actual={path.relative_to(packaged).as_posix():path for path in packaged.rglob('*') if path.is_file()}
    missing=expected.keys()-actual.keys();extra=actual.keys()-expected.keys()
    if missing or extra:
        raise RuntimeError(f'Source inventory mismatch: missing={sorted(missing)}, extra={sorted(extra)}')
    for name,path in expected.items():
        if path.read_bytes()!=actual[name].read_bytes():raise RuntimeError('Source mismatch: '+name)
    return sorted(expected)

def bundle_synths(core_bytes,synth_bytes):
    """Compare unpacked bytes on both sides, including source and licenses."""
    return core_bytes>0 and synth_bytes<=core_bytes

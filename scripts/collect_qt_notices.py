"""Collect verbatim upstream license files and attribution metadata at pinned tags.

Run explicitly when updating dependencies; the release packager only copies the
checked-in results. This is a notice superset, not a claim that all Qt modules ship.
"""
from pathlib import Path,PurePosixPath
from concurrent.futures import ThreadPoolExecutor
import urllib.request,json,hashlib,time

ROOT=Path(__file__).resolve().parent.parent
DEST=ROOT/'licenses'/'qt-6.9.2'

def fetch(url):
    for attempt in range(3):
        try:return urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Lingfeng-license-audit'}),timeout=30).read()
        except Exception:
            if attempt==2:raise
            time.sleep(.5)

manifest=[]
for repo in ('qtbase','qtsvg','qtimageformats','pyside-setup'):
    owner='pyside' if repo=='pyside-setup' else 'qt'
    tag='v6.9.2';tree=json.loads(fetch(f'https://api.github.com/repos/{owner}/{repo}/git/trees/{tag}?recursive=1'))
    if tree.get('truncated'):raise RuntimeError('Incomplete upstream tree')
    paths={f['path'] for f in tree['tree'] if f['type']=='blob'}
    chosen={p for p in paths if p.startswith('LICENSES/') or (p.startswith('src/') or p.startswith('sources/')) and (PurePosixPath(p).name.lower().startswith(('license','copying','copyright')) or p.endswith('qt_attribution.json'))}
    fetched={}
    def get(path):
        url=f'https://raw.githubusercontent.com/{owner}/{repo}/{tag}/{path}'
        target=DEST/repo/path
        content=target.read_bytes() if target.exists() else fetch(url)
        return path,content,url
    def save(items):
        for path,content,url in items:
            target=DEST/repo/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content);fetched[path]=content
            manifest.append(dict(file=str(target.relative_to(DEST)).replace('\\','/'),source=url,sha256=hashlib.sha256(content).hexdigest()))
    with ThreadPoolExecutor(max_workers=8) as pool:save(pool.map(get,sorted(chosen)))
    # Some metadata references README or source headers containing the notice.
    extras=set()
    for path,content in fetched.items():
        if not path.endswith('qt_attribution.json'):continue
        data=json.loads(content,strict=False);data=data if isinstance(data,list) else [data]
        for item in data:
            refs=item.get('LicenseFile',[]);refs=refs if isinstance(refs,list) else [refs]
            for ref in refs:
                candidate=str(PurePosixPath(path).parent/ref)
                if candidate in paths and candidate not in fetched:extras.add(candidate)
    with ThreadPoolExecutor(max_workers=8) as pool:save(pool.map(get,sorted(extras)))
    print(repo,len(fetched),flush=True)
(DEST/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
print('Collected',len(manifest),'upstream files')

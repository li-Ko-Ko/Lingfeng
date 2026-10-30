"""Run each unittest module in a fresh Qt process and keep a release report."""
import json,os,re,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from popscore import __version__

os.chdir(ROOT)
version_parts=__version__.split('.')
tag='v'+version_parts[1]+(version_parts[2] if version_parts[2]!='0' else '')
out=ROOT/'output'/f'{tag}-regression';out.mkdir(parents=True,exist_ok=True)
(ROOT/'tmp').mkdir(exist_ok=True)
env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8',TEMP=str(ROOT/'tmp'),TMP=str(ROOT/'tmp'),LINGFENG_USER_DATA=str(ROOT/'tmp/regression-user-data'),LINGFENG_SYNTH_CACHE=str(ROOT/'tmp/regression-synth-index.json'))
results=[]
for path in sorted((ROOT/'tests').glob('test_*.py')):
    module='tests.'+path.stem;start=time.perf_counter()
    with (out/(path.stem+'.log')).open('w',encoding='utf-8') as log:
        try:code=subprocess.run([sys.executable,'-m','unittest',module,'-v'],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=360).returncode
        except subprocess.TimeoutExpired:code=-1
    content=(out/(path.stem+'.log')).read_text('utf-8');counts=re.findall(r'Ran (\d+) tests?',content)
    result=dict(module=module,count=int(counts[-1]) if counts else 0,exit_code=code,seconds=round(time.perf_counter()-start,2))
    results.append(result);print(result,flush=True)
    (ROOT/'output'/f'{tag}-tests.json').write_text(json.dumps(dict(version=__version__,status='passed' if all(r['exit_code']==0 for r in results) else 'failed',count=sum(r['count'] for r in results),modules=results),indent=2),'utf-8')
sys.exit(0 if all(r['exit_code']==0 for r in results) else 1)

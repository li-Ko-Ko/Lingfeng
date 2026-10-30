"""Run current unittest modules in isolated Qt processes and keep a report.

With no arguments, run every tests/test_*.py module. Pass module names to run
a focused selection; archived tests/legacy scripts are intentionally excluded.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from lingfeng import __version__


def version_tag(version):
    """Keep existing v502 report names while accepting the 0.51 version."""
    parts=version.split('.')
    if parts[0]=='0':parts=parts[1:]
    if len(parts)>1 and parts[-1]=='0':parts=parts[:-1]
    return 'v'+''.join(parts)


def run(modules=(),timeout=360):
    available={path.stem:path for path in sorted((ROOT/'tests').glob('test_*.py'))}
    selected=list(dict.fromkeys(name.removeprefix('tests.') for name in modules)) or list(available)
    unknown=set(selected)-available.keys()
    if unknown:raise ValueError('Unknown regression modules: '+', '.join(sorted(unknown)))
    if not selected:raise RuntimeError('No regression modules found')
    tag=version_tag(__version__)
    out=ROOT/'output'/f'{tag}-regression';out.mkdir(parents=True,exist_ok=True)
    temporary=ROOT/'tmp';temporary.mkdir(exist_ok=True)
    results=[]
    for name in selected:
        module='tests.'+name;start=time.perf_counter()
        with tempfile.TemporaryDirectory(prefix=name+'-',dir=temporary) as folder:
            isolated=Path(folder)
            env=dict(os.environ,QT_QPA_PLATFORM='offscreen',PYTHONIOENCODING='utf-8',
                     TEMP=folder,TMP=folder,LINGFENG_USER_DATA=str(isolated/'user-data'),
                     LINGFENG_SYNTH_CACHE=str(isolated/'synth-index'/'current.json'))
            log_path=out/(name+'.log')
            with log_path.open('w',encoding='utf-8') as log:
                try:
                    code=subprocess.run([sys.executable,'-m','unittest',module,'-v'],
                        cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout).returncode
                except subprocess.TimeoutExpired:
                    log.write(f'\nRegression module exceeded {timeout} seconds.\n');code=-1
            content=log_path.read_text('utf-8');counts=re.findall(r'Ran (\d+) tests?',content)
            count=int(counts[-1]) if counts else 0
            if code==0 and count==0:code=1
        result=dict(module=module,count=count,exit_code=code,seconds=round(time.perf_counter()-start,2))
        results.append(result);print(result,flush=True)
        status=('passed' if all(row['exit_code']==0 for row in results) else 'failed') if len(results)==len(selected) else 'running'
        report=dict(version=__version__,status=status,count=sum(row['count'] for row in results),
                    completed_modules=len(results),total_modules=len(selected),modules=results)
        (ROOT/'output'/f'{tag}-tests.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    return 0 if all(row['exit_code']==0 for row in results) else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('modules',nargs='*',help='Current module names, e.g. test_music or tests.test_music')
    parser.add_argument('--timeout',type=float,default=360,help='Timeout per module in seconds')
    args=parser.parse_args()
    if args.timeout<=0:parser.error('--timeout must be positive')
    try:raise SystemExit(run(args.modules,args.timeout))
    except ValueError as exc:parser.error(str(exc))

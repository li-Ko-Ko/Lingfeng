"""Audit extractable application text; report dynamic calls for manual review.

This checks catalogue completeness and formatting, not rendered layout or the
meaning of translations. Help and instrument names use explicit bilingual data.
Run: python scripts/audit_text.py --output output/v51-text-audit.json
"""
import argparse
import ast
from collections import Counter
import json
from pathlib import Path
import re
from string import Formatter

ROOT=Path(__file__).resolve().parent.parent
HAN=re.compile('[\u3400-\u9fff]')
INTENTIONAL_EN_HAN={'简体中文','语言 / Language'}


def literal_choices(node):
    if isinstance(node,ast.Constant) and isinstance(node.value,str):return [node.value]
    if isinstance(node,ast.IfExp):return literal_choices(node.body)+literal_choices(node.orelse)
    return []


def fields(text):
    return sorted((name,spec,conversion) for _,name,spec,conversion in Formatter().parse(text) if name is not None)


def audit(root=ROOT):
    root=Path(root)
    path=root/'lingfeng/platform/en.json'
    pairs=json.loads(path.read_text('utf-8'),object_pairs_hook=lambda items:items)
    catalog=dict(pairs);duplicates=[key for key,count in Counter(key for key,_ in pairs).items() if count>1]
    required={};dynamic=[];calls=0;exceptions=0;files=[root/'main.py',*sorted((root/'lingfeng').rglob('*.py'))]
    for file in files:
        tree=ast.parse(file.read_text('utf-8'),filename=str(file));relative=file.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node,ast.Call) or not node.args:continue
            name=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ''
            if name=='tr':
                calls+=1;choices=literal_choices(node.args[0])
                if not choices:dynamic.append({'file':relative,'line':node.lineno,'expression':ast.unparse(node.args[0])})
            elif name in ('ValueError','RuntimeError','OSError'):
                exceptions+=1;choices=literal_choices(node.args[0])
            else:continue
            for source in choices:
                if HAN.search(source):required.setdefault(source,[]).append(f'{relative}:{node.lineno}')
    # Registries and labels passed to tr through variables also need coverage.
    registries={'ui/keybindings.py':('COMMANDS','FIXED_KEYS'),
                'music/chord_operations.py':('QUALITY_LABELS',),'music/model.py':('PATTERNS',)}
    def strings(value):
        if isinstance(value,str):yield value
        elif isinstance(value,dict):
            for key,item in value.items():yield from strings(key);yield from strings(item)
        elif isinstance(value,(tuple,list)):
            for item in value:yield from strings(item)
    for filename,names in registries.items():
        for node in ast.parse((root/'lingfeng'/filename).read_text('utf-8')).body:
            if not isinstance(node,ast.Assign) or not any(isinstance(t,ast.Name) and t.id in names for t in node.targets):continue
            try:value=ast.literal_eval(node.value)
            except (ValueError,TypeError):continue
            for source in strings(value):
                if HAN.search(source):required.setdefault(source,[]).append(f'lingfeng/{filename}:{node.lineno}')
    missing=[{'source':source,'locations':locations} for source,locations in required.items() if source not in catalog]
    bad_fields=[];empty=[];unexpected_han=[]
    for source,target in catalog.items():
        if not isinstance(target,str) or not target.strip():empty.append(source);continue
        try:
            if fields(source)!=fields(target):bad_fields.append(source)
        except ValueError:bad_fields.append(source)
        if HAN.search(target) and source not in INTENTIONAL_EN_HAN:unexpected_han.append(source)
    result={'status':'passed' if not any((duplicates,missing,bad_fields,empty,unexpected_han)) else 'failed',
            'files_scanned':len(files),'catalog_entries':len(catalog),'translation_calls':calls,
            'exception_calls_checked':exceptions,'required_sources':len(required),
            'missing_translations':missing,'duplicate_catalog_keys':duplicates,'invalid_format_fields':bad_fields,
            'empty_translations':empty,'unexpected_chinese_in_english':unexpected_han,
            'intentional_bilingual_language_labels':sorted(INTENTIONAL_EN_HAN),
            'dynamic_translation_calls':dynamic,
            'limits':['Dynamic expressions, OS/native-library errors and user-entered text require runtime review.',
                      'Help and GM instrument pairs are verified in tests/test_v50_help.py.',
                      'Static coverage does not prove visual fit or semantic translation accuracy.']}
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);args=parser.parse_args()
    result=audit()
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    summary={key:value for key,value in result.items() if key not in ('dynamic_translation_calls','limits')}
    print(json.dumps(summary,ensure_ascii=False,indent=2));raise SystemExit(0 if result['status']=='passed' else 1)

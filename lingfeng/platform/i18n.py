"""Explicit Chinese/English UI catalog. Musical data is never translated."""
import json
from pathlib import Path

LANGUAGE='zh'
EN=json.loads((Path(__file__).parent/'en.json').read_text(encoding='utf-8'))
ZH={}


def set_language(language):
    global LANGUAGE
    LANGUAGE='en' if language=='en' else 'zh'

def tr(source,*args):
    text=EN.get(source,source) if LANGUAGE=='en' else ZH.get(source,source)
    return text.format(*args) if args else text

"""Explicit Chinese/English UI catalog. Musical data is never translated."""
import json
from pathlib import Path
from PySide6.QtCore import QObject,QEvent
from PySide6.QtWidgets import QDialogButtonBox

LANGUAGE='zh'
EN=json.loads((Path(__file__).parent/'en.json').read_text(encoding='utf-8'))
ZH={}


def set_language(language):
    global LANGUAGE
    LANGUAGE='en' if language=='en' else 'zh'

def tr(source,*args):
    text=EN.get(source,source) if LANGUAGE=='en' else ZH.get(source,source)
    return text.format(*args) if args else text

class DialogLanguageFilter(QObject):
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.Show and isinstance(obj,QDialogButtonBox):
            labels={'Ok':'确定','Cancel':'取消','Save':'保存','Discard':'不保存','Yes':'是','No':'否','Close':'关闭','Apply':'应用'}
            for code,label in labels.items():
                button=obj.button(getattr(QDialogButtonBox.StandardButton,code))
                if button:button.setText(tr(button.property('localizedLabel') or label))
        return False

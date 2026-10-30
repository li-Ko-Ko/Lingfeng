"""Translate Qt standard buttons when dialogs become visible."""
from PySide6.QtCore import QObject, QEvent
from PySide6.QtWidgets import QDialogButtonBox
from lingfeng.platform.i18n import tr

class DialogLanguageFilter(QObject):
    def eventFilter(self,obj,event):
        if event.type()==QEvent.Type.Show and isinstance(obj,QDialogButtonBox):
            labels={'Ok':'确定','Cancel':'取消','Save':'保存','Discard':'不保存','Yes':'是','No':'否','Close':'关闭','Apply':'应用'}
            for code,label in labels.items():
                button=obj.button(getattr(QDialogButtonBox.StandardButton,code))
                if button:button.setText(tr(button.property('localizedLabel') or label))
        return False

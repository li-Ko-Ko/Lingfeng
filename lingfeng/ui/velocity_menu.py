"""Common velocity choices; numeric input always starts at the saved default."""
from PySide6.QtWidgets import QInputDialog
from lingfeng.platform.i18n import tr
from lingfeng.platform.chord_preferences import default_velocity
from lingfeng.audio.velocity import options


def populate_velocity_menu(menu,role,apply,*,title='修改力度',default_first=True,current=None):
    default=default_velocity(role)
    def add_default():
        action=menu.addAction(tr('使用默认力度（{0}）',default),lambda:apply(default))
        menu.default_action=action
    if default_first:add_default();menu.addSeparator()
    for value in options():
        action=menu.addAction(str(value),lambda checked=False,v=value:apply(v));action.setData(value)
        if current is not None:action.setCheckable(True);action.setChecked(current=={value})
    menu.addSeparator()
    if not default_first:add_default()
    def prompt():
        value,ok=QInputDialog.getInt(menu,tr(title),tr('MIDI 力度（1–127）'),default,1,127)
        if ok:apply(value)
    menu.custom_action=menu.addAction(tr('自定义力度…'),prompt)
    menu.action_refs=menu.actions()


def input_velocity(parent,role,apply,title='修改力度'):
    value,ok=QInputDialog.getInt(parent,tr(title),tr('MIDI 力度（1–127）'),default_velocity(role),1,127)
    if ok:apply(value)

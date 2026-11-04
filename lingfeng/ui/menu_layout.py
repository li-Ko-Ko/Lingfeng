"""Group editing commands while retaining their original QAction objects."""
from PySide6.QtWidgets import QMenu
from lingfeng.platform.i18n import tr


def arrange_menu(menu,layout):
    original=menu.actions();by_text={a.text().split('\t',1)[0]:a for a in original if not a.isSeparator()}
    used=set();groups=[]
    for action in original:menu.removeAction(action)
    for title,labels in layout:
        if labels is None:
            if title is None:menu.addSeparator();continue
            action=by_text.get(tr(title))
            if action is not None:menu.addAction(action);used.add(action)
            continue
        group=QMenu(tr(title),menu)
        for label in labels:
            action=by_text.get(tr(label))
            if action is not None:group.addAction(action);used.add(action)
        if group.actions():
            group.action_refs=group.actions();groups.append(group);menu.addMenu(group)
    # Retain commands introduced by another feature instead of hiding them.
    for action in original:
        if action not in used and not action.isSeparator():menu.addAction(action)
    menu.group_menus=groups;menu.action_refs=original+menu.actions()
    for surface in (menu,*menu.findChildren(QMenu)):
        surface.setProperty('editorContextMenu',True)


def arrange_chord_menu(menu):
    arrange_editor_menu(menu,'chord')


def arrange_note_menu(menu):
    arrange_editor_menu(menu,'note')


def arrange_editor_menu(menu,kind):
    from lingfeng.platform.context_menu_preferences import blocks
    layout=[]
    for block in blocks(kind):
        if layout and block['id'] in ('clipboard','dynamics','recognition','delete'):layout.append((None,None))
        if block['grouped']:layout.append((block['title'],block['labels']))
        else:layout.extend((label,None) for label in block['labels'])
    arrange_menu(menu,layout)

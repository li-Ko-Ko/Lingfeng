"""Edit context-menu ordering/grouping without changing live preferences."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QTabWidget, QVBoxLayout, QWidget)

from lingfeng.platform.context_menu_preferences import BLOCKS, default_layout, normalize_layout, settings_dict
from lingfeng.platform.i18n import tr


class ContextMenuSettingsDialog(QDialog):
    def __init__(self, parent=None, values=None):
        super().__init__(parent)
        self.setWindowTitle(tr('右键菜单'))
        self.resize(660, 570)
        self.setMinimumSize(480, 420)
        values = settings_dict() if values is None else values
        layout = normalize_layout(values.get('context_menu_layout') if isinstance(values, dict) else None)
        box = QVBoxLayout(self)
        info = QLabel(tr('拖动调整整组顺序。勾选将该组放入子菜单，取消勾选直接显示。复制、粘贴、分割与合并始终直接显示；这些设置不会隐藏命令。'))
        info.setWordWrap(True)
        box.addWidget(info)
        self.tabs = QTabWidget()
        box.addWidget(self.tabs, 1)
        self.lists = {}
        self.details = {}
        for kind, title in (('chord', '和弦菜单'), ('note', '音符菜单')):
            page = QWidget()
            page_box = QVBoxLayout(page)
            listing = QListWidget()
            listing.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            listing.setDefaultDropAction(Qt.DropAction.MoveAction)
            listing.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            self.lists[kind] = listing
            page_box.addWidget(listing, 1)
            details = QLabel()
            details.setWordWrap(True)
            details.setMinimumHeight(54)
            details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.details[kind] = details
            page_box.addWidget(details)
            actions = QHBoxLayout()
            for text, callback in ((tr('上移'), lambda checked=False, k=kind: self.move_item(k, -1)),
                                   (tr('下移'), lambda checked=False, k=kind: self.move_item(k, 1)),
                                   (tr('恢复本页默认值'), lambda checked=False, k=kind: self.reset_page(k))):
                button = QPushButton(text)
                button.clicked.connect(callback)
                actions.addWidget(button)
            page_box.addLayout(actions)
            listing.currentItemChanged.connect(lambda current, previous, k=kind: self.show_details(k))
            self.populate(kind, layout[kind])
            self.tabs.addTab(page, tr(title))
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        box.addWidget(self.buttons)

    def populate(self, kind, entries):
        definitions = {block['id']: block for block in BLOCKS[kind]}
        listing = self.lists[kind]
        listing.clear()
        for entry in entries:
            definition = definitions[entry['id']]
            text = tr(definition['title'])
            if not definition['groupable']:
                text += ' · ' + tr('直接显示（固定）')
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, entry['id'])
            if definition['groupable']:
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if entry['grouped'] else Qt.CheckState.Unchecked)
            else:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            item.setToolTip(tr('包含：{0}', '、'.join(tr(label) for label in definition['labels'])))
            listing.addItem(item)
        if listing.count():
            listing.setCurrentRow(0)

    def move_item(self, kind, delta):
        listing = self.lists[kind]
        row = listing.currentRow()
        target = row + delta
        if row >= 0 and 0 <= target < listing.count():
            item = listing.takeItem(row)
            listing.insertItem(target, item)
            listing.setCurrentRow(target)

    def reset_page(self, kind):
        self.populate(kind, default_layout()[kind])

    def show_details(self, kind):
        current = self.lists[kind].currentItem()
        code = current.data(Qt.ItemDataRole.UserRole) if current is not None else None
        definition = next((block for block in BLOCKS[kind] if block['id'] == code), None)
        self.details[kind].setText(tr('包含：{0}', '、'.join(tr(label) for label in definition['labels'])) if definition else '')

    def value(self):
        result = {}
        for kind, listing in self.lists.items():
            definitions = {block['id']: block for block in BLOCKS[kind]}
            result[kind] = []
            for row in range(listing.count()):
                item = listing.item(row)
                code = item.data(Qt.ItemDataRole.UserRole)
                grouped = definitions[code]['groupable'] and item.checkState() == Qt.CheckState.Checked
                result[kind].append(dict(id=code, grouped=bool(grouped)))
        return {'context_menu_layout': normalize_layout(result)}

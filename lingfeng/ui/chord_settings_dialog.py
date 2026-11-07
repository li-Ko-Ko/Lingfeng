"""Quick-chord selection and the complete quality reference."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
                               QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget,
                               QVBoxLayout, QWidget)

from lingfeng.music.model import QUALITIES, SHARP
from lingfeng.music.quality_catalog import yue2_lossless_quality
from lingfeng.platform.chord_preferences import (DEFAULT_QUICK_QUALITIES,
                                               normalize_qualities,
                                               settings_dict)
from lingfeng.platform.i18n import tr


def quality_formula(code):
    """Written chord degrees, retaining compound and double-altered degrees."""
    from lingfeng.music.quality_catalog import degree_formula
    return degree_formula(code)


class ChordSettingsDialog(QDialog):
    def __init__(self, parent=None, values=None):
        super().__init__(parent)
        self.setWindowTitle(tr('和弦性质'))
        self.resize(740, 600)
        self.setMinimumSize(570, 480)
        values = settings_dict() if values is None else values
        selected = normalize_qualities(values.get('quick_chord_qualities'))
        from lingfeng.music.chord_operations import quality_items
        self.quality_labels = dict(quality_items())

        box = QVBoxLayout(self)
        self.tabs = QTabWidget()
        box.addWidget(self.tabs, 1)
        quick = QWidget()
        quick_box = QVBoxLayout(quick)
        note = QLabel(tr('勾选要用于编辑和弦与右键菜单的性质。这里使用 PyChord 名称，每项都可无损转换为 YuE2 ABC 和弦。可拖动或使用上移、下移调整顺序。'))
        note.setWordWrap(True)
        quick_box.addWidget(note)
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        quick_box.addWidget(self.list, 1)
        self.summary = QLabel()
        quick_box.addWidget(self.summary)
        actions = QHBoxLayout()
        for label, callback in ((tr('上移'), lambda: self.move_item(-1)),
                                (tr('下移'), lambda: self.move_item(1)),
                                (tr('全选'), lambda: self.set_all(True)),
                                (tr('全不选'), lambda: self.set_all(False)),
                                (tr('恢复常用选项'), self.reset_quick)):
            button = QPushButton(label)
            button.clicked.connect(callback)
            actions.addWidget(button)
        quick_box.addLayout(actions)
        self.tabs.addTab(quick, tr('快速创建和弦'))
        self.list.itemChanged.connect(self.update_summary)
        self.populate_quick(selected)

        reference = QWidget()
        reference_box = QVBoxLayout(reference)
        preview_controls = QHBoxLayout()
        preview_controls.addWidget(QLabel(tr('预览根音')))
        self.preview_root = QComboBox()
        for pc, name in enumerate(SHARP):
            self.preview_root.addItem(name, pc)
        preview_controls.addWidget(self.preview_root)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('搜索名称、性质或数字关系'))
        self.search.setClearButtonEnabled(True)
        preview_controls.addWidget(self.search, 1)
        reference_box.addLayout(preview_controls)
        self.preview = QTableWidget(len(QUALITIES), 3)
        self.preview.setHorizontalHeaderLabels([tr('和弦名称'), tr('和弦性质'), tr('数字关系（根音 = 1）')])
        self.preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.preview.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.preview.verticalHeader().setVisible(False)
        self.preview.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.preview.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.preview.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        reference_box.addWidget(self.preview, 1)
        reference_note = QLabel(tr('数字以和弦根音为 1，保留升降号及 9、11、13 等扩展音；同义名称分别列出。'))
        reference_note.setWordWrap(True)
        reference_box.addWidget(reference_note)
        self.tabs.addTab(reference, tr('所有支持的和弦'))
        self.preview_root.currentIndexChanged.connect(self.update_preview)
        self.search.textChanged.connect(self.filter_preview)
        self.update_preview()

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        box.addWidget(self.buttons)

    def populate_quick(self, selected):
        self.list.clear()
        order = selected + [code for code in self.quality_labels if code not in selected]
        for code in order:
            if yue2_lossless_quality(code) is None:
                continue
            formula = quality_formula(code)
            item = QListWidgetItem(self.quality_labels[code] + '    ' + formula)
            item.setData(Qt.ItemDataRole.UserRole, code)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if code in selected else Qt.CheckState.Unchecked)
            item.setToolTip('C' + code + ' = ' + formula)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        self.update_summary()

    def move_item(self, delta):
        row = self.list.currentRow()
        target = row + delta
        if row >= 0 and 0 <= target < self.list.count():
            item = self.list.takeItem(row)
            self.list.insertItem(target, item)
            self.list.setCurrentRow(target)

    def set_all(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.list.count()):
            self.list.item(row).setCheckState(state)

    def reset_quick(self):
        self.populate_quick(list(DEFAULT_QUICK_QUALITIES))

    def update_summary(self):
        count = sum(self.list.item(row).checkState() == Qt.CheckState.Checked for row in range(self.list.count()))
        self.summary.setText(tr('已选 {0} / {1} 个和弦性质', count, self.list.count()))

    def update_preview(self):
        root = SHARP[self.preview_root.currentData()]
        for row, code in enumerate(QUALITIES):
            values = (root + code, self.quality_labels[code], quality_formula(code))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, code)
                item.setToolTip(value)
                self.preview.setItem(row, column, item)
        self.filter_preview()

    def filter_preview(self):
        query = self.search.text().strip().casefold()
        for row in range(self.preview.rowCount()):
            text = ' '.join(self.preview.item(row, column).text() for column in range(self.preview.columnCount()))
            self.preview.setRowHidden(row, bool(query) and query not in text.casefold())

    def value(self):
        selected = [self.list.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.list.count())
                    if self.list.item(row).checkState() == Qt.CheckState.Checked]
        return {'quick_chord_qualities': selected}

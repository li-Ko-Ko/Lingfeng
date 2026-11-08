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


class ChordQualityReference(QWidget):
    """Searchable catalogue shared by the settings and the chord picker."""

    def __init__(self, labels, root=0, parent=None):
        super().__init__(parent)
        self.labels = labels
        box = QVBoxLayout(self)
        controls = QHBoxLayout()
        controls.addWidget(QLabel(tr('预览根音')))
        self.preview_root = QComboBox()
        for pc, name in enumerate(SHARP):
            self.preview_root.addItem(name, pc)
        self.preview_root.setCurrentIndex(root % 12)
        controls.addWidget(self.preview_root)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('搜索名称、性质或数字关系'))
        self.search.setClearButtonEnabled(True)
        controls.addWidget(self.search, 1)
        box.addLayout(controls)
        self.preview = QTableWidget(len(QUALITIES), 3)
        self.preview.setHorizontalHeaderLabels([tr('和弦名称'), tr('和弦性质'), tr('数字关系（根音 = 1）')])
        self.preview.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.preview.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.preview.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.preview.verticalHeader().setVisible(False)
        self.preview.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.preview.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.preview.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        box.addWidget(self.preview, 1)
        note = QLabel(tr('数字以和弦根音为 1，保留升降号及 9、11、13 等扩展音；同义名称分别列出。'))
        note.setWordWrap(True)
        box.addWidget(note)
        self.preview_root.currentIndexChanged.connect(self.update_preview)
        self.search.textChanged.connect(self.filter_preview)
        self.update_preview()

    def update_preview(self):
        root = SHARP[self.preview_root.currentData()]
        for row, code in enumerate(QUALITIES):
            values = (root + code, self.labels[code], quality_formula(code))
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
        row = self.preview.currentRow()
        if row >= 0 and self.preview.isRowHidden(row):
            self.preview.clearSelection()


class ChordQualityPickerDialog(QDialog):
    def __init__(self, root, quality, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('从完整和弦列表选择…'))
        self.resize(740, 560)
        self.setMinimumSize(540, 380)
        from lingfeng.music.chord_operations import quality_items
        box = QVBoxLayout(self)
        self.warning = QLabel(tr('部分和弦性质可能与 YuE2 生态不兼容。导出 YuE2 兼容版 ABC 时，无法无损转换的和弦需确认替换或省略。'))
        self.warning.setWordWrap(True)
        font = self.warning.font()
        font.setBold(True)
        self.warning.setFont(font)
        box.addWidget(self.warning)
        reference = ChordQualityReference(dict(quality_items()), root)
        self.preview, self.search = reference.preview, reference.search
        box.addWidget(reference, 1)
        self.compatibility = QLabel()
        self.compatibility.setWordWrap(True)
        box.addWidget(self.compatibility)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        box.addWidget(self.buttons)
        self.preview.itemSelectionChanged.connect(self.update_selection)
        self.search.textChanged.connect(self.update_selection)
        self.preview.itemDoubleClicked.connect(self.accept)
        if quality in QUALITIES:
            row = list(QUALITIES).index(quality)
            self.preview.selectRow(row)
            self.preview.scrollToItem(self.preview.item(row, 0))
        self.update_selection()

    def update_selection(self):
        quality = self.value()
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(quality is not None)
        if quality is None:
            text = ''
        elif yue2_lossless_quality(quality) is None:
            text = tr('此和弦性质无法无损转换为 YuE2 和弦。')
        else:
            text = tr('此和弦性质可无损转换为 YuE2 和弦。')
        self.compatibility.setText(text)

    def accept(self):
        if self.value() is not None:
            super().accept()

    def value(self):
        items = self.preview.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items and not self.preview.isRowHidden(items[0].row()) else None


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

        reference = ChordQualityReference(self.quality_labels)
        self.preview, self.preview_root, self.search = reference.preview, reference.preview_root, reference.search
        self.tabs.addTab(reference, tr('所有支持的和弦'))

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

    def value(self):
        selected = [self.list.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.list.count())
                    if self.list.item(row).checkState() == Qt.CheckState.Checked]
        return {'quick_chord_qualities': selected}

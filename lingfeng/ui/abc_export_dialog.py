from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHeaderView, QLabel, QMessageBox,
    QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)
from PySide6.QtCore import Qt

from lingfeng.music.abc_export import (
    abc_location, abc_track_project, sheetsage_chord_changes, sheetsage_issues,
    valid_yue2_chord, yue2_link_replacement,
)
from lingfeng.platform.i18n import tr
from lingfeng.ui.track_picker import TrackPicker


class AbcExportDialog(QDialog):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.overrides = {}
        self.links = [(bar, label, replacement)
                      for bar, measure in enumerate(project.measures, 1)
                      if (label := measure.section) and (replacement := yue2_link_replacement(label))]
        self.setWindowTitle(tr('导出 ABC'))
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        self.format = QComboBox()
        self.format.addItem(tr('YuE2 兼容版 ABC（和弦符号）'), True)
        self.format.addItem(tr('完整 ABC（和弦符号与音符）'), False)
        layout.addWidget(self.format)
        self.tracks = TrackPicker(project)
        layout.addWidget(self.tracks)
        self.details = QLabel()
        self.details.setWordWrap(True)
        layout.addWidget(self.details)
        self.rewrite_links = QCheckBox(tr('导出时将 link 替换为 interlude'))
        self.convert_chords = QCheckBox(tr('预填不兼容和弦的替换建议'))
        for rule in (self.rewrite_links, self.convert_chords):
            rule.setChecked(True)
            rule.toggled.connect(self._update)
            layout.addWidget(rule)
        self.check = QPushButton(tr('检查 YuE2 兼容性'))
        self.check.clicked.connect(self.check_compatibility)
        layout.addWidget(self.check)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.format.currentIndexChanged.connect(self._update)
        self.tracks.changed.connect(self._update)
        self._update()

    def _update(self):
        roles = self.tracks.roles()
        selected = abc_track_project(self.project, roles) if roles else None
        self.issues = sheetsage_issues(selected) if selected else [tr('请选择至少一个导出轨道。')]
        self.changes = sheetsage_chord_changes(selected) if selected else []
        if self.links and not self.rewrite_links.isChecked():
            self.issues.append(tr('YuE2 不支持 link。请改用 interlude 或启用导出替换。'))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(bool(roles))
        compatible = self.format.currentData()
        for widget in (self.rewrite_links, self.convert_chords, self.check):
            widget.setVisible(compatible)
        if compatible:
            details = tr('Vocal 和 Ins 各为单声部。未选的旋律用休止填充，和弦符号写在 Vocal 的实际变更时点。')
            if self.issues:
                details += '\n' + tr('有 {0} 项问题须在导出前修改。', len(self.issues))
            elif self.changes:
                details += '\n' + tr('导出前需要确认 {0} 处和弦替换。', len(self.changes))
        else:
            details = tr('输出所选旋律和和弦轨。和弦轨保留实际音高和节奏，旋律包含首段唱词。')
        self.details.setText(details)

    def _location(self, tick):
        return abc_location(self.project, tick)

    def compatibility_report(self):
        required = list(self.issues)
        optional = []
        if self.links:
            labels = [tr('第 {0} 小节', bar) + f'  {label} → {replacement}'
                      for bar, label, replacement in self.links]
            if self.rewrite_links.isChecked():
                optional.extend([tr('YuE2 不支持 link，导出时将按以下方案替换。'), *labels])
            else:
                required.extend(labels)
        if self.changes:
            omitted = tr('省略')
            if self.convert_chords.isChecked():
                optional.append(tr('下列和弦替换会在导出前供你编辑和确认。'))
                optional.extend(f'{self._location(tick)}  {original} → {converted or omitted}'
                                for tick, original, converted in self.changes)
            else:
                required.append(tr('下列和弦需在导出确认窗口逐处填写替换符号，或确认省略。'))
                required.extend(f'{self._location(tick)}  {original}' for tick, original, _ in self.changes)
        return '\n\n'.join((tr('必须修改') + '\n' + ('\n'.join(required) or tr('无')),
                             tr('可选处理') + '\n' + ('\n'.join(optional) or tr('无'))))

    def check_compatibility(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('YuE2 兼容性检查'))
        dialog.resize(660, 380)
        layout = QVBoxLayout(dialog)
        report = QPlainTextEdit(self.compatibility_report(), dialog)
        report.setReadOnly(True)
        layout.addWidget(report)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, parent=dialog)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.exec()

    def accept(self):
        if not self.tracks.roles():
            return
        if self.format.currentData():
            if self.issues:
                self.check_compatibility()
                return
            if self.links:
                bars = '、'.join(str(bar) for bar, _, _ in self.links)
                result = QMessageBox.information(
                    self, tr('YuE2 段落替换'),
                    tr('YuE2 不支持 link。以下小节的 link 将在导出时替换为 interlude：{0}。', bars),
                    QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
                if result != QMessageBox.StandardButton.Ok:
                    return
            if self.changes and not self.confirm_replacements():
                return
        super().accept()

    def confirm_replacements(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('确认 YuE2 和弦替换'))
        dialog.resize(640, 390)
        layout = QVBoxLayout(dialog)
        info = QLabel(tr('双击替换栏可编辑，例如 Cmaj7/G。留空将省略该符号。修改仅用于本次导出。'))
        info.setWordWrap(True)
        layout.addWidget(info)
        table = QTableWidget(len(self.changes), 3, dialog)
        table.setHorizontalHeaderLabels([tr('位置'), tr('原和弦'), tr('替换和弦')])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        prefill = self.convert_chords.isChecked()
        for row, (tick, original, converted) in enumerate(self.changes):
            for column, text in enumerate((self._location(tick), original, converted if prefill else '')):
                item = QTableWidgetItem(text)
                if column != 2:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(row, column, item)
        layout.addWidget(table)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)
        buttons.rejected.connect(dialog.reject)

        def confirm():
            values = {}
            for row, (tick, _, _) in enumerate(self.changes):
                value = table.item(row, 2).text().strip()
                if not valid_yue2_chord(value):
                    table.setCurrentCell(row, 2)
                    QMessageBox.warning(dialog, dialog.windowTitle(),
                                        tr('第 {0} 行的替换和弦不符合 YuE2 格式。', row+1))
                    return
                values[tick] = value
            self.overrides = values
            dialog.accept()

        buttons.accepted.connect(confirm)
        return dialog.exec() == QDialog.DialogCode.Accepted

    def value(self):
        return dict(sheetsage=self.format.currentData(), which=self.tracks.roles(), chord_overrides=self.overrides,
                    rewrite_links=self.rewrite_links.isChecked(), convert_chords=self.convert_chords.isChecked())

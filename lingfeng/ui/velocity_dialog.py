"""Manual velocity presets with opt-in inspection of the current chord sound."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QLineEdit, QPushButton)
from lingfeng.audio.velocity import DEFAULT_OPTIONS, detect_options, parse_options
from lingfeng.platform.i18n import tr


class VelocityOptionsDialog(QDialog):
    def __init__(self, values, spec, parent=None):
        super().__init__(parent); self.setWindowTitle(tr('力度选项')); self.setMinimumWidth(460)
        self.spec = dict(spec)
        form = QFormLayout(self)
        info = QLabel(tr('设置和弦右键菜单的 MIDI 力度（1–127），用逗号或空格分隔。启动、打开设置或切换音源均不会检测；仅点击下方按钮时读取当前和弦轨音色。'))
        info.setWordWrap(True); form.addRow(info)
        self.values = QLineEdit(', '.join(map(str, values))); form.addRow(tr('常用力度'), self.values)
        reset = QPushButton(tr('恢复常用值')); reset.clicked.connect(lambda: self.values.setText(', '.join(map(str, DEFAULT_OPTIONS)))); form.addRow(reset)
        self.detect_button = QPushButton(tr('检测当前和弦音源并生成选项'))
        self.detect_button.clicked.connect(self.detect); form.addRow(self.detect_button)
        self.notice = QLabel(); self.notice.setWordWrap(True); self.notice.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); form.addRow(self.notice)
        note = QLabel(tr('采样音源按力度区间的中间值生成建议。不同键位、交叉层及控制器切换可能产生不同分层；区间数不等于所有音高的采样层数。原生合成与外部 MIDI 音源无法查询采样层，保留现有选项。单层音色仍可用不同力度控制强弱。确认后保存，取消则不修改。'))
        note.setWordWrap(True); form.addRow(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); form.addRow(buttons)

    def detect(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor); self.detect_button.setEnabled(False)
        try:
            report = detect_options(self.spec)
            if report is None:
                self.notice.setText(tr('当前音源不提供可查询的采样力度层，已保留现有选项。'))
            else:
                self.values.setText(', '.join(map(str, report['options'])))
                ranges = ', '.join(f'{a}–{b}' for a, b in report['bands'])
                self.notice.setText(tr('检测到 {0} 个力度区间：{1}。已生成各区间中间值，可手动调整后确认。', len(report['bands']), ranges))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.notice.setText(tr('检测失败，已保留现有选项：{0}', str(exc)))
        finally:
            self.detect_button.setEnabled(True); QApplication.restoreOverrideCursor()

    def value(self):
        return parse_options(self.values.text())

    def accept(self):
        try:
            self.value()
        except ValueError:
            self.notice.setText(tr('请输入 1–127 的整数，用逗号或空格分隔。')); return
        super().accept()

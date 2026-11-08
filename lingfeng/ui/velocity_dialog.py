"""Manual velocity presets with opt-in inspection of the current chord sound."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFormLayout,
                               QFrame, QGroupBox, QLabel, QLayout, QLineEdit,
                               QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
                               QWidget)
from lingfeng.audio.velocity import DEFAULT_OPTIONS, detect_options, parse_options
from lingfeng.platform.i18n import tr


class VelocityOptionsWidget(QWidget):
    def __init__(self, values, spec, parent=None):
        super().__init__(parent)
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


class VelocityOptionsDialog(QDialog):
    def __init__(self, values, spec, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('力度选项')); self.setMinimumWidth(460)
        box = QVBoxLayout(self)
        self.options = VelocityOptionsWidget(values, spec, self)
        box.addWidget(self.options)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject)
        box.addWidget(self.buttons)

    # Keep the standalone dialog's controls available to existing callers.
    @property
    def values(self): return self.options.values
    @property
    def notice(self): return self.options.notice
    @property
    def detect_button(self): return self.options.detect_button
    def detect(self): return self.options.detect()
    def value(self): return self.options.value()

    def accept(self):
        try:
            self.value()
        except ValueError:
            self.notice.setText(tr('请输入 1–127 的整数，用逗号或空格分隔。')); return
        super().accept()


class DynamicsSettingsDialog(VelocityOptionsDialog):
    """Creation defaults and velocity-menu presets share one saved transaction."""
    def __init__(self, values, spec, parent=None, defaults=None):
        from lingfeng.platform.chord_preferences import normalize_velocities, settings_dict
        super().__init__(values, spec, parent)
        self.setWindowTitle(tr('音符与力度'))
        self.resize(600, 590); self.setMinimumWidth(520)
        defaults = normalize_velocities((settings_dict() if defaults is None else defaults).get('default_velocities'))
        creation = QGroupBox(tr('创建默认值'))
        form = QFormLayout(creation)
        self.melody_velocity = QSpinBox(); self.instrument_velocity = QSpinBox(); self.chord_velocity = QSpinBox()
        for control, role in ((self.melody_velocity, 'melody'), (self.instrument_velocity, 'instrument'),
                              (self.chord_velocity, 'harmony')):
            control.setRange(1, 127); control.setValue(defaults[role])
            control.setToolTip(tr('MIDI 力度（1–127）'))
        form.addRow(tr('人声默认力度'), self.melody_velocity)
        form.addRow(tr('乐器默认力度'), self.instrument_velocity)
        form.addRow(tr('和弦默认力度'), self.chord_velocity)
        info = QLabel(tr('和弦各声部共用力度。和弦卷帘新建音符跟随所在和弦的力度，空白处使用和弦默认力度。没有创建记录时，空和弦和未识别和弦也使用默认力度。'))
        info.setWordWrap(True); form.addRow(info)
        box = self.layout()
        box.removeWidget(self.options)
        presets = QGroupBox(tr('常用力度与音源检测'))
        preset_box = QVBoxLayout(presets); preset_box.addWidget(self.options)
        content = QWidget()
        content_box = QVBoxLayout(content)
        content_box.setContentsMargins(0, 0, 0, 0)
        content_box.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        content_box.addWidget(creation); content_box.addWidget(presets)
        content_box.addStretch()
        self.scroll = QScrollArea()
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True); self.scroll.setWidget(content)
        content.setAutoFillBackground(False)
        self.scroll.viewport().setAutoFillBackground(False)
        box.insertWidget(0, self.scroll, 1)

    def value(self):
        return {'default_velocities': {'melody': self.melody_velocity.value(),
                                       'instrument': self.instrument_velocity.value(),
                                       'harmony': self.chord_velocity.value()},
                'chord_velocity_options': self.options.value()}

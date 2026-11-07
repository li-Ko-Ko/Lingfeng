from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QWidget

from lingfeng.audio.midi import EXPORT_ROLES, selected_roles
from lingfeng.platform.i18n import tr


class TrackPicker(QWidget):
    changed = Signal()

    def __init__(self, project, which='both', parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.checks = {}
        selected = selected_roles(which)
        labels = (project.melody_name(0), project.melody_name(1), tr('和弦'))
        for role, label in zip(EXPORT_ROLES, labels):
            box = QCheckBox(label)
            box.setChecked(role in selected)
            box.toggled.connect(lambda checked: self.changed.emit())
            layout.addWidget(box)
            self.checks[role] = box
        layout.addStretch()

    def roles(self):
        return tuple(role for role, box in self.checks.items() if box.isChecked())

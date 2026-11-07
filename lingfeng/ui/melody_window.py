"""A floating piano roll bound to one melody track."""

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from lingfeng.platform.i18n import tr
from lingfeng.ui.controls import DurationSelector, GridSelector, RollViewControls
from lingfeng.ui.flow_layout import FlowLayout
from lingfeng.ui.panes import FloatingPane, RollTransport, RollVolumeControls
from lingfeng.ui.piano_roll import PianoRoll


class MelodyWindow(FloatingPane):
    def __init__(self, owner, track):
        super().__init__(owner.project.melody_name(track), owner, f'melody_{track}')
        self.track = track
        body = QWidget()
        self.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)
        self.transport_controls = RollTransport(owner)
        layout.addWidget(self.transport_controls)

        toolbar = QWidget()
        tools = FlowLayout(toolbar)
        tools.setContentsMargins(0, 0, 0, 0)
        self.tool = QComboBox()
        for label, value in [('智能工具', 'smart'), ('绘制工具', 'draw')]:
            self.tool.addItem(tr(label), value)
        self.length = DurationSelector()
        self.grid = GridSelector()
        tools.addWidget(self.tool)
        tools.addWidget(QLabel(tr('时值')))
        tools.addWidget(self.length)
        tools.addWidget(QLabel(tr('吸附')))
        tools.addWidget(self.grid)
        self.roll = PianoRoll(owner.project)
        self.roll.melody_track = track
        self.roll.set_project(owner.project)
        self.roll.set_panel('navigator', False)
        self.roll.set_panel('chords', owner.floating_melody_chords)
        self.view_controls = RollViewControls(self.roll)
        tools.addWidget(self.view_controls)
        tools.addStretch()
        layout.addWidget(toolbar)
        layout.addWidget(self.roll, 1)
        self.volume_controls = RollVolumeControls(owner)
        layout.addWidget(self.volume_controls)

        self.sync = QAction(tr('同步时间轴'), self)
        self.sync.setCheckable(True)
        self.sync.setToolTip(tr('同步主界面的滚动、缩放与跟随播放游标；取消后独立控制。'))
        self.sync.toggled.connect(lambda enabled: owner.set_timeline_sync(enabled, self.roll))
        self.transport_controls.follow.toggled.connect(lambda enabled: owner.sync_follow(enabled, self.roll))
        options = self.transport_controls.options.menu()
        options.addAction(self.sync)
        options.addSeparator()
        options.addAction(self.roll.lane.velocity_action)
        for key in ('chords', 'velocity', 'ruler'):
            options.addAction(self.view_controls.panel_actions[key])
        self.tool.currentIndexChanged.connect(lambda: setattr(self.roll, 'tool', self.tool.currentData()))
        self.length.currentIndexChanged.connect(self.set_duration)
        self.grid.currentIndexChanged.connect(self.set_grid)

    def set_grid(self):
        self.roll.grid = self.grid.currentData()
        self.roll.grid_bars = self.grid.bars
        self.roll.refresh()

    def set_duration(self):
        self.roll.duration = self.length.currentData()
        self.roll.duration_bars = self.length.bars

    def view_state(self):
        roll = self.roll
        pitch = roll.pitch_at(roll.ruler_height + max(1, roll.viewport().height() - roll.ruler_height) / 2)
        return dict(
            geometry=self.saveGeometry(), scroll=roll.horizontalScrollBar().value(), zoom=roll.zoom,
            height=roll.row_height, pitch=pitch, compact=roll.compact, bounds=roll.pitch_range,
            manual_bounds=roll.manual_pitch_range, tool=self.tool.currentIndex(), grid=self.grid.currentIndex(),
            triplet=self.grid.triplet, length=self.length.currentIndex(), length_triplet=self.length.triplet,
            dotted=self.length.dotted_action.isChecked(), panels=roll.panels.copy(),
            selected=set(roll.selected_ids), duration=roll.previous_duration, previous=roll.previous_note_id,
            sync=self.sync.isChecked(), follow=self.transport_controls.follow.isChecked(),
        )

    def restore_view_state(self, state):
        roll = self.roll
        self.restoreGeometry(state['geometry'])
        self.tool.setCurrentIndex(state['tool'])
        self.grid.setCurrentIndex(state['grid'])
        self.grid.set_triplet(state['triplet'])
        self.length.setCurrentIndex(state['length'])
        self.length.set_triplet(state['length_triplet'])
        self.length.dotted_action.setChecked(state['dotted'])
        for key, value in state['panels'].items():
            self.view_controls.panel_actions[key].setChecked(value)
        roll.zoom = state['zoom']
        roll.compact = state['compact']
        roll.pitch_range = state['bounds']
        roll.manual_pitch_range = state['manual_bounds']
        self.view_controls.height.setValue(state['height'])
        roll.selected_ids = state['selected']
        roll.selected_note = next(iter(roll.selected_ids), '')
        roll.previous_duration = state['duration']
        roll.previous_note_id = state['previous']
        roll.refresh()
        roll.horizontalScrollBar().setValue(state['scroll'])
        roll.center_pitch(state['pitch'])
        self.sync.setChecked(state['sync'])
        blocked = self.transport_controls.follow.blockSignals(True)
        self.transport_controls.follow.setChecked(state['follow'])
        self.transport_controls.follow.blockSignals(blocked)

    def closeEvent(self, event):
        event.ignore()
        self.owner.toggle_roll_floating(self)

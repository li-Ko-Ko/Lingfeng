from __future__ import annotations
import copy
import sys

from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtGui import QFont,QAction,QKeySequence,QShortcut,QIcon,QActionGroup
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QPushButton, QToolButton, QComboBox, QCheckBox, QStackedWidget, QSplitter, QFileDialog, QMessageBox, QInputDialog, QDialog, QMenu, QMenuBar, QSizePolicy, QSlider, QWidgetAction, QFormLayout, QAbstractSpinBox
from lingfeng.music.model import Project, PPQ, pitch_name, uid, demo_project
from lingfeng.ui.piano_roll import PianoRoll
from lingfeng.ui.score_view import ScoreView
from lingfeng.ui.dialogs import NoteDialog, ChordDialog, MarkerDialog, SoundSettingsDialog
from lingfeng.ui.controls import DurationSelector, GridSelector, RollViewControls, IconButton, SizeControl, FontSizeControl
from lingfeng.ui.theme import stylesheet, apply_theme, is_dark
from lingfeng.audio.transport import Transport
from lingfeng.engraving.notation import ScoreLayout
from lingfeng.audio.midi import export_daw_bundle
from lingfeng.ui.fonts import ensure_fonts

from lingfeng.music.note_operations import NoteClipboard, shift_in_scale, join_notes, split_notes
from lingfeng.ui.flow_layout import FlowLayout
from lingfeng.platform.i18n import tr, set_language
from lingfeng.ui.language_filter import DialogLanguageFilter
from lingfeng.platform.help_content import BRAND
from lingfeng.ui.help_dialog import HelpDialog, ColorSettingsDialog
from lingfeng.ui.theme import set_roll_palettes, set_roll_coloring, set_note_degrees
from lingfeng.engraving.presentation import apply_forced_row, add_compression, add_annotation, forced_row_allowed

from lingfeng.platform.paths import resource_root, user_data_dir, documents_dir, safe_name

STYLE=stylesheet(False)


def button(text,slot=None,checkable=False):
    b=QPushButton(text);b.setCheckable(checkable)
    if slot:b.clicked.connect(slot)
    return b


def row(parent=None):
    layout=FlowLayout(parent);layout.setContentsMargins(12,7,12,7);layout.setSpacing(8);return layout


from lingfeng.ui.workspace import WorkspaceMixin
from lingfeng.ui.panes import TitleBar
from lingfeng.ui.history import HistoryMixin, HistoryState

class MainWindow(HistoryMixin,WorkspaceMixin,QMainWindow):
    def __init__(self,project=None):
        from lingfeng.ui.windowing import set_app_identity
        set_app_identity()
        super().__init__();ensure_fonts();self.project=project or demo_project();self.path=None
        if not self.project.chords:self.project.fill_chord_gaps()
        self.dirty=False;self.undo_history=[];self.redo_history=[];self.clipboard=None;self.note_clipboard=None;self.chord_clipboard=None;self.clipboard_kind=None
        self.playhead=0;self.play_anchor=0;self.transport_active=False;self.workspace='compose';self.loading=False;self.loop_range=None
        self.harmony_window=None;self.syncing_views=False;self.volume_before=None
        self.volume_timer=QTimer(self);self.volume_timer.setSingleShot(True);self.volume_timer.setInterval(350);self.volume_timer.timeout.connect(self.commit_volume)
        self.transport=Transport(self);self.transport.error.connect(self.status_message)
        self.setWindowFlags(Qt.WindowType.Window|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowMinMaxButtonsHint);self.setWindowTitle(BRAND);self.resize(1420,900);self.setMinimumSize(620,560)
        self.setWindowIcon(QIcon(str(resource_root()/'assets'/'lingfeng.ico')))
        from lingfeng.platform.preferences import load_preferences
        preferences=load_preferences(user_data_dir());self._preferences=preferences
        from lingfeng.music.chord_operations import set_quality_order
        from lingfeng.ui.keybindings import load_bindings, EditorKeys
        self.keybindings=load_bindings(preferences.get('keybindings',{}));self.editor_keys=EditorKeys(self);QApplication.instance().installEventFilter(self.editor_keys)
        set_quality_order(preferences.get('chord_order',[]))
        from lingfeng.ui.dialogs import chord_edit_defaults
        self.chord_edit_options=chord_edit_defaults(preferences.get('chord_edit_options',{}))
        self.last_project_dir=preferences.get('last_project_dir',str(documents_dir()))
        from lingfeng.music.progressions import load_library
        self.progression_presets=load_library(preferences.get('progression_presets',[]),preferences.get('progression_catalog_version',0))
        from lingfeng.ui.theme import set_accidental_preference
        set_accidental_preference(preferences.get('accidental_preference','sharp'))
        self.language=preferences.get('language','zh');set_language(self.language)
        set_roll_palettes(preferences.get('colors',{}))
        set_roll_coloring(preferences.get('roll_coloring',{}))
        set_note_degrees(preferences.get('show_note_degrees',True))
        self.show_information=preferences.get('show_information',True)
        ruler=preferences.get('chord_ruler_scale',1);self.chord_ruler_scale=ruler if ruler in (0,.25,.5,1,2,'bar') else 1
        self.language_filter=DialogLanguageFilter(self);QApplication.instance().installEventFilter(self.language_filter)
        self.build_ui();self.build_menu();self.refresh();self.set_theme(preferences.get('theme','light'));self.enable_native_frame()
        from lingfeng.audio.midi_input import MidiInputController
        self.midi_input=MidiInputController(self)
        self.timer=QTimer(self);self.timer.setTimerType(Qt.TimerType.PreciseTimer);self.timer.setInterval(8);self.timer.timeout.connect(self.playback_tick);self.timer.start()
        self.autosave=QTimer(self);self.autosave.setInterval(30000);self.autosave.timeout.connect(self.recover_save);self.autosave.start()
        QTimer.singleShot(0,self,lambda:self.roll.center_pitch(60))
        self.status_message(tr('Smart：空白拖动框选 · Draw：单击写入或删除，拖动编辑 · 右键复制变换'))
        from lingfeng import __version__
        if preferences.get('app_version')!=__version__:self.save_preferences()

    def build_ui(self):
        shell=QWidget();shell.setObjectName('shell');main=QVBoxLayout(shell);main.setContentsMargins(0,0,0,0);main.setSpacing(0);self.setCentralWidget(shell)
        header=QFrame();header.setObjectName('header');h=row(header);self.header_layout=h;h.setContentsMargins(8,4,8,4)
        brand=QVBoxLayout();brand.setSpacing(1);brand.setContentsMargins(0,0,0,0);name=QLabel(BRAND);name.setObjectName('brand');name.hide()
        self.subtitle=QLabel();self.subtitle.setObjectName('subtitle');self.subtitle.setMaximumWidth(240);self.subtitle.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);brand.addWidget(self.subtitle);h.addLayout(brand);h.addSpacing(12)
        self.compose_button=button(tr('创作'),lambda:self.switch_workspace('compose'),True);self.score_button=button(tr('制谱'),lambda:self.switch_workspace('score'),True)
        self.score_button.setToolTip(tr('切入制谱时同步音乐；卷帘编辑期间保留当前谱面。'))
        h.addWidget(self.compose_button);h.addWidget(self.score_button);h.addStretch()
        self.play_button=IconButton('play');self.play_button.activated.connect(self.toggle_play);self.play_button.setObjectName('play');h.addWidget(self.play_button)
        self.replay_button=IconButton('replay');self.replay_button.activated.connect(self.replay);self.replay_button.doubleActivated.connect(self.return_to_start);h.addWidget(self.replay_button)
        self.loop=QCheckBox(tr('循环选区'));self.loop.toggled.connect(self.change_loop);h.addWidget(self.loop)
        self.follow_playhead=QCheckBox(tr('跟随播放游标'));self.follow_playhead.setChecked(True);self.follow_playhead.setToolTip(tr('播放时自动滚动时间轴，使播放游标保持可见。'));h.addWidget(self.follow_playhead)
        self.bpm=SizeControl(100,20,300);self.bpm.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.PlusMinus);self.bpm.setRange(20,300);self.bpm.setValue(self.project.bpm);self.bpm.setSuffix(' BPM');self.bpm.valueChanged.connect(self.set_bpm);self.bpm.setFixedWidth(108);h.addWidget(self.bpm)
        h.addSpacing(10);h.addWidget(button(tr('保存'),self.save));export=QToolButton();export.setText(tr('导出'));export.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QMenu(export);self.populate_export_menu(menu);export.setMenu(menu);h.addWidget(export);main.addWidget(header)
        self.stack=QStackedWidget();main.addWidget(self.stack,1)
        self.compose=QWidget();self.compose_layout=QVBoxLayout(self.compose);self.compose_layout.setContentsMargins(16,14,16,12);self.stack.addWidget(self.compose)
        self.score_page=QWidget();self.score_layout=QVBoxLayout(self.score_page);self.score_layout.setContentsMargins(14,10,14,10);self.score_layout.setSpacing(8);self.stack.addWidget(self.score_page)
        st=row();st.setContentsMargins(2,0,2,0)
        self.score_style=QComboBox()
        for text,value in [(tr('立体简谱'),'spatial'),(tr('立体简谱 · 紧凑'),'compact'),(tr('传统简谱'),'traditional')]:self.score_style.addItem(text,value)
        self.score_style.currentIndexChanged.connect(lambda:self.set_notation('style',self.score_style.currentData()));st.addWidget(self.score_style)
        self.score_selection=QComboBox();self.score_selection.addItem(tr('小节选择'),'measure');self.score_selection.addItem(tr('拍选择'),'beat');self.score_selection.currentIndexChanged.connect(lambda:self.score_view.canvas.set_selection_unit(self.score_selection.currentData()));st.addWidget(self.score_selection)
        def score_field(label,field,extra=None):
            group=QWidget();line=QHBoxLayout(group);line.setContentsMargins(0,0,0,0);line.setSpacing(6)
            text=QLabel(tr(label));text.setBuddy(field);line.addWidget(text);line.addWidget(field)
            if extra is not None:line.addWidget(extra)
            st.addWidget(group)
        self.perline=SizeControl(4,1,16);self.perline.setSuffix('')
        self.perline.currentIndexChanged.connect(lambda:self.set_notation('per_line',self.perline.currentData()));score_field('每行小节',self.perline)
        self.note_font=FontSizeControl();self.font_limit_label=QLabel(tr('上限 {0}',26))
        self.note_font.currentIndexChanged.connect(lambda:self.set_notation('font_size',self.note_font.currentData()));score_field('音符字号',self.note_font,self.font_limit_label)
        st.addWidget(button(tr('推荐字号'),self.recommend_score_font))
        self.rowgap=SizeControl(15,4,32);self.rowgap.setSuffix('');self.rowgap.valueChanged.connect(lambda n:self.set_notation('row_gap',n));score_field('音高间距',self.rowgap)
        self.system_gap=SizeControl(12,0,80);self.system_gap.setSuffix('');self.system_gap.valueChanged.connect(lambda n:self.set_notation('system_gap',n));score_field('谱行间距',self.system_gap)
        self.score_zoom=QComboBox()
        self.score_zoom.addItem(tr('填满屏幕'),'width');self.score_zoom.addItem(tr('整页显示'),'page')
        for percent in (25,50,75,100,125,150,200,300,400):self.score_zoom.addItem(f'{percent}%',percent/100)
        self.score_zoom.setToolTip(tr('填满屏幕按可视宽度缩放；Ctrl+鼠标滚轮缩放，按住鼠标中键拖动页面。'))
        self.score_zoom.currentIndexChanged.connect(self.change_score_zoom);st.addWidget(self.score_zoom)
        st.addStretch()
        self.edit_toggle=button(tr('展开编辑器'),self.toggle_editor,True);self.edit_toggle.setChecked(True);self.edit_toggle.hide()
        self.score_options=IconButton('options');self.score_options.setToolTip(tr('谱面选项'));self.score_options.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QMenu(self.score_options);panel=QWidget();form=QFormLayout(panel);form.setSpacing(12)
        self.circle=QCheckBox(tr('圈出和弦音'));self.circle.toggled.connect(lambda v:self.set_notation('circles',v));form.addRow(self.circle)
        self.chromatic=QCheckBox(tr('调外音着色'));self.chromatic.toggled.connect(lambda v:self.set_notation('color',v));form.addRow(self.chromatic)
        self.scale_lines=QCheckBox(tr('显示其它音阶谱线'));self.scale_lines.toggled.connect(lambda v:self.set_notation('show_scale_lines',v));form.addRow(self.scale_lines)
        self.showlyrics=QCheckBox(tr('显示歌词'));self.showlyrics.toggled.connect(lambda v:self.set_notation('lyrics',v));form.addRow(self.showlyrics)
        self.dock_height=SizeControl(360,160,1000);self.dock_height.setSingleStep(20);self.dock_height.currentIndexChanged.connect(self.resize_dock);form.addRow(tr('编辑器高度'),self.dock_height)
        widget_action=QWidgetAction(menu);widget_action.setDefaultWidget(panel);menu.addAction(widget_action);self.score_options.setMenu(menu);st.addWidget(self.score_options)
        self.score_layout.addLayout(st)
        self.score_splitter=QSplitter(Qt.Orientation.Vertical);self.score_view=ScoreView(self.project,deferred=True);self.score_view.zoomChanged.connect(self.sync_score_zoom);self.score_splitter.addWidget(self.score_view);self.score_layout.addWidget(self.score_splitter,1)
        self.score_view.canvas.layoutChanged.connect(self.sync_score_font)
        self.score_view.canvas.noteSpelling.connect(self.set_spelling);self.score_view.canvas.lineBreak.connect(self.toggle_linebreak);self.score_view.canvas.measureClicked.connect(self.score_bar_clicked)
        self.score_view.canvas.chordSpelling.connect(self.set_chord_spelling)
        self.score_view.canvas.playheadChanged.connect(lambda tick:self.seek(self.roll.snap_time(tick)))
        self.score_view.canvas.pasteRequested.connect(lambda tick:self.note_command(self.roll,'paste',tick))
        self.score_view.canvas.commandRequested.connect(self.score_command)
        self.editor=QFrame();self.editor.setObjectName('editorCard');ed=QVBoxLayout(self.editor);ed.setContentsMargins(1,1,1,1);ed.setSpacing(0)
        tools=row();self.tool=QComboBox()
        for text,value in [(tr('智能工具'),'smart'),(tr('绘制工具'),'draw')]:self.tool.addItem(text,value)
        self.tool.currentIndexChanged.connect(lambda:setattr(self.roll,'tool',self.tool.currentData()));tools.addWidget(self.tool)
        tools.addWidget(QLabel(tr('时值')));self.length=DurationSelector();self.length.currentIndexChanged.connect(self.change_duration);tools.addWidget(self.length)
        self.dotted=self.length.dotted_action
        self.grid=GridSelector();self.grid.currentIndexChanged.connect(self.change_grid)
        self.harmony_button=button(tr('和弦钢琴卷帘'),lambda:self.open_harmony());tools.addWidget(self.harmony_button)
        tools.addStretch();ed.addLayout(tools)
        self.roll=PianoRoll(self.project);ed.addWidget(self.roll,1)
        bottom=row();self.view_controls=RollViewControls(self.roll);tools.addWidget(self.view_controls.options);bottom.addWidget(self.view_controls);bottom.addStretch()
        self.volume_sliders={};self.volume_labels={};self.mute_buttons={}
        for key,name in [('melody',tr('旋律')),('chords',tr('和弦'))]:
            audio_group=QWidget();audio_row=QHBoxLayout(audio_group);audio_row.setContentsMargins(0,0,0,0);audio_row.setSpacing(6)
            label=QLabel(name);audio_row.addWidget(label)
            mute=button(tr('静音'),self.update_audio,True);mute.setToolTip(name+' · '+tr('静音（试听状态，不改变导出 MIDI）'));audio_row.addWidget(mute);self.mute_buttons[key]=mute
            slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(0,127);slider.setFixedWidth(85)
            value=QLabel();value.setFixedWidth(27);slider.setToolTip(tr('轨道音量 CC7，独立于音符力度'))
            slider.valueChanged.connect(lambda volume,k=key:self.change_volume(k,volume));audio_row.addWidget(slider);audio_row.addWidget(value);bottom.addWidget(audio_group)
            self.volume_sliders[key]=slider;self.volume_labels[key]=value
        ed.addLayout(bottom)
        self.compose_layout.addWidget(self.editor)
        self.roll.noteAdded.connect(self.add_note);self.roll.noteMoved.connect(self.move_note);self.roll.noteProperties.connect(self.edit_note);self.roll.noteDeleted.connect(self.delete_note);self.roll.noteSelected.connect(self.note_selected)
        self.roll.chordRequested.connect(self.edit_chord);self.roll.deleteChord.connect(self.delete_chord);self.roll.selectionChanged.connect(self.selection_changed);self.roll.playheadChanged.connect(self.seek);self.roll.audition.connect(self.transport.begin_audition);self.roll.auditionReleased.connect(self.transport.end_audition)
        self.roll.harmonyRequested.connect(self.open_harmony);self.roll.chordMoved.connect(self.move_chord)
        self.roll.chordSelected.connect(self.select_chord);self.roll.notesBatch.connect(lambda a,d:self.edit_notes(self.roll,a,d))
        self.roll.viewChanged.connect(lambda:self.sync_views(self.roll))
        self.roll.markerRequested.connect(self.edit_marker);self.roll.insertMeasureRequested.connect(self.insert_measure);self.roll.playRequested.connect(self.play_from)
        self.roll.contextRequested.connect(self.edit_context)
        self.roll.notesResized.connect(lambda notes:self.edit_notes(self.roll,notes,[],overwrite=True))
        self.roll.commandRequested.connect(lambda command,tick:self.note_command(self.roll,command,tick))
        self.organize_workspace()

    def build_menu(self):
        file=self.menuBar().addMenu(tr('文件'));edit=self.menuBar().addMenu(tr('编辑'))
        self.view_menu=self.visibility_button.menu();self.view_menu.setTitle(tr('视图'));self.menuBar().addMenu(self.view_menu);self.visibility_button.hide()
        def action(menu,text,slot,key=None):
            a=QAction(text,self);a.triggered.connect(slot)
            if key:
                from lingfeng.ui.keybindings import menu_shortcut
                menu_shortcut(a,self,key,popup=False)
            menu.addAction(a);return a
        action(file,tr('新建'),self.new,'new');action(file,tr('打开项目…'),self.open,'open');file.addSeparator();action(file,tr('保存'),self.save,'save');action(file,tr('另存为…'),lambda:self.save(True),'save_as');file.addSeparator()
        self.populate_export_menu(file.addMenu(tr('导出')))
        action(file,tr('恢复上次自动保存'),self.restore_recovery);file.addSeparator();action(file,tr('载入演示练习'),self.load_demo)
        action(edit,tr('撤销'),self.undo,'undo');action(edit,tr('重做'),self.redo,'redo');edit.addSeparator();action(edit,tr('剪切选区'),self.cut_selection,'cut_selection');action(edit,tr('复制选区'),self.copy_selection,'copy_selection');action(edit,tr('粘贴到选区起点'),self.paste_selection,'paste_selection')
        edit.addSeparator();action(edit,tr('导入 MIDI 到旋律…'),lambda:self.import_midi('melody'));action(edit,tr('导入 MIDI 到和弦…'),lambda:self.import_midi('chords'));edit.addSeparator()
        action(edit,tr('作品信息…'),self.project_info)
        self.lyrics_action=action(edit,tr('歌词编辑器…'),self.batch_lyrics);self.lyrics_action.setVisible(self.workspace=='score')
        settings=self.menuBar().addMenu(tr('设置'));action(settings,tr('音源与音色…'),self.sound_settings)
        action(settings,tr('MIDI 键盘输入…'),self.midi_input_settings)
        settings.addSeparator()
        action(settings,tr('和弦菜单偏好…'),self.chord_preferences)
        action(settings,tr('快捷键设置…'),self.keybinding_settings)
        settings.addSeparator()
        themes=settings.addMenu(tr('外观'));group=QActionGroup(self);group.setExclusive(True);self.theme_actions={}
        for label,code in [(tr('浅色'),'light'),(tr('深色'),'dark')]:
            item=action(themes,label,lambda checked=False,c=code:self.set_theme(c,True));item.setCheckable(True);group.addAction(item);self.theme_actions[code]=item
        import lingfeng.ui.theme as theme
        self.note_degrees_action=settings.addAction(tr('显示音符音级数字'));self.note_degrees_action.setCheckable(True);self.note_degrees_action.setChecked(theme.SHOW_NOTE_DEGREES)
        self.note_degrees_action.setToolTip(tr('全局显示或隐藏旋律、和弦卷帘音符上的 1–7 及变化音记号；不改变谱面或 MIDI。'))
        self.note_degrees_action.toggled.connect(self.change_note_degrees)
        self.information_action=settings.addAction(tr('显示底部信息提示'));self.information_action.setCheckable(True);self.information_action.setChecked(self.show_information);self.information_action.toggled.connect(self.change_information)
        ruler=settings.addMenu(tr('和弦轨辅助时间尺'));group=QActionGroup(self);group.setExclusive(True);self.chord_ruler_actions={}
        for title,value in [('关闭',0),('1/4 拍',.25),('1/2 拍',.5),('1 拍',1),('2 拍',2),('1 小节','bar')]:
            item=ruler.addAction(tr(title));item.setCheckable(True);item.setChecked(value==self.chord_ruler_scale);group.addAction(item);self.chord_ruler_actions[value]=item
            item.triggered.connect(lambda checked=False,v=value:self.change_chord_ruler(v))
        ruler.setToolTipsVisible(True)
        for item in ruler.actions():item.setToolTip(tr('仅显示上下对称刻度；吸附仍使用当前窗口的主时间轴格点。'))
        coloring=settings.addMenu(tr('卷帘染色'));self.coloring_actions={}
        for role,title,match in [('melody','旋律卷帘','按和弦音染色'),('harmony','和弦卷帘','按旋律音染色')]:
            sub=coloring.addMenu(tr(title))
            for key,label in [('match',match),('scale','按调内音染色')]:
                item=sub.addAction(tr(label));item.setCheckable(True);item.setChecked(theme.ROLL_COLORING[role][key]);self.coloring_actions[role,key]=item
                item.toggled.connect(lambda value,r=role,k=key:self.change_coloring(r,k,value))
        coloring.addSeparator();action(coloring,tr('自定义色彩方案'),self.color_settings)
        accidentals=settings.addMenu(tr('卷帘升降号偏好'));accidental_group=QActionGroup(self);accidental_group.setExclusive(True)
        for title,value in [('升号 #','sharp'),('降号 b','flat')]:
            item=accidentals.addAction(tr(title));item.setCheckable(True);item.setChecked(theme.ACCIDENTAL_PREFERENCE==value);accidental_group.addAction(item)
            item.triggered.connect(lambda checked=False,v=value:self.change_accidentals(v))
        action(settings,tr('管理和弦进行…'),self.progression_settings)
        languages=settings.addMenu(tr('语言 / Language'));language_group=QActionGroup(self);language_group.setExclusive(True)
        for label,code in [(tr('简体中文'),'zh'),('English','en')]:
            item=action(languages,label,lambda checked=False,c=code:self.change_language(c));item.setCheckable(True);item.setChecked(code==self.language);language_group.addAction(item)
        help_menu=self.menuBar().addMenu(tr('帮助'));action(help_menu,tr('操作说明'),self.help)
        action(help_menu,tr('关于伶风'),lambda:HelpDialog(self,about=True).exec())
        bar=self.menuBar();bar.setSizePolicy(QSizePolicy.Policy.Maximum,QSizePolicy.Policy.Preferred);self.title_bar=TitleBar(self,bar);self.setMenuWidget(self.title_bar)

    def status_message(self,text):
        self.statusBar().showMessage(text,18000)

    def shared_footers(self):
        return (self.audio_footer,self.melody_volume,self.harmony_window.volume_controls,self.score_footer)

    def change_information(self,visible):
        self.show_information=bool(visible)
        for footer in self.shared_footers():footer.set_status(self.statusBar().currentMessage())
        self.save_preferences()

    def change_chord_ruler(self,value):
        self.chord_ruler_scale=value
        for scale,action in self.chord_ruler_actions.items():action.setChecked(scale==value)
        for lane in (self.chord_lane,self.roll.lane,self.harmony_window.roll.lane):lane.aux_ruler_scale=value;lane.update()
        self.save_preferences()

    def mutate(self,label,operation,keep_playing=True,recording=False,source=None,preserve_chord_move=False,score_spellings=False):
        location=self.history_location(source)
        if score_spellings:location['score_spellings']=True
        self.commit_volume()
        if not keep_playing:self.stop(preserve_auditions=True)
        before=HistoryState(self.project.to_dict(),location);trial=Project.from_dict(before)
        try:
            operation(trial);trial.fill_chord_gaps();trial.rescan_changed_harmony(before);trial.validate()
        except (ValueError,TypeError,KeyError) as exc:
            QMessageBox.warning(self,label,tr(str(exc)));return False
        session=getattr(self,'chord_move_session',None)
        if session and not preserve_chord_move:
            selected=lambda p:[c for c in p.chords if c.id in session.ids]
            if trial.measures!=self.project.measures or selected(trial)!=selected(self.project):self.clear_chord_move_session()
        self.undo_history.append(before);self.undo_history=self.undo_history[-100:];self.redo_history.clear()
        playing=self.transport.playing;tick=self.transport.position() if playing else self.playhead
        self.project=trial;self.dirty=True
        if recording:self.transport.refresh_recording(trial)
        elif playing:self.transport.revise(trial)
        self.refresh(score_spellings=score_spellings)
        if playing and not self.transport.playing:self.resume_edited_playback(tick)
        self.status_message(label);return True

    def resume_edited_playback(self,tick):
        tick=max(0,min(int(tick),self.project.end-1))
        a,b=self.loop_bounds()
        loop=self.loop_active() and a<=tick<b
        self.transport.play(self.project,tick,b if loop else self.project.end,loop,volumes=self.effective_volumes(),loop_start=a)
        self.transport_active=True;self.show_cursor(tick);self.update_transport_buttons()

    def refresh(self,score_spellings=False):
        self.loading=True
        self.subtitle.setText(self.project.title+(tr('  ·  未保存') if self.dirty else tr('  ·  本地项目')))
        self.setWindowTitle(f"{self.project.title}{' *' if self.dirty else ''} — {'Lingfeng' if self.language=='en' else '伶风'}")
        self.bpm.setValue(self.project.bpm)
        for key,slider in self.volume_sliders.items():
            slider.setValue(self.project.volumes[key]);self.volume_labels[key].setText(str(self.project.volumes[key]))
        try:self.update_audio()
        except RuntimeError as exc:self.status_message(tr(str(exc)))
        if getattr(self,'workspace_ready',False):self.main_roll.set_project(self.project)
        self.roll.set_project(self.project)
        if self.workspace=='score':self.score_view.canvas.sync_presentation(self.project,score_spellings)
        self.score_style.setCurrentIndex(self.score_style.findData(self.project.notation['style']));self.perline.setCurrentIndex(self.perline.findData(self.project.notation['per_line']))
        self.rowgap.setValue(self.project.notation['row_gap']);self.system_gap.setValue(self.project.notation.get('system_gap',12));self.circle.setChecked(self.project.notation['circles']);self.chromatic.setChecked(self.project.notation['color']);self.showlyrics.setChecked(self.project.notation['lyrics']);self.scale_lines.setChecked(self.project.notation.get('show_scale_lines',False));self.note_font.setValue(self.project.notation.get('font_size',15))
        self.compose_button.setChecked(self.workspace=='compose');self.score_button.setChecked(self.workspace=='score')
        self.rowgap.setEnabled(self.project.notation['style']!='traditional');self.rowgap.setToolTip(tr('控制立体与紧凑简谱的音高行距离；传统简谱不按音高分行。'))
        self.loading=False;self.selection_changed(self.roll.selection)
        if self.harmony_window:self.harmony_window.refresh()
        if self.loop_range and self.loop_range[1]>self.project.end:
            self.loop_range=(self.loop_range[0],self.project.end) if self.loop_range[0]<self.project.end else None
            self.sync_loop_range();self.change_loop(self.loop.isChecked())
        if getattr(self,'workspace_ready',False):self.logic_panel.refresh();self.lyric_panel.refresh();self.sync_views(self.roll);self.update_shared_views();self.update_transport_buttons()

    def switch_workspace(self,workspace,refresh_score=True):
        if workspace==self.workspace:return True
        self.switching_workspace=True
        if workspace=='score':
            if self.project.notation.get('font_layout_version')!=45:self.prepare_score_font()
            self.compose_float_state=(self.melody_window.isFloating(),self.harmony_window.isFloating())
            self.compose_view_state={key:self.visibility_actions[key].isChecked() for key in ('melody','harmony','chords')}
            self.compose_float_open=(self.melody_window.floating_visible,self.harmony_window.floating_visible)
            self.melody_window.setFloating(False);self.harmony_window.setFloating(False)
        self.workspace=workspace;self.score_view.canvas.suspended=workspace!='score'
        self.stack.setCurrentWidget(self.compose if workspace=='compose' else self.score_page)
        if workspace=='score' and refresh_score:self.score_view.canvas.rebuild(self.project)
        if workspace=='score':self.sync_score_font();self.show_cursor(self.playhead)
        self.lyrics_action.setVisible(workspace=='score')
        self.compose_button.setChecked(workspace=='compose');self.score_button.setChecked(workspace=='score')
        if workspace=='compose':
            self.melody_window.setFloating(self.compose_float_state[0]);self.harmony_window.setFloating(self.compose_float_state[1])
            for pane,visible in zip((self.melody_window,self.harmony_window),getattr(self,'compose_float_open',(True,True))):pane.floating_visible=visible
            for key,value in getattr(self,'compose_view_state',{}).items():
                action=self.visibility_actions[key];blocked=action.blockSignals(True);action.setChecked(value);action.blockSignals(blocked)
        self.switching_workspace=False
        self.mount_panels();self.roll.update_ranges();self.harmony_window.roll.update_ranges()
        if workspace=='score':self.status_message(tr('谱面：拖动框选 · Ctrl 增选 · Shift 连续选择 · 右键打开对应卷帘；结构逻辑中记录 A、B 区域。'))
        else:self.status_message(tr('Smart：空白拖动框选 · Draw：单击写入或删除，拖动编辑 · 右键复制变换'))
        return True

    def change_score_zoom(self):
        if not hasattr(self,'score_view'):return
        choice=self.score_zoom.currentData()
        if choice in ('width','page'):self.score_view.fit_zoom(choice)
        elif isinstance(choice,(int,float)):self.score_view.set_zoom(choice)

    def sync_score_font(self):
        canvas=self.score_view.canvas
        if self.workspace!='score' or canvas.layout is None:return
        limit=canvas.layout.font_limit;value=canvas.project.notation['font_size']
        if self.project.notation.get('font_size',15)!=value:
            self.project.notation['font_size']=value;self.dirty=True
            self.subtitle.setText(self.project.title+tr('  ·  未保存'))
            self.setWindowTitle(f"{self.project.title} * — {'Lingfeng' if self.language=='en' else '伶风'}")
        blocked=self.note_font.blockSignals(True)
        try:
            self.note_font.setMaximum(limit);self.note_font.setSingleStep(1 if limit>=1 else .01 if limit>=.01 else .0001)
            self.note_font.setValue(value)
        finally:self.note_font.blockSignals(blocked)
        self.font_limit_label.setText(tr('上限 {0}',f'{limit:g}'))
        tip=tr('当前排版的字号上限为 {0}；保持每行小节数，不允许重叠。调整排版后重新计算上限，强制合行仍按比例缩小。',f'{limit:g}')
        self.note_font.setToolTip(tip);self.font_limit_label.setToolTip(tip)

    def sync_score_zoom(self,scale,mode):
        combo=self.score_zoom;blocked=combo.blockSignals(True)
        try:
            index=combo.findData(mode if mode!='manual' else scale)
            if index<0:
                index=combo.findData('custom')
                if index<0:combo.addItem('', 'custom');index=combo.count()-1
                combo.setItemText(index,f'{scale*100:.0f}%')
            combo.setCurrentIndex(index)
        finally:combo.blockSignals(blocked)

    def locate_score_measure(self,bar,roll):
        if self.workspace!='score' or self.score_panel_state['harmony' if roll is self.harmony_window.roll else 'melody']['floating'] or not roll.isVisible():return
        if not self.score_view.locate_bar(bar):
            self.status_message(tr('该小节尚未生成谱面；重新切入制谱模式后更新。'))

    def score_font_project(self,project):
        if self.workspace!='score' or self.score_view.canvas.layout is None:return project
        snapshot=copy.deepcopy(self.score_view.canvas.project)
        for key in ('style','per_line','font_size','row_gap','circles','color','lyrics'):snapshot.notation[key]=project.notation[key]
        return snapshot

    def change_volume(self,key,value):
        if self.loading:return
        # Live CC7: moving a volume control does not stop the transport.
        if self.volume_before is None:self.volume_before=HistoryState(self.project.to_dict(),self.history_location())
        self.volume_timer.start()
        self.project.volumes[key]=value;self.dirty=True;self.volume_labels[key].setText(str(value))
        self.subtitle.setText(self.project.title+tr('  ·  未保存'))
        try:self.update_audio()
        except RuntimeError as exc:self.status_message(tr(str(exc)))

    def commit_volume(self):
        if self.volume_before is not None:
            self.undo_history.append(self.volume_before);self.undo_history=self.undo_history[-100:];self.redo_history.clear();self.volume_before=None
        self.volume_timer.stop()

    def open_harmony(self,cid='',tick=None):
        chord=next((c for c in self.project.chords if c.id==cid),None)
        locate_requested=chord is not None or tick is not None
        tick=chord.start if chord else self.playhead if tick is None else tick
        if self.workspace=='score':
            self.show_score_panel('harmony')
        else:self.show_roll_in_place(self.harmony_window)
        pane=self.score_floats['harmony'] if self.workspace=='score' else self.harmony_window
        if pane.isFloating():
            if pane.isMinimized():pane.showNormal()
            pane.raise_();pane.activateWindow()
        roll=self.harmony_window.roll
        restoring=getattr(self,'restoring_layout',False)
        if chord:
            if restoring:self.harmony_window.select_chord(chord.id,False,False)
            else:self.chord_selection({chord.id},roll)
        self.sync_views(roll)
        if not locate_requested or restoring:roll.setFocus();return
        def locate():
            if chord and self.harmony_window.current_id!=chord.id:return
            roll.ensure_tick(tick);roll.center_pitch(self.harmony_window.initial_pitch());roll.setFocus();self.cancel_follow(roll)
        locate();QTimer.singleShot(0,self,locate)

    def select_chord(self,cid):
        self.roll.selected_chord=cid
        if self.harmony_window and not (self.workspace=='compose' and self.harmony_window.isFloating()):self.harmony_window.select_chord(cid,False)
        self.roll.refresh();self.update_shared_views()

    def sync_views(self,source):
        if self.syncing_views or not getattr(self,'workspace_ready',False):return
        linked=self.rolls_linked();self.syncing_views=True
        try:
            target=self.harmony_window.roll if source is self.roll else self.roll
            old_compact=target.compact;target_center=target.pitch_at(target.ruler_height+max(1,target.viewport().height()-target.ruler_height)/2)
            pitches={n.pitch for n in self.project.notes+self.project.harmony_notes()} if linked else None
            for roll in (self.roll,self.harmony_window.roll):roll.shared_pitches=pitches
            if linked:
                target.compact=source.compact
                if target.row_height!=source.row_height:target.set_row_height(source.row_height)
                for controls in (self.view_controls,self.harmony_window.view_controls):
                    controls.range.blockSignals(True);controls.range.setCurrentIndex(int(source.compact));controls.range.blockSignals(False)
                    controls.height.blockSignals(True);controls.height.setValue(source.row_height);controls.height.blockSignals(False)
            source.update_ranges();target.update_ranges()
            if linked and target.compact!=old_compact:
                pitches=sorted({n.pitch for n in target.notes})
                target.center_pitch(pitches[len(pitches)//2] if pitches else target_center)
            target.refresh();source.refresh()
        finally:self.syncing_views=False
        self.update_shared_views()

    def change_chord_structure(self,chord):
        from lingfeng.music.note_operations import repartition_chord
        self.mutate(tr('已调整和弦结构范围'),lambda p:repartition_chord(p,chord.id,chord.start,chord.end))

    def move_chord(self,chord):
        self.mutate(tr('已移动／调整和弦区间，节奏型已更新'),lambda p:p.put_chord(chord))

    def edit_notes(self,roll,added,deleted,overwrite=True):
        # Every incoming note owns its time on its pitch: create, move, resize and paste.
        selected_ids=set()
        def op(p):
            incoming=copy.deepcopy(added)
            if overwrite and roll.role=='melody':
                from lingfeng.engraving.lyrics import detach
                detach(p)
                for n in incoming:n.lyric=''
            if roll.role=='harmony':
                from lingfeng.music.note_operations import overwrite_note
                remove=set(deleted)|{n.id for n in incoming}
                notes=[n for n in p.harmony_notes() if n.id not in remove]
                for n in incoming:
                    notes=overwrite_note(n,notes) if overwrite else notes+[n]
                    selected_ids.add(n.id)
                p.set_harmony_notes(notes)
            else:
                ids=set(deleted)|{n.id for n in incoming};p.notes=[n for n in p.notes if n.id not in ids]
                for n in incoming:p.add_note(n,overwrite=overwrite);selected_ids.add(n.id)
        success=self.mutate(tr('已编辑音符'),op,source=roll)
        if success and added:
            roll.selected_ids=roll.expand_note_selection(selected_ids&{n.id for n in roll.notes});roll.selected_note=next(iter(roll.selected_ids),'');roll.refresh()
            current=next((n for n in roll.notes if n.id==added[0].id),None)
            if current:roll.remember_duration(current)
        return success

    def active_roll(self):
        focus=QApplication.focusWidget()
        surface=self.edit_surface(focus)
        if surface=='chords':return self.chord_lane.editor
        if surface=='melody':return self.roll
        if surface=='harmony':return self.harmony_window.roll
        if self.workspace=='score':return self.harmony_window.roll if self.current_score_panel()=='harmony' else self.roll
        if self.workspace=='compose' and not self.visibility_actions['melody'].isChecked() and self.visibility_actions['harmony'].isChecked():return self.harmony_window.roll
        if self.harmony_window and ((self.harmony_window.isFloating() and self.harmony_window.isActiveWindow()) or (focus and self.harmony_window.isAncestorOf(focus))):return self.harmony_window.roll
        if getattr(self,'last_main_surface',None)=='harmony' and not self.harmony_window.isFloating() and self.visibility_actions['harmony'].isChecked():return self.harmony_window.roll
        return self.roll

    def keybinding_settings(self):
        from lingfeng.ui.keybindings import KeyBindingsDialog
        dialog=KeyBindingsDialog(self.keybindings,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.keybindings=dialog.value();self.save_preferences();self.update_shortcuts();self.update_transport_buttons()

    def update_shortcuts(self):
        from lingfeng.ui.keybindings import menu_shortcut
        for action in self.findChildren(QAction):
            command=action.property('shortcutCommand')
            if command:menu_shortcut(action,self,command,popup=bool(action.property('shortcutPopup')))

    def editor_key_command(self,command):
        roll=self.active_roll();chords=getattr(roll,'edit_target','notes')=='chords'
        if command in ('view_left','view_right'):
            bar=roll.horizontalScrollBar()
            bar.setValue(bar.value()+bar.singleStep()*(1 if command=='view_right' else -1));self.cancel_follow(roll);return
        if command=='grid_triplet':
            controls=self.harmony_window if roll is self.harmony_window.roll else self
            controls.grid.set_triplet(not controls.grid.triplet);return
        if command=='switch_input':self.switch_input_roll(roll);return
        if command=='toggle_tool':
            current=self.harmony_window.tool if roll is self.harmony_window.roll else self.tool
            command='draw' if current.currentData()=='smart' else 'smart'
        if command=='play':self.toggle_play();return
        if command=='replay':self.replay();return
        if command=='edit_chord':
            if chords and len(roll.selected_chords)==1:
                cid=next(iter(roll.selected_chords));self.edit_chord(cid,self.playhead)
            return
        if command=='beginning':self.return_to_start();return
        if command in ('smart','draw'):
            controls=self.harmony_window if roll is self.harmony_window.roll else self
            controls.tool.setCurrentIndex(controls.tool.findData(command));return
        if command in ('left','right'):
            selected=self.chord_selection_extents(roll) if chords else roll.selected_notes()
            if not selected:return
            start=max(0,min(self.project.end-1,min(n.start for n in selected)));a,b=roll.bucket(start)
            delta=((b if command=='right' else a if start>a else roll.bucket(max(0,a-1))[0])-start) if not chords else (b-a)*(1 if command=='right' else -1)
            if chords:self.chord_command('move:'+str(delta),set(roll.selected_chords),roll)
            else:
                notes=copy.deepcopy(selected)
                for n in notes:n.start+=delta
                if self.edit_notes(roll,notes,[]):
                    roll.ensure_selection_visible(dx=delta)
                    if len(notes)==1:roll.audition.emit([notes[0].pitch]);roll.auditionReleased.emit()
            return
        if chords:
            if command in ('up','down') and roll.selected_chords:
                if all(c.recognized for c in self.project.chords if c.id in roll.selected_chords):self.chord_command('root_step:'+str(1 if command=='up' else -1),set(roll.selected_chords),roll)
                else:self.status_message(tr('更换根音要求所选和弦属性均可识别。'))
            elif command in ('scale_up','scale_down') and roll.selected_chords:
                from lingfeng.music.chord_operations import can_move_diatonic
                steps=1 if command in ('up','scale_up') else -1
                selected=[c for c in self.project.chords if c.id in roll.selected_chords]
                if can_move_diatonic(self.project,selected,steps):self.chord_command('diatonic:'+str(steps),set(roll.selected_chords),roll)
                else:self.status_message(tr('调内移动要求和弦属性可识别，且全部和弦音都在当前调式内。'))
            elif command in ('split','merge','delete') and roll.selected_chords:self.chord_command(command,set(roll.selected_chords),roll)
        elif command=='delete':
            if roll.selected_ids:self.edit_notes(roll,[],list(roll.selected_ids))
        else:self.note_command(roll,{'merge':'join','up':'chromatic:1','down':'chromatic:-1','scale_up':'up','scale_down':'down','octave_up':'chromatic:12','octave_down':'chromatic:-12'}.get(command,command))

    def switch_input_roll(self,source):
        target=self.roll if source is self.harmony_window.roll else self.harmony_window.roll
        role='melody' if target is self.roll else 'chords'
        if self.workspace=='score':
            key='melody' if role=='melody' else 'harmony';self.show_score_panel(key)
            pane=self.score_floats[key]
        else:
            pane=self.melody_window if role=='melody' else self.harmony_window
            self.show_roll_in_place(pane)
        if pane.isMinimized():pane.showNormal()
        window=pane if pane.isFloating() else self
        window.raise_();window.activateWindow();target.edit_target='notes';target.setFocus()
        self.midi_input.target=role

    def note_command(self,roll,command,tick=0):
        notes=roll.selected_notes()
        if command=='quantize':self.quantize(roll);return
        if command.startswith('copy:'):
            try:self.note_clipboard=NoteClipboard.capture(notes,self.project,command.split(':')[1])
            except ValueError as exc:QMessageBox.warning(self,tr('音符操作'),str(exc));return
            self.clipboard_kind='notes'
            for editor in [self.roll]+([self.harmony_window.roll] if self.harmony_window else []):editor.has_note_clipboard=self.note_clipboard is not None
            self.score_view.canvas.has_note_clipboard=self.note_clipboard is not None
            self.status_message(tr('已复制 {0} 个音符；在目标位置右键粘贴，或定位后按 Ctrl+V。', len(notes)));return
        try:
            if command=='paste':
                if not self.note_clipboard:return
                added=self.note_clipboard.paste(self.project,tick)
                self.edit_notes(roll,added,[],overwrite=True);return
            if not notes:return
            if command.startswith('chromatic:'):
                added=copy.deepcopy(notes)
                for n in added:n.pitch+=int(command.split(':')[1])
                if any(not 21<=n.pitch<=108 for n in added):raise ValueError(tr('变换后的音符超出 88 键范围。'))
            elif command in ('up','down'):added=shift_in_scale(notes,self.project,1 if command=='up' else -1)
            elif command=='join':added=join_notes(notes)
            elif command=='split':added=split_notes(notes,roll.grid)
            else:return
            if self.edit_notes(roll,added,[n.id for n in notes]):
                if command.startswith('chromatic:'):roll.ensure_selection_visible(dy=int(command.split(':')[1]))
                elif command in ('up','down'):roll.ensure_selection_visible(dy=1 if command=='up' else -1)
                if len(added)==1 and (command.startswith('chromatic:') or command in ('up','down')):
                    roll.audition.emit([added[0].pitch]);roll.auditionReleased.emit()
        except ValueError as exc:QMessageBox.warning(self,tr('音符操作'),tr(str(exc)))

    def quantize(self,roll):
        selected=roll.selected_notes()
        if not selected:return
        added=[]
        for original in selected:
            n=copy.deepcopy(original);n.start=max(0,min(self.project.end-n.duration,roll.snap_time(n.start)))
            added.append(n)
        self.edit_notes(roll,added,[])

    def toggle_editor(self):
        # Compatibility for older automation; panels are now controlled by View.
        self.score_view.canvas.editing=True;self.mount_panels();self.resize_score()

    def selection_changed(self,ranges):
        self.roll.selection=copy.deepcopy(ranges)
        if getattr(self,'workspace_ready',False):
            self.main_roll.selection=copy.deepcopy(ranges);self.main_roll.refresh()
            self.harmony_window.roll.selection=copy.deepcopy(ranges);self.harmony_window.roll.refresh()
        self.roll.refresh()

    def edit_context(self,ranges):
        from lingfeng.music.timing import selected_measures
        parent,origin=self.edit_dialog_origin()
        bars=selected_measures(self.project,ranges)
        if not bars:return
        def select_bars():
            ranges=[self.project.starts[i:i+2] for i in bars]
            for roll in (self.roll,self.harmony_window.roll):roll.selection=copy.deepcopy(ranges);roll.refresh()
            self.update_shared_views()
        select_bars()
        dialog=MarkerDialog(self.project,bars[0],parent,bars=bars)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            values=dialog.value()
            if not self.confirm_meter_trim(bars,values['numerator'],values['denominator'],parent):
                self.restore_dialog_origin(parent,origin);return
            if self.mutate(tr('已将拍号与调性应用到所选小节'),lambda p:p.set_markers(bars,**values,allow_trim=True),source=origin):
                select_bars()
        self.restore_dialog_origin(parent,origin)

    def confirm_meter_trim(self,bars,numerator,denominator,parent=None):
        from lingfeng.music.meter import losses
        melody,chords,rap=losses(self.project,bars,numerator,denominator)
        if not any((melody,chords,rap)):return True
        message=tr('缩短小节将删除或截断 {0} 个旋律音符、{1} 个和弦音符及 {2} 个说唱节奏事件，并裁切和弦区间、重新识别节奏型。是否继续？此操作可以撤销。',melody,chords,rap)
        return QMessageBox.question(parent or self,tr('确认缩短小节'),message,QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)==QMessageBox.StandardButton.Yes

    def propagate_marker(self,index,kind):
        parent,origin=self.edit_dialog_origin()
        label=tr('已将本小节调性应用至后续所有小节') if kind=='key' else tr('已将本小节拍号应用至后续所有小节')
        if kind=='meter':
            m=self.project.measures[index]
            if not self.confirm_meter_trim(range(index+1,len(self.project.measures)),m.numerator,m.denominator,parent):
                self.restore_dialog_origin(parent,origin);return
        if self.mutate(label,lambda p:p.propagate_marker(index,kind,allow_trim=True),source=origin):
            self.selection_changed([self.project.starts[index:index+2]]);self.update_shared_views()
        self.restore_dialog_origin(parent,origin)

    def zoom(self,delta):self.roll.zoom_at(1.2**(delta/12));self.roll.navigationRequested.emit()

    def change_grid(self):
        self.roll.grid=self.grid.currentData();self.roll.grid_bars=self.grid.bars;self.score_view.canvas.grid=self.roll.grid;self.score_view.canvas.grid_bars=self.roll.grid_bars
        self.roll.refresh();self.sync_grid_views(self.roll);self.update_shared_views()

    def change_duration(self):
        self.roll.duration=self.length.currentData();self.roll.duration_bars=self.length.bars

    def add_note(self,note):
        self.edit_notes(self.roll,[note],[])

    def move_note(self,note):self.edit_notes(self.roll,[note],[])

    def edit_note(self,nid):
        note=next((n for n in self.project.notes if n.id==nid),None)
        if not note:return
        dialog=NoteDialog(note,self.project,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            changed=dialog.value();changed.lyric=note.lyric;self.move_note(changed)

    def delete_note(self,nid):self.mutate(tr('已删除音符'),lambda p:setattr(p,'notes',[n for n in p.notes if n.id!=nid]),source=self.roll)

    def note_selected(self,nid):
        n=next(n for n in self.project.notes if n.id==nid);self.status_message(tr('{0} · {1:g} 拍 · 右键编辑属性', pitch_name(n.pitch), n.duration / PPQ))

    def edit_chord(self,cid,tick):
        parent,origin=self.edit_dialog_origin()
        chord=next((c for c in self.project.chords if c.id==cid),None)
        if chord is None:
            self.chord_command('insert',max(0,min(self.project.end-1,self.roll.snap_time(tick))));return
        dialog=ChordDialog(chord,self.project,parent,defaults=self.chord_edit_options)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            new=dialog.value()
            if self.mutate(tr('已更新和弦'),lambda p:p.put_chord(new),source=origin):
                self.chord_edit_options=dialog.options();self.save_preferences();self.transport.audition(new.pitches,True)
        self.restore_dialog_origin(parent,origin)

    def delete_chord(self,cid):self.mutate(tr('已删除和弦'),lambda p:setattr(p,'chords',[c for c in p.chords if c.id!=cid]))

    def set_spelling(self,nid,flat):
        if not any(n.id==nid for n in self.project.notes):return
        def op(p):next(n for n in p.notes if n.id==nid).flat=flat
        self.mutate(tr('已切换谱面等音写法；创作区仍统一显示升号'),op,score_spellings=True)

    def set_chord_spelling(self,cid,flat):
        if not any(c.id==cid for c in self.project.chords):return
        def op(p):next(c for c in p.chords if c.id==cid).flat=flat
        self.mutate(tr('已切换谱面和弦的等音写法'),op,score_spellings=True)

    def set_notation(self,key,value):
        if not self.loading:
            def op(p):
                p.notation[key]=value
                if key=='style':p.notation['font_size']=ScoreLayout(self.score_font_project(p)).recommended_font_size
                p.notation['font_layout_version']=45
            self.mutate(tr('已更新谱面排版'),op,source='score')

    def prepare_score_font(self):
        # Initial engraving is part of entering score mode, not an extra undo
        # step above the user's last music edit. The result persists in the file.
        self.project.notation.update(font_size=ScoreLayout(self.project).recommended_font_size,font_layout_version=45)
        self.dirty=True;self.refresh()

    def recommend_score_font(self):
        if not self.loading:
            def op(p):p.notation.update(font_size=ScoreLayout(self.score_font_project(p)).recommended_font_size,font_layout_version=45)
            self.mutate(tr('已设置推荐字号'),op,source='score')

    def toggle_linebreak(self,bar):
        if not self.score_structure_current():return
        def op(p):p.measures[bar].break_after=not p.measures[bar].break_after
        self.mutate(tr('已更新换行'),op)

    def score_bar_clicked(self,bar):
        if not 0<=bar<len(self.project.measures):return
        self.roll.selection=[self.project.starts[bar:bar+2]];self.selection_changed(self.roll.selection);self.roll.ensure_tick(self.project.starts[bar]);self.roll.refresh()

    def batch_lyrics(self):
        if self.workspace!='score' and not self.switch_workspace('score'):return
        self.show_score_panel('lyrics')
        self.lyric_panel.open_editor()

    def append_measure(self):self.insert_measure(len(self.project.measures))

    def set_section(self,bars=None,name=None):
        from lingfeng.music.model import SECTIONS, section_name
        if bars is None:
            from lingfeng.music.timing import selected_measures
            bars=selected_measures(self.project,self.active_roll().selection) or [self.project.measure_at(self.playhead)]
        if name is None:
            choices=[tr('移除段落标识'),*SECTIONS]
            name,ok=QInputDialog.getItem(self,tr('段落标识'),tr('每个所选小节开始一个新段落；同名标识仍分段。'),choices,0,False)
            if not ok:return
            if name==choices[0]:name=''
        name=section_name(name)
        self.mutate(tr('已设置段落标记'),lambda p:[setattr(p.measures[i],'section',name) for i in bars])

    def project_info(self):
        title,ok=QInputDialog.getText(self,tr('作品信息'),tr('标题：'),text=self.project.title)
        if ok:self.mutate(tr('已更新标题'),lambda p:setattr(p,'title',title.strip() or tr('未命名作品')))

    def set_bpm(self,value):
        if not self.loading:self.mutate(tr('已更新速度'),lambda p:setattr(p,'bpm',value))

    def copy_selection(self):
        roll=self.active_roll()
        if getattr(roll,'edit_target','notes')=='chords' and roll.selected_chords:self.chord_command('copy',set(roll.selected_chords),roll);return
        if roll.selected_ids:self.note_command(roll,'copy:direct');return
        self.clipboard_kind='range'
        self.note_clipboard=None;self.roll.has_note_clipboard=False;self.score_view.canvas.has_note_clipboard=False
        if self.harmony_window:self.harmony_window.roll.has_note_clipboard=False
        ranges=self.roll.selection
        if not ranges:return
        anchor=ranges[0][0];limit=ranges[-1][1]
        notes=[];chords=[];chord_meters=[]
        for a,b in ranges:
            for event in self.project.notes:
                if event.start<b and event.end>a:
                    n=copy.deepcopy(event);n.start=max(event.start,a)-anchor;n.duration=min(event.end,b)-max(event.start,a);n.id=uid();notes.append(n)
            for event in self.project.chords:
                if event.start<b and event.end>a:
                    from lingfeng.music.meter import signature
                    chord_meters.append(signature(self.project,event.start));c=event.clip(max(event.start,a),min(event.end,b));c.start-=anchor;chords.append(c)
        self.clipboard_meters=chord_meters
        self.clipboard=(notes,chords,limit-anchor);self.status_message(tr('已复制 {0} 个音符与 {1} 个和弦；在目标选区按 Ctrl+V', len(notes), len(chords)))

    def cut_selection(self):
        roll=self.active_roll()
        if roll.edit_target=='chords' and roll.selected_chords:
            ids=set(roll.selected_chords);self.copy_selection();self.chord_command('delete',ids,roll)
        elif roll.selected_ids:
            ids=list(roll.selected_ids);self.copy_selection();self.edit_notes(roll,[],ids)

    def select_all(self):
        if self.edit_surface(QApplication.focusWidget())=='score':
            canvas=self.score_view.canvas;canvas.selected_units().update(key for _,_,key in canvas.selection_rects());canvas.update();canvas.selectionChanged.emit();return
        roll=self.active_roll()
        if roll.edit_target=='chords':self.chord_selection({c.id for c in self.project.chords},roll)
        else:
            self.select_element('notes',roll);roll.selected_ids={n.id for n in roll.notes};roll.selected_note=next(iter(roll.selected_ids),'');roll.refresh()

    def paste_selection(self):
        if self.clipboard_kind=='chords':
            roll=self.active_roll();self.chord_command('paste',roll.position_tick(),roll);return
        if self.note_clipboard and self.clipboard_kind in ('notes',None):
            roll=self.active_roll();self.note_command(roll,'paste',roll.position_tick());return
        if not self.clipboard:return
        notes,chords,length=self.clipboard;start=self.roll.selection[0][0]
        if start+length>self.project.end:QMessageBox.warning(self,tr('粘贴'),tr('项目长度不够，请先增加小节。'));return
        from lingfeng.music.chord_operations import ChordClipboard
        for c,meter in zip(chords,getattr(self,'clipboard_meters',[(4,4)]*len(chords))):
            if not ChordClipboard([c],(meter,)).can_paste(self.project,start+c.start):self.status_message(tr('粘贴范围必须完整位于匹配的拍号区间内。'));return
        def op(p):
            from lingfeng.engraving.lyrics import detach
            detach(p)
            for old in notes:
                n=copy.deepcopy(old);n.id=uid();n.start+=start;n.lyric='';p.add_note(n,overwrite=True)
            for old in chords:
                c=copy.deepcopy(old);c.id=uid();c.start+=start
                if c.notes is not None:
                    for n in c.notes:n.id=uid()
                p.put_chord(c)
        self.mutate(tr('已粘贴选区'),op)

    def undo(self):
        self.restore_history(self.undo_history,self.redo_history)

    def redo(self):
        self.restore_history(self.redo_history,self.undo_history)

    def save_preferences(self):
        from lingfeng.ui.theme import CUSTOM_PALETTES, ROLL_COLORING, SHOW_NOTE_DEGREES, ACCIDENTAL_PREFERENCE
        from lingfeng.music.chord_operations import QUALITY_ORDER
        from lingfeng.music.progression_catalog import CATALOG_VERSION
        try:
            from lingfeng.platform.preferences import save_preferences
            self._preferences=save_preferences(user_data_dir(),{'theme':'dark' if is_dark() else 'light','language':self.language,'colors':CUSTOM_PALETTES,'roll_coloring':ROLL_COLORING,'show_note_degrees':SHOW_NOTE_DEGREES,'show_information':self.show_information,'chord_ruler_scale':self.chord_ruler_scale,'chord_order':QUALITY_ORDER,'chord_edit_options':self.chord_edit_options,'keybindings':self.keybindings,'last_project_dir':self.last_project_dir,'progression_presets':self.progression_presets,'progression_catalog_version':CATALOG_VERSION,'accidental_preference':ACCIDENTAL_PREFERENCE},getattr(self,'_preferences',{}))
        except OSError as exc:self.status_message(tr('偏好设置未保存：{0}',exc))

    def change_language(self,language,persist=True):
        if self.language==language:return
        workspace=self.workspace;editing=self.edit_toggle.isChecked();theme='dark' if is_dark() else 'light'
        session=dict(mutes={k:b.isChecked() for k,b in self.mute_buttons.items()},loop=self.loop.isChecked(),follow=self.follow_playhead.isChecked(),dock_height=self.dock_height.currentData())
        session.update(visibility={k:a.isChecked() for k,a in self.visibility_actions.items()},melody_float=self.melody_window.isFloating(),score_float=self.score_tools.isFloating(),tab=self.score_tabs.currentIndex(),logic=self.logic_panel.export_state(),track_sizes=self.tracks.sizes())
        session['timeline_views']=[dict(zoom=r.zoom,scroll=r.horizontalScrollBar().value(),grid=r.grid,grid_bars=r.grid_bars,height=r.row_height,compact=r.compact) for r in (self.main_roll,self.roll,self.harmony_window.roll)]
        session['timeline_sync']=(self.melody_sync.isChecked(),self.harmony_window.sync.isChecked());session['view_follow']=(self.melody_transport.follow.isChecked(),self.harmony_window.transport_controls.follow.isChecked());session['compose_floats']=self.compose_float_state
        session['float_open']=(self.melody_window.floating_visible,self.harmony_window.floating_visible)
        session['compose_view_state']=getattr(self,'compose_view_state',None);session['compose_float_open']=getattr(self,'compose_float_open',None)
        session['score_panels']=copy.deepcopy(self.score_panel_state);session['score_active']=self.current_score_panel();session['score_geometry']={k:p.saveGeometry() for k,p in self.score_floats.items()}
        session['lyric_draft']=self.lyric_panel.export_state()
        session['floating_melody_chords']=self.floating_melody_chords
        session['chord_velocity']=[lane.velocity_visible for lane in (self.chord_lane,self.roll.lane,self.harmony_window.roll.lane)]
        harmony=self.harmony_window.roll;session['harmony_tools']=(self.harmony_window.grid.currentIndex(),self.harmony_window.grid.triplet,self.harmony_window.length.currentIndex(),self.harmony_window.length.triplet,self.harmony_window.dotted.isChecked(),harmony.previous_duration,harmony.previous_note_id);session['harmony_pitch']=harmony.pitch_at(harmony.ruler_height+max(1,harmony.viewport().height()-harmony.ruler_height)/2)
        canvas=self.score_view.canvas;session['score_selection']=(canvas.selection_unit,set(canvas.selected_bars),set(canvas.selected_beats),canvas.selection_anchor)
        session['score_snapshot']=(canvas.project,canvas.layout)
        session['score_view']=(self.score_view.zoom_mode,canvas.scale,self.score_view.horizontalScrollBar().value(),self.score_view.verticalScrollBar().value())
        roll=self.roll;view=dict(compact=roll.compact,height=roll.row_height,zoom=roll.zoom,panels=dict(roll.panels),selected=set(roll.selected_ids),selection=copy.deepcopy(roll.selection),tool=roll.tool,grid=self.grid.currentIndex(),triplet=self.grid.triplet,length=self.length.currentIndex(),dotted=self.dotted.isChecked(),length_triplet=self.length.triplet,previous=roll.previous_duration,previous_id=roll.previous_note_id,scroll=roll.horizontalScrollBar().value(),pitch=roll.pitch_at(roll.ruler_height+max(1,roll.viewport().height()-roll.ruler_height)/2))
        dock=None
        self.workspace_ready=False
        # Transfer Qt's focus chain before retiring peer windows. A focused
        # editor pending deleteLater must not remain the active focus object
        # while the replacement panes are reparented into native windows.
        self.setFocus()
        if self.harmony_window:
            dock=(self.harmony_window.isVisible(),self.harmony_window.isFloating(),self.harmony_window.current_id)
            self.harmony_window.hide();self.harmony_window.deleteLater();self.harmony_window=None
        for pane in (self.melody_window,self.score_tools,*self.score_floats.values()):pane.hide();pane.deleteLater()
        for shortcut in self.findChildren(QShortcut):shortcut.setEnabled(False);shortcut.deleteLater()
        for action in self.findChildren(QAction):action.setShortcut(QKeySequence())
        old=self.takeCentralWidget();old.hide();old.deleteLater()
        self.setMenuWidget(None);self.setMenuBar(QMenuBar(self))
        self.language=language;set_language(language);self.workspace='compose';self.loading=True
        self.build_ui();self.build_menu();self.refresh();self.set_theme(theme)
        self.score_view.canvas.project,self.score_view.canvas.layout=session['score_snapshot']
        mode,scale,scroll_x,scroll_y=session['score_view'];self.score_view.set_zoom(scale,mode=mode)
        self.restoring_layout=True
        self.melody_chords_action.setChecked(session['floating_melody_chords'])
        for lane,value in zip((self.chord_lane,self.roll.lane,self.harmony_window.roll.lane),session['chord_velocity']):lane.set_velocity_visible(value)
        for key,value in session['mutes'].items():self.mute_buttons[key].setChecked(value)
        self.update_audio();self.loop.blockSignals(True);self.loop.setChecked(session['loop']);self.loop.blockSignals(False);self.follow_playhead.setChecked(session['follow'])
        self.dock_height.setCurrentIndex(self.dock_height.findData(session['dock_height']))
        self.tool.setCurrentIndex(self.tool.findData(view['tool']));self.grid.setCurrentIndex(view['grid']);self.grid.set_triplet(view['triplet'])
        self.length.setCurrentIndex(view['length']);self.length.set_triplet(view['length_triplet']);self.dotted.setChecked(view['dotted']);self.roll.previous_duration=view['previous'];self.roll.previous_note_id=view['previous_id']
        self.roll.zoom=view['zoom'];self.roll.set_row_height(view['height']);self.view_controls.height.setCurrentIndex(self.view_controls.height.findData(view['height']))
        self.view_controls.range.setCurrentIndex(1 if view['compact'] else 0)
        for key,value in view['panels'].items():self.view_controls.panel_actions[key].setChecked(value)
        self.roll.selected_ids=view['selected'];self.roll.selection=view['selection'];self.roll.has_note_clipboard=self.note_clipboard is not None
        self.score_view.canvas.has_note_clipboard=self.note_clipboard is not None
        unit,bars,beats,anchor=session['score_selection'];self.score_selection.setCurrentIndex(self.score_selection.findData(unit));self.score_view.canvas.selected_bars=bars;self.score_view.canvas.selected_beats=beats;self.score_view.canvas.selection_anchor=anchor
        for key,value in session['visibility'].items():self.visibility_actions[key].setChecked(value)
        self.melody_window.setFloating(session['melody_float']);self.score_tools.setFloating(session['score_float']);self.score_tabs.setCurrentIndex(session['tab']);self.logic_panel.restore_state(session['logic'])
        if workspace=='score':self.switch_workspace('score',refresh_score=False);self.edit_toggle.setChecked(editing);self.toggle_editor()
        if dock and workspace=='compose':
            self.harmony_window.setFloating(dock[1]);self.harmony_window.current_id=dock[2]
        for pane,visible in zip((self.melody_window,self.harmony_window),session['float_open']):
            pane.floating_visible=visible
            if workspace=='compose' and pane.isFloating():pane.setVisible(visible)
        if workspace=='score':
            self.compose_float_state=session['compose_floats']
            if session['compose_view_state'] is not None:self.compose_view_state=session['compose_view_state']
            if session['compose_float_open'] is not None:self.compose_float_open=session['compose_float_open']
        self.score_panel_state=session['score_panels'];self.mount_panels()
        for key,geometry in session['score_geometry'].items():self.score_floats[key].restoreGeometry(geometry)
        if session['score_active']:self.score_tabs.setCurrentWidget(self.score_pages[session['score_active']])
        self.lyric_panel.restore_state(session['lyric_draft'])
        if not self.rolls_linked():
            grid,triplet,length,ltriplet,dotted,previous,previous_id=session['harmony_tools'];h=self.harmony_window;h.grid.setCurrentIndex(grid);h.grid.set_triplet(triplet);h.length.setCurrentIndex(length);h.length.set_triplet(ltriplet);h.dotted.setChecked(dotted);h.roll.previous_duration=previous;h.roll.previous_note_id=previous_id
        for index,(_,r,check,controls) in enumerate(self.view_panes()):
            check.blockSignals(True);check.setChecked(session['timeline_sync'][index]);check.blockSignals(False);controls.follow.setChecked(session['view_follow'][index])
        self.syncing_views=True;self.syncing_time=True
        try:
            for r,state in zip((self.main_roll,self.roll,self.harmony_window.roll),session['timeline_views']):
                r.zoom=state['zoom'];r.grid=state['grid'];r.grid_bars=state['grid_bars'];r.compact=state['compact'];r.set_row_height(state['height']);r.update_ranges();r.horizontalScrollBar().setValue(state['scroll'])
                if r is not self.main_roll:
                    controls=self.view_controls if r is self.roll else self.harmony_window.view_controls
                    controls.height.blockSignals(True);controls.height.setValue(state['height']);controls.height.blockSignals(False)
                    controls.range.blockSignals(True);controls.range.setCurrentIndex(int(state['compact']));controls.range.blockSignals(False)
        finally:self.syncing_views=False;self.syncing_time=False
        if workspace=='compose':QTimer.singleShot(0,self,lambda:self.tracks.setSizes(session['track_sizes']))
        self.show_cursor(self.playhead);QTimer.singleShot(0,self,lambda:self.roll.center_pitch(view['pitch']));QTimer.singleShot(0,self,lambda:self.harmony_window.roll.center_pitch(session['harmony_pitch']))
        self.restoring_layout=False;self.update_shared_views();self.update_transport_buttons()
        QTimer.singleShot(0,self,lambda:(self.score_view.horizontalScrollBar().setValue(scroll_x),self.score_view.verticalScrollBar().setValue(scroll_y)))
        self.status_message(tr('Smart：空白拖动框选 · Draw：单击写入或删除，拖动编辑 · 右键复制变换'))
        if persist:self.save_preferences()

    def set_theme(self,mode,persist=False):
        mode='dark' if mode=='dark' else 'light';apply_theme(mode=='dark');self.theme_actions[mode].setChecked(True)
        from lingfeng.ui.windowing import theme_frame
        for window in (self,self.melody_window,self.harmony_window,self.score_tools,*self.score_floats.values()):theme_frame(window)
        if persist:self.save_preferences()

    def change_coloring(self,role,key,value):
        import lingfeng.ui.theme as theme
        options=copy.deepcopy(theme.ROLL_COLORING);options[role][key]=value;set_roll_coloring(options)
        for r in (self.roll,self.harmony_window.roll):r.refresh()
        self.save_preferences()

    def change_accidentals(self,value):
        from lingfeng.ui.theme import set_accidental_preference
        set_accidental_preference(value);self.save_preferences()
        for roll in (self.roll,self.main_roll,self.harmony_window.roll):roll.refresh()

    def change_note_degrees(self,visible):
        set_note_degrees(visible)
        for r in (self.roll,self.harmony_window.roll):r.refresh()
        self.save_preferences()

    def update_transport_buttons(self):
        kind='pause' if self.transport.playing else 'play';self.play_button.set_kind(kind)
        buttons=[self.play_button]
        if getattr(self,'workspace_ready',False):
            for _,_,_,controls in self.view_panes():
                controls.play.set_kind(kind)
                buttons.append(controls.play)
                controls.loop.blockSignals(True);controls.loop.setChecked(self.loop.isChecked());controls.loop.blockSignals(False)
                controls.bpm.blockSignals(True);controls.bpm.setValue(self.project.bpm);controls.bpm.blockSignals(False)
        label=tr('暂停' if self.transport.playing else '播放');key=self.keybindings.get('play','')
        if key:label+=' ('+key+')'
        for btn in buttons:btn.setToolTip(label);btn.setAccessibleName(label)

    def resize_score(self):
        if self.workspace!='score':return
        docked=self.score_tabs.count()>0
        self.score_splitter.setMaximumHeight(16777215)
        self.score_view.setMinimumHeight(100)
        self.score_splitter.setStretchFactor(0,1);self.score_splitter.setStretchFactor(1,0)
        if docked:self.resize_dock()

    def resize_dock(self):
        if self.workspace=='score':
            height=self.dock_height.currentData();self.score_splitter.setSizes([max(150,self.score_splitter.height()-height),height])

    def import_midi(self,target):
        from lingfeng.audio.midi_import import read_midi, apply_midi
        from lingfeng.ui.import_dialog import MidiImportDialog
        path,_=QFileDialog.getOpenFileName(self,tr('导入 MIDI'),'',tr('MIDI 文件 (*.mid *.midi)'))
        if not path:return
        try:data=read_midi(path)
        except (OSError,ValueError) as exc:QMessageBox.warning(self,tr('导入 MIDI'),tr(str(exc)));return
        start=self.active_roll().snap_time(self.playhead);dialog=MidiImportDialog(self.project,data,target,start,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        if self.mutate(tr('已导入 MIDI；可撤销覆盖'),lambda p:apply_midi(p,data,dialog.indices(),target,start,dialog.meter.isChecked(),dialog.tempo.isChecked(),dialog.quantization())):
            if target=='chords':self.open_harmony()
            roll=self.roll if target=='melody' else self.harmony_window.roll
            roll.selected_ids={n.id for n in roll.notes if start<=n.start<start+data.end_for(dialog.indices())};roll.refresh();roll.ensure_tick(start)

    def edit_marker(self,index):self.edit_context([self.project.starts[index:index+2]])

    def insert_measure(self,index):
        parent,origin=self.edit_dialog_origin()
        dialog=MarkerDialog(self.project,index,parent,True)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            count=dialog.count.value()
            if self.mutate(tr('已插入 {0} 个小节，后方音乐顺延',count),lambda p:p.insert_measures(index,count,**dialog.value()),source=origin):
                self.roll.selection=[[self.project.starts[index],self.project.starts[index+count]]];self.selection_changed(self.roll.selection);self.roll.ensure_tick(self.project.starts[index]);self.roll.refresh()
        self.restore_dialog_origin(parent,origin)

    def delete_measures(self,bars):
        from lingfeng.music.bar_operations import delete_bars, deletion_has_content
        bars=sorted(set(bars))
        if not bars or len(bars)>=len(self.project.measures):self.status_message(tr('项目至少需要保留一个小节。'));return
        if deletion_has_content(self.project,bars):
            answer=QMessageBox.question(self,tr('删除小节'),tr('删除所选 {0} 个小节及其中内容？跨界音符与和弦会截断，后方音乐前移。可用 Ctrl+Z 撤销。',len(bars)),QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
            if answer!=QMessageBox.StandardButton.Yes:return
        if self.mutate(tr('已删除所选小节'),lambda p:delete_bars(p,bars)):
            index=min(bars[0],len(self.project.measures)-1);self.selection_changed([self.project.starts[index:index+2]])
            canvas=self.score_view.canvas;canvas.selected_bars={index};canvas.selected_beats.clear();canvas.selectionChanged.emit();canvas.update()
            self.playhead=min(self.playhead,self.project.end-1);self.play_anchor=min(self.play_anchor,self.project.end-1)

    def midi_input_settings(self):
        from lingfeng.audio.midi_input import MidiInputDialog
        self.midi_input.reset();dialog=MidiInputDialog(self.midi_input,self)
        if dialog.exec()!=QDialog.DialogCode.Accepted:return
        if dialog.enabled.isChecked() and dialog.device.currentData() is None:
            QMessageBox.warning(self,tr('MIDI 键盘输入'),tr('请连接 MIDI 键盘并刷新设备列表。'));return
        try:
            self.midi_input.configure(dialog.device.currentData(),dialog.device.currentText(),dialog.target.currentData(),dialog.enabled.isChecked())
            if self.midi_input.enabled and self.midi_input.target=='chords':self.open_harmony()
            self.status_message(tr('MIDI 键盘录入已启用') if self.midi_input.enabled else tr('MIDI 键盘录入已关闭'))
        except (OSError,RuntimeError) as exc:QMessageBox.warning(self,tr('MIDI 键盘输入'),str(exc))

    def sound_settings(self):
        self.transport.close();self.stop()
        dialog=SoundSettingsDialog(self.project.audio,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.mutate(tr('已更新两轨音源与音色'),lambda p:setattr(p,'audio',dialog.value()))

    def effective_volumes(self):return {key:0 if self.mute_buttons[key].isChecked() else value for key,value in self.project.volumes.items()}

    def update_audio(self):
        self.transport.configure(self.project.audio);self.transport.set_volumes(self.effective_volumes())

    def change_loop(self,enabled):
        if not enabled:
            self.loop_range=None;self.sync_loop_range()
            for gesture in (self.timeline.gesture,self.roll.timeline_gesture,self.harmony_window.roll.timeline_gesture):
                if gesture.state and not gesture.state['upper']:gesture.cancel()
        self.update_transport_buttons()
        if not self.transport.playing:return
        start,end=self.loop_bounds()
        self.transport.set_loop(self.project,self.loop_active(),start,end)

    def loop_active(self):return self.loop.isChecked() and self.loop_range is not None

    def loop_bounds(self):return self.loop_range if self.loop_active() else (0,self.project.end)

    def sync_loop_range(self):
        for r in (self.roll,self.main_roll,self.harmony_window.roll):
            r.loop_range=self.loop_range
            if self.loop_range is None:r.loop_anchor=None
            elif r.loop_anchor is None:r.loop_anchor=self.loop_range[0]
            r.refresh()
        self.timeline.update()

    def set_loop_range(self,bounds):
        a,b=bounds;a=max(0,min(int(a),self.project.end-1));b=max(a+1,min(int(b),self.project.end))
        self.loop_range=(a,b);self.sync_loop_range()
        if not self.loop.isChecked():self.loop.setChecked(True)
        else:self.change_loop(True)

    def toggle_play(self):
        if self.transport.playing:self.playhead=self.transport.position();self.stop();return
        try:
            loop_start,b=self.loop_bounds()
            a=self.playhead if loop_start<=self.playhead<b else loop_start
            if not loop_start<=self.play_anchor<b:self.play_anchor=a
            self.transport.play(self.project,a,b,self.loop_active(),volumes=self.effective_volumes(),loop_start=loop_start);self.transport_active=True;self.show_cursor(a);self.update_transport_buttons()
        except Exception as exc:QMessageBox.warning(self,tr('播放不可用'),tr(str(exc)))

    def show_cursor(self,tick):
        tick=max(0,min(tick,self.project.end-1));anchor=self.play_anchor if self.transport.playing else None
        rolls=[self.roll]
        if self.harmony_window:rolls.append(self.harmony_window.roll)
        if getattr(self,'workspace_ready',False):rolls.append(self.main_roll)
        for r in rolls:
            r.cursor_tick=tick;r.play_tick=tick if self.transport.playing else None;r.anchor_tick=anchor
            r.viewport().update();r.lane.update();r.navigator.update()
        if getattr(self,'workspace_ready',False):
            for widget in (self.timeline,self.navigator,self.chord_lane):widget.update()
        if self.workspace=='score':
            self.score_view.canvas.play_tick=tick;self.score_view.canvas.anchor_tick=anchor;self.score_view.canvas.update()

    def stop(self,preserve_auditions=False):
        if not preserve_auditions and hasattr(self,'midi_input'):self.midi_input.reset()
        if preserve_auditions:self.transport.stop(preserve_auditions=True)
        else:self.transport.stop()
        self.transport_active=False
        if hasattr(self,'play_button'):self.update_transport_buttons()
        if hasattr(self,'roll'):self.roll.play_tick=None;self.show_cursor(self.playhead)
        if self.harmony_window:self.harmony_window.roll.play_tick=None;self.harmony_window.roll.refresh()

    def stop_to_anchor(self):self.stop();self.playhead=self.play_anchor;self.show_cursor(self.playhead)
    def replay(self):
        # Restart directly instead of routing through the play/pause toggle.
        # In particular, queued completion signals must not turn this into Pause.
        if not self.transport.playing:
            start=max(0,min(self.play_anchor,self.project.end-1))
            self.playhead=start;self.show_cursor(start);self.roll.ensure_tick(start);self.harmony_window.roll.ensure_tick(start)
            if self.workspace=='score':self.score_view.locate_tick(start)
            return
        loop_start,end=self.loop_bounds()
        start=self.play_anchor if loop_start<=self.play_anchor<end else loop_start
        try:
            self.transport.play(self.project,start,end,self.loop_active(),volumes=self.effective_volumes(),loop_start=loop_start)
            self.transport_active=True;self.playhead=start;self.show_cursor(start);self.update_transport_buttons()
        except Exception as exc:QMessageBox.warning(self,tr('播放不可用'),tr(str(exc)))
    def rewind(self):self.return_to_start()
    def return_to_start(self):
        self.stop();self.seek(0);self.roll.ensure_tick(0)
        if self.workspace=='score':self.score_view.locate_bar(0)
    def play_from(self,tick):
        self.seek(tick)
        if not self.transport.playing:self.toggle_play()

    def seek(self,tick):
        playing=self.transport.playing
        self.playhead=max(0,min(tick,self.project.end-1));self.play_anchor=self.playhead
        if playing:
            a,b=self.loop_bounds()
            loop=self.loop_active() and a<=self.playhead<b
            try:
                self.transport.play(self.project,self.playhead,b if loop else self.project.end,loop,volumes=self.effective_volumes(),loop_start=a)
                self.transport_active=True;self.update_transport_buttons()
            except Exception as exc:self.stop();self.status_message(str(exc))
        self.show_cursor(self.playhead)
        self.status_message(tr('定位：第 {0} 小节 · Space 播放 / 暂停', self.project.measure_at(self.playhead) + 1))

    def playback_tick(self):
        if self.transport.playing:
            tick=self.transport.position();self.playhead=tick;self.roll.play_tick=tick
            self.follow_views(tick)
            self.show_cursor(tick)
        elif self.transport_active:self.stop_to_anchor()

    def maybe_save(self):
        if not self.dirty:return True
        result=QMessageBox.question(self,tr('保存修改'),tr('当前作品有未保存的修改。'),QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
        return self.save() if result==QMessageBox.StandardButton.Save else result==QMessageBox.StandardButton.Discard

    def replace_project(self,p,path=None):
        self.score_view.canvas.clear_layout()
        if not p.chords:p.fill_chord_gaps()
        for roll in (self.roll,self.harmony_window.roll):roll.previous_duration=None;roll.previous_note_id=''
        self.clear_chord_move_session()
        self.loop.setChecked(False);self.loop_range=None;self.sync_loop_range()
        self.commit_volume()
        self.stop();self.project=p;self.path=Path(path) if path else None;self.dirty=False;self.undo_history.clear();self.redo_history.clear();self.playhead=0;self.play_anchor=0;self.roll.cursor_tick=0;self.logic_panel.reset();self.roll.selection=[[0,p.measures[0].ticks]];self.refresh();self.roll.center_pitch(p.context_at(0).tonic+6)
        self.lyric_panel.reset_project()
        if self.workspace=='score':
            if p.notation.get('font_layout_version')!=45:self.prepare_score_font()
            self.score_view.canvas.rebuild(self.project)

    def new(self):
        if self.maybe_save():self.replace_project(Project(title=tr('未命名作品')))

    def load_demo(self):
        if self.maybe_save():self.replace_project(demo_project())

    def open(self):
        if not self.maybe_save():return
        path,_=QFileDialog.getOpenFileName(self,tr('打开项目'),str(self.path.parent if self.path else Path(self.last_project_dir)),tr('伶风工程 (*.lfs *.leadsheet)'))
        if path:
            try:self.replace_project(Project.load(path),path);self.last_project_dir=str(Path(path).parent);self.save_preferences()
            except Exception as exc:QMessageBox.warning(self,tr('无法打开'),tr(str(exc)))

    def save(self,save_as=False):
        self.commit_volume()
        path=self.path
        if path is not None and path.suffix.lower()!='.lfs':path=path.with_suffix('.lfs')
        if path is None or save_as:
            name,_=QFileDialog.getSaveFileName(self,tr('保存项目'),str(path or Path(self.last_project_dir)/(safe_name(self.project.title)+'.lfs')),tr('伶风工程 (*.lfs)'))
            if not name:return False
            path=Path(name)
            if path.suffix.lower()!='.lfs':path=path.with_suffix('.lfs')
        try:self.project.save(path)
        except Exception as exc:QMessageBox.warning(self,tr('保存失败'),tr(str(exc)));return False
        self.path=path;self.last_project_dir=str(path.parent);self.save_preferences();self.dirty=False;self.refresh();self.status_message(tr('已保存：{0}', path));return True

    def recover_save(self):
        if self.dirty:
            try:
                folder=user_data_dir();folder.mkdir(parents=True,exist_ok=True);self.project.save(folder/'recovery.lfs')
            except OSError:pass

    def restore_recovery(self):
        path=user_data_dir()/'recovery.lfs'
        if path.exists() and self.maybe_save():
            try:self.replace_project(Project.load(path));self.dirty=True;self.refresh()
            except Exception as exc:QMessageBox.warning(self,tr('恢复失败'),tr(str(exc)))
        elif not path.exists():self.status_message(tr('暂无自动保存。编辑后每30秒保存一次恢复副本。'))

    def populate_export_menu(self,menu):
        for label,kind in [('PDF 乐谱…','pdf'),('MIDI…','midi'),('MP3…','mp3')]:
            menu.addAction(tr(label),lambda checked=False,k=kind:self.open_export(k))

    def open_export(self,format,which='both'):
        from lingfeng.ui.export_dialog import ExportDialog
        self.stop();self.transport.cancel_auditions()
        ExportDialog(self,format,which).exec()

    def save_pdf(self):self.open_export('pdf')

    def save_midi(self,which='both'):self.open_export('midi',which)

    def save_daw_bundle(self):
        name,_=QFileDialog.getSaveFileName(self,tr('导出 DAW 迁移包'),str(documents_dir()/(safe_name(self.project.title)+'-DAW.zip')),'ZIP (*.zip)')
        if not name:return
        try:export_daw_bundle(self.project,name);self.status_message(tr('已导出含完整 MIDI、独立分轨与时间轴说明的 DAW 迁移包'))
        except Exception as exc:QMessageBox.warning(self,tr('迁移包导出失败'),tr(str(exc)))

    def help(self):
        HelpDialog(self).exec()

    def chord_preferences(self):
        from lingfeng.ui.dialogs import ChordPreferenceDialog
        from lingfeng.music.chord_operations import set_quality_order
        dialog=ChordPreferenceDialog(self)
        if dialog.exec()==QDialog.DialogCode.Accepted:set_quality_order(dialog.value());self.save_preferences()

    def progression_settings(self,query='',source=None,ids=None):
        from lingfeng.ui.progression_dialogs import ProgressionManagerDialog
        parent=source.window() if source is not None else self
        from lingfeng.music.progressions import selection_root_query
        tick=min((c.start for c in self.project.chords if c.id in (ids or set())),default=self.playhead)
        context=self.project.context_at(tick)
        factory=(lambda t:selection_root_query(self.project,ids,t)) if ids else None
        dialog=ProgressionManagerDialog(self.progression_presets,parent,query=query,tonic=context.tonic,mode=context.mode,query_factory=factory)
        if dialog.exec()==QDialog.DialogCode.Accepted:self.progression_presets=dialog.value();self.save_preferences()
        if source is not None:self.restore_dialog_origin(parent,source)

    def search_progressions(self,ids,source=None):
        from lingfeng.music.progressions import selection_root_query
        try:query=selection_root_query(self.project,ids)
        except ValueError as exc:self.status_message(str(exc));return
        self.progression_settings(query,source or self.active_roll(),ids)

    def apply_progression(self,cid,source):
        from lingfeng.ui.progression_dialogs import ProgressionDialog
        from lingfeng.music.progressions import apply
        dialog=ProgressionDialog(self.project,cid,self.progression_presets,self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            ids=[]
            if self.mutate(tr('已应用和弦进行'),lambda p:ids.extend(apply(p,cid,**dialog.value())),source=source):self.chord_selection(set(ids),source)

    def capture_progression(self,ids):
        from lingfeng.music.progressions import presets
        from lingfeng.ui.progression_dialogs import CaptureProgressionDialog
        parent,origin=self.edit_dialog_origin()
        try:dialog=CaptureProgressionDialog(self.project,ids,parent)
        except ValueError as exc:self.status_message(str(exc));return
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.progression_presets=presets([*presets(self.progression_presets),dialog.value()])
            self.save_preferences();self.status_message(tr('已保存和弦进行预设'))

    def color_settings(self):
        dialog=ColorSettingsDialog(self)
        if dialog.exec()==QDialog.DialogCode.Accepted:set_roll_palettes(dialog.values);self.save_preferences()

    def score_command(self,command,payload):
        if not self.score_structure_current():return
        bars=payload['bars'];ranges=payload['ranges']
        if command=='delete_bars':self.delete_measures(bars);return
        def operation(p):
            if command=='force_row':
                if not forced_row_allowed(p,bars,self.score_view.canvas.layout.systems):raise ValueError(tr('需要连续小节，且选区从当前谱行开头开始。'))
                apply_forced_row(p,bars)
            elif command=='auto_rows':
                p.notation['forced_rows']=[r for r in p.notation.get('forced_rows',[]) if not set(bars)&set(range(*r))]
                p.notation['forced_row_fonts']=[r for r in p.notation.get('forced_row_fonts',[]) if not set(bars)&set(range(r[0],r[1]))]
            elif command.startswith('compress:'):add_compression(p,bars,command.split(':')[1])
            elif command=='expand':p.notation['compressions']=[c for c in p.notation.get('compressions',[]) if not set(bars)&set(range(c['start'],c['end']))]
            elif command.startswith('symbol:'):
                if len(ranges)!=1:raise ValueError(tr('请选择连续的小节或拍。'))
                add_annotation(p,command.split(':')[1],*ranges[0])
            elif command=='clear_symbols':p.notation['symbols']=[item for item in p.notation.get('symbols',[]) if not any(item['start']<b and a<item['end'] for a,b in ranges)]
            elif command=='remove_structure':
                key,index=payload['key']
                if key in ('compressions','symbols') and 0<=index<len(p.notation.get(key,[])):p.notation[key].pop(index)
        self.mutate(tr('已更新谱面排版与符号，演奏时间线保持不变'),operation)

    def score_structure_current(self):
        canvas=self.score_view.canvas
        if canvas.layout is not None and canvas.project.starts!=self.project.starts:
            self.status_message(tr('小节结构已改变，请重新切入制谱模式同步后操作。'));return False
        return True

    def closeEvent(self,event):
        if self.maybe_save():
            self.midi_input.close()
            self.transport.close()
            for pane in (self.melody_window,self.harmony_window,self.score_tools,*self.score_floats.values()):pane.hide()
            event.accept()
        else:event.ignore()


def run(path=None):
    app=QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('Lingfeng');app.setApplicationDisplayName('伶风 Lingfeng — For Pop Music');app.setFont(QFont('Microsoft YaHei',9));app.setStyle('Fusion');app.setStyleSheet(STYLE)
    from lingfeng.platform.preferences import load_preferences
    set_language(load_preferences(user_data_dir()).get('language'))
    project=Project.load(path) if path else None
    window=MainWindow(project)
    if path:window.path=Path(path)
    window.show()
    return app.exec()

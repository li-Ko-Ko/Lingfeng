"""Bilingual help content shared by the desktop UI and documentation exporter.

This module deliberately has no Qt or application-state dependencies. Topic IDs
are the Chinese titles used by HELP_CATEGORIES; edit both language bodies here.
"""
from html import unescape
import re

BRAND = '伶风 Lingfeng'

TAGLINE = 'Lingfeng — For Pop Music'

ABOUT_ZH = ('<h1>伶风</h1><p><b>为流行音乐而生 · For Pop Music</b></p>\n'
 '<p>伶风是一款面向 Windows 电脑、键鼠友好的轻量级音序器（sequencer），用于流行音乐创作与分析，并集成简谱制谱。用鼠标与键盘编写旋律、安排和弦，再将音乐整理成可阅读、可分享的乐谱。</p>\n'
 '<h3>在电脑上轻松创作</h3>\n'
 '<p>界面为鼠标、键盘和桌面多窗口操作设计，支持快捷键、可调整布局及独立钢琴卷帘。免安装发行包解压即可使用，无需另装 Python；随包附带轻量合成音源（37 个预设），支持目录扩展，也可选择 Windows MIDI '
 '设备。创作、制谱与工程保存均可在本地离线完成。</p>\n'
 '<h3>从音乐到乐谱</h3>\n'
 '<ul><li>编辑多声部旋律与和弦，试听音符、编排伴奏节奏型。</li>\n'
 '<li>制作传统简谱、立体简谱与紧凑谱面，添加歌词并调整排版。</li>\n'
 '<li>导入 MIDI，分轨导出到其他音乐软件，或输出 PDF 乐谱与 MP3 音频。</li></ul>\n'
 '<h3>专注创作，衔接专业制作</h3>\n'
 '<p>伶风专注于旋律、和弦编写与简谱制谱。音频录音、混音与母带处理建议在 Cakewalk Next 等专业数字音频工作站（DAW）中完成；可将旋律与和弦分轨导出为 MIDI，继续制作。</p>\n'
 '<h3>灵感与独立实现</h3>\n'
 '<p>伶风的音乐创作思路受 Hooktheory Hookpad 与 Helio 启发，钢琴卷帘与桌面编辑交互参考 Cakewalk，尤其是 Cakewalk Next '
 '的公开文档。本应用独立实现，与上述产品及其权利人无隶属、合作或认可关系；相关名称和商标归各自权利人所有。发行包不包含它们的专有代码、音源或图形；常用进行以罗马数字自行整理。</p>\n'
 '<h3>开源与许可</h3>\n'
 '<p>伶风原创应用代码以 MIT 许可证开源，发行包的 source/ 提供源码与重建脚本，LICENSE 列出许可条件。PySide6、Qt 等第三方组件保留各自许可，详见 docs/THIRD_PARTY.md 与 '
 'licenses/。开源许可仅涵盖有权授权的内容，不授予上述产品的商标或专有资源使用权。</p>\n'
 '<h3>名字的由来</h3>\n'
 '<p>“伶风”取自古代乐官“伶”与《诗经》国风“风”，寓意流行音乐创作开放、亲切、不故作神秘。让写歌与记谱更简单，是伶风的初衷。</p>')

ABOUT_EN = ('<h1>Lingfeng</h1><p><b>For Pop Music</b></p>\n'
 '<p>Lingfeng is a lightweight, mouse-and-keyboard-friendly sequencer for pop music creation and analysis on Windows '
 'PCs, with integrated jianpu (numbered notation). Write melodies and arrange chords with a mouse and keyboard, then '
 'turn your music into scores you can read and share.</p>\n'
 '<h3>Made for your computer</h3>\n'
 '<p>The interface is designed for mouse, keyboard and desktop multi-window use, with shortcuts, adjustable layouts '
 'and floating piano rolls. Unzip the portable release to get started, with no separate Python installation. '
 'Lightweight native synth packs are included (37 presets); installed Windows MIDI devices are also available. '
 'Compose, prepare scores and save projects locally, even offline.</p>\n'
 '<h3>From music to scores</h3>\n'
 '<ul><li>Edit polyphonic melodies and chords, audition notes and arrange accompaniment patterns.</li>\n'
 '<li>Create traditional, spatial and compact jianpu scores, add lyrics and refine the layout.</li>\n'
 '<li>Import MIDI, export separate tracks to other music software, or share a PDF score and MP3 audio.</li></ul>\n'
 '<h3>Focus on composition, continue in a DAW</h3>\n'
 '<p>Lingfeng focuses on writing melodies and chords and preparing jianpu scores. For audio recording, mixing and '
 'mastering, use a dedicated digital audio workstation (DAW), such as Cakewalk Next. Export melody and chord tracks as '
 'MIDI to continue production there.</p>\n'
 '<h3>Inspiration and independent implementation</h3>\n'
 "<p>Lingfeng's approach to music creation is inspired by Hooktheory Hookpad and Helio. Its piano roll and desktop "
 'editing interactions draw on Cakewalk, especially the public Cakewalk Next documentation. This independently '
 'implemented app is not affiliated with, partnered with or endorsed by those products or their rights holders. Their '
 'names and trademarks belong to their respective owners. The release includes none of their proprietary code, sound '
 'sources or graphics. Common progression recipes are independently expressed as Roman numerals.</p>\n'
 '<h3>Open source and licensing</h3>\n'
 '<p>Lingfeng’s original application code is open source under the MIT License. The release includes source code and '
 'rebuild scripts in source/, with the license terms in LICENSE. Third-party components, including PySide6 and Qt, '
 'retain their own licenses; see docs/THIRD_PARTY.md and licenses/. The open-source license covers only rights that '
 'can be granted and does not grant rights to the trademarks or proprietary resources of the products named '
 'above.</p>\n'
 '<h3>Behind the name</h3>\n'
 '<p>Lingfeng draws on the ancient music officials (<i>ling</i>) and the folk airs of the <i>Book of Songs</i> '
 '(<i>feng</i>), standing for pop music creation that is open, friendly, and free from mystique. Its purpose is to '
 'make songwriting and notation simpler.</p>')

HELP_CATEGORIES = (('开始使用与工程', 'Start and projects', ('开始与工程', '升级与偏好保留')),
 ('旋律输入与编辑',
  'Melody input and editing',
  ('智能与绘制工具', '时值、吸附与小节设置', '默认时值跟随与属七降五', '音符变换', '长音符、隐藏与编辑视角', '导入 MIDI', 'MIDI 输入与量化')),
 ('和弦与进行',
  'Chords and progressions',
  ('小节、和弦区间与实际音符',
   '和弦区间与快速编辑',
   '和弦结构与节奏型',
   '和弦边界与连续音符',
   '低音与和弦转位',
   '和弦调内移动',
   '和弦节奏、节奏型与独立窗口',
   '实际和弦音、重新生成与辅助时间尺',
   '选择、预览与和弦编辑逻辑',
   '段落与和弦进行',
   '调式数字与创作提示',
   '调式标号与四项和弦记忆',
   '密集和弦、八度移动与根五交替',
   '拍号区间与和弦提示',
   '移动边界、暂存与删除小节',
   '右键菜单、选择与自定义节奏型')),
 ('工作区、导航与快捷键',
  'Workspace, navigation and shortcuts',
  ('工作区与悬浮窗口', '和弦轨联动与高亮', '独立窗口与和弦力度', '时间尺、循环与鼠标拖屏', '方向键、三连音与边缘框选', '快捷键与定位线', '统一快捷键与冲突处理', '颜色与可视区域')),
 ('播放、音源与导出', 'Playback, sounds and export', ('播放与音源', '统一字号与合成音源', '按格式导出', '导出与迁移')),
 ('制谱、歌词与结构',
  'Scores, lyrics and structure',
  ('休止符与立体简谱', '谱面缩放、拍间分隔与更新', '两端对齐与字号上限', '紧凑传统简谱与 32 分音符对', '谱面选择与局部合行', '歌词与符号位置', '反复压缩与跳转', '其他谱面符号')),
 ('关于与许可', 'About and licensing', ()))

TOPICS = [('开始与工程',
  'Getting started',
  '新建默认 4/4、C3 Ionian。工程后缀 <b>.lfs</b> 是 Lingfeng Lead Sheet 的缩写，保存全部音乐与谱面排版。“编辑 → '
  '作品信息”确认标题后，当前谱面标题立即更新；撤销与重做同样更新标题，无需重新进入制谱。打开与保存会记住上次工程目录；新建与新增小节按小节填充 N.C.（无和弦）区间。保存、撤销与重做分别使用 '
  'Ctrl+S、Ctrl+Z、Ctrl+Y（或 Ctrl+Shift+Z）。这些快捷键在独立卷帘中同样可用。撤销或重做会激活操作所属的编辑器；布局改变后使用其当前位置，不中断播放。',
  'New projects use 4/4 and C3 Ionian. <b>.lfs</b> stands for Lingfeng Lead Sheet and stores music and page layout. '
  'Confirm a title in Edit → Project information to update the displayed score title immediately. Undo and redo update '
  'it too, without re-entering Score mode. Open and Save remember the last project folder. New projects and added bars '
  'contain one N.C. (no chord) region per bar. Use Ctrl+S to save, Ctrl+Z to undo and Ctrl+Y (or Ctrl+Shift+Z) to '
  'redo, including in floating rolls. Undo and redo activate the editor where the operation took place, using its '
  'current location after layout changes, without interrupting playback.'),
 ('升级与偏好保留',
  'Upgrades and personal settings',
  '<h3>1. 更新程序</h3><p>完整解压新版本到新文件夹，退出旧程序后运行新版 Lingfeng.exe。保留 _internal 和 synths 文件夹。程序不要求把旧发行包的配置复制到新目录。</p><h3>2. '
  '个人设置与和弦进行</h3><p>语言、外观、快捷键、和弦菜单顺序、四项和弦编辑记忆和自定义进行保存在 Windows '
  '当前用户的数据目录，升级后继续读取。同一用户在不同解压目录启动，使用同一份个人设置。新增默认值只补齐新设置；已清空的快捷键与用户的进行修改、删除应继续保留。</p><h3>3. 工程与声音</h3><p>旋律、和弦实际 '
  'MIDI、调性、拍号、工程音源选择、歌词与谱面排版随 .lfs '
  '保存。更新前保存工程并保留副本。新工程的音源默认值不覆盖已有工程；缺少音源时重新安装或扫描完整音源文件夹。旧工程转换只在需要时迁移已知格式，已经保存的显式和弦音符不会因名称转换重新配器。</p><h3>4. '
  '自动恢复</h3><p>自动保存是恢复副本，不能代替手动保存。异常退出后，从文件菜单恢复并另存为工程；删除或移动程序目录前先确认工程已保存。</p><h3>5. 迁移与备份</h3><p>每个应用版本首次升级前保留 '
  'preferences.pre-版本号.json（例如 preferences.pre-0.50.2.json），后续保存保留 preferences.json.bak。主偏好损坏时可从备份恢复，并保留 '
  'preferences.json.corrupt 原件。额外音源扫描目录和新工程音色默认值也继续沿用；程序位置变化后重新扫描验证音源，不直接复用旧 DLL 路径。工程和个人偏好分别保存，自动恢复工程不会重置个人进行库。</p>',
  '<h3>1. Update the application</h3><p>Extract the complete new release into a new folder. Exit the old application '
  'and run the new Lingfeng.exe. Keep _internal and synths. You do not need to copy configuration out of the previous '
  'release folder.</p><h3>2. Personal settings and progression library</h3><p>Language, appearance, shortcuts, '
  'chord-menu order, the four remembered chord settings and custom progressions are stored in the current Windows '
  'user’s data directory and reused after upgrades. Launches from different extracted folders share these settings. '
  'New defaults fill newly introduced settings; cleared shortcuts and progression edits or deletions remain personal '
  'choices.</p><h3>3. Projects and sound</h3><p>Melody, performed chord MIDI, keys, meters, project sound choices, '
  'lyrics and engraving are stored in .lfs. Save projects and keep copies before updating. New-project sound defaults '
  'do not replace existing project choices. Reinstall or rescan complete synth folders when a source is missing. Known '
  'legacy formats migrate as needed; a chord-name migration does not revoice already saved explicit notes.</p><h3>4. '
  'Recovery</h3><p>Autosave is a recovery copy, not a replacement for saving. After an unexpected exit, use the File '
  'recovery command and save the recovered project. Confirm that projects are saved before moving or deleting an '
  'application folder.</p><h3>5. Migration and backups</h3><p>The first upgrade to each application version keeps '
  'preferences.pre-VERSION.json, for example preferences.pre-0.50.2.json. Later saves keep preferences.json.bak. If '
  'preferences become corrupt, the backup can be used while preserving the original as preferences.json.corrupt. Extra '
  'synth scan folders and new-project instrument defaults carry over too. Moving the application triggers validated '
  'rescanning rather than directly trusting old DLL paths. Projects and preferences are saved separately; project '
  'recovery does not reset the personal progression library.</p>'),
 ('智能与绘制工具',
  'Smart and Draw',
  '智能工具：单击选择，空白拖动框选；Ctrl 单击增减，Shift '
  '扩展框选。多选后单击其中一项，释放且未拖动时缩为单选；从已选项开始拖动保留整组。双击空白格内写入，双击音符删除。<br>绘制工具：单击格内写入，单击已有音符删除；拖动已有音符移动，拖动边缘调整时值。绘制中按 Shift '
  '锁定音高。音符实体与琴键用于编辑、选择和试听。单击卷帘格点纵线或相邻音符间的窄缝可吸附定位，不写入音符；先判断音符实体，长音内部仍编辑该音符。智能工具按住空白处后显示十字框选，拖动不定位；绘制工具禁用卷帘左右键框选，含 '
  'Ctrl／Shift 组合。创作中单击时间轴下半部时间尺定位，双击从该处播放；制谱中还可单击谱面定位。',
  'Smart: click to select, drag blank space to marquee, Ctrl-click to add or remove. Clicking a selected member of a '
  'group narrows the selection on release if no drag occurred; starting a drag retains the group. Double-click a blank '
  'cell to insert or a note to delete.<br>Draw: click a cell to insert and an existing note to delete. Drag existing '
  'notes to move or resize their edges. Hold Shift during drawing to lock pitch. Note bodies and piano keys edit, '
  'select or audition. Click a vertical grid boundary or the narrow visual gap between adjacent notes to snap the '
  'position marker without writing a note. Note bodies take priority, so grid lines inside a sustained note still edit '
  'that note. In Smart, holding blank space activates the marquee crosshair; dragging selects without seeking. Draw '
  'disables left/right-button piano-roll marquees, including Ctrl/Shift modifiers. In Compose, click the lower time '
  'ruler to seek or double-click it to play. The score also supports click-to-seek.'),
 ('时值、吸附与小节设置',
  'Duration, snap and bar settings',
  '左侧“时值”控制新音符长度，支持全音符至 1/128、1/2/4/8 '
  '小节、“跟随网格”和“上一次时值”。附点与三连音互斥；上一次时值取最近选择、绘制或拉伸的音符。右侧“吸附”在琴键设置旁，独立决定卷帘纵线和时间轴最小单位，支持三连音，没有自适应模式。选中音符后右键“按当前格点量化”，将起点吸附到当前格点，保留时长。<br>时间轴上半部按整小节选择；Ctrl '
  '单击增减不连续小节，Shift 单击从锚点连续选择，Ctrl+Shift '
  '追加范围。下半部为独立时间尺，按吸附格点定位或设置循环。右键“设置所选小节拍号与调性”将选区扩展为整小节并一次应用。普通批量设置仅修改所选小节。只选一个小节时，右键可将其调性或拍号应用至后续所有小节，覆盖后方已有变化；调性包含主音与调式，拍号包含分子与分母，两项独立应用。最后一小节无后续小节时禁用。首小节显示完整标记；后续仅显示与前一小节不同的标记。缩短小节会删除或截断音符时先确认，后方音乐随小节长度顺延。<br>卷帘音符和根音／低音选择控件遵循全局升降号偏好；和弦名称与提示优先使用调式或和弦音程的拼写，谱面音符右键可切换等音降号。主音大调为数字参照，和弦变化不改变主音。',
  'Duration on the left sets new note length: whole notes through 1/128, 1/2/4/8 bars, Follow grid or Previous note. '
  'Dotted and triplet are mutually exclusive. Previous note uses the most recently selected, drawn or resized note. '
  'Snap beside the keyboard settings independently controls vertical grid lines and the smallest timeline unit. It '
  'supports triplets, without an adaptive mode. Quantize is available only in the context menu for selected notes and '
  'snaps their starts while keeping durations.<br>The upper timeline selects whole bars. Ctrl-click toggles individual '
  'bars; Shift-click extends from the anchor; Ctrl+Shift adds a range. The separate lower time ruler uses the snap '
  'grid for positioning and loops. Set meter and key for selected bars expands the selection to complete bars and '
  'applies it once. The standard batch command changes only selected bars. With one bar selected, its context menu can '
  'apply that bar’s key or meter to all following bars, replacing later changes. Key includes tonic and mode; meter '
  'includes numerator and denominator. These commands act independently and are disabled at the final bar. The first '
  'bar shows the full marker; later bars show only changes. Shortening a bar asks for confirmation if notes would be '
  'deleted or cut; subsequent music shifts with bar length.<br>Piano-roll letter names follow the global accidental '
  'preference; root/bass letter names follow the same preference. Chord names and tooltips prefer mode-aware or '
  'chord-interval spelling; score notes can use enharmonic flats. Numbers reference the parallel major scale; chord '
  'changes do not change the tonic.'),
 ('默认时值跟随与属七降五',
  'Default duration tracking and dominant flat five',
  '时值默认选择“上一次时值”。还没有可追踪音符时，新音符暂按起点所在格点长度创建，选项保持不变；之后跟随最近创建、选择或编辑音符的实际时值，包括拉伸、属性修改及撤销。改变格点不会覆盖已记住的时值。旋律与和弦卷帘分别记忆，切换语言或停靠状态保留，新建／打开工程重新从格点起步；手动固定时值和“跟随网格”仍可选。<br><br>新增“7b5 '
  '· 属七降五和弦”，组成 1、3、♭5、♭7（0、4、6、10 半音），例如 C7b5 = C、E、G♭、B♭。支持和弦菜单、识别、转位、进行配方（如 V7b5）、MIDI 与工程保存。它与 '
  'm7b5（半减七和弦）的区别是三音为大三度。',
  'Note duration defaults to Previous note. With no tracked note yet, creation temporarily uses the grid cell at its '
  'onset without changing the selected mode. It then follows the actual duration of the latest created, selected or '
  'edited note, including resizing, property edits and undo. Grid changes do not overwrite the remembered duration. '
  'Melody and harmony rolls keep separate histories across language and docking changes; new/open projects start with '
  'the grid fallback again. Fixed durations and Follow grid remain available.<br><br>7b5 · Dominant seventh flat five '
  'adds degrees 1, 3, flat 5 and flat 7 (0, 4, 6, 10 semitones). C7b5 contains C, E, Gb and Bb. It supports chord '
  'menus, recognition, inversions, progression recipes such as V7b5, MIDI and project files. Unlike m7b5 '
  '(half-diminished seventh), its third is major.'),
 ('音符变换',
  'Note transformations',
  '框选后右键：直接复制、逆行（时间反向）、倒影（音高翻转）、逆行倒影。直接复制保留实际音高，包括调外音；含调外音的选区禁止其他三种复制。变换粘贴按落点调式还原音阶级数。等时值 1243 逆行变为 3421，倒影为 '
  '4312。<br>Alt+W／S 调内移动（Alt+↑／↓ 同样可用）。相邻同音高音符可合并；右键二等分音符不要求对齐格点，允许分到 1/64；已有 1/64 '
  '不可再分，三连音同理。拉伸或粘贴同音高音符时，以新音符覆盖重叠部分；旧音符保留边界外的前段、后段，完全覆盖则移除。仅边界相接不会合并，不同音高可自由叠加。音符的起止与力度分别保留，Ctrl+Z 可撤销。',
  'After selecting notes, right-click for direct copy, retrograde (time reverse), inversion (pitch flip), or both. '
  'Direct copy preserves absolute pitches, including chromatic notes. The other three are disabled if any selected '
  'note is outside its scale. Transformed paste uses scale degrees in the destination mode. Equal-length 1243 becomes '
  '3421 in retrograde or 4312 in inversion.<br>Alt+W/S moves notes within the scale (Alt+Up/Down also works). Join '
  'adjacent same-pitch notes; split notes in half regardless of grid alignment, down to a 1/64 note or 1/64-note '
  'triplet. Resizing or pasting a note replaces only overlapping time on the same pitch. Existing notes retain their '
  'outside prefixes and suffixes; fully covered notes are removed. Touching boundaries do not merge notes. Different '
  'pitches can overlap freely, with separate timing and velocity. Ctrl+Z undoes the edit.'),
 ('长音符、隐藏与编辑视角',
  'Long notes, hiding and edit scrolling',
  '跨调性／调式的长音符在开头按时间顺序显示音级，例如 1 (3, '
  '2)；相接的和弦长音片段共用标签。设置中的数字显示开关全局生效。<br>主界面卷帘标题右侧的关闭图标用于隐藏，与视图菜单的勾选同步，可再次勾选恢复。<br>键盘或右键移动选中音符时，视角保持不动，直到最后一个可见选中音符将移出视野，才滚动使它完整可见。横向保留音符全长与所在拍号一拍中的较短长度。拖动、拉伸或绘制音符到网格边缘时缓慢滚动；松开鼠标或 '
  'Esc 停止，不改变播放位置。<br>时间轴右键在小节前／后插入时可选择数量、拍号、调性，插入空白并顺延音乐，一次撤销整批恢复，工程最多 1000 小节。',
  'Long notes crossing keys or modes display degrees in time order at their start, such as 1 (3, 2). Joined chord-note '
  'fragments share the label. The global degree-display setting applies.<br>The close icon beside each docked roll '
  'title hides that roll and updates View; check it again to restore the roll.<br>Moving notes with keys or context '
  'menus keeps the view still until the last visible selected note is about to leave it. Vertical scrolling keeps that '
  'note fully visible; horizontal scrolling keeps the shorter of its full duration and one beat in its local meter '
  'visible. Dragging, resizing or drawing near the grid edge scrolls gradually. Release or Esc stops scrolling without '
  'seeking playback.<br>Insert bars before/after a bar on the timeline accepts a quantity, meter and key. It inserts '
  'silence and shifts later music, with one undo for the whole batch and a maximum of 1,000 bars per project.'),
 ('导入 MIDI',
  'Import MIDI',
  '编辑 → 导入 MIDI '
  '到旋律／和弦。选择文件后勾选来源音轨，确认播放游标起点及覆盖范围，再选择是否覆盖拍号、速度。默认保留拍号和速度。导入仅替换目标轨道对应区间，区间外内容及另一轨的音符位置保留，可撤销。跨覆盖边界的已有音符和和弦保留外侧片段。和弦导入生成自定义结构框并识别和弦，跨小节长音保留完整时长。<br>支持 '
  'PPQ 制式 MIDI Type 0/1；导入实际音高、起止和力度；保留工程歌词，忽略新 MIDI 的歌词。同音高重叠保留后续发音起点，以后来的音符覆盖交叠部分，避免将连奏误判为持续柱式。88 '
  '键范围外的音符不会静默丢弃，会拒绝导入并提示调整音域。覆盖拍号要求从小节边界开始；末个导入小节之后恢复原拍号。不合法的拍号边界会提示取消覆盖拍号。当前工程为固定速度，选择覆盖速度时只使用 MIDI '
  '首个速度；不导入后续速度变化、音色或控制器自动化。',
  'Edit → Import MIDI into melody/chords. Choose source tracks, review the playhead start and replacement range, then '
  'optionally replace meter or tempo. Both options are off by default. Only the corresponding destination range is '
  'replaced; outside content and note positions in the other track remain intact. Undo restores the project. Notes and '
  'chords crossing the range retain their outside pieces. Chord import creates custom regions and recognizes their '
  'tones; notes spanning barlines keep their full duration.<br>Supports PPQ-based MIDI Type 0/1, importing pitch, '
  'timing and velocity while retaining existing lyrics and ignoring incoming MIDI lyrics. Same-pitch overlaps retain '
  'later note onsets: later notes replace overlapping time rather than merging a legato passage into one sustained '
  'block. Notes outside the 88-key range are rejected with an explanation instead of silently discarded. Meter '
  'replacement starts at a bar boundary and restores the original meter after the last imported bar. Incompatible '
  'meter boundaries can be avoided by leaving meter replacement unchecked. The project has a fixed tempo: replacing it '
  'uses only the first MIDI tempo. Later tempo changes, instruments and controller automation are not imported.'),
 ('MIDI 输入与量化',
  'MIDI input and quantization',
  '设置 → MIDI '
  '键盘输入：选择设备及目标轨道后启用。暂停时逐步录入，同时按键形成和弦；连奏与延音踏板保留后续按键的先后起点，松开全部琴键或延音踏板后前进；播放时实时录入，力度来自键盘。起点与结束强制吸附当前目标卷帘格点，包括三连音。设备不会在启动时自动启用。<br>导入窗口单独选择量化格点，可保留原始时间或指定普通／三连音网格。“结合连续节奏识别三连音”要求同一拍内至少两个偏离常规格点的三连音起点，并比较两种网格的误差；时长结合后续音符处理小间隙。单个音符或自由速度段无法可靠推断时，请显式指定网格或保留原始时间。',
  'Settings → MIDI keyboard input: select a device and destination, then enable recording. Step input while paused '
  'groups near-simultaneous keys into a chord, but preserves successive onsets during legato or pedal holds. It '
  'advances after all keys and the sustain pedal are released. E switches the target roll and MIDI input track. During '
  'playback, input is recorded live with keyboard velocity. Onsets and endings snap to the destination roll’s current '
  'grid, including triplets. Devices are not armed automatically at launch.<br>Import has a separate quantization '
  'grid: keep original timing or choose a straight/triplet grid. Triplet detection requires at least two off-straight '
  'triplet onsets within a beat and compares grid errors. Duration look-ahead closes small performance gaps. Isolated '
  'notes and free-tempo passages may require an explicit grid or original timing.'),
 ('小节、和弦区间与实际音符',
  'Bars, chord regions and performed notes',
  '<h3>1. '
  '小节决定时间结构</h3><p>小节拍号决定一拍的长度与小节边界，调性决定数字音级的参照。连续相同拍号组成一个可编辑区间；调性变化本身不切断实际音符。插入、删除或改变小节长度会移动后续音乐；拍号变化处的和弦区间按边界拆分。</p><h3>2. '
  '和弦轨决定区间操作</h3><p>和弦卡片保存根音、性质、指定低音和生成参数，并控制该区间的生成、替换、移动与裁切。已识别节奏型按各完整小节生成后裁切；锁定的自定义节奏型移动只平移，扩大只留空。静音 N.C. '
  '区间只占位置，不产生音符。</p><h3>3. 和弦卷帘决定实际演奏</h3><p>直接编辑卷帘会改变实际 '
  'MIDI，并据此重新识别各区间；识别不补音。连续音符可以跨多个和弦区间。合并相邻和弦只去掉边界；显式分割则切开跨界音符。重新生成或应用节奏型会替换手工音符，执行前先核对选区；可以撤销。</p><h3>4. '
  '谱面与导出</h3><p>播放、音频及 MIDI 导出使用最新实际音符。谱面在进入制谱时同步，编辑过程中保留当前排版；需要更新时回到创作再切入制谱。PDF 使用当前显示谱面。</p>',
  '<h3>1. Bars define musical time</h3><p>Meter defines beat length and bar boundaries; key and mode define the '
  'reference for degree numbers. Consecutive equal meters form one editing region. A key change alone does not cut '
  'sounding notes. Inserting, deleting or changing bar lengths shifts later music; chord regions split at meter '
  'changes.</p><h3>2. The chord lane controls region operations</h3><p>Chord cards hold root, quality, specified bass '
  'and generation settings, and control generation, replacement, movement and cropping in their region. Recognized '
  'patterns generate over complete bars and are cropped afterward. Locked Custom patterns only translate on moves, and '
  'extension adds silence. N.C. regions occupy time without generating notes.</p><h3>3. The chord roll controls the '
  'performance</h3><p>Direct note edits change performed MIDI and refresh recognition in each affected region. '
  'Recognition never fills missing voices. A sustained note can cross several chord regions. Merging adjacent chords '
  'removes boundaries only; an explicit split cuts crossing notes. Regeneration or applying a pattern replaces manual '
  'notes: review the selection first and use Undo if needed.</p><h3>4. Scores and export</h3><p>Playback, audio and '
  'MIDI export use the latest performed notes. Engraving synchronizes on entering Score mode and retains its displayed '
  'layout during music edits. Return to Compose and re-enter Score when a refresh is needed. PDF uses the displayed '
  'score.</p>'),
 ('和弦区间与快速编辑',
  'Chord regions and quick editing',
  '在和弦轨任意位置右键插入空白和弦；也可选择“在定位线处插入”。自动长度截止当前小节末尾或下个和弦起点，以较近者为准；另有 1／2／3 拍、1／2／3／4 '
  '小节。拍按当前位置拍号分母计数，小节按后续实际拍号计时，曲尾截断。占用位置直接覆盖，保留未覆盖片段。和弦轨点击不定位播放游标。右键“编辑和弦”设置根音、性质与节奏型；空白区间确认后生成音符。<br>节奏型统一从和弦右键菜单设置。根音菜单显示“数字级数 '
  '· 音名”，以和弦开始处的主音为 1，数字采用主音大调参照并保留调式音级，字母输入遵循卷帘升降号偏好，不随点击点或播放位置改变。已识别的和弦可右键选择十二种根音、常用和弦性质、替换低音和节奏型；设置 → '
  '和弦菜单偏好可拖动或用上下按钮调整性质顺序。“替换低音”提供十二个音；“和弦转位”提供原位至第四转位，音数不足的转位禁用，两项都即时替换低音声部，保留根音和上方声部，不保留勾选状态；应用节奏型替换手工音符，可撤销。单击和弦与 '
  'Tab 切换使用和弦轨音色与音量，试听一小节柱式和弦（至少 650 毫秒）。单选时再次单击取消选择也试听；长按可延长，框选不自动试听。右键“试听实际和弦”按 MIDI '
  '起止、力度、节奏型播放；多选时按时间顺序紧邻试听。新点击立即替换旧试听，播放状态与位置不变。旋律下方最近的和弦轨悬停或单击选中会在和弦持续范围内高亮旋律卷帘的弦内音背景，包括其它八度。单选时再次单击取消；多选时单击其中一项缩为单选。Shift '
  '单击连续选取，Ctrl 单击增减，Ctrl+Shift 追加连续范围。拖动空白处框选和弦，支持复制、二等分、删除和统一升降半音／八度。二等分下限与音符一致；多个和弦均已识别、名称相同且相邻时可合并，保留实际音符节奏。复制 Ctrl '
  '多选的和弦，粘贴时按原时间顺序紧邻排列，去掉选区间空隙；音符复制仍保留空隙。',
  'Right-click anywhere in the chord lane to insert an empty chord at the snapped pointer or at the position marker. '
  'Auto ends at the nearer bar boundary or next chord start; other choices are 1/2/3 beats or 1/2/3/4 bars. Beats use '
  'the local meter denominator; bars use subsequent actual meters, clamped at the song end. Occupied portions are '
  'overwritten; uncovered pieces remain. Clicking the chord lane does not seek. Edit chord sets the root, quality and '
  'pattern; confirming an empty region generates its notes.<br>Patterns are controlled from chord context menus. Root '
  'choices display “degree · note name”, using the tonic at the chord’s start as 1, major-reference numbers with modal '
  'degree identity, and sharp letter names. The click position and playhead do not change these labels. Recognized '
  'chords offer 12 roots, 19 common qualities, bass replacements and patterns. Settings → Chord menu preferences '
  'reorders qualities by dragging or using up/down buttons. Replace bass offers all 12 pitches; Chord inversion offers '
  'root position through fourth inversion, disabling inversions that require more chord tones. Both are one-shot bass '
  'replacements, preserving the chord root and upper voices, with no persistent check mark. Applying a pattern '
  'replaces custom notes and can be undone. Click a chord or press Tab to audition a one-bar block chord (at least 650 '
  'ms), using the chord track sound and volume. Clicking the sole selected chord again deselects it and still '
  'auditions; holding can extend the sound. Marquee selection is silent. Audition actual chords plays MIDI timing, '
  'velocities and rhythms; multiple selected regions play consecutively in timeline order without gaps. A new click '
  'replaces the old preview without changing playback state or position. In the main window, hover or click to '
  'highlight the chord-tone background rows across its duration, including other octaves. Click again to deselect. '
  'Shift-click selects a contiguous range, Ctrl-click toggles selection, and Ctrl+Shift adds a range. Drag from empty '
  'space to select several chords. Batch commands include copy, split, delete and uniform semitone/octave shifts. '
  'Binary splitting has the same minimum duration as notes. Adjacent chords in the same meter region can merge: only '
  'the boundary is removed, all MIDI onsets and velocities are retained, and recognition runs again. Chords copied '
  'from disjoint Ctrl selections paste consecutively in source time order, removing gaps; note copies retain gaps.'),
 ('和弦结构与节奏型',
  'Chord structure and patterns',
  '和弦卷帘时间轴下方显示与主和弦轨相同的卡片和区间；数据实时同步。悬浮和弦窗口独立保存选择与悬停状态，不选中主界面和弦，也不高亮旋律。停靠时共享选择。<br>长按结构卡片边缘调整范围：缩短删除范围外音符，不创建新的和弦；扩大自定义区间仅增加空白，原有音符保持绝对时间。已知名称且节奏型可识别的和弦，移动、缩短或扩大时按完整小节生成，再截取区间；每小节重新开始节奏型，按实际拍号计算长度。起于第 '
  '2 拍、止于第 4 拍的和弦仅保留第 2–3 拍的片段。移动、伸缩或编辑后即时更新节奏型识别；按实际音符的起止与音高排列匹配，允许八度重叠和不同力度。识别本身不改 '
  'MIDI。已识别节奏型在移动、伸缩后重建为和弦默认配器与默认力度，逐音属性重置。自定义节奏型移动只平移，伸缩只裁切，保留剩余音符属性。旧工程打开时保持原演奏，编辑区间或重新应用节奏型后采用新规则。覆盖相邻和弦时，用当前区间的空白或节奏型替换覆盖部分，未覆盖部分保留原音符。移动中部改变和弦位置；已识别节奏型按目标小节位置重建，自定义音符只平移。主和弦轨的拉伸保留原属性；自定义音符不会自动填充。所有操作可撤销。',
  'Below the chord roll timeline, chord cards show the same data and regions as the main chord lane. Edits synchronize '
  'immediately. Floating chord windows keep their own selection and hover state, without selecting main-window chords '
  'or highlighting melody rows. Docked selection is shared.<br>Hold and drag a structure-card edge: shortening deletes '
  'outside notes without creating leftover regions. Extending custom content adds silence and preserves existing '
  'absolute note times. Named chords with recognizable patterns are generated over each complete bar and cropped to '
  'the region after moving or resizing. Patterns restart at every bar using its actual meter. A region starting at '
  'beat 2 and ending at beat 4 retains only beats 2–3. Recognition updates immediately after moving, resizing or '
  'editing. It matches actual note timing and pitch order, allowing octave doublings and varied velocities. '
  'Recognition alone does not change MIDI. Moving or resizing a recognized pattern rebuilds notes using the chord’s '
  'default voicing, gate and velocity, resetting per-note edits. Custom patterns only translate on moves or crop on '
  'resizing, preserving surviving note attributes. Old projects retain their performance on opening and adopt bar '
  'phase when regions are edited or patterns reapplied. Covered neighbor portions are replaced by the edited region’s '
  'silence or rhythm; uncovered portions retain their performed notes. Dragging the center moves the region: '
  'recognized patterns rebuild at the destination bar phase; custom notes translate unchanged. Resizing the main chord '
  'lane retains chord attributes; custom notes are not automatically filled. All edits support Undo.'),
 ('和弦边界与连续音符',
  'Chord regions and continuous notes',
  '和弦边界用于识别和编辑实际 MIDI。在和弦卷帘新建、移动、拉伸或粘贴的音符可以跨越多个和弦块：保留一次起音、一次止音，分别刷新各块识别结果，不自动改动边界。MIDI '
  '导入会延长初始和弦区间，避免导入长音在小节线处被切断。<br>新建／添加小节与移动／缩短和弦后，空余区间自动填为 N.C.，不产生声音。右键合并相邻和弦只取消边界、不改变 '
  'MIDI，随后重新识别。二等分和弦或在定位线处分割会真正切开跨越分割点的音符。编辑或替换和弦时按新的和弦区间切开原音符。<br>可识别和弦更改根音或性质会按原有其它参数重新生成；已识别节奏型保持，性质变更恢复根音低音。替换低音与转位仍仅修改最低声部。根音列表按起点调性从 '
  '1 '
  '开始，改变起点保持所选音高。编辑器只记住上次确认的性质、节奏型、发音长度和力度，跨和弦和重启生效；根音默认起点调号主音，低音默认等于根音。改变根音同步低音，单独改变低音保留根音。起点、时长、伴奏八度取当前和弦，重新生成默认开启，取消不更新记忆。不支持的生成节奏型回退为持续柱式。首次默认勾选重新生成和弦；名称和节奏型均已识别时，更改根音／性质仍会重建。所有已提交音符、区间与 '
  'MIDI 输入更改都会刷新识别；识别本身不补音。谱面圈音和悬停提示始终依据实际 MIDI。',
  'Chord regions identify and edit performed MIDI. Notes created, moved, resized or pasted in the chord roll can span '
  'several blocks with one note-on and one note-off. Each region is recognized from its portion without moving its '
  'boundaries. MIDI import extends initial chord regions so sustained notes are not cut at bar lines.<br>New/added '
  'bars and space vacated by chord moves/resizes receive silent N.C. regions. Merge adjacent chords removes only '
  'boundaries, preserving MIDI before recognition. Splitting in half or at the position marker cuts notes at the '
  'requested split. Editing or replacing a chord cuts original events at the replacement region.<br>Changing a '
  'recognized chord root or quality rebuilds it with the other settings, retaining a recognized pattern. Quality '
  'changes reset the bass to the root. Bass replacement and inversion only change the lowest voice. Root lists start '
  'at degree 1 in the onset key and retain the selected pitch when the onset changes. Only confirmed quality, pattern, '
  'gate and velocity carry over across chords and restarts. Root starts at the onset key tonic and bass at the root. '
  'Root changes also move bass; bass changes leave root untouched. Start, duration and accompaniment octave come from '
  'the current chord; regeneration starts enabled. Cancel retains prior defaults. Unsupported generation patterns fall '
  'back to Block. Regenerate chord is enabled initially; root/quality changes rebuild when both name and pattern are '
  'recognized. Committed note/region edits and MIDI input refresh recognition, which never adds tones by itself. Score '
  'circles and chord tooltips use performed MIDI.'),
 ('低音与和弦转位',
  'Bass and chord inversion',
  '已识别和弦的右键菜单分为“替换低音”和“和弦转位”。前者提供全部十二个音，后者提供原位至第四转位（九和弦），不足音数的选项禁用。两者都是即时替换最低声部的操作，保留根音、性质、上方声部、节奏和逐音力度；不作为可持续勾选的属性。多选及未识别和弦禁用这两个菜单。',
  'For recognized chords, the context menu separates Replace bass (all 12 pitches) from Chord inversion (root position '
  'through fourth inversion for ninth chords). Inversions requiring more tones than the chord contains are disabled. '
  'Each action immediately replaces the lowest voice while retaining root, quality, upper voices, timing and per-note '
  'velocities; it is not a persistent checked attribute. Both menus are disabled for multiple or unrecognized chords.'),
 ('和弦调内移动',
  'Diatonic chord movement',
  '和弦根音与性质可识别时，W／S 更换根音一个半音，保持性质、节奏与其它属性，低音恢复为新根音。Alt+W／S 按和弦开始处的调式移动一级，并调整性质以保持调内，例如 C/E → '
  'Dm；同样恢复根音低音，不保留转位。无需先识别转位。只有调内和弦可执行调内移动；目标性质不支持或音高越界时禁用，多选必须全部合法。右键 → 和弦移动提供相同操作，以及独立的固定半音／八度移调分组。快捷键与旋律的调内移动共用设置。',
  'For recognized chords, W/S change the root by one semitone while preserving quality, rhythm and other properties, '
  'restoring bass to the new root. Alt+W/S move by a scale step in the mode at each chord start, adapting quality to '
  'stay diatonic: C/E → Dm. This also restores root-position bass; it does not preserve inversion or require inversion '
  'recognition. Diatonic movement is available only for diatonic chords. Unsupported target qualities or out-of-range '
  'pitches disable it; all selected chords must be valid. Move chord in the context menu provides these commands and a '
  'separate fixed semitone/octave transposition group. Scale-step bindings are shared with melody notes.'),
 ('和弦节奏、节奏型与独立窗口',
  'Harmonic rhythm, accompaniment patterns and floating windows',
  '和弦节奏（harmonic rhythm）指和弦根音、性质等多久变化一次，由和弦块起止位置体现。和弦节奏型（accompaniment '
  'pattern）指一个和弦内部的织体与发音安排，例如持续柱式、反拍或琶音；“自定义”锁定的是节奏型，不是和弦变化频率。<br>旋律和和弦音符的新建、拖动、拉伸和粘贴使用相同覆盖规则：只替换同音高的重叠部分，保留旧音符两侧剩余片段，边界相接不合并。不同音高可以同时发声。长音只有一个连续外形，跨和弦或调性边界时仅改变内部颜色；格线绘制在音符下方。<br>设置 '
  '→ 卷帘染色：旋律卷帘独立控制和弦匹配、调内音染色；和弦卷帘独立控制旋律匹配、调内音染色。和弦卷帘按整个和弦块内出现或持续经过的旋律音级染色，没有和弦块时不染旋律匹配色。开关只影响卷帘颜色，不改变 '
  'MIDI、谱面或手动选择高亮。<br>Shift＋滚轮与 '
  'Ctrl＋滚轮均以指针为中心缩放时间轴、和弦轨和卷帘；停靠时三者同步，独立窗口按“同步时间轴”开关决定是否联动。Alt＋滚轮水平浏览；橙色播放游标离开正在浏览的卷帘后才取消跟随。<br>独立卷帘与主窗口共用应用标识，在 '
  'Windows '
  '任务栏分组下显示一个图标，悬停可预览各窗口。独立窗口与主窗口互不强制置顶，可分别最小化和恢复；选择主窗口时可将其切至前台。顶部依次为停靠、最小化、最大化／还原、关闭；边框随主题变化。播放栏始终靠右排列在窗口上部；底部提供旋律、和弦的音量与静音，所有窗口双向同步同一组轨道设置。旋律独立窗口播放栏最右侧“其它选项”可显示／隐藏自己的和弦轨，不影响主界面的显示勾选。',
  'Harmonic rhythm is how often chord roots and qualities change, represented by chord-region boundaries. An '
  'accompaniment pattern is the texture and note timing inside a chord, such as sustained blocks, offbeats or '
  'arpeggios. Custom locks the accompaniment pattern, not the rate of harmonic change.<br>Creating, moving, resizing '
  'and pasting notes use the same overwrite rule in both rolls: replace only overlapping time at the same pitch and '
  'preserve the remaining pieces on either side. Touching notes do not merge. Different pitches can sound together. A '
  'long note has one continuous outline; only its internal color changes across harmonic or key boundaries. Grid lines '
  'stay behind notes.<br>Settings → Piano roll coloring provides independent chord-match and scale-tone switches for '
  'the melody roll, and melody-match and scale-tone switches for the chord roll. Melody pitches sounding anywhere '
  'within a chord region tint the entire region; empty regions have no melody-match tint. These options change roll '
  'colors only, leaving MIDI, score rendering and selection highlights intact.<br>Shift+wheel and Ctrl+wheel zoom '
  'around the pointer over timelines, chord lanes and piano rolls. Docked views stay synchronized; floating views use '
  'their Sync timeline setting. Alt+wheel browses horizontally; following is disabled when the orange playhead leaves '
  'the piano roll being browsed.<br>Floating rolls share the main application identity: with Windows taskbar grouping '
  'enabled, one icon offers previews of every window. Each window can be brought forward, minimized or restored '
  'independently. The title bar has Dock, Minimize, Maximize/Restore and Close controls, with a theme-aware border. '
  'Transport controls stay at the upper right. The bottom mixer controls melody and chord volumes and mutes, '
  'synchronized across all windows. Window options at the floating melody roll’s upper right can show or hide its own '
  'chord lane independently of the main View menu.'),
 ('实际和弦音、重新生成与辅助时间尺',
  'Performed chord tones, regeneration and auxiliary ruler',
  '谱面圈音和谱面和弦悬浮提示采用该和弦区间实际 MIDI 的音高集合，包含不同八度；不根据名称补推未奏出的音。当前识别采用精确音高类匹配，不推断省略音。IV '
  '片段如果只奏低音，其它和弦音不圈出是正常的；显示不会修改音乐。<br>编辑和弦窗口的“重新生成和弦”默认开启。先按实际片段识别节奏型，再按当前根音、性质和低音补齐和弦音，确认后替换实际音符，可撤销。例如低音＋和弦截取的一拍只有带间隙的低音，会识别为四分柱式再补齐和弦。取消勾选保留现有音符编辑；选择新节奏型会重新勾选。<br>右键更换根音或性质也使用更改前实际片段识别的节奏型重新生成。按当前伴奏八度的默认配器生成；性质变更恢复根音低音，逐音编辑恢复默认力度与发音长度。替换低音、转位仅修改低音，不补齐声部。未知或锁定自定义节奏不自动猜测；需要完整重建时，在编辑窗口选择节奏型并勾选重新生成。移动、伸缩继续按完整小节生成再截取。<br>设置 '
  '→ 和弦轨辅助时间尺默认 1 拍，可关闭或选 1/4 拍、1/2 拍、2 拍、1 '
  '小节；拍长按当地拍号计算。刻度上下对称，静止时位于和弦块后方，移动、伸缩预览时随高亮边框显示。它不接受点击、框选或定位，也不控制吸附。<br>当前页面任一停靠卷帘控制主时间轴缩放与吸附格点，新显示或重新停靠的卷帘继承目标页面尺度。独立卷帘保留本地格点；同步时间轴仍控制横向缩放、滚动与跟随。循环只显示两端竖线与中间底色，边缘仍可伸缩。',
  'Score circles and chord hover details use pitch classes actually present in the chord region’s MIDI, across '
  'octaves. They do not infer unplayed tones from a chord name. The recognizer requires an exact pitch-class match and '
  'does not infer omissions. If an IV fragment plays only its bass, leaving other tones uncircled is expected. Display '
  'never edits music.<br>Regenerate chord is checked by default in Edit chord. Identify the performed fragment’s '
  'pattern first, then fill voices from the current root, quality and bass. Confirming replaces notes and can be '
  'undone. A one-beat crop of Bass + chord containing only a gated bass pulse becomes quarter blocks before voices are '
  'filled. Uncheck to retain note edits; choosing another pattern rechecks it.<br>Quick root and quality changes also '
  'regenerate using the pattern identified from the actual fragment before editing. Voices use the default voicing at '
  'the retained accompaniment octave; quality changes reset bass to the root, and per-note edits return to default '
  'velocity and gate. Bass replacement and inversion change only the bass. Unknown or locked Custom rhythms are not '
  'assigned a guessed pattern; choose a pattern in Edit chord and check Regenerate chord for a complete rebuild. '
  'Moving and resizing retain full-bar generation and crop rules.<br>Settings → Chord lane auxiliary ruler defaults to '
  '1 beat, with Off, 1/4 beat, 1/2 beat, 2 beats and 1 bar options. Beat length follows the local meter. Symmetrical '
  'top and bottom ticks sit behind stationary cards and appear with the highlighted border during move/resize '
  'previews. It does not handle clicks, selection, positioning or snapping.<br>Either docked roll controls the current '
  'page’s timeline zoom and snap grid. Newly shown or redocked rolls inherit the destination page’s scale. Floating '
  'rolls retain local grids; Sync timeline still links zoom, scrolling and follow state. Loops use only vertical '
  'endpoints and fill, with resizable edges.'),
 ('选择、预览与和弦编辑逻辑',
  'Selection, previews and chord editing',
  '多选音符或和弦后，普通单击其中一项，松开且未拖动时只选该项；从已选项开始拖动保留整组。Ctrl '
  '单击未选项加入、已选项移除，移除后不启动拖动。此选择规则适用于智能工具音符与和弦；绘制工具单击已有音符仍直接删除。单独选中的和弦再次单击仍取消选择。<br>移动、拉伸时以原位虚影和目标轮廓对照定位，松开后一次提交；Esc '
  '或隐藏卷帘取消尚未提交的手势并清除虚影。拉伸只追踪水平位置，鼠标移到别的音高行也继续捕获；仅上下移动不改变时值。<br>右键更换可识别和弦的性质，保留区间、节奏型、伴奏八度、力度和发音长度，恢复根音低音，按更改前实际片段识别出的节奏型重新生成和弦音。例如两拍 '
  'vi 四分柱式改成 vi7 '
  '后仍为四分柱式。未知或锁定自定义的事件节奏保持，只重新映射音高；主动应用节奏型才覆盖原手工节奏。和弦节奏表示和声变化频率，节奏型表示柱式、琶音等内部织体。<br>和弦名称与悬停提示优先按当前调式拼写音名，例如 F Ionian 的 '
  'IV 写 Bb；调外音按和弦性质音程拼写，如 C 小三和弦的 '
  'Eb（b3）。未分类音使用和弦等音偏好。卷帘按全局升降号偏好显示，调内数字保留调式音级；根音与低音输入字母同样遵循卷帘升降号偏好。和弦编辑器根音选项同时显示数字与音名，依据和弦开始处调性计算，开始位置改变后同步更新。<br>简谱延音线连接同一音符的记谱片段：除跨拍、跨小节外，单个符号无法表示的真实时长也可能需要分解。细微 '
  'MIDI 舍入误差不会额外生成碎片、微小休止与多余连线；真正的持续时值仍保留必要连线。排版修正不改变演奏或导出 MIDI。',
  'Clicking a member of a multiple note or chord selection narrows it on release if no drag occurred. Dragging from a '
  'selected member retains the group. Ctrl-click adds an unselected member or removes a selected one; removal never '
  'starts dragging. These selection rules apply to Smart notes and chord cards. Draw still deletes an existing note on '
  'click. Clicking the sole selected chord again still deselects it.<br>Move and resize gestures show the original '
  'position as a ghost and the target as an outline. Release commits one edit; Escape or hiding the roll cancels the '
  'pending gesture and clears its preview. Resizing follows horizontal position even after the pointer moves to '
  'another pitch row; vertical motion alone does not change duration.<br>Changing a recognized chord’s quality retains '
  'its region, complete voicing registers, bass and other parameters. It regenerates and fills voices using the '
  'accompaniment pattern identified from the performed fragment before editing. For example, changing a two-beat vi '
  'with quarter blocks to vi7 keeps quarter blocks. Unknown or locked Custom rhythms retain event timing while pitches '
  'are remapped. Explicitly applying an accompaniment pattern replaces manual rhythm. Harmonic rhythm means how often '
  'the harmony changes; an accompaniment pattern is the internal texture, such as blocks or arpeggios.<br>Chord names '
  'and hover details prefer the active mode’s pitch spelling, such as Bb for IV in F Ionian. Chromatic tones use '
  'chord-quality interval spelling, such as Eb (b3) in C minor; unclassified tones use the chord’s enharmonic '
  'preference. Rolls follow the global accidental preference while preserving in-key modal degree identities; '
  'root/bass letter names follow the same preference. The chord editor’s root choices show both degree and pitch name '
  'for the chord’s starting key, updating when the start changes.<br>A score tie joins notation fragments of the same '
  'note. Crossing beats or bars is not the only reason: a real duration that cannot use one symbol may also require '
  'decomposition. Small MIDI rounding errors no longer add tiny fragments, rests or redundant ties; ties needed for '
  'genuine durations remain. These notation adjustments do not alter playback or exported MIDI.'),
 ('段落与和弦进行',
  'Sections and chord progressions',
  '时间轴上半部选中小节后右键 → 段落标识，相同名称也可分别成段。“编辑”主菜单不再提供段落标识入口。<br>右键和弦 → 从此处应用和弦进行，按现有块顺序替换，不新增小节。主音列表按实际音高排列，使用 1–7 加升降号标号，1 '
  '为起始所选小节主音；默认沿用该主音。整段使用所选主音，即使经过谱面调号变化也不自动重解释。可保留已识别节奏型，或统一节奏、力度、发音长度。<br>保存所选和弦也提供主音选择，自动重算罗马数字，保留性质和指定低音。C 调下 '
  'Gm–C–F 相对 C 为 v–I–IV，相对 F 为 '
  'ii–V–I。名称留空时使用数字进行；主音不存进配方，也不修改工程调号。<br>检索所选和弦时，改变主音自动重算根音条件；从设置打开时默认游标小节主音。手动输入支持罗马数字或实际和弦名，如 Gm C '
  'F。罗马数字保持相对关系，实际和弦名随主音换算。忽略性质、低音、转位，允许中间夹有其它和弦，保留 # 与 b '
  '的区别。检索不修改工程或配方。<br>管理窗口的添加/修改只有罗马数字和可选名称，不设置主音。确认保存库，取消放弃本次管理修改。支持 '
  'I/3（指定低音）、V/vi（副属）、V/vi/#5（副属指定低音）。预设按音级排序，共同前缀时短进行在前。包含 21 组公开目录与 5 组原有进行；来源见 docs/PROGRESSIONS.md。',
  'Select bars in the upper ruler and right-click to assign section markers. Repeated names still define separate '
  'sections. Section markers are no longer offered in the main Edit menu.<br>Apply a progression from a chord context '
  'menu to replace existing regions without adding measures. The tonic selector is ordered by pitch and labeled with '
  'modal degrees 1–7 and accidentals; 1 is the first selected measure tonic. All target regions use the chosen tonic '
  'even across score key changes. Keep recognized rhythms or broadcast a pattern, velocity and gate.<br>Capture also '
  'offers a tonic selector and recalculates Roman numerals while preserving quality and bass. Gm–C–F is v–I–IV in C, '
  'or ii–V–I in F. Empty names use the recipe. Tonic is never stored in the recipe or written to score keys.<br>Search '
  'from selected chords rebases the roots when tonic changes; opening from Settings uses the cursor measure tonic. '
  'Type Roman relationships or literal chord names such as Gm C F. Roman queries remain relative; literal chords are '
  'reinterpreted. Root search ignores quality, bass and inversion, allows gaps and preserves #/b spelling. Search '
  'changes neither music nor recipes.<br>Library Add/Edit contains only Roman relationships and an optional name, with '
  'no tonic selector. Confirm saves changes; Cancel discards the session. I/3, V/vi and V/vi/#5 support bass and '
  'applied chords. Recipes sort by degrees, shorter matching prefixes first. The library includes 21 public catalogue '
  'recipes and 5 existing recipes; see docs/PROGRESSIONS.md for sources.'),
 ('调式数字与创作提示',
  'Modal degrees and composition hints',
  '调内音优先使用该调式的七个音级；Lydian 为 1、2、3、#4、5、6、7，Aeolian 为 1、2、b3、4、5、b6、b7。全局升降号偏好只改变调外数字的等音写法，以及卷帘和调性选择框中的音名字母；不把调内 #4 改写成 '
  'b5。谱面音级遵守同样规则。<br>小节调性选择的主音列表有数字辅助，各调式选项显示完整的数字与音名对应；创作时间轴提示只显示主音、调式和拍号。<br>创作和弦悬浮提示按和弦定义排序、去除八度重复，数字相对和弦根音。新增 '
  'mM7（1、b3、5、7）；add2（1、2、3、5）替代 add9，旧生成型迁移后使用密集排列，显式 MIDI 保留实际演奏。M9 保持 1、3、5、7、9。例如 Fmaj7 为 1:F、3:A、5:C、7:E，Cm9 使用 '
  'b3:Eb、b7:Bb、9:D。只列实际 MIDI '
  '出现的和弦音，低音单列。未知和弦按实际音高从低到高去重，仅列音名；名称或性质未知时，节奏显示未知节奏型。制谱模式保留完整音区、调性数字和实际低音提示。<br>独立和弦卷帘打开和弦或拍号调性对话框后，确认和取消均留在原窗口，撤销仍回到编辑来源。',
  'In-key notes keep the seven degrees of their mode: Lydian is 1, 2, 3, #4, 5, 6, 7; Aeolian is 1, 2, b3, 4, 5, b6, '
  'b7. The global accidental preference affects chromatic numbers and letter names in the roll and key selector; it '
  'never respells an in-key #4 as b5. Score degrees follow the same rule.<br>The tonic selector provides degree hints, '
  'and each mode option lists its degrees and letter names. Composition timeline hints show only tonic, mode and '
  'meter.<br>Composition chord hints order actual tones by the chord definition and remove octave duplicates. '
  'Qualities include mM7 (1, b3, 5, 7) and add2 (1, 2, 3, 5); legacy generated add9 migrates to close position while '
  'explicit MIDI is preserved. M9 retains 1, 3, 5, 7, 9. Numbers are relative to the chord root: Fmaj7 shows 1:F, 3:A, '
  '5:C, 7:E; Cm9 uses b3:Eb, b7:Bb, 9:D. Only performed tones appear, with the bass on its own row. Unknown chords '
  'list unique letter names from lowest to highest without interval numbers. An unknown chord name or quality always '
  'yields Unknown pattern. Score mode keeps full registers, key-relative degrees and actual bass information.<br>Chord '
  'and key/meter dialogs opened in a floating chord roll stay with that window on acceptance or cancellation; undo '
  'retains the editing origin.'),
 ('调式标号与四项和弦记忆',
  'Modal labels and four remembered chord settings',
  '卷帘音符、和弦根音与低音、进行主音统一使用 1–7 加升降号。调内音按调式定义保留：Aeolian 是 1、2、b3、4、5、b6、b7；Lydian 的 #4 不随降号偏好改成 '
  'b5。调外自然音级直接使用数字，其余按卷帘升降号偏好。十二个选项按实际音高从起点小节主音开始排列，C 背景下 F 是 '
  '4。<br>和弦编辑仅记住上次确认的性质、节奏型、发音长度和力度。根音默认起点调号主音，低音默认等于根音。改变根音会同步低音，改变低音不改变根音；低音只有十二个实际音高选项。起点、时长和八度取当前和弦，重新生成默认开启，取消不更新记忆。旧版其它记忆字段自动忽略。',
  'Roll notes, chord root/bass choices and progression tonics share degree labels 1–7 with accidentals. Scale tones '
  'keep their modal identities: Aeolian uses 1, 2, b3, 4, 5, b6, b7; Lydian keeps #4 even with flat preference. Other '
  'tones use natural degrees first, then the roll accidental preference. Twelve choices are pitch-ordered from the '
  'anchor tonic; F relative to C is 4.<br>Chord editing remembers only confirmed quality, pattern, gate and velocity. '
  'Root starts at the onset key tonic and bass at root. Root changes move bass; bass changes leave root untouched. '
  'Bass has twelve explicit pitches. Start, duration and octave come from the current chord, and regeneration starts '
  'enabled. Cancel keeps prior memory; retired preference fields are ignored.'),
 ('密集和弦、八度移动与根五交替',
  'Close voicing, octave moves and alternating bass',
  'add2 默认上方音按 1、2、3、5 密集排列，例如 Cadd2 为 C3、D3、E3、G3，另有低音 C2。重新应用持续柱式等节奏型或 add2 性质会恢复默认配器；可随后在卷帘人工调整 voicing。读取旧 add9 '
  '的生成型时使用该排列；已保存的显式 MIDI 不在加载时改写。<br><br>旋律与和弦卷帘的音符右键菜单新增「上移八度」「下移八度」，默认 '
  'Ctrl+↑／Ctrl+↓，可在快捷键设置修改。支持多选、浮窗与撤销，保留起点、时长和力度；任何选中音越过 88 键范围时整体不移动。<br><br>新增「根五交替 · 四分柱式」「根五交替 · 八分柱式」「根五交替 · '
  '反拍柱式」。支持分子为偶数的拍号，分母可为 2、4、8、16：低音每拍按根音、五音交替，每小节重置；例如 4/4 为第 1、3 拍根音，第 2、4 '
  '拍五音。上方演奏完整和弦，分别每个四分音符、每个八分音符或每拍后半拍起音。低音按分母定义一拍，2/2 每拍 1920 tick，4/8 每拍 480 tick；反拍随拍号改变。发音长度应用当前 '
  'gate，末尾按小节和和弦边界裁切。指定低音可替代根音低音；减／增和弦使用其减／增五音。',
  'add2 defaults to close-position upper tones 1, 2, 3, 5: C3, D3, E3, G3 above bass C2 for Cadd2. Reapplying a '
  'pattern or add2 quality restores the default voicing; adjust individual notes afterward. Legacy generated add9 uses '
  'this layout; loading explicit MIDI preserves its voicing.<br><br>Both piano rolls offer Move up/down an octave, '
  'default Ctrl+Up/Ctrl+Down, configurable in Settings. Multiple notes, floating windows and undo are supported. '
  'Timing and velocities remain unchanged; a selection exceeding the 88-key range is rejected as a '
  'whole.<br><br>Alternating bass · Quarter blocks / Eighth blocks / Offbeat blocks support even numerators with '
  'denominators 2, 4, 8 or 16. Bass alternates root and fifth on successive meter beats, restarting each bar. Complete '
  'upper chords play every quarter note, every eighth note, or on the second half of each meter beat. Thus bass beats '
  'last 1920 ticks in 2/2 and 480 ticks in 4/8; offbeats follow the denominator too. Gate applies to both voices, with '
  'notes clipped at bar and region ends. A specified bass can replace the root bass; diminished/augmented chords use '
  'their altered fifth.'),
 ('拍号区间与和弦提示',
  'Meter regions and chord details',
  '跨主音或调式的和弦以 → 分隔罗马数字，/ 仅表示指定低音。创作和弦提示按调性分行，去除音区重复并以和弦根音为 '
  '1；谱面保持实际音区、调性数字与最低音。<br>连续相同拍号形成一个区间。快捷键左右移动在原区间两端裁切，拉伸与合并也受区间边界限制。鼠标可跨过其它拍号区域拖至相同拍号区间，松开在不同拍号区间不修改。粘贴必须与来源拍号完全匹配，并完整放入目标区间。已识别节奏型按完整小节重建后截取；未知节奏型平移 '
  'MIDI 后重新识别；自定义（锁定）不识别节奏型。<br>节奏型选项依起点拍号启用：持续柱式支持全部拍号；四分柱式支持分母 2／4；八分柱式和上／下行琶音要求完整八分音符单位；阿尔贝蒂、低音 + 和弦、反拍型要求分母 2／4 '
  '且含偶数个四分音符。<br>加长小节插入空白，不延长和弦。缩短会删除或截断音符时先确认，取消不改工程，确认可撤销。等时长拍号变更不改旋律时间，但仍按新拍号重新识别和弦。跨拍号分界的和弦自动拆开。<br>卷帘绘成一条的和弦长音片段可整体选中，边缘拖动调整整条外侧，保留内部发音起点与力度。',
  'Roman numerals across tonic or mode changes are separated by →; / is reserved for bass notes. Hover over a chord to '
  'see its actual pitches, scale degrees and bass for each key/mode.<br>Consecutive bars with the same meter form a '
  'region. Keyboard movement crops at both ends of its original region; resizing and merging also respect the '
  'boundaries. Mouse dragging can pass over other meters to a matching region; releasing over a different meter '
  'changes nothing. Each pasted chord must match the source meter exactly and fit fully inside its destination region. '
  'Recognized patterns regenerate from full bars and are cropped. Unrecognized patterns translate MIDI and are '
  'reidentified; Custom (locked) disables pattern recognition.<br>Pattern availability follows the start meter: '
  'sustain supports all meters; quarter blocks support denominators 2/4; eighth blocks and ascending/descending '
  'arpeggios require whole eighth-note units; Alberti, bass + chord and offbeat patterns require an even number of '
  'quarter-note units and denominator 2/4.<br>Longer bars insert silence without extending chords. Shortening that '
  'removes note time requires confirmation and can be undone. Equal-duration meter changes retain melody timing but '
  'still reidentify chords. Chords spanning new meter boundaries are split.<br>Chord-note fragments drawn as a single '
  'long note select together. Dragging an outer edge preserves internal MIDI onsets and velocities.'),
 ('移动边界、暂存与删除小节',
  'Movement boundaries, temporary recovery and bar deletion',
  '连续相同拍号小节形成一个独立编辑区间；曲首、曲尾、拍号更改处都是截断边界。4/4 与 4/8 不相同，3/4 与 6/8 '
  '也不相同。复制记录来源拍号，粘贴前整批检查，每个和弦必须完整落在匹配区间；不合法时菜单禁用，快捷键不修改工程。<br>同一连续区间内可多选左右移动；跨区间多选禁用左右移动，即使两区间拍号相同。混合调内与调外和弦时禁用 '
  'Alt+W/S 调内移动。<br>连续移动保留未裁切的选区原稿。全部移出边界的和弦暂时从演奏与导出中移除；保持选择反向移动可以还原。取消选择、撤销／重做、修改所选和弦或小节结构后结束暂存，此后通过 Ctrl+Z '
  '恢复。暂存不写入工程。<br>拖拽及伸缩过程中仅显示位置预览，松开鼠标才修改 MIDI '
  '并更新识别。键盘移动保持视角，直到最后一个可见选中元素将移出视野；拖拽以光标位置控制边缘滚动。<br>时间轴或谱面右键可删除一个或多个小节。含音符、和弦、歌词或谱面符号时先确认；跨界内容切断，后方音乐前移。受影响的重复压缩会展开，剩余分行与符号重新定位；一次撤销可还原。至少保留一个小节。',
  'Consecutive bars with an identical meter form one continuous editing span. The song start, end and every meter '
  'change are crop boundaries; equal durations do not make signatures equivalent. Copy retains source meters. Paste '
  'preflights the entire batch: each chord must fit completely inside a matching region. Invalid menu actions are '
  'disabled, and keyboard paste makes no changes.<br>Horizontal multi-selection movement requires one continuous '
  'region, including when separated regions share a meter. Alt+W/S is disabled for a mixture of diatonic and chromatic '
  'chords.<br>Consecutive moves retain unclipped selection originals. Completely cropped chords disappear from '
  'performance and export, but reverse movement restores them while selected. Deselecting, undo/redo, editing the '
  'selected chords or changing bar structure ends this temporary state; use Ctrl+Z afterwards. Temporary originals are '
  'not saved.<br>Dragging and resizing show position previews only; MIDI and recognition update on release. Keyboard '
  'movement keeps the view until the last visible selected element is about to leave it; edge scrolling during '
  'dragging follows the pointer.<br>Right-click the timeline or score to delete one or more bars. Bars containing '
  'notes, chords, lyrics or symbols require confirmation. Crossing content is cut, later music shifts earlier, '
  'affected repeat compression expands, and surviving layout and symbols are remapped. One undo restores the edit. '
  'Keep at least one bar.'),
 ('右键菜单、选择与自定义节奏型',
  'Context menus, selection and Custom pattern',
  '设置 → 显示音符音级数字：全局控制两个卷帘音符上的 1–7 及变化音记号，包含停靠、独立窗口与制谱下栏；默认开启并保存为偏好。不改变键盘名称、和弦名称、谱面或 '
  'MIDI。<br>音符与和弦一次只能选择一类；框选音符会取消所有窗口的和弦选择，选和弦会取消音符选择。右键和弦明确选中目标，打开子菜单后仍保持高亮。单选与多选的同类菜单顺序相同，不适用操作禁用：音符属性、和弦属性／根音／性质／低音仅限单选；可识别且拍号相同的和弦支持批量更改内置节奏型；复制、移动、删除、实际试听与自定义锁定可批量操作；合并仅在合法多选时启用。时间轴菜单只有小节拍号、调性、插入及删除小节命令，多选时向后广播与插入禁用。谱面多选小节同样保留完整菜单。<br>节奏型 '
  '→ 自定义：勾选后不识别节奏型，移动只平移、伸缩只裁切，保留实际音符属性。取消勾选仅恢复动态识别，不改 '
  'MIDI。固定半音／八度移动自动勾选，根音半音和调内移动不自动勾选；选择内置节奏型会解除勾选并重建。此状态随工程和复制保存。<br>在和弦钢琴卷帘中编辑会复用已有窗口、切换到对应选项卡并定位，保留播放进度。谱面局部调性与拍号始终在和弦标记上方。',
  'Settings → Show scale-degree numbers on notes controls 1–7 and accidental labels in both piano rolls, including '
  'docked, floating and score-tab views. It defaults to on and is saved as a preference. Keyboard names, chord names, '
  'scores and MIDI are unchanged.<br>Only notes or chords can be selected at a time, across all windows. Selecting '
  'notes clears chord selections and vice versa. Right-clicking a chord selects it and keeps it highlighted while its '
  'menu is open. Menus keep the same order for one or multiple selections, disabling unavailable operations. Note '
  'properties and chord properties, root, quality and bass require one target. Recognized chords with the same meter '
  'support batch pattern changes. Copy, movement, deletion, actual audition and Custom locking support multiple '
  'targets; merging requires a valid group. Timeline menus contain only measure key, meter, insertion and deletion '
  'commands; propagation and insertion are disabled for multiple measures. Score measure menus also retain their '
  'complete list.<br>Pattern → Custom locks out pattern recognition: moves translate events, resizing only crops, and '
  'note attributes remain intact. Unchecking resumes recognition without altering MIDI. Fixed semitone/octave '
  'transposition enables Custom automatically; root and diatonic movement do not. Applying a built-in pattern clears '
  'the lock and rebuilds notes. The flag is saved in projects and copied with chords.<br>Edit in chord piano roll '
  'reuses the existing window, selects its tab and locates the chord without seeking playback. Local key and meter '
  'labels appear above chord symbols in the score.'),
 ('工作区与悬浮窗口',
  'Workspace and floating windows',
  '导航器位于播放栏下方、卷帘设置上方，以绿色旋律线与蓝色和弦线同时显示两轨全曲。创作界面继续显示时间轴、旋律钢琴卷帘、和弦轨、和弦钢琴卷帘及轨道音量。顶部“视图”菜单独立控制显隐；和弦卷帘、力度窗格默认隐藏。两个卷帘右上角使用相同的悬浮／停靠图标。悬浮旋律窗口保留下方和弦轨，悬浮和弦窗口在自身时间轴下显示与主轨一致的结构卡片；数据同步，选择与高亮独立。创作与制谱的两个悬浮卷帘均提供独立时间轴、播放／暂停、回放、循环、跟随和速度控件。播放、位置、循环选区和速度全局共享；未同步时跟随独立。在播放栏最右侧“其它选项”分别勾选“同步时间轴”，先采用主界面跟随状态，再与主时间轴双向同步缩放、滚动和跟随开关；取消后独立控制。主时间轴始终保留自身视窗，即使两个卷帘都悬浮也能浏览；停靠卷帘始终双向同步主时间轴，重新停靠时采用主视窗。任一停靠卷帘都有可用的设置栏。<br>创作中两个卷帘停靠时共用底端水平滚动条，以及音高范围、键高、缩放、智能／绘制工具和网格设置。已用音高取两轨的并集。两个悬浮卷帘都可独立浏览，改变一个窗口的同步开关不会更改另一个。调整键高时，以音符区的纵向中心为锚点，不把标尺和和弦结构栏计入中心；共享键高时两个卷帘分别保留自身中央音高。<br>制谱下栏提供“旋律卷帘／和弦卷帘／歌词／结构逻辑”四个选项卡。右上角悬浮与关闭按钮只操作当前选项卡；浮窗可单独停靠或关闭。首次进入显示全部选项卡，之后切回制谱恢复上次布局。主界面跟随开关适用于谱面与当前选中的停靠卷帘；切换到原先未选中的卷帘时再更新其跟随位置。悬浮卷帘使用与创作模式相同的独立跟随和同步时间轴选项。“视图”菜单随模式切换，可重新打开各面板。歌词提交、删除和撤销即时更新当前谱面的歌词呈现。右键谱面可直接进入对应卷帘。悬停谱面和弦显示实际和弦音的数字级数、字母音名与八度，以及实际最低音。大小控件支持 '
  '+/−，面板之间可拖动分隔线。',
  'The overview sits below transport and above piano-roll settings. Green melody lines and blue chord lines show both '
  'complete tracks. Composition continues with the timeline, melody roll, chord lane, chord roll and volumes. View '
  'controls visibility; the chord roll and velocity lanes start hidden. Both rolls use the same Float/Dock icon at the '
  'upper right. The floating melody roll retains its chord lane. The floating chord roll displays matching chord cards '
  'below its own timeline; data is shared, while selection and highlighting remain local. In both Compose and Score, '
  'floating rolls have their own timeline and Play/Pause, Replay, Loop range, Follow playhead and Tempo controls. '
  'Playback, position, loop selection and tempo are shared. Following is independent when timeline sync is off, and '
  'linked to the main view when on. Enable Sync timeline in Other options at the far right of the transport row to '
  'link scrolling, zoom and follow-playhead state to the main view in both directions. The main timeline retains its '
  'own viewport even with both rolls floating. Docked rolls always synchronize with the main timeline and adopt its '
  'viewport when redocked. Every docked roll retains an available settings bar.<br>Docked composition rolls share a '
  'bottom horizontal scrollbar, pitch range, key height, zoom, Smart/Draw tool and grid settings. Used pitches '
  'includes both tracks. Both floating rolls can be browsed independently; changing one Sync timeline switch does not '
  'change the other. Key-height changes preserve the vertical center of the note area, excluding the ruler and chord '
  'structure header. Shared key-height changes retain each roll’s own central pitch.<br>Score mode has four tabs: '
  'Melody roll, Chord roll, Lyrics and Score structure. Float or close affects only the current tab. Each floating '
  'pane can dock or close independently. The first visit shows all tabs; subsequent visits restore the previous '
  'layout. Main Follow playhead applies to the score and the selected docked roll; switching to an inactive roll '
  'updates its followed position then. Floating rolls use the same independent follow and timeline-sync options as '
  'Compose. The View menu changes with the mode and reopens individual panels. Applied lyric edits, deletion and undo '
  'update the displayed lyric presentation immediately. Right-click the score to open the corresponding roll. Hover '
  'over a chord symbol to see its actual tones as scale degrees and letter names with octaves, plus the lowest '
  'sounding pitch. Size controls have +/− buttons; drag splitters to resize panels.'),
 ('和弦轨联动与高亮',
  'Chord lane layout and highlighting',
  '显示／停靠和弦卷帘时取消视图 → '
  '和弦轨的勾选，悬浮后恢复勾选。关闭独立卷帘只隐藏窗口；再次勾选视图中的对应卷帘会将它放回主界面。两个卷帘的悬浮、停靠和显隐变化恢复每个窗口一条和弦轨的默认布局，普通刷新不重设，用户可手动显示两条。悬浮旋律自带和弦轨，独立于主界面勾选，音乐数据同步。旋律高亮只取下方最近的和弦轨：主和弦轨显示时优先，隐藏时取同一窗口的和弦卷帘结构轨；悬浮旋律只取自己的和弦轨。独立和弦窗口不影响旋律高亮。',
  'Showing or docking the chord roll unchecks View → Chord lane; floating it checks the main lane again. Closing a '
  'floating roll hides it; checking that roll in View brings it back to the main page. Changes to roll visibility or '
  'docking restore one default chord lane per window. Ordinary refreshes preserve manual overrides, so both '
  'main-window lanes can be shown. A floating melody roll has its own synchronized chord lane, independent of the main '
  'checkbox. Melody highlighting uses only the nearest lane below it: the main lane when shown, otherwise the docked '
  'chord roll structure lane. A floating melody uses only its own lane. The floating chord window never highlights the '
  'melody.'),
 ('独立窗口与和弦力度',
  'Floating windows and chord velocity',
  '独立窗口顶部依次为停靠、最小化、最大化／还原、关闭；下方播放栏最右侧为“其它选项”。视图中的卷帘勾选仅表示它在主界面显示：悬浮自动取消勾选，停靠自动勾选。关闭任一独立卷帘只隐藏它；勾选视图总是将卷帘显示在主界面。右键进入卷帘、E '
  '切换输入轨和撤销定位沿用已有独立窗口；语言切换和制谱往返保留布局与显隐。主窗口和独立卷帘共用任务栏应用标识，Windows '
  '合并任务栏按钮时，一个图标可预览全部窗口。<br>和弦轨右键、主界面视图或独立窗口其它选项中可显示“和弦轨力度窗格”。每个和弦一根力度柱；拖动会统一设置其内部所有音符的力度，多选时同时修改所选和弦，支持撤销。和弦卷帘底部的力度窗格仍用于逐音调整。力度改变 '
  'MIDI 发音强度，与底部轨道音量独立。',
  'Floating title bars contain Dock, Minimize, Maximize/Restore and Close, in that order. Other options sits at the '
  'right end of the transport row below. A roll is checked in View only when shown on the main page: floating unchecks '
  'it and docking checks it. Closing either floating roll hides it; checking View always shows it on the main page. '
  'Edit in piano roll, E and undo navigation reuse existing floating windows. Language and workspace changes retain '
  'layout and visibility. All windows use one application identity: Windows taskbar grouping presents one icon with '
  'previews of all windows.<br>Show Chord lane velocity from its context menu, the main View menu, or floating Other '
  'options. One stem per chord sets all its notes to the same velocity; multiple selections are edited together. Undo '
  'is supported. The velocity lane below the chord piano roll still edits individual notes. Velocity affects MIDI note '
  'dynamics independently of track volume.'),
 ('时间尺、循环与鼠标拖屏',
  'Time ruler, loops and mouse navigation',
  '时间轴上半部第一行显示小节号及段落标识，第二行显示拍号及调性，两行分别水平对齐；相同拍号与调性不重复显示。上半部以整小节框选和右键编辑；下半部时间尺有独立背景与分隔线。时间尺单击吸附定位，不改变播放或暂停状态；拖动只设置循环、不移动定位线，同时开启“循环选区”。Shift '
  '连续扩展，Ctrl '
  '不追加离散循环；框选后可拖动左右边界伸缩。关闭循环清除范围，重新开启不会恢复旧选区。框选其它音符、和弦、小节均保留循环。时间尺不提供右键操作。<br>时间轴上半部、智能工具的卷帘和和弦轨支持右键拖动框选，松开后打开对应菜单；不拖动时为普通右键。卷帘和和弦轨中键按住拖屏；卷帘可横纵移动，和弦轨只追踪水平。手动浏览卷帘时，橙色播放游标离开正在浏览的卷帘后才取消跟随；仍在视野内时不立即拉回视角。谱面浏览改为检查游标所在小节：该小节完全离开谱面视口便取消跟随，不受下方卷帘是否仍显示游标影响。框选拖至左右边缘会持续滚动，卷帘还支持上下边缘滚动；时间轴上下两区都支持边缘滚动。<br>所有窗口底部共用一行信息与音量控制，旋律、和弦音量与静音同步。信息最多 '
  '80 字符，窄窗口按宽度省略，不换行。“设置 → 显示底部信息提示”默认开启，可单独关闭提示而保留音量。',
  'The upper timeline places bar numbers and sections on its first row, with meter and key aligned on its second row. '
  'Unchanged meter/key labels remain suppressed. Select complete bars here for editing. A divider and distinct '
  'background separate the lower time ruler. Click it to snap the position marker without changing playback state. '
  'Drag to set a loop without moving the position marker; this enables Loop selection. Shift extends a continuous '
  'range; Ctrl does not add disjoint ranges. Drag either loop edge to resize. Disabling Loop clears the range; '
  'enabling it again never restores the old range. Note, chord and bar selections preserve the loop. The lower ruler '
  'has no right-click actions.<br>Right-drag in the upper timeline, a Smart-tool piano roll or chord lane selects a '
  'range and opens its context menu on release. A stationary right-click opens the usual menu. Middle-drag pans both '
  'axes in piano rolls and horizontally in chord lanes. Manual piano-roll browsing disables following when the orange '
  'playhead leaves that roll; the view does not jump back while the cursor remains visible. Score browsing instead '
  'checks the measure containing the playhead: following stops once that measure leaves the score viewport completely, '
  'regardless of whether a docked roll still shows the playhead. Selection near an edge scrolls continuously: '
  'horizontally in both timeline bands and chord lanes, and on both axes in piano rolls.<br>Every window shares a '
  'single footer row with status and synchronized melody/chord volume and mute controls. Hints are limited to 80 '
  'characters and elided to fit narrow windows without wrapping. Settings → Show footer hints is on by default; '
  'turning it off keeps the mixer controls.'),
 ('方向键、三连音与边缘框选',
  'Arrow navigation, triplets and edge selection',
  '方向键 ←／→ 浏览当前编辑器时间轴；橙色播放游标离开正在浏览的卷帘后才取消跟随，不移动音符、和弦或播放位置。A／D 移动选中元素，视角在最后一个可见选中元素将移出视野时跟随。Shift+3 '
  '切换吸附格点三连音，不改变输入音符时值；停靠卷帘共享设置，悬浮卷帘保留各自设置。上述按键可在设置 → '
  '快捷键设置中修改，文字输入框内不触发。<br>从空白处拖动框选和弦或音符，将指针停留在视角边缘时缓慢滚动：和弦轨横向滚动，卷帘可横向和纵向滚动。选区起点固定在音乐时间和音高行，已经滚出视角的元素仍可保留选中。松开鼠标、按 Esc '
  '或隐藏编辑器会停止边缘滚动并清除框选框。<br>所选和弦全部可识别且拍号相同时，右键 → 节奏型可批量应用，即使它们被不同拍号的小节隔开。拍号必须完全相同，例如 3/4 与 6/8 '
  '不等同；不支持该拍号的节奏型禁用。保留各和弦的根音、性质、低音、区间和默认力度，按小节节奏型重建实际音符并解除自定义锁定。整批修改只需一次撤销。',
  'Left/Right scroll the active editor. Following is disabled when the orange playhead leaves that piano roll, without '
  'moving notes or chords or seeking. A/D move selected events, following the trailing selection extremity when '
  'needed. Shift+3 toggles triplet snapping without changing input note duration. Docked rolls share settings; '
  'floating rolls keep their own. These keys can be changed in Settings → Keyboard shortcuts and do not trigger inside '
  'text fields.<br>Drag from empty space to select chords or notes. Holding the pointer near an edge scrolls '
  'gradually: horizontally in chord lanes, horizontally and vertically in piano rolls. The selection origin stays '
  'anchored to musical time and pitch rows, retaining selected events that have scrolled out of view. Release, Escape '
  'or hiding the editor stops scrolling and clears the rectangle.<br>If all selected chords are recognized and share '
  'exactly the same meter, Pattern supports batch changes, even in regions separated by a different meter. 3/4 and 6/8 '
  'are distinct. Unsupported patterns are disabled. Each chord retains its root, quality, bass, region and default '
  'velocity; performed notes are rebuilt from the bar pattern and Custom locks are cleared. One undo restores the '
  'entire batch.'),
 ('快捷键与定位线',
  'Keyboard shortcuts and position marker',
  '在主界面与独立卷帘中，Ctrl+C／X／V 复制／剪切／粘贴选中的音符或和弦，Ctrl+A 全选当前编辑目标。文本输入框使用自己的剪贴板与撤销记录。<br>默认 W／S 升降音符一个半音，Alt+W／S '
  '调内移动一级；和弦轨选中和弦时，W／S 更换根音一个半音，Alt+W／S 调内移动一级；两者均恢复根音低音。C 编辑选中和弦；Tab 选择下一和弦，最后一个之后回到第一个，不定位播放游标。A／D '
  '按当前吸附网格左右移动音符或和弦。右键音符同时提供半音和调内移动。Q 在智能／绘制工具间切换，E 切换旋律／和弦输入位置（需要时呼出或激活对应窗口）。空格播放／暂停，R 回到定位线并保持播放状态，Ctrl+Home '
  '返回曲首并暂停。Shift+S 二等分，Alt+Shift+M 合并，Delete 删除。设置 → '
  '快捷键设置可修改或清空这些键位，输入冲突组合会列出原功能，确认后清除其绑定并转给当前功能；取消保留原设置。歌词、数值、下拉框和对话框输入不会触发编辑命令。<br>右键音符或空白网格，可“在定位线处粘贴音符”；和弦菜单提供对应粘贴与插入选项。播放中定位线为固定蓝色虚线，暂停时为当前橙色位置线；不会使用正在移动的播放游标。空白卷帘悬停为箭头，开始框选才显示十字。',
  'In the main and floating editors, Ctrl+C/X/V copy/cut/paste the selected notes or chords; Ctrl+A selects all of the '
  'current editing target. Text fields use their own clipboard and undo history.<br>Defaults: W/S move selected notes '
  'by one semitone; Alt+W/S move them by one scale step. With chords selected in a chord lane, W/S change the root by '
  'one semitone; Alt+W/S move by scale degree. Both restore root-position bass. C edits the selected chord; Tab '
  'selects the next chord, wrapping to the first without seeking. A/D move either selection horizontally by the '
  'current snap grid. Note context menus offer both semitone and scale-step movement. Q toggles Smart/Draw; E switches '
  'melody/chord input focus, revealing or activating the corresponding roll when needed. Space plays/pauses; R returns '
  'to the position marker without changing playback state; Ctrl+Home returns to the beginning and pauses. Shift+S '
  'splits, Alt+Shift+M merges, and Delete deletes. Settings → Keyboard shortcuts changes or clears these bindings and '
  'lists the actions affected by a conflicting assignment. Confirm to clear their old binding and transfer the key, or '
  'cancel to keep the previous settings. Fixed system/input keys remain reserved. Text, numeric, combo-box and dialog '
  'input never triggers editing commands.<br>Right-click notes or blank grid space to paste notes at the position '
  'marker; chord menus provide matching paste and insert commands. During playback this means the fixed blue dashed '
  'anchor, and while paused it means the orange current-position line, never the advancing playhead. Blank roll hover '
  'uses an arrow; the crosshair appears only when selecting.'),
 ('统一快捷键与冲突处理',
  'Unified shortcuts and reassignment',
  '设置 → 快捷键设置包含文件操作、剪贴板、选择、Tab '
  '和备用键位。右键菜单与主菜单右侧统一显示当前绑定，多个键位并列显示；清空后隐藏。更改即时应用到主窗和独立卷帘。冲突提示会明确列出原功能，确认后清除原绑定并转给当前功能；取消提示恢复原值，取消整个设置窗口则不保存这次修改。文本框保留自身编辑行为；Esc、Enter、Shift+Tab、Alt+F4 '
  '等固定键在设置底部只读列出。',
  'Settings → Keyboard shortcuts includes file, clipboard, selection, Tab and alternate bindings. Main and context '
  'menus show the current keys in an aligned column, including alternatives; clearing a binding removes its label. '
  'Changes apply immediately in main and floating windows. Conflicts name the affected actions: confirm to clear their '
  'previous binding and transfer the key, or cancel to restore the old value. Canceling the entire dialog discards all '
  'changes. Text fields retain their own editing behavior; fixed keys such as Esc, Enter, Shift+Tab and Alt+F4 are '
  'listed read-only at the bottom.'),
 ('颜色与可视区域',
  'Colors and visibility',
  '旋律卷帘：取整个和弦区间出现过的和弦音级，覆盖该区间全长。和弦卷帘：取当前和弦块内出现过或持续经过的旋律音级，覆盖整个和弦块；没有和弦块时不标记旋律匹配音。两者再与当前调式组合成四色。<br>设置 → 卷帘染色 → '
  '自定义色彩方案，分别设置浅色／深色的背景色与音符色。文字自动选择深浅色。力度窗格默认隐藏；顶部“视图”菜单控制页面元素与各卷帘的力度窗格；全部 88 '
  '键／已用音高、键高和缩放位于卷帘上方。<br>鼠标放在时间轴、和弦轨或卷帘上时，Ctrl／Shift＋滚轮以鼠标下的时间位置为中心横向缩放，三处规则一致；右上角 −／＋ '
  '以音符网格可视区中央为中心。到达曲首后固定左边界缩小。最大每四分音符 2048 像素，六十四分音符宽 128 像素（相应三连音约 85 像素）。高倍率时间标尺显示“小节.拍＋拍内分数”，例如 1.2+1/16 '
  '表示第一小节第二拍之后的十六分之一拍。Alt＋滚轮水平滚动。曲尾之后的留白只供浏览，不添加小节。',
  'Melody roll: pitch classes from the entire chord region color its full duration. Chord roll: melody pitch classes '
  'sounding anywhere within a chord region color that entire region; empty regions have no melody-match tint. Both '
  'combine these sets with the active scale into four categories.<br>Settings → Piano roll coloring → Custom colors '
  'edits background and note colors separately for light and dark themes. Text contrast adapts automatically. Velocity '
  'is hidden by default. The top View menu controls page elements and each velocity lane. Pitch range, key height and '
  'zoom sit above each roll.<br>Ctrl/Shift+wheel over the timeline, chord lane or a piano roll zooms time around the '
  'pointer with the same rules; the upper-right −/+ buttons zoom around the visible note grid’s center. Once the '
  'beginning is reached, zooming out keeps the left edge fixed. The maximum is 2048 pixels per quarter note: 128 '
  'pixels per 64th note, or about 85 for a 64th-note triplet. At fine zoom, labels use bar.beat + a fraction of that '
  'beat: 1.2+1/16 means one sixteenth of a beat after beat 2 in bar 1. Alt+wheel scrolls horizontally. Blank viewing '
  'space beyond the end does not add bars.'),
 ('播放与音源',
  'Playback and sounds',
  '编辑音符、和弦、拍号、速度和排版，以及撤销／重做时，播放继续；未受影响的长音保持，后续事件在提交编辑后更新。空格播放／暂停。回放按钮单击返回已记录的播放起点；播放中继续播放，暂停时保持暂停。双击返回开头并暂停。播放时蓝色虚线保留起点，橙色实线随当前进度移动；暂停后只显示当前位置。同一主界面的视图始终共用“跟随播放游标”。创作中控制主时间轴与停靠卷帘；制谱中控制谱面和当前选中的停靠卷帘选项卡，未选中的卷帘可在切换到该页时再跟随。两种模式的独立卷帘浮窗均有自己的跟随开关；取消“同步时间轴”后独立浏览，勾选时先采用主界面的跟随状态，此后跟随开关双向联动。拖动滑块、导航器、中键拖屏、滚轮或方向键浏览后，按操作来源决定是否取消跟随。浏览谱面时，游标所在小节只要还有部分出现在谱面视口中便保留跟随；小节完全离开谱面视口即取消，下方卷帘可见的游标不再阻止取消。浏览卷帘时，橙色播放游标离开该卷帘即取消，制谱与创作使用同一机制，避免被谱面拉回最左侧。拖住谱面滑块时暂缓自动跟随；轻微浏览保留手动视角，不立即拉回。蓝色虚线起点不参与判定。同步的浮窗共用跟随状态；独立浮窗只影响自身。播放位置、记录起点与播放状态均不变；需要恢复时重新勾选。循环只使用时间尺的独立选区，不使用小节或音符选区。关闭循环会清除该选区，重新勾选时需重新框选时间尺。播放中取消循环会从当前位置顺着越过选区末尾，继续到曲尾，持续音不重触发。播放中开启循环时，尚未经过选区末尾则在该末尾开始重复；已经经过末尾则本次继续，下一次从选区开始播放时生效。旋律和和弦各有音量与静音。设置中选择 '
  'MIDI 音源和 GM 音色。Windows MIDI 打开音源和停止时会清理本程序所用通道的持续音状态，避免高音在松键或停止后残留；仅停止播放时不切断要求保留的试听。Windows MIDI '
  '的具体音色由系统或设备提供。点击试听至少约 650 毫秒，按住琴键或 Smart 音符持续发声；Draw 新建按住可延长试听，删除不发声。新点击立即替换旧试听。单击和弦或 Tab 切换试听一小节柱式和弦，至少 650 '
  '毫秒，长按可延长。右键“试听实际和弦”才按实际 MIDI '
  '播放；多选按时间顺序紧邻试听。在时间轴或制谱谱面点击新位置时，播放中继续、暂停时保持暂停，虚线起点随点击更新。卷帘音符实体、琴键、和弦轨及其右键菜单不改变播放位置；卷帘格点纵线的窄缝单击可定位。静音只影响本机播放与试听，轨道音量与音色写入 '
  'MIDI。',
  'Editing notes, chords, meter, tempo or layout, and undo/redo, keeps playback running. Unchanged sustains are '
  'retained and upcoming events update after the edit is committed. Space plays or pauses. Replay returns to the '
  'recorded anchor without changing the playing or paused state. Double-click to return to the beginning and pause. '
  'During playback a blue dashed line marks the anchor, while an orange line shows the current position. The anchor '
  'line disappears when paused. Views on the same main page always share Follow playhead. In Compose it controls the '
  'main timeline and docked rolls. In Score it controls the score and the selected docked piano-roll tab; an inactive '
  'roll can catch up when its tab is selected. In both modes, each floating roll has its own follow switch. With Sync '
  'timeline off it can browse independently; enabling sync copies the main follow state and then links the switches in '
  'both directions. After scrollbar, overview, middle-drag, wheel or arrow-key navigation, cancellation depends on the '
  'view being browsed. In the score, following stays enabled while any part of the measure containing the playhead '
  'remains in the score viewport; it stops once that measure leaves completely, even if a docked roll still shows the '
  'playhead. In a piano roll, following stops when the orange playhead leaves that roll. Compose and Score use the '
  'same roll behavior, preventing the score from pulling the cursor back to the left edge. Automatic score following '
  'pauses while its scrollbar is held. Small manual adjustments remain in place without an immediate jump back. The '
  'blue dashed anchor does not count. Synchronized floats share follow state; an independent float affects only '
  'itself. Playback position, anchor and state remain unchanged. Check Follow playhead again to resume following. Loop '
  'uses the separate time-ruler selection, never bar or note selections. Disabling Loop clears its range; re-enabling '
  'it requires a new ruler selection. Turning it off during playback continues through the former boundary to the end '
  'of the song without retriggering sustained notes. Turning it on before the selection ends repeats at that end; if '
  'playback has already passed the end, the current pass continues and looping applies the next time playback starts '
  'in the selection. Melody and chords have independent volumes and mute. Choose MIDI devices and GM programs in '
  'Settings. Windows MIDI clears sustain and sounding-note state on the channels used by this application when opening '
  'or stopping, preventing held high notes from remaining after release or Stop. Stopping playback alone retains '
  'auditions when requested. The actual Windows MIDI timbre is supplied by the system or device. Click audition lasts '
  'at least about 650 ms; holding piano keys, Smart notes or newly drawn notes sustains it. Draw deletion is silent. A '
  'new click immediately replaces the previous audition. Clicking a chord or pressing Tab previews a one-bar block '
  'chord; Audition actual chords plays real MIDI timing, velocities and patterns, consecutively for multiple '
  'selections. Clicking a new timeline or score position preserves the playing or paused state and moves the dashed '
  'anchor. Note bodies, piano keys, chord lanes and chord context menus never seek. A stationary click in a narrow '
  'vertical grid gap can seek. Mute affects local playback and audition; track volume and programs are exported to '
  'MIDI.'),
 ('统一字号与合成音源',
  'Global score fonts and synth packs',
  '立体简谱小节内各拍等长，小节宽度随密度分配；普通谱行使用全局一致的字号。传统简谱按可见符号均匀排列，强制合行按小节数比例缩小。卷帘默认键高 20。<br><br>0.44 附带三组合成音源、37 '
  '个预设，完整解压即可使用。以后扩展时，把完整音源文件夹复制到程序同级 synths/，打开 设置 → 音源与音色 → '
  '重新扫描并保存。可添加额外扫描目录，结果和默认选择自动保存，下次启动读取缓存。新装、移动或更新音源后需重新扫描；替换 DLL 前关闭程序。<br><br>基础包有 15 个 FM 键盘、拨弦、贝斯与弓弦预设；风琴与管乐包有 8 '
  '个预设；扩展乐器包另有 14 个钟琴、元音、竖笛、吹瓶、西塔琴和拨弦模型。编辑播放、试听、监听与离线 MP3 共用所选合成音源。程序本体不包含采样音源；未装音源包仍可编辑、保存、导出 PDF/MIDI，并使用 Windows '
  'MIDI。旧 samples/builtin 工程迁移为基础合成包，缺失音源不会阻止打开工程。<br><br>MP3 导出提供商用版权提示和 .mp3.licenses.txt；STK '
  '开源许可文本与源码随音源包提供。软件许可不替代作品、歌词与其他素材权利。普通 VST/CLAP 不能直接复制加载；详情见 docs/SOUNDBANKS.md。',
  'Spatial bars have equal beats and widths based on density, with a uniform global font. Traditional notation spaces '
  'visible symbols evenly; forced rows shrink by their bar-count ratio. Piano-roll keys default to 20 '
  'pixels.<br><br>In 0.44, three lightweight packs with 37 presets are bundled. Extract everything to use them '
  'immediately. To add more packs, copy a complete folder into synths/ beside the executable, then use Settings → '
  'Sound sources and instruments → Rescan and save. Extra directories are supported. The index and defaults persist; '
  'startup reads the cache. Rescan after adding, moving or updating packs; close the application before replacing a '
  'DLL.<br><br>Essentials provides 15 FM keyboard, plucked/bass and bowed-string presets. Colors adds 8 organ, bell, '
  'bar and wind presets; Acoustic Models adds 14 bell, vowel, recorder, bottle, sitar and plucked-string models. '
  'Playback, audition, monitoring and offline MP3 share the selected synth. The application contains no sample bank. '
  'Without packs, editing, saving, PDF/MIDI export and installed Windows MIDI remain available. Legacy samples/builtin '
  'projects migrate to Essentials; missing packs do not prevent opening projects.<br><br>MP3 export displays '
  'commercial-use notices and writes a .mp3.licenses.txt file. Each pack includes its STK license and source. Software '
  'licenses do not replace rights in compositions, lyrics or other material. Standard VST/CLAP plugins cannot be '
  'copied directly into this host; see docs/SOUNDBANKS.md.'),
 ('按格式导出',
  'Export by format',
  '文件 → 导出提供 PDF、MIDI、MP3，各自打开独立导出窗口并暂停播放。PDF 只按当前谱面页码范围导出，不使用小节、循环或段落范围。<br>MIDI 与 MP3 '
  '可选旋律、和弦或两轨，范围可选全部、小节、当前循环；已有段落标识时还可按段落导出。范围内音符裁切到边界，输出从零开始；工程不变。MIDI 保留音色、音量、速度、拍号和段落标识。<br>MP3 '
  '提供两种方式：所选合成音源离线渲染，保留逐音力度和轨道音量；导出前显示商用版权提示，并保存署名文件；Windows MIDI '
  '实时录制使用默认系统音源与输出回录，需等待整段时长，同一输出设备上的其它声音也会录入，导出前请停止其它声音。两种方式均可取消；取消不替换已有文件。录音、混音和母带制作建议在 Cakewalk Next 等专业 DAW 中继续。',
  'File → Export provides PDF, MIDI and MP3, each opening a separate export dialog and pausing playback. PDF exports a '
  'page range from the current score layout only, without bar, loop or section ranges.<br>MIDI and MP3 export melody, '
  'chords or both, over all music, selected bar numbers or the current loop; section export is available when markers '
  'exist. Notes are clipped to the range and output starts at time zero without changing the project. MIDI retains '
  'programs, volumes, tempo, meters and section markers.<br>MP3 offers two methods: selected-synth offline rendering '
  'preserves velocities and track volumes, displays commercial-use conditions and writes a credits file. Windows MIDI '
  'real-time capture uses the default system sound source and output loopback, taking the full duration; other audio '
  'on the same device is also captured, so stop it first. Both methods support cancellation without replacing an '
  'existing file. Continue audio recording, mixing and mastering in a dedicated DAW such as Cakewalk Next.'),
 ('导出与迁移',
  'Export and migration',
  'PDF 使用与屏幕相同的矢量排版，始终白底。MIDI 支持旋律／和弦独立输出或合并分轨；DAW 迁移包含独立分轨和时间轴说明。谱面压缩、强制合行和演奏提示均不修改 MIDI 音符。分发时保留 Lingfeng.exe 与 '
  '_internal 文件夹。',
  'PDF uses the same vector layout as the screen, always on white paper. Export melody, chords or a multi-track MIDI '
  'file; the DAW bundle includes separate tracks and a timeline guide. Score compression, forced systems and '
  'directions never change MIDI notes. Keep Lingfeng.exe together with its _internal folder when distributing.'),
 ('休止符与立体简谱',
  'Rests and spatial jianpu',
  '三种谱式均以 0 填充休止，包括开头与全休止小节。立体／紧凑简谱的休止符 0 和说唱 x 位于每行音域中间，不依附前音高度。紧凑模式逐行计算，保留包住音域的 1／5 边界。默认仅显示 1／5 '
  '横线，谱面选项可开启其它调内横线。立体与紧凑简谱按密度分配小节宽度，每个小节内按实际时间等距排列，各拍长度相同；小节作为整体换行。全谱数字、休止符和说唱 x '
  '共用字号，和弦、歌词及节奏符号随之等比缩放。首次进入制谱或切换谱式时自动设置推荐字号；手动修改后会保存，也可点击「推荐字号」重新计算。字号选项显示并限制在当前布局的不重叠上限，保持每行小节数；有效字号就是实际全局字号，音高间距保持设置值。布局改变会重新计算上限，旧工程超限字号会调整并保存为实际值。强制合行记录原每行小节数，按「原每行小节数 '
  '÷ 合并后可见小节数」缩放，比例最大为 1；例如 4 小节合为 6 小节时使用全局字号的 2/3。传统简谱按音符、休止及延音横线等可见符号分配均匀位置，附点和升降号与音符一起保留空间。屏幕、点击定位、播放游标与 PDF '
  '使用同一布局。',
  'All styles fill silence with 0, including leading rests and silent measures. Spatial and compact scores center '
  'rests and unpitched rap x symbols within each system’s pitch range. Compact ranges are calculated per system and '
  'preserve enclosing 1/5 boundaries. Only 1/5 horizontal lines appear by default; score options can show other scale '
  'lines. Spatial and compact scores allocate bar widths by density and keep time linear within each bar, so its beats '
  'are equally wide. Whole bars stay on one line. Digits, rests and rap x share a score-wide font; chords, lyrics and '
  'rhythm symbols scale with it. First entering Score mode or changing notation style applies a recommended font. '
  'Manual changes persist; Recommend font recalculates it. The font selector shows and enforces the current '
  'overlap-free maximum while keeping measures per line fixed. Accepted values are the actual global size. Layout '
  'changes recalculate the cap; oversized legacy values are corrected and saved. Pitch spacing remains as set. Forced '
  'rows remember the original bars-per-line count and scale by original count divided by merged visible count, capped '
  'at 1. Merging 4-bar rows into 6 bars uses two-thirds of the global font. Traditional notation allocates evenly '
  'spaced positions to notes, rests and extension dashes, reserving room for accidentals and dots. Screen, hit '
  'testing, playback and PDF share the same layout.'),
 ('谱面缩放、拍间分隔与更新',
  'Score zoom, beat groups and refresh',
  '传统简谱在同一拍内紧凑等距排列，拍与拍之间增加留白；分组按拍号分母计算，支持切分、附点、延音横线和强制合行。制谱工具栏新增页面缩放，可选「填满屏幕」（适合可视宽度）、「整页显示」及百分比。Ctrl+鼠标滚轮围绕指针缩放，按住鼠标中键可左右、上下拖动；普通滚轮仍滚动页面，Alt+左键拖动也保留。缩放只改变查看比例，不改变字号、布局或 '
  'PDF。谱面手动滚动、缩放或拖屏后，游标所在的小节完全离开谱面视口时取消跟随；小节仍部分可见便保留。拖住谱面滑块时暂缓自动跟随，避免拖动被自动滚动打断。<br><br>音乐内容在切入制谱时生成并保留：普通卷帘音符、和弦修改不会实时重排，回到创作再切入制谱后同步；作品信息中的标题、歌词提交与撤销，以及字号、谱式、合行和符号等直接谱面操作即时响应。标题更新不会把尚未同步的音乐编辑带入当前谱面。打开另一份工程会生成其谱面。制谱中的 '
  'PDF '
  '导出使用当前显示谱面，MIDI/音频导出使用最新工程音乐。<br><br>下方编辑器停靠且显示卷帘时，双击旋律或和弦卷帘上方的小节编号，上方滚动到相应谱行并使目标小节进入视野，已有可见位置不强制居中。压缩隐藏的小节定位到对应可见段；浮动卷帘与创作模式不触发此联动。音符双击编辑和下层时间标尺双击播放保持原操作。',
  'Traditional notation keeps symbols close and evenly spaced within a beat, with extra space between beat groups. '
  'Groups follow the meter denominator and support syncopation, dots, extension dashes and forced rows. Score zoom '
  'offers Fill width, Fit page and percentages. Ctrl+mouse wheel zooms around the pointer; holding the middle button '
  'pans in both directions. Ordinary wheel scrolling and Alt+left-drag remain available. Zoom changes the view only, '
  'leaving engraving and PDF size unchanged. After manual score scrolling, zooming or panning, following stops once '
  'the measure containing the playhead leaves the score viewport completely; a partly visible measure keeps following '
  'enabled. Automatic score following pauses while its scrollbar is held, so it cannot interrupt the '
  'drag.<br><br>Music is engraved when entering Score mode. Regular note and chord edits in either workspace do not '
  'reflow the displayed score; switch to Compose and back to Score to synchronize them. The project title, lyric '
  'apply/undo and direct font, style, row and symbol controls update immediately. Updating a title does not import '
  'pending music edits into the displayed score. Opening a different project creates its own score. PDF export from '
  'Score uses the displayed score; MIDI and audio use the latest project music.<br><br>With a piano roll docked below '
  'the score, double-click its upper measure-number band to reveal that measure and its score row on both axes, '
  'without forced centering. Hidden repeats navigate to their visible source. Floating editors and Compose mode do not '
  'trigger this navigation. Note double-click editing and lower-ruler double-click playback retain their actions.'),
 ('两端对齐与字号上限',
  'Justification and font limits',
  '传统简谱每行对齐左右页边距；拍内符号保持紧凑，额外空间放在拍组之间。末行和强制合行也对齐；单拍小节无内部拍间隙时留在末尾。<br><br>字号旁显示当前上限，输入及加号不能超过上限。保持每行小节数不变，改变排版后重新计算上限，旧工程超限字号会调整并保存为实际值。全谱使用选定字号；强制合行按保存的比例缩小。极密谱面可使用明确显示的小数值。创作模式仍不更新谱面，音乐修改在重新切入制谱时同步。',
  'Traditional rows align with both page margins, including final and forced rows. Extra space goes between beat '
  'groups while symbol cells remain compact; one-beat bars leave spare width at the end.<br><br>The font control '
  'displays its maximum and cannot exceed it. Measures per line stay fixed. Layout changes recalculate the cap; '
  'oversized legacy values are corrected and saved. The chosen font is used throughout the score; forced rows retain '
  'their proportional reduction. Very dense scores display a fractional size. Compose mode still suspends score '
  'updates; music refreshes on re-entering Score mode.'),
 ('紧凑传统简谱与 32 分音符对',
  'Compact traditional rows and isolated 32nd pairs',
  '创作模式暂停隐藏谱面的布局、重绘和定位请求，切入制谱时再同步。传统简谱行对齐两侧页边距，额外空白放在拍间；拍内符号靠拢，拍间仍有留白，小节线缩短到音符附近，谱行与歌词纵向留白同步收紧。字号全局一致、强制合行比例规则保留。<br><br>所有简谱自动应用独立的 '
  '32 分音符对排版：按拍号分母划分拍组，拍内没有 16 分音符且只有两个连续 32 分音符时，从相邻的附点八分音符部分借出显示空间。附点八分 + 32 分 + 32 分按八分 + 16 分 + 16 分占位，去掉该附点，但两个 '
  '32 分音符仍保留三条减时线。长音中的对应片段会拆出并用延音线相连；附点休止符也适用。含 16 分音符、更多 32 分音符或不连续的组合保持原样。<br><br>此规则仅改变谱面排版与附点显示。音符真实起点、时长、力度、播放与 '
  'MIDI 完全保留；点击和播放游标仍对应真实时间。',
  'Compose mode suspends hidden-score layout, repaint and navigation work until Score mode is entered. Traditional '
  'rows reach both page margins, placing extra space between beat groups. Symbols sit closer within beats, while '
  'inter-beat gaps remain; short barlines surround the note row and vertical space for rows and lyrics is reduced. '
  'Global font sizing and proportional forced-row sizing remain.<br><br>All score styles apply an isolated 32nd-pair '
  'spacing rule. Within a meter-denominator beat containing no sixteenths and exactly two consecutive 32nds, visual '
  'space is borrowed from an adjacent dotted-eighth portion. Dotted eighth + 32nd + 32nd occupies the same space as '
  'eighth + sixteenth + sixteenth. The companion dot is omitted, but both 32nds retain three underlines. A '
  'corresponding portion of a sustained note is split off and tied; dotted rests are supported too. Groups with '
  'sixteenths, extra 32nds or nonconsecutive pairs retain their original engraving.<br><br>This changes engraving and '
  'dot display only. Actual onsets, durations, velocities, playback and MIDI remain intact; clicks and the playhead '
  'still refer to real time.'),
 ('谱面选择与局部合行',
  'Score selection and local systems',
  '谱面工具栏选择“小节选择”或“拍选择”。单击选择，再次单击已选小节或拍取消该项；Ctrl 单击增减、Shift 单击扩展连续范围，拖动框选；Alt '
  '拖动浏览页面。右键操作选区。<br>连续小节且首小节位于当前行开头时，可“强制合并为一行”。该行字号按合并时的每行小节数与合并后小节数之比绑定全局字号，后续行继续使用默认每行小节数；立体与紧凑音域重新计算。可右键恢复自动分行。',
  'Choose Measure selection or Beat selection in the score toolbar. Click to select; click a selected bar or beat '
  'again to deselect it. Ctrl-click toggles, Shift-click extends a range, or drag a marquee; Alt-drag pans the page. '
  'Right-click to act on the selection.<br>Consecutive measures starting at a system boundary can be forced into one '
  'system. That system scales from the global font by its saved original measure count divided by its merged count; '
  'later systems retain the default measure count. Spatial and compact pitch ranges are recalculated. Right-click to '
  'restore automatic systems.'),
 ('歌词与符号位置',
  'Lyrics and symbol placement',
  '歌词在制谱下栏编辑，首次打开会自动回填已有歌词。选择起始小节、小节数量与段次，或点击“使用谱面选区”，自动回填该范围已有歌词；确认与删除只影响所选范围和段次，保留范围外歌词与其他段次。允许只填部分起点，不能超出范围。节奏点取旋律 '
  'MIDI 的全部唯一音符起点；同刻多音只匹配一个字，长音内的新音符仍增加起点，跨小节持续音不重复计入。回填每小节一行，中文连写，仅英文词用空格分隔；标点保留且不额外占位。/s 消耗一个起点且不显示文字；/- '
  '消耗一个起点，并从前一个音符画连音弧线，仅改变谱面。例如 我/-/- 在 1、2、3 上分别连接 1→2、2→3。行首续接为向右下弯入音符的半段弧线。旧工程中原有的跳过回填为 /s，不自动添加弧线。生成 & '
  '模板后可保留部分未填占位，这些 & 不会保存。每行约束在对应小节，空行保留位置；旧 | 分隔仍兼容。<br>使用 /x{我是一个rapper} 将其中五个字／词按现有旋律起点匹配，谱面数字改为与 0 同样居中的 x，节奏与 '
  'MIDI 音符不变。可混合输入唱词、说唱组、/s 与 /-；连续说唱回填为一个 /x{...}，跨小节在花括号内换行。花括号必须成对、不嵌套，组内不附加时值。examples/lingfeng-rap.lfs '
  '提供说唱示意，examples/lingfeng-melisma.lfs 演示跳过与逐对连音。原有 我/64.爱/64你/64 显式时值说唱仍可使用。提交、删除、撤销与重做更新工程歌词；谱面在重新切入制谱时同步。切换制谱和导出 '
  'PDF 不检查旧歌词匹配。反复段落的不同歌词仍按段次堆叠。<br>符号位置规则：小节／双小节／结束线与反复线位于边界；Segno、Coda 在上方；D.C.、D.S.、N/R、Fine、F.O.、rit.、ad lib. '
  '在下方。谱面提示不生成速度或音量曲线，不改变 MIDI 顺序。',
  'Edit lyrics in Score mode; saved lyrics load on first opening. Choose the start bar, bar count and stanza, or use '
  'the score selection, to load existing lyrics. Apply/delete affects only that range and stanza, preserving outside '
  'lyrics and other stanzas. Partial entry is allowed. Rhythm uses all distinct melody MIDI starts: simultaneous notes '
  'share a slot, new notes under sustains add slots, and sustained notes crossing barlines do not create extra starts. '
  'Autofill uses one line per bar, continuous Chinese and spaces between English words. Punctuation takes no extra '
  'slots. /s skips one onset invisibly; /- adds a display-only slur from the preceding note. 我/-/- over 1, 2, 3 draws '
  'two slurs: 1→2 and 2→3. Row-entry continuations curve down towards the note. Saved legacy skips load as /s without '
  'adding slurs. Unfilled & slots are not saved. Empty lines retain bar positions; legacy | separators remain '
  'readable.<br>Use /x{我是一个rapper} to bind five characters/words to existing melody onsets and replace their score '
  'digits with centered x symbols at the same vertical position as 0. Rhythm and sounding MIDI notes remain unchanged. '
  'Mix sung text, rap groups and skips freely. Consecutive rap merges into one /x{...} group, with newlines across '
  'bars. Braces must match, cannot nest, and contain no explicit durations. See examples/lingfeng-rap.lfs for rap and '
  'examples/lingfeng-melisma.lfs for skips and successive slurs. Legacy explicit rap timing such as 我/64.爱/64你/64 '
  'remains supported. Apply, delete, undo and redo update project lyrics. Re-enter Score mode to refresh engraving. '
  'Switching to Score and exporting PDF do not validate old lyric matches. Repeated passages retain stacked '
  'stanzas.<br>Symbol placement rules: barlines and repeat signs at measure boundaries; Segno and Coda above; D.C., '
  'D.S., N/R, Fine, F.O., rit. and ad lib. below. Directions do not create tempo/volume automation or change MIDI '
  'order.'),
 ('反复压缩与跳转',
  'Repeat compression and jumps',
  '打开制谱模式，在“结构逻辑”页选择类型并“创建符号”，再在谱面选择小节并分别记录区域 '
  'A、B。可创建多个待配置符号并来回切换。两区必须连续、相邻且等长；检查通过后添加反复。右键也可压缩选中的两段相同音乐。校验两轨音高、起止、力度、和弦标签、拍号与调性；不同歌词按段落堆叠在格点下方；跨区间延音、内容不同或嵌套压缩不可用。D.C. '
  '从全曲开头重复，D.S. 自动配对 Segno；al Fine 只用于演奏时间线末段。N/R 表示跳转后不再执行内部反复。<br>尾声跳转需分别记录 A、B、A′、C 四区，要求 A 与 A′ 音乐一致：隐藏第二次 A，自动放置 '
  'Segno、To Coda、D.S. al Coda 与 Coda。修改音乐后如校验不再通过，自动展开显示。右键谱面上任一结构符号可删除该组逻辑，立即还原完整谱面，Ctrl+Z 可撤销。所有压缩都保留原 MIDI 与播放顺序。',
  'Expand the score editor, choose a type in Score structure and click Create symbol. Select measures on the score and '
  'capture regions A and B separately. You can keep multiple drafts and switch between them. Each must be consecutive; '
  'both must be adjacent and equally long. Add the repeat after validation. The score context menu also supports '
  'repeat compression. Both tracks are checked for pitches, timing, velocities, chord symbols, meter and key. '
  'Different lyrics are stacked below the grid as separate verses. Sustains across boundaries, differing content and '
  'nested compression are unavailable. D.C. returns to the beginning; D.S. pairs with an automatic Segno. Al Fine is '
  'available only at the end of the performed timeline. N/R means no internal repeats after the jump.<br>For a Coda '
  'jump, capture four regions: A, B, A′ and C. A and A′ must match: the second A is hidden and Segno, To Coda, D.S. al '
  'Coda and Coda are placed automatically. If music edits invalidate a match, it expands again. Right-click a rendered '
  'structure symbol to delete that structure and restore the full score. Ctrl+Z undoes the deletion. MIDI and playback '
  'order always remain intact.'),
 ('其他谱面符号',
  'Other score symbols',
  '小节选择可添加普通小节线、双小节线、结束线、Segno 与 Coda。拍选择可添加 F.O.（淡出）、rit.（渐慢）、ad lib.（自由演奏）和 Fine（结束）。符号菜单会根据选区位置与实际音符启用；结束线、Fine '
  '和淡出只用于演奏结束处。<br>这些是演奏提示；本版不从力度推测演奏意图，也不自动生成速度或音量曲线。右键可清除选区符号。',
  'Measure selection supports regular, double and final barlines, Segno and Coda. Beat selection supports F.O. (fade '
  'out), rit. (ritardando), ad lib. (freely) and Fine. Availability depends on the range and actual notes; final '
  'barlines, Fine and fade out require the end of the performance.<br>These are performance directions. This version '
  'does not infer intent from velocities or generate tempo or volume automation. Right-click to clear symbols in the '
  'selection.')]

def category_for(topic):
    return next(index for index, (_, _, titles) in enumerate(HELP_CATEGORIES) if topic in titles)


def plain_text(html):
    return unescape(re.sub('<[^>]+>', ' ', html))

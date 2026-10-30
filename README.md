# 伶风 Lingfeng — For Pop Music · 0.50.2

**伶风——为流行音乐而生**

伶风是面向 Windows 键鼠操作的轻量音序器，用于旋律、和弦与伴奏编写，并集成传统、立体、紧凑简谱及歌词排版。工程保存为 **.lfs**（Lingfeng Lead Sheet），可导出 PDF、MIDI 和 MP3。完整解压便携包即可使用，无需安装 Python。

Lingfeng is a lightweight Windows sequencer for melody, chords and accompaniment, with traditional, spatial and compact jianpu (numbered notation), lyrics and rap. Projects use **.lfs** (Lingfeng Lead Sheet). Export PDF, MIDI or MP3; extract the portable archive to run without Python.

这是一个个人维护的开源桌面项目。当前支持并验证 **Windows x64**，开发与打包使用 **Python 3.13、PySide6**；实时声音使用随附的 STK 合成包或已安装的 Windows MIDI 输出。

This is a personally maintained open-source desktop project. **Windows x64** is the supported and tested platform. Development and packaging use **Python 3.13 and PySide6**, with bundled STK synthesis packs or installed Windows MIDI outputs for sound.

- [开始使用 / Getting started](#1-开始使用--getting-started)
- [操作帮助 / User guide](docs/HELP.md)
- [源码运行与构建 / Source and builds](#6-帮助源码与重建--help-source-and-rebuilding)
- [更新日志 / Changelog](CHANGELOG.md) · [参与贡献 / Contributing](CONTRIBUTING.md) · [MIT 许可 / License](LICENSE)

## 1. 开始使用 / Getting started

### 1.1 运行与音源 / Running and sound sources

完整解压后运行 `Lingfeng.exe`，保留 `_internal/` 和 `synths/`。当前发行附带 3 组合成音源、37 个预设；无合成包时仍可编辑、导出 PDF/MIDI，并使用 Windows MIDI。可将 `.lfs` 拖到程序图标上打开；`Register-project-type.cmd` 可选注册当前用户的打开方式。

Extract the entire archive, keeping `_internal/` and `synths/`, then run `Lingfeng.exe`. The release includes three synth packs with 37 presets. Without packs, editing, PDF/MIDI export and Windows MIDI remain available. Drop an `.lfs` onto the executable to open it; `Register-project-type.cmd` optionally registers the association for the current user.

新增音源：把完整音源文件夹放到程序同级 `synths/`，打开 **设置 → 音源与音色 → 重新扫描并保存**。也可添加额外扫描目录。音源包总解压体积不超过程序本体时合并打包，否则另发音源 ZIP。详见 [音源包说明](docs/SOUNDBANKS.md)。

To add a pack, copy its complete folder into `synths/`, then choose **Settings → Sound sources and instruments → Rescan and save**. Additional scan folders are supported. Synth collections larger than the core application ship as separate ZIPs. See [Soundbanks](docs/SOUNDBANKS.md).

Windows MIDI 在打开音源和停止时清理本程序所用通道的持续音状态，避免高音在松键或停止后残留。它仍使用工程所选的系统或设备音色；不会自动替换音源或改写音符。

Windows MIDI clears sustain and sounding-note state on this application's channels when opening or stopping, preventing high notes from remaining after release or Stop. It retains the project's selected system or device instrument, without replacing the source or changing the notes.

### 1.2 工程与升级 / Projects and upgrades

新建默认 8 小节、4/4、100 BPM、C3 Ionian；每小节用无声 N.C. 和弦区间填满。打开/保存记住最近工程目录；编辑后自动保存恢复副本，可从文件菜单恢复。Ctrl+S/Z/Y 保存/撤销/重做，独立窗口同样适用。容器版本和兼容范围见 [工程格式](docs/FORMAT.md)。

New projects use eight bars, 4/4, 100 BPM and C3 Ionian, with silent N.C. chord regions. Open/Save remembers the project folder. An autosave recovery copy is available from File. Ctrl+S/Z/Y saves/undoes/redoes in both main and floating windows. See [Project format](docs/FORMAT.md) for container compatibility.

0.50 起，本机偏好集中迁移并在升级前备份：保留语言、主题、颜色、快捷键和自定义和弦进行；显式清空的绑定和空进行库不会被默认项复活。新版本可解压到新目录，用户设置仍从用户数据目录读取；音源默认和额外扫描目录迁移后重新扫描，工程已存的音色与配器保留。不要删除旧版本或备份，直到新版本工程与音源确认可用。

Version 0.50 centralizes preference migration with backups before upgrades. Language, theme, colors, shortcuts and custom progressions are retained, including cleared bindings and an empty progression library. Extracting a new version into a new folder keeps shared user settings. Sound defaults and extra scan folders migrate while pack paths are rescanned; saved project instruments and voicings are retained. Keep the previous version and backups until your projects and sound sources are confirmed in the new version.

旧版默认 `synths/` 中自行添加的音源包需要复制到新版 `synths/`，或移到额外扫描目录；旧安装的默认音源目录不会自动成为新版的扫描来源。

Copy user-installed packs from the previous default `synths/` into the new version's `synths/`, or place them in an extra scan folder. The previous installation's default folder is not automatically added as an extra source.

## 2. 创作与编辑 / Composition and editing

### 2.1 音符、格点与时值 / Notes, grid and duration

- **Smart**：单击选择，空白拖动框选，双击格内创建，双击音符删除。**Draw**：单击格内创建，单击已有音符删除，拖动移动或伸缩。
- 新建、移动、伸缩和粘贴只覆盖同音高重叠部分，保留外侧片段；相接不自动合并。量化位于选中音符的右键菜单。
- 时值与吸附格点分开。默认“上一次时值”：没有可追踪音符时临时按格点创建，此后跟随最近创建、选择或编辑音符的真实长度，包括拉伸、属性和撤销。
- 旋律与和弦卷帘分别记忆时值，语言/停靠切换保留，新建/打开工程重置；也可选择固定时值或跟随网格。附点与三连音互斥，Shift+3 切换格点三连音。

**Smart** selects on click/drag, inserts on double-click in a cell and deletes on double-click on a note. **Draw** inserts/deletes on click and moves/resizes by dragging. Edits replace only same-pitch overlaps, retaining outside pieces; adjacent notes remain separate. Quantize is in the note context menu.

Duration and snap are independent. **Previous note** starts with a temporary grid fallback, then follows the actual duration of the latest created, selected or edited note, including resize, properties and undo. Melody and harmony remember separately across language/docking changes; new/open projects reset the history. Fixed duration and Follow grid are also available. Dotted and triplet modes are exclusive; Shift+3 toggles triplet snapping.

### 2.2 时间轴、循环与窗口 / Timeline, looping and windows

时间轴上半部选择小节（Ctrl 分选、Shift 连选），右键设置拍号/调性、批量插入、删除及段落（段落标识仅在此处提供，已从“编辑”主菜单移除）；下半部单击格点定位，双击播放，拖动设置循环。音符、和弦和小节选择不清除循环。中键拖屏；Ctrl/Shift+滚轮围绕鼠标缩放；拖动滑块、导航器、中键或其它手动浏览后，橙色播放游标离开正在浏览的卷帘时才取消跟随；仍可见时保留手动视角，到达边缘再自动滚动。

The upper timeline selects bars (Ctrl/Shift); its context menu sets meter/key, inserts or deletes bars, and assigns sections. Section markers are available here and have been removed from the main Edit menu. The lower ruler seeks on click, plays on double-click and defines a loop by dragging. Musical selections retain the loop. Middle-drag pans; Ctrl/Shift-wheel zooms around the pointer. Scrollbar, overview, middle-drag and other manual navigation disable following when the orange playhead leaves the piano roll being browsed. While it remains visible, the manual view stays in place until automatic scrolling is needed at the edge.

旋律/和弦卷帘均可独立悬浮。View 勾选只代表主界面显示；浮窗关闭后可从 View 放回主窗口。E 切换输入轨、进入和弦卷帘编辑、撤销定位沿用已有浮窗。创作与制谱的独立浮窗都可分别跟随，或勾选“同步时间轴”与主界面联动。制谱主跟随开关控制谱面和当前选中的停靠卷帘；未选卷帘切换时再跟随。同一界面的跟随设置始终共用，但手动导航按正在浏览的视图判断：谱面中游标所在的小节完全离开谱面视口便取消，下方卷帘仍显示游标也不会阻止；卷帘中游标离开该卷帘便取消，避免被谱面拉回左边缘。拖住谱面滑块时暂缓自动跟随，保留拖动后的视角。语言与工作空间切换保留布局。播放时编辑、撤销和重做通过调度修订保持播放，未变持续音不应重新触发。

Both piano rolls can float. View checkmarks mean visible on the main page; View can reclaim a closed float. Input-track switching, chord editing and undo navigation reuse existing floating windows. Floating rolls in both Compose and Score can follow independently or enable Sync timeline to link with the main page. In Score, main Follow playhead controls the score and selected docked roll; inactive rolls catch up on selection. Views on the same page always share follow state, but manual navigation is evaluated in the view being browsed. In the score, following stops once the measure containing the playhead leaves the score viewport completely, even if a docked roll still shows the playhead. In a piano roll, it stops when the playhead leaves that roll, so the score cannot pull it back to the left edge. Automatic score following pauses while its scrollbar is held, preserving the dragged view. Language/workspace changes retain the layout. Playback edits and undo/redo revise the schedule in place, preserving unchanged sustained notes.

0.50 将旋律和和弦 MIDI 的定时调度、音源路由和声音输出放到独立音频进程，使工程编辑与排版的 Python 工作不再阻塞已提交音符的起音/止音。循环按固定时间边界运行，减少多次循环的累计偏移。

Version 0.50 moves timed MIDI scheduling, instrument routing and sound output into a separate audio process, isolating scheduled note-on/off events from Python editing and engraving work. Loops anchor to fixed time boundaries to avoid cumulative drift.

### 2.3 快捷键 / Keyboard shortcuts

| 默认键 / Default | 功能 / Action |
| --- | --- |
| Space | 播放/暂停 / Play/pause |
| W/S、Alt+W/S | 半音/调内移动 / Semitone/scale-step movement |
| A/D | 按格点移动所选音乐 / Move selected music by grid |
| ←/→ | 浏览时间轴 / Browse the timeline |
| Ctrl+↑/↓ | 选中音符上下八度 / Move selected notes by an octave |
| Q、E | 切换工具/输入轨 / Switch tool/input track |
| R、C、Tab | 返回定位线/编辑和弦/下一和弦 / Replay anchor/edit chord/next chord |
| Shift+3 | 吸附三连音 / Triplet snapping |

**设置 → 快捷键设置** 列出全部应用命令和备用键。菜单显示实际绑定，清空后隐藏；冲突转移需确认，取消保留原设置。修改即时应用到主窗口和浮窗，文本框保留自身编辑键；固定系统键只读列出。

**Settings → Keyboard shortcuts** lists all commands and alternate bindings. Menus show current keys; clearing hides them. Confirming a conflict transfers the key; cancellation retains the previous setting. Changes apply to main/floating windows immediately. Text fields retain their editing keys, and fixed system keys are listed read-only.

### 2.4 MIDI 导入与键盘输入 / MIDI import and keyboard input

文件菜单可将所选 MIDI 轨道导入旋律或和弦卷帘，使用独立导入量化设置，保留原时间或选择普通/三连音网格，可选导入拍号与速度。导入覆盖可撤销，已有歌词不自动重新绑定。

File imports selected MIDI tracks into melody or harmony, using an independent quantization setting: retain original timing or choose a straight/triplet grid, with optional meter and tempo import. Replacement can be undone, and existing lyrics are not automatically rebound.

设置 → MIDI 键盘输入选择设备与目标轨并启用。暂停时逐步录入，临近同时按键组合为和弦，松开按键和踏板后前进；播放中实时录入并保留键盘力度。起止点吸附到目标卷帘的当前格点，E 同时切换目标轨。启动时不会自动启用录入设备。

Settings → MIDI keyboard input selects a device and destination. Paused step input groups near-simultaneous keys and advances after keys/pedal release; playback records live with keyboard velocity. Starts/ends snap to the target roll's grid, and E also changes the input target. Devices are not armed automatically at startup.

## 3. 和弦、节奏与进行 / Chords, patterns and progressions

### 3.1 和弦区间与实际 MIDI / Regions and performed MIDI

和弦节奏表示变化频率，和弦节奏型表示织体和起音安排。和弦卷帘长音可跨区间边界；识别依据实际 MIDI，识别本身不补音。移动/缩短后空白填 N.C.。合并区间保留 MIDI 再识别；显式分割会切开分割点处的持续音。

Harmonic rhythm describes chord-change frequency; accompaniment patterns describe note timing and texture. Sustains may cross chord-region boundaries. Recognition uses performed MIDI and never adds tones. Vacated space becomes N.C. Merging regions preserves MIDI before recognition; explicit splits cut sustained notes at the selected point.

修改可识别和弦的根音/性质时保留其它参数重生成，性质变更恢复根音低音；指定低音/转位只改低音。自定义锁定保留人工节奏，动态未识别显示“未知节奏型”。普通小节线不强迫重新起音；拍号变化是和弦移动/伸缩的结构边界，粘贴整批检查目标拍号。

Root/quality changes regenerate recognized chords with other parameters retained; quality changes reset bass to root. Bass/inversion changes affect only bass. Custom locks retain manual timing; unrecognized timing is labeled Unknown pattern. Ordinary barlines do not force new onsets. Meter changes bound chord movement/resizing, and paste validates the whole batch against target meters.

根音和低音列表从起点小节主音开始，保留调式音级拼写。编辑仅记住性质、节奏型、gate 和力度；根音默认当地主音，低音默认等于根音，改变根音同步低音。起点、时长、八度取当前和弦；取消不更新记忆。

Root/bass pickers start at the onset key tonic and retain modal degree spellings. Only quality, pattern, gate and velocity are remembered. Root defaults to the local tonic and bass follows root changes. Start, length and octave come from the target chord; Cancel leaves remembered defaults unchanged.

### 3.2 性质与节奏型 / Qualities and patterns

支持 mM7、add2、M9、7b5 等性质。add2 默认密集 1–2–3–5 加独立低音，旧 add9 名称兼容迁移为 add2，已保存的显式 MIDI 不在加载时改写。7b5 为 1、3、♭5、♭7，与 m7b5 的小三度不同。

Qualities include mM7, add2, M9 and 7b5. add2 defaults to close-position 1–2–3–5 above a separate bass; legacy add9 names migrate to add2 while saved explicit MIDI remains untouched. 7b5 contains 1, 3, flat 5 and flat 7; m7b5 has a minor third.

柱式、分解和琶音按真实小节相位生成并裁切。根五交替的四分/八分/反拍柱式支持偶数分子、分母 2/4/8/16；低音按分母拍交替根音与五音，每小节重置，上方演奏完整和弦，gate 与边界裁切适用。

Block and arpeggiated patterns use actual bar phase and region clipping. Alternating-bass quarter/eighth/offbeat blocks support even numerators with denominators 2/4/8/16. Bass alternates root/fifth on denominator beats, restarting each bar; upper voices play complete chords with gate and boundary clipping.

### 3.3 进行库与局部主音 / Progression library and local tonic

应用罗马数字进行按现有和弦块顺序替换，不增加小节；整次操作使用所选主音，跨调号也不自动重解释。可保留已识别节奏、选择未知/自定义的备用节奏，或统一节奏、力度和 gate。多选可识别和弦按时间顺序保存，保留性质与转位，如 I/3、V7/7。

Applying Roman recipes replaces existing regions without adding bars. Every target uses the tonic selected for that operation, even across key changes. Retain recognized patterns with a fallback, or broadcast pattern, velocity and gate. Capturing recognized selections keeps chronological order, qualities and bass degrees such as I/3 or V7/7.

设置中的管理窗口支持名称或根音序列检索、添加、修改和删除，确认才保存，取消放弃草稿。根音检索为有序子序列，允许中间有其它和弦；忽略性质/转位，保留 #/b 拼写差别。可从选中和弦打开检索，并手输罗马数字或实际和弦名。内置 26 组去重进行及来源见 [进行说明](docs/PROGRESSIONS.md)。

The manager searches by name or root sequence and adds/edits/deletes entries; confirm saves and Cancel discards the draft. Root search is an ordered subsequence with gaps, ignoring quality/inversion while retaining sharp/flat spelling. Search from selected chords, Roman numerals or letter names. See [Progressions](docs/PROGRESSIONS.md) for the 26 default recipes and sources.

## 4. 制谱与歌词 / Engraving and lyrics

### 4.1 排版与查看 / Layout and navigation

立体/紧凑谱按密度分配小节宽，各小节内实际时间线性、各拍等长；传统谱拍内紧凑等距、拍间留白，每行（含末行、强制合行）对齐页边距。数字、休止符和 x 共用全局字号，附属符号等比缩放。字号控件显示并限制不重叠上限，每行小节数保持；字号与音高间距独立。首次进入或切换谱式可自动推荐字号，手动设置会保存。

Spatial/compact scores allocate widths by density and map actual time linearly within each bar. Traditional rows keep symbols compact within beats, leave inter-beat gaps and align both margins, including final/forced rows. Digits, rests and x share a global font, with proportional attached symbols. The font control exposes and enforces the collision-free maximum while retaining measures per line. Font size and pitch spacing are independent; recommended and manual sizes are supported.

强制合行按“原每行小节数 ÷ 合并后可见小节数”缩小，最大为 1。独立连续 32 分音符对可借用相邻附点八分音符的显示空间，保留减时线；只改显示，不改 MIDI。结构符号/反复压缩只改变谱面，删除恢复完整显示，段落和播放顺序不改。

Forced rows scale by original bars per line divided by visible bars, capped at 1. Isolated consecutive 32nd pairs may borrow visual space from adjacent dotted eighths while retaining their underlines. These are display changes only. Structure symbols/repeat compression affect the score, and removal restores the full view without changing playback.

页面缩放提供填满屏幕、整页、百分比；Ctrl+滚轮围绕指针缩放，中键或 Alt+左键拖动。双击制谱下方停靠卷帘的小节编号定位上方谱行。普通卷帘音乐修改再次进入制谱后同步；作品信息确认后的标题、歌词提交/删除/撤销和直接谱面操作即时同步；标题更新不会带入尚未同步的音乐编辑。

Score zoom offers Fill width, Fit page and percentages; Ctrl-wheel zooms at the pointer, and middle-drag or Alt-left-drag pans. Double-click a docked editor's upper bar number to reveal that score row. Regular piano-roll music edits synchronize on re-entering Score; confirmed project titles, lyric apply/delete/undo and direct presentation controls update immediately. Updating a title preserves the pending music snapshot.

### 4.2 歌词输入、Rap 与连音 / Lyrics, rap and slurs

匹配以所选小节内全部旋律 MIDI 的唯一音符起点为准。同刻多声部只占一个槽，长音下出现新起点仍增加槽，跨小节持续不重复；和弦轨不计入。中文逐字、英文按词，允许中英文紧贴、英文缩写、引号和标点；标点不新增起点。

Lyrics follow every distinct melody MIDI onset in the selected bars. Simultaneous notes share a slot; new attacks under a sustain add slots; bar-crossing sustains do not. Harmony is excluded. Chinese characters and English words can be adjacent; contractions, quotes and punctuation are retained without extra slots.

| 输入 / Input | 含义 / Meaning |
| --- | --- |
| `/s` | 跳过一个起点，无文字/连线 / Skip one onset without text or a line |
| `/-` | 跳过并从前一个旋律起点画连音 / Skip and slur from the preceding onset |
| `/x{我来了 Let us rap!}` | 按已有起点显示 Rap x，保留原 MIDI / Rap x on existing onsets, MIDI unchanged |
| `&` | 未填模板槽，不保存为歌词 / Unfilled template slot, not saved as lyric text |
| 换行 / Newline | 每小节一行，Rap 组可跨行 / One line per bar; rap groups may span lines |

例如 `我/-/-/s` 消耗四个起点，在第 1→2、2→3 之间各画一条连音，第 4 点无字无线。行首/页首续线用左上到右下的半弧。普通 `-` 保留为标点或英文词内连字符；旧工程的跳过回填为 `/s`，旧 `|` 和显式 Rap 时值语法继续兼容。

For example, `我/-/-/s` uses four onsets, slurring 1→2 and 2→3, then skipping onset 4. Row/page entries use descending half-curves. Plain `-` remains punctuation or part of an English word. Legacy skips autofill as `/s`; old `|` separators and explicit-duration rap remain supported.

范围、数量、段次改变后回填已有歌词；保留未提交草稿。可少填，空行保留小节，中间缺口用 `&`。确认/删除仅影响该范围和段次，支持撤销重做。Rap、跳过、连音都不改变原 MIDI 音高、时值、力度。示例：[歌词与 Rap](examples/lingfeng-rap.lfs)、[跳过与连音](examples/lingfeng-melisma.lfs)，均附同名 MIDI。

Range/stanza changes autofill saved lyrics while retaining unsubmitted drafts. Partial entry is allowed; blank lines retain bars and `&` preserves internal gaps. Apply/delete affects only that range and stanza and supports undo/redo. Rap, skips and slurs retain MIDI pitch, timing and velocity. Examples: [Lyrics and rap](examples/lingfeng-rap.lfs), [Skips and slurs](examples/lingfeng-melisma.lfs), each with a matching MIDI file.

## 5. 导出与许可 / Export and licensing

导出会暂停播放并打开独立窗口。

Export pauses playback and opens a separate dialog.

| 格式 / Format | 内容与范围 / Content and range |
| --- | --- |
| PDF | 当前显示谱面的页码 / Pages from the displayed score |
| MIDI | 旋律、和弦或两轨；全部、小节、循环、段落 / Melody, harmony or both; all, bars, loop or section |
| MP3 | 同 MIDI 范围；离线合成或 Windows MIDI 输出回录 / Same ranges; offline synthesis or Windows MIDI output capture |

MIDI 使用 960 PPQ、标准 Type 1，保留共同零点便于分轨交接 DAW。尚未完成 Cakewalk Next 内的直接导入验收。MP3 离线使用工程音源/预设并保留力度/音量；Windows MIDI 选择实时录制或先改用合成音源。回录可能包含同设备其它声音。取消不覆盖已有文件。

MIDI uses 960 PPQ and Type 1 with a shared origin for DAW handoff. Direct Cakewalk Next import acceptance has not been completed. Offline MP3 uses project synths/presets, velocity and volume; Windows MIDI requires output capture or switching to a synth. Capture can include other sounds on the same device. Cancel preserves existing files.

MP3 窗口显示所用音色的商用提示，并生成 `.mp3.licenses.txt`。当前发行使用 3 组 STK 算法合成包、37 个预设，各包保留 STK 版权、许可和对应源码；旧采样音源不再分发。Windows 音源遵循提供方条款。音源软件许可不代替作品、歌词及其他素材的授权。详见 [音源包说明](docs/SOUNDBANKS.md)。

The MP3 dialog shows instrument-specific commercial-use information and writes `.mp3.licenses.txt`. The current release uses three STK algorithmic synth packs with 37 presets, retaining STK notices, licenses and corresponding source. Retired sample instruments are no longer distributed. Windows instruments follow provider terms. Synth software licenses do not clear compositions, lyrics or other material. See [Soundbanks](docs/SOUNDBANKS.md).

## 6. 帮助、源码与重建 / Help, source and rebuilding

**帮助菜单**提供按类别和主题组织、可搜索的中英操作说明，离线文本见 [操作帮助](docs/HELP.md)。工程规范、进行库与音源说明分别见 [FORMAT](docs/FORMAT.md)、[PROGRESSIONS](docs/PROGRESSIONS.md)、[SOUNDBANKS](docs/SOUNDBANKS.md)。原创应用采用 [MIT](LICENSE)，第三方详情见 [THIRD_PARTY](docs/THIRD_PARTY.md)、[LICENSE_AUDIT](docs/LICENSE_AUDIT.md) 和 `licenses/`。参考产品及独立实现说明见 [REFERENCES](docs/REFERENCES.md)。

**Help** provides searchable bilingual instructions grouped by category and topic, also available as the offline [User guide](docs/HELP.md). See [FORMAT](docs/FORMAT.md), [PROGRESSIONS](docs/PROGRESSIONS.md) and [SOUNDBANKS](docs/SOUNDBANKS.md) for the project format, recipes and instruments. Original code is [MIT](LICENSE); dependencies retain their licenses in [THIRD_PARTY](docs/THIRD_PARTY.md), [LICENSE_AUDIT](docs/LICENSE_AUDIT.md) and `licenses/`. [REFERENCES](docs/REFERENCES.md) describes product inspirations and independent implementation.

### 6.1 从源码运行 / Run from source

在 Windows 上安装 Python 3.13 x64，然后在仓库根目录的 PowerShell 中执行：

Install Python 3.13 x64 on Windows, then run in PowerShell from the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

合成包放在 `synths/`；缺少包时可使用已安装的 Windows MIDI，编辑与 PDF/MIDI 导出仍可使用。音源重建方法和外部工具版本见 [SOUNDBANKS](docs/SOUNDBANKS.md)。

Synth packs belong in `synths/`. Without them, installed Windows MIDI remains available, as do editing and PDF/MIDI export. See [SOUNDBANKS](docs/SOUNDBANKS.md) for synth rebuilding and external tool versions.

### 6.2 测试与打包 / Tests and packaging

```powershell
.\.venv\Scripts\python.exe scripts/run_regression.py
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build.ps1 -Python '.\.venv\Scripts\python.exe'
```

回归脚本将测试偏好与缓存隔离到 `tmp/`，日志写入 `output/`；完整测试包含 Windows 与音频相关检查，需要对应运行环境。构建输出位于 `dist/<版本>/Lingfeng/` 和 `dist/Lingfeng-<版本>-Windows-x64.zip`。独立 EXE 可用 `--self-test <输出目录>` 自检，发行包用 `scripts/verify_release.py` 检查。更多开发约定见 [CONTRIBUTING](CONTRIBUTING.md)。

The regression runner isolates test preferences and caches in `tmp/` and writes logs to `output/`. The complete suite includes Windows and audio checks that require the corresponding environment. Builds appear under `dist/<version>/Lingfeng/` and `dist/Lingfeng-<version>-Windows-x64.zip`. The executable supports `--self-test <output-directory>`; `scripts/verify_release.py` checks the portable package. See [CONTRIBUTING](CONTRIBUTING.md) for development conventions.

发行包 `source/` 提供重建输入，音源包内含对应源码和许可；编码器源码及替换说明位于 `licenses/audio-source/`。原创应用代码采用 MIT，STK、Qt/PySide6、编码器和其他依赖继续遵循各自许可。

Release `source/` contains rebuild inputs, synth packs include their sources/licenses, and `licenses/audio-source/` contains encoder sources and replacement instructions. Original application code is MIT; STK, Qt/PySide6, the encoder and other dependencies retain their own licenses.

### 6.3 源码目录与公开范围 / Repository layout and shared files

| 路径 / Path | 内容 / Contents |
| --- | --- |
| `popscore/` | 音乐模型、编辑器、谱面、歌词、音频与中英文界面 / Model, editors, scores, lyrics, audio and bilingual UI |
| `scripts/`、`build.ps1` | 检查、音源构建与 Windows 打包 / Checks, synth building and Windows packaging |
| `tests/` | 模型、交互、排版与音频回归 / Model, interaction, engraving and audio regressions |
| `docs/` | 操作帮助、格式、音源与第三方说明 / User guide, format, synths and third-party notices |
| `assets/` | 程序界面资源 / Application UI assets |
| `native/`、`synths/` | 原生桥接器、批准的音源包及对应源码 / Native bridge, approved synth packs and their sources |
| `examples/` | 随项目提供的演示与回归示例 / Included demos and regression examples |
| `licenses/` | 第三方许可与对应源码说明 / Dependency notices and corresponding-source information |

公开仓库用于程序源码与可公开示例。私人乐谱工程、商业曲谱/PDF、歌词素材、录音、用户设置、调试输出及本机构建依赖不应提交；报告问题时请使用可公开的最小复现。现有个人文件保留在本地，公开版本变化记录在 [CHANGELOG](CHANGELOG.md)。

The public repository contains program source and shareable examples. Do not commit private scores, commercial sheet music/PDFs, lyric material, recordings, user preferences, debug output or local build environments. Use a shareable minimal reproduction when reporting a problem. Personal files remain local; public release changes are recorded in [CHANGELOG](CHANGELOG.md).

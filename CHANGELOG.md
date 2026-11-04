# 更新日志 / Changelog

仅记录实际已生成发行归档的版本；本地工作版本另见 `CHANGELOG_LOCAL.md`（仅本地 / local only），生成归档不代表已经上传或发布。完整操作说明见 [README](README.md) 与 [HELP](docs/HELP.md)。版本层级按大版本系列组织：`0.50.x` 属于 **0.5 系列**；具体发行号与工程格式版本分别维护。

Versions with generated release archives only; local work is recorded in `CHANGELOG_LOCAL.md`（仅本地 / local only）. Archive generation does not imply uploading or publishing. See [README](README.md) and [HELP](docs/HELP.md) for usage. Releases are grouped into version families: `0.50.x` belongs to **0.5**. Application releases and project-format versions are maintained separately.

## 0.5 系列 / 0.5 family

### 0.57 — 段落导航与全局节奏型识别 / Section navigation and global rhythm recognition

日期 / Date: 2026-11-05；基于 / Based on: 0.56.6；GitHub 上一发布版 / Previous GitHub release: 0.55

- 小节右键保留段落标识设置，新增按标识名与所在小节跳转；导航器以无文字边界提示段落起点，保留选区、循环与音乐内容。
- 设置 → 和弦新增全局节奏型识别开关。关闭时停止自动分析、隐藏和弦轨节奏型，属性、移动、伸缩、分割合并及拍号编辑按实际 MIDI 处理；重新开启沿用各和弦的独立设置。手动指定节奏型与重新生成继续可用。
- 同时包含 0.56–0.56.6 的完整和弦目录、默认力度、快速性质与右键菜单设置、手动和弦标记、自定义卷帘音域、谱面标识及歌词连音改进。
- 立体／紧凑简谱支持多声部，传统简谱仅用于单声部；手动标记参与旋律高亮与谱面弦内音圈。歌词自动连音优先于冲突手动弧，保留原标识条目。
- 复制粘贴保留实际配器、时序、逐音力度与副本独立事件标识；和弦粘贴按目标拍号区间或工程末尾裁切。和弦音符撤销／重做保留当前镜头，移动快捷键固定使用方向键及修饰组合。
- 精简项目主页并更新中英帮助、工程格式和构建说明。便携 ZIP 包含四组轻量音源、复现源码及第三方许可，附 SHA-256 校验文件。
- 验证：117 模块／1336 项回归通过，源码和实际 EXE 各 414 项自检通过；独立公开副本完成 53 项针对性回归、干净构建及源码／重建 EXE 各 414 项自检。

Bar menus add jumps to marked measures, and navigators show unlabeled section boundaries. A global rhythm-recognition switch pauses automatic analysis and hides chord-lane patterns while preserving performed MIDI and per-chord settings. Explicit pattern generation remains available.

This release also includes the completed 0.56–0.56.6 chord catalogue, saved editing preferences, manual labels, polyphonic spatial/compact scores, lyric slurs, MIDI-preserving cropped pastes and stable undo views. The portable ZIP includes four lightweight sound packs, reproducible source, license notices and a SHA-256 sidecar. All 1336 regressions and both 414-check acceptance runs passed; an independent public checkout was also rebuilt and verified.

### 0.55 — 和弦力度菜单与按需分层建议 / Chord velocity menus and opt-in layer suggestions

日期 / Date: 2026-11-02；基于 / Based on: 0.54.3；GitHub 上一发布版 / Previous GitHub release: 0.51

- 和弦轨右键“修改力度”支持单个及多个和弦，提供七个常用值及 1–127 自定义值；统一修改和弦生成力度与内部音符，保留音高、节奏和区间，支持撤销／重做及工程保存。
- 设置 → 力度选项可编辑常用列表、恢复默认并按需检测当前工程和弦轨的 SFZ／SF2 音色，按有效力度区间生成中间值建议。只在点击检测按钮时读取元数据，启动或切换音源均不检测；确认保存，取消不修改。重复采样区域不重复计数，跨键位／重叠区间不宣称为所有音高统一的层数；不支持查询的音源保留现有值。
- 此次 GitHub 发布同时包含 0.52–0.54.3 已完成的免费钢琴／电钢琴、大型键盘音源按需下载、加载进度、逐拍制谱、严格单旋律检查及传统推荐字号／强制合行改进。
- 更新中英帮助、格式、音源与构建说明。仅公开运行、构建、测试及必要用户说明和许可；本地工程、开发环境、维护文档和本地更新日志不上传。
- 验证：91 个模块、1107 项回归测试通过；源码和独立 EXE 各 370 项自检通过。实际检查 138 个采样音色的力度元数据。主 ZIP 附带四组轻量音源、复现源码和许可；旧发行包保留。

Right-click one or multiple chords to set a common MIDI velocity, including a custom 1–127 value, with undo/redo and project persistence. Settings offers a saved list and explicit metadata-only inspection of the current SFZ/SF2 chord preset. Detection never runs at startup or on sound changes. Suggested bands are not advertised as a universal sample-layer count.

This GitHub release also brings the completed 0.52–0.54.3 piano downloads, loading progress, beat-aware notation, monophonic score checks and font/merged-row improvements. All 1107 regressions and both 370-check source/standalone acceptance runs passed. The portable ZIP includes four lightweight sound packs, reproducible source and notices. Local projects and maintenance records remain private; existing archives are preserved.

### 0.53.2 — 传统简谱连奏与跨拍记谱 / Traditional legato and beat spelling

日期 / Date: 2026-11-01；基于 / Based on: 0.53.1

- 修复导入旋律中相邻音符短尾重叠被误判为复音、导致传统简谱意外掉到第二条音符行的问题；真正同时起音或长时间重叠的复音继续分声部显示。
- 传统简谱的切分和跨拍附点音在拍边界拆分，以同一音符的延音线连接；附点记谱留在所属拍内，整拍长音保留延音横线。
- 原始音符、歌词绑定、播放及 MIDI 时值不变，屏幕、PDF 与点击定位共用排版。

Traditional notation keeps short overlapping legato tails on the melody line while retaining genuine polyphony. Offbeat notes and dotted values crossing a beat are split and tied; aligned whole-beat sustains retain extension dashes. Source notes, lyric bindings, playback and MIDI timing remain unchanged. Screen, PDF and hit testing share the same engraving.

### 0.53.1 — 传统逐拍排版与推荐字号 / Traditional beat spacing and advisory font sizes

日期 / Date: 2026-11-01；基于 / Based on: 0.53

- 传统简谱改为按各拍自身的可见符号数量分配宽度；同一行使用紧凑、统一的拍间距，跨小节也一致，不再为小节最后一拍保留额外尾部空白。强制合行时拍间距与字号按保存比例缩小。
- 立体简谱的推荐字号按实际符号位置判断，避免不同音高、不同位置的音符互相限制。字号提示改为建议上限，可手动超出建议并保存；推荐按钮仍可恢复建议字号。
- 屏幕、PDF 与点击定位使用同一排版，保留音乐时间与播放内容。免费音源与 0.53 兼容。

Traditional notation now sizes each beat by its own visible symbol count, uses a small consistent gap throughout each row, and removes extra trailing beat space. Forced rows scale gaps with their saved font ratio. Spatial font recommendations use actual symbol placement; the displayed limit is advisory and larger user-selected sizes are preserved. Screen, PDF and hit testing share the layout without changing music or sound packs.

### 0.53 — 拍长比例与大型键盘音源 / Beat-proportional layout and optional keyboards

日期 / Date: 2026-11-01；基于 / Based on: 0.52

- 修正制谱小节宽度：最密一拍的起点数决定每拍宽度，再乘该小节的实际拍数。2/4 的 `[2,2]` 与 4/4 的 `[2,2,2,2]` 每拍等宽，小节宽度比为 `1:2`；同拍数的原 `4:2` 示例保持。三种谱式、点击映射和 PDF 共用，不改变 MIDI。
- 增加可选下载的 Greg Sullivan 电钢琴合集和完整 GM 键盘音源，保留本地小型音源及已有大钢琴；全部免费，较大音源独立于主程序包。
- 为播放和采样音源试听增加后台加载窗口，显示等待时间并可取消。优化大音源校验、缓冲和播放中编辑的命令调度，保留播放时钟与持续音。

Version 0.53 uses busiest-beat density multiplied by actual beat count, so equal-density 2/4 and 4/4 bars have equal beat widths and a 1:2 bar ratio. Optional free electric-piano and full GM keyboard packs expand the sound catalog. Loading runs behind a responsive, cancellable window, and large-bank initialization/rendering and live-edit dispatch are optimized without rewriting MIDI timing.

### 0.52 — 密度比例排版与免费钢琴音源 / Density-based engraving and free pianos

日期 / Date: 2026-11-01；基于 / Based on: 0.51

- 制谱时以小节内最密一拍的可见音符起点数分配行内小节宽度；例如 `[1,2,3,4]` 与 `[2,2,2,2]` 为 `4:2`，同刻多音共用一个位置，空小节至少占一份宽度。三种谱式、强制合行、点击定位和 PDF 共用此规则；不改 MIDI 时间或播放。
- 随包提供免费的小型原声钢琴、Rhodes、Wurlitzer、CP80 与 Pianet 音源，保留原有三组 STK 音源。新工程优先使用小型钢琴，已有工程及已保存的默认音色继续保留。
- 设置 → 音源与音色新增“下载／添加音源”：大钢琴按需下载，也可安装本地完整音源 ZIP。后台显示进度，支持取消，下载固定版本并核对大小及 SHA-256，完整校验后才安装；不会覆盖已有音源文件夹。
- 实时试听和离线 MP3 共用 SFZ 播放器；离线导出等待采样流读取，避免快速导出遗漏声音。随包保留样本署名、sfizz 及其依赖的许可和对应源码。
- 覆盖旧目录升级时刷新一次音源索引，保留个人默认音色和额外目录；延长大钢琴多通道初始化时限，避免正常加载被误判为超时。

Version 0.52 divides each row's bar widths by the busiest beat's visible onset count, so the example above is exactly 4:2. Screen, hit testing and PDF share the layout without changing music timing. Free acoustic/electric pianos are included; an optional grand can be downloaded or installed from a local pack ZIP. Background downloads support cancellation and checksum verification, preserve existing packs, and retain source credits and licenses. Existing projects and sound preferences remain supported.

### 0.51 — 可维护稳定基线 / Maintainable baseline

日期 / Date: 2026-10-30；基于 / Based on: 0.50.2

- 源码统一为 `lingfeng` 包，按音乐、制谱、音频、界面、基础服务和诊断分配模块；活动文件采用小写下划线命名，图标、线程及主题属性移除旧产品名。
- 分离设备路由与播放控制，共用路径、事件裁切、COM 生命周期及窗口边框服务；分开进行/结构规则与界面，消除相应反向连接与重复实现。
- 启动入口统一支持 `main.py`、`python -m lingfeng` 和 `--version`；静态帮助脱离 Qt，文件关联与安装自检分离。
- 归档失效的历史手工探针，删除未用控件和不可能通过当前校验的旧 schema 分支；保留有用途的备用播放、旧工程 schema 5/6、用户偏好迁移及接口别名。
- 构建、翻译审计和源码校验递归覆盖全部子包/资源；统一源码清单，回归按模块隔离用户数据，支持两段版本号。
- 工程 schema 6、偏好 schema 1、音源 ABI 1 不变；13 个随附工程与 0.50.2 的完整数据、播放事件和 MIDI 导出字节对比一致。

Version 0.51 reorganizes 0.50.2 into the consistently named `lingfeng` package and separates shared services and UI/business responsibilities. Recursive source packaging and isolated regression runs support reproducible builds and tests. Supported projects, preference migrations and audio contracts retain their compatibility. All 13 bundled projects preserve their complete data, performed events and MIDI bytes against 0.50.2.

### 0.50.2 — Windows 停音与视图跟随 / Windows note release and view following

日期 / Date: 2026-10-30

- 清理 Windows MIDI 已有延音状态，停止时清除目标通道的持续发声；初始化保留选定音色，修复合成线程启动失败时的连接清理竞态。
- 谱面拖动滑块或中键期间暂缓自动跟随；游标所在小节完全离开谱面视口后取消，其他视图中仍可见的游标不再阻止该判定。
- 制谱卷帘按自身游标可见性决定取消，与创作模式一致；手动右移后不再被谱面拉回左侧。
- 新增音频、谱面和卷帘回归检查，更新中英文帮助。

Windows MIDI now clears retained sustain and sounding voices on the intended channels while keeping the selected instrument. Synthesis startup failure cleanup is also corrected. Score following pauses during manual drags and cancels when the playing measure leaves that score viewport. Piano-roll navigation uses the roll's own playhead visibility, preventing the score from pulling a browsed roll back to the left edge. Audio/view regressions and bilingual help were updated.

The audio repair covers retained sustained voices and stop silence; normal high-frequency components of the Windows instrument are not filtered.

### 0.50.1 — 作品信息与跟随控制 / Project information and follow controls

日期 / Date: 2026-10-30

- 作品标题与作者即时同步当前谱面和 PDF 快照，支持撤销与重做，保留尚未同步的音乐编辑。
- 编辑菜单移除段落入口，小节时间轴右键入口保留。
- 制谱主界面支持停靠卷帘跟随，悬浮卷帘拥有独立跟随与时间轴同步设置；修复窄同步浮窗的滚动一致性。

Titles and author information update the score/PDF snapshot immediately, including undo/redo, while retaining pending music edits. Section markers remain in the bar context menu. Score mode gains docked-roll follow controls and independent floating-roll follow/sync settings, with consistent scrolling for narrow synced windows. The cancellation rules are refined in 0.50.2 above.

### 0.50.0 — 播放架构与升级保留 / Playback architecture and upgrade preservation

日期 / Date: 2026-10-30

- MIDI 事件调度、音源路由和声音输出移至独立音频进程，减少界面编辑与排版对已提交发声事件的阻塞；循环按固定时间边界计时。
- 偏好引入版本记录、原子保存、升级备份和损坏恢复；保留自定义键位、和弦进行、显式空库和未知字段。
- 跨安装目录迁移默认音色与额外扫描目录，并重新校验本机音源路径。
- 帮助按功能整理为 7 类、45 个主题，支持中英文全文检索，并提供同源生成的离线手册。

Timed MIDI scheduling, routing and output move to a separate audio process to isolate scheduled playback from editing and engraving. Loops use fixed time boundaries. Versioned preferences add atomic writes, upgrade backups and recovery, preserving custom shortcuts, progressions, empty libraries and unknown fields. Sound defaults and extra scan directories carry over between installations while packs are revalidated. Help is organized into seven categories and 45 searchable bilingual topics, with an offline guide generated from the same content.

# 更新日志 / Changelog

公开发行摘要。完整操作说明见 [README](README.md) 与 [HELP](docs/HELP.md)。版本层级按大版本系列组织：`0.50.x` 属于 **0.5 系列**；具体发行号与工程格式版本分别维护。

Public release notes. See [README](README.md) and [HELP](docs/HELP.md) for usage. Releases are grouped into version families: `0.50.x` belongs to **0.5**. Application releases and project-format versions are maintained separately.

## 0.5 系列 / 0.5 family

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

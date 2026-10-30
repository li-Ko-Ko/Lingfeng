# 设计与实现参考

来源记录日期：2026-10-28。代码路径以分发包的 `source/` 为基准，练习路径以分发包根目录为基准。外部链接用于说明实现来源；操作帮助和谱例均已随包提供。下面列出具体参考范围；界面、图形、节奏型和演奏代码为本项目独立实现。

## Cakewalk Next

- [Understanding Piano Roll View](https://help.cakewalk.com/hc/en-us/articles/56266627933465-Understanding-Piano-Roll-View-in-Cakewalk-Next)：参考键盘、时间标尺、力度栏、导航器，以及 Smart 的选择／移动／边缘缩放与 Draw 的拖绘分工。按本项目要求移除 Fill。
- [Cakewalk Next User Manual](https://bandlab.github.io/cakewalk/docs/Cakewalk_Next_User_Manual.pdf)，第141–145页：已读取绘制、Shift音高锁定、Ctrl框选增选、组合选择、整组拖动、两端缩放、Esc取消、分割／合并和双击删除的具体说明。0.6将音符手势从短按／长按区分改为直接拖动；和弦块保留用户要求的长按缩放。本项目额外允许 Smart 直接拖空白框选，分割采用二等分，最低至六十四分音符或对应三连音，合并限定为按行连续的音符。当前实现逐音力度与固定轨道 CC7，不包含通用 CC 自动化曲线或完整 DAW 音频剪辑功能。
- [Import Audio/MIDI files into Next](https://help.cakewalk.com/hc/en-us/articles/13327425804569-Import-Audio-MIDI-files-into-Next)：文档确认 Insert 菜单及拖入 Clips 面板的导入入口。

迁移使用标准 MIDI Type 1、960 PPQ、共同 tick 0 与共同结束时间。项目按 MIDI 编号保留音高，不依赖不同 DAW 的八度名称。没有读写 Cakewalk 专有工程格式，尚未在 Cakewalk Next 程序内完成实际导入验收。

- [Understanding Transport Controls](https://help.cakewalk.com/hc/en-us/articles/45227757109529-Understanding-Transport-Controls)：参考播放／暂停、Now Time 定位、标尺双击播放及 W 返回定位的交互；本项目“回放”从最近在时间轴或制谱谱面选定的起点重播，保持原播放或暂停状态。

## Windows 音源

- [midiOutGetDevCapsW](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-midioutgetdevcapsw)：枚举已安装输出设备的名称。
- [midiOutOpen](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-midioutopen)：以设备编号或 MIDI_MAPPER 打开 WinMM 输出。默认使用 Mapper，两轨可独立路由并发送 GM Program Change 与 CC7。

## Hooktheory / Hookpad

- [Hookpad User Guide — Playback and Voicing](https://www.hooktheory.com/support/hookpad#playback-and-voicing)：参考和弦块与伴奏节奏型分离、配音八度和独立音量的交互概念。

这里的持续柱式、四分柱式、八分柱式、上行/下行琶音、阿尔贝蒂低音、低音+和弦及反拍型均以本项目代码生成；未提取或分发 Hooktheory 的声音、图形或私有预设。

## 和弦识别算法

- [PyChord analyzer.py](https://github.com/yuma-m/pychord/blob/master/pychord/analyzer.py)
- [PyChord MIT license](https://github.com/yuma-m/pychord/blob/master/LICENSE)

参考其“轮换候选根音→换算相对音程→匹配和弦模板→保留低音转位”的算法思路。`popscore/recognition.py` 为独立实现，没有复制 PyChord 源码；和弦进行模块另行使用原样 PyChord 运行时依赖；它用去重后的 pitch-class 集合匹配本项目模板，消除八度重复，保留所有精确匹配，按已有标记与实际最低音排序。

识别范围为一个和弦块中的全部实际音符，适合柱式、琶音和自定义伴奏。经过音会导致不匹配；此时显示 `?`，不会强行套用近似标签。C6 / Am7 等歧义会保留候选，用户可选择。分段可按拍设置，分析不会擅自改变主音或调式。

## Helio 选区变换

- [Helio Refactoring](https://docs.helio.fm/refactoring.html)：参考逆行、旋律倒影及组合操作的交互概念。
- [Helio release notes](https://github.com/helio-fm/helio-sequencer/blob/develop/CHANGELOG.md)：参考调内移动与相邻音符合并。

`operations.py` 独立实现上述变换，没有复制 Helio 源码。逆行以音符片段的首尾时间为界反射音符起止；倒影使用最低／最高调内级数之和减去原级数，保持选区的调内音域。复制不改变原音符；粘贴按目标音符起点的调性还原。直接复制保留调外音；逆行、倒影及组合操作拒绝含调外音的源选区。一般音程倒影也可以围绕其他轴定义，本项目采用固定且可复现的选区音域中点。

## 打包

- [Qt for Python deployment](https://doc.qt.io/qtforpython-6/deployment/index.html)
- [PyInstaller](https://pyinstaller.org/en/stable/)

使用 PyInstaller 目录式免安装包，Qt DLL 独立保留。依赖版本、许可证与上游来源随包附带；用户自己的 Windows 字体不随包复制。


## 记号与操作约定

- 界面约定：Draw 单击删除；直接复制以外的变换只接受调内源音。完整操作与符号位置规则已收录在随包帮助中。
- [MusicXML 4.0 sound](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/sound/)：D.C.、D.S.、Segno、Coda、Fine 的关联语义。
- [MusicXML 4.0 repeat](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/repeat/)：跳转后的反复策略（N/R）。
- [Steinberg Dorico Popover Reference](https://www.steinberg.help/api/khub/documents/NNqtt0gVE9kWZRClp6krTQ/content)：ritardando 属于渐慢。本版 rit. 采用“渐慢（ritardando）”，不与 ritenuto（立即放慢）混用。

反复压缩独立实现，比较与 MIDI 导出相同的内部演奏数据；谱面符号不注入 MIDI 跳转、速度或音量自动化。界面上的演奏提示不表示已从 MIDI 证明演奏意图。


## 随包谱例与符号位置

使用随包的 `examples/lingfeng-symbols.lfs` 检查普通反复和尾声跳转，使用 `examples/lingfeng-lyric-bars.lfs` 检查歌词、说唱和小节范围。无需外部谱例文件。

小节线、双小节线、结束线与反复线位于小节边界；Segno、Coda 位于上方；D.C.、D.S.、N/R、Fine、F.O.、rit.、ad lib. 位于下方。歌词始终在网格下方，文字提示在歌词之后。当前不提供一二房、装饰音或自由连线工具。

## 0.12 MIDI 输入与量化

- [music21 Stream.quantize](https://music21.org/music21docs/moduleReference/moduleStreamBase.html#music21.stream.base.Stream.quantize)：候选细分格点、分别量化起点和时长、利用下一起点改善量化间隙。参考算法思想，独立实现，不引入 music21 依赖或复制源代码。附加保守的连续三连音证据判断；不是完美节奏识别。
- [music21 Tuplets](https://music21.org/music21docs/usersGuide/usersGuide_19_duration2.html)：三连音有理时值。960 PPQ 下常规 1/64 为 60 ticks，对应三连音为 40 ticks。
- [Microsoft midiInOpen](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-midiinopen)、[MIM_DATA](https://learn.microsoft.com/en-us/windows/win32/multimedia/mim-data)、[midiInStart](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-midiinstart)：WinMM 输入句柄、短消息和设备时间戳。驱动回调只入队，Qt 主线程定时消费，音符起止强制使用当前网格。MIDI 驱动和实体键盘仍需要实际硬件验证。


## 0.13 歌词输入

- [Hookpad v1 用户手册 — Lyrics](https://www.hooktheory.com/support/hookpad-v1)：下划线跳过音符，连字符自定义英语分音节。采用用户要求的这一输入规则；当前 Hookpad 新版也提供逐格歌词输入，不能把两个版本操作混为一谈。
- 中文逐字、同刻多声部按唯一 onset 匹配、`我/64.爱/64你/64` 显式说唱语法是本程序按用户要求实现的扩展，不声称是 Hookpad 既有功能。

## Windows 窗口与任务栏

- [Application User Model IDs](https://learn.microsoft.com/en-us/windows/win32/shell/appids)：主窗口与独立卷帘共用 `Lingfeng.ForPopMusic` 应用标识，交由 Windows 任务栏分组；独立窗口保留各自预览。程序不修改系统的任务栏合并偏好。
- [DWMWINDOWATTRIBUTE](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute)：为原生边框设置深浅主题及边框颜色，保留 Windows 缩放与贴靠行为。


## Windows 多窗口与任务栏 / Windows windows and taskbar

- [Window Features](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features)：有原生 owner 的窗口始终在 owner 上方，owner 最小化时还会联动隐藏。独立编辑器因此使用无 owner 的平级顶层窗口，应用自行管理其生命周期。
- [Application User Model IDs](https://learn.microsoft.com/en-us/windows/win32/shell/appids)：所有窗口共用进程级 AppUserModelID 以分组，不使用 owner 关系来实现任务栏分组。
- Peer top-level windows avoid the always-above and minimize/hide coupling of native owned windows. A shared process AppUserModelID provides taskbar grouping; application code manages editor lifetime.

## 应用开源许可 / Application open-source license

- [MIT License — Open Source Initiative](https://opensource.org/license/mit)：原创应用代码使用 MIT，正式条款随包附于 LICENSE。第三方组件保持各自许可，见 THIRD_PARTY.md。
- The original application code uses MIT, included as LICENSE. Third-party components retain their own licenses as listed in THIRD_PARTY.md.

## 0.34 和弦进行与音频导出

- [Hooktheory Popular Chord Progressions](https://www.hooktheory.com/theorytab/popular-chord-progressions)、[Trends](https://www.hooktheory.com/trends)：参考常见进行的音乐概念，自行用罗马数字整理预设，没有抓取谱例或图片。
- [PyChord](https://github.com/yuma-m/pychord)：1.4.1 的 Chord.transpose/components 用于和弦组成校验与移调；罗马数字语法、按起点调性解释和广播操作由本项目实现。
- [Microsoft MIDI messages](https://learn.microsoft.com/en-us/windows/win32/multimedia/sending-individual-midi-messages)：WinMM 输出 MIDI，不直接返回 PCM。
- [SoundCard](https://github.com/bastibe/SoundCard)：0.4.5 WASAPI loopback 采集默认扬声器输出，仅启用输出回录，不选择麦克风。
- [lameenc](https://github.com/chrisstaite/lameenc/tree/v1.8.1)：PCM 编码为 MP3；源码和许可随包提供。

离线钢琴／电钢琴由本项目原创的加法／FM 合成器生成，不复制 Windows GM 音源。实时回录需等待所选范围实际时长，并可能包含同输出设备上的其他音频；系统延迟不以固定毫秒值假定补偿。播放游标读取与 MIDI 调度相同的单调时钟，避免使用过期的 GUI 定时值。

Windows 回录工作线程分别初始化与释放 COM（包括重复导出），依据 [CoInitializeEx](https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-coinitializeex) 的线程局部初始化规则；不依赖 SoundCard 首次导入所在的已结束线程。


## 0.37 进行目录 / Progression catalogue

新增指定 Hooktheory 公开页面的 21 组完整和弦序列及短识别名称，保留来源说明。只包含音乐事实和自行实现的转换、检索及界面代码；未合并网页播放器代码、图片、歌曲谱例或 MIDI。完整清单与表示法见 [PROGRESSIONS.md](PROGRESSIONS.md)。没有增加依赖，原依赖许可不变。

The 21 complete harmonic recipes and short identifying names from the specified public Hooktheory page have source attribution. Only musical facts and independently implemented conversion, search and UI code are included; no website player code, images, song transcriptions or MIDI examples are bundled. See [PROGRESSIONS.md](PROGRESSIONS.md). Dependencies and their licenses are unchanged.

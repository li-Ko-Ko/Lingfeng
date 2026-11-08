# 第三方组件与来源 / Third-party notices and sources

伶风原创应用代码采用 [MIT](../LICENSE)。第三方组件、音源和运行库保留各自版权与许可，不被应用的 MIT 条款替换。实际版本见发行包 `build-info.json`，完整许可与版权文本见 `licenses/` 及各音源包。

Lingfeng's original code is MIT. Dependencies, synth packs and runtimes retain their own copyrights and licenses. Exact build versions are recorded in `build-info.json`; complete notices are included in `licenses/` and each synth pack.

## 组件与许可 / Components and licenses

| 组件 / Component | 版本 / Version | 条款及来源 / Terms and source |
| --- | --- | --- |
| CPython | 3.13.9 | PSF 及历史许可；`licenses/PYTHON.txt`；[源码](https://www.python.org/downloads/source/) |
| PySide6 Essentials / Shiboken6 | 6.9.2 | 本包使用 LGPL-3.0 适用组件；[对应源码](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.9.2-src/) |
| Qt Core / Gui / Widgets / Network / Svg 及平台、图像格式插件 | 6.9.2 | LGPL-3.0 及内置第三方条款；[对应源码](https://download.qt.io/archive/qt/6.9/6.9.2/submodules/) |
| PyInstaller bootloader | 6.20.0 | GPL-2.0 及 bootloader 分发例外；[源码与许可](https://github.com/pyinstaller/pyinstaller/tree/v6.20.0) |
| PyChord | 1.4.2 | MIT；和弦性质目录、组成校验与移调；[固定发行](https://pypi.org/project/pychord/1.4.2/)、[源码与许可](https://github.com/yuma-m/pychord) |
| SoundCard | 0.4.5 | BSD-3-Clause；WASAPI 输出与回录；[源码](https://github.com/bastibe/SoundCard) |
| lameenc / LAME | 1.8.1 / 3.100 | LGPL-3.0 / LGPL-2.0-or-later；[对应源码、哈希与替换说明](../licenses/audio-source/README.md) |
| NumPy | 2.2.6 | BSD-3-Clause 及随附 OpenBLAS、GCC Runtime Exception 等条款；[源码](https://github.com/numpy/numpy/tree/v2.2.6) |
| CFFI / pycparser | 2.1.1 / 3.12 | MIT（含 libffi 对应许可）/ BSD-3-Clause；[CFFI](https://github.com/python-cffi/cffi)、[pycparser](https://github.com/eliben/pycparser) |
| STK | 5.0.1 | STK 宽松许可；各音源包 `LICENSE-STK.txt`；[对应源码](https://github.com/thestk/stk/tree/5.0.1) |
| PFSynth | `2989410` | MIT；`LICENSE-PFSynth.txt`；[固定源码](https://github.com/olaugh/pfsynth/tree/2989410f821ef15e4992c2e092fdf07d57d54796) |
| OpenSSL、libffi、bzip2、zlib、liblzma、mpdecimal 等运行库 | 见随附清单 | Apache-2.0、MIT、BSD 类及 0BSD 等条款；保留 `licenses/runtime/` 与 `mpdecimal-COPYRIGHT.txt` |
| Microsoft VC/UCRT | 见实际二进制 | Microsoft 可再分发运行库条款；不是开源组件，不纳入应用 MIT |

各 wheel 的完整许可随包复制。NumPy 的完整 LICENSE.txt 包含其捆绑运行库条款，不能将整套内容统一标为 BSD。Qt 内置 FreeType、HarfBuzz、libpng、libjpeg-turbo、PCRE2、zlib、WebP、TIFF 等组件的许可与 attribution 保留在 `licenses/qt-6.9.2/`。

0.56 的和弦目录通过 PyChord 1.4.2 的公开 `QualityManager.get_qualities()` API 核对了全部 104 个名称（含同义符号），保留原有 21 项的顺序与音程，另包含本应用原有的密集排列 `add2 = 1 2 3 5`，合计 105 项。上游 `add9 = 1 3 5 9` 与 `add2` 分别保存；0.56 以前工程中的旧 `add9` 仍兼容迁移为 `add2`，不会改动显式 MIDI。`music/quality_catalog.py` 保存可重现的静态音程事实，使版本查询与工程模型导入无需先加载外部库。节奏、MIDI 保留、标记与候选排序仍由应用实现。

Version 0.56 checks all 104 upstream names and aliases against PyChord 1.4.2's public quality API, retaining legacy ordering and Lingfeng's separate close-position `add2`, for 105 supported choices. Upstream `add9` keeps its ninth voicing. Older documents retain the legacy `add9` to `add2` migration without rewriting explicit MIDI. A static degree catalogue allows dependency-free model/version imports; rhythm, annotation and candidate ranking remain original application code.

`licenses/qt-6.9.2/manifest.json` 记录从固定上游标签收集的许可、版权、attribution 文件及其 SHA-256。这是许可集合，不表示所有上游模块均被编入。当前包未引入 Qt Charts 等仅 GPL 的 Qt 模块；光栅绘制不分发未使用的 Mesa/LLVM `opengl32sw.dll`。

FreeType acknowledgment: Portions of the Qt runtime use the FreeType Project, copyright © 1996–2024 The FreeType Project (www.freetype.org). All rights reserved. FreeType is used under the FreeType License (FTL); the full upstream text and attribution metadata are included.

## 可替换库与对应源码 / Replacement and corresponding source

Qt、PySide6、Shiboken6 及编码器的 DLL/PYD 独立位于 `_internal/`，没有静态合并到伶风原创代码。可用与 Python 3.13、Windows x64、Qt/PySide 6.9.2 ABI 兼容的自建版本替换，或使用随附应用源码、`build.ps1` 和固定依赖文件重新构建。应用不限制为调试修改后的 LGPL 库而进行的逆向工程。

DLL/PYD files remain separate under `_internal/`. Compatible Python 3.13 / Windows x64 / Qt-PySide 6.9.2 builds can replace them, or the supplied application source can be rebuilt. Reverse engineering for debugging modifications to LGPL libraries is not restricted.

- [Qt 6.9.2 source archives](https://download.qt.io/archive/qt/6.9/6.9.2/submodules/) · [Qt for Python 6.9.2 source](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.9.2-src/) · [Qt licensing](https://doc.qt.io/archives/qt-6.9/licensing.html) · [LGPL v3](https://www.gnu.org/licenses/lgpl-3.0.html)
- `licenses/audio-source/` 包含 lameenc/LAME 对应源码归档、上游 Windows 构建补丁、SHA-256 与兼容扩展替换说明。LAME 静态构建于独立、可替换的 lameenc 扩展内，未合并到应用原创代码；采用上游 wheel，没有额外编码器补丁。

## 钢琴与电钢琴 / Piano and electric-piano packs

默认发行包随附 Greg Sullivan 电钢琴、GeneralUser GS 主包、三组 STK 和 PFSynth。Greg 使用 sfizz 播放 SFZ。GeneralUser GS 主包使用 FluidSynth 2.6.1 播放原版 SF2，在伶风中提供库 0 的 128 个基础 GM 音色。GS 变体库和鼓组可另装独立音源包。

Default releases bundle Greg Sullivan electric pianos, the main GeneralUser GS pack, three STK packs and PFSynth. Greg uses sfizz for SFZ. The main GeneralUser GS pack uses FluidSynth 2.6.1 to play the original SF2 and exposes the 128 standard GM sounds from bank 0 in Lingfeng. GS variation banks and drum kits use separate packs.

GeneralUser GS 主包保留上游的 `GeneralUser-GS-LICENSE.txt`，包括对部分采样来源的说明。该包及可选的 MuseScore Lite、YDP、FluidR3 GM 各自在 `runtime/` 保留 FluidSynth、libsndfile、mpg123 和 LAME 的 LGPL 条款、对应源码、版权文本、构建资料和所需补丁，以及 FLAC、Ogg、Vorbis、Opus 等依赖的通知。引擎及依赖 DLL 独立可替换。

The main GeneralUser GS pack retains the upstream `GeneralUser-GS-LICENSE.txt`, including the author's notes on sample provenance. The main pack and optional MuseScore Lite, YDP and FluidR3 GM each retain the applicable LGPL and permissive terms, corresponding source, notices, build information and patches for FluidSynth and its codec dependencies under `runtime/`. The runtime DLLs are independently replaceable. [FluidSynth](https://github.com/FluidSynth/fluidsynth) · [FluidR3 Debian source](https://deb.debian.org/debian/pool/main/f/fluid-soundfont/)

0.52 首次随附 `piano-small` 免费采样包，0.53 首次提供 Greg 与 FluidR3 GM 的可选下载。sfizz 1.2.3 Windows x64 C API 采用 BSD-2-Clause，完整源码归档和依赖通知位于 SFZ 音源包的 `runtime/`。构建脚本固定官方二进制与源码哈希。FluidR3 音色采用 MIT 许可。

Version 0.52 first bundled the free `piano-small` pack. Version 0.53 first offered Greg and FluidR3 GM as optional downloads. The BSD-2-Clause sfizz 1.2.3 runtime's complete source and dependency notices are included in each SFZ pack under `runtime/`. The builder pins official binary and source hashes. FluidR3 samples retain MIT terms.

| 样本 / Samples | 来源 / Source | 许可 / License |
| --- | --- | --- |
| Kawai upright | [FreePats KW](https://github.com/freepats/upright-piano-KW) | CC0-1.0 |
| Rhodes GM subset | [Jeff Learman / Discord GM](https://github.com/sfzinstruments/Discord-SFZ-GM-Bank) | CC0-1.0，仅这个独立 GM 子集 / This separately released GM subset only |
| Wurlitzer, CP80, Pianet T | [Greg Sullivan / kinwie](https://github.com/sfzinstruments/GregSullivan.E-Pianos) | CC-BY-3.0 |
| GeneralUser GS 2.0.3 | [S. Christian Collins and sample contributors](https://www.schristiancollins.com/generaluser.php) | GeneralUser GS License v2.0，含采样条款 / Includes sample terms |
| Optional MuseScore General Lite | [S. Christian Collins, Frank Wen and other contributors](https://people.debian.org/~tg/sf/) | MIT，保留上游署名与许可 / MIT with upstream credits and terms retained |
| Optional YDP Grand | [Zenph Studios and Mikhail Krishtal for OLPC (samples), Roberto / FreePats (SF2)](https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html#ydp-grand-piano) | CC-BY-3.0 |
| Optional Salamander grand | [Alexander Holm / Chisato Yamauchi / Jeff Learman](https://github.com/jlearman/zynthian-salamander-grand) | CC-BY-3.0 samples; CC0 SFZ |

各包保留许可、署名、固定版本、修改和文件 SHA-256。SFZ 与预设的调整包括明亮钢琴 EQ、电钢琴边缘音域、Rhodes 包络头和 Salamander 最低力度。录音样本保持原始编码。Salamander 可独立下载和安装。SFZ 音源使用已固定版本的 [sfizz 1.2.3](https://github.com/sfztools/sfizz/releases/tag/1.2.3)。

Packs retain licenses, attribution, revisions, mapping changes and file hashes. Recordings retain their original encoding. Salamander is available as a separate download. See `scripts/build_piano_packs.py` and the sound pack guide for source and reproduction details. [SOUNDBANKS](SOUNDBANKS.md)

## 合成音源 / Synth packs

三个 STK 包附带实际编译源码、重建命令、STK 许可与 MIT 桥接器许可。STK 修改包括内嵌单周期数学振荡器表、实例局部伪随机状态、预分配复音池、MIDI/包络处理、Sitar 线性延迟、滤波和力度校准。 [音源安装与 ABI](SOUNDBANKS.md)

PFSynth 由 John O’Laughlin 开发，钢琴模型源码和伶风适配器各自保留 MIT 许可。包内附实际编译的源码与拟合参数、重建命令、上游版本及修改记录。上游拟合参数来自对 Alexander Holm 的 Salamander 钢琴采样（CC BY 3.0）和 Modartt Pianoteq 6 输出的测量。随包内容为模型参数和实现，原始录音和演示素材保留在各自上游来源。 [PFSynth 上游来源说明](https://github.com/olaugh/pfsynth/blob/2989410f821ef15e4992c2e092fdf07d57d54796/README.md)

Zig 0.14.1 及静态编译的 libc++、libc++abi、libunwind、MinGW 运行库许可保留在 `synths/<pack>/licenses/zig-runtime/`。Windows 输出适配器修正 SoundCard 0.4.5 短缓冲写入与提交长度问题，未修改已安装的 SoundCard 包。MP3 署名说明记录实际所选音源；软件与音源许可不替代作品、歌词或录音素材授权。

Each STK pack includes the source used to build it, rebuild instructions and notices. The bridge and presets are MIT. STK and compiler runtimes retain their own terms.

The PFSynth piano model by John O’Laughlin and Lingfeng's adapter retain their MIT licenses. The pack contains the source used to build it, fitted parameters, rebuild instructions and a record of the pinned revision and changes. Upstream measured Alexander Holm's Salamander piano samples (CC BY 3.0) and output from Modartt's Pianoteq 6 to fit its parameters. The pack ships model parameters and their implementation. The recordings and demo material remain with their upstream sources. [PFSynth source notes](https://github.com/olaugh/pfsynth/blob/2989410f821ef15e4992c2e092fdf07d57d54796/README.md)

## 实现参考与署名 / Implementation references

下列为交互、算法或音乐表示的参考来源；应用界面、绘制、节奏与演奏逻辑由本项目独立实现，没有合并这些产品的专有代码、图像、声音或播放器资源。

| 来源 / Reference | 参考范围 / Scope |
| --- | --- |
| [Cakewalk Next Piano Roll](https://help.cakewalk.com/hc/en-us/articles/56266627933465-Understanding-Piano-Roll-View-in-Cakewalk-Next)、[用户手册](https://bandlab.github.io/cakewalk/docs/Cakewalk_Next_User_Manual.pdf)（141–145 页）、[Transport](https://help.cakewalk.com/hc/en-us/articles/45227757109529-Understanding-Transport-Controls) | Smart/Draw 卷帘、选择/移动/缩放与传输交互；使用标准 MIDI 迁移，不读写 Cakewalk 专有工程 |
| [Hookpad Playback and Voicing](https://www.hooktheory.com/support/hookpad#playback-and-voicing)、[Hookpad v1](https://www.hooktheory.com/support/hookpad-v1) | 和弦块、节奏型与歌词交互；音乐生成和歌词扩展独立实现 |
| [PyChord analyzer](https://github.com/yuma-m/pychord/blob/master/pychord/analyzer.py)、[MIT license](https://github.com/yuma-m/pychord/blob/master/LICENSE) | `music/recognition.py` 参考根音轮换与音程模板匹配思路，未复制源码；进行模块另使用原样 PyChord 依赖 |
| [Helio Refactoring](https://docs.helio.fm/refactoring.html)、[源码与许可](https://github.com/helio-fm/helio-sequencer) | 逆行、倒影、调内移动与合并的交互概念；未复制上游 GPL-3.0 源码 |
| [music21 quantize](https://music21.org/music21docs/moduleReference/moduleStreamBase.html#music21.stream.base.Stream.quantize)、[Tuplets](https://music21.org/music21docs/usersGuide/usersGuide_19_duration2.html) | 候选格点与三连音时间表示；独立实现，不引入 music21 依赖或源码 |
| [MusicXML sound](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/sound/)、[repeat](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/repeat/)、[Dorico popovers](https://www.steinberg.help/api/khub/documents/NNqtt0gVE9kWZRClp6krTQ/content) | D.C./D.S./Segno/Coda/Fine、反复策略及 ritardando 等记号语义；不表示支持 MusicXML 导入导出 |
| [Microsoft WinMM output](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-midioutopen)、[input](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-midiinopen)、[CoInitializeEx](https://learn.microsoft.com/en-us/windows/win32/api/combaseapi/nf-combaseapi-coinitializeex) | MIDI 设备、消息、时间戳与线程局部 COM 生命周期 |
| [Windows AppUserModelID](https://learn.microsoft.com/en-us/windows/win32/shell/appids)、[Window Features](https://learn.microsoft.com/en-us/windows/win32/winmsg/window-features)、[DWM](https://learn.microsoft.com/en-us/windows/win32/api/dwmapi/ne-dwmapi-dwmwindowattribute) | 多窗口任务栏分组、平级窗口生命周期与原生边框主题 |

内置进行目录整理自 [Hooktheory Popular Chord Progressions](https://www.hooktheory.com/theorytab/popular-chord-progressions)。21 组公开目录与另 5 组默认进行的序列、来源及转位表示见 [PROGRESSIONS](PROGRESSIONS.md)。只包含音乐事实和短识别名称，不包含网页播放器代码、图片、歌曲转录或原始 MIDI。

伶风与 Hooktheory、Cakewalk、Helio 及其权利人没有隶属、合作、赞助或认可关系。相关名称和商标归各自权利人所有；本项目开源许可不授予这些商标或专有资源的使用权。

Lingfeng is independently implemented and is not affiliated with, partnered with, sponsored by or endorsed by these products or their rights holders. Their names and trademarks remain theirs; the application's license grants no rights to those trademarks or proprietary resources.

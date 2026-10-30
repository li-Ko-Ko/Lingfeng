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
| PyChord | 1.4.1 | MIT；和弦组成校验与移调；[源码与许可](https://github.com/yuma-m/pychord) |
| SoundCard | 0.4.5 | BSD-3-Clause；WASAPI 输出与回录；[源码](https://github.com/bastibe/SoundCard) |
| lameenc / LAME | 1.8.1 / 3.100 | LGPL-3.0 / LGPL-2.0-or-later；[对应源码、哈希与替换说明](../licenses/audio-source/README.md) |
| NumPy | 2.2.6 | BSD-3-Clause 及随附 OpenBLAS、GCC Runtime Exception 等条款；[源码](https://github.com/numpy/numpy/tree/v2.2.6) |
| CFFI / pycparser | 2.1.1 / 3.12 | MIT（含 libffi 对应许可）/ BSD-3-Clause；[CFFI](https://github.com/python-cffi/cffi)、[pycparser](https://github.com/eliben/pycparser) |
| STK | 5.0.1 | STK 宽松许可；各音源包 `LICENSE-STK.txt`；[对应源码](https://github.com/thestk/stk/tree/5.0.1) |
| OpenSSL、libffi、bzip2、zlib、liblzma、mpdecimal 等运行库 | 见随附清单 | Apache-2.0、MIT、BSD 类及 0BSD 等条款；保留 `licenses/runtime/` 与 `mpdecimal-COPYRIGHT.txt` |
| Microsoft VC/UCRT | 见实际二进制 | Microsoft 可再分发运行库条款；不是开源组件，不纳入应用 MIT |

各 wheel 的完整许可随包复制。NumPy 的完整 LICENSE.txt 包含其捆绑运行库条款，不能将整套内容统一标为 BSD。Qt 内置 FreeType、HarfBuzz、libpng、libjpeg-turbo、PCRE2、zlib、WebP、TIFF 等组件的许可与 attribution 保留在 `licenses/qt-6.9.2/`。

`licenses/qt-6.9.2/manifest.json` 记录从固定上游标签收集的许可、版权、attribution 文件及其 SHA-256。这是许可集合，不表示所有上游模块均被编入。当前包未引入 Qt Charts 等仅 GPL 的 Qt 模块；光栅绘制不分发未使用的 Mesa/LLVM `opengl32sw.dll`。

FreeType acknowledgment: Portions of the Qt runtime use the FreeType Project, copyright © 1996–2024 The FreeType Project (www.freetype.org). All rights reserved. FreeType is used under the FreeType License (FTL); the full upstream text and attribution metadata are included.

## 可替换库与对应源码 / Replacement and corresponding source

Qt、PySide6、Shiboken6 及编码器的 DLL/PYD 独立位于 `_internal/`，没有静态合并到伶风原创代码。可用与 Python 3.13、Windows x64、Qt/PySide 6.9.2 ABI 兼容的自建版本替换，或使用随附应用源码、`build.ps1` 和固定依赖文件重新构建。应用不限制为调试修改后的 LGPL 库而进行的逆向工程。

DLL/PYD files remain separate under `_internal/`. Compatible Python 3.13 / Windows x64 / Qt-PySide 6.9.2 builds can replace them, or the supplied application source can be rebuilt. Reverse engineering for debugging modifications to LGPL libraries is not restricted.

- [Qt 6.9.2 source archives](https://download.qt.io/archive/qt/6.9/6.9.2/submodules/) · [Qt for Python 6.9.2 source](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.9.2-src/) · [Qt licensing](https://doc.qt.io/archives/qt-6.9/licensing.html) · [LGPL v3](https://www.gnu.org/licenses/lgpl-3.0.html)
- `licenses/audio-source/` 包含 lameenc/LAME 对应源码归档、上游 Windows 构建补丁、SHA-256 与兼容扩展替换说明。LAME 静态构建于独立、可替换的 lameenc 扩展内，未合并到应用原创代码；采用上游 wheel，没有额外编码器补丁。

## 合成音源 / Synth packs

三个 STK 包附带实际编译源码、重建命令、STK 许可与 MIT 桥接器许可；安装及 ABI 见 [SOUNDBANKS](SOUNDBANKS.md)。STK 修改包括内嵌单周期数学振荡器表、实例局部伪随机状态、预分配复音池、MIDI/包络处理、Sitar 线性延迟、滤波和力度校准。没有录制乐器采样资产；Microsoft 系统音源与用户系统字体不随包分发。

Zig 0.14.1 及静态编译的 libc++、libc++abi、libunwind、MinGW 运行库许可保留在 `synths/<pack>/licenses/zig-runtime/`。Windows 输出适配器修正 SoundCard 0.4.5 短缓冲写入与提交长度问题，未修改已安装的 SoundCard 包。MP3 署名说明记录实际所选音源；软件与音源许可不替代作品、歌词或录音素材授权。

Each STK pack includes the compiled source, rebuild instructions and notices. Host, bridge and presets are MIT; STK and compiler runtimes retain their own terms. No Microsoft MIDI sound-bank, system-font or recorded-instrument assets are redistributed.

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

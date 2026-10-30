# 许可核对 / License review — 0.41.0

核对日期：2026-10-29；0.51 路径整理：2026-10-30。范围：`lingfeng/`、`main.py`、资源生成脚本、固定版本构建依赖以及 Windows 目录式发行包中的动态库。以下是源码与分发内容核对，不是对商标、专利或所有司法辖区的法律保证。

Reviewed on 2026-10-29: application source, resource-generation scripts, pinned build dependencies and DLLs in the Windows portable release. This is a source/distribution review, not a guarantee about trademarks, patents or every jurisdiction.

## 结论 / Findings

原创应用代码继续使用 MIT；整个发行包包含多种依赖许可。0.34 新增 PyChord、SoundCard、lameenc、NumPy、CFFI 和 pycparser。逐项保留 wheel 许可和运行库版权；MP3 编码器另附对应源码和重建说明。Helio、Hookpad 与 Cakewalk 仍仅为公开交互参考，没有合并其代码。

Original application code remains MIT. The distribution contains separately licensed dependencies. Version 0.34 adds PyChord, SoundCard, lameenc, NumPy, CFFI and pycparser. Wheel/runtime notices are retained; the MP3 encoder includes corresponding source and rebuild instructions. Helio, Hookpad and Cakewalk remain interaction references, with no code incorporated.

| 内容 / Component | 采用条款 / Terms used | 兼容与处理 / Treatment |
| --- | --- | --- |
| Lingfeng 原创代码 | MIT | 保留根目录及 source/LICENSE；retain both license copies. |
| PySide6 Essentials、Shiboken6 6.9.2 | LGPL-3.0 | 动态加载，不静态合并进 MIT 源码；保留 LGPL 与 GPL 全文、版权和对应源码入口，允许替换兼容库及调试修改后的库。Dynamically loaded; notices, source access and replacement/rebuild instructions retained. |
| Qt Core、Gui、Widgets、Network、Svg 与所用插件 6.9.2 | LGPL-3.0 及内置第三方许可 | 本包未引入 Qt Charts 等仅 GPL 的 Qt 模块。逐项上游许可及 attribution 元数据已补充在 licenses/qt-6.9.2；其中包含上游模块许可的完整集合，不表示每个模块／平台代码都已编入。No GPL-only Qt modules are included; the notice collection is a documented superset. |
| Qt 内置 FreeType、HarfBuzz、libpng、libjpeg-turbo、PCRE2、zlib、WebP、TIFF 等 | FTL、MIT、BSD、Libpng、IJG 等 | 保留项目版权与条款；FreeType 选择 FTL，并明确署名。Retain notices and use FreeType under FTL. |
| CPython 3.13.9 | PSF 及历史许可 | licenses/PYTHON.txt；原样运行库，与 MIT 应用并存。Unmodified runtime with its own license. |
| OpenSSL、libffi、bzip2、zlib、liblzma、mpdecimal | Apache-2.0、MIT、BSD 类及 0BSD 等 | 保留 licenses/runtime 与 mpdecimal-COPYRIGHT.txt，不重新许可。Preserve runtime notices. |
| Microsoft VC/UCRT | Microsoft 可再分发运行库条款 | 不是开源组件，不纳入应用 MIT；保留微软条款。Proprietary redistributable runtime, outside the application MIT license. |
| PyInstaller 6.20.0 bootloader | GPL-2.0 + bootloader 分发例外 | 上游例外允许输出程序采用自己的许可；保留 COPYING.txt。The bootloader exception permits the generated application to retain its license. |
| PyChord 1.4.1 | MIT | 原样依赖用于和弦进行；保留版权与许可。Unmodified dependency with notices. |
| Helio 交互参考 | 上游 GPL-3.0 | 当前仅参考交互概念，没有合并其代码；不能据此把未来复制的 GPL 代码直接改标 MIT。No code included; future GPL code reuse needs a separate compatibility review. |

FreeType acknowledgment: Portions of the Qt runtime use the FreeType Project, copyright © 1996–2024 The FreeType Project (www.freetype.org). All rights reserved. FreeType is used under the FreeType License (FTL); the full upstream text and attribution metadata are included.

## 本次补充 / Corrections in this release

- 0.26 的 Qt 许可收集主要依赖 Python wheel 的 dist-info，未完整覆盖 Qt 内置组件。0.27 从 `v6.9.2` 官方源码固定标签收集许可、版权及 attribution，保留原文；manifest.json 记录来源 URL 与 SHA-256。
- 更新实际模块清单，补列 Network、Svg、图像格式插件以及系统运行库；Microsoft 运行库与原创开源代码明确分开。
- 软件只使用 QWidget/QPainter 光栅绘制，发行包移除 PySide 自动收集的可选 `opengl32sw.dll`（Mesa/LLVM 软件 OpenGL 回退库），避免分发未使用的额外二进制组件。原 PySide 安装不受影响。

Version 0.26's wheel-metadata collection did not cover all embedded Qt notices. Version 0.27 adds verbatim notices and attribution metadata from pinned official source tags, with source URLs and SHA-256 hashes. The runtime inventory now explicitly includes Network, Svg, image plugins and Microsoft runtimes. The unused optional Mesa/LLVM software OpenGL fallback is omitted from this raster-widget application; the installed development environment is unchanged.

## 可替换库与对应源码 / Replacement and corresponding source

`_internal/` 及其 PySide6、shiboken6 子目录中的 DLL/PYD 保持分离；可使用与 Python 3.13、Windows x64、Qt/PySide 6.9.2 ABI 兼容的自建版本替换。完整应用源码与 build.ps1、固定依赖文件随包提供，支持重新构建。应用许可不限制为调试修改后的 LGPL 库而进行的逆向工程。以下为与二进制版本对应的上游源码及条款入口；上游库未由本项目修改。

DLL/PYD files remain separate under `_internal/` and its PySide6/Shiboken6 subdirectories. Replace them with compatible Python 3.13 / Windows x64 / Qt-PySide 6.9.2 builds, or rebuild the supplied application source. Reverse engineering for debugging modifications to LGPL libraries is not restricted. The unmodified upstream source and license references are:

- [Qt 6.9.2 source archives](https://download.qt.io/archive/qt/6.9/6.9.2/submodules/)
- [Qt for Python 6.9.2 source](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.9.2-src/)
- [Qt 6.9 licensing](https://doc.qt.io/archives/qt-6.9/licensing.html)
- [LGPL v3](https://www.gnu.org/licenses/lgpl-3.0.html)
- [PyInstaller 6.20.0 COPYING](https://github.com/pyinstaller/pyinstaller/blob/v6.20.0/COPYING.txt)
- [PyChord license](https://github.com/yuma-m/pychord/blob/master/LICENSE)
- [Helio license](https://github.com/helio-fm/helio-sequencer/blob/develop/LICENSE)

核对结果适用于本次实际包与独立实现。未来增加第三方代码、插件、音源或字体时，需要重新核对实际许可证；“灵感来自”或“采用 MIT”本身不替代授权。

These findings apply to this release and its independent implementation. New third-party code, plugins, sound libraries or fonts require review of their actual terms; attribution or the application's MIT license alone is not permission to use them.

## 0.34 MP3 与进行依赖核对

新增版本与条款见 THIRD_PARTY.md。SoundCard 使用 BSD-3-Clause，CFFI 为 MIT，pycparser 为 BSD-3-Clause。NumPy 2.2.6 wheel 的完整 LICENSE.txt 保留 OpenBLAS、GCC runtime exception 等捆绑说明。lameenc 1.8.1 为 LGPL-3.0，内含 LAME 3.100（LGPL-2.0-or-later）；采用上游现成 wheel，不增加补丁。对应源码 archive、上游 Windows 补丁及哈希已保存在 licenses/audio-source/。发行包动态加载独立 .pyd，允许用户用兼容重建版本替换；应用源码全量提供，不限制为调试修改库而进行逆向工程。LGPL/GPL 完整文本由依赖许可副本和原有 licenses 保留。

SoundCard is BSD-3-Clause, CFFI MIT and pycparser BSD-3-Clause. NumPy's complete wheel notice includes bundled OpenBLAS and GCC runtime exceptions. lameenc 1.8.1 uses LGPL-3.0 with LAME 3.100 under LGPL-2.0-or-later. Unmodified upstream wheels are used. Matching source archives, upstream Windows patches and hashes are supplied in licenses/audio-source/. The independently loaded .pyd can be replaced with a compatible rebuilt version. Complete application source is supplied; reverse engineering to debug modified libraries is not prohibited. Full LGPL/GPL texts are retained with dependency notices.


## 0.37 进行目录 / Progression catalogue

新增指定 Hooktheory 公开页面的 21 组完整和弦序列及短识别名称，保留来源说明。只包含音乐事实和自行实现的转换、检索及界面代码；未合并网页播放器代码、图片、歌曲谱例或 MIDI。完整清单与表示法见 [PROGRESSIONS.md](PROGRESSIONS.md)。没有增加依赖，原依赖许可不变。

The 21 complete harmonic recipes and short identifying names from the specified public Hooktheory page have source attribution. Only musical facts and independently implemented conversion, search and UI code are included; no website player code, images, song transcriptions or MIDI examples are bundled. See [PROGRESSIONS.md](PROGRESSIONS.md). Dependencies and their licenses are unchanged.


## 0.44 合成音源 / Native synthesis packs

程序本体不再分发 sfizz 或采样库。STK 5.0.1 的三个轻量音源包随程序合并提供（总大小超过本体时独立打包），使用上游宽松许可；每包保留版权、许可、实际编译源码和重建命令。Lingfeng 的桥接器、预设和宿主为 MIT。STK 修改为内嵌单周期数学振荡器表、实例局部伪随机状态；复音、MIDI、淡入淡出由桥接器实现。无录制乐器采样资产。来源：https://github.com/thestk/stk/tree/5.0.1 。详细接口与安装见 SOUNDBANKS.md。

The application no longer distributes sfizz or recorded sample banks. Three lightweight STK 5.0.1 packs ship with the application (separately if their combined size exceeds the core) under the upstream permissive terms with notices, compiled source and build instructions. Host, bridge and presets are MIT. Oscillator tables are synthetic single-cycle data. Windows MIDI assets are not redistributed. Export credits identify the actual selected packs; composition and lyrics rights remain separate.

原生包静态编译所用 Zig 0.14.1 / libc++ / libc++abi / libunwind / MinGW 运行库许可随包保存在 `synths/<pack>/licenses/zig-runtime/`。Windows 输出适配器修正 SoundCard 0.4.5 短缓冲写入与提交长度不一致的问题；未修改已安装的 SoundCard 包。

0.44 增加 Sitar、BlowHole、BlowBotl、Recorder、PercFlut、FMVoices，沿用同一 STK 5.0.1 许可；修改的 Sitar 线性延迟、桥接滤波和力度响应随源码提供。实际包包含对应源码与 Zig 运行库许可。

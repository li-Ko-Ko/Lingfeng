# 第三方组件与来源

## 应用许可 / Application license

伶风原创应用代码采用 MIT 许可证，完整条款在发行包根目录及 `source/` 的 `LICENSE`。下列依赖及其版权、许可证不被 MIT 条款替换；这些组件依各自的许可证分发。

Lingfeng's original application code uses the MIT License, supplied as `LICENSE` at the release root and inside `source/`. The dependencies below retain their copyright notices and licenses; they are distributed under those licenses, not relicensed under MIT.

分发包使用独立动态库；`_internal` 中的 Qt DLL 可以用兼容版本替换。`source/` 含应用源码与重建脚本。应用不限制为调试修改后的 LGPL 库而进行的逆向工程。

| 组件 | 版本 | 许可与来源 |
| --- | --- | --- |
| CPython | 见 build-info.json | Python Software Foundation License；[源码与许可](https://www.python.org/downloads/source/) |
| PySide6 Essentials / Shiboken6 | 6.9.2 | LGPL v3 / GPL / 商业许可选项；本包使用 LGPL 适用组件；[Qt for Python 6.9.2 源码](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.9.2-src/) |
| Qt Core / Gui / Widgets / Network / Svg 及平台、图像格式插件 | 6.9.2 | LGPL v3 及内置组件许可；随附固定标签上游许可与 attribution；[对应 Qt 6.9.2 源码](https://download.qt.io/archive/qt/6.9/6.9.2/submodules/) |
| PyInstaller 引导程序 | 6.20.0 | GPL 及分发例外；[源码](https://github.com/pyinstaller/pyinstaller/tree/v6.20.0) |

精确依赖版本在 `build-info.json`，完整第三方许可在 `licenses/`。这些许可不改变各组件原作者的版权。Qt 依赖的字体、图像等组件许可一并保留在上游许可目录中。

0.27 核对报告见 [LICENSE_AUDIT.md](LICENSE_AUDIT.md)。`licenses/qt-6.9.2/manifest.json` 记录 167 个从官方固定标签收集的许可、版权与 attribution 文件及其 SHA-256；此目录是上游许可的集合，不表示所有模块均已编入。Microsoft VC/UCRT 属于可再分发的专有运行库，并非 MIT 或开源组件。FreeType 使用 FTL：Portions of the Qt runtime use the FreeType Project, copyright © 1996–2024 The FreeType Project (www.freetype.org). All rights reserved.

See [LICENSE_AUDIT.md](LICENSE_AUDIT.md) for the 0.27 review. The pinned Qt notice manifest records 167 upstream files and their SHA-256 hashes; it is a notice superset, not a list of all compiled modules. Microsoft VC/UCRT are proprietary redistributable runtimes, outside the original application's MIT license. FreeType is used under FTL, with attribution above and full upstream notices included.

和弦识别为本项目独立实现；0.34 新增 PyChord 1.4.1 运行时依赖，用于和弦进行中的组成校验与移调，保留其 MIT 许可。见 REFERENCES.md。Hooktheory 和 Cakewalk 名称仅用于解释参考来源和迁移目标；没有打包其软件、音源或资源。

伶风的创作与编辑体验受 Hooktheory 和 Cakewalk（尤其是 Cakewalk Next）启发，应用由本项目独立实现；不存在与这些产品或其权利人的隶属、合作、赞助或认可关系。相关名称和商标归各自权利人所有。开源许可不授予这些商标或专有资源的使用权，也不代替必要的第三方授权。

Lingfeng's composition and editing experience is inspired by Hooktheory and Cakewalk, especially Cakewalk Next, and is independently implemented. It is not affiliated with, partnered with, sponsored by or endorsed by those products or their rights holders. Their names and trademarks belong to their respective owners. The open-source license grants no rights to those trademarks or proprietary resources and does not replace any required third-party authorization.

实时与离线音频通过独立 STK 合成音源包播放，也支持 Windows MIDI；中文字体使用用户系统字体。未将 Microsoft 系统音源或字体文件复制进分发包。

## 0.34 新增依赖 / Added dependencies

| 组件 / Component | 版本 / Version | 许可与用途 / License and use |
| --- | --- | --- |
| PyChord | 1.4.1 | MIT；进行和弦校验与移调 / progression chord validation and transposition |
| SoundCard | 0.4.5 | BSD-3-Clause；Windows WASAPI 输出回录 / output loopback |
| lameenc | 1.8.1 | LGPL-3.0；独立可替换的 MP3 编码扩展 / replaceable MP3 extension |
| LAME | 3.100 | LGPL-2.0-or-later；lameenc 的编码引擎 / encoding engine |
| NumPy | 2.2.6 | BSD-3-Clause 及随附 OpenBLAS、GCC Runtime Exception 等条款 / synthesis and audio buffers, with bundled notices |
| CFFI | 2.1.1 | MIT，内含 libffi 对应许可 / WASAPI binding support |
| pycparser | 3.12 | BSD-3-Clause；C 声明解析 / C declaration parser |

各 wheel 的完整许可随包复制。NumPy 的 LICENSE.txt 包含其捆绑运行库条款，不将它们统一标为 BSD。lameenc 和 LAME 对应版本源码、上游构建补丁、SHA-256 与兼容替换说明在 licenses/audio-source/。lameenc 将 LAME 静态构建到可替换的 Python 扩展内；没有静态合并到伶风原创代码。应用源码与构建脚本随包提供，允许调试、修改和替换 LGPL 组件。

Full wheel notices are copied into the release. NumPy's LICENSE.txt retains its bundled runtime terms rather than relabeling all code as BSD. Corresponding lameenc/LAME sources, the upstream build patch, hashes and replacement instructions are in licenses/audio-source/. LAME is statically built into the replaceable lameenc extension, not into Lingfeng's original code. Application source and rebuild scripts are supplied, allowing debugging, modification and replacement of LGPL components.

来源 / Sources: https://github.com/yuma-m/pychord · https://github.com/bastibe/SoundCard · https://github.com/chrisstaite/lameenc · https://lame.sourceforge.io/ · https://numpy.org/ · https://github.com/python-cffi/cffi · https://github.com/eliben/pycparser


## 0.37 进行目录 / Progression catalogue

新增指定 Hooktheory 公开页面的 21 组完整和弦序列及短识别名称，保留来源说明。只包含音乐事实和自行实现的转换、检索及界面代码；未合并网页播放器代码、图片、歌曲谱例或 MIDI。完整清单与表示法见 [PROGRESSIONS.md](PROGRESSIONS.md)。没有增加依赖，原依赖许可不变。

The 21 complete harmonic recipes and short identifying names from the specified public Hooktheory page have source attribution. Only musical facts and independently implemented conversion, search and UI code are included; no website player code, images, song transcriptions or MIDI examples are bundled. See [PROGRESSIONS.md](PROGRESSIONS.md). Dependencies and their licenses are unchanged.


## 0.44 合成音源 / Native synthesis packs

程序本体不再分发 sfizz 或采样库。STK 5.0.1 的三个轻量音源包随程序合并提供（总大小超过本体时独立打包），使用上游宽松许可；每包保留版权、许可、实际编译源码和重建命令。Lingfeng 的桥接器、预设和宿主为 MIT。STK 修改为内嵌单周期数学振荡器表、实例局部伪随机状态；复音、MIDI、淡入淡出由桥接器实现。无录制乐器采样资产。来源：https://github.com/thestk/stk/tree/5.0.1 。详细接口与安装见 SOUNDBANKS.md。

The application no longer distributes sfizz or recorded sample banks. Three lightweight STK 5.0.1 packs ship with the application (separately if their combined size exceeds the core) under the upstream permissive terms with notices, compiled source and build instructions. Host, bridge and presets are MIT. Oscillator tables are synthetic single-cycle data. Windows MIDI assets are not redistributed. Export credits identify the actual selected packs; composition and lyrics rights remain separate.

原生包静态编译所用 Zig 0.14.1 / libc++ / libc++abi / libunwind / MinGW 运行库许可随包保存在 `synths/<pack>/licenses/zig-runtime/`。Windows 输出适配器修正 SoundCard 0.4.5 短缓冲写入与提交长度不一致的问题；未修改已安装的 SoundCard 包。

0.44 增加 Sitar、BlowHole、BlowBotl、Recorder、PercFlut、FMVoices，沿用同一 STK 5.0.1 许可；修改的 Sitar 线性延迟、桥接滤波和力度响应随源码提供。实际包包含源码与 Zig 运行库许可；本地候选目录与鼓素材不分发。

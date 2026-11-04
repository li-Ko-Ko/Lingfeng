# 伶风 Lingfeng

**为流行音乐而生 · For Pop Music**

面向 Windows 的轻量音乐创作与简谱制谱软件，用于编写旋律、和弦、伴奏与歌词。

A lightweight Windows app for songwriting and jianpu, with melody, chords, accompaniment and lyrics.

**当前源码 0.57 · Windows x64 · Python 3.13 / PySide6**

**Current source: 0.57 · Windows x64 · Python 3.13 / PySide6**

[下载已发布版本 / Download a published release](https://github.com/li-Ko-Ko/Lingfeng/releases/latest) · [操作帮助 / User guide](docs/HELP.md) · [问题反馈 / Issues](https://github.com/li-Ko-Ko/Lingfeng/issues)

0.57 是当前源码及本地独立程序版本，最近生成的发行归档为 0.55。本次源码更新未生成 0.57 发行 ZIP；下载版本以 Releases 页面为准。使用便携包时完整解压，运行其中的 `Lingfeng.exe`，保留 `_internal/` 和 `synths/`。

The current source and local standalone version is 0.57; the most recently generated release archive is 0.55. This source update does not include a 0.57 release ZIP. Check Releases for available downloads. Extract a portable package completely, then run `Lingfeng.exe` while keeping `_internal/` and `synths/`.

独立程序无需安装 Python，附带免费钢琴、电钢琴及 37 个合成音色，大型钢琴与键盘音源可按需下载。

The standalone application needs no Python installation. Free piano, electric pianos and 37 synth presets are included, with optional piano and keyboard downloads.

## 主要功能 / Features

- 旋律与和弦钢琴卷帘，支持选择、移动、量化、复制、分割合并及撤销；可停靠或独立悬浮 / Melody and chord piano rolls with editing, quantization, copying, split/join and undo, docked or floating.
- 伴奏节奏型与和弦进行库；全局“设置 → 和弦 → 节奏型识别”可暂停全部自动节奏分析并隐藏和弦轨节奏型，保留实际 MIDI 和各和弦的独立开关 / Accompaniment patterns and progression library; Settings → Chords → Rhythm recognition pauses automatic analysis and hides lane patterns while retaining performed MIDI and per-chord settings.
- 小节右键设置段落标识或按已有标识跳转；导航器仅显示段落边界，不显示标识文字 / Assign sections or jump to marked bars from bar menus; navigators show section boundaries without section text.
- 旋律与和弦默认力度、常用力度及快速和弦性质可保存；和弦默认力度统一全部声部，卷帘逐音编辑可保留不同力度 / Saved note/chord defaults, velocity presets and quick chord qualities; chord velocity applies to every voice while individual note edits can retain different dynamics.
- 手动和弦标记同步旋律卷帘高亮及谱面弦内音圈，保留实际 MIDI；复制粘贴保留实际配器、时序与逐音力度 / Manual chord labels guide melody highlights and score chord-tone circles without changing MIDI; copies preserve performed voicing, timing and note velocities.
- 立体／紧凑简谱支持多声部，传统简谱用于单声部；歌词、Rap、连音弧与排版共用屏幕和 PDF 呈现 / Spatial and compact jianpu support polyphony, traditional jianpu uses monophony, with lyrics, rap, slurs and shared screen/PDF engraving.
- MIDI 导入，PDF、MIDI、MP3 导出；工程保存为 `.lfs`，支持中英界面与浅深主题 / MIDI import; PDF, MIDI and MP3 export; `.lfs` projects, Chinese/English UI and light/dark themes.

## 精选截图 / Featured

<table>
  <tr>
    <td width="50%"><strong>旋律与和弦编辑 / Piano rolls</strong><br><a href="docs/screenshots/compose.png"><img src="docs/screenshots/compose.png" alt="旋律与和弦双卷帘、音级配色及伴奏区间" width="640"></a></td>
    <td width="50%"><strong>立体简谱 / Spatial jianpu</strong><br><a href="docs/screenshots/spatial-score.png"><img src="docs/screenshots/spatial-score.png" alt="原创示例的立体简谱、和弦标记与歌词" width="640"></a></td>
  </tr>
  <tr>
    <td width="50%"><strong>歌词与 Rap / Lyrics and rap</strong><br><a href="docs/screenshots/lyrics-rap.png"><img src="docs/screenshots/lyrics-rap.png" alt="传统简谱中的歌词与Rap排版及编辑面板" width="640"></a></td>
    <td width="50%"><strong>和弦进行库 / Chord progressions</strong><br><a href="docs/screenshots/progression-library.png"><img src="docs/screenshots/progression-library.png" alt="内置和弦进行库的罗马数字、实际和弦及根音序列检索" width="640"></a></td>
  </tr>
</table>

## 从源码运行与构建 / Run and build from source

在 Windows x64 安装 Python 3.13 和 Git 后，使用 PowerShell 执行。固定直接依赖版本的 `requirements-build.txt` 同时包含运行与构建所需包。

On Windows x64 with Python 3.13 and Git installed, run these PowerShell commands. `requirements-build.txt` pins the direct runtime and build dependencies.

```powershell
git clone https://github.com/li-Ko-Ko/Lingfeng.git
Set-Location Lingfeng
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe main.py
```

生成本地独立程序：

Build the local standalone application:

```powershell
.\build.ps1 -Python '.\.venv\Scripts\python.exe'
```

当前输出为 `dist/0.57/Lingfeng/Lingfeng.exe`。默认构建只更新独立程序文件夹，不生成发行 ZIP 或校验文件。仓库保留应用源码、构建脚本、验证用例、示例、四组随附音源及其重建输入和许可；无需本机构建目录或个人设置。依赖安装需联网，安装后的随附音源可离线使用。完整环境、验证及音源重建步骤见 [CONTRIBUTING](CONTRIBUTING.md)。

The current output is `dist/0.57/Lingfeng/Lingfeng.exe`. The default build updates the standalone folder without creating a release ZIP or checksum. The repository includes application source, build scripts, regression tests, examples and four bundled sound packs with rebuild inputs and licenses. Local build folders and personal settings are unnecessary. Dependency installation needs network access; installed bundled sounds work offline. See [CONTRIBUTING](CONTRIBUTING.md) for environment, validation and sound rebuild steps.

## 文档 / Documentation

[源码运行与构建 / Build from source](CONTRIBUTING.md) · [工程格式 / Project format](docs/FORMAT.md) · [音源 / Soundbanks](docs/SOUNDBANKS.md) · [发行日志 / Release history](CHANGELOG.md)

个人维护的开源项目，使用 Python 3.13 与 PySide6。原创代码采用 [MIT](LICENSE)；依赖与音源保留[各自许可](docs/THIRD_PARTY.md)。

A personally maintained open-source project built with Python 3.13 and PySide6. Original code is [MIT](LICENSE); dependencies and synth packs retain [their own licenses](docs/THIRD_PARTY.md).

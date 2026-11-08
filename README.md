# 伶风 Lingfeng

**为流行音乐而生 · For Pop Music**

面向 Windows 的轻量流行音乐创作与制谱软件。分别编写人声旋律、乐器旋律和和弦，加入歌词并排成简谱。

A lightweight Windows app for pop songwriting and jianpu engraving. Write separate vocal and instrumental melodies, add chords and lyrics, and prepare a score.

**当前源码 0.60.9 · Windows x64 / Current source 0.60.9**

[已发布的便携版 / Published portable builds](https://github.com/li-Ko-Ko/Lingfeng/releases) · [操作帮助 / User guide](docs/HELP.md) · [问题反馈 / Issues](https://github.com/li-Ko-Ko/Lingfeng/issues)

下载后完整解压，运行 `Lingfeng.exe`，保留同级的 `_internal/` 和 `synths/` 文件夹。

Extract the download completely, then run `Lingfeng.exe`. Keep the `_internal/` and `synths/` folders beside it.

独立程序无需安装 Python。便携版随附 Greg Sullivan 电钢琴、三组 STK 音源、GeneralUser GS 主包和 PFSynth 物理建模钢琴。GeneralUser GS 在伶风中提供 128 个基础 GM 音色，初次使用时默认选用原声大钢琴。Salamander 音乐会钢琴和 FluidR3 GM 可按需下载。可以一键提高三轨中较轻的合成音源增益，再逐轨微调和试听。

The standalone application needs no Python installation. Portable builds include Greg Sullivan electric pianos, three STK packs, the main GeneralUser GS pack and the PFSynth physically modeled piano. GeneralUser GS provides 128 standard GM sounds in Lingfeng, with Grand Piano selected in fresh settings. Salamander Concert Grand and FluidR3 GM are optional downloads. Auto-calibration boosts quieter synth tracks, and each track's gain can be edited and previewed.

## 主要功能 / Features

- **创作 / Compose.** 人声、乐器和和弦分轨编辑，支持独立悬浮卷帘、量化、复制粘贴、剪切和撤销。剪切和弦在原处留下保有原区间与节奏设置的 N.C. / Edit separate vocal, instrumental and chord tracks in floating piano rolls with quantization, copy, paste, cut and undo. Cutting a chord leaves an N.C. region with the original span and rhythm settings.
- **导航 / Navigate.** 按段落跳转、选择音符并定位到对应卷帘。导航器可按轨显示、自动隐藏空轨和调整高度。 / Jump to marked sections and reveal selected notes in the corresponding roll. Choose which tracks appear in the resizable navigator, which automatically hides empty tracks.
- **制谱 / Engrave.** 立体与紧凑简谱支持多声部。传统简谱只检查已勾选的旋律是否为单声部。支持两轨歌词、说唱、连音弧与 PDF 导出。 / Spatial and compact jianpu support polyphony. Traditional jianpu checks only the selected melody tracks for monophony. Engrave lyrics on both tracks, rap and slurs, and export to PDF.
- **乐谱交换 / Exchange scores.** 按小节导入 MIDI、ABC 和 MusicXML，选择轨道导出 ABC、MusicXML/MXL、MIDI 或 DAW 迁移包。 / Import MIDI, ABC and MusicXML at a selected bar. Choose tracks to export as ABC, MusicXML/MXL, MIDI or a DAW transfer bundle.
- **伴奏与音频 / Accompaniment and audio.** 使用和弦进行库和伴奏节奏型，单独调整三轨的音色、音量与合成增益，并离线渲染 MP3。 / Use the chord progression library and accompaniment patterns, control each track’s sound, volume and synth gain, and render MP3 offline.
- **本地工程 / Local projects.** 用 `.lfs` 保存创作和制谱内容，可切换中英文与浅深主题。 / Save composition and engraving in `.lfs` projects, with a Chinese or English interface and light or dark themes.

## ABC 与 YuE2 / ABC and YuE2

在「文件 → 导出 → ABC」可选择完整 ABC 或 YuE2 兼容版。完整版可保留实际和弦音符与首段唱词。兼容版写入同步的 `Vocal`、`Ins` 声部、段落和和弦符号。导出前可以检查调式、复音与节奏格点，并预览和弦替换。

Choose Full ABC or YuE2-compatible ABC under File → Export → ABC. Full ABC can include performed chord notes and the first sung verse. The compatible format writes synchronized `Vocal` and `Ins` parts with section markers and chord symbols. Check key modes, polyphony and timing, and review chord substitutions before exporting.

在单独配置的 ComfyUI 中，把导出的 ABC 接到 **YuE2 Generate Song** 的 `score_abc` 输入，填写歌词和风格，并在 **YuE2 Options** 中将 `cot` 设为 `full`。已用原创片段验证从伶风导出、YuE2 解析到音频生成的交接。[ABC 与 YuE2 操作帮助](docs/HELP.md#topic-8-2)

In a separately configured ComfyUI setup, connect the exported ABC to `score_abc` on **YuE2 Generate Song**, supply the lyrics and style, and set `cot` to `full` in **YuE2 Options**. An original draft was used to verify the handoff from Lingfeng export through YuE2 parsing and audio generation. [ABC and YuE2 user guide](docs/HELP.md#topic-8-2)

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

## 从源码运行 / Run from source

需要 Windows x64 和 Python 3.13。在仓库根目录使用 PowerShell 执行：

Requires Windows x64 and Python 3.13. Run these PowerShell commands from the repository root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe main.py
```

构建、测试及音源重建见 [CONTRIBUTING / Build, test and sound rebuild instructions](CONTRIBUTING.md)。

## 文档 / Documentation

[源码运行与构建 / Build from source](CONTRIBUTING.md) · [工程格式 / Project format](docs/FORMAT.md) · [音源 / Soundbanks](docs/SOUNDBANKS.md) · [发行日志 / Release history](CHANGELOG.md)

个人维护的开源项目，使用 Python 3.13 与 PySide6。原创代码采用 [MIT](LICENSE)；依赖与音源保留[各自许可](docs/THIRD_PARTY.md)。

A personally maintained open-source project built with Python 3.13 and PySide6. Original code is [MIT](LICENSE); dependencies and synth packs retain [their own licenses](docs/THIRD_PARTY.md).

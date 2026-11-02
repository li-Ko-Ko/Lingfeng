# 伶风 Lingfeng

**为流行音乐而生 · For Pop Music**

面向 Windows 的轻量音乐创作与简谱制谱软件，用于编写旋律、和弦、伴奏与歌词。

A lightweight Windows app for songwriting and jianpu, with melody, chords, accompaniment and lyrics.

**当前本地版本 0.55；最近生成的发行包 0.55 · Windows x64 · 便携免安装**

**Current local version: 0.55; most recently generated release archive: 0.55 · Windows x64 · Portable**

[下载已发布版本 / Download a published release](https://github.com/li-Ko-Ko/Lingfeng/releases/latest) · [操作帮助 / User guide](docs/HELP.md) · [问题反馈 / Issues](https://github.com/li-Ko-Ko/Lingfeng/issues)

本地构建后运行 `dist/0.55/Lingfeng/Lingfeng.exe`，保留 `_internal/` 和 `synths/`。默认构建只更新独立程序文件夹；明确要求归档时才生成新的 ZIP 和校验文件，已有归档保持不变。使用下载的历史发行 ZIP 时，先完整解压再运行其中的 `Lingfeng.exe`。

After a local build, run `dist/0.55/Lingfeng/Lingfeng.exe`, keeping `_internal/` and `synths/`. Builds update only the standalone folder by default. A new ZIP and checksum require an explicit archive request; existing archives remain unchanged. Extract a downloaded historical release ZIP completely before running its executable.

独立程序无需安装 Python，附带免费钢琴、电钢琴及 37 个合成音色，大型钢琴与键盘音源可按需下载。

The standalone application needs no Python installation. Free piano, electric pianos and 37 synth presets are included, with optional piano and keyboard downloads.

## 主要功能 / Features

- 旋律与和弦卷帘、伴奏节奏型、和弦进行库 / Piano rolls, accompaniment patterns and chord progressions.
- 和弦右键批量修改力度；可自定义常用值并手动检测采样力度区间 / Batch chord velocities, custom presets and opt-in sample velocity inspection.
- 传统、立体和紧凑简谱，支持歌词与 Rap 排版 / Traditional, spatial and compact jianpu with lyrics and rap.
- MIDI 导入，PDF、MIDI、MP3 导出；工程保存为 `.lfs` / MIDI import; PDF, MIDI and MP3 export; `.lfs` projects.

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

## 文档 / Documentation

[源码运行与构建 / Build from source](CONTRIBUTING.md) · [工程格式 / Project format](docs/FORMAT.md) · [音源 / Soundbanks](docs/SOUNDBANKS.md) · [发行日志 / Release history](CHANGELOG.md)

个人维护的开源项目，使用 Python 3.13 与 PySide6。原创代码采用 [MIT](LICENSE)；依赖与音源保留[各自许可](docs/THIRD_PARTY.md)。

A personally maintained open-source project built with Python 3.13 and PySide6. Original code is [MIT](LICENSE); dependencies and synth packs retain [their own licenses](docs/THIRD_PARTY.md).

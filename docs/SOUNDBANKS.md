# 0.56.2 音符与力度设置 / Notes and velocity settings

和弦轨右键一个或多个和弦 → 修改力度。设置 → 音符与力度将旋律／和弦默认力度与常用值放在同一窗口，可编辑常用值并点击“检测当前和弦音源并生成选项”；检测当前工程和弦轨所选音色，确认后保存，取消丢弃。默认、启动、打开设置和切换音源均不检测。

SFZ 读取 include／宏展开及 global／master／group／region 继承后的 `lovel`／`hivel`，排除 release 区域；SF2 只读取当前 bank／program 的预设及乐器区域表，合并全局／局部设置并相交键位及力度范围，跳过采样音频。按有效区间生成中间值；重复区域、立体声或轮替采样不重复计数。跨键位边界、重叠与交叉层会影响建议，区间数不等于所有音高统一的采样层数，也不是响度测量。原生合成与外部 MIDI 无法报告采样层时保留常用值；单层音色仍响应力度。

Right-click one or several chords → Change velocity. Settings → Notes and velocity combines melody/chord defaults with the common list. It also offers optional inspection of the current project’s chord preset. Only the detection button starts inspection; OK saves and Cancel discards it. SFZ attack mappings and the selected SF2 bank/program supply velocity ranges without decoding samples or executing synth DLLs. Deduplicated bands produce midpoint suggestions, with gaps retained. Key-dependent splits, overlaps, crossfades and controllers may differ from a uniform layer model. Native synths and external MIDI keep the existing list. Single-layer sounds still respond to velocity.

Mapping references: [SFZ velocity selection](https://sfzformat.com/opcodes/lovel/), [SoundFont 2.04 specification](https://www.synthfont.com/sfspec24.pdf).

---

# 音源 / Sound packs

0.53 首次提供 Greg Sullivan 电钢琴合集和 FluidR3 GM 键盘音源的可选下载。Greg 的三个电钢琴音色来自旧版小型钢琴包使用的同一批录音。

Version 0.53 first offered Greg Sullivan electric pianos and the 128-instrument FluidR3 GM bank as optional downloads. Greg's three electric pianos use the same recordings as the legacy small piano pack.

| 可选下载 / Optional download | 下载 / Download | 完整安装 / Installed with runtime sources |
| --- | --- | --- |
| Salamander 音乐会钢琴 / Concert Grand | 约 182 MiB | 约 238 MiB |
| FluidR3 GM 键盘音源 / GM Keyboards | 约 137 MiB | 约 151 MiB |

首次播放或试听显示可取消的后台加载窗口，包含等待时间；播放中添加音符继续使用同一个播放进程和音源。校验缓存追踪映射、样本和父目录的变化；检测变动后重新验证。编辑命令后台发送、相邻的过期谱表修订合并，MIDI 顺序和同步操作边界保留；输出线程定期处理音频，避免持续命令挤占填充时间。

Initial loading uses a responsive, cancellable window. Live edits reuse the worker and loaded instruments. Validated file metadata is cached with change detection; audio buffers are reused. Background command delivery preserves MIDI order and barriers while coalescing superseded adjacent schedule revisions.

默认构建和发行包随附 Greg Sullivan 电钢琴、三组 STK、GeneralUser GS 主包和 PFSynth 物理建模钢琴。保留 `_internal/` 与 `synths/` 即可离线使用随附音源。

Default builds and releases include Greg Sullivan electric pianos, three STK packs, the main GeneralUser GS pack and the PFSynth physically modeled piano. Keep `_internal/` and `synths/` to use the bundled sounds offline.

## 随附音源 / Included sounds

| 包 / Pack | 音色 / Instruments | 解压体积 / Unpacked size |
| --- | --- | --- |
| `generaluser-gs` | GeneralUser GS 2.0.3 的 128 个基础 GM 音色，原声大钢琴为音色编号 01 / 128 standard GM sounds from GeneralUser GS 2.0.3, including Grand Piano at program 0 | 约 40 MiB，含原版 SF2、引擎、源码和许可 / About 40 MiB including the original SF2, runtime, source and notices |
| `pfsynth` | 支持延音、选择延音和弱音踏板的物理建模钢琴 / Physically modeled piano with sustain, sostenuto and soft-pedal support | 约 0.6 MiB，含引擎、源码和许可 / About 0.6 MiB including the engine, source and notices |
| `piano-electric` | Greg Sullivan 的 Wurlitzer EP200、CP80、Pianet T 电钢琴 / Greg Sullivan's Wurlitzer EP200, CP80 and Pianet T | 约 41.8 MiB，含引擎、源码和许可 / About 41.8 MiB including runtime source and notices |
| `stk-essentials` | 16 个 FM 键盘、拨弦、贝斯与弓弦预设 / 16 FM keyboard, plucked, bass and bowed presets | 轻量原生合成 / Lightweight native synthesis |
| `stk-colors` | 8 个风琴、钟、敲击条与管乐预设 / 8 organ, bell, bar and wind presets | 同上 / As above |
| `stk-acoustic` | 14 个钟琴、元音、竖笛、吹瓶、西塔琴和拨弦模型 / 14 bell, vowel, recorder, bottle, sitar and plucked models | 同上 / As above |

和弦轨可在“设置 → 音源与输入 → 音源与音色”选用“STK · 键盘与弦乐”的“50 · 轻弦和声”。此音色使用多声部原生弓弦合成，无需下载采样。

For the chord track, select “50 · Light chord strings” from STK Essentials under Settings → Sound and input → Sound sources and instruments. The preset uses polyphonic bowed-string synthesis and requires no sample download.

GeneralUser GS 主包保留未经修改的上游 SF2。发行版在音色列表中提供库 0 的 128 个基础 GM 音色。编号 GS 变体库和鼓组可通过单独的音源包添加。

The main GeneralUser GS pack preserves the original upstream SF2. The release lists the 128 standard GM programs from bank 0. Numbered GS variation banks and drum kits are available through separately installed packs.

全新设置下，人声、乐器和和弦轨默认使用 GeneralUser GS 的「01 · 原声大钢琴」。已保存且可用的新工程默认音色优先。旧工程如需使用 MuseScore Lite、YDP、Kawai 或 Rhodes，可从旧版安装复制完整的 `musescore-lite-piano-test`、`ydp-grand` 或 `piano-small` 目录到新程序旁的 `synths/` 后重新扫描，也可导入已有的完整音源 ZIP。

Fresh settings select GeneralUser GS “01 · Grand Piano” for vocal, instrument and chord tracks. Available saved new-project defaults take precedence. To use MuseScore Lite, YDP, Kawai or Rhodes in older projects, copy the complete `musescore-lite-piano-test`, `ydp-grand` or `piano-small` folder into `synths/` and rescan, or import an existing complete pack ZIP.

随包音源和通过「下载／添加音源」安装的音源会为可测量的音色生成 `calibration.json`。程序按固定音高和力度测量，向 YDP 的参考响度靠拢。直接复制旧音源目录后重新扫描会沿用已有的测量结果，无法测量的音色沿用原电平。「自动校准三轨响度」会算入已有的预设补偿和当前增益，以同一轨道音量下最响的可测量音色为参照，只提高较轻轨道的「音源增益」。填入的增益可手动修改，试听使用窗口里的当前数值。

Bundled packs and packs installed through Download / add sounds receive a `calibration.json` for presets that can be measured. A fixed note and velocity probe matches levels to the YDP reference. Rescanning a copied pack uses its existing measurements. Presets that cannot be measured keep their original levels. Auto-calibrate track loudness takes existing preset compensation and track gain into account. It compares measurable sounds at the same track volume and increases the sound source gain of quieter tracks. The resulting gains remain editable, and preview uses the current values in the dialog.

## 下载与本地添加 / Download and local installation

1. 打开 **设置 → 音源与输入 → 音源与音色 → 下载／添加音源…**。
2. 选择需要的音源，点击 **下载并添加**。Salamander 为 16 层力度的 Yamaha C5，FluidR3 提供 128 种 GM 乐器。大小和许可在窗口中显示。
3. 下载在后台显示进度，可取消；固定版本、大小和 SHA-256 校验通过后才安装。取消或失败清理本次临时文件，不改动已经安装的音源。成功后自动扫描，可为旋律和和弦分别选择音源及音色。
4. 已有完整伶风音源 ZIP 时，选择 **从本地 ZIP 添加…**。也可复制完整文件夹到程序同级 `synths/`，点击 **重新扫描并保存**，或添加其它扫描目录。

Use **Settings → Sound and input → Sound sources and instruments → Download / add sounds…** to choose a sound bank or install a local pack ZIP. Background downloads are explicit, cancellable, pinned and SHA-256 checked. Success refreshes the index; failure preserves existing packs. The GM download verifies all soundfont, runtime and source archives separately before installing.

安装目标为程序同级 `synths/`，程序目录必须可写。同名音源已存在时不覆盖，移动或更新旧包前请关闭程序。自动安装 Salamander 可复用 Greg 电钢琴包或旧版小型钢琴包中的已核验 sfizz 引擎。完整的 Salamander ZIP 自带引擎。通过 ZIP 安装时需要完整的伶风音源包。

The application folder must be writable. Close Lingfeng before moving or replacing installed packs. Automatic Salamander installation reuses the verified sfizz runtime from Greg or the legacy small piano pack. A complete Salamander ZIP includes its own runtime. ZIP installation requires a complete Lingfeng pack.

索引、额外目录与默认音色持久保存，普通启动读取缓存，不联网。覆盖旧目录升级时按新版本刷新一次索引，保留默认选择和额外目录；之后不重复扫描。新增、移动或更新外部音源后显式扫描。工程只保存稳定包 ID 与 GM 程序号。缺失音源不妨碍打开、编辑、保存或 PDF/MIDI 导出；离线音频需要工程指定音源。Windows MIDI 仍可用，系统资源不随包分发。

大钢琴首次加载播放／试听通道时可能需要十几至数十秒；加载后继续使用已建立的通道。Large sampled pianos may take tens of seconds to load initially; established channels are reused afterward.

## 播放与许可 / Playback and licenses

播放、试听、监听和离线 MP3 使用同一所选引擎。离线 SFZ 导出启用 freewheeling，等待采样流读取完成。主输出保留立体声峰值保护。

在「音源与音色」中可为使用合成音源的各轨分别设置 −24 至 +24 dB 的音源增益。这个值随工程保存，在混音和峰值保护之前应用，与轨道音量 CC7 独立。

Sound sources and instruments provides independent −24 to +24 dB gain for each track using a synth pack. The project stores this gain separately from MIDI CC7 and applies it before mixing and peak protection.

Playback, audition, monitoring and MP3 share the selected renderer. Offline SFZ rendering waits for sample reads through freewheeling. The common stereo peak limiter remains active.

- **FreePats KW、Rhodes GM 子集 / subset**：CC0-1.0。Rhodes CC0 只适用于包内 GM 子集，不扩展到完整 jRhodes3c/3d 库。
- **Greg Sullivan 电钢琴、YDP 原声三角钢琴、Salamander 采样 / samples**采用 CC BY 3.0。分发保留署名、许可链接和修改说明。Salamander 的 SFZ 映射采用 CC0。
- **sfizz 1.2.3**：BSD-2-Clause；完整源码归档、依赖通知、来源与哈希在每包 `runtime/`。上游于 2026-06-21 归档，本版固定并验证该版本。
- **STK 5.0.1**：STK 宽松许可；各包保留实际编译源码、修改、Zig 运行库通知和重建命令。STK 包没有乐器录音，FM 使用内嵌数学波形表。
- **PFSynth** 采用 MIT 许可。钢琴音源包包含适配器、模型源码、拟合参数和重建命令。拟合参考与编译运行库的署名见[第三方说明](THIRD_PARTY.md)。
- **GeneralUser GS 2.0.3** 保留 GeneralUser GS License v2.0 和上游采样条款，使用 FluidSynth 2.6.1 播放。
- **MuseScore General Lite、FluidR3 GM** 采用 MIT 许可。音源版权与许可原文随包保存。FluidSynth 2.6.1 通过独立 DLL 播放 SF2 和 SF3，复用伶风音频输出和离线导出。
- **FluidSynth / libsndfile / mpg123 / LAME** 各自保留 LGPL 条款、对应源码、编译信息及补丁。静态编入运行库的 FLAC、Ogg、Vorbis、Opus 等保留各自宽松许可。GeneralUser GS 主包及可选的 MuseScore Lite、YDP、FluidR3 GM 各自在 `runtime/` 保留上述资料，DLL 位于 `bin/`。

实际来源、固定提交、输入哈希和修改见每包 `source.json`，文件校验见 `files.sha256.json`。修改包括电钢琴 88 键边缘扩展、Rhodes 全局包络头修正、大钢琴最低力度从 2 扩展到 1；样本音频不变。MP3 导出保留音源许可说明；作品、歌词及其它素材的权利另行适用。

Credits, revisions, hashes and modifications are recorded in each pack. SFZ curation includes edge ranges, the Rhodes envelope header and the grand's velocity-1 region; audio samples remain unchanged. MP3 exports retain credits. Sound licenses do not replace rights in compositions, lyrics or other material.

[GeneralUser GS](https://www.schristiancollins.com/generaluser.php) · [PFSynth](https://github.com/olaugh/pfsynth) · [MuseScore General Lite](https://people.debian.org/~tg/sf/) · [FreePats YDP Grand](https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html#ydp-grand-piano) · [FreePats KW](https://github.com/freepats/upright-piano-KW) · [Greg Sullivan](https://github.com/sfzinstruments/GregSullivan.E-Pianos) · [CC0 Rhodes GM](https://github.com/sfzinstruments/Discord-SFZ-GM-Bank) · [Compact Accurate Salamander](https://github.com/jlearman/zynthian-salamander-grand) · [sfizz](https://github.com/sfztools/sfizz) · [STK](https://github.com/thestk/stk/tree/5.0.1)

## 重建 / Rebuild

```powershell
python scripts/build_piano_packs.py --pack electric --download
```

以上命令准备随附的 Greg。脚本只在显式指定 `--download` 时联网，并核验固定输入的哈希。缓存为 `output/piano-sources/`，输出为 `synths/`。缓存齐全后可离线重建。可用 `--pack all` 重建旧版小型钢琴与 Salamander，用 `--pack gm` 重建 FluidR3，或用 `--pack musescore-lite` 和 `--pack ydp` 准备旧版工程所用的音源目录。其他音源需要单独的可安装 ZIP 时可加 `--zip`。

The command above prepares the bundled Greg pack. The builder checks pinned input hashes and accesses the network only with `--download`. Rebuild offline once the cache is complete. Use `--pack all` for the legacy small piano and Salamander, `--pack gm` for FluidR3, or `--pack musescore-lite` and `--pack ydp` for packs used in older projects. For other packs, add `--zip` to create a separately installable ZIP.

仓库提供完整的 GeneralUser GS 主包、STK 和 PFSynth 音源目录。STK 可用 `scripts/build_synth_packs.py --stk <STK-5.0.1> --zig <Zig-0.14.1>` 重建，STK 和 PFSynth 均附有 `source/BUILD.txt`。程序源码在发行包 `source/`。

The repository supplies complete GeneralUser GS main, STK and PFSynth pack folders. Rebuild STK with `scripts/build_synth_packs.py --stk <STK-5.0.1> --zig <Zig-0.14.1>`. STK and PFSynth both include `source/BUILD.txt`. The release includes the application source under `source/`.

## 音源接口 / Pack interface

清单保留 `schema: 1`、`abi: 1`、`platform: windows-x64`、稳定 ID、双语名称、版本、来源、作者、许可、DLL 与 SHA-256。`engine` 缺省为 `native`，原接口不变：

```c
int lf_abi(void);
const char *lf_error(void);
void *lf_create(int rate, int model, int voices);
void lf_free(void *engine);
int lf_control(void *engine, int control, double value);
int lf_event(void *engine, int status, int a, int b);
int lf_render(void *engine, float *stereo, int frames);
int lf_tone(void *engine, double cutoff); /* optional */
```

`engine: "sfz"` 使用 sfizz C API，预设另外指定包内相对 `sfz` 路径，`voices` 可设 32–1024。预设保留 `program`、`model`、双语名称、线性 `gain` 与可选 MIDI `controls`；滤波写在 SFZ，不使用原生 `cutoff_hz`。扫描检查清单、DLL 和样本引用，不执行 DLL；播放加载时再次核对 DLL 哈希。只安装可信来源的原生音源包。

SFZ packs declare `engine: "sfz"`, use sfizz's C API, and add a relative SFZ mapping to each preset. Scans validate manifests and referenced files without executing native code; DLL hashes are checked again on load. Native packs keep the ABI above.

SF2 包声明 `engine: "sf2"`，各预设使用相对 `sf2` 路径、`model`（GM 程序号）和可选 `bank`。`library_hashes` 列出引擎及依赖 DLL 的 SHA-256；只加载包内经核验的 DLL，声音文件检查 SF2 头和路径。完整包 ZIP 安装保持原流程。

SF2 packs use FluidSynth and provide relative soundfont paths, program/bank IDs and checksums for every runtime DLL. Native/SFZ/SF2 all expose the same host send/render/close contract.

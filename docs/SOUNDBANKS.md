# 0.56.2 音符与力度设置 / Notes and velocity settings

和弦轨右键一个或多个和弦 → 修改力度。设置 → 音符与力度将旋律／和弦默认力度与常用值放在同一窗口，可编辑常用值并点击“检测当前和弦音源并生成选项”；检测当前工程和弦轨所选音色，确认后保存，取消丢弃。默认、启动、打开设置和切换音源均不检测。

SFZ 读取 include／宏展开及 global／master／group／region 继承后的 `lovel`／`hivel`，排除 release 区域；SF2 只读取当前 bank／program 的预设及乐器区域表，合并全局／局部设置并相交键位及力度范围，跳过采样音频。按有效区间生成中间值；重复区域、立体声或轮替采样不重复计数。跨键位边界、重叠与交叉层会影响建议，区间数不等于所有音高统一的采样层数，也不是响度测量。原生合成与外部 MIDI 无法报告采样层时保留常用值；单层音色仍响应力度。

Right-click one or several chords → Change velocity. Settings → Notes and velocity combines melody/chord defaults with the common list. It also offers optional inspection of the current project’s chord preset. Only the detection button starts inspection; OK saves and Cancel discards it. SFZ attack mappings and the selected SF2 bank/program supply velocity ranges without decoding samples or executing synth DLLs. Deduplicated bands produce midpoint suggestions, with gaps retained. Key-dependent splits, overlaps, crossfades and controllers may differ from a uniform layer model. Native synths and external MIDI keep the existing list. Single-layer sounds still respond to velocity.

Mapping references: [SFZ velocity selection](https://sfzformat.com/opcodes/lovel/), [SoundFont 2.04 specification](https://www.synthfont.com/sfspec24.pdf).

---

# 0.53 音源 / Sound packs

0.53 新增两个可选下载：**Greg Sullivan 电钢琴合集**（Wurlitzer、CP80、Pianet T，与小型包同一批录音的独立合集）和 **FluidR3 GM 键盘音源**（128 种钢琴、电钢琴、弦乐、吉他等 GM 乐器）。二者均免费，不放入主程序 ZIP。现有小型音源和 Salamander 大钢琴继续兼容。

Version 0.53 adds optional Greg Sullivan electric pianos and the 128-instrument FluidR3 GM keyboard bank. Both are free and stay outside the main ZIP. The Greg collection is a standalone version of the recordings already included in the small pack, not a higher-resolution recording upgrade.

| 可选下载 / Optional download | 下载 / Download | 完整安装 / Installed with runtime sources |
| --- | --- | --- |
| Salamander 音乐会钢琴 / Concert Grand | 约 182 MiB | 约 238 MiB |
| Greg Sullivan 电钢琴合集 / E-Pianos | 约 18.4 MiB | 约 41.8 MiB |
| FluidR3 GM 键盘音源 / GM Keyboards | 约 137 MiB | 约 151 MiB |

首次播放或试听显示可取消的后台加载窗口，包含等待时间；播放中添加音符继续使用同一个播放进程和音源。校验缓存追踪映射、样本和父目录的变化；检测变动后重新验证。编辑命令后台发送、相邻的过期谱表修订合并，MIDI 顺序和同步操作边界保留；输出线程定期处理音频，避免持续命令挤占填充时间。

Initial loading uses a responsive, cancellable window. Live edits reuse the worker and loaded instruments. Validated file metadata is cached with change detection; audio buffers are reused. Background command delivery preserves MIDI order and barriers while coalescing superseded adjacent schedule revisions.

伶风附带免费的小型钢琴／电钢琴包，以及原有三组 STK 合成包。大钢琴独立下载，不增加主程序 ZIP 的体积。完整解压程序包，保留 `_internal/` 与 `synths/` 即可离线使用附带音源。

Lingfeng includes a free small piano/electric-piano pack and three STK synth packs. The optional grand is downloaded separately. Extract the whole ZIP and retain `_internal/` and `synths/`; installed sounds work offline.

## 随附音源 / Included sounds

| 包 / Pack | 音色 / Instruments | 解压体积 / Unpacked size |
| --- | --- | --- |
| `piano-small` | Kawai 原声与明亮钢琴、Rhodes、Wurlitzer、CP80、Pianet T / Acoustic and bright piano, Rhodes, Wurlitzer, CP80, Pianet T | 约 79 MiB，含引擎、源码和许可 / About 79 MiB including runtime source and notices |
| `stk-essentials` | 15 个 FM 键盘、拨弦、贝斯与弓弦预设 / 15 FM keyboard, plucked, bass and bowed presets | 轻量原生合成 / Lightweight native synthesis |
| `stk-colors` | 8 个风琴、钟、敲击条与管乐预设 / 8 organ, bell, bar and wind presets | 同上 / As above |
| `stk-acoustic` | 14 个钟琴、元音、竖笛、吹瓶、西塔琴和拨弦模型 / 14 bell, vowel, recorder, bottle, sitar and plucked models | 同上 / As above |

小型包的 FreePats Kawai 立式钢琴为双力度层；Rhodes 为独立发布的单力度层 CC0 GM 子集。Wurlitzer、CP80 与 Pianet 由 Greg Sullivan 录音、kinwie 映射。这些采样在体积与实际钢琴音色之间折中，不承诺达到深度采样商业乐器的真实度。新用户默认旋律为明亮原声钢琴、和弦为原声钢琴；已保存默认值和已有工程音色继续保留。

The small pack balances size and piano character: a two-layer Kawai upright, a single-layer CC0 Rhodes GM subset, and Greg Sullivan electric pianos mapped by kinwie. Fresh settings prefer bright acoustic for melody and acoustic for chords. Saved defaults and existing projects retain their selected sounds.

## 下载与本地添加 / Download and local installation

1. 打开 **设置 → 音源与输入 → 音源与音色 → 下载／添加音源…**。
2. 选择需要的音源，点击 **下载并添加**。Salamander 为 16 层力度的 Yamaha C5；Greg 合集为三种电钢琴；FluidR3 提供 128 种 GM 乐器。大小和许可在窗口中显示。
3. 下载在后台显示进度，可取消；固定版本、大小和 SHA-256 校验通过后才安装。取消或失败清理本次临时文件，不改动已经安装的音源。成功后自动扫描，可为旋律和和弦分别选择音源及音色。
4. 已有完整伶风音源 ZIP 时，选择 **从本地 ZIP 添加…**。也可复制完整文件夹到程序同级 `synths/`，点击 **重新扫描并保存**，或添加其它扫描目录。

Use **Settings → Sound and input → Sound sources and instruments → Download / add sounds…** to choose a sound bank or install a local pack ZIP. Background downloads are explicit, cancellable, pinned and SHA-256 checked. Success refreshes the index; failure preserves existing packs. The GM download verifies all soundfont, runtime and source archives separately before installing.

安装目标为程序同级 `synths/`，程序目录必须可写。同名音源已存在时不覆盖；关闭程序后再移动或更新旧包。自动下载大钢琴需要本版本小型包中的已核验引擎；手工安装完整大钢琴 ZIP 则自带引擎。普通 VST/CLAP 插件、裸 SFZ 或 SF2 不是完整伶风音源 ZIP。

The application folder must be writable. Existing pack folders are never overwritten; close Lingfeng before moving or replacing them. Automatic grand installation reuses the small pack's verified runtime. A complete offline grand ZIP includes its own runtime. Plain plugins, SFZ and SF2 files are not complete pack ZIPs.

索引、额外目录与默认音色持久保存，普通启动读取缓存，不联网。覆盖旧目录升级时按新版本刷新一次索引，保留默认选择和额外目录；之后不重复扫描。新增、移动或更新外部音源后显式扫描。工程只保存稳定包 ID 与 GM 程序号。缺失音源不妨碍打开、编辑、保存或 PDF/MIDI 导出；离线音频需要工程指定音源。Windows MIDI 仍可用，系统资源不随包分发。

大钢琴首次加载播放／试听通道时可能需要十几至数十秒；加载后继续使用已建立的通道。Large sampled pianos may take tens of seconds to load initially; established channels are reused afterward.

## 播放与许可 / Playback and licenses

播放、试听、监听和离线 MP3 使用同一所选引擎。小型包 128 复音，大钢琴 256 复音。离线 SFZ 导出启用 freewheeling，等待采样流读取完成；主输出保留立体声峰值保护。

Playback, audition, monitoring and MP3 share the selected renderer. Small/grand packs use 128/256 voices. Offline SFZ rendering waits for sample reads through freewheeling. The common stereo peak limiter remains active.

- **FreePats KW、Rhodes GM 子集 / subset**：CC0-1.0。Rhodes CC0 只适用于包内 GM 子集，不扩展到完整 jRhodes3c/3d 库。
- **Greg Sullivan 电钢琴、Salamander 采样 / samples**：CC-BY-3.0；分发保留署名、许可链接和修改说明。大钢琴映射为 CC0；原作者、重制和转换署名随包保存。
- **sfizz 1.2.3**：BSD-2-Clause；完整源码归档、依赖通知、来源与哈希在每包 `runtime/`。上游于 2026-06-21 归档，本版固定并验证该版本。
- **STK 5.0.1**：STK 宽松许可；各包保留实际编译源码、修改、Zig 运行库通知和重建命令。STK 包没有乐器录音，FM 使用内嵌数学波形表。
- **FluidR3 GM**：MIT；音源版权与许可原文随包保存。FluidSynth 2.6.1 通过独立 DLL 播放 SF2，不创建自己的音频／MIDI 设备，复用伶风输出和离线导出。
- **FluidSynth / libsndfile / mpg123 / LAME**：保留各自 LGPL 条款、对应源码、编译信息及补丁；静态编入运行库的 FLAC、Ogg、Vorbis、Opus 等保留各自宽松许可。全部位于可选 GM 包的 `runtime/`，DLL 位于 `bin/`；不统一改标 MIT，不随主程序包分发。

实际来源、固定提交、输入哈希和修改见每包 `source.json`，文件校验见 `files.sha256.json`。修改包括电钢琴 88 键边缘扩展、Rhodes 全局包络头修正、大钢琴最低力度从 2 扩展到 1；样本音频不变。MP3 导出保留音源许可说明；作品、歌词及其它素材的权利另行适用。

Credits, revisions, hashes and modifications are recorded in each pack. SFZ curation includes edge ranges, the Rhodes envelope header and the grand's velocity-1 region; audio samples remain unchanged. MP3 exports retain credits. Sound licenses do not replace rights in compositions, lyrics or other material.

来源 / Sources: [FreePats KW](https://github.com/freepats/upright-piano-KW), [Greg Sullivan](https://github.com/sfzinstruments/GregSullivan.E-Pianos), [CC0 Rhodes GM](https://github.com/sfzinstruments/Discord-SFZ-GM-Bank), [compact Accurate Salamander](https://github.com/jlearman/zynthian-salamander-grand), [sfizz](https://github.com/sfztools/sfizz), [STK](https://github.com/thestk/stk/tree/5.0.1).

## 重建 / Rebuild

```powershell
python scripts/build_piano_packs.py --download --pack all --zip
python scripts/build_piano_packs.py --download --pack upgrades --zip
```

脚本使用 Python 标准库，只在显式 `--download` 时联网，每个固定输入通过哈希后才使用。缓存为 `output/piano-sources/`，输出为 `synths/`；`--zip` 生成完整可安装 ZIP。之后不带 `--download` 可离线重建。主程序发行白名单只有小型钢琴与三组 STK；大钢琴始终独立。

The standard-library builder only accesses the network with `--download`; all fixed inputs are hash-verified. Omit that switch to rebuild offline from cache. `--pack upgrades` builds the optional electric/GM packs; `--zip` produces installable archives. All large/optional packs remain separate from the application release.

STK 重建仍使用 `scripts/build_synth_packs.py --stk <STK-5.0.1> --zig <Zig-0.14.1>`，或包内 `source/BUILD.txt`。程序源码在发行包 `source/`。

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

# 0.44 合成音源包 / Synthesis packs

本版程序包附带全部 3 个轻量 STK 音源包、37 个预设；完整解压即可使用。打包器比较解压后文件总大小（均含源码、许可）：音源总大小不超过程序本体时合并，否则音源独立打包。旧 SFZ/sfizz 采样系统不再加载或分发。

## 安装与更新

1. 解压程序本体，保留 `_internal/`，运行 `Lingfeng.exe`。
2. 本版附带 `stk-essentials`（15 个键盘、拨弦、贝斯、弓弦）、`stk-colors`（8 个风琴、钟、敲击条与管乐）和 `stk-acoustic`（14 个扩展乐器预设）。首次启动自动建立索引。
3. 以后扩展时，把解压出的整个音源文件夹复制到 `Lingfeng.exe` 同级的 `synths/`，例如 `synths/stk-essentials/synth.json`。
4. 打开 设置 → 音源与音色 → 重新扫描并保存，为旋律和和弦分别选择音源及音色。也可添加外部目录；每个扫描目录查找自身和下一层的 `synth.json`。
5. 扫描结果与默认选择缓存在用户目录，下次启动直接读取，不遍历音源内容。新增、移动、替换音源后需要重新扫描。关闭程序后替换已加载的 DLL，再启动扫描。

没有音源包也能编辑、保存、导出 PDF/MIDI，或用已安装的 Windows MIDI 播放。离线 MP3 必须安装并选择合成包；Windows 音源可使用实时录制。缺失音源不会妨碍打开工程，也不会静默替换工程保存的音色。

工程仅保存 `synth:包ID` 和 GM 程序编号，不保存本机路径。旧 `samples`/`builtin` 自动迁移到 `synth:stk-essentials`，编号保留。新工程初始旋律为 02 明亮 FM 键盘；确认音源设置后，新工程使用上次选择。已保存工程保留自身设置。

## 引擎、预设与许可

采用 [STK 5.0.1](https://github.com/thestk/stk/tree/5.0.1) 原生 C++ 乐器算法：Rhodey/Wurley FM 电键盘、BeeThree 风琴、TubeBell、Plucked/StifKarp 拨弦、Bowed 弓弦、Brass、Clarinet、Flute、Saxofony 和 BandedWG；新增 Sitar、BlowHole、BlowBotl、Recorder、PercFlut 与 FMVoices。

这些是合成风格预设，不承诺模拟真实录音。GM 编号用于保留 MIDI 导出及 DAW 对应关系，不表示与系统 GM 音色完全相同。没有乐器录音库；FM 振荡器使用 STK 原有两个单周期数学波形表，编译进 DLL，无音频文件加载。

STK 使用自己的宽松许可，允许使用、修改和再分发，需保留原版权与许可文本。每包附带 `LICENSE-STK.txt`、MIT 桥接代码许可、实际编译源码和重建命令。修改包括：内嵌数学振荡器表、独立伪随机状态、预分配复音池、MIDI 事件与释放包络；Sitar 使用稳定的线性延迟插值，铜管最小激励与输出力度分开；各预设去直流并衰减多余高频，主输出保留峰值保护。合成器软件许可不替代作品、歌词及其他素材版权；MP3 窗口显示商用提示，并保存 `.mp3.licenses.txt`。

重建音源时，向 `scripts/build_synth_packs.py` 显式传入官方 STK 5.0.1 源码根目录 `--stk` 和完整 Zig 0.14.1 工具链中的可执行文件 `--zig`。也可按各音源包 `source/BUILD.txt`，直接编译随包提供的对应源码。

## 音源包接口 v1

兼容包由 `synth.json`、独立 Windows x64 DLL、许可文件组成；普通 VST/CLAP/SFZ 不能直接复制使用。扫描阶段不执行 DLL，只校验清单、路径和 SHA-256；开始播放时检查 ABI。只安装可信来源的原生音源包。

清单要求 `schema: 1`、`abi: 1`、`platform: windows-x64`、稳定 `id`、中英名称、版本、`library`、`sha256`、作者、来源、许可与 `presets`。每个预设具有 0–127 唯一 GM `program`、中英名称、整数 `model`、线性 `gain`、可选 `controls`，以及可选 `cutoff_hz`（200–16000 Hz）。示例见基础包 `synth.json`。路径不得指向包外。重复包 ID 按扫描顺序保留第一个，并显示冲突。

C ABI（cdecl，导出名不修饰）：

```c
int lf_abi(void);                          // 必须为 1
const char *lf_error(void);                // 线程局部 UTF-8 错误
void *lf_create(int rate,int model,int voices); // rate=44100, voices=32
void lf_free(void *engine);
int lf_control(void *engine,int control,double value); // 预设参数
int lf_event(void *engine,int status,int a,int b);      // MIDI
int lf_render(void *engine,float *stereo,int frames);  // 交错双声道
int lf_tone(void *engine,double cutoff); // 可选扩展；有 cutoff_hz 的预设必须支持
```

每个 MIDI 通道具有独立实例，宿主串行访问同一实例；不同实例可能在实时与导出线程并发调用。返回码 0 成功。`lf_create` 失败返回空指针。输出有限的线性浮点数，不含主音量归一化。支持 note on/off、力度、CC7/11/10、延音、弯音、CC120/123；不需要完整 MIDI 文件播放器。主程序用同一音源渲染编辑、键盘监听、试听和离线 MP3。

## Build and install (English)

The three lightweight packs (37 presets) are bundled with the application. If the total unpacked synth payload exceeds the core application size, packaging produces separate synth ZIPs instead. Copy each complete pack folder into `synths/` beside Lingfeng.exe, then open Settings → Sound sources and instruments → Rescan and save. The validated JSON index and defaults persist under `%LOCALAPPDATA%/Lingfeng/synth-index/`, keyed per application location. Startup reads that index. Rescan after adding/moving/updating packs; restart after replacing a loaded DLL. The project stores stable IDs rather than paths.

The native packs use STK 5.0.1 algorithmic instruments, not recorded instrument libraries. FM oscillators embed two synthetic, single-cycle tables. Source, modifications, notices and a Zig 0.14.1 rebuild command accompany each pack. Run `scripts/build_synth_packs.py` with explicit `--stk` and `--zig` paths to rebuild from official sources, or follow the included `source/BUILD.txt`. Standard VST/CLAP plugins are not accepted by the ABI above.

原生包静态编译所用 Zig 0.14.1 / libc++ / libc++abi / libunwind / MinGW 运行库许可随包保存在 `synths/<pack>/licenses/zig-runtime/`。Windows 输出适配器修正 SoundCard 0.4.5 短缓冲写入与提交长度不一致的问题；未修改已安装的 SoundCard 包。

## 0.44 校准与验证

音色滤波在原生线程中按音符执行，截止频率随高音上移，避免低通截掉高音基频。持续音、延音、弯音与重触发继续支持；每通道预分配 32 复音。设置试听先释放主播放的 Windows MIDI 占用；默认 MIDI 映射器与其实际设备名称通过 WinMM 查询结果去重。关闭后清空句柄，下次播放按工程设置重新打开。

`scripts/verify_audio.py --loopback` 检查全部合成预设的 88 键、锚点力度、8 秒长音、延音/止音、复音性能，以及本机 Windows GM 128 音色和全部音源组合的实际输出。结果写入 `output/audio-verification/report.json`；每包有简短 WAV 试听。自动检查衡量无声、数值稳定、峰值和尾音，不代替主观音色评价。

The new models use the same STK permissive license. Sitar uses bounded linear delay interpolation; brass separates minimum physical excitation from MIDI loudness. Preset-specific tone filters, DC removal, smoothed note transitions and a stereo limiter protect the output. Run the verification script for offline checks and optional actual output loopback. Synthetic tone is intentional; no recorded sample bank is included.

Windows MIDI 音色按 GM1 编号显示完整中英名称。设备打开/映射依据 [Microsoft WinMM 文档](https://learn.microsoft.com/en-us/windows/win32/api/mmeapi/nf-mmeapi-midioutmessage)；GM 编号对照厂商公开 [miniEngine Pro 手册附录](https://www.midiplus.com.tw/en/MIDIPLUS-Download-detail/0/Manual_Of_miniEnginePro_EN/)。Windows 原有音色资源未随包分发。


## Windows MIDI 持续音清理 / Sustain-state recovery

0.50.2 打开 Windows MIDI 输出后，仅初始化本程序占用的 0–5 通道：重置控制器（CC121）、释放持续踏板（CC64）、立即停止声音（CC120）、清除音符（CC123），并将弯音归中，然后应用工程选择的 program 和音量。这样可清理设备遗留的踏板/弯音状态，不替换已保存音色或改变乐谱音高。

播放停止仅清理两条播放通道（0、1）；完整停止再清理试听与监听通道（2–5）。保留试听的停止路径不应切断其它通道。Windows 默认映射器与其实际设备名称仍复用同一输出。

These controls reset only the six channels owned by Lingfeng. Opening Windows MIDI resets controllers, releases sustain, sends All Sound Off and All Notes Off, and centers pitch bend before applying the selected programs and volumes. Stopping playback clears channels 0 and 1; a full stop also clears audition and monitoring channels 2–5. A stop that preserves auditions leaves those other channels sounding.

Windows MIDI 音色及其高频组成由系统或设备提供。本轮修复针对持续音状态残留，不对全部 GM 音色做滤波，不替换 Windows 音源，也不改变 MIDI/PDF 导出内容。实际输出和停音检查不等于已消除所有设备上的主观高频不适。

Windows MIDI timbre and its high-frequency content come from the system or device. This repair addresses retained sustain state; it does not filter all GM instruments, replace Windows MIDI, or change MIDI/PDF exports. Output and note-release checks do not establish that every device is free of subjective high-frequency discomfort.

# 参与贡献 / Contributing

伶风是个人维护的 Windows 桌面项目。欢迎报告可复现的问题，并提交针对明确问题的小范围修改。当前支持环境为 Windows x64、Python 3.13；应用版本由 `popscore/__init__.py` 定义。

Lingfeng is a personally maintained Windows desktop project. Reproducible bug reports and focused fixes are welcome. The supported environment is Windows x64 with Python 3.13; `popscore/__init__.py` defines the application version.

## 1. 开发环境 / Development environment

在仓库根目录执行以下 PowerShell 命令。使用独立虚拟环境，无需修改全局 Python：

Run these PowerShell commands from the repository root using a dedicated virtual environment:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

当前发行包含三组 STK 原生合成包、37 个预设。预编译包需要保留其完整文件夹；重建音源需要 STK 5.0.1、Zig 0.14.1 和 `scripts/build_synth_packs.py` 的显式 `--stk`、`--zig` 路径。接口与构建说明见 [SOUNDBANKS](docs/SOUNDBANKS.md)。Windows MIDI 使用本机已安装的输出设备，系统音色资源不在仓库中分发。

The release contains three STK native packs with 37 presets. Keep each prebuilt pack folder complete. Rebuilding uses STK 5.0.1, Zig 0.14.1 and explicit `--stk`/`--zig` paths for `scripts/build_synth_packs.py`; see [SOUNDBANKS](docs/SOUNDBANKS.md). Windows MIDI uses locally installed devices; system instrument resources are not redistributed.

## 2. 报告问题 / Report a problem

请提供以下信息：

Please include:

- 程序版本、Windows 版本，以及使用便携包还是源码 / Application and Windows versions, and portable or source execution.
- 最短复现步骤、预期结果与实际结果 / Minimal reproduction steps, expected behavior and actual behavior.
- 涉及的创作/制谱模式、卷帘、停靠或悬浮状态 / Workspace, roll and docking/floating state involved.
- 音频问题涉及的输出设备、音色、音高和播放/停止时机 / For audio issues: device, instrument, pitches and whether the problem happens during playback or after stopping.
- 可公开的最小工程或示意截图；必要时提供已去除个人路径的错误文本 / A shareable minimal project or screenshot, with personal paths removed from error text when needed.

请新建几个音符重现问题，或删除与问题无关的音乐。不要上传私人作品、未经许可的歌曲歌词/曲谱、他人的录音、账号信息、密钥或完整用户偏好目录。截图也请检查用户名、文件路径和未公开作品信息。

Prefer a new project with a few notes, or remove music unrelated to the problem. Do not upload private works, unlicensed lyrics/scores, other people's recordings, account details, secrets or a complete preferences folder. Check screenshots for usernames, paths and unpublished work as well.

## 3. 修改与验证 / Changes and validation

保持每次修改围绕一个问题。音乐时间与演奏数据归模型所有，谱面排版不应改写 MIDI；普通编辑通过现有事务/撤销路径提交。界面文案需同时维护中文与英文，不使用显示标签作为稳定数据值。

Keep changes focused on one problem. The model owns musical time and performed events; engraving must not rewrite MIDI. Use the existing edit transaction/undo paths. Maintain Chinese and English UI text together, and keep stable data values independent of display labels.

```powershell
.\.venv\Scripts\python.exe scripts/run_regression.py
.\.venv\Scripts\python.exe scripts/audit_text.py
```

统一回归为每个 `tests/test_*.py` 模块创建独立进程，默认使用无屏幕 Qt 平台，并将 `LINGFENG_USER_DATA`、`LINGFENG_SYNTH_CACHE`、临时目录隔离到仓库 `tmp/`。结果写入 `output/`。完整套件包含 Windows 设备、原生合成与音频检查；无声、数值稳定或停音测试不能替代所有设备上的主观听感验收。修改后先运行相关模块，再进行发行需要的完整回归。

The runner starts each `tests/test_*.py` module in a separate process with offscreen Qt. It isolates `LINGFENG_USER_DATA`, `LINGFENG_SYNTH_CACHE` and temporary files under `tmp/`, writing results to `output/`. The full suite includes Windows device, native synthesis and audio checks. Silence, numerical stability and stop tests do not replace subjective listening on every device. Run relevant modules during development and the full suite for a release.

单独运行会建立窗口或使用偏好的测试时，也请设置隔离路径；不要让测试覆盖日常设置或和弦进行库：

When running tests individually, isolate their data as well so they cannot overwrite normal settings or progression presets:

```powershell
$env:QT_QPA_PLATFORM = 'offscreen'
$env:LINGFENG_USER_DATA = Join-Path $PWD 'tmp\manual-test-user'
$env:LINGFENG_SYNTH_CACHE = Join-Path $PWD 'tmp\manual-test-index\current.json'
.\.venv\Scripts\python.exe -m unittest tests.test_music tests.test_harmony -v
```

编辑帮助后运行 `python scripts/export_help.py`，从同一主题重新生成 [HELP](docs/HELP.md)；使用与项目相同的虚拟环境执行该命令。提交说明应包含具体问题、修改后的行为、实际运行的检查和仍未验证的范围。不要仅为匹配实现而放宽测试断言。

After editing help, run `python scripts/export_help.py` with the project environment to regenerate [HELP](docs/HELP.md) from the same topics. Describe the concrete problem, resulting behavior, checks actually run and any unverified scope in the change description. Do not relax assertions solely to match an implementation.

## 4. 打包 / Packaging

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\build.ps1 -Python '.\.venv\Scripts\python.exe'
```

构建产物位于 `dist/`。运行独立 EXE 的 `--self-test <输出目录>`，再执行 `python scripts/verify_release.py` 检查 ZIP、校验和、源码与音源一致性。发行包保留第三方许可和对应源码说明。不要把本机构建环境、录音、调试日志或私人工程作为程序源码提交。

Build outputs go to `dist/`. Run the executable with `--self-test <output-directory>`, then use `python scripts/verify_release.py` to check the archive, checksum, source and synth consistency. Preserve third-party notices and corresponding-source information in releases. Do not commit local environments, recordings, debug logs or private projects as source.

## 5. 许可 / Licensing

原创应用代码采用 [MIT](LICENSE)。提交代码时需有权按该许可公开；引入第三方代码、字体、图像、音源或示例前，保留其原许可与来源并说明兼容条件。不能因为项目使用 MIT 就把第三方依赖重新标为 MIT。

Original application code is [MIT](LICENSE). Contributions must be shareable under that license. Retain source and license information for new third-party code, fonts, images, instruments or examples, and explain their compatibility. The application's MIT license does not relicense its dependencies.

STK 合成包沿用 STK 许可，Qt/PySide6、编码器等各自保留条款。详见 [THIRD_PARTY](docs/THIRD_PARTY.md)、[LICENSE_AUDIT](docs/LICENSE_AUDIT.md) 和 [SOUNDBANKS](docs/SOUNDBANKS.md)。软件与音源许可不替代作品、歌词及录音素材的授权。

STK packs retain their STK terms; Qt/PySide6, the encoder and other dependencies retain theirs. See [THIRD_PARTY](docs/THIRD_PARTY.md), [LICENSE_AUDIT](docs/LICENSE_AUDIT.md) and [SOUNDBANKS](docs/SOUNDBANKS.md). Software/instrument licenses do not clear compositions, lyrics or recordings.

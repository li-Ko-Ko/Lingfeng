# 参与贡献 / Contributing

伶风是个人维护的 Windows 桌面项目。欢迎报告可复现的问题，并提交针对明确问题的小范围修改。当前支持环境为 Windows x64、Python 3.13；应用版本由 `lingfeng/__init__.py` 定义。

Lingfeng is a personally maintained Windows desktop project. Reproducible bug reports and focused fixes are welcome. The supported environment is Windows x64 with Python 3.13; `lingfeng/__init__.py` defines the application version.

## 1. 开发环境 / Development environment

从全新检出开始执行以下 PowerShell 命令，使用 Windows x64 的 Python 3.13 和独立虚拟环境。

Start from a fresh checkout using Windows x64, Python 3.13 and a dedicated virtual environment.

```powershell
git clone https://github.com/li-Ko-Ko/Lingfeng.git
Set-Location Lingfeng
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe main.py --version
.\.venv\Scripts\python.exe main.py
```

`requirements-build.txt` 固定直接运行与构建依赖，包括 PySide6/shiboken6 6.9.2 和 PyInstaller 6.20.0；仅运行时也可安装 `requirements.txt`，其中 Qt 允许兼容版本范围。所有命令均从仓库根目录执行，不需要开发者本机的虚拟环境、缓存或安装路径。这些输入用于重建相同版本的程序及功能；传递依赖、Windows 与构建工具环境仍可能影响产物，不承诺 EXE 逐字节一致。

`requirements-build.txt` pins direct runtime and build dependencies, including PySide6/shiboken6 6.9.2 and PyInstaller 6.20.0. For runtime-only use, `requirements.txt` allows a compatible Qt range. Run every command from the repository root; no maintainer-specific environment, cache or installation path is required. These inputs reproduce the application version and functionality. Transitive dependencies, Windows and build-tool environments can still affect outputs; byte-for-byte identical executables are not promised.

默认构建随附 Greg Sullivan 电钢琴、三组 STK 原生合成包、GeneralUser GS 主包和 PFSynth 物理建模钢琴。Greg 使用包内 sfizz 播放 SFZ。GeneralUser GS 使用 FluidSynth 播放原版 SF2，在伶风中提供 128 个基础 GM 音色。保留预编译音源的完整文件夹。重建 STK 音源需要 STK 5.0.1、Zig 0.14.1 和 `scripts/build_synth_packs.py` 的显式 `--stk`、`--zig` 路径。PFSynth 的重建命令位于音源包的 `source/BUILD.txt`。Windows MIDI 使用本机已安装的输出设备。音源接口与构建说明见 [SOUNDBANKS](docs/SOUNDBANKS.md)。

首次从源码打包，先运行 `python scripts/build_piano_packs.py --pack electric --download` 准备 Greg。脚本仅在显式指定 `--download` 时访问网络。仓库提供 STK、GeneralUser GS 主包和 PFSynth 的完整目录。已有完整 Greg 音源目录时可直接构建。

Default builds include Greg Sullivan electric pianos, three native STK packs, the main GeneralUser GS pack and the PFSynth physically modeled piano. Greg uses sfizz for SFZ. GeneralUser GS uses FluidSynth to play the original SF2 and exposes 128 standard GM sounds in Lingfeng. Keep each prebuilt pack folder complete. Rebuilding the STK packs uses STK 5.0.1, Zig 0.14.1 and explicit `--stk`/`--zig` paths for `scripts/build_synth_packs.py`. PFSynth rebuild instructions are in its `source/BUILD.txt`. Windows MIDI uses locally installed devices. See [SOUNDBANKS](docs/SOUNDBANKS.md) for pack interfaces and build instructions.

Before packaging from a fresh checkout, run `python scripts/build_piano_packs.py --pack electric --download` to prepare Greg. Network access requires `--download`. The repository supplies complete STK, GeneralUser GS main and PFSynth pack folders. You can build directly when a complete Greg pack is already present.

若要手动直接重建原生 STK 包，先创建仓库 `tmp/`；该脚本把编译子进程的 `TEMP`／`TMP` 指向此目录。将下面两个工具路径替换为已准备好的完整 STK 5.0.1 源码目录与 Zig 0.14.1 可执行文件。常规程序构建使用仓库已有的完整音源包，不要求重新编译它们。

Before directly rebuilding the native STK packs, create the repository's `tmp/` directory: the builder uses it for compiler `TEMP`/`TMP`. Replace the two tool paths below with the complete STK 5.0.1 source directory and Zig 0.14.1 executable. A normal application build uses the complete packs already in the repository and does not require recompiling them.

```powershell
New-Item -ItemType Directory -Force tmp | Out-Null
.\.venv\Scripts\python.exe scripts/build_synth_packs.py --stk 'path\to\STK-5.0.1' --zig 'path\to\zig.exe'
```

## 2. 报告问题 / Report a problem

请在 [GitHub Issues](https://github.com/li-Ko-Ko/Lingfeng/issues) 查看是否已有相同问题；没有对应记录时，可新建问题并附上下面的复现信息。

Check [GitHub Issues](https://github.com/li-Ko-Ko/Lingfeng/issues) for an existing report. If there is no matching issue, open one with the reproduction details below.

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

源码及构建依赖位于仓库；静态帮助内容位于 `lingfeng/platform/help_content.py`，普通启动不执行安装自检。公开源码和发行包仅包含运行、重建、测试、用户说明及第三方许可所需文件。

The repository and release source bundle contain the inputs needed to run, rebuild and test the application, plus user documentation and third-party notices.

公开文件由 `scripts/release_policy.py` 的 `repository_files()` 清单统一选择。应用功能、完整离线音源、验证与许可构成可复现程序所需的公开文件集：

`repository_files()` in `scripts/release_policy.py` selects the public tree. Its scope covers application functionality, bundled offline sounds, validation and licensing:

| 文件 / Files | 用途 / Purpose |
| --- | --- |
| `main.py`、`lingfeng/`、审核后的 `assets/` | 启动入口、应用代码、语言目录与界面资源 / Launcher, application code, translations and UI assets |
| `requirements*.txt`、`build.ps1`、审核后的 `scripts/` | 运行依赖、程序打包、音源重建与校验 / Dependencies, packaging, sound rebuilds and checks |
| `native/`、审核后的 `synths/` | 原生合成接口、离线声音、引擎及对应重建输入 / Native synthesis, offline sounds, runtimes and their rebuild inputs |
| `tests/`、审核后的 `examples/` | 回归用例、测试辅助模块与可公开示例 / Regression tests, test helpers and shareable examples |
| `README.md`、`CONTRIBUTING.md`、`CHANGELOG.md`、审核后的 `docs/`、`licenses/`、`LICENSE` | 用户说明、格式、发行记录、来源及第三方条款 / Guides, format, archive history, sources and license terms |

六组随附音源是 `piano-electric`、`stk-essentials`、`stk-colors`、`stk-acoustic`、`generaluser-gs` 和 `pfsynth`。公开源码保留三组 STK、GeneralUser GS 主包、PFSynth 和旧版 `piano-small` 的音源文件。打包时从完整目录复制音源、引擎源码及许可。生成的 EXE、`dist/`、虚拟环境、缓存、验证输出、个人工程及用户偏好排除在源码交付清单外。

The six bundled packs are `piano-electric`, `stk-essentials`, `stk-colors`, `stk-acoustic`, `generaluser-gs` and `pfsynth`. The public source inventory retains the three STK packs, the main GeneralUser GS pack, PFSynth and the legacy `piano-small` assets. The standalone build copies sounds, runtime sources and licenses from the complete pack folders. Generated executables, `dist/`, environments, caches, validation outputs, personal scores and user preferences are excluded from the source delivery inventory.

保持每次修改围绕一个问题。音乐时间与演奏数据归模型所有，谱面排版不应改写 MIDI；普通编辑通过现有事务/撤销路径提交。界面文案需同时维护中文与英文，不使用显示标签作为稳定数据值。

Keep changes focused on one problem. The model owns musical time and performed events; engraving must not rewrite MIDI. Use the existing edit transaction/undo paths. Maintain Chinese and English UI text together, and keep stable data values independent of display labels.

```powershell
.\.venv\Scripts\python.exe scripts/run_regression.py
.\.venv\Scripts\python.exe scripts/audit_text.py
```

可先只运行相关模块，例如 0.57.1 的拖屏、缓存与撤销历史：

For a focused check, pass module names, for example panning, caches and undo history in 0.57.1:

```powershell
.\.venv\Scripts\python.exe scripts/run_regression.py test_v571_panning test_v571_caches test_v571_history
```

统一回归为每个 `tests/test_*.py` 模块创建独立进程，默认使用无屏幕 Qt 平台，并将 `LINGFENG_USER_DATA`、`LINGFENG_SYNTH_CACHE`、临时目录隔离到仓库 `tmp/`。结果写入 `output/`。完整套件包含 Windows 设备、原生合成与音频检查；无声、数值稳定或停音测试不能替代所有设备上的主观听感验收。修改后先运行相关模块，再进行发行需要的完整回归。

The runner starts each `tests/test_*.py` module in a separate process with offscreen Qt. It isolates `LINGFENG_USER_DATA`, `LINGFENG_SYNTH_CACHE` and temporary files under `tmp/`, writing results to `output/`. The full suite includes Windows device, native synthesis and audio checks. Silence, numerical stability and stop tests do not replace subjective listening on every device. Run relevant modules during development and the full suite for a release.

单独运行会建立窗口或使用偏好的测试时，也请设置隔离路径；不要让测试覆盖日常设置或和弦进行库：

When running tests individually, isolate their data as well so they cannot overwrite normal settings or progression presets:

```powershell
New-Item -ItemType Directory -Force tmp | Out-Null
$env:QT_QPA_PLATFORM = 'offscreen'
$env:LINGFENG_USER_DATA = Join-Path $PWD 'tmp\manual-test-user'
$env:LINGFENG_SYNTH_CACHE = Join-Path $PWD 'tmp\manual-test-index\current.json'
.\.venv\Scripts\python.exe -m unittest tests.test_music tests.test_harmony -v
```

源码也提供与便携程序相同的自检入口。请在单独的 PowerShell 终端中使用隔离设置目录；结果的 `result.json` 应为 `status: passed`。自检会创建临时工程、图片、PDF 与音频验证文件，不用于普通启动。

The source and portable application share a self-test entry point. Use isolated settings in a separate PowerShell terminal, and check that the resulting `result.json` has `status: passed`. Self-tests create projects, images, PDFs and audio verification files; normal startup does not run them.

```powershell
$env:LINGFENG_USER_DATA = Join-Path $PWD 'tmp\self-test-user'
$env:LINGFENG_SYNTH_CACHE = Join-Path $PWD 'tmp\self-test-index\current.json'
.\.venv\Scripts\python.exe main.py --self-test output\self-test-source
```

编辑帮助后运行 `python scripts/export_help.py`，从同一主题重新生成 [HELP](docs/HELP.md)；使用与项目相同的虚拟环境执行该命令。提交说明应包含具体问题、修改后的行为、实际运行的检查和仍未验证的范围。不要仅为匹配实现而放宽测试断言。

After editing help, run `python scripts/export_help.py` with the project environment to regenerate [HELP](docs/HELP.md) from the same topics. Describe the concrete problem, resulting behavior, checks actually run and any unverified scope in the change description. Do not relax assertions solely to match an implementation.

## 4. 打包 / Packaging

```powershell
.\build.ps1 -Python '.\.venv\Scripts\python.exe'
```

默认构建只更新 `dist/<版本>/Lingfeng/` 独立程序文件夹，包含源码、许可及上文列出的六组音源。ZIP 和 `.sha256` 由显式归档命令生成。运行独立 EXE 的 `--self-test <输出目录>`，再执行 `python scripts/verify_release.py` 检查文件夹的源码、运行资源和音源一致性。可把文件夹路径作为位置参数传入。

The default output is the standalone folder `dist/<version>/Lingfeng/`, including source, licenses and the six sound packs listed above. An explicit archive command produces the ZIP and `.sha256`. Run the executable with `--self-test <output-directory>`, then use `python scripts/verify_release.py` to check the folder's source, frozen resources and sounds. An explicit folder path may be supplied as a positional argument.

在单独的 PowerShell 终端中验证当前源码版本的构建。等待窗口版 EXE 的自检进程结束后读取报告。

To verify the build for the current source version, use a separate PowerShell terminal. Wait for the windowed executable to finish before reading the report.

```powershell
$env:LINGFENG_USER_DATA = Join-Path $PWD 'tmp\portable-test-user'
$env:LINGFENG_SYNTH_CACHE = Join-Path $PWD 'tmp\portable-test-index\current.json'
$testOutput = Join-Path $PWD 'output\self-test-portable'
$version = .\.venv\Scripts\python.exe -c 'from lingfeng import __version__; print(__version__)'
$standalone = Join-Path $PWD "dist\$version\Lingfeng"
$executable = Join-Path $standalone 'Lingfeng.exe'
$check = Start-Process -FilePath $executable -ArgumentList @('--self-test', "`"$testOutput`"") -WindowStyle Hidden -Wait -PassThru
if ($check.ExitCode -ne 0) { throw 'Standalone self-test failed. Check result.json.' }
Get-Content (Join-Path $testOutput 'result.json')
.\.venv\Scripts\python.exe scripts/verify_release.py $standalone
```

只有明确要求生成新的发行归档时，才使用下面的可选命令。已有同版本 ZIP 或校验文件会报错并保留，不允许覆盖；不会隐式生成单独的音源 ZIP。

Use the optional commands below only when a new release archive is explicitly requested. An existing version ZIP or checksum causes an error and is preserved. Separate sound-pack ZIPs are never created implicitly.

```powershell
.\build.ps1 -Python '.\.venv\Scripts\python.exe' -Archive
# Or archive an already built standalone folder explicitly:
.\.venv\Scripts\python.exe scripts/package_release.py --archive
.\.venv\Scripts\python.exe scripts/verify_release.py --archive
```

[CHANGELOG](CHANGELOG.md) 仅记录实际已生成发行归档的版本；只有源码和本地文件夹的更新不新增发行节点。创建归档不代表已经上传或发布。保留第三方许可和对应源码说明；不要提交本机构建环境、录音、调试日志或私人工程。

[CHANGELOG](CHANGELOG.md) records versions for which release archives were actually generated. Source-only and local-folder updates do not add release entries. Creating an archive does not imply uploading or publishing it. Preserve third-party notices and corresponding-source information; do not commit local environments, recordings, debug logs or private projects as source.

## 5. 许可 / Licensing

原创应用代码采用 [MIT](LICENSE)。提交代码时需有权按该许可公开；引入第三方代码、字体、图像、音源或示例前，保留其原许可与来源并说明兼容条件。不能因为项目使用 MIT 就把第三方依赖重新标为 MIT。

Original application code is [MIT](LICENSE). Contributions must be shareable under that license. Retain source and license information for new third-party code, fonts, images, instruments or examples, and explain their compatibility. The application's MIT license does not relicense its dependencies.

STK 合成包沿用 STK 许可，Qt/PySide6、编码器等各自保留条款。组件、来源与兼容替换说明统一见 [THIRD_PARTY](docs/THIRD_PARTY.md)，音源安装与 ABI 见 [SOUNDBANKS](docs/SOUNDBANKS.md)。软件与音源许可不替代作品、歌词及录音素材的授权。

STK packs retain their STK terms; Qt/PySide6, the encoder and other dependencies retain theirs. Component sources and replacement instructions are in [THIRD_PARTY](docs/THIRD_PARTY.md); synth installation and ABI details are in [SOUNDBANKS](docs/SOUNDBANKS.md). Software/instrument licenses do not clear compositions, lyrics or recordings.

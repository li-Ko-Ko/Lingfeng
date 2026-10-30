# MP3 encoder corresponding source and replacement

Lingfeng uses unmodified lameenc 1.8.1 (LGPL-3.0) and its bundled LAME 3.100 encoder (LGPL-2.0-or-later). The original application remains MIT. Complete notices and upstream source archives are included here. `manifest.json` records their SHA-256 hashes.

- lameenc: https://github.com/chrisstaite/lameenc/tree/v1.8.1
- LAME archive: https://sourceforge.net/projects/lame/files/lame/3.100/lame-3.100.tar.gz/download
- The LAME archive hash is pinned in upstream lameenc's `CMakeLists.txt`.
- `patch-lame.cmake`, included in the lameenc source archive and separately here, is the upstream Windows build patch. Lingfeng adds no patches.

To modify/rebuild, unpack both source archives, use Python 3.13 x64 with the Windows C/C++ build tools, CMake and the upstream `CMakeLists.txt` / `setup.py`. CMake builds the static LAME encoder into the replaceable Python extension. Point its LAME ExternalProject source at the supplied archive when building offline. Copy the resulting compatible `lameenc.cp313-win_amd64.pyd` into the portable app's `_internal` folder, or install it in a source environment and rebuild Lingfeng using `source/build.ps1` and `source/requirements-build.txt`. The application's complete source is supplied separately.

The application does not prohibit modifying or replacing this library, or reverse engineering for debugging those modifications. The encoder extension is a separate dynamically loaded module, not embedded into Lingfeng's original source. SoundCard's BSD-3-Clause source, NumPy's BSD and bundled notices, and CFFI's MIT and pycparser's BSD-3-Clause notices are preserved in the release's `licenses` directory. No Microsoft MIDI sound-bank files are redistributed.

伶风允许修改、替换兼容的编码器扩展及为调试修改后的库而进行逆向工程。使用随附源码和构建脚本即可重建应用；第三方库保持各自许可，不能将整包称为“全部 MIT”。

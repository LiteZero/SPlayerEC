# SPlayerEC · K20 GT 歌词互联

[![Build Windows](https://github.com/LiteZero/SPlayerEC/actions/workflows/build.yml/badge.svg)](https://github.com/LiteZero/SPlayerEC/actions/workflows/build.yml)
[![License: LGPL-3.0-or-later](https://img.shields.io/badge/License-LGPL--3.0--or--later-blue.svg)](LICENSE)

通过 SPlayer-Next 的现有插件 API，将当前歌词发送到迈从 K20 GT 音箱，从而实现类似于官方的桌面歌词功能。

适用于 64 位 Windows 10/11，以及提供插件 API 2 或更高版本的 SPlayer-Next

## 开始使用

1. 安装 `SPlayerEC`，或解压便携包后运行 `SPlayerEC-Bridge.exe`
2. 用 USB 连接 K20 GT，关闭 MCHOSE HUB 的歌词同步。
3. 在 SPlayer 中打开「设置 → 插件管理 → 本地导入」，选择 `k20gt-lyrics.js`。桥接程序窗口有「打开插件文件夹」按钮
4. 确认插件已启用，并保留 `network` 和 `control` 权限。`control` 用于读取播放进度或快照，插件不会执行播放、暂停、切歌或音量修改
5. 播放带歌词的歌曲，桥接窗口显示「已连接 K20 GT」后即可同步

安装包会安装桥接程序、插件文件和说明，插件需要在播放器中手动导入一次。便携包可以放在任意目录，但移动文件后需重新设置登录启动

## 日常使用

- 插件设置可选择原文、翻译或音译，缺少对应文本时使用原文
- 每页最多 52 个 UTF-8 字节，长行按播放时间分页，不截断中文和 emoji
- 暂停保留当前页；拖动进度或倍速后会按实际播放进度校正显示
- API 4 及以上支持歌词偏移的精确分页；API 2/3 通过播放器行事件跟随当前歌词，但旧接口不提供偏移快照，非零偏移下长行分页和间奏边界可能有偏差
- 间奏、停止、无歌词时退出歌词显示通道
- 关闭桥接窗口会隐藏到托盘，右键托盘图标选择「退出」才会关闭程序并清屏
- 可在桥接窗口勾选登录 Windows 时启动，默认关闭
- USB 插拔或写入失败后自动重连，只保留最新文字
- 关闭插件内部同步开关会主动清屏；从 SPlayer 禁用/卸载插件或退出播放器后，桥接程序在最后一次有效心跳的 8 秒后清屏并释放设备
- 插件只向本机 `127.0.0.1:19620` 请求，不向外部服务上传歌词

桥接程序只在有文字时打开设备，没有歌词时显示「等待歌词」。USB 写入返回成功只能证明命令发送成功，最终字形取决于音箱字库

## 文件与维护

- `plugin/k20gt-lyrics.js`：可直接导入的单文件插件
- `splayerec/` 和 `bridge.py`：桥接程序源码
- `dist/SPlayerEC-1.0.1-portable/`：无需 Python 的可运行目录
- `dist/SPlayerEC-1.0.1-x64-setup.exe`：当前用户安装包，无需管理员权限
- `dist/SPlayerEC-1.0.1-x64-portable.zip`：完整便携压缩包
- `dist/SHA256SUMS.txt`：交付文件校验值
- `VALIDATION.md`：测试范围、真机写入与内存采样记录

插件更新后重新导入同一脚本即可，插件 ID 保持不变。桥接更新前请退出托盘程序。播放器升级后需继续支持插件 API 2 或以上

安装版路径默认为 `%LOCALAPPDATA%\Programs\SPlayerEC`，日志在 `%LOCALAPPDATA%\SPlayerEC\bridge.log`，最多保留三份各 256 KB 的日志，不记录歌词正文

## 本地接口

`GET http://127.0.0.1:19620/health` 返回版本、连接状态、当前文字和成功写入次数

`POST http://127.0.0.1:19620/v1/display` 接受 `Content-Type: application/json` 和正文 `{"text":"歌词"}`。空字符串清屏，每次有效请求续期 8 秒，接口限制正文为 4096 字节、文字为 52 个 UTF-8 字节

接口仅监听 IPv4 回环地址，写入时校验 Host、拒绝 Origin 请求且不提供 CORS。它面向本机程序互联，不作为多用户认证服务

## 开发与构建

Python 3.14 x64、Node.js 22+，全部命令在项目目录执行：

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-build.txt
.venv/Scripts/python -m unittest discover -s tests -v
node --test tests/plugin.test.cjs
.venv/Scripts/python bridge.py
.venv/Scripts/python scripts/build.py
```

构建脚本下载并核对 NSIS 3.0.4.1 的 SHA-256，使用 PyInstaller 生成自带 Python 运行环境的程序，再生成安装包、便携包和对应源码归档。不依赖 SPlayer 的 node_modules、Rust、Visual Studio 或 FFmpeg

只读设备诊断：`SPlayerEC-Bridge.exe --probe --output devices.json`。无窗口诊断：`SPlayerEC-Bridge.exe --headless`，该模式持续运行到进程收到退出信号

需要从脚本安全退出时，可执行 `SPlayerEC-Bridge.exe --quit`，它会通知现有进程清屏并退出。安装包卸载也使用此方式

真机测试可执行 `.venv/Scripts/python scripts/integration.py ../SPlayer-Next`，会启动便携版和 SPlayer 的实际插件沙箱，在音箱上显示测试文字并执行三轮各 60 秒内存采样。需要相邻 SPlayer 源码已安装 Node 依赖和 Electron，仅此测试需要引用播放器源码

安装版 API 3 兼容性测试可执行 `node scripts/legacy-host-smoke.cjs`，默认只读提取 `D:/Program Files/SPlayer-Next/resources/app.asar` 中的元数据解析器和插件宿主，在独立端口 19621 验证，不操作现有播放器配置或音箱。可通过首个命令行参数指定安装目录，此测试也需要相邻 SPlayer 源码的 Electron 和 ASAR 工具依赖

## GitHub Actions 构建

仓库只保存源码、测试、说明和构建配置，`dist/`、`build/`、工具下载、虚拟环境和本机测试报告均不提交

推送到 `main`、推送 `v*` 标签或提交拉取请求时，会自动执行 Windows x64 构建。也可打开仓库的 **Actions → Build Windows → Run workflow** 手动触发

工作流在 Windows 环境安装 Python 3.14、Node.js 24 和固定版本的构建依赖，运行 24 项自动化测试，再生成安装包、便携包、随附源码 ZIP 和 SHA-256 清单，不依赖 SPlayer 源码或 USB 设备

构建成功后，在该次运行页面的 **Artifacts** 中下载 `SPlayerEC-windows-x64`，解压后可取得安装包和便携包。产物保留 30 天；工作流不会把生成的二进制文件提交回仓库，也不会自动创建 Release

在下载目录执行 `sha256sum -c SHA256SUMS.txt` 可验证安装包和便携包。CI 不执行真机写入、安装卸载和完整播放器联动测试，本机的历史验证范围见 VALIDATION.md

## 许可

本项目原创源码采用 **LGPL-3.0-or-later**，可按 GNU Lesser General Public License 第 3 版或任意后续版本使用、修改和分发。完整条款见 LICENSE / COPYING.LESSER，以及作为其组成部分的 GPL-3.0 条款 COPYING

本仓库不包含 SPlayer-Next 的播放器实现或打包程序。

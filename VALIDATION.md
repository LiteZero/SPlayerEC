# 验证记录

## 2026-11-01 歌词插件 1.0.2 修复

歌词修复位于插件端，仍兼容 1.0.1 桥接程序。1.0.2 发布将插件、桥接程序和安装包版本统一为 1.0.2，并通过现有 GitHub Actions 构建；发布配置同时提供独立插件 JS、独立桥接 EXE、含二者的安装包与便携包及四个文件的 SHA-256 清单，并验证独立文件与便携包内文件一致。下文的安装及真机记录属于历史版本，不代表本次重新执行。

查阅官方插件 [播放控制文档](https://github.com/SPlayer-Dev/SPlayer-Next/blob/47d74cf1a87cc0f526c25110bb0cb924f6268f1d/docs/plugins/control.md)、[API 变更记录](https://github.com/SPlayer-Dev/SPlayer-Next/blob/47d74cf1a87cc0f526c25110bb0cb924f6268f1d/docs/plugins/changelog.md) 和 [播放事件桥源码](https://github.com/SPlayer-Dev/SPlayer-Next/blob/47d74cf1a87cc0f526c25110bb0cb924f6268f1d/electron/main/plugins/playbackBridge.ts)：API 2 起提供 `playStateChange`，载荷包含 `state: "playing" | "paused" | "stopped"` 及毫秒进度 `position`；当前行以 `startTime` 选取，不以 `endTime` 提前取消。

同时只读检查本机安装的 SPlayer-Next 1.2.0，宿主 API 为 5；安装版事件桥与上述行为一致。本机播放器日志未发现逐次播放状态事件或本插件异常记录，不能用这些日志直接还原用户遇到的具体歌曲问题。

修复内容：

- 暂停、停止事件立即使旧进度请求失效，清屏成功后不再发送请求或轮询进度；恢复事件触发同步。
- 在途请求完成或失败时不能覆盖更新的暂停状态，发送队列丢弃暂停前积压的歌词。
- `endTime` 只决定分页速度，末页保持到下一行、明确空行或歌曲结束；无有效 `endTime` 时使用下一行或歌曲结束作为分页边界。
- 歌曲结束判断使用实际播放进度，避免歌词偏移使尾句提前消失。
- 与宿主选行一致，没有明确空行的间奏保留上一句；不再仅凭上一句 `endTime` 清屏。

执行 `node --test tests/plugin.test.cjs`，28 项通过。覆盖 API 2/3/4/5 的暂停/停止清屏与持续静默、恢复、长句末页保持、下一行及歌曲结束、空行、UTF-8 分页、歌词偏移、倍速、过期异步结果和失败、慢请求队列及故障恢复。本次未修改 Python 源码，未重新运行 Python 测试。

另外从 `D:/Program Files/SPlayer-Next/resources/app.asar` 只读提取原始插件 worker，在 Node.js 24.21.0 的 `worker_threads` 中适配 `process.parentPort` 后运行原始 VM 沙箱，通过独立的随机回环端口完成真实 HTTP 请求。分别以实际 API 5 及兼容 API 3 运行，验证两页长句、超过 `endTime` 后继续显示、暂停与停止期间各 2.5 秒无请求及进度读取、恢复、下一行、歌曲结束，均通过且无警告或错误日志。

此次 worker 验证使用人工构造的歌词和播放输入，不是 Electron utility process 或完整播放器实播；未向音箱写入，未修改播放器配置。原始记录保存在本机忽略目录 `build/plugin-fix-worker-smoke-api5.json` 和 `build/plugin-fix-worker-smoke-api3.json`。实际歌曲及音箱屏幕表现仍需更新插件后验证。

## 历史验证记录

日期：2026-10-20，时区：Asia/Shanghai

环境：Windows x64，Python 3.14.7，Node.js 24.21.0，Electron 43.2.0

以下原始 JSON 记录保留在本机，不提交到 GitHub，也不放入源码归档。CI 只执行自动化测试和打包，不将历史真机验证视为每次构建的结果

## 1.0.1 兼容性修复

针对用户安装的 SPlayer-Next 1.1.0（宿主 API 3），插件补齐 `@type control`，最低声明 API 2；API 2/3 使用 `player.getPosition()` 和播放事件，API 4 及以上保留播放快照

当前共 24 项自动化测试通过：Python 11 项、Node.js 13 项。新增测试覆盖 API 2/3 完全不存在 `getNowPlaying` 时的加载、控制能力声明、歌词分页、暂停、同一行跳转、倍速、停止、当前行索引及背景人声索引映射

执行 `scripts/legacy-host-smoke.cjs`，从用户实际安装目录的 `app.asar` 只读提取原始元数据解析器和插件 worker，使用安装版原始解析器确认插件可通过导入检查，类型为 control 且具有 network/control 权限，再运行原始 worker 的 Electron utility process

验证普通中文歌词、两页长行、暂停时同一行内跳转、翻译切换、停止清屏及恢复、内部开关停用后不再请求、卸载后停止请求。共完成 295 次旧版进度接口调用、39 次 HTTP 请求，没有调用 API 4 接口，没有警告或错误日志

接口使用独立的 `127.0.0.1:19621` HTTP 测试服务，未调用用户现有桥接程序或向音箱写入，也未修改安装的播放器及其配置。原始记录：`tests/legacy-host-smoke.json`，其中 `complete` 为 true

| 阶段               | 隔离 Electron 进程工作集合计 |
| ------------------ | ---------------------------: |
| 空宿主等待 60 秒   |                   204.86 MiB |
| 插件启用等待 60 秒 |                   226.15 MiB |
| 插件卸载后         |                   226.19 MiB |

这些采样包含测试主进程、网络服务、GPU 和插件宿主；启用后发起了实际 HTTP 请求，不代表插件自身占用。未运行完整播放器、未执行 10 分钟以上长期测试，卸载后工作集也不保证立即回落

旧版接口不提供歌词偏移和倍速快照：倍速通过实测进度跟随，当前歌词行通过宿主事件选择；非零歌词偏移下的长行精确分页和间奏边界不能保证与 API 4 一致

1.0.1 重新构建安装包与便携包，并检查归档完整性、插件内容一致性和 SHA-256。本次保留用户正在运行的旧桥接程序，未重新执行安装、卸载或真机写入测试；下面的真机与安装记录属于 1.0.0

## 1.0.0 自动化测试记录

共 19 项通过：Python 11 项、Node.js 8 项

- 普通歌词和清屏报文的全部头部字节、64 字节总长、UTF-8 容量和无效字符拒绝
- 中文和 emoji 分页、翻译与音译回退、背景人声过滤
- 暂停保持、同一行内跳转、歌词偏移、倍速和间奏清屏
- 同文本请求合并、必要心跳、慢请求只保留最新页、桥接故障重试限频
- 切歌后丢弃旧快照、插件设置停用后停止持续请求
- 慢 USB 写入合并、掉线后显示最新页、失联清屏、退出释放
- 真实 HTTP 接口的正文大小、UTF-8 长度、Origin、Host 和 Content-Type 校验
- 安全退出请求通知主循环，由主循环统一清理设备

Python 静态检查和格式化、JavaScript 格式检查通过，构建时重新执行上述自动化测试

## 1.0.0 实际宿主与硬件

当时使用 SPlayer-Next 当前源码的 Electron 43.2.0 插件沙箱，实际连接的 K20 GT USB 设备为 `3837:60C6`

执行 `scripts/integration.py`，启动打包的便携版托盘程序，并从相邻 SPlayer 源码编译、运行实际的 `host.worker.ts`

插件在 Electron utility process 的实际 VM 上下文中加载，通过实际 `splayer` 消息接口和 Electron `net.fetch` 访问桥接程序，再由 Windows HID 完成真实 USB 写入

已成功发送「SPlayerEC 歌词测试」、中文长句的两个分页、「翻译同步测试」和「后台歌词互联测试」。同一行内修改播放位置而不发送 lineChange，也能由快照校正到正确分页

卸载插件后，停止所有插件定时器和请求，8 秒心跳到期后桥接状态变为 waiting，当前文字清空，设备句柄释放。测试结束通过 `--quit` 关闭托盘程序

这些播放输入来自测试构造的曲目、歌词和进度快照，未启动完整播放器界面，也未覆盖实际音频解码播放。USB 写入成功已确认，音箱屏幕最终字形仍需目视确认，长时间播放、休眠唤醒和真实拔插留待日常使用验证

原始数据：`tests/host-smoke.json`

## 1.0.0 内存采样

每个阶段均等待 60 秒，使用 Electron `app.getAppMetrics()` 和 Windows `tasklist` 工作集数据。基线已经启动共享插件宿主和独立桥接程序，尚未加载歌词插件

| 阶段       | Electron 隔离宿主合计 | 其中插件 utility process | 桥接程序进程合计 |
| ---------- | --------------------: | -----------------------: | ---------------: |
| 加载前     |            226.30 MiB |                60.39 MiB |        71.19 MiB |
| 插件启用后 |            231.82 MiB |                62.05 MiB |        72.04 MiB |
| 插件卸载后 |            231.64 MiB |                61.93 MiB |        72.04 MiB |

桥接程序的单文件打包方式包含启动器和工作进程，两者已计入。插件卸载后共享宿主及桥接程序仍可继续服务，工作集不保证立即回到基线；桥接退出后进程结束

这里没有播放器主窗口和音频引擎，数据仅说明隔离场景的增量与短时稳定性，不能作为完整 SPlayer 的内存占用或 10 分钟以上长期稳定性结论

## 1.0.0 安装与交付

提供安装版 EXE、便携 ZIP、可直接导入的 JS 插件、项目对应源码 ZIP 和 SHA-256 清单

安装包以当前用户权限安装到独立测试目录，核对程序和插件内容，启动安装后的桥接程序并完成「安装版歌词测试」的真实 HID 写入，随后正常退出和卸载，检查安装文件及安装注册表清理

原始数据：`tests/installer-smoke.json`

交付程序自带 Python 运行环境，正常使用不依赖系统 Python、Node.js、Rust、Visual Studio 或 SPlayer 源码。未对 SPlayer-Next 的现有工作树作修改

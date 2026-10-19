通过 SPlayer-Next 插件与独立 USB HID 桥接程序，将歌词同步到迈从 K20 GT 音箱

## 下载与使用

- `SPlayerEC-*-x64-setup.exe`：Windows 10/11 x64 安装包，无需管理员权限
- `SPlayerEC-*-x64-portable.zip`：便携版，解压后运行 `SPlayerEC-Bridge.exe`
- `SHA256SUMS.txt`：安装包和便携包的 SHA-256 校验值

用 USB 连接 K20 GT，启动桥接程序，再在 SPlayer「设置 → 插件管理 → 本地导入」中导入包内的 `plugin/k20gt-lyrics.js`，允许 `network` 和 `control` 权限并启用插件

插件支持 API 2 及以上，已验证 SPlayer-Next 1.1.0 的 API 3 宿主。已有桥接程序的用户可只更新插件文件，若存在旧版失败条目，先删除再导入

支持中文长句分页、翻译和音译、暂停保持、拖动进度及倍速跟随。API 2/3 不提供歌词偏移快照，非零偏移下的长行分页和间奏边界可能存在偏差

运行时不需要安装 Python、Node.js 或 SPlayer 源码。安装包和便携包包含对应源码 ZIP、构建说明与第三方许可，本项目原创源码采用 LGPL-3.0-or-later

## 构建验证

本次发布由 GitHub Actions 从版本标签构建，执行 24 项自动化测试、ZIP 完整性检查和 SHA-256 校验后发布。CI 不执行真实 USB 写入、安装卸载或完整播放器联动测试

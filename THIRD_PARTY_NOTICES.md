# 第三方组件

SPlayerEC 基于 Python 标准库和以下开源组件构建，未修改其源代码

| 组件               | 用途                                | 许可与来源                                                  |
| ------------------ | ----------------------------------- | ----------------------------------------------------------- |
| Python 3.14        | 桥接运行环境、ctypes、HTTP、Tkinter | PSF License，https://www.python.org/                        |
| Tcl/Tk             | 状态窗口                            | Tcl/Tk License，https://www.tcl.tk/                         |
| pystray 0.19.5     | Windows 托盘                        | LGPL-3.0，https://github.com/moses-palmer/pystray           |
| Pillow 13.0.0      | 生成托盘图标                        | MIT-CMU，https://python-pillow.org/                         |
| PyInstaller 6.22.3 | 自带运行环境打包                    | GPL-2.0 with bootloader exception，https://pyinstaller.org/ |
| NSIS 3.0.4.1       | 当前用户安装包                      | zlib/libpng 与组件各自许可，https://nsis.sourceforge.io/    |

项目原创源码采用 LGPL-3.0-or-later，发布包内的 `SPlayerEC-1.0.1-source.zip` 提供对应源码，可解压修改并按 README 重建。上述依赖可通过固定版本的 requirements 文件和官方项目地址取得，`licenses/` 随附它们的许可文本

SPlayer-Next 为独立的 AGPL-3.0 项目，来源：https://github.com/SPlayer-Dev/SPlayer-Next 。本仓库仅通过其公开插件接口互联，不包含其播放器源码或二进制。歌词分页参考 LiteZero 自行添加的 K20 GT 辅助代码（提交 `cf0bdce0`），设备报文依据用户提供的前期 USB 测试，不将 SPlayer-Next 上游代码改标为 LGPL

`scripts/legacy-host-smoke.cjs` 和 `scripts/host-smoke.cjs` 仅在本机测试时读取外部 SPlayer 安装或源码；提取、编译生成的宿主代码保存在忽略的 `build/` 目录，不随本仓库或源码 ZIP 发布

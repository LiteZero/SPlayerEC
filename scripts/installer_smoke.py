# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (C) 2026 LiteZero

"""在独立临时安装目录验证安装、运行和卸载"""

import hashlib
import json
import subprocess
import time
import urllib.request
import winreg
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    """确认没有现有安装后，安装到项目构建目录并验证卸载清理"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\SPlayerEC"):
            pass
    except FileNotFoundError:
        pass
    else:
        raise RuntimeError("已有 SPlayerEC 安装，请勿用安装测试覆盖现有配置")
    try:
        with urllib.request.urlopen("http://127.0.0.1:19620/health", timeout=1):
            pass
    except OSError:
        pass
    else:
        raise RuntimeError("已有桥接程序运行，请先退出再执行安装测试")
    directory = (ROOT / "build" / "installer-smoke").resolve()
    if directory.parent != (ROOT / "build").resolve() or directory.exists():
        raise RuntimeError("安装测试目录必须是尚不存在的 build/installer-smoke")
    installer = ROOT / "dist" / "SPlayerEC-1.0.1-x64-setup.exe"
    report = {"installed": False, "launched": False, "uninstalled": False}
    subprocess.run(
        [str(installer), "/S", f"/D={directory}"], check=True, timeout=45, creationflags=0x08000000
    )
    report["installed"] = True
    executable = directory / "SPlayerEC-Bridge.exe"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\SPlayerEC") as key:
        assert Path(winreg.QueryValueEx(key, "InstallDir")[0]) == directory
    for name in ["SPlayerEC-Bridge.exe", "plugin/k20gt-lyrics.js", "README.md", "VALIDATION.md"]:
        assert (
            hashlib.sha256((directory / name).read_bytes()).digest()
            == hashlib.sha256(
                (ROOT / "dist" / "SPlayerEC-1.0.1-portable" / name).read_bytes()
            ).digest()
        )
    child = subprocess.Popen([str(executable), "--tray"], creationflags=0x08000000)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            try:
                with urllib.request.urlopen("http://127.0.0.1:19620/health", timeout=1) as response:
                    report["health"] = json.load(response)
                report["launched"] = True
                break
            except OSError:
                time.sleep(0.2)
        assert report["launched"], "安装后的桥接程序未启动"
        request = urllib.request.Request(
            "http://127.0.0.1:19620/v1/display",
            json.dumps({"text": "安装版歌词测试"}).encode(),
            {"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            assert json.load(response)["ok"]
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with urllib.request.urlopen("http://127.0.0.1:19620/health", timeout=1) as response:
                state = json.load(response)
            if state["state"] == "connected" and state["writes"] >= 1:
                report["deviceWrite"] = state
                break
            time.sleep(0.1)
        assert "deviceWrite" in report, "安装版未完成真实设备写入"
    finally:
        subprocess.run(
            [str(executable), "--quit"], check=True, timeout=10, creationflags=0x08000000
        )
        child.wait(timeout=10)
        subprocess.run(
            [str(directory / "Uninstall.exe"), "/S"],
            check=True,
            timeout=30,
            creationflags=0x08000000,
        )
        deadline = time.monotonic() + 15
        while executable.exists() and time.monotonic() < deadline:
            time.sleep(0.2)
        assert not executable.exists(), "卸载后仍残留程序"
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\SPlayerEC"):
                pass
        except FileNotFoundError:
            report["uninstalled"] = True
        assert report["uninstalled"], "卸载后仍残留安装注册表"
        (ROOT / "tests" / "installer-smoke.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()

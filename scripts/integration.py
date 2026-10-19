# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (C) 2026 LiteZero

"""真机验证：启动便携版，通过实际插件宿主发送测试文字"""

import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    """隔离运行交付程序与 SPlayer 插件宿主，验证后清屏退出"""
    executable = ROOT / "dist" / "SPlayerEC-1.0.1-portable" / "SPlayerEC-Bridge.exe"
    try:
        with urllib.request.urlopen("http://127.0.0.1:19620/health", timeout=1):
            pass
    except OSError:
        pass
    else:
        raise RuntimeError("请先退出已运行的桥接程序，再执行真机测试")
    child = subprocess.Popen([str(executable), "--tray"], creationflags=0x08000000)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if child.poll() is not None:
                raise RuntimeError(f"桥接程序启动失败：{child.returncode}")
            try:
                with urllib.request.urlopen("http://127.0.0.1:19620/health", timeout=1) as response:
                    if json.load(response).get("app") == "SPlayerEC":
                        break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("桥接程序未在时限内启动")
        command = ["node", "scripts/host-smoke.cjs"]
        if len(sys.argv) > 1:
            command.append(sys.argv[1])
        subprocess.run(command, cwd=ROOT, check=True)
    finally:
        subprocess.run(
            [str(executable), "--quit"],
            check=False,
            timeout=10,
            creationflags=0x08000000,
        )
        try:
            child.wait(timeout=10)
        except subprocess.TimeoutExpired:
            child.terminate()
            child.wait(timeout=5)


if __name__ == "__main__":
    main()

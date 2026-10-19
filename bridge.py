# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (C) 2026 LiteZero

"""SPlayerEC 的打包入口和命令行诊断工具"""

import argparse
import json
import logging
import os
import signal
import sys
import threading
import time
import urllib.request
from logging.handlers import RotatingFileHandler
from pathlib import Path

from splayerec.hid import K20GT, WindowsHID
from splayerec.http_server import PORT, start_server
from splayerec.service import BridgeService

log = logging.getLogger("splayerec")


def main():
    """启动桥接或只读设备探测，退出时关闭接口并清理设备"""
    parser = argparse.ArgumentParser(description="SPlayerEC · K20 GT 歌词桥接")
    parser.add_argument("--headless", action="store_true", help="无窗口运行，用于诊断")
    parser.add_argument("--tray", action="store_true", help="启动时隐藏到托盘")
    parser.add_argument("--probe", action="store_true", help="仅枚举设备并输出 JSON，不发送文字")
    parser.add_argument("--quit", action="store_true", help="通知正在运行的桥接程序清屏并退出")
    parser.add_argument("--output", type=Path, help="将探测结果写入指定文件")
    args = parser.parse_args()
    if args.quit:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=1) as response:
                if json.load(response).get("app") != "SPlayerEC":
                    return
            request = urllib.request.Request(
                f"http://127.0.0.1:{PORT}/v1/shutdown",
                b'{"action":"exit"}',
                {"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=2):
                pass
            end = time.monotonic() + 5
            while time.monotonic() < end:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/health", timeout=0.5):
                        pass
                except OSError:
                    break
                time.sleep(0.1)
        except OSError:
            pass
        return
    if args.probe:
        result = json.dumps({"devices": WindowsHID().devices()}, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(result, encoding="utf-8")
        if sys.stdout is not None:
            print(result)
        return
    data = Path(os.environ["LOCALAPPDATA"]) / "SPlayerEC"
    data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            RotatingFileHandler(
                data / "bridge.log",
                maxBytes=256 * 1024,
                backupCount=2,
                encoding="utf-8",
            )
        ],
    )
    service = BridgeService(K20GT)
    stopping = threading.Event()
    try:
        try:
            server = start_server(service, shutdown_event=stopping)
        except OSError as error:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{PORT}/health", timeout=1
                ) as response:
                    existing = json.load(response)
                if existing.get("app") == "SPlayerEC":
                    message = "SPlayerEC 已在运行，请从系统托盘打开状态窗口"
                else:
                    message = f"端口 {PORT} 已被其他程序占用"
            except OSError, ValueError:
                message = f"无法启动本机接口：{error}"
            log.error(message)
            if args.headless:
                raise RuntimeError(message) from error
            from tkinter import messagebox

            messagebox.showinfo("SPlayerEC", message)
            return
        log.info("桥接程序已启动，监听 127.0.0.1:%s", PORT)
        try:
            if args.headless:
                signal.signal(signal.SIGINT, lambda *_args: stopping.set())
                signal.signal(signal.SIGTERM, lambda *_args: stopping.set())
                stopping.wait()
            else:
                from splayerec.ui import run_ui

                run_ui(service, tray=args.tray, shutdown_event=stopping)
        finally:
            server.shutdown()
            server.server_close()
    finally:
        service.stop()
        log.info("桥接程序已退出")


if __name__ == "__main__":
    main()

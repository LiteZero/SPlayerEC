# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (C) 2026 LiteZero

"""有界的最新文字队列和设备生命周期管理"""

import logging
import threading
import time

from .protocol import encode_report

LEASE_SECONDS = 8
log = logging.getLogger("splayerec.usb")


class BridgeService:
    def __init__(self, device_factory):
        """接收设备构造器，所有 USB 操作均由单一工作线程执行"""
        self._factory = device_factory
        self._lock = threading.Condition()
        self._text = ""
        self._seen = None
        self._stopping = False
        self._status = {"state": "waiting", "error": "", "writes": 0}
        self._thread = threading.Thread(target=self._run, name="k20gt-usb", daemon=True)
        self._thread.start()

    def submit(self, text: str):
        """校验一页文字并覆盖待发内容，同时续期插件心跳"""
        encode_report(text)
        with self._lock:
            self._text = text
            self._seen = time.monotonic()
            self._lock.notify()

    def snapshot(self):
        """读取轻量连接状态，不复制歌词历史"""
        with self._lock:
            return {
                **self._status,
                "active": self._seen is not None,
                "text": self._text,
            }

    def stop(self):
        """通知工作线程清屏并关闭设备，等待有限时间"""
        with self._lock:
            self._stopping = True
            self._lock.notify()
        self._thread.join(timeout=4)

    def _run(self):
        """串行写入并合并积压页面，在失联、异常和退出时释放句柄"""
        device = None
        sent = None
        last_write = 0
        retry_at = 0
        previous_error = ""
        try:
            while True:
                with self._lock:
                    if self._stopping:
                        break
                    now = time.monotonic()
                    if self._seen is not None and now - self._seen >= LEASE_SECONDS:
                        self._text, self._seen = "", None
                    text = self._text
                try:
                    if not text:
                        if device is not None:
                            device.show("")
                            device.close()
                            device, sent = None, None
                        with self._lock:
                            self._status.update(state="waiting", error="")
                    elif now >= retry_at:
                        if device is None:
                            device = self._factory()
                            sent = None
                        if sent != text or now - last_write >= 3:
                            device.show(text)
                            sent, last_write = text, time.monotonic()
                            with self._lock:
                                self._status["writes"] += 1
                        previous_error = ""
                        with self._lock:
                            self._status.update(state="connected", error="")
                except (OSError, TimeoutError) as error:
                    if device is not None:
                        device.close()
                        device = None
                    message = str(error)
                    if message != previous_error:
                        log.warning("设备连接失败：%s", message)
                    previous_error = message
                    retry_at = time.monotonic() + 2
                    with self._lock:
                        self._status.update(state="disconnected", error=message)
                with self._lock:
                    if not self._stopping and self._text == text:
                        self._lock.wait(timeout=0.1)
        finally:
            if device is not None:
                try:
                    device.show("")
                except OSError, TimeoutError:
                    log.warning("退出时音箱清屏未完成")
                finally:
                    device.close()

# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (C) 2026 LiteZero

"""协议、HTTP 边界和 USB 生命周期的行为测试"""

import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from splayerec.http_server import start_server
from splayerec.protocol import encode_report
from splayerec.service import BridgeService


def eventually(predicate, timeout=2):
    """等待跨线程结果，并在超时后报告断言失败"""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("异步结果未在时限内出现")


class FakeDevice:
    def __init__(self):
        """保存实际发送的短文本，不模拟内部实现"""
        self.writes = []
        self.closed = False

    def show(self, text):
        """记录设备输出"""
        self.writes.append(text)

    def close(self):
        """记录句柄已释放"""
        self.closed = True


class ProtocolTests(unittest.TestCase):
    def test_wire_format(self):
        """核对带 Report ID 的协议字节和 UTF-8 内容"""
        data = "歌词🎵".encode()
        report = encode_report("歌词🎵")
        self.assertEqual(len(report), 64)
        self.assertEqual(
            report[:11],
            bytes([0xBC, 0xAA, 1, 0, 4 + len(data), 0, 2, 0x0B, 1, 5, len(data)]),
        )
        self.assertEqual(report[11 : 11 + len(data)], data)
        self.assertEqual(report[11 + len(data) :], bytes(53 - len(data)))

    def test_empty_exits_lyric_mode(self):
        """空文字必须发送退出命令而不是开启空白页"""
        self.assertEqual(encode_report("")[:11], bytes([0xBC, 0xAA, 1, 0, 4, 0, 2, 0x0B, 0, 0, 0]))

    def test_capacity(self):
        """按字节限制容量，拒绝截断和无效 Unicode"""
        self.assertEqual(len(encode_report("a" * 52)), 64)
        for text in ["a" * 53, "中" * 18, "\ud800"]:
            with self.assertRaises(ValueError):
                encode_report(text)


class ServiceTests(unittest.TestCase):
    def test_clear_and_shutdown_release(self):
        """收到清屏后释放设备，退出时也清屏释放"""
        devices = []

        def create():
            """记录工作线程新开的设备实例"""
            device = FakeDevice()
            devices.append(device)
            return device

        service = BridgeService(create)
        try:
            service.submit("第一句")
            eventually(lambda: devices and devices[0].writes == ["第一句"])
            service.submit("")
            eventually(lambda: devices[0].closed)
            self.assertEqual(devices[0].writes[-1], "")
            service.submit("第二句")
            eventually(lambda: len(devices) == 2 and devices[1].writes)
        finally:
            service.stop()
        self.assertTrue(devices[-1].closed)
        self.assertEqual(devices[-1].writes[-1], "")

    def test_stalled_writer_keeps_only_latest(self):
        """慢写入期间抛弃中间页，防止歌词队列积压"""
        entered, release = threading.Event(), threading.Event()
        device = FakeDevice()
        original = device.show

        def blocked(text):
            """仅阻塞第一条写入，模拟慢 USB"""
            if text == "第一句":
                entered.set()
                release.wait(2)
            original(text)

        device.show = blocked
        service = BridgeService(lambda: device)
        try:
            service.submit("第一句")
            self.assertTrue(entered.wait(1))
            service.submit("过期句")
            service.submit("最新句")
            release.set()
            eventually(lambda: len(device.writes) == 2)
            self.assertEqual(device.writes, ["第一句", "最新句"])
        finally:
            release.set()
            service.stop()

    def test_lease_expiry(self):
        """插件停止续期后自动清屏，不长久持有设备"""
        device = FakeDevice()
        with patch("splayerec.service.LEASE_SECONDS", 0.2):
            service = BridgeService(lambda: device)
            try:
                service.submit("即将失联")
                eventually(lambda: device.closed)
                self.assertEqual(device.writes, ["即将失联", ""])
                self.assertFalse(service.snapshot()["active"])
            finally:
                service.stop()

    def test_reconnect_recovers_latest(self):
        """设备掉线后重连只显示最新内容"""
        device = FakeDevice()
        attempts = []

        def create():
            """第一次模拟设备未插入"""
            attempts.append(True)
            if len(attempts) == 1:
                raise OSError("设备未连接")
            return device

        service = BridgeService(create)
        try:
            service.submit("旧句")
            eventually(lambda: service.snapshot()["state"] == "disconnected")
            service.submit("重连后最新句")
            eventually(lambda: bool(device.writes), timeout=3)
            self.assertEqual(device.writes, ["重连后最新句"])
        finally:
            service.stop()


class HTTPTests(unittest.TestCase):
    def setUp(self):
        """使用随机回环端口运行真实 HTTP 接口"""
        self.device = FakeDevice()
        self.service = BridgeService(lambda: self.device)
        self.shutdown_event = threading.Event()
        self.server = start_server(self.service, port=0, shutdown_event=self.shutdown_event)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        """关闭监听并释放工作线程"""
        self.server.shutdown()
        self.server.server_close()
        self.service.stop()

    def request(self, body, headers=None):
        """通过真实连接发起请求并保留错误状态"""
        request = urllib.request.Request(
            self.base + "/v1/display",
            body,
            {"Content-Type": "application/json", **(headers or {})},
        )
        try:
            return urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as response:
            return response

    def test_post_and_health(self):
        """真实 JSON 请求应到达设备并更新状态"""
        with self.request(json.dumps({"text": "真实接口测试"}).encode()) as response:
            self.assertEqual(response.status, 200)
            self.assertTrue(json.load(response)["ok"])
        eventually(lambda: self.device.writes == ["真实接口测试"])
        with urllib.request.urlopen(self.base + "/health") as response:
            data = json.load(response)
        self.assertEqual(data["app"], "SPlayerEC")
        self.assertEqual(data["state"], "connected")
        self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))

    def test_reject_cross_site(self):
        """拒绝浏览器 Origin、错误 Host 和表单提交"""
        for headers, status in [
            ({"Origin": "https://example.com"}, 403),
            ({"Origin": "null"}, 403),
            ({"Host": "example.com"}, 403),
            ({"Content-Type": "text/plain"}, 415),
        ]:
            with self.request(b'{"text":"blocked"}', headers) as response:
                self.assertEqual(response.status, status)
        self.assertEqual(self.device.writes, [])

    def test_reject_invalid_and_oversize(self):
        """无效正文和超容量文字不能到达设备"""
        for body, status in [
            (b"{}", 400),
            (b"[]", 400),
            (b"{", 400),
            (b"x" * 4097, 413),
            (json.dumps({"text": "a" * 53}).encode(), 400),
        ]:
            with self.request(body) as response:
                self.assertEqual(response.status, status)
        self.assertEqual(self.device.writes, [])

    def test_shutdown_request(self):
        """退出请求只通知主循环，交由主循环清屏和释放设备"""
        request = urllib.request.Request(
            self.base + "/v1/shutdown",
            b'{"action":"exit"}',
            {"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            self.assertEqual(response.status, 200)
        self.assertTrue(self.shutdown_event.wait(1))


if __name__ == "__main__":
    unittest.main()

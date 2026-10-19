# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (C) 2026 LiteZero

"""只监听本机的短报文 HTTP 接口"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import __version__

PORT = 19620


class BridgeHTTPServer(HTTPServer):
    allow_reuse_address = False

    def get_request(self):
        """限制单个客户端占用读取连接的时间"""
        connection, address = super().get_request()
        connection.settimeout(2)
        return connection, address


def start_server(service, port=PORT, shutdown_event=None):
    """在回环地址启动接口，端口冲突时立即报错"""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            """关闭逐请求日志，避免心跳产生持续磁盘写入"""

        def reply(self, status, body):
            """返回短 JSON 响应并关闭连接"""
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(data)
            except BrokenPipeError, ConnectionResetError:
                pass

        def do_GET(self):
            """提供本机诊断状态，不向浏览器开放跨域权限"""
            if self.path != "/health":
                self.reply(404, {"error": "接口不存在"})
                return
            self.reply(200, {"app": "SPlayerEC", "version": __version__, **service.snapshot()})

        def do_POST(self):
            """接收插件发送的一页 UTF-8 文字并拒绝浏览器跨站请求"""
            if (
                self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}"
                or self.headers.get("Origin") is not None
            ):
                self.reply(403, {"error": "仅允许本机插件请求"})
                return
            if self.path not in ("/v1/display", "/v1/shutdown"):
                self.reply(404, {"error": "接口不存在"})
                return
            if self.headers.get_content_type() != "application/json" or self.headers.get(
                "Transfer-Encoding"
            ):
                self.reply(415, {"error": "需要定长 JSON 请求"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096:
                    self.reply(413, {"error": "请求大小必须为 1–4096 字节"})
                    return
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("请求正文不完整")
                data = json.loads(raw.decode("utf-8"))
                if self.path == "/v1/shutdown":
                    if shutdown_event is None or data != {"action": "exit"}:
                        raise ValueError("无效的退出请求")
                    self.reply(200, {"ok": True})
                    shutdown_event.set()
                    return
                if not isinstance(data, dict) or not isinstance(data.get("text"), str):
                    raise TypeError("缺少 text 字符串")
                service.submit(data["text"])
            except (ValueError, TypeError) as error:
                self.reply(400, {"error": str(error)})
                return
            self.reply(200, {"ok": True, "state": service.snapshot()["state"]})

    server = BridgeHTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, name="k20gt-http", daemon=True)
    thread.start()
    return server

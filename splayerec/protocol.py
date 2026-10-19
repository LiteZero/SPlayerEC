# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (C) 2026 LiteZero

"""K20 GT 普通歌词报文，仅控制文字显示"""

REPORT_ID = 0xBC
MAX_TEXT_BYTES = 52


def encode_report(text: str) -> bytes:
    """编码包含 Report ID 的 64 字节输出报文，空文字表示清屏"""
    data = text.encode("utf-8", errors="strict")
    if len(data) > MAX_TEXT_BYTES:
        raise ValueError("单页文字不能超过 52 个 UTF-8 字节")
    report = bytearray(64)
    report[:11] = bytes(
        [
            REPORT_ID,
            0xAA,
            1,
            0,
            4 + len(data),
            0,
            2,
            0x0B,
            int(bool(text)),
            5 if text else 0,
            len(data),
        ]
    )
    report[11 : 11 + len(data)] = data
    return bytes(report)

# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (C) 2026 LiteZero

"""使用 Windows 自带 HID 接口，不依赖驱动替换或外部 DLL"""

import ctypes as c
from ctypes import wintypes as w

from .protocol import encode_report


class GUID(c.Structure):
    _fields_ = [("a", w.DWORD), ("b", w.WORD), ("d", w.WORD), ("e", c.c_ubyte * 8)]


class Interface(c.Structure):
    _fields_ = [
        ("size", w.DWORD),
        ("guid", GUID),
        ("flags", w.DWORD),
        ("reserved", c.c_void_p),
    ]


class Attributes(c.Structure):
    _fields_ = [
        ("size", w.DWORD),
        ("vendor", w.WORD),
        ("product", w.WORD),
        ("version", w.WORD),
    ]


class Caps(c.Structure):
    _fields_ = [
        ("usage", w.WORD),
        ("page", w.WORD),
        ("input", w.WORD),
        ("output", w.WORD),
        ("feature", w.WORD),
        ("reserved", w.WORD * 17),
        ("links", w.WORD),
        ("input_buttons", w.WORD),
        ("input_values", w.WORD),
        ("input_indices", w.WORD),
        ("output_buttons", w.WORD),
        ("output_values", w.WORD),
        ("output_indices", w.WORD),
        ("feature_buttons", w.WORD),
        ("feature_values", w.WORD),
        ("feature_indices", w.WORD),
    ]


class Overlapped(c.Structure):
    _fields_ = [
        ("internal", c.c_size_t),
        ("internal_high", c.c_size_t),
        ("offset", w.DWORD),
        ("offset_high", w.DWORD),
        ("event", w.HANDLE),
    ]


def bind(dll, name, result, *args):
    """绑定系统函数签名，避免 64 位句柄被截断"""
    function = getattr(dll, name)
    function.restype, function.argtypes = result, list(args)
    return function


class WindowsHID:
    def __init__(self):
        """绑定设备枚举和可取消的异步写入接口"""
        kernel, hid, setup = [
            c.WinDLL(n, use_last_error=True) for n in ("kernel32", "hid", "setupapi")
        ]
        ptr = c.c_void_p
        self.guid = bind(hid, "HidD_GetHidGuid", None, c.POINTER(GUID))
        self.info = bind(
            setup, "SetupDiGetClassDevsW", ptr, c.POINTER(GUID), w.LPCWSTR, ptr, w.DWORD
        )
        self.enum = bind(
            setup,
            "SetupDiEnumDeviceInterfaces",
            w.BOOL,
            ptr,
            ptr,
            c.POINTER(GUID),
            w.DWORD,
            c.POINTER(Interface),
        )
        self.detail = bind(
            setup,
            "SetupDiGetDeviceInterfaceDetailW",
            w.BOOL,
            ptr,
            c.POINTER(Interface),
            ptr,
            w.DWORD,
            c.POINTER(w.DWORD),
            ptr,
        )
        self.destroy = bind(setup, "SetupDiDestroyDeviceInfoList", w.BOOL, ptr)
        self.open = bind(
            kernel,
            "CreateFileW",
            w.HANDLE,
            w.LPCWSTR,
            w.DWORD,
            w.DWORD,
            ptr,
            w.DWORD,
            w.DWORD,
            w.HANDLE,
        )
        self.close = bind(kernel, "CloseHandle", w.BOOL, w.HANDLE)
        self.attributes = bind(hid, "HidD_GetAttributes", w.BOOL, w.HANDLE, c.POINTER(Attributes))
        self.preparsed = bind(hid, "HidD_GetPreparsedData", w.BOOL, w.HANDLE, c.POINTER(ptr))
        self.free = bind(hid, "HidD_FreePreparsedData", w.BOOL, ptr)
        self.caps = bind(hid, "HidP_GetCaps", c.c_long, ptr, c.POINTER(Caps))
        self.event = bind(kernel, "CreateEventW", w.HANDLE, ptr, w.BOOL, w.BOOL, w.LPCWSTR)
        self.write = bind(
            kernel,
            "WriteFile",
            w.BOOL,
            w.HANDLE,
            ptr,
            w.DWORD,
            c.POINTER(w.DWORD),
            c.POINTER(Overlapped),
        )
        self.wait = bind(kernel, "WaitForSingleObject", w.DWORD, w.HANDLE, w.DWORD)
        self.result = bind(
            kernel,
            "GetOverlappedResult",
            w.BOOL,
            w.HANDLE,
            c.POINTER(Overlapped),
            c.POINTER(w.DWORD),
            w.BOOL,
        )
        self.cancel = bind(kernel, "CancelIoEx", w.BOOL, w.HANDLE, c.POINTER(Overlapped))
        self.invalid = c.c_void_p(-1).value

    def devices(self):
        """枚举目标 VID/PID 下的 64 字节读写控制接口"""
        guid = GUID()
        self.guid(c.byref(guid))
        info = self.info(c.byref(guid), None, None, 0x12)
        if info == self.invalid:
            raise c.WinError(c.get_last_error())
        found = []
        try:
            index = 0
            while True:
                interface = Interface()
                interface.size = c.sizeof(interface)
                if not self.enum(info, None, c.byref(guid), index, c.byref(interface)):
                    if c.get_last_error() != 259:
                        raise c.WinError(c.get_last_error())
                    break
                index += 1
                needed = w.DWORD()
                self.detail(info, c.byref(interface), None, 0, c.byref(needed), None)
                buffer = c.create_string_buffer(needed.value)
                c.cast(buffer, c.POINTER(w.DWORD))[0] = 8 if c.sizeof(c.c_void_p) == 8 else 6
                if not self.detail(
                    info, c.byref(interface), buffer, len(buffer), c.byref(needed), None
                ):
                    continue
                path = c.wstring_at(c.addressof(buffer) + 4)
                if "vid_3837&pid_60c6" not in path.lower():
                    continue
                handle = self.open(path, 0, 3, None, 3, 0, None)
                if handle == self.invalid:
                    continue
                try:
                    attr = Attributes()
                    attr.size = c.sizeof(attr)
                    if not self.attributes(handle, c.byref(attr)) or (
                        attr.vendor,
                        attr.product,
                    ) != (0x3837, 0x60C6):
                        continue
                    data, caps = c.c_void_p(), Caps()
                    if self.preparsed(handle, c.byref(data)):
                        try:
                            if (
                                self.caps(data, c.byref(caps)) >= 0
                                and caps.input == 64
                                and caps.output == 64
                            ):
                                found.append(
                                    {
                                        "path": path,
                                        "usage": caps.usage,
                                        "usage_page": caps.page,
                                    }
                                )
                        finally:
                            self.free(data)
                finally:
                    self.close(handle)
        finally:
            self.destroy(info)
        return found

    def write_report(self, handle, report: bytes):
        """在有限等待时间内写入报文，超时后取消并回收异步结构"""
        buffer = c.create_string_buffer(report, len(report))
        event = self.event(None, True, False, None)
        if not event:
            raise c.WinError(c.get_last_error())
        overlapped = Overlapped()
        overlapped.event = event
        count = w.DWORD()
        pending = False
        try:
            if not self.write(handle, buffer, len(report), c.byref(count), c.byref(overlapped)):
                error = c.get_last_error()
                if error != 997:
                    raise c.WinError(error)
                pending = True
                if self.wait(event, 1000) != 0:
                    raise TimeoutError("K20 GT 写入超时")
                if not self.result(handle, c.byref(overlapped), c.byref(count), False):
                    raise c.WinError(c.get_last_error())
                pending = False
            if count.value != len(report):
                raise OSError("K20 GT 写入不完整")
        finally:
            if pending:
                self.cancel(handle, c.byref(overlapped))
                self.result(handle, c.byref(overlapped), c.byref(count), True)
            self.close(event)


class K20GT:
    def __init__(self):
        """打开唯一的目标音箱控制接口，避免误选其他设备"""
        self.api = WindowsHID()
        devices = self.api.devices()
        if not devices:
            raise OSError("未检测到 K20 GT，请检查 USB 连接")
        if len(devices) != 1:
            raise OSError("检测到多个 K20 GT 控制接口，请只连接一台音箱")
        self.handle = self.api.open(devices[0]["path"], 0x40000000, 3, None, 3, 0x40000000, None)
        if self.handle == self.api.invalid:
            raise c.WinError(c.get_last_error())

    def show(self, text: str):
        """显示一页文字，空文字退出歌词通道"""
        self.api.write_report(self.handle, encode_report(text))

    def close(self):
        """关闭当前设备句柄"""
        if self.handle is not None:
            self.api.close(self.handle)
            self.handle = None

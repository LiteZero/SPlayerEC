# SPDX-License-Identifier: LGPL-3.0-or-later
# Copyright (C) 2026 LiteZero

"""构建独立可执行文件、便携包和当前用户安装包"""

import hashlib
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION = "1.0.1"


def main():
    """验证源码后打包，并输出可校验的交付文件"""
    subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(["node", "--test", "tests/plugin.test.cjs"], cwd=ROOT, check=True)
    tools = ROOT / "tools"
    tools.mkdir(exist_ok=True)
    nsis = tools / "nsis"
    compiler = nsis / "Bin" / "makensis.exe"
    if not compiler.exists():
        archive = tools / "nsis.7z"
        if not archive.exists():
            urllib.request.urlretrieve(
                "https://github.com/electron-userland/electron-builder-binaries/releases/download/nsis-3.0.4.1/nsis-3.0.4.1.7z",
                archive,
            )
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        if checksum != "9877df902530f96357d13a7a31ae2b9df67f48b11ffc9a1700a7c961574ec5fa":
            raise RuntimeError("NSIS 下载校验失败，请删除 tools/nsis.7z 后重试")
        nsis.mkdir(exist_ok=True)
        subprocess.run(
            [r"C:\Windows\System32\tar.exe", "-xf", str(archive), "-C", str(nsis)],
            check=True,
        )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            "--name",
            "SPlayerEC-Bridge",
            "--distpath",
            str(ROOT / "build" / "exe"),
            "--workpath",
            str(ROOT / "build" / "pyinstaller"),
            "--specpath",
            str(ROOT / "build"),
            "--hidden-import",
            "pystray._win32",
            "--exclude-module",
            "numpy",
            "--exclude-module",
            "matplotlib",
            "--exclude-module",
            "PIL.ImageQt",
            str(ROOT / "bridge.py"),
        ],
        cwd=ROOT,
        check=True,
    )
    dist = ROOT / "dist"
    portable = dist / f"SPlayerEC-{VERSION}-portable"
    portable.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "build" / "exe" / "SPlayerEC-Bridge.exe", portable)
    for name in [
        "README.md",
        "LICENSE",
        "COPYING",
        "COPYING.LESSER",
        "THIRD_PARTY_NOTICES.md",
        "VALIDATION.md",
    ]:
        shutil.copy2(ROOT / name, portable)
    shutil.copytree(ROOT / "licenses", portable / "licenses", dirs_exist_ok=True)
    (portable / "plugin").mkdir(exist_ok=True)
    shutil.copy2(ROOT / "plugin" / "k20gt-lyrics.js", portable / "plugin")
    source_zip = portable / f"SPlayerEC-{VERSION}-source.zip"
    with zipfile.ZipFile(source_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for name in ["splayerec", "plugin", "tests", "scripts", "installer", "licenses", ".github"]:
            for path in (ROOT / name).rglob("*"):
                if (
                    path.is_file()
                    and "__pycache__" not in path.parts
                    and not path.name.endswith("-smoke.json")
                ):
                    archive.write(path, path.relative_to(ROOT))
        for name in [
            "bridge.py",
            "requirements.txt",
            "requirements-build.txt",
            "README.md",
            "LICENSE",
            "COPYING",
            "COPYING.LESSER",
            "THIRD_PARTY_NOTICES.md",
            "VALIDATION.md",
            "pyproject.toml",
            ".gitignore",
            ".gitattributes",
        ]:
            archive.write(ROOT / name, name)
    subprocess.run(
        [str(compiler), "/INPUTCHARSET", "UTF8", str(ROOT / "installer" / "setup.nsi")],
        cwd=ROOT / "installer",
        check=True,
    )
    portable_zip = dist / f"SPlayerEC-{VERSION}-x64-portable.zip"
    with zipfile.ZipFile(portable_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in portable.rglob("*"):
            if path.is_file():
                archive.write(path, Path("SPlayerEC") / path.relative_to(portable))
    files = [
        dist / f"SPlayerEC-{VERSION}-x64-setup.exe",
        portable_zip,
    ]
    (dist / "SHA256SUMS.txt").write_text(
        "\n".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(dist).as_posix()}"
            for path in files
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print("交付文件已生成到", dist)


if __name__ == "__main__":
    main()

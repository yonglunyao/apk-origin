#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""APK Origin Verify Toolkit 环境自检（只读，无副作用，不依赖环境变量）"""
import os
import subprocess
import sys
from pathlib import Path


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        out = (r.stdout + r.stderr).strip().splitlines()
        return r.returncode == 0, out[0] if out else ""
    except Exception as e:
        return False, str(e)


def main():
    plugin_root = Path(__file__).resolve().parents[1]
    bin_dir = plugin_root / "bin"
    jadx_dir = bin_dir / "jadx-1.5.5"
    bt_dir = bin_dir / "build-tools"

    print("=" * 62)
    print(" APK Origin Verify Toolkit - 环境自检")
    print(" 插件目录: " + str(plugin_root))
    print("=" * 62)

    checks = []

    # 环境依赖（用户需提供）
    ok, v = run(["java", "-version"])
    checks.append(("Java (jadx 依赖)", ok, v or "未找到，安装 JRE 11+ https://adoptium.net/"))
    ok, v = run([sys.executable, "--version"])
    checks.append(("Python", ok, v))

    # 插件内置 jadx
    jadx_jar = jadx_dir / "lib" / "jadx-1.5.5-all.jar"
    jadx_bat = jadx_dir / "bin" / "jadx.bat"
    checks.append(("插件内置 jadx.jar", jadx_jar.is_file(), str(jadx_jar)))
    checks.append(("插件内置 jadx.bat", jadx_bat.is_file(), str(jadx_bat)))

    # 插件内置 build-tools
    checks.append(("插件内置 aapt.exe", (bt_dir / "aapt.exe").is_file(), str(bt_dir / "aapt.exe")))
    checks.append(("插件内置 apksigner.bat", (bt_dir / "apksigner.bat").is_file(), str(bt_dir / "apksigner.bat")))
    checks.append(("插件内置 apksigner.jar", (bt_dir / "lib" / "apksigner.jar").is_file(),
                   str(bt_dir / "lib" / "apksigner.jar")))
    checks.append(("插件内置 dexdump.exe", (bt_dir / "dexdump.exe").is_file(), str(bt_dir / "dexdump.exe")))
    dlls = ["libLLVM_android.dll", "libclang_android.dll", "libbcc.dll", "libbcinfo.dll", "libwinpthread-1.dll"]
    missing_dll = [d for d in dlls if not (bt_dir / d).is_file()]
    checks.append(("插件内置 runtime dll (5个)", not missing_dll,
                   "完整" if not missing_dll else "缺失: " + ",".join(missing_dll)))

    # 插件内置 ndk-tools（.so 符号/字符串分析，Flutter libapp.so 必需）
    ndk_dir = bin_dir / "ndk-tools"
    ndk_tools = ["readelf.exe", "nm.exe", "strings.exe", "objdump.exe"]
    missing_ndk = [t for t in ndk_tools if not (ndk_dir / t).is_file()]
    checks.append(("插件内置 ndk-tools (.so 分析)", not missing_ndk,
                   "完整" if not missing_ndk else "缺失: " + ",".join(missing_ndk)))

    # jadx 实际可执行（验证 Java 能驱动插件内置 jadx）
    ok, v = run([str(jadx_bat), "--version"])
    checks.append(("jadx 可执行性", ok, v or "执行失败（检查 Java 是否安装）"))

    # 联网 MCP（插件 .mcp.json，需填 API key；非阻塞）
    mcp_cfg = plugin_root / ".mcp.json"
    placeholders = mcp_cfg.read_text(encoding="utf-8").count("<YOUR_") if mcp_cfg.is_file() else -1
    if placeholders == 0:
        mcp_detail = ".mcp.json 所有 key 已填"
    elif placeholders > 0:
        mcp_detail = f".mcp.json 还有 {placeholders} 个 <YOUR_xxx_KEY> 待填"
    else:
        mcp_detail = ".mcp.json 不存在"
    checks.append(("联网 MCP key (可选, 非阻塞)", placeholders == 0, mcp_detail))

    all_ok = True
    for name, ok, detail in checks:
        optional = "可选" in name
        mark = "!" if (not ok and optional) else ("[OK]" if ok else "[X]")
        if not ok and not optional:
            all_ok = False
        print(f" {mark} {name}: {detail}")
    print("=" * 62)
    if all_ok:
        print(" 全部核心依赖就绪（插件内置工具 + Java/Python 环境）")
        print(" 调用: /apk-origin:verify <apk目录>")
    else:
        print(" 部分核心依赖缺失，请检查插件 bin/ 完整性与 Java 安装")
        sys.exit(1)


if __name__ == "__main__":
    main()

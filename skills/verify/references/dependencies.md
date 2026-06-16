# 依赖清单

verify 依赖的外部工具、MCP 服务、Skills 完整列表及获取方式。

---

## 1. MCP 工具

### 1.1 jadx CLI（插件已内置，无需 MCP）

**用途**：Phase 0 统一反编译 APK → Java 源码，供全部 Agent 共享 grep/read。

**插件内置**：`bin/jadx-1.5.5/`（`lib/jadx-1.5.5-all.jar` 61M + POSIX 启动脚本）。session 临时加入 PATH 即用（见 SKILL.md 工具段）。

> 不依赖 jadx MCP。P1 Agent 直接 grep Phase 0 已生成的 `.java` 源码，**禁止再次反编译**。jadx MCP 仅在需要交叉引用/类继承链等复杂场景时可选增强，非必需。

---

### 1.2 联网搜索 / 网页读取 / GitHub 读取 MCP（必需 — P0 阶段）

**用途**：威胁情报查询、应用画像搜索、开发者身份交叉验证、域名 whois、网页/GitHub 详情读取。

插件 `.mcp.json` 已配置以下 MCP，需填入对应 API key（将 `<YOUR_xxx_KEY>` 替换为真实密钥）：

| MCP | 工具 | 用途 | API key |
|-----|------|------|---------|
| `google-search` | `mcp__google-search__google_search` | **主搜索**（英文优先） | GEMINI_API_KEY |
| `WebSearch` | `mcp__WebSearch__bailian_web_search` | 中文补充搜索 | DASHSCOPE_API_KEY |
| `web-reader` | `mcp__web-reader__webReader` | 网页正文读取 | ZHIPUAI_API_KEY |
| `zread` | `mcp__zread__read_file` / `search_doc` | GitHub 仓库读取（开发者身份验证） | ZHIPUAI_API_KEY |

**使用优先级**：google-search（英文）→ WebSearch（中文补充）；网页详情用 web-reader；GitHub 用 zread。

> 任一搜索 MCP 未配置 key 时 Agent A/I 联网降级，代码层分析不受影响。

---

### 1.3 frida-mobile-mcp（可选 — 插件已配置）

**用途**：动态运行时验证（hook 网络层、method channel、加密 API）。

**插件配置**：`.mcp.json` 已用 `npx frida-mobile-mcp` 配置（npx 自动拉取，无需 `npm install -g`）。仅报告中给出动态验证建议时使用，不是分析流程必需步骤。

---

## 2. Skill 依赖（可选辅助，插件未打包）

### 2.1 jadx Skill / 2.2 mobile-security Skill

**说明**：原 skill 设计提及的 `jadx` / `mobile-security` 辅助 skill **插件未打包**（提供完整 jadx 工作流 checklist、smali/Frida bypass 等）。本插件的核心提取与分析已由 `apk_extract.py` + 内置 `jadx` CLI + `ndk-tools` 自包含覆盖，不依赖这两个 skill。

如需增强，用户可自行安装到 `~/.claude/skills/`，Agent 按需调用。

---

## 3. 平台工具

### 3.1 Android Build-Tools（插件已内置 — apksigner / aapt / aapt2 / dexdump）

**用途**：apk_extract.py 内部调用 `apksigner`（签名证书）和 `aapt`（Manifest 组件、元信息）。

**插件内置**：`bin/build-tools/`（Windows 原生，52M）。`apk_extract.py` 的 `find_build_tools` 自动向上查找定位，**无需配置环境变量**。

**macOS/Linux**：`bin/build-tools/` 为 Windows 原生二进制不可用，需用本机 Android SDK build-tools 替换该目录内容，或设 `ANDROID_BUILD_TOOLS` 环境变量指向本机 SDK（apk_extract.py 的 fallback）。

---

### 3.2 readelf / nm / strings / objdump（P1 阶段）—— 插件已内置

**用途**：Agent E 分析 native .so 符号表和字符串（Flutter `libapp.so` 必需）。

**插件内置**：`bin/ndk-tools/`（来源 Android NDK llvm 工具：`readelf.exe` / `nm.exe` / `strings.exe` / `objdump.exe` + `libwinpthread-1.dll`，共 ~43M）。session 临时加入 PATH 即用：

    export PATH="$PLUGIN_ROOT/bin/ndk-tools:$PATH"

**说明**：
- `apk_extract.py` 已内置二进制字符串扫描（替代 `strings` 做基础 URL/IP 提取）
- `readelf`/`nm` 符号表分析无 Python 替代，必须用本工具
- 仅 Windows（macOS/Linux 用本机 NDK 的 llvm 工具或系统 binutils）

---

### 3.3 Python 3（必需）

**用途**：运行 `scripts/apk_extract.py` 提取 APK 结构化数据。

**版本要求**：Python ≥ 3.8（仅使用 stdlib：argparse, json, os, re, subprocess, zipfile, pathlib）。

---

## 4. 依赖检查命令速查

```bash
# MCP 工具
jadx --version                          # jadx 反编译器
grep jadx ~/.claude.json               # jadx MCP server 是否配置

# 平台工具
apksigner --version                     # Android 签名验证
aapt version                            # Android 资源解析
python3 --version                       # Python 运行环境
readelf --version 2>/dev/null || echo "需安装 Android NDK"
nm --version 2>/dev/null || echo "需安装 Android NDK"

# 可选
frida --version                         # Frida 动态分析（报告建议时使用）
```

---

## 5. 依赖可用性速查表

| 阶段 | 依赖 | 必需性 | 无它时的影响 |
|------|------|--------|-------------|
| Phase 0 | apksigner + aapt | 必需 | 无法提取证书/组件/元信息，skill 完全不可用 |
| Phase 0 | Python 3 | 必需 | 无法运行 apk_extract.py |
| P0 | WebSearch MCP | 必需 | Agent A/B/I 无法做开发者身份/域名/舆情交叉验证 |
| P1 | jadx CLI 输出（共享） | 必需 | Agent D/E/F/G/H 无法做代码层注入/安全机制/核心逻辑分析 |
| P1 | readelf/nm/strings | 按需 | Agent E 无法对比 .so 符号表，仅比存在性 |
| 报告 | frida-mobile-mcp | 可选 | 报告中无法自动做动态验证，仅给出文字建议 |

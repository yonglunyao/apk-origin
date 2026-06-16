# APK Origin

> 开箱即用的 APK 跨渠道来源一致性核查：判断 AppGallery 与 Google Play 两个渠道的 APK 是否同源，检测仿冒 / 重打包 / 后门注入。

内置 **jadx CLI** + **Android build-tools（apksigner/aapt）**，通过**相对路径直接调用，不修改任何环境变量**。装好 Java + Python 即可用。

---

## 快速开始（Windows）

### 1. 安装插件

**方式 A — 从 GitHub 安装**（已含 `.claude-plugin/marketplace.json`，支持 marketplace 安装）：

```bash
# 在 Claude Code 内（替换 yonglunyao 为实际仓库 owner）
/plugin marketplace add yonglunyao/apk-origin
/plugin install apk-origin@apk-origin-market

# 或命令行
claude plugin marketplace add yonglunyao/apk-origin
claude plugin install apk-origin@apk-origin-market
```

> 部署前：把 `.claude-plugin/plugin.json`、`.claude-plugin/marketplace.json` 里的 `yonglunyao` 替换为实际 GitHub 用户名，push 到 GitHub。

**方式 B — 本地加载**（开发/测试）：

```bash
claude --plugin-dir D:/temp/apk-analyse/apk-origin
```

### 2. 自检（确认 Java/Python + 内置工具完整）

```bash
python D:/temp/apk-analyse/apk-origin/scripts/doctor.py
```

无需配置环境变量——`apk_extract.py` 自动定位插件内置 build-tools，jadx 通过插件相对路径调用。

### 3. 配置 MCP API key

插件 `.mcp.json` 已配置联网 MCP，需填入对应 API key（将 `<YOUR_xxx_KEY>` 替换为真实密钥）：

| MCP | 用途 | key 获取 |
|-----|------|---------|
| google-search | 主搜索（英文） | https://aistudio.google.com/apikey |
| WebSearch（百炼） | 中文补充 | https://bailian.console.aliyun.com |
| web-reader + zread | 网页 / GitHub 读取（共用智谱 key） | https://open.bigmodel.cn |

未配置时 Agent A/I 联网降级，代码层分析不受影响。

### 4. 使用

```
/apk-origin:verify D:\path\to\apks\<package>
```

输入目录含两个 APK：`ag-<package>.apk`（AppGallery）和 `gp-<package>.apk` 或 `gp-<package>/`（Google Play，支持 split APK 目录）。

---

## 工作流

```
Phase 0  反编译（jadx CLI 统一反编译，4 进程并行）
   ↓
P0  关键信号（4 Agent 并行：B 网络端点 / A 证书身份 / C Manifest / I 舆情）
   ↓
P1  结构分析（5 Agent 并行：D 入口注入 / E .so / F 敏感值 / G 安全机制 / H 核心逻辑）
   ↓
S   汇总判定 → Q 规范性校验（不通过自动修正一轮）
   ↓
报告 results/<包名>_<日期>/<包名>_同源核查报告.md
```

判定：任一 P0 红旗 → 不同源/仿冒（高）；P0 全过 + P1 红旗 → 疑似篡改（中）；全通过 → 同源（高）。

---

## 插件结构

```
apk-origin/
├── .claude-plugin/plugin.json     插件清单（name: apk-origin）
├── skills/verify/      核心分析 skill（SKILL.md + references + apk_extract.py）
├── bin/
│   ├── jadx-1.5.5/                jadx CLI（61M，Java 跨平台）
│   ├── build-tools/               Android 关键工具（52M，Windows 原生）
│   │   ├── aapt.exe / aapt2.exe / dexdump.exe
│   │   ├── apksigner.bat + lib/apksigner.jar
│   │   └── *.dll（LLVM/clang 运行时）
│   └── ndk-tools/                 readelf/nm/strings/objdump（43M，.so 分析，Flutter 必需）
├── .mcp.json                      MCP 配置（API key 占位符，需填入）
├── scripts/doctor.py              只读自检（不写环境变量）
└── README.md
```

---

## 设计原则：零环境变量污染

- **jadx**：skill 通过插件相对路径 `<插件根>/bin/jadx-1.5.5/bin/jadx.bat` 调用，**不加入 PATH**
- **aapt/apksigner**：`apk_extract.py` 自动向上查找 `<插件根>/bin/build-tools`，**不设 ANDROID_BUILD_TOOLS**
- **MCP**：`.mcp.json` 已含配置骨架，API key 用 `<YOUR_xxx_KEY>` 占位，填入即可；工具路径完全不碰环境变量

skill base 目录（SKILL.md 所在目录）上溯两级即插件根，所有工具路径由此推算。

---

## 依赖

### 已内置（无需另装）
- jadx CLI 1.5.5、apksigner、aapt、aapt2、dexdump
- readelf / nm / strings / objdump（LLVM，Native .so 符号/字符串分析，Flutter `libapp.so` 必需）

### 需用户提供
- **Java 11+**（jadx 运行依赖）：[adoptium.net](https://adoptium.net/)
- **Python 3.8+**：运行 apk_extract.py / doctor.py

### 联网 MCP（`.mcp.json` 已配置，需填 API key）

| MCP | 用途 | API key |
|-----|------|---------|
| `google-search` | 主搜索（英文优先） | GEMINI_API_KEY |
| `WebSearch`（百炼） | 中文补充搜索 | DASHSCOPE_API_KEY |
| `web-reader` | 网页正文读取 | ZHIPUAI_API_KEY |
| `zread` | GitHub 仓库读取 | ZHIPUAI_API_KEY |
| `frida-mobile-mcp` | 动态验证（可选） | npx 自取 |

### 未内置说明
- **jadx / mobile-security skill**：原 skill 文档提及的辅助 skill 当前系统无源，未打包；apk_extract.py 已自包含核心提取能力。
- **readelf / nm / strings**：apk_extract.py 内置二进制扫描替代，非必需。

---

## 平台限制

本插件**全量打包为 Windows 开箱**：aapt/aapt2/dexdump/dll 为 Windows 原生二进制。jadx（Java）/ apksigner（Java）天然跨平台。

macOS/Linux 需用本机 build-tools 替换 `bin/build-tools/` 内容，或保留 `ANDROID_BUILD_TOOLS` 环境变量指向本机 SDK（apk_extract.py 的 fallback）。

---

## 排障

```bash
python scripts/doctor.py          # 只读自检
```

- jadx/apksigner/aapt 全部插件内置，**不依赖 PATH，无需 setx**
- Java 未找到 → 安装 JRE 11+
- MCP 搜索不工作 → 在 `.mcp.json` 填入对应 API key（替换 `<YOUR_xxx_KEY>`）

---

## 打包分发

```bash
cd D:/temp/apk-analyse
Compress-Archive -Path apk-origin -DestinationPath apk-origin.zip
```

体积约 156M（含 jadx + build-tools + ndk-tools 二进制）。

---

## 版本

- v1.0.0：首发。9 Agent（B/A/C/I/D/E/F/G/H）+ S 汇总 + Q 规范校验，P0→P1 两阶段并行工作流，零环境变量设计。

## License

MIT

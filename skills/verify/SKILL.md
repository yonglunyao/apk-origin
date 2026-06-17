---
name: verify
description: "Compare two APKs from different distribution channels (AppGallery vs Google Play) to determine if they share the same origin. Agent-driven multi-phase parallel analysis — Phase 0 unified decompile → P0 + P1 parallel agents (up to 10 concurrent) → final verdict. All phases execute fully, jadx output shared across agents to avoid redundant decompilation. Use when: judging if two APKs are from the same developer, detecting repackaging/backdoor injection, verifying an AppGallery APK against a Google Play trusted copy, or any cross-channel APK provenance question."
---

# APK 跨渠道来源一致性核查

## 核心原则

- **目标**：逐项排除不同源/仿冒/后门注入的证据，不是证明同源
- **最高信号**：网络端点差异（不同后端域名 = 不同代码源，接近铁证）
- **分层递进**：P0 → P1 逐层深入，全部执行完毕后才汇总判定
- **一次反编译**：Phase 0 用 jadx CLI 统一反编译，P1 的 Agent 禁止再次调用 jadx 反编译，只 grep/read 已有 `.java` 源码
- **并行约束**：每层并行 Agent ≤ 10 个
- **⚠️ 必须用 Task 工具启动 subagent**：P0/P1/Q 的每个 Agent 都是一次独立的 Task 工具调用（`subagent_type="general-purpose"`），同层多个 Agent 放在**同一条消息**里并行启动。**主 agent 只负责编排（启动 subagent、收集结果、汇总报告），禁止自己顺序执行分析维度**——这是本 skill 的核心架构，违反会导致失去并行加速和上下文隔离。S（汇总）由主 agent 自己做（已持有全部 subagent 输出）。
- **⚠️ subagent 上下文隔离**：每个 subagent 是全新上下文，不读 SKILL.md，主 agent 的 `export PATH` 也**不跨 subagent 进程**。因此启动依赖插件内置工具的 subagent（**主要是 Agent E 用 ndk-tools**）前，主 agent 必须在该 subagent 的 prompt 顶部注入「插件根目录：<PLUGIN_ROOT 绝对路径>」（替换 `{plugin_root}` 变量），让 subagent 自己 export PATH 定位 `bin/ndk-tools`。
- **按需深入**：Agent 以 apk_extract.py JSON 为基线，自主决定是否调用 jadx/readelf/WebSearch 深入
- **临时文件集中管理**：所有分析产物必须写入 `results/<应用名>_<日期>/`，禁止散落到项目根目录

## 输出目录规范

每次分析必须创建独立的工作目录，所有中间产物和最终报告集中存放：

```
results/<应用名>_<YYYYMMDD>/
├── ag.json                  # apk_extract.py AG 输出
├── gp.json                  # apk_extract.py GP 输出
├── jadx/                    # jadx 反编译输出（按需）
│   ├── ag/
│   └── gp/
├── temp/                    # 临时文件（.so提取、证书dump等）
└── <包名>_同源核查报告.md  # 最终报告
```

**规则**：
- Phase 0 开始前先创建 `results/<应用名>_<YYYYMMDD>/` 目录
- `ag.json` / `gp.json` 写入该目录，禁止写项目根目录
- jadx 反编译指定输出到 `results/<应用名>_<YYYYMMDD>/jadx/`
- 任何临时解包/提取操作使用 `results/<应用名>_<YYYYMMDD>/temp/`
- 最终报告命名为 `<包名>_同源核查报告.md` 写入该目录
- 禁止在项目根目录创建 `temp_*`、`*.json`、`*.log` 等散落文件

## 前置依赖

本插件**已内置 jadx CLI 和 Android build-tools（apksigner/aapt/dexdump）**，通过相对路径直接调用，无需配置环境变量或另装逆向工具链。运行仅需：

- **Java 11+**（jadx 运行依赖；如未安装：[adoptium.net](https://adoptium.net/)）
- **Python 3.8+**（运行 apk_extract.py）
- **可选**：联网 MCP（插件 `.mcp.json` 已配置 google-search / WebSearch / web-reader / zread，需填入对应 API key；详见 `references/dependencies.md` 1.2 节）

工具路径（无需环境变量）：skill base（本 SKILL.md 所在目录）上溯两级即插件根，jadx 在 `<插件根>/bin/jadx-1.5.5/bin/`，aapt/apksigner 由 apk_extract.py 自动定位 `<插件根>/bin/build-tools`。自检：`python <插件根>/scripts/doctor.py`

## 工作流

### Phase 0：数据提取 + 反编译（前置，~2分钟）

**目录命名**：以 AG APK 所在目录名为 `<应用名>`（如 `apks/com.dlabs.mosaicwallet` → 目录名 `com.dlabs.mosaicwallet`）。

**缓存检查**：若 `results/<应用名>_<YYYYMMDD>/ag.json` 存在且其修改时间晚于对应 APK 文件，则跳过提取直接使用缓存。jadx 输出同理。

**无缓存时执行（全部并行）**：

```bash
# 工具路径（插件内置，session 临时 PATH，不写用户环境变量）
PLUGIN_ROOT="$(cd "<skill_base>/../.." && pwd)"   # skill base = 本 SKILL.md 所在目录，插件根 = 上溯两级
export PATH="$PLUGIN_ROOT/bin/jadx-1.5.5/bin:$PLUGIN_ROOT/bin/ndk-tools:$PATH"
# → 该 Bash 内 jadx/readelf/nm/strings/objdump 直接可用；aapt/apksigner 由 apk_extract.py 自动定位

mkdir -p results/<应用名>_<YYYYMMDD>/jadx/ag results/<应用名>_<YYYYMMDD>/jadx/gp

# 以下 4 个命令互不依赖，全部后台并行
python <skill_base>/scripts/apk_extract.py <ag_apk_or_dir> -o results/<应用名>_<YYYYMMDD>/ag.json &
python <skill_base>/scripts/apk_extract.py <gp_apk_or_dir> -o results/<应用名>_<YYYYMMDD>/gp.json &
jadx --no-res --deobf <ag_apk_or_dir> -d results/<应用名>_<YYYYMMDD>/jadx/ag &
jadx --no-res --deobf <gp_apk_or_dir> -d results/<应用名>_<YYYYMMDD>/jadx/gp &
wait   # 等全部完成再继续
```

- 4 个进程并行而非两段 `wait`，总时间由最慢的一个决定（~2 分钟 vs 旧方案 3 分钟）
- `--no-res`：跳过资源（仅代码，快 3-5 倍）。**疑似品牌冒充/钓鱼界面时去掉 `--no-res` 纳入资源对比**
- `--deobf`：反混淆，使类名/方法名可读
- 如果逐条在终端执行（非脚本），用 `jobs` 检查后台任务而非 `wait`

**输出结构**：

```
results/<应用名>_<YYYYMMDD>/
├── ag.json / gp.json         # apk_extract.py 输出
├── jadx/
│   ├── ag/sources/           # AG Java 源码（所有 Agent 共享读取）
│   └── gp/sources/           # GP Java 源码
└── temp/                     # 临时文件
```

- apk_extract.py 输出字段：`.meta`、`.certs`、`.components`、`.files`、`.strings`（含 `.urls`、`.ips`、`.secrets`）
- 需要 Android build-tools（apksigner/aapt）

**变量提取与注入**（启动 subagent 前替换 `{变量}`）：

主 agent 在 Phase 0 已算出 `PLUGIN_ROOT`（插件根绝对路径）。启动每个 subagent 前：① 用下面命令从 ag.json/gp.json 提取各 {变量} 值填入 prompt；② **Agent E** 还须在 prompt 顶部注入「插件根目录：<PLUGIN_ROOT>」（替换 `{plugin_root}`），否则它无法定位 ndk-tools。

```bash
# 通用 dump（按需切片填入各 {变量}）
python -c "import json,pprint; d=json.load(open('results/<应用名>_<YYYYMMDD>/ag.json')); pprint.pprint(d)"
# 常用字段（certs/cert_dn/label/urls/ips/secrets/libs/package/strings）
python -c "import json; d=json.load(open('results/<应用名>_<YYYYMMDD>/ag.json')); print('certs:',d['certs'],'| cert_dn:',d['certs']['cert_dn'],'| label:',d['meta']['label'])"
python -c "import json; d=json.load(open('results/<应用名>_<YYYYMMDD>/ag.json')); print('urls:',d['strings']['urls'],'| ips:',d['strings']['ips'],'| secrets:',d['strings'].get('secrets'))"
python -c "import json; d=json.load(open('results/<应用名>_<YYYYMMDD>/ag.json')); print('libs:',d['files']['libs'],'| package:',d['meta']['package'],'| components:',d['components'])"
```
GP 侧同理（换 gp.json）。Agent I 纯 WebSearch，但需 `{ag_cert_dn}` / `{ag_label}` / `{package_name}` 三个字段。

### P0：关键信号（4 个并行 subagent，~2分钟）

> ⚠️ **强制：必须用 Task 工具启动 subagent，禁止主 agent 自己顺序执行**。在**同一条消息**里发起 4 个 Task 工具调用（`subagent_type="general-purpose"`），每个调用的 `prompt` 参数 = 对应 Agent 的完整 prompt。4 个 subagent **并行**执行。并行 subagent 是本 skill 的核心设计（隔离上下文 / 并行 4 倍加速 / 防止主 agent 上下文污染），主 agent 自己顺序做这 4 个维度会违背设计且慢 4 倍——**不要这样做**。

每个 subagent 的 `prompt` = 从 `references/agent-prompts.md` 复制对应 `## Agent X` 段全文（替换 {变量} 后）传入。

| Agent | subagent 职责 | 关键输入 | prompt 来源 |
|-------|---------------|---------|-----------|
| B | 网络端点差异 | ag/gp.json `.strings` | `## Agent B` |
| A | 开发者身份与证书 | ag/gp.json `.certs` | `## Agent A` |
| C | Manifest 高危差异 | ag/gp.json `.meta`+`.components` | `## Agent C` |
| I | 网络情报交叉验证 | WebSearch | `## Agent I` |

**一条消息内 4 个 Task 工具调用并行**（每个的 prompt = 对应 Agent 完整模板）：

- Task(subagent_type="general-purpose", description="Agent B 网络端点", prompt=<Agent B 模板>)
- Task(subagent_type="general-purpose", description="Agent A 证书身份", prompt=<Agent A 模板>)
- Task(subagent_type="general-purpose", description="Agent C Manifest", prompt=<Agent C 模板>)
- Task(subagent_type="general-purpose", description="Agent I 网络情报", prompt=<Agent I 模板>)

P0 完成后继续执行 P1，不做提前终止。**每阶段完成后向用户汇报该阶段所有 Agent 的结论摘要。**

### P1：结构分析（5 个并行 subagent，~2分钟）

P0 完成后无论结果如何均继续执行。> ⚠️ **同样强制用 Task 工具**：在**同一条消息**里发 5 个 Task 工具调用（`subagent_type="general-purpose"`），5 个 subagent 并行。**禁止主 agent 自己顺序做**（理由同 P0）。

| Agent | subagent 职责 | 关键工具 | prompt 来源 |
|-------|---------------|---------|-----------|
| D | 入口点注入检测 | grep/jadx 源码（Phase 0 共享） | `## Agent D` |
| E | Native .so 差异 | readelf/strings | `## Agent E` |
| F | 硬编码敏感值 | grep/jadx 源码 + apk_extract.py | `## Agent F` |
| G | 安全机制对比 | grep/jadx 源码 | `## Agent G` |
| H | 核心安全逻辑 | grep/jadx 源码 | `## Agent H` |

**一条消息内 5 个 Task 工具调用并行**（每个的 prompt = 对应 Agent 完整模板）：

- Task(subagent_type="general-purpose", description="Agent D 入口点", prompt=<Agent D 模板>)
- Task(subagent_type="general-purpose", description="Agent E .so", prompt=<Agent E 模板>)
- Task(subagent_type="general-purpose", description="Agent F 敏感值", prompt=<Agent F 模板>)
- Task(subagent_type="general-purpose", description="Agent G 安全机制", prompt=<Agent G 模板>)
- Task(subagent_type="general-purpose", description="Agent H 核心逻辑", prompt=<Agent H 模板>)

P1 完成后直接进入 S 汇总判定。**无 P2 阶段**（原 P2 仅剩 H，已并入 P1）。

### S：汇总判定

**主 agent 汇总**（不需要 Task subagent——主 agent 已持有 P0/P1 全部 9 个 subagent 的输出）：按决策规则判定，按 `references/report-template.md` 结构输出完整 Markdown 报告，保存到 `results/<应用名>_<YYYYMMDD>/<包名>_同源核查报告.md`。汇总时参照 `references/agent-prompts.md` 的 `## Agent S` 模板（冲突裁决、场景分析等）。

### Q：报告规范性校验（1 个 Task subagent）

> ⚠️ **强制用 Task 工具启动 Q subagent**（`subagent_type="general-purpose"`），不要主 agent 自己跳过校验。Q 用 Read 工具读取报告，对照 `references/report-template.md` 逐项校验结构 / 格式 / 必备要素（**不评判同源结论**）。详细 checklist 见 `references/agent-prompts.md` 的 `## Agent Q`。

- Task(subagent_type="general-purpose", description="Agent Q 报告校验", prompt=<Agent Q 模板，替换 {report_path} 为 `results/<应用名>_<YYYYMMDD>/<包名>_同源核查报告.md`>)

**Q 判定与修正循环（最多 1 轮）**：

| Q 判定 | 处理 |
|--------|------|
| 通过 | 工作流结束，向用户汇报最终结论 |
| 需修正 | 将 Q 输出的 fatal_issues / important_issues 的 `fix_instruction` 反馈给 **主 agent（即 S 阶段的执行者）**，主 agent 用 Edit **仅修改报告不符合项**（保留已正确内容，不重写全文、不再起 subagent）→ 再启动 Q subagent 复检 |
| 复检仍不通过 | 接受当前报告，向用户汇报时标注剩余规范性问题 |

## 决策规则

```
任一 P0 Agent (B|A|C|I) 红旗       → 不同源/仿冒 (置信度:高)
P0 全通过, P1 (D|E|F|G|H) 任一红旗 → 疑似篡改 (置信度:中)
全通过                                → 同源 (置信度:高)（附带静态盲区声明 + 动态验证建议）
```

**加密货币/金融应用 Agent I 升级**：当应用为钱包、交易所、DeFi 时：
- 执法部门查封（FBI/DOJ/SEC）→ 直接判"不同源/仿冒"（置信度：高），不依赖其他维度
- 多起诈骗/杀猪盘投诉且模式一致 → 与 P0 其他红旗等效

### Agent 意见冲突处理

当同一 Agent 在不同运行中给出不同结论时（如 Agent A 第一次判红旗、第二次判一致），由 Agent S 根据**证据坚实度**裁决：
- 有公开可查证据（证书身份链、FBI 查封记录等）→ 采信证据更强的结论
- 无证据的推断（如"可能是子公司/外包商"）→ 不采信，标注"无证据支撑"
- 裁决结果在报告中单列一段说明分歧和取舍理由

## 报告输出

Agent S 按 `references/report-template.md` 结构输出完整 Markdown 报告，**保存到 `results/<应用名>_<YYYYMMDD>/<包名>_同源核查报告.md`**。**核心原则：所有 AG vs GP 对比信息优先使用表格呈现，避免纯列表形式。**

报告包含：结论摘要（判定+应用画像+证据矩阵）→ 关键信号(P0) → 结构分析(P1)  综合研判 → 建议措施 → 残余风险 → 元数据 → 附录A（分析方法）

## 关键陷阱

调用各 Agent 前，确保它们理解以下陷阱（详见 `references/signing-traps.md`）：

- **GP App Signing**：GP 包常由 Google 重签名（DN=`CN=Android, O=Google Inc.`），证书不同不必然不同源
- **华为 AppGallery 重签名**：AG 包也可能被华为重签名（DN=`CN=App Gallery, O=Huawei Software Technologies`），需识别双平台重签名场景
- **版本不同 → 哈希必不同**：只比符号/字符串/结构，不比 DEX/.so 哈希
- **Split APK**：GP 可能是 base+config.* split，apk_extract.py 传目录自动合并
- **Flutter/RN**：Dart 逻辑在 libapp.so，JS 在 assets bundle，DEX 字符串为空是正常的
- **AG 证书 DN 不可作为身份依据**：证书中的人名/公司名可任意填写且未经验证（尤其海外应用），开发者身份以 GP/App Store 的企业验证信息为准
- **无官方基准**：非开源/无公开发布时，签名为相对比较，网络端点/代码结构成为主力

## 工具

**插件内置（相对路径直调，无需环境变量）**：每个 Bash 调用开头先定位插件根并临时加入 PATH（env 不跨 Bash 调用，故每次需重设；此为 session 临时变量，不写用户环境）：

```bash
PLUGIN_ROOT="$(cd "<skill_base>/../.." && pwd)"   # skill base = 本 SKILL.md 所在目录，插件根 = 上溯两级
export PATH="$PLUGIN_ROOT/bin/jadx-1.5.5/bin:$PLUGIN_ROOT/bin/ndk-tools:$PATH"
```

此后该 Bash 内 `jadx` / `readelf` / `nm` / `strings` / `objdump` 直接可用（jadx 在所有平台都通过 POSIX 启动脚本调用，裸 `jadx` 即可）。

- `scripts/apk_extract.py` — APK 结构化数据提取（JSON）；自动定位 `<插件根>/bin/build-tools`，aapt/apksigner 无需 PATH
- `bin/jadx-1.5.5/` — jadx CLI（Phase 0 统一反编译，P1 Agent grep/read 已有源码）
- `bin/build-tools/` — apksigner、aapt、aapt2、dexdump（apk_extract.py 自动调用）
- `bin/ndk-tools/` — readelf、nm、strings、objdump（LLVM，Native .so 符号/字符串分析，Flutter `libapp.so` 必需）
- Bash (grep/read) — P1 代码搜索（共享 Phase 0 jadx 输出）
- 联网 MCP（`.mcp.json` 已配置，需填 API key）：google-search（主，英文）/ WebSearch（中文补充）/ web-reader（网页正文）/ zread（GitHub 仓库）— 威胁情报、应用画像、开发者身份验证
- frida-mobile-mcp — 可选动态验证（报告中建议时使用）

## 参考文档

- `references/agent-prompts.md` — 各 Agent 完整 prompt 模板（启动 Agent 时使用）
- `references/report-template.md` — 报告输出模板（Agent S 输出格式）
- `references/red-flags.md` — 各维度红旗判定标准
- `references/signing-traps.md` — 签名与构建常见陷阱
- `references/dependencies.md` — 依赖清单与获取方式（MCP/平台工具/Python）

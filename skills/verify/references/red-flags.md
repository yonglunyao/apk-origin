# 红旗判定标准

每个分析维度的具体红旗条件，各 Agent 在分析时参照执行。

---

## A. 签名证书

**数据来源**：apk_extract.py → `ag.json /.certs`、`gp.json /.certs`

**红旗**：
- AG 证书自签且 DN 异常（个人名/壳公司/与官方品牌不符）
- AG 证书 ≠ 官方公开证书（对照 VirusTotal 上传 GP 包反查、官网下载包、GitHub Release）
- 证书有效期异常（超长/已过期后重新签发）
- 仅 v1 签名（现代应用应有 v2/v3）

**注意**：
- GP App Signing：Google 重签名后 DN=`CN=Android, O=Google Inc.`，AG≠GP 证书是常态
- AG 证书反而更接近开发者原始密钥 → 优先对照 AG 证书 vs 官方公开证书
- **DN 异常不可单独定红旗**：AG 证书 DN 可任意填写且未经第三方验证（尤其海外应用），「自签/DN 异常」仅在已通过 GP/App Store 确认开发者身份后作为佐证，不单独触发红旗。详见 signing-traps.md §7

---

## B. 网络端点

**数据来源**：apk_extract.py → `ag.json /.strings`、`gp.json /.strings`（已扫 DEX+.so+assets bundle）

**红旗**：
- **AG 独有不明域名**（最高优先级）
- AG 独有裸 IP 地址
- AG 独有动态域名 / 短链服务 / .cn .ru 或小国 TLD
- AG 独有 pastebin / telegram api / google docs 链接（常作 C2）
- 硬编码 AWS/GCP 凭证串、JWT、私钥头 `-----BEGIN`

**过滤**：googleapis、gstatic、flutter.dev、dart.dev、schema.org 等框架域名已自动排除

---

## C. Manifest 权限/组件

**数据来源**：apk_extract.py → `ag.json /.meta`、`ag.json /.components`

**高危权限红旗**（AG 独有）：
- READ_SMS / SEND_SMS / RECEIVE_SMS — 验证码拦截
- BIND_ACCESSIBILITY_SERVICE — 无障碍劫持
- INSTALL_PACKAGES / REQUEST_INSTALL_PACKAGES — 静默安装
- SYSTEM_ALERT_WINDOW — 悬浮窗钓鱼
- 后台定位 / 录音 / 拍照相关

**组件红旗**：
- 额外 `exported="true"` 的 Activity/Service/Receiver（无权限保护）
- 额外的 `<provider>` 或自定义 deep scheme
- **注意**：排除框架组件 `io.flutter.embedding.android.*`、`com.facebook.react.*`

**元信息红旗**：
- debuggable=true 的发布包
- minSdk 相邻小版本跳动（28↔30）无法用版本时间线解释
- versionName 相同但 versionCode 倒挂

---

## D. 入口点注入

**数据来源**：jadx CLI 反编译输出（Phase 0 共享）→ Application 子类 + 主 Activity

**红旗**：
- AG 的 `Application.onCreate()` / `attachBaseContext()` 多了 Service 启动
- AG 多了动态广播注册（`registerReceiver`）
- AG 多了 `DexClassLoader` / `PathClassLoader` 动态加载
- AG 多了 `System.loadLibrary` 加载未知 .so
- AG 多了新的 Application 子类（GP 无此子类）

---

## E. Native .so

**数据来源**：apk_extract.py → `ag.json /.files.libs`、`gp.json /.files.libs` + `readelf`/`strings`

**红旗**：
- AG 独有 .so 且内部字符串出现不明 URL/IP/命令
- AG 同名 .so 多出导出函数（init/decode/send/upload 类）
- AG 缺少关键加密 .so（librsa_bridge / libcrypto / libwallet / libsecp256k1）
- **不比哈希**：版本不同哈希必不同

---

## F. 硬编码敏感值

**数据来源**：apk_extract.py → `ag.json /.strings` + jadx 验证上下文

**红旗**：
- AG 独有 API key / OAuth secret / JWT secret
- AG 独有数据库连接串 / 云服务凭证
- AG 独有私钥头（`-----BEGIN RSA PRIVATE KEY-----`）
- AG 换了上报 key（Firebase/Amplitude/Sentry 等分析 SDK 的 key 不同）

**注意**：渠道差异可能合法换了分析 SDK key，需 jadx 验证上下文

---

## G. 安全机制

**数据来源**：jadx CLI 反编译输出（Phase 0 共享）→ 关键字搜索

**红旗**：
- AG 缺少 root 检测（`RootBeer`/`su`/`Magisk` 检测）
- AG 缺少模拟器检测（`isEmulator`/`qemu`/`goldfish`）
- AG 缺少 Frida hook 检测（`frida`/端口 27042）
- AG 缺少 SSL pinning（`TrustManager`/`CertificatePinner`/`OkHttp`）
- **一方有、另一方无 → 仿冒者可能故意移除以降低分析门槛**

---

## H. 核心安全逻辑（钱包/金融）

**数据来源**：jadx CLI 反编译输出（Phase 0 共享）→ 核心类定位

**红旗**：
- 助记词熵源被改为固定/弱随机（`SecureRandom` → `Random`）
- 种子/私钥外传逻辑（网络层发送种子字符串）
- 私钥存储路径/加密方式被简化
- 助记词导入/导出逻辑中多了不明网络调用
- Flutter 应用：需对 `libapp.so` 做字符串/符号分析

---

## I. 网络情报与舆情

**数据来源**：Google Search（优先英文）/ WebSearch → 应用画像、执法记录、诈骗投诉、监管牌照、用户评价

**红旗**：
- **执法部门查封/起诉**（FBI / DOJ / SEC / CFTC）→ 红旗，**独立触发「不同源/仿冒」（置信度:高）**，不依赖其他维度
- **多起模式一致的诈骗/杀猪盘投诉**（投诉数量多、手法相同、损失可追溯）→ 红旗，与 P0 其他红旗等效
- 应用被多家威胁情报厂商标记为恶意/仿冒（VirusTotal / ScamAdviser / 多源一致）

**可解释（不触发红旗）**：
- 单条或零星用户投诉、客服响应慢、低分评价
- 第三方冒充该应用品牌的钓鱼（外部攻击者行为，非应用本身）
- 已公开披露并修复的历史漏洞

**注意**：Agent I 的 `risk_level` 高 且 命中执法查封 → verdict 视为红旗；普通负面舆情为「有负面情报(可解释)」

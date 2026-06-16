# 签名与构建陷阱

跨渠道比对中最容易误判的几个坑，各 Agent 必须了解。

---

## 1. Google Play App Signing

启用 App Signing 的应用，Google 用自己的密钥重签名 GP 包：
- GP 包证书 DN 常为 `CN=Android, O=Google Inc.`（非开发者）
- AppGallery 通常保留开发者上传的原始密钥
- **AG≠GP 证书不必然不同源**，这是常态
- AG 证书反而更接近开发者原始签名 → 作为官方基准对照

**判定**：不要因 AG≠GP 证书判不同源。要对照 AG 证书 vs 公开官方证书/第三方情报。

> **实例**：Mosaic Wallet（`com.dlabs.mosaicwallet`）AG 证书 `O=Dynamic Laboratories`，GP 证书 `CN=Android, O=Google Inc.`。若只看 GP≠AG 证书则误判不同源。实际 AG 证书 `Dynamic Laboratories` = `Dlabs Kft.`（匈牙利），与 Google 确认的官方开发者一致。

---

## 2. 华为 AppGallery 平台重签名

华为应用市场也会对上传的 APK 进行重签名：
- AG 证书 DN 可能出现 `CN=App Gallery, O=Huawei Software Technologies Co., Ltd, C=China`
- 与 Google App Signing 机制类似，开发者原始密钥被平台证书替换
- **AG 证书 ≠ GP 证书时可能双方都被平台重签名**，开发者原始证书在任一 APK 中均不可见

**判定**：当两个渠道证书都不是开发者原始密钥时（双平台重签名），证书比对完全失效。必须通过开发者身份确认（Agent A WebSearch）+ 代码层（Agent B/C/D/F）判断同源性。

> **实例**：Klever Wallet（`finance.klever.bitcoin.wallet`）AG 证书为 `CN=App Gallery, O=Huawei Software Technologies`，GP 证书为 `CN=Android, O=Google Inc.`。双方都是平台重签名，开发者原始密钥不可见。最终通过 Agent A 确认 Klever Exchange 为官方开发者，Agent B/D/F 确认代码一致，判定同源。

### 双平台重签名场景识别

| AG 证书 DN | GP 证书 DN | 场景 | 处理 |
|-----------|-----------|------|------|
| 开发者密钥 | Google Inc. | 标准 GP App Signing | AG 证书为基准 |
| Huawei Software Technologies | Google Inc. | **双平台重签名** | 证书比对失效，依赖开发者身份 + 代码层 |
| 开发者密钥 | 开发者密钥 | 无平台重签名 | 直接比对证书 |
| Huawei Software Technologies | 开发者密钥 | 仅 AG 重签名 | GP 证书为基准 |

---

## 3. 版本不同 → 哈希必不同

不同 versionCode 的构建，classes.dex / .so 字节必然不同：
- ❌ 用 classes.dex SHA-256 或 .so SHA-256 判"魔改"→ 必然假阳
- ✅ 比符号表 / 字符串 / 结构相似度
- 只有**同一 versionCode** 且签名一致时，逐字节哈希才有意义

---

## 4. Split APK 结构

Google Play 用 App Bundle 拆成 base + config.{abi/locale/density}：
- base.apk：classes.dex + AndroidManifest，**无 .so**
- config.arm64_v8a.apk：lib/arm64-v8a/*.so
- AppGallery 通常是含全部 ABI/资源的 universal 单包

**陷阱**：只比 base 会误判"GP 缺 .so/缺资源"
**解决**：apk_extract.py 传目录路径时自动合并 base+splits

---

## 5. Flutter / React Native

- Flutter：Dart 代码编译进 `libapp.so`；classes.dex 只是引擎桥接壳
- RN：JS bundle 在 `assets/index.android.bundle`
- DEX 字符串几乎为空是**正常的**
- **必须扫 libapp.so / assets bundle 才能抓到业务 URL/IP**
- apk_extract.py 自动扫 .so + assets/*.bundle + assets/*.hbc

---

## 6. 资源混淆

R8 resource shrinking / AndResGuard 把资源重命名（如 `res/M9.png`）：
- 一方开了、另一方没开 → 图标/资源路径不同，**正常**
- 不等于代码不同

---

## 7. 证书开发者身份不可验证

Android 签名证书中的身份信息（DN 字段）**可以任意填写，没有第三方验证机制**：
- 证书 `CN=Ivan Galkin, O=FinFlow, C=RU` 完全可以由任意人/组织生成
- 华为应用市场对海外开发者**没有能力核实**证书中的开发者身份是否真实
- 证书声称的公司名、人名、地址可能全部是伪造的
- Apple App Store / Google Play 有 DUNS 等企业验证流程，华为应用市场对海外应用**没有同等机制**

**身份来源可信度对照**：

| 来源 | 验证机制 | 可信度 | Agent A 用法 |
|------|---------|--------|-------------|
| Google Play 开发者名称 | Google 企业验证 | ✅ 高 | **作为开发者身份基准** |
| Apple App Store Seller | DUNS 企业验证 | ✅ 高 | **作为开发者身份基准** |
| AG 证书 DN | 无 | ❌ 不可采信 | 不作为身份判断依据 |
| AG 页面开发者名 | 无（海外应用） | ❌ 不可采信 | 仅供参考 |

**结论**：Agent A 的核心任务不是"比对证书"，而是**以 GP/App Store 的已验证开发者身份为基准，对照 AG APK 的代码/行为是否符合这一定位**。证书 DN 本身不作为开发者身份证据——它只是签名密钥的标记，而密钥可以被任何人持有。

> 这种限制意味着代码层（Agent B/C/D/F）才是同源判定的**真正主力**。Agent A 的作用从"裁决者"降级为"佐证来源"——它可以提供强信号（如 FBI 查封 + 证书不匹配），但不能单独定论。

## 8. 无官方基准时
- 无法获"官方证书"基准
- 签名降级为相对比较（AG vs GP），不能单独定论
- 网络端点/代码结构/核心逻辑成为同源判定的真正主力
- 任何一处未解释的核心差异都不能判同源

> **实例**：Iron Wallet（`com.wallet.crypto.btc.eth`）非开源，官网不提供 APK 下载。AG 证书 `CN=Ivan Galkin, O=FinFlow` 与 GP 证书 `CN=Android, O=Google Inc.`。无官方证书基准，Agent A 通过 WebSearch 多次搜索 Ivan Galkin/FinFlow 与 INWAY AG 的关系均无公开关联，最终裁决「无证据支撑的推断不被采信」，判红旗。

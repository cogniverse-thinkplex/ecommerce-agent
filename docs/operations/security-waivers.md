# 安全扫描豁免

安全扫描默认严格失败。下列条目是经过依赖解析验证、具有复查期限的临时豁免，不代表漏洞已修复。

## CVE-2026-114603 — opentelemetry-api 1.44.0

- 记录日期：2026-10-27
- 到期复查：2026-11-27
- 当前影响：生产依赖树由 LiteLLM/遥测组件引入 `opentelemetry-api 1.44.0`。
- 阻塞原因：修复版为 1.45.1；tau2 的 `livekit-agents` 可选依赖当前限定 `<1.45`。uv 对项目全部 extras 的解析证明直接提升到 1.45.1 无解。
- 缓解措施：应用不接收或解析外部 OpenTelemetry 配置，不对公网暴露遥测接收端点；容器以非 root、只读文件系统运行。
- 解除条件：LiveKit 依赖放宽到 `opentelemetry-api>=1.45.1`，或将语音 extras 从生产包彻底拆分后，删除 `scripts/security_scan.sh` 中对应 `--ignore-vuln` 并重新锁定依赖。


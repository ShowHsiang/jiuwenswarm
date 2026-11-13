---
id: S_01_runtime-monitor
title: 原生主 Agent Runtime Memory 与 BAI 应用契约
type: S
author: ShowHsiang
author_email: xiangxiaoneng@h-partners.com
modules:
  - jiuwenswarm/server/runtime/agent_adapter
  - jiuwenswarm/common
  - jiuwenswarm/server/runtime/session
  - jiuwenswarm/channels/web/frontend
files:
  - jiuwenswarm/server/runtime/agent_adapter/runtime_monitor.py
  - jiuwenswarm/server/runtime/agent_adapter/interface_deep.py
  - jiuwenswarm/common/browser_settings.py
  - jiuwenswarm/resources/config.yaml
  - jiuwenswarm/server/runtime/session/session_history.py
  - jiuwenswarm/channels/web/frontend/src/features/runtimeMonitorNotices.ts
---

# Runtime Memory 与 BAI 应用契约

## 边界与唯一入口

SDK 的 ReAct/RuntimeMonitor 负责步骤、证据、收益窗口、触发、建议及效果。应用只在 JiuWenSwarmDeepAdapter 的 create/reload/cleanup 装配一个主 Agent monitor，并投影 SDK 通知；无独立执行循环。默认关闭，启用后默认 observe/JEV。active 才将建议送入下一次主模型请求；LLM 保留实际动作决策权。成本预测不实现，恢复层由独立实现以后对接。BACKTRACK 只是推理建议。

## 单一 JEV 配置来源

`execution_guard.runtime_monitor` 仅包含 enabled、mode、backend、parameters；额外字段严格拒绝。JEV 连接必须来自现有“设置 → 模型 → 决策模型”的 `browser.decision`，通过 common.browser_settings.resolve_jev_connection 解析；旧 runtime_monitor.jev 和 JEV_API_KEY 不再消费。

共享 provider/model/api_base/api_key_env，不共享浏览器模式、超时、重试和决策次数。TypeSafe/custom 使用 /systemone，OpenRouter 使用 /decisions；密钥由原配置服务保存，运行时按既有 crypto provider 解密。BAI 使用自身 A/B 超时、零客户端重试。LLM 后端借用当前主模型，不解析 JEV 连接、不关闭共享模型。

## 重载与资源

相同有效配置复用 client/window；浏览器模式/别名变动不触发重建。密钥轮换关闭旧客户端并重建，不重置评分 generation。JEV 模型或端点、BAI mode/backend 改变使 generation 失效重建。缺失共享密钥抛 MissingJevCredentialError（ValueError 子类）；首次创建不装配，已有绑定则解绑并关闭，避免清空密钥后继续消费缓存。其它无效重载保持旧绑定且只记录异常类型。参数关闭与 cleanup 幂等释放已拥有客户端。

## 传输与持久记录

`chat.runtime_monitor` 只含 schema_version、任务/generation 身份、窗口统计、步骤及最近建议摘要；不包含目标全文、参数、证据原文或密钥。`chat.notice` 使用 notice_type=runtime_intervention 和稳定 notice_id=generation:advice_id，展示原因、建议及状态。同一建议状态变化更新同一条系统提示；传输去重保留状态变化，历史还原最后状态。结构化诊断即使 content 为空也可落盘。

投影失败不改变执行结论，成功投递后才更新去重缓存；不提供 exactly-once 或恢复检查点。没有业务 EvidenceAdapter 的可信验收证明，verified_progress_count 保持 0。

## 验证入口

应用装配与闭环：tests/unit_tests/agentserver/test_runtime_monitor.py；共享连接/真实 HTTP 线格式/配置文件及密钥生命周期：test_runtime_monitor_config.py。共用设置还需 browser_decision_config、jev_model_clear、moa_config、moa_runtime 消费方回归。前端使用 test:runtime-monitor、test:jev-settings、test:subagent-history。环境和当前证据归档于 F_20261113_1109_runtime-bai-shared-jev；SDK 算法契约保留在 agent-core 的 S_02_runtime-monitor。

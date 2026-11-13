---
id: F_20261113_1109_runtime-bai-shared-jev
title: Runtime BAI 共用决策模型配置与双仓官方基线同步
type: F
author: ShowHsiang
author_email: xiangxiaoneng@h-partners.com
modules:
  - jiuwenswarm/server/runtime/agent_adapter
  - jiuwenswarm/common
  - jiuwenswarm/channels/web/frontend
files:
  - jiuwenswarm/server/runtime/agent_adapter/runtime_monitor.py
  - jiuwenswarm/common/browser_settings.py
  - jiuwenswarm/resources/config.yaml
  - tests/unit_tests/agentserver/test_runtime_monitor_config.py
  - tests/unit_tests/agentserver/test_runtime_monitor.py
  - tests/conftest.py
  - pyproject.toml
designs:
  - agent-core:D-20261029-1613-react-runtime-intervention
---

# Runtime BAI 共用决策模型配置与官方基线同步

## 依据与决策关系

续接已确认的 [SDK 设计](../../../../agent-core/.agents/agent-docs/designs/active/D-20261029-1613-react-runtime-intervention/design.md) 与 [SDK F 记忆](../../../../agent-core/.agents/agent-docs/features/F_20261111_1938_react-runtime-bai.md)。用户明确要求：应用 JEV 复用浏览器/前端决策模型配置；两个独立开发分支都要集成官方最新 develop；继续使用本地 SDK 联调。本记录维护应用侧新的实际决策，原文中的旧基线和独立 JEV 配置仅是历史事实。当前应用契约见 [S_01](../specs/runtime/S_01_runtime-monitor.md)。不重新设计 SDK 算法，不引入成本预测或恢复层。

## 基线与合并

SDK `react-runtime-bai` 合入官方 `openJiuwen/agent-core` develop `fbe6a0d903522712de8094bffd1017964280bdae`，合并提交 `ac1007990`。仅文档生成索引冲突，使用仓库脚本重建。

应用 `runtime-bai-adaptation` 从已推送 `b4a5cee3d` 保留历史，合入官方 `openJiuwen/jiuwenswarm` develop。最初取得 `4b7a8d3f9`，交付核对发现上游新增 `f5638897d03df426c82fd3a9e9417b59cde7f504`，通过合并提交 `298eb136e` 纳入该提交；初次合并提交为 `98ca3c7a1`。旧 Electron 能力已经在官方实现中演进，逐项审阅冲突后采用官方现行行为，保留 BAI 初始化/重载/清理、事件/历史及本地 SDK 增量。旧 browser_config 副本因全部调用方已迁移至 common 删除。

首次尝试批量选择上游冲突版本被自动审批拒绝；之后逐项读取差异与冲突，按已审阅范围解决，未绕过审批或强推历史。原未跟踪日志、搜索目录和 SDK 本地材料保留。

## 共享配置实现

直接复用 resolve_jev_connection，不再维护 RuntimeMonitor 的 JevSettings。TypeSafe/OpenRouter/custom 的模型、端点与密钥和前端设置一致；使用现有解密逻辑，不泄露原始密钥。浏览器模式与其预算不控制 BAI，LLM 替换接口不依赖 JEV。连接指纹仅为哈希；模型/端点变化刷新评分 generation，密钥轮换只更新 client。清空当前共享密钥关闭缓存 client 并解绑；其它无效重载保留有效旧状态。MissingJevCredentialError 继承 ValueError，现有消费者的异常契约兼容。

新增实际 HTTP MockTransport 测试核对三个 provider 的 URL/模型/认证及响应解码；配置测试走真实 ConfigAdapter 的 CONFIG_SAVE_ALL/PATH_SET，将一份配置和密钥保存到临时 YAML/.env，再由 BAI 消费。未连接真实 JEV 服务。

## 依赖与环境

保留 `../agent-core` editable，同时用 uv.override-dependencies 覆盖新 agent-gateway 的传递远端 SDK 钉。保留官方 filelock/protocol 约束。当前 Windows/Python 3.11 venv 按官方 lock 补入 Gateway、protocol、runtime-foundation、computeruse 和 JiuwenMemory；没有借机升级其它依赖。

完整 uv lock 仍不可解：应用要求 opentelemetry-sdk>=1.28.0,<1.42，而本地 SDK 要求 >=1.45.1。uv.lock 随官方 develop 更新，不是这组本地 SDK 的完整解析结果。仅可支持已验证的 editable 联调路径；干净环境、生产打包和全平台依赖安装未验证。

## 验证与收尾

SDK 相关回归 207 passed。前端 test:jev-settings 72 passed，test:runtime-monitor 4 passed，test:subagent-history 52 passed；只使用 esbuild/Node 行为测试，未运行格式化或静态检查。测试夹具补齐上游新增图标导出和 UTF-8 文件读取；JEV 替身先加载 SDK 类型契约，避免污染 MoA 的延迟导入类型检查。

应用扩展回归覆盖 RuntimeMonitor/共享 JEV/浏览器决策/MoA/配置服务/历史/热重载/上下文/A2X/Swarm 浏览器/Electron 契约共 **388 passed**，最终验证进程退出码 0。Windows 收尾发现应用 logger 恢复的文件 handler 不在 logging 的弱引用注册表内，shutdown 未关闭仍挂载的流；测试收尾显式移除/关闭该 logger 的 handler，随后 shutdown 并清理临时目录，完整范围复验通过。此前已知旧版路径大小写断言未在本轮重复计入成功范围。

未执行真实模型调用、完整浏览器端到端或全仓测试。配置/传输/生命周期、SDK 版本或共享决策模型协议变化需要重验；用户验收仍待后续实际使用反馈。


### 可复现验证范围

在激活应用 .venv 并设置 PYTHONPATH=仓库根、PYTHONDONTWRITEBYTECODE=1 后运行：

```powershell
python -m pytest tests/unit_tests/agentserver/test_runtime_monitor.py tests/unit_tests/agentserver/test_runtime_monitor_config.py tests/unit_tests/common/test_browser_decision_config.py tests/unit_tests/common/test_jev_model_clear.py tests/unit_tests/common/test_moa_config.py tests/unit_tests/common/test_moa_config_panel.py tests/unit_tests/agentserver/test_moa_runtime.py tests/unit_tests/test_session_history_empty_filter.py tests/unit_tests/agentserver/test_agent_reload_scope.py tests/unit_tests/agentserver/test_deep_adapter_runtime_config_timing.py tests/unit_tests/agentserver/test_context_engine_config_wiring.py tests/unit_tests/agentserver/test_a2x_client_init.py tests/agents/swarm/test_electron_browser_fallback.py tests/unit_tests/test_desktop_electron_contract.py -q -o addopts='' --asyncio-mode=auto -o log_cli=false --tb=short --show-capture=no --disable-warnings
```

前端目录依次运行 npm run test:jev-settings、npm run test:runtime-monitor、npm run test:subagent-history，合计 **128 passed**。测试中的 HTTP transport、JEV/LLM 响应和 UI 服务请求为可控替身；生产装配入口、请求编码、配置文件/.env 写入、历史写入与会话状态检查为真实代码。


### 交付前检视

只读检视限定本次共享配置增量及官方合并保留的 SDK 装配入口：核对 browser.decision 解析、前端配置服务写入、凭据清空与轮换、LLM 隔离、评分 generation、创建/重载/清理和事件投影。依据应用 S_01_runtime-monitor、SDK S_02_runtime-monitor 及现行配置契约，未发现该范围新的阻断问题。修正文档中可能被理解为运行时不读取配置的表述，并更新本地依赖注释；行为代码与上述通过测试的候选相同。全量依赖锁仍受上述 OpenTelemetry 约束冲突限制，不将定向回归视作安装或全应用端到端验收。交付前再次查询官方远端，两仓 develop SHA 与“基线与合并”所记一致。

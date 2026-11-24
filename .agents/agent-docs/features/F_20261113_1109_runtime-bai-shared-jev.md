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
  - jiuwenswarm/server/runtime/agent_adapter/runtime_file_evidence.py
  - jiuwenswarm/common/browser_settings.py
  - jiuwenswarm/resources/config.yaml
  - tests/unit_tests/agentserver/test_runtime_monitor_config.py
  - tests/unit_tests/agentserver/test_runtime_monitor.py
  - tests/conftest.py
  - jiuwenswarm/server/wire_truncate.py
  - pyproject.toml
designs:
  - agent-core:D-20261029-1613-react-runtime-intervention
---

# Runtime BAI 共用决策模型配置与官方基线同步

## 2026-11-24 原件适配与真实模型对照

测试工作区按已核对的工具结果摘要登记五份合成材料。对象、属性和版本用于关联副本，签署原件登记两项裁决权，清单内没有预置门位或封签答案。原生工具调用、失败回退和配置重载均由适配回归覆盖。两条既有会话回放及一次实时共享 JEV 试验在五步读取上均得到 `0,1,1,2,0`。SDK 修复记录为 `B_20261124_1538_runtime-evidence-disputes`。

通过测试网页的真实会话复验，串行读取时监控分别报告 0、1、1、2、0。四份副本并行读取再查阅原件时两轮分别报告 2、0，两项矛盾由同一批 JEV 识别。两种方式都触发 EVIDENCE_CONFLICT、送达 VERIFY 并记录 improved。真实共享 JEV 另以宿主签发的合成入库验收做探索基准，三份不同的低收益响应在第五轮只触发 LOW_GAIN_STREAK，收到签收单后连续计数归零。

WREN 轮询对照固定原用户问题、前四次工具响应及当时的五个 JEV 响应。从第五步起使用相同的真实主模型和只读工具，三组交替运行 observe/active。除干预消息外首次自由请求的消息摘要完全一致。observe 三次均在第七步取得签收单。active 分别在第七、第五、第五步取得，三次都实际送达建议。两组各三次均答对签收人和时间。此处结果限于这一任务和模型配置。

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
python -m pytest tests/unit_tests/agentserver/test_runtime_monitor.py tests/unit_tests/agentserver/test_runtime_monitor_config.py tests/unit_tests/common/test_browser_decision_config.py tests/unit_tests/common/test_jev_model_clear.py tests/unit_tests/common/test_moa_config.py tests/unit_tests/common/test_moa_config_panel.py tests/unit_tests/agentserver/test_moa_runtime.py tests/unit_tests/test_session_history_empty_filter.py tests/unit_tests/agentserver/test_agent_reload_scope.py tests/unit_tests/agentserver/test_deep_adapter_runtime_config_timing.py tests/unit_tests/agentserver/test_context_engine_config_wiring.py tests/unit_tests/agentserver/test_a2x_client_init.py tests/agents/swarm/test_electron_browser_fallback.py tests/unit_tests/test_desktop_electron_contract.py tests/unit_tests/test_history_replay.py tests/unit_tests/test_history_index_paging.py tests/unit_tests/test_history_review_regressions.py tests/unit_tests/agentserver/test_history_get_stream_split.py -q -o addopts='' --asyncio-mode=auto -o log_cli=false --tb=short --show-capture=no --disable-warnings
```

前端目录依次运行 npm run test:jev-settings、npm run test:runtime-monitor、npm run test:subagent-history，合计 **128 passed**。测试中的 HTTP transport、JEV/LLM 响应和 UI 服务请求为可控替身；生产装配入口、请求编码、配置文件/.env 写入、历史写入与会话状态检查为真实代码。


### 交付前检视

只读检视限定本次共享配置增量及官方合并保留的 SDK 装配入口：核对 browser.decision 解析、前端配置服务写入、凭据清空与轮换、LLM 隔离、评分 generation、创建/重载/清理和事件投影。依据应用 S_01_runtime-monitor、SDK S_02_runtime-monitor 及现行配置契约，未发现该范围新的阻断问题。修正文档中可能被理解为运行时不读取配置的表述，并更新本地依赖注释；行为代码与上述通过测试的候选相同。全量依赖锁仍受上述 OpenTelemetry 约束冲突限制，不将定向回归视作安装或全应用端到端验收。交付前再次查询官方远端，两仓 develop SHA 与“基线与合并”所记一致。


### 推送期间新增官方历史恢复更新

初次推送完成后的核对发现官方 develop 新增 9f403d1ca27cfb73a5521a7c7d7e1f517c0dc61d（会话历史恢复内存优化），已继续合入；本节记录取代前文 f5638897d 作为最终应用基线。此提交没有前端或依赖约束变化。核对自动合并后的 create/reload/cleanup、事件投影及历史写入，BAI 增量均保留。官方已有的上下文快照实现不等于本功能已实现恢复层，BAI 未接入恢复动作。

扩展读取链检视发现原适配只覆盖历史落盘，chat.notice 被共享的历史查询事件白名单过滤。JSONL 回归先重现查询结果为空；将 chat.notice 纳入共享白名单，使 Web/Control/旧 session handler 一致支持提示还原。真实历史 writer 加 index/cursor 分页验证同一建议 applied → improved 的稳定 ID、状态与顺序，旧 JSON 存储按既有契约验证 index 分页。chat.runtime_monitor 仍仅保留在诊断历史，原始诊断和提示均不作为主模型上下文恢复输入。已同步 S_01 与中英文接入说明。

在最终集成候选上运行上面的扩展命令，**500 passed，退出码 0**，包括 14 个原范围及 history_replay、history_index_paging、history_review_regressions、history_get_stream_split。SDK 207 与前端 128 的证据仍对应未变的相关代码。只读复查确认三个历史查询入口共用该事件集合；未新增 JEV 调用、成本预测或恢复动作。全量依赖锁限制保持不变。

## 2026-11-23 正式发布基线

用户选择以正式发布线为准并保留特性开发历史。应用使用官方 `releases/0.2.9` 的 `fdaec9d182fe2869dee9a37fec7893d13c1f2dee`，包含 `v0.2.9` 标签提交 `453dce3054babf7f3a7000c8e57e068de01d8d2e` 及其后的修复。依据此前 `9f403d1ca` 与特性分支 `23cbf6916` 的差异，将共享决策模型、原生主 Agent monitor、消息与历史、前端及回归用例三方移植至发布代码。原特性提交和发布提交作为合并双亲。测试清理沿用发布版日志句柄释放流程，在释放前停止后台日志。设置页 Node 夹具按发布组件的导入契约提供 i18n 初始化插件及 Vite DEV 值。

SDK 对应 `v0.1.21`（`102e69254`）。应用保留发布版 `openjiuwen==0.1.21`、extras 及其余依赖约束，在 `[tool.uv.sources]` 将 SDK 指向 `../agent-core`。`uv lock` 解析 336 个包，相对官方锁的包名和版本集合一致。`uv lock --check`、已有 `.venv` 的 `uv sync --locked`、全新临时 venv 的 `uv sync --locked --no-dev` 均通过。新环境从项目目录外导入应用适配器及 SDK monitor，验证 editable 导入路径为 `D:/agent-core`，实际安装 workswarm 0.2.9、openjiuwen 0.1.21、openjiuwen-agent-gateway 0.1.0 和 opentelemetry-sdk 1.41.1。此前 develop 组合的锁定限制仅适用于旧基线。

在锁定依赖的应用开发环境复验上述 18 个后端测试文件，**521 项通过**。前端 `test:runtime-monitor` 4 项、`test:jev-settings` 78 项、`test:subagent-history` 52 项，共 **134 项通过**。SDK 本轮相关回归 **203 项通过**。本轮验证范围为发布基线上的安装、装配、配置、消息、历史和监控行为，真实模型判断质量仍待原测试计划后续测量。

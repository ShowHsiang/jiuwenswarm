# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Native-agent runtime monitoring: assembly and bounded user-facing projections.

The SDK owns evidence, scoring and advice. This module owns the JEV client and
projects detached snapshots into the existing chat stream/history transport.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from collections import OrderedDict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

logger = logging.getLogger(__name__)
SNAPSHOT_EVENT = "chat.runtime_monitor"
NOTICE_TYPE = "runtime_intervention"
SCHEMA_VERSION = "runtime-monitor.v1"


class JevSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    api_key: SecretStr = SecretStr("")
    api_base: str = "https://api.typesafe.ai"
    model_name: str = "jev-latest"


class RuntimeMonitorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool = False
    mode: Literal["observe", "active"] = "observe"
    backend: Literal["jev", "llm"] = "jev"
    jev: JevSettings = Field(default_factory=JevSettings)
    parameters: dict[str, Any] = Field(default_factory=dict)


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def project_snapshot(memory, config) -> dict[str, Any]:
    """Whitelist diagnostics. Raw prompts, tool arguments and evidence stay private."""
    return {
        "event_type": SNAPSHOT_EVENT,
        "schema_version": SCHEMA_VERSION,
        "task_id": memory.goal.task_id,
        "generation": memory.generation,
        "goal_version": memory.goal.version,
        "revision": memory.revision,
        "mode": config.mode,
        "window": memory.window(config).model_dump(mode="json"),
        "stalled": memory.stalled,
        "steps": [{
            "step_id": step.step_id, "status": step.status,
            "gain": step.gain, "gain_is_lower_bound": step.gain_is_lower_bound,
            "eligible": step.eligible,
            "assessed": step.assessment is not None,
            "backend": step.assessment.backend if step.assessment else None,
            "assessment_failed": bool(step.assessment and step.assessment.error),
        } for step in memory.steps[-config.window_size:]],
        "advice": [{
            "advice_id": advice.advice_id, "state": advice.state,
            "recommendation": advice.option.recommendation,
            "triggers": list(advice.trigger_codes), "followed": advice.followed,
            "delivered": bool(advice.delivered_requests), "degraded": advice.degraded,
        } for advice in memory.advice[-8:]],
    }


_RECOMMENDATIONS = {
    "CONTINUE": ("继续当前方向", "continue the current approach"),
    "VERIFY": ("核查证据", "verify the evidence"),
    "REPLAN": ("换一个方向", "try a different approach"),
    "BACKTRACK": ("重审已有推理", "reconsider earlier reasoning"),
}
_STATES = {
    "created": ("等待主模型处理", "awaiting the main agent"),
    "delivered": ("建议已送达主模型", "delivered to the main agent"),
    "observing": ("正在观察后续效果", "observing the outcome"),
    "improved": ("观察到目标改善", "observed progress on the target"),
    "no_observed_improvement": ("尚未观察到目标改善", "no progress observed on the target"),
    "inconclusive": ("证据不足，效果暂无法判断", "insufficient evidence to judge the outcome"),
    "expired": ("建议已过期", "advice expired"),
    "superseded": ("已由新建议替代", "replaced by new advice"),
    "observed_only": ("观察模式，未发送干预", "observe mode; no intervention sent"),
}
_TRIGGERS = {
    "LOW_GAIN_STREAK": ("连续低收益", "consecutive low progress"),
    "LOW_WINDOW_GAIN": ("近期收益偏低", "low progress in the recent window"),
    "REPEATED_ACTION": ("重复动作与结果", "repeated actions and results"),
    "EVIDENCE_CONFLICT": ("证据矛盾", "conflicting evidence"),
    "PREMISE_REFUTED": ("已有验证被推翻", "previous verification refuted"),
    "OFF_TRACK": ("偏离目标", "departure from the goal"),
    "ASSESSMENT_GAP": ("评估资料不足", "insufficient assessment evidence"),
}


def intervention_notice(snapshot: dict, advice: dict, language: str) -> dict:
    index = 1 if language == "en" else 0
    recommendation = _RECOMMENDATIONS[advice["recommendation"]][index]
    state = _STATES[advice["state"]][index]
    reasons = ", ".join(_TRIGGERS[code][index] for code in advice["triggers"] if code in _TRIGGERS)
    window = snapshot["window"]
    mean = window["gain_mean"]
    mean_text = f"{mean:.2f}" if mean is not None else ("unknown" if index else "未知")
    if index:
        content = (f"Progress monitoring: {recommendation}. {state}. Reason: {reasons}. "
                   f"Recent steps: {len(window['step_ids'])}; mean progress: {mean_text}; "
                   f"verified progress: {window['verified_progress_count']}.")
    else:
        content = (f"进展监控：建议{recommendation}。{state}。原因：{reasons}。"
                   f"最近 {len(window['step_ids'])} 轮平均收益 {mean_text}，"
                   f"已验证进展 {window['verified_progress_count']} 项。")
    return {
        "event_type": "chat.notice", "notice_type": NOTICE_TYPE,
        "notice_id": f"{snapshot['generation']}:{advice['advice_id']}",
        "content": content,
        "runtime_monitor": {
            "schema_version": SCHEMA_VERSION, "task_id": snapshot["task_id"],
            "generation": snapshot["generation"], "mode": snapshot["mode"],
            "goal_version": snapshot["goal_version"], "advice": advice,
        },
    }


class RuntimeMonitorBinding:
    """One adapter's SDK monitor and its owned JEV client; no independent task loop."""

    def __init__(self, signature: str, language: str, client=None):
        self.signature = signature
        self.language = language
        self.client = client
        self.monitor = None
        self.closed = False
        self._snapshots: OrderedDict[str, str] = OrderedDict()
        self._notices: OrderedDict[tuple[str, str], str] = OrderedDict()

    @staticmethod
    def _remember(cache, key, value, limit):
        cache[key] = value
        cache.move_to_end(key)
        while len(cache) > limit:
            cache.popitem(last=False)

    async def publish(self, session, memory) -> None:
        if self.closed:
            return
        from openjiuwen.core.session.stream import OutputSchema

        snapshot = project_snapshot(memory, self.monitor.config)
        session_id = str(session.get_session_id())
        signature = _digest({key: value for key, value in snapshot.items() if key != "revision"})
        if self._snapshots.get(session_id) != signature:
            await session.write_stream(OutputSchema(type=SNAPSHOT_EVENT, index=0, payload=snapshot))
            self._remember(self._snapshots, session_id, signature, 32)
        for advice in snapshot["advice"]:
            # Compare lifecycle, not changing window statistics; a stable advice does not spam chat.
            notice = intervention_notice(snapshot, advice, self.language)
            key = (session_id, notice["notice_id"])
            advice_signature = _digest(advice)
            if self._notices.get(key) == advice_signature:
                continue
            await session.write_stream(OutputSchema(type="chat.notice", index=0, payload=notice))
            self._remember(self._notices, key, advice_signature, 64)

    async def aclose(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.client is not None:
            try:
                await self.client.aclose()
            except Exception as exc:
                logger.warning("Runtime monitoring client cleanup failed: %s", type(exc).__name__)
        self._snapshots.clear()
        self._notices.clear()


async def configure_runtime_monitor(agent, config: dict, *, current=None, chat_model=None,
                                    language: str = "zh") -> RuntimeMonitorBinding | None:
    """Install or reload optional monitoring. Unchanged settings preserve the client/window.

    Validation happens before replacing an existing binding. Callers can retain the
    previous binding if a requested reload is invalid. Disabled config imports no SDK monitor.
    """
    section = (config.get("execution_guard") or {}).get("runtime_monitor") or {}
    settings = RuntimeMonitorSettings.model_validate(section)
    if not settings.enabled:
        if current is not None:
            agent.set_runtime_monitor(None)
            await current.aclose()
        return None

    from openjiuwen.core.single_agent.runtime_monitor import (
        LlmRuntimeEvaluator, RuntimeMonitor, RuntimeMonitorConfig,
    )

    if not callable(getattr(agent, "set_runtime_monitor", None)):
        raise ValueError("runtime_monitor_requires_local_agent_core")
    parameters = dict(settings.parameters)
    if "mode" in parameters:
        raise ValueError("set_mode_in_runtime_monitor_section")
    monitor_config = RuntimeMonitorConfig(mode=settings.mode, **parameters)
    # A mode/backend change must not inherit active advice or an exhausted episode.
    # The stable Session key is retained; SDK bind resets the old scoring generation.
    monitor_config = monitor_config.model_copy(update={
        "rubric_version": f"{monitor_config.rubric_version}:{settings.backend}:{settings.mode}",
    })
    api_key = settings.jev.api_key.get_secret_value() or os.environ.get("JEV_API_KEY", "")
    signature = _digest([
        settings.model_dump(mode="json"), _digest(api_key), language,
        id(chat_model) if settings.backend == "llm" else None,
    ])
    if current is not None and not current.closed and current.signature == signature:
        agent.set_runtime_monitor(current.monitor)
        return current

    client = None
    if settings.backend == "jev":
        if not api_key or api_key.startswith("${"):
            raise ValueError("runtime_monitor_jev_api_key_missing")
        from openjiuwen.core.foundation.llm.system_one import JevSystemOneClient

        client = JevSystemOneClient(
            api_key=api_key, api_base=settings.jev.api_base, model_name=settings.jev.model_name,
            max_retries=0, timeout=max(monitor_config.assessment_timeout, monitor_config.review_timeout),
        )
        evaluator = None
    else:
        if chat_model is None:
            raise ValueError("runtime_monitor_llm_model_missing")
        evaluator = LlmRuntimeEvaluator(chat_model, timeout=max(
            monitor_config.assessment_timeout, monitor_config.review_timeout,
        ))
    binding = RuntimeMonitorBinding(signature, language, client)
    try:
        binding.monitor = RuntimeMonitor(
            jev_client=client, evaluator=evaluator, config=monitor_config,
            scope_id="jiuwenswarm:main:runtime-monitor", on_update=binding.publish,
        )
        agent.set_runtime_monitor(binding.monitor)
    except BaseException:
        await binding.aclose()
        raise
    if current is not None:
        await current.aclose()
    return binding

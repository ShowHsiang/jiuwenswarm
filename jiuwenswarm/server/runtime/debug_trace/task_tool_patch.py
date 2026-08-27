# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.

"""Monkeypatch the SDK's builtin ``TaskTool.invoke`` to capture subagent streams.

The builtin TaskTool (``openjiuwen.harness.tools.subagent.task_tool``) drives
subagents via ``await subagent.invoke(...)``, which returns only the final
output string — its internal reasoning / tool calls / token usage never reach
the parent run's :class:`DebugTraceLogger`. This patch wraps ``invoke`` so that,
when a debug run is actively capturing subagent flow, the subagent is instead
driven through ``stream()`` via :func:`invoke_subagent_with_trace` and its
chunks land in the dump under ``source=subagent:builtin:<type>``.

Any run that is NOT capturing (no debug run, or ``include_subagent_flow`` off)
short-circuits to the pristine original ``invoke`` (``_orig_invoke``) for zero
behaviour change — the re-implemented parse/create/invoke path runs only while
a dump is actually being written. Safe to apply unconditionally at startup.
"""

from __future__ import annotations

_PATCH_APPLIED = False


def apply_task_tool_debug_patch() -> None:
    """Patch ``TaskTool.invoke`` to capture subagent streams under ``/debug``.

    Idempotent: a module flag plus a class-attribute guard make repeat calls
    no-ops.
    """
    global _PATCH_APPLIED
    if _PATCH_APPLIED:
        return

    from openjiuwen.harness.tools.subagent.task_tool import TaskTool

    if getattr(TaskTool, "debug_trace_patch_applied", False):
        _PATCH_APPLIED = True
        return

    _orig_invoke = TaskTool.invoke

    async def _invoke_with_trace(self, inputs, **kwargs):  # type: ignore[no-untyped-def]
        from openjiuwen.core.common.exception.codes import StatusCode
        from openjiuwen.core.common.exception.errors import build_error
        from openjiuwen.core.common.logging import logger
        from openjiuwen.core.session.agent import Session
        from openjiuwen.harness.tools.base_tool import ToolOutput

        from jiuwenswarm.server.runtime.debug_trace import (
            get_debug_trace_logger,
            invoke_subagent_with_trace,
        )
        from jiuwenswarm.server.runtime.debug_trace.context import (
            get_debug_trace_logger_for_session,
        )

        # Not capturing -> pristine original SDK path, unchanged.
        dbg = get_debug_trace_logger()
        if dbg is None:
            # TaskTool.invoke runs in the DeepAgent's supervisor task (created at
            # session setup, before any /debug request publishes the ContextVar),
            # so the per-request binding above doesn't reach it. Fall back to the
            # session-keyed registry — we hold the parent Session in kwargs.
            parent_session = kwargs.get("session", None)
            if isinstance(parent_session, Session):
                dbg = get_debug_trace_logger_for_session(parent_session.get_session_id())
                if dbg is not None:
                    logger.info(
                        "[TaskTool] (debug) recovered trace logger via session "
                        "registry: %s", parent_session.get_session_id(),
                    )
        if dbg is None or not dbg.captures_subagent_flow():
            return await _orig_invoke(self, inputs, **kwargs)

        parent_session = kwargs.get("session", None)
        if not isinstance(parent_session, Session):
            raise build_error(
                StatusCode.TOOL_TASK_TOOL_INVOKED,
                reason="TaskTool requires a valid session in kwargs",
            )

        if isinstance(inputs, dict):
            subagent_type = inputs.get("subagent_type")
            task_description = inputs.get("task_description")
            resume_task_id = inputs.get("resume_task_id")
        else:
            raise build_error(
                StatusCode.TOOL_TASK_TOOL_INVOKED,
                reason=f"Invalid inputs type: {type(inputs)}",
            )

        if not subagent_type or not task_description:
            raise build_error(
                StatusCode.TOOL_TASK_TOOL_INVOKED,
                reason="Both 'subagent_type' and 'task' are required",
            )

        browser_capabilities = None
        if str(subagent_type) == "browser_agent":
            raw_capabilities = inputs.get("browser_capabilities")
            if raw_capabilities is None:
                browser_capabilities = []
            elif isinstance(raw_capabilities, list) and all(
                isinstance(capability_name, str)
                for capability_name in raw_capabilities
            ):
                browser_capabilities = list(raw_capabilities)
            else:
                raise build_error(
                    StatusCode.TOOL_TASK_TOOL_INVOKED,
                    reason="'browser_capabilities' must be a list of strings",
                )
        elif resume_task_id:
            raise build_error(
                StatusCode.TOOL_TASK_TOOL_INVOKED,
                reason="'resume_task_id' is supported only for browser_agent",
            )

        parent_session_id = parent_session.get_session_id()
        try:
            try:
                sub_session_id = self._build_sub_session_id(
                    parent_session_id,
                    str(subagent_type),
                    str(resume_task_id or ""),
                )
            except TypeError:
                if resume_task_id:
                    raise ValueError("The installed SDK does not support browser task resume")
                sub_session_id = self._build_sub_session_id(parent_session_id, str(subagent_type))
        except ValueError as exc:
            raise build_error(
                StatusCode.TOOL_TASK_TOOL_INVOKED,
                reason=str(exc),
            ) from exc
        logger.info(
            "[TaskTool] (debug) Creating subagent: %s, parent_session=%s, sub_session=%s",
            subagent_type, parent_session_id, sub_session_id,
        )

        try:
            if browser_capabilities is None:
                subagent = self.parent_agent.create_subagent(subagent_type, sub_session_id)
            else:
                subagent = self.parent_agent.create_subagent(
                    subagent_type,
                    sub_session_id,
                    browser_capabilities=browser_capabilities,
                )
        except Exception as exc:
            logger.error(
                "[TaskTool] Subagent creation failed: type=%s, error=%s",
                subagent_type, exc,
            )
            raise build_error(
                StatusCode.TOOL_TASK_TOOL_INVOKED,
                reason=f"Subagent {subagent_type} creation failed: {exc}",
            ) from exc

        try:
            subagent_inputs = {"query": task_description, "conversation_id": sub_session_id}
            if str(subagent_type) == "browser_agent" and resume_task_id:
                subagent_inputs["run_context"] = {
                    "browser_resume": True,
                    "resume_task_id": sub_session_id,
                }
            result = await invoke_subagent_with_trace(
                subagent,
                inputs=subagent_inputs,
                session=parent_session,
                source_label=f"subagent:builtin:{subagent_type}",
            )
            output = result.get("output", "")
            build_result_data = getattr(self, "_build_result_data", None)
            if callable(build_result_data):
                result_data = build_result_data(
                    result,
                    output,
                    agent_id=subagent.card.id,
                    subagent_type=str(subagent_type),
                    sub_session_id=sub_session_id,
                )
            else:
                result_data = {"output": output, "agent_id": subagent.card.id}
                if str(subagent_type) == "browser_agent":
                    result_data["resume_task_id"] = sub_session_id
            return ToolOutput(
                success=True,
                data=result_data,
                error=None,
            )
        except Exception as exc:
            logger.error(
                "[TaskTool] Subagent: %s execution failed, error=%s",
                subagent_type, exc,
            )
            raise build_error(
                StatusCode.TOOL_TASK_TOOL_INVOKED,
                reason=f"Subagent {subagent_type} execution failed: {exc}",
            ) from exc

    TaskTool.invoke = _invoke_with_trace  # type: ignore[assignment]
    TaskTool.debug_trace_patch_applied = True
    _PATCH_APPLIED = True


__all__ = ["apply_task_tool_debug_patch"]

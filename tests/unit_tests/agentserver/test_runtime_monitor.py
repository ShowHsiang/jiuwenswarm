"""Application assembly, live SDK feedback and user-visible notice/history contracts."""
import asyncio
import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from openjiuwen.core.context_engine import ContextWindow
from openjiuwen.core.foundation.llm import AssistantMessage, AssistantMessageChunk, ToolCall, ToolMessage
from openjiuwen.core.foundation.llm.system_one import ChoiceAnswer, NoulAnswer, SystemOneResponse, SystemOneUsage
from openjiuwen.core.foundation.tool import ToolInfo
from openjiuwen.core.session.agent import Session
from openjiuwen.core.single_agent import AgentCard
from openjiuwen.harness import create_deep_agent
from openjiuwen.harness.schema.interaction import RoundWorkItem

from jiuwenswarm.server.runtime.agent_adapter import interface_deep
from jiuwenswarm.server.runtime.agent_adapter.runtime_monitor import (
    RuntimeMonitorSettings, configure_runtime_monitor, project_snapshot,
)
from tests.unit_tests.agentserver.permissions.test_permission_cold_build import cold


class FakeJev:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.max_retries = kwargs["max_retries"]
        self.calls = []
        self.close_count = 0
        type(self).instances.append(self)

    async def system_one(self, data, questions, **kwargs):
        self.calls.append(data)
        answers = {}
        for key, question in questions.items():
            if question.type == "choice":
                choices = list(question.criteria)
                if key.startswith("gain:"):
                    found = any("verified source" in o["text"] for o in data["step"]["observations"])
                    choice = "NEW_EVIDENCE" if found else "NO_GAIN"
                elif key == "advice_option":
                    choice = "verify"
                elif key == "followed_advice":
                    choice = "YES"
                else:
                    choice = "COMPATIBLE"
                answers[key] = ChoiceAnswer(choice=choice, confidence=0.99, probabilities={
                    item: 0.99 if item == choice else 0.01 / (len(choices) - 1) for item in choices
                })
            else:
                answers[key] = NoulAnswer(noul=0.1 if key == "off_track" else 0.9)
        return SystemOneResponse(model="test-jev", answers=answers,
                                 usage=SystemOneUsage(input_tokens=10, output_tokens=2))

    async def aclose(self):
        self.close_count += 1


@pytest.fixture
def fake_jev(monkeypatch):
    FakeJev.instances = []
    monkeypatch.setattr("openjiuwen.core.foundation.llm.system_one.JevSystemOneClient", FakeJev)
    return FakeJev


def config(mode="active", **parameters):
    return {"execution_guard": {"runtime_monitor": {
        "enabled": True, "mode": mode, "jev": {"api_key": "test-only-not-a-secret"},
        "parameters": {"warmup_steps": 0, "low_gain_steps": 1, **parameters},
    }}}


@pytest.mark.asyncio
async def test_disabled_monitor_does_not_require_new_sdk_or_create_client(fake_jev):
    assert await configure_runtime_monitor(object(), {}) is None
    assert not fake_jev.instances
    assert RuntimeMonitorSettings().backend == "jev"


@pytest.mark.asyncio
async def test_reload_reuses_client_and_disable_releases_it_once(fake_jev):
    agent = SimpleNamespace(set_runtime_monitor=MagicMock())
    first = await configure_runtime_monitor(agent, config())
    second = await configure_runtime_monitor(agent, config(), current=first)
    assert first is second
    assert first.client.max_retries == 0
    assert first.monitor.config.mode == "active"
    assert len(fake_jev.instances) == 1
    assert await configure_runtime_monitor(agent, {}, current=first) is None
    await first.aclose()
    assert first.client.close_count == 1
    agent.set_runtime_monitor.assert_called_with(None)


@pytest.mark.asyncio
async def test_invalid_reload_preserves_previous_binding_and_secrets_are_not_logged(fake_jev):
    agent = SimpleNamespace(set_runtime_monitor=MagicMock())
    first = await configure_runtime_monitor(agent, config())
    invalid = config(window_size=0)
    with pytest.raises(ValueError):
        await configure_runtime_monitor(agent, invalid, current=first)
    assert not first.closed
    assert agent.set_runtime_monitor.call_args.args[0] is first.monitor
    assert "test-only-not-a-secret" not in repr(RuntimeMonitorSettings.model_validate(config()["execution_guard"]["runtime_monitor"]))
    await first.aclose()


@pytest.mark.asyncio
async def test_llm_replacement_uses_supplied_model_without_owning_it(fake_jev):
    model = SimpleNamespace(invoke=AsyncMock())
    settings = {"execution_guard": {"runtime_monitor": {"enabled": True, "backend": "llm"}}}
    agent = SimpleNamespace(set_runtime_monitor=MagicMock())
    binding = await configure_runtime_monitor(agent, settings, chat_model=model)
    assert binding.monitor.evaluator.model is model
    assert binding.client is None and not fake_jev.instances
    await binding.aclose()


@pytest.mark.asyncio
async def test_missing_key_does_not_construct_a_client(fake_jev, monkeypatch):
    monkeypatch.delenv("JEV_API_KEY", raising=False)
    settings = {"execution_guard": {"runtime_monitor": {"enabled": True}}}
    with pytest.raises(ValueError, match="api_key_missing"):
        await configure_runtime_monitor(SimpleNamespace(set_runtime_monitor=MagicMock()), settings)
    assert not fake_jev.instances


@pytest.mark.asyncio
async def test_real_adapter_factory_installs_monitor_and_cleanup_closes_client(cold, fake_jev):
    cold.raw.update(config())
    await cold.create()
    binding = cold.adapter._runtime_monitor_binding
    assert binding is not None
    assert cold.adapter._instance.react_agent._runtime_monitor is binding.monitor
    await cold.adapter.cleanup()
    assert binding.client.close_count == 1
    assert cold.adapter._instance.react_agent._runtime_monitor is None


class MainModel:
    model_config = None
    model_client_config = None

    def __init__(self):
        self.requests = []

    async def invoke(self, messages, **kwargs):
        self.requests.append(list(messages))
        if len(self.requests) > 2:
            return AssistantMessage(content="done")
        has_advice = any("[runtime_intervention]" in str(m.content) for m in messages)
        return AssistantMessage(content="", tool_calls=[ToolCall(
            id=f"call-{len(self.requests)}", type="function", name="verify" if has_advice else "search",
            arguments='{"query":"cause"}',
        )])

    async def stream(self, messages, **kwargs):
        result = await self.invoke(messages, **kwargs)
        yield AssistantMessageChunk(content=result.content, tool_calls=result.tool_calls)


def wire(agent, model):
    messages = []
    context = MagicMock()
    context.get_messages.side_effect = lambda **kwargs: list(messages)
    context.add_messages = AsyncMock(side_effect=lambda message: messages.append(message))
    context.session_id.return_value = "runtime-test"

    async def window(**kwargs):
        return ContextWindow(system_messages=kwargs["system_messages"], context_messages=list(messages),
                             tools=kwargs.get("tools") or [])

    context.get_context_window = AsyncMock(side_effect=window)
    engine = MagicMock()
    engine.create_context = AsyncMock(return_value=context)
    engine.get_context.return_value = context
    engine.save_contexts = AsyncMock()
    agent.context_engine = engine
    agent._llm = model
    agent.ability_manager.list_tool_info = AsyncMock(return_value=[
        ToolInfo(name=name, description=name, parameters={}) for name in ("search", "verify")
    ])
    actions = []

    async def execute(**kwargs):
        results = []
        for call in kwargs["tool_call"]:
            actions.append(call.name)
            text = "verified source for cause" if call.name == "verify" else "no new information"
            message = ToolMessage(content=text, tool_call_id=call.id)
            if kwargs.get("on_tool_result"):
                kwargs["on_tool_result"](call, message)
            results.append((text, message))
        return results

    agent.ability_manager.execute = execute
    return actions


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["active", "observe"])
@pytest.mark.parametrize("entry", ["invoke", "interaction_round"])
async def test_application_binding_drives_real_loop_and_projects_advice_outcome(mode, entry, fake_jev, monkeypatch, tmp_path):
    monkeypatch.setattr("openjiuwen.harness.deep_agent.schedule_image_support_probe", lambda *a, **k: None)
    model = MainModel()
    agent = create_deep_agent(model=model, card=AgentCard(id=uuid.uuid4().hex, name="monitored-app"),
                              rails=[], enable_task_loop=False, enable_sys_operation=False,
                              add_general_purpose_agent=False, workspace=str(tmp_path))
    adapter = object.__new__(interface_deep.JiuWenSwarmDeepAdapter)
    adapter._instance = agent
    adapter._resolve_prompt_language = lambda: "en"
    await adapter._sync_runtime_monitor(config(mode), model)
    binding = adapter._runtime_monitor_binding
    actions = wire(agent.react_agent, model)
    events = []
    session = Session(session_id=uuid.uuid4().hex, card=agent.card)
    session.write_stream = AsyncMock(side_effect=lambda chunk: events.append(chunk))
    try:
        inputs = {"query": "private goal not for broadcast"}
        if entry == "invoke":
            result = await agent.invoke(inputs, session)
            assert result["output"] == "done"
        else:
            work = RoundWorkItem.user(request_id="request-1", inputs=inputs)
            outcome = await asyncio.wait_for(agent.run_one_round(work, "task-1", session), timeout=15)
            assert outcome.error_code is None
            assert binding.monitor.get_memory(session).goal.task_id == "task-1"
        assert actions == (["search", "verify"] if mode == "active" else ["search", "search"])
        parsed = [adapter._parse_stream_chunk(chunk) for chunk in events
                  if getattr(chunk, "type", None) in {"chat.runtime_monitor", "chat.notice"}]
        notices = [event for event in parsed if event["event_type"] == "chat.notice"]
        assert notices
        assert len({notice["notice_id"] for notice in notices}) == 1
        assert notices[-1]["runtime_monitor"]["advice"]["state"] == (
            "improved" if mode == "active" else "observed_only"
        )
        assert ("[runtime_intervention]" in "\n".join(str(m.content) for m in model.requests[1])) == (mode == "active")
        assert "private goal not for broadcast" not in json.dumps(parsed)
        assert "verified source for cause" not in json.dumps(parsed)
        assert "test-only-not-a-secret" not in json.dumps(parsed)
        assert len(binding.client.calls) == 3  # A, B, A; no extra supervision for the final answer.
        before = len(events)
        await binding.monitor.publish(session)
        assert len(events) == before, "identical snapshots and notices are deduplicated"
    finally:
        await agent._force_cleanup_controller()
        await binding.aclose()
        await agent._agent_callback_manager.clear()
        await agent.react_agent.agent_callback_manager.clear()


@pytest.mark.asyncio
async def test_snapshot_identity_isolated_per_session(fake_jev):
    agent = SimpleNamespace(set_runtime_monitor=MagicMock())
    binding = await configure_runtime_monitor(agent, config())
    snapshots = []
    for sid in ("session-one", "session-two"):
        session = Session(session_id=sid)
        session.write_stream = AsyncMock(side_effect=lambda item: snapshots.append(item.payload))
        binding.monitor.bind(session, "private goal")
        await binding.monitor.publish(session)
    assert len(snapshots) == 2
    assert snapshots[0]["task_id"] != snapshots[1]["task_id"]
    assert snapshots[0]["generation"] != snapshots[1]["generation"]
    assert snapshots[0]["window"]["verified_progress_count"] == 0
    await binding.aclose()


@pytest.mark.asyncio
async def test_mode_reload_starts_a_fresh_generation_and_closes_old_client(fake_jev):
    agent = SimpleNamespace(set_runtime_monitor=MagicMock())
    first = await configure_runtime_monitor(agent, config("observe"))
    session = Session(session_id="mode-reload")
    first.monitor.bind(session, "task")
    old = first.monitor.get_memory(session)
    second = await configure_runtime_monitor(agent, config("active"), current=first)
    second.monitor.bind(session, "", resume=True)
    new = second.monitor.get_memory(session)
    assert new.goal.task_id == old.goal.task_id
    assert new.generation != old.generation
    assert first.client.close_count == 1
    assert not new.advice and new.episode_interventions == 0
    session.write_stream = AsyncMock()
    await first.publish(session, old)
    session.write_stream.assert_not_awaited()
    await second.aclose()


@pytest.mark.asyncio
async def test_failed_projection_can_retry_without_duplicate_snapshot(fake_jev):
    from openjiuwen.core.single_agent.runtime_monitor.schema import Advice, AdviceOption

    binding = await configure_runtime_monitor(SimpleNamespace(set_runtime_monitor=MagicMock()), config())
    session = Session(session_id="retry-publication")
    binding.monitor.bind(session, "task")
    memory = binding.monitor.get_memory(session)
    memory.advice.append(Advice(
        advice_id="a1", option=AdviceOption(option_id="verify", recommendation="VERIFY", target_ref="progress", instruction="Verify progress"),
        goal_version=1, created_seq=1, memory_revision=memory.revision, trigger_codes=["LOW_GAIN_STREAK"],
    ))
    session.write_stream = AsyncMock(side_effect=[None, OSError("disconnected"), None])
    with pytest.raises(OSError):
        await binding.publish(session, memory)
    await binding.publish(session, memory)
    assert [call.args[0].type for call in session.write_stream.call_args_list] == [
        "chat.runtime_monitor", "chat.notice", "chat.notice",
    ]
    await binding.aclose()


def test_snapshots_and_notices_survive_actual_history_writer(tmp_path, monkeypatch):
    from openjiuwen.core.single_agent.runtime_monitor import RuntimeMonitorConfig
    from openjiuwen.core.single_agent.runtime_monitor.memory import RuntimeMemory
    from openjiuwen.core.single_agent.runtime_monitor.schema import RuntimeGoal
    from jiuwenswarm.server.runtime.session import session_history, session_metadata
    from tests.unit_tests.test_session_history_empty_filter import _wait_history

    monkeypatch.setattr(session_history, "get_agent_sessions_dir", lambda: tmp_path)
    monkeypatch.setattr(session_metadata, "update_session_metadata", lambda **kwargs: None)
    monkeypatch.setattr(session_metadata, "set_session_delivery_context", lambda **kwargs: None)
    snapshot = project_snapshot(RuntimeMemory(goal=RuntimeGoal(task_id="task-1", text="private"), rubric_version="progress-v1"), RuntimeMonitorConfig())
    notice = {"notice_id": "gen:advice-1", "notice_type": "runtime_intervention", "runtime_monitor": {"advice": {"state": "improved"}}}
    for event, content, extra in [
        ("chat.runtime_monitor", "", {"schema_version": "invalid"}),
        ("chat.runtime_monitor", "", snapshot),
        ("chat.notice", "Observed progress", notice),
    ]:
        session_history.append_history_record(session_id="runtime-history", request_id="r1", channel_id="web",
            role="assistant", event_type=event, content=content, timestamp=1.0, extra=extra)
    rows = _wait_history("runtime-history", min_count=2)
    assert [row["event_type"] for row in rows] == ["chat.runtime_monitor", "chat.notice"]
    assert rows[0]["window"] == snapshot["window"]
    assert rows[1]["notice_id"] == "gen:advice-1"
    assert rows[1]["runtime_monitor"]["advice"]["state"] == "improved"

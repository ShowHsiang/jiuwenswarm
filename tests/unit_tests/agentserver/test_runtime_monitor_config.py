"""Shared decision-model settings reach the BAI transport and reload lifecycle."""
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import yaml

from openjiuwen.core.foundation.llm.system_one import ChoiceQuestion, JevSystemOneClient
from openjiuwen.core.session.agent import Session

from jiuwenswarm.common import config as config_module
from jiuwenswarm.common.browser_settings import JEV_PROVIDER_DEFAULTS
from jiuwenswarm.server.runtime.agent_adapter.interface_deep import JiuWenSwarmDeepAdapter
from jiuwenswarm.server.runtime.agent_adapter.runtime_monitor import configure_runtime_monitor
from tests.unit_tests.agentserver.test_runtime_monitor import config, fake_jev


@pytest.mark.asyncio
@pytest.mark.parametrize("provider,endpoint", [
    ("typesafe", "/systemone"), ("openrouter", "/decisions"), ("custom", "/systemone"),
])
async def test_shared_settings_reach_real_jev_request(monkeypatch, provider, endpoint):
    monkeypatch.setattr(config_module, "get_crypto_provider", lambda: None)
    monkeypatch.setenv(JEV_PROVIDER_DEFAULTS[provider]["api_key_env"], "synthetic-shared-key")
    raw = config()
    base = JEV_PROVIDER_DEFAULTS[provider]["api_base"] or "https://jev.example.test/v1"
    model = JEV_PROVIDER_DEFAULTS[provider]["model"]
    raw["browser"] = {"enabled": False, "decision": {
        "mode": "llm", "provider": provider, "api_base": base, "model": model,
        "request_timeout_ms": 30000, "max_retries": 1, "max_decisions": 40,
    }}
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"model": model, "answers": {
            "result": {"type": "choice", "choice": "yes", "confidence": 0.95,
                       "probabilities": {"yes": 0.95, "no": 0.05}},
        }, "usage": {"input_tokens": 2, "output_tokens": 1}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        constructed = []

        def client(**kwargs):
            constructed.append(kwargs)
            return JevSystemOneClient(**kwargs, http_client=http)

        monkeypatch.setattr("openjiuwen.core.foundation.llm.system_one.JevSystemOneClient", client)
        binding = await configure_runtime_monitor(SimpleNamespace(set_runtime_monitor=MagicMock()), raw)
        try:
            answer = await binding.client.system_one({"evidence": "synthetic"}, {
                "result": ChoiceQuestion(instructions="Is the evidence supported?", criteria={"yes": "Supported", "no": "Unsupported"}),
            })
            assert answer.answers["result"].choice == "yes"
            assert str(requests[0].url) == base + endpoint
            assert requests[0].headers["authorization"] == "Bearer synthetic-shared-key"
            assert json.loads(requests[0].content)["model"] == model
            assert constructed[0]["max_retries"] == 0
            assert constructed[0]["timeout"] == 1.5
        finally:
            await binding.aclose()


@pytest.mark.asyncio
async def test_connection_reload_ignores_browser_mode_but_updates_client_and_model_generation(fake_jev, monkeypatch):
    raw = config()
    raw["browser"] = {"decision": {"provider": "typesafe", "mode": "llm"}}
    agent = SimpleNamespace(set_runtime_monitor=MagicMock())
    session = Session(session_id="shared-connection-reload")
    first = await configure_runtime_monitor(agent, raw)
    first.monitor.bind(session, "task")
    original = first.monitor.get_memory(session)
    browser_only = deepcopy(raw)
    browser_only["browser"]["decision"].update(mode="hybrid", display_name="New label", max_decisions=2)
    assert await configure_runtime_monitor(agent, browser_only, current=first) is first
    monkeypatch.setenv("TYPESAFE_API_KEY", "rotated-key")
    second = await configure_runtime_monitor(agent, raw, current=first)
    assert second is not first and first.client.close_count == 1
    assert second.client.kwargs["api_key"] == "rotated-key"
    second.monitor.bind(session, "", resume=True)
    assert second.monitor.get_memory(session).generation == original.generation
    raw["browser"]["decision"]["model"] = "jev-next"
    third = await configure_runtime_monitor(agent, raw, current=second)
    third.monitor.bind(session, "", resume=True)
    assert third.monitor.get_memory(session).generation != original.generation
    assert second.client.close_count == 1
    await third.aclose()


@pytest.mark.asyncio
async def test_saved_encrypted_key_is_decrypted_only_for_the_client(fake_jev, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "encrypted-shared-key")
    decrypt = MagicMock(return_value="decrypted-shared-key")
    monkeypatch.setattr(config_module, "get_crypto_provider", lambda: SimpleNamespace(decrypt=decrypt))
    binding = await configure_runtime_monitor(SimpleNamespace(set_runtime_monitor=MagicMock()), config())
    assert binding.client.kwargs["api_key"] == "decrypted-shared-key"
    decrypt.assert_called_once_with("encrypted-shared-key")
    assert "decrypted-shared-key" not in binding.signature
    assert "encrypted-shared-key" not in binding.signature
    await binding.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["decrypt", "url"])
async def test_invalid_shared_reload_keeps_binding_without_leaking_keys(fake_jev, monkeypatch, caplog, failure):
    raw = config()
    agent = SimpleNamespace(set_runtime_monitor=MagicMock())
    binding = await configure_runtime_monitor(agent, raw)
    adapter = object.__new__(JiuWenSwarmDeepAdapter)
    adapter._instance = agent
    adapter._runtime_monitor_binding = binding
    monkeypatch.setattr(adapter, "_resolve_prompt_language", lambda: "zh")
    if failure == "decrypt":
        decrypt = MagicMock(side_effect=ValueError("sensitive-error-value"))
        monkeypatch.setattr(config_module, "get_crypto_provider", lambda: SimpleNamespace(decrypt=decrypt))
    else:
        raw["browser"] = {"decision": {"api_base": "https://user:sensitive-error-value@example.test"}}
    await adapter._sync_runtime_monitor(raw, None)
    assert adapter._runtime_monitor_binding is binding
    assert not binding.closed and len(fake_jev.instances) == 1
    assert "sensitive-error-value" not in caplog.text
    assert "test-only-not-a-secret" not in caplog.text
    await binding.aclose()


@pytest.mark.asyncio
async def test_llm_backend_does_not_resolve_shared_jev_or_require_a_key(fake_jev, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("LLM monitoring must not resolve Jev credentials")

    monkeypatch.setattr("jiuwenswarm.server.runtime.agent_adapter.runtime_monitor.resolve_jev_connection", unexpected)
    raw = config()
    raw["execution_guard"]["runtime_monitor"]["backend"] = "llm"
    raw["browser"] = {"decision": "invalid"}
    model = SimpleNamespace(invoke=AsyncMock())
    binding = await configure_runtime_monitor(SimpleNamespace(set_runtime_monitor=MagicMock()), raw, chat_model=model)
    assert binding.monitor.evaluator.model is model
    assert not fake_jev.instances
    await binding.aclose()


@pytest.mark.asyncio
async def test_frontend_save_persists_one_connection_and_reloads_bai(tmp_path, monkeypatch, fake_jev):
    from jiuwenswarm.common.config_panel import config_set_handlers as handlers
    from jiuwenswarm.common.schema.agent import AgentRequest
    from jiuwenswarm.common.schema.message import ReqMethod
    from jiuwenswarm.server.runtime.gateway_adapter.config_adapter import ConfigAdapter

    config_path = tmp_path / "config.yaml"
    env_path = tmp_path / ".env"
    config_path.write_text(yaml.safe_dump(config()), encoding="utf-8")
    env_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_YAML_PATH", config_path)
    monkeypatch.setattr(config_module, "get_config_file", lambda: config_path)
    monkeypatch.setattr(handlers, "ENV_FILE", env_path)
    monkeypatch.setattr(handlers, "_get_crypto_provider", lambda: None)
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    gateway = ConfigAdapter(on_config_saved=AsyncMock(return_value=True))

    saved_key = await gateway.handle(AgentRequest(
        request_id="shared-key", channel_id="web", session_id="one", req_method=ReqMethod.CONFIG_SAVE_ALL,
        params={"config": {"jev_openrouter_api_key": "saved-through-frontend"}},
    ))
    assert saved_key.ok
    saved_model = await gateway.handle(AgentRequest(
        request_id="shared-model", channel_id="web", session_id="one", req_method=ReqMethod.PATH_SET,
        params={"chrome_path": "", "headless": True, "decision_mode": "llm",
                "decision_provider": "openrouter", "decision_model": "typesafe/jev-1.13",
                "decision_api_base": "https://openrouter.ai/api/alpha", "decision_display_name": "Shared Jev"},
    ))
    assert saved_model.ok and saved_model.payload["jev_key_configured"]
    persisted = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert "jev" not in persisted["execution_guard"]["runtime_monitor"]
    assert "saved-through-frontend" not in config_path.read_text(encoding="utf-8")
    assert "saved-through-frontend" in env_path.read_text(encoding="utf-8")
    agent = SimpleNamespace(set_runtime_monitor=MagicMock())
    binding = await configure_runtime_monitor(agent, persisted)
    assert binding.client.kwargs["api_key"] == "saved-through-frontend"
    assert binding.client.kwargs["endpoint_path"] == "/decisions"
    assert binding.client.kwargs["model_name"] == saved_model.payload["decision_model"]
    cleared = await gateway.handle(AgentRequest(
        request_id="clear-key", channel_id="web", session_id="one", req_method=ReqMethod.CONFIG_SAVE_ALL,
        params={"config": {"jev_openrouter_api_key": ""}},
    ))
    assert cleared.ok
    assert await configure_runtime_monitor(agent, persisted, current=binding) is None
    agent.set_runtime_monitor.assert_called_with(None)
    assert binding.client.close_count == 1

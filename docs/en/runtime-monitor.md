# Runtime Memory and BAI integration

The native main Agent uses the SDK RuntimeMonitor for evidence, progress windows, intervention advice and outcome tracking. The application owns configuration, client lifecycle, bounded chat notices and history. Cost prediction is excluded. Recovery will be integrated separately.

## Shared decision model

Configure JEV in **Settings → Models → Decision model**. BAI and the browser Agent share `browser.decision` (provider, api_base, model, api_key_env) and the existing credential store:

| Provider | Credential variable | Endpoint appended to API base |
| --- | --- | --- |
| TypeSafe | TYPESAFE_API_KEY | /systemone |
| OpenRouter | OPENROUTER_API_KEY | /decisions |
| Custom | JEV_CUSTOM_API_KEY | /systemone |

Enable monitoring separately in the effective workspace config:

```yaml
execution_guard:
  runtime_monitor:
    enabled: true
    mode: observe
    backend: jev
    parameters:
      window_size: 5
      warmup_steps: 2
      low_gain_steps: 3
      conflict_threshold: 2
      assessment_timeout: 1.5
      review_timeout: 1.5
```

Start in observe mode; active sends advice to the main model. Browser modes, timeouts and decision limits do not control BAI. BAI uses its own timeouts and zero client retries. `backend: llm` uses the current main model and does not require JEV credentials.

Remove the old `execution_guard.runtime_monitor.jev` section; the dedicated `JEV_API_KEY` setting is no longer consumed. Existing user workspace files are not migrated automatically. Saved encrypted credentials are decrypted at runtime and excluded from notices and plaintext fingerprints.

Reload reuses unchanged clients. Key rotation replaces the client while retaining the progress window. Changing the JEV model/endpoint or BAI mode/backend starts a new scoring generation. Clearing the selected shared key detaches monitoring and closes its cached client. Other invalid reloads retain the previous valid binding. Disable and cleanup also release the owned client.

## Local integration

Use the app's `runtime-bai-adaptation` branch (official `releases/0.2.9`) and an adjacent `../agent-core` checkout on `react-runtime-bai` (official `v0.1.21`). From the application repository run:

```shell
uv sync --locked
uv run --locked jiuwenswarm-start
```

The app retains the release pin `openjiuwen==0.1.21` and its extra constraints. The uv source and lockfile resolve it to the adjacent editable checkout. Gateway, protocol and other packages use the release lock's versions. Restart the app after editing the SDK to load the changes.

For a different checkout location, use `scripts/use-local-agent-core.ps1 -AgentCorePath <path>` in an existing environment with the matching release dependencies. The helper checks the branch and import path. Start that environment directly or use `uv run --no-sync` so the custom path takes effect.

BAI emits `chat.runtime_monitor` diagnostics and stable `chat.notice` entries with `notice_type=runtime_intervention`. History restores the last state of each advice. The shared history event allowlist retains notices for JSONL index/cursor paging and legacy JSON index paging. Raw monitor snapshots stay out of chat history pages; diagnostics and notices are excluded from model context replay. No recovery checkpoints or external rollback are executed. Generic tool observations alone cannot certify business acceptance; add an EvidenceAdapter for verified domain progress.

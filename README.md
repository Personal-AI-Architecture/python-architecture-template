# Python PAA Template

Reference Python implementation for the [Personal AI Architecture (PAA)](https://github.com/Personal-AI-Architecture/the-architecture).
It is designed to help you understand the PAA boundaries quickly, run a
working local example without a provider account, and extend the implementation
without losing contract alignment.

The current contract checks cover per-request model and provider selection,
provider-profile routing, saved reply provenance, context limits, and notices
for omitted complete turns. This starter's small text journey is not a full
implementation of every PAA tool and product conformance case.

## What you get

- A canonical PAA Gateway with conversation routes and SSE responses.
- A provider-neutral Agent Loop and a deterministic offline mock adapter.
- A clear adapter boundary for connecting a real model provider.
- Runtime configuration that keeps provider selection out of request metadata.
- Pinned and vendored PAA contracts under `paa.lock.json`, `contracts/`, and
  `vendor/paa-contracts/`.
- Python-native contract, import-boundary, lock-in, unit, integration,
  conformance, acceptance, and static type checks.
- Integration with the shared language-neutral PAA conformance validator.

The starter uses Python's standard library for its runtime and demo server.
The only development dependency is mypy for static type checking.

## Requirements

- Python 3.11 or newer
- `curl` for the HTTP walkthrough
- Node.js 20 or newer only when running the shared cross-language validator

## Quickstart

The first demo requires no installation, framework, model account, or network
connection:

```bash
python scripts/demo.py
```

You should see a request enter the Gateway, pass through the Agent Loop and
mock adapter, stream `text-delta` and `done` events, and persist a two-message
conversation.

## Run the HTTP example

Start the local server:

```bash
export PAA_DEMO_API_KEY='replace-with-a-local-test-token'
python scripts/run_server.py
```

In another terminal, check the demo host and send a canonical PAA message:

```bash
curl http://127.0.0.1:8000/health

curl -N -X POST http://127.0.0.1:8000/conversations/messages -H 'Content-Type: application/json' -H "X-API-Key: $PAA_DEMO_API_KEY" -d '{"content":[{"type":"text","text":"Explain what PAA is."}]}'
```

The response is a Server-Sent Events stream. `/health` belongs to the local
demo host; the conversation routes are the PAA-facing contract.
The demo accepts the configured owner token as `X-API-Key` or Bearer auth,
rejects requests over 1 MiB, and saves conversations as plain JSON under
`RUNTIME_MEMORY_ROOT` (default `.paa-memory`). This token is for local testing.
To select the included OpenAI-compatible adapter at startup, set
`RUNTIME_PROVIDER_ADAPTER=openai-compatible`, `PAA_MODEL_API_BASE_URL`,
`PAA_MODEL_ID`, `PAA_MODEL_CONTEXT_LIMIT`, and `PAA_MODEL_API_KEY` in the local
environment. The model context limit must be a verified value for that model.

Generate the first local owner token with `openssl rand -hex 24` and keep its
value outside Memory; set `PAA_DEMO_API_KEY` to that value. The server seeds
owner preferences in Memory on first start. To configure multiple
OpenAI-compatible profiles, put this JSON in an untracked file and set
`PAA_ADAPTER_CONFIG_FILE` to its path (replace the model ID and limit with a
verified value):

```json
{"provider_profiles":{"openrouter":{"base_url":"https://openrouter.ai/api/v1","api_key_env":"OPENROUTER_API_KEY","model_context_limits":{"your-model-id":8192}}}}
```

Set `OPENROUTER_API_KEY` in the environment, never in that file or Memory.
The endpoint shown is [OpenRouter's documented API base](https://openrouter.ai/developers).
`PAA_DEFAULT_PROVIDER` and `PAA_MODEL_ID` seed preferences only when no
owner selection exists. To change the selection while the server runs, call
the authenticated Memory preference route:

```bash
curl -X PUT http://127.0.0.1:8000/owner/preferences \
  -H 'Content-Type: application/json' -H "X-API-Key: $PAA_DEMO_API_KEY" \
  -d '{"model":"your-model-id","active_provider_profile":"openrouter"}'
```

The next message uses the selected model and profile without a restart. An
unknown choice produces an error instead of silently selecting a default.

## Install development tools

The runtime has no third-party dependencies. Install the optional development
dependency when you want the full validation command:

```bash
python -m venv .venv
```

Activate the environment, then install the template with its development extra:

```bash
# macOS/Linux
source .venv/bin/activate

# Windows PowerShell equivalent: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Validate the template

Run the live Gateway check from this workspace (it starts the server with a
temporary token and memory root, then verifies auth, SSE, filters, size limits,
and restart persistence):

```bash
node ../paa-conformance-validator/bin/paa-live-target.js --target paa.target.json
```

Run the complete self-contained Python validation path:

```bash
python scripts/validate.py
```

This runs:

1. PAA pin, contract, schema, import-boundary, and provider lock-in checks.
2. mypy static type checking for `src/`.
3. Python syntax compilation.
4. Unit, HTTP integration, conformance, and acceptance suites.

The local validator does not require a PAA checkout. To compare the vendored
contracts against the exact PAA source commit as well, provide a local PAA
checkout and the shared validator:

```bash
python scripts/validate.py \
  --source-checkout /path/to/personal-ai-architecture \
  --shared-validator /path/to/paa-conformance-validator/bin/paa-validate.js
```

The current contract baseline is pinned to:

```text
cfeb96df743feee91afc80ac81f0c4fd9a62c123
```

The shared validator is the external, language-neutral gate. The Python
scripts and tests are the internal implementation gate; both should pass before
publishing a template change.

The included GitHub Actions workflow runs the same checks against the exact
pinned PAA source on every push and pull request.

The executable checks cover this starter's text-message journey and declared component boundaries. Pinning the full PAA contract set does not by itself certify unimplemented product-specific paths such as production authentication, approval policy, or multimodal provider handling.

## PAA request flow

```text
Client
  -> Gateway routes
  -> canonical EngineRequest
  -> Agent Loop
  -> Model Adapter
  -> canonical stream events
  -> SSE response and conversation memory
```

The implementation keeps provider-native payloads inside
`src/paa_template/adapters/`. The Agent Loop and Gateway operate on canonical
PAA message, tool, metadata, and stream shapes.

## Routes

| Method | Route | Purpose |
|---|---|---|
| `POST` | `/conversations/messages` | Start a conversation and stream a response |
| `GET` | `/conversations` | List conversation summaries |
| `GET` | `/conversations/{id}` | Read conversation history |
| `POST` | `/conversations/{id}/messages` | Continue an existing conversation |
| `POST` | `/chat` | Compatibility alias documented as `EXT-001` |
| `GET` | `/health` | Local demo-server health check; not a PAA contract route |

Message requests use the PAA public shape:

```json
{
  "content": [{"type": "text", "text": "Help me plan my finances"}],
  "metadata": {
    "source": "example-client"
  }
}
```

The Gateway requires `X-Actor-ID` and `X-Actor-Permissions` for message
requests. The demo uses simple headers so the boundary is visible; production
authentication and authorization should be supplied by the host application.

## Adapters and providers

`MockAdapter` is deterministic and offline, making the starter safe to run in
CI and in a first local walkthrough. `OpenAICompatibleAdapter` demonstrates
where provider-native `/chat/completions` transport belongs. It accepts an
injected transport rather than requiring credentials or network access in the
template.

To add a provider:

1. Implement the adapter under `src/paa_template/adapters/`.
2. Translate provider payloads into canonical PAA types at that boundary.
3. Register runtime selection in `adapters/loader.py`.
4. Add adapter behavior tests and run `python scripts/validate.py`.

Do not put provider URLs, API keys, model overrides, or provider-shaped tool
payloads into the Gateway or Agent Loop.

## Project layout

```text
src/paa_template/
  adapters/       Provider boundary and adapter loader
  config/         Runtime configuration
  engine/         Provider-neutral Agent Loop
  gateway/        PAA routes, conversation store, and demo HTTP host
  memory/         Memory persistence boundary
  types/          Canonical PAA contracts
scripts/          Demo, server, and validation entry points
tests/
  unit/           Focused component tests
  integration/    Gateway lifecycle and HTTP tests
  conformance/   Contract and boundary tests
contracts/            Local PAA contract mirror
vendor/           Exact pinned PAA contract source
```

## Scope and production notes

This is a reference starter, not a production deployment. The default memory
store is in-process, the mock adapter is intentionally simple, and the
standard-library HTTP host is for demonstration. A production host should add
persistent storage, authentication middleware, operational logging, provider
credentials management, and deployment-specific controls while preserving the
PAA contract boundary.

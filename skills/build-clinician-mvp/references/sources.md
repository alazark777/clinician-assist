# Official guidance used

Checked 2026-09-24; official MCP v2 protocol support rechecked 2026-09-25 at [SDK protocol versions](https://py.sdk.modelcontextprotocol.io/v2/protocol-versions/). This is documentation verification, not a runtime compatibility test. Project-specific choices (paths, budgets, ports, fixture sizes) are engineering decisions, not requirements imposed by these sources. Read the pinned-version documentation when implementing; record deviations rather than silently replacing the stack.

| Source | Applied decision |
|---|---|
| [MCP Streamable HTTP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http) | Separate HTTP server, official SDK wire handling, per-request context, origin validation |
| [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) and [releases](https://github.com/modelcontextprotocol/python-sdk/releases) | Target stable v2 line with exact lockfile version; don't copy v1 session code |
| [MCP tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) | Explicit schemas, validated structured responses, bounded results, tool error separation |
| [MCP security guidance](https://modelcontextprotocol.io/docs/tutorials/security/security_best_practices) | Server-specific audience validation, no token passthrough, untrusted discovery |
| [MCP authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization) | Hosted auth must follow the applicable spec; demo signed tokens are deliberately labeled local fixtures |
| [OpenTelemetry context propagation](https://opentelemetry.io/docs/concepts/context-propagation/) | Correlation across processes, no patient context in baggage |
| [OpenTelemetry sensitive data](https://opentelemetry.io/docs/security/handling-sensitive-data/) | Data minimization and source-side scrubbing, collector filters as a second layer |
| [Collector configuration](https://opentelemetry.io/docs/collector/configuration/) | External collector pipelines, bounded buffers, portable exporters |
| [Anthropic agent evaluations](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents) | Outcome and tool-trace checks, explicit real-model versus stub results |
| [Anthropic tool design](https://www.anthropic.com/engineering/writing-tools-for-agents) | Clear tool purposes, useful structured responses, expected tool-use tests |
| [Anthropic tool-use API](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) | Application-owned client tool execution behind ModelPort; tools run through the local MCP client |
| [Docker bind mounts](https://docs.docker.com/engine/storage/bind-mounts/) | Read-only patient mount, no repository/golden-answer mount |
| [FastAPI CORS](https://fastapi.tiangolo.com/tutorial/cors/) | Explicit localhost web origin rather than wildcard credentialed CORS |
| [Playwright testing](https://playwright.dev/docs/best-practices) | User-visible browser journeys with isolated test data |
| [WHO health AI guidance](https://www.who.int/news/item/18-01-2024-who-releases-ai-ethics-and-governance-guidance-for-large-multi-modal-models) | Defined clinical task and clinician involvement before clinical-use claims |

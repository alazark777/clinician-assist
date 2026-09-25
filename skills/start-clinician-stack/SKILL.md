---
name: start-clinician-stack
description: Starts, stops, restarts, and diagnoses the complete local clinician assistant stack with Podman, Jaeger tracing, records MCP, agent API, and web UI. Use after laptop restart or when the user asks to run or recover the clinician assistant.
disable-model-invocation: true
---

# Start clinician stack

Run the bundled script; do not recreate its steps manually:

```bash
~/.cursor/skills/start-clinician-stack/scripts/clinician-stack.sh start
```

Commands: `start` (default), `stop`, `restart`, `status`, `logs`.

The script:
- starts the Podman machine and the agent observability compose stack;
- sends both Python services to the same OTLP collector and Jaeger UI;
- starts records MCP, agent API, and Vite as independent host processes;
- reuses healthy services, rejects unrelated port occupants, and waits for readiness;
- writes PID files and logs under the kit's ignored `var/runtime/`.

Report the final URLs printed by the script. If it fails, report the failing prerequisite or service and the referenced log path. Never print `.env` contents or provider keys.

Default kit path:
`/Users/alk/Desktop/cc-data-science/Learning/clinician-assist/clinician-assistant-kit`

Override only when needed:

```bash
CLINICIAN_KIT_ROOT=/absolute/path clinician-stack.sh start
```

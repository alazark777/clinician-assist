# Stage C evaluator reports

Run from repository root:

```bash
evaluation/scripts/run_stage_c.sh
```

Artifacts:

- `stage_c_latest.json` — consolidated verdict, counts, extension proofs, and per-case metrics
- `stage_c_report_<timestamp>.json` — immutable run snapshot
- `../../var/evaluation/observations_*.jsonl` — normalized observations used by `grade.py`

Real-model repetitions run only when `MODEL_BACKEND` is explicitly `google`, `openai`, or `custom`, with a non-stub `MODEL_ID` and matching credentials:

| `MODEL_BACKEND` | Required env |
|---|---|
| `google` | `GOOGLE_API_KEY` (Gemini OpenAI-compat base URL is fixed in the agent runtime) |
| `openai` | `OPENAI_API_KEY`; optional `OPENAI_BASE_URL` |
| `custom` | `MODEL_API_KEY`, `MODEL_BASE_URL` |

The harness never infers backend from keys alone (e.g. `OPENAI_API_KEY` without `MODEL_BACKEND=openai`). Stage C reports include `credentials_present` booleans only—never secret values. Otherwise the real-model suite is **skipped**, never passed.

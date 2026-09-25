# Records developer handoff

Own `records-mcp/**`; follow [contracts](../skills/build-clinician-mvp/references/contracts.md) and [sources](../skills/build-clinician-mvp/references/sources.md).

Implement `clinician_records` with SDK-managed protocol handling. Verify algorithm, issuer, audience, and expiry independently per request. Resolve opaque IDs through the authorized patient index; never concatenate IDs into paths or store patient context globally.

Publish strict schemas and versioned `ok`/`empty`/`unavailable`/`denied` envelopes. Separate protocol errors from tool failures using pinned SDK conventions. Enforce 20 IDs/read, 100 inventory records, and 100 KB/result; mark inventory overflow incomplete. Publish inventory `fact_keys` for deterministic selection. Return exact-ID reads atomically; never hide an omitted record in an `ok` batch. Reserve `empty` for a confirmed empty inventory. Preserve source provenance. Unknown fields and unsupported versions fail closed.

Run these commands from `records-mcp/`:

```bash
podman compose -f compose.yaml up --build -d
uv run python -m clinician_records --host 127.0.0.1 --port 8001
uv run pytest tests
```

Podman is the supported container engine. Publish only
`127.0.0.1:8001:8001`; run non-root with read-only root, dropped
capabilities, resource limits, tmpfs `/tmp`, and only the read-only patient
mount. Exclude repository, evals, secrets, and agent SQLite. After the stack is
up, run `scripts/verify_container_isolation.sh` or
`uv run pytest tests/test_container.py`; both skip only when no usable Podman
service is reachable or the service is not running. Process-only debugging
cannot pass isolation acceptance.

Environment names appear in README; `PATIENT_DATA_DIR` locates records and `MCP_VERIFICATION_KEY` supplies public verification material. Test token failures, interleaving, limits, origin validation, traversal, and denied writes/mount access. Diagnose empty versus unavailable using the envelope and safe error codes.

Extend typed registrations and reviewed client allowlists; keep count/ping test-only by default. Submit reproducible isolation/contract results to the tester, then obtain human stage acceptance.

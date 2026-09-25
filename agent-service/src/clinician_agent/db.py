"""SQLite persistence and migrations."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import aiosqlite

from clinician_agent.schemas import (
    FeedbackDecision,
    Profile,
    ProfileRequest,
    ProfileResponse,
    RunStatus,
    Source,
    Usage,
)
from clinician_agent.util import utc_now

logger = logging.getLogger(__name__)

MIGRATION_VERSION = 1


@dataclass(frozen=True)
class RunRow:
    """Durable run state."""

    run_id: str
    caller_id: str
    request_id: str
    input_hash: str
    patient_id: str
    visit_context: str
    as_of: date
    run_status: RunStatus
    profile_id: str | None
    error_code: str | None
    trace_id: str
    usage: Usage | None


@dataclass(frozen=True)
class ProfileRow:
    """Saved profile envelope."""

    profile_id: str
    run_id: str
    caller_id: str
    patient_id: str
    profile_version: int
    review_status: str
    review_revision: int
    profile: Profile
    sources: list[Source]
    usage: Usage


class Database:
    """Async SQLite access without cross-external transactions."""

    def __init__(self, path: Path) -> None:
        """Bind a database file path."""
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def path(self) -> Path:
        """Return the database path."""
        return self._path

    async def connect(self) -> None:
        """Open the database and apply migrations."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._apply_migrations()

    async def close(self) -> None:
        """Close the connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def _apply_migrations(self) -> None:
        """Run pending SQL migrations."""
        assert self._conn is not None
        migration_path = Path(__file__).resolve().parents[2] / "migrations" / "001_initial.sql"
        sql = migration_path.read_text(encoding="utf-8")
        await self._conn.executescript(sql)
        now = utc_now().isoformat()
        await self._conn.execute(
            "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
            (MIGRATION_VERSION, now),
        )
        await self._conn.commit()

    async def mark_interrupted_runs(self) -> int:
        """Mark in-flight runs interrupted on process restart."""
        assert self._conn is not None
        now = utc_now().isoformat()
        cursor = await self._conn.execute(
            """
            UPDATE runs
            SET run_status = ?, updated_at = ?
            WHERE run_status = ?
            """,
            (RunStatus.INTERRUPTED.value, now, RunStatus.RUNNING.value),
        )
        await self._conn.commit()
        return cursor.rowcount

    async def claim_run(
        self,
        *,
        run_id: str,
        caller_id: str,
        request_id: str,
        input_hash: str,
        body: ProfileRequest,
        trace_id: str,
    ) -> tuple[RunRow | None, str]:
        """Atomically claim a run; returns existing row or None after insert."""
        assert self._conn is not None
        existing = await self.get_run_by_request(caller_id, request_id)
        if existing is not None:
            return existing, "existing"
        now = utc_now().isoformat()
        try:
            await self._conn.execute(
                """
                INSERT INTO runs (
                    run_id, caller_id, request_id, input_hash, patient_id,
                    visit_context, as_of, run_status, profile_id, error_code,
                    trace_id, usage_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, NULL, ?, ?)
                """,
                (
                    run_id,
                    caller_id,
                    request_id,
                    input_hash,
                    body.patient_id,
                    body.visit_context,
                    body.as_of.isoformat(),
                    RunStatus.RUNNING.value,
                    trace_id,
                    now,
                    now,
                ),
            )
            await self._conn.commit()
        except aiosqlite.IntegrityError:
            existing = await self.get_run_by_request(caller_id, request_id)
            return existing, "existing"
        row = await self.get_run(run_id)
        assert row is not None
        return row, "created"

    async def get_run_by_request(self, caller_id: str, request_id: str) -> RunRow | None:
        """Fetch a run by idempotency key."""
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT * FROM runs WHERE caller_id = ? AND request_id = ?",
            (caller_id, request_id),
        )
        row = await cursor.fetchone()
        return self._row_to_run(row) if row else None

    async def get_run(self, run_id: str) -> RunRow | None:
        """Fetch a run by identifier."""
        assert self._conn is not None
        cursor = await self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,))
        row = await cursor.fetchone()
        return self._row_to_run(row) if row else None

    async def count_active_runs(self) -> int:
        """Count runs still executing."""
        assert self._conn is not None
        cursor = await self._conn.execute(
            "SELECT COUNT(*) AS count FROM runs WHERE run_status = ?",
            (RunStatus.RUNNING.value,),
        )
        row = await cursor.fetchone()
        return int(row["count"]) if row else 0

    async def complete_run(
        self,
        *,
        run_id: str,
        profile_id: str,
        usage: Usage,
    ) -> None:
        """Mark a run completed."""
        assert self._conn is not None
        now = utc_now().isoformat()
        await self._conn.execute(
            """
            UPDATE runs
            SET run_status = ?, profile_id = ?, usage_json = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (
                RunStatus.COMPLETED.value,
                profile_id,
                usage.model_dump_json(),
                now,
                run_id,
            ),
        )
        await self._conn.commit()

    async def fail_run(self, *, run_id: str, error_code: str) -> None:
        """Mark a run failed."""
        assert self._conn is not None
        now = utc_now().isoformat()
        await self._conn.execute(
            """
            UPDATE runs
            SET run_status = ?, error_code = ?, updated_at = ?
            WHERE run_id = ?
            """,
            (RunStatus.FAILED.value, error_code, now, run_id),
        )
        await self._conn.commit()

    async def save_profile(
        self,
        *,
        profile_id: str,
        run_id: str,
        caller_id: str,
        patient_id: str,
        profile: Profile,
        sources: list[Source],
        usage: Usage,
    ) -> ProfileRow:
        """Persist a generated profile."""
        assert self._conn is not None
        now = utc_now().isoformat()
        await self._conn.execute(
            """
            INSERT INTO profiles (
                profile_id, run_id, caller_id, patient_id, profile_version,
                review_status, review_revision, profile_json, sources_json,
                usage_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 1, 'draft', 0, ?, ?, ?, ?, ?)
            """,
            (
                profile_id,
                run_id,
                caller_id,
                patient_id,
                profile.model_dump_json(),
                json.dumps([source.model_dump(mode="json") for source in sources]),
                usage.model_dump_json(),
                now,
                now,
            ),
        )
        await self._conn.commit()
        row = await self.get_profile(profile_id)
        assert row is not None
        return row

    async def get_profile(self, profile_id: str) -> ProfileRow | None:
        """Load a saved profile."""
        assert self._conn is not None
        cursor = await self._conn.execute("SELECT * FROM profiles WHERE profile_id = ?", (profile_id,))
        row = await cursor.fetchone()
        if not row:
            return None
        profile = Profile.model_validate_json(row["profile_json"])
        sources_raw = json.loads(row["sources_json"])
        sources = [Source.model_validate(item) for item in sources_raw]
        usage = Usage.model_validate_json(row["usage_json"])
        return ProfileRow(
            profile_id=row["profile_id"],
            run_id=row["run_id"],
            caller_id=row["caller_id"],
            patient_id=row["patient_id"],
            profile_version=int(row["profile_version"]),
            review_status=row["review_status"],
            review_revision=int(row["review_revision"]),
            profile=profile,
            sources=sources,
            usage=usage,
        )

    async def apply_feedback(
        self,
        *,
        profile_id: str,
        expected_profile_version: int,
        expected_review_revision: int,
        decision: FeedbackDecision,
        actor: str,
        comment: str | None,
    ) -> ProfileRow:
        """Apply version-bound feedback atomically."""
        assert self._conn is not None
        profile = await self.get_profile(profile_id)
        if profile is None:
            raise KeyError("profile_not_found")
        if profile.profile_version != expected_profile_version:
            raise ValueError("profile_version_conflict")
        if profile.review_revision != expected_review_revision:
            raise ValueError("review_revision_conflict")
        review_status = "accepted" if decision == FeedbackDecision.ACCEPT else "needs_correction"
        new_revision = profile.review_revision + 1
        now = utc_now().isoformat()
        await self._conn.execute(
            """
            UPDATE profiles
            SET review_status = ?, review_revision = ?, updated_at = ?
            WHERE profile_id = ? AND profile_version = ? AND review_revision = ?
            """,
            (review_status, new_revision, now, profile_id, expected_profile_version, expected_review_revision),
        )
        await self._conn.execute(
            """
            INSERT INTO audit_events(actor, run_id, profile_id, action, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                actor,
                profile.run_id,
                profile_id,
                f"feedback.{decision.value}",
                json.dumps({"comment": comment}),
                now,
            ),
        )
        await self._conn.commit()
        updated = await self.get_profile(profile_id)
        assert updated is not None
        return updated

    async def save_source_snapshots(self, *, run_id: str, records: list[dict[str, Any]]) -> None:
        """Persist read record snapshots for a run."""
        assert self._conn is not None
        now = utc_now().isoformat()
        for record in records:
            await self._conn.execute(
                """
                INSERT OR REPLACE INTO source_snapshots(
                    run_id, record_id, version, record_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    record["record_id"],
                    int(record["version"]),
                    json.dumps(record),
                    now,
                ),
            )
        await self._conn.commit()

    async def append_audit(
        self,
        *,
        actor: str,
        action: str,
        run_id: str | None = None,
        profile_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """Append a non-clinical audit event."""
        assert self._conn is not None
        await self._conn.execute(
            """
            INSERT INTO audit_events(actor, run_id, profile_id, action, detail_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                actor,
                run_id,
                profile_id,
                action,
                json.dumps(detail or {}),
                utc_now().isoformat(),
            ),
        )
        await self._conn.commit()

    def _row_to_run(self, row: aiosqlite.Row) -> RunRow:
        """Convert a SQLite row to a run dataclass."""
        usage = Usage.model_validate_json(row["usage_json"]) if row["usage_json"] else None
        return RunRow(
            run_id=row["run_id"],
            caller_id=row["caller_id"],
            request_id=row["request_id"],
            input_hash=row["input_hash"],
            patient_id=row["patient_id"],
            visit_context=row["visit_context"],
            as_of=date.fromisoformat(row["as_of"]),
            run_status=RunStatus(row["run_status"]),
            profile_id=row["profile_id"],
            error_code=row["error_code"],
            trace_id=row["trace_id"],
            usage=usage,
        )

    def to_profile_response(self, row: ProfileRow, *, trace_id: str) -> ProfileResponse:
        """Map a profile row to the public response envelope."""
        return ProfileResponse(
            profile_id=row.profile_id,
            run_id=row.run_id,
            trace_id=trace_id,
            profile_version=row.profile_version,
            review_status=row.review_status,  # type: ignore[arg-type]
            review_revision=row.review_revision,
            profile=row.profile,
            usage=row.usage,
        )

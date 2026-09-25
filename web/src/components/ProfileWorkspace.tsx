import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  createProfile,
  deleteDemoSession,
  getProfile,
  listPatients,
  pollUntilProfile,
  submitFeedback,
} from "../api/client";
import type {
  PatientSummary,
  ProfileResponse,
  RunResponse,
} from "../api/types";
import { useGenerationSession } from "../hooks/useGenerationSession";
import { toSafeUserError, type SafeUserError } from "../utils/errors";
import {
  normalizeProfileId,
  readLastProfileId,
  rememberLastProfileId,
} from "../utils/lastProfileId";
import { ErrorBanner } from "./ErrorBanner";
import { FactsPanel } from "./FactsPanel";
import { FeedbackPanel } from "./FeedbackPanel";
import { GapsConflictsPanel } from "./GapsConflictsPanel";
import { SourcesPanel } from "./SourcesPanel";

/** Synthetic patient fixtures use 2026 dates; must be on/after record event dates. */
const DEFAULT_AS_OF = "2026-12-01";

interface ProfileWorkspaceProps {
  onLoggedOut: () => void;
}

export function ProfileWorkspace({ onLoggedOut }: ProfileWorkspaceProps) {
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  const [patientId, setPatientId] = useState("");
  const [visitContext, setVisitContext] = useState(
    "Diabetes pre-visit medication and lab review",
  );
  const [asOf, setAsOf] = useState(DEFAULT_AS_OF);
  const [profile, setProfile] = useState<ProfileResponse | null>(null);
  const [runState, setRunState] = useState<RunResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<SafeUserError | null>(null);
  const [reloadId, setReloadId] = useState(() => readLastProfileId());
  const [interruptedRunId, setInterruptedRunId] = useState<string | null>(null);

  const { resolveRequestId } = useGenerationSession();
  const abortRef = useRef<AbortController | null>(null);
  const activePatientRef = useRef("");

  const cancelInFlight = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    listPatients(controller.signal)
      .then((items) => {
        setPatients(items);
        if (items.length > 0) {
          setPatientId((current) => current || items[0].patient_id);
        }
      })
      .catch((err) => setError(toSafeUserError(err)));
    return () => controller.abort();
  }, []);

  const applyProfileIfCurrent = useCallback(
    (next: ProfileResponse, expectedPatientId: string) => {
      if (activePatientRef.current !== expectedPatientId) {
        return;
      }
      setProfile(next);
      rememberLastProfileId(next.profile_id);
      setReloadId(next.profile_id);
      setRunState(null);
      setInterruptedRunId(null);
    },
    [],
  );

  async function runGeneration(forceNewRequestId: boolean) {
    if (!patientId) {
      setError({
        title: "Select a patient",
        detail: "Choose an authorized patient before generating a profile.",
      });
      return;
    }

    cancelInFlight();
    const controller = new AbortController();
    abortRef.current = controller;
    activePatientRef.current = patientId;
    setBusy(true);
    setError(null);
    setRunState(null);
    setInterruptedRunId(null);

    const requestId = resolveRequestId(
      { patientId, visitContext, asOf },
      forceNewRequestId,
    );

    try {
      const outcome = await createProfile(
        {
          patient_id: patientId,
          visit_context: visitContext,
          as_of: asOf,
          request_id: requestId,
        },
        controller.signal,
      );

      if (outcome.kind === "profile") {
        applyProfileIfCurrent(outcome.profile, patientId);
        return;
      }

      if (outcome.kind === "interrupted") {
        setInterruptedRunId(outcome.runId);
        setError(toSafeUserError(new Error(outcome.message), outcome.runId));
        return;
      }

      setRunState({
        run_id: outcome.runId,
        run_status: "running",
        profile_id: null,
        error_code: null,
      });

      const completed = await pollUntilProfile(
        outcome.runId,
        outcome.pollPath,
        controller.signal,
        (tick) => setRunState(tick),
      );
      applyProfileIfCurrent(completed, patientId);
    } catch (err) {
      if (controller.signal.aborted) {
        return;
      }
      setError(toSafeUserError(err, runState?.run_id));
    } finally {
      if (abortRef.current === controller) {
        abortRef.current = null;
      }
      setBusy(false);
    }
  }

  function handlePatientChange(nextId: string) {
    cancelInFlight();
    activePatientRef.current = nextId;
    setPatientId(nextId);
    setProfile(null);
    setRunState(null);
    setError(null);
    setInterruptedRunId(null);
  }

  async function handleReload(event: FormEvent) {
    event.preventDefault();
    const profileId = normalizeProfileId(reloadId);
    if (!profileId) {
      return;
    }
    if (profileId.startsWith("run_")) {
      setError({
        title: "Wrong ID type",
        detail:
          "Reload needs the Profile ID (prof_… from the heading), not the Run ID (run_…).",
      });
      return;
    }
    cancelInFlight();
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setError(null);
    try {
      const loaded = await getProfile(profileId, controller.signal);
      activePatientRef.current = loaded.profile.patient_id;
      setPatientId(loaded.profile.patient_id);
      setProfile(loaded);
      rememberLastProfileId(loaded.profile_id);
      setReloadId(loaded.profile_id);
    } catch (err) {
      if (!controller.signal.aborted) {
        const safe = toSafeUserError(err);
        if (safe.code === "not_found" || safe.title === "Request failed") {
          setError({
            title: "Profile not found",
            detail:
              "No saved profile for this ID with your demo session. Use a prof_… ID from a prior generate on the same agent database (AGENT_DB_PATH), or generate again.",
            code: safe.code,
          });
        } else {
          setError(safe);
        }
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  async function handleLogout() {
    cancelInFlight();
    try {
      await deleteDemoSession();
    } catch {
      /* still clear local state */
    }
    setProfile(null);
    onLoggedOut();
  }

  async function handleFeedback(
    decision: "accept" | "needs_correction",
    comment: string,
  ) {
    if (!profile) {
      return;
    }
    cancelInFlight();
    const controller = new AbortController();
    abortRef.current = controller;
    setBusy(true);
    setError(null);
    const expectedPatient = profile.profile.patient_id;
    try {
      const updated = await submitFeedback(
        profile.profile_id,
        {
          profile_version: profile.profile_version,
          review_revision: profile.review_revision,
          decision,
          comment: comment || null,
        },
        controller.signal,
      );
      if (activePatientRef.current !== expectedPatient) {
        return;
      }
      setProfile({
        ...profile,
        review_status: updated.review_status,
        review_revision: updated.review_revision,
        profile_version: updated.profile_version,
      });
    } catch (err) {
      if (!controller.signal.aborted) {
        setError(toSafeUserError(err, profile.run_id));
      }
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  const retrievalLabel =
    profile?.profile.status === "incomplete"
      ? "Retrieval incomplete — review gaps before clinical use"
      : profile?.profile.status === "complete"
        ? "Retrieval complete"
        : null;

  return (
    <div className="workspace" data-testid="profile-workspace">
      <header className="app-header">
        <div>
          <h1>Pre-visit profile (demo)</h1>
          <p className="subtitle">
            Draft only — acceptance records demo review; source records are never
            modified.
          </p>
        </div>
        <button type="button" className="secondary" onClick={handleLogout}>
          Sign out
        </button>
      </header>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      <section className="panel controls" aria-labelledby="controls-heading">
        <h2 id="controls-heading">Visit context</h2>
        <div className="grid-two">
          <label>
            Patient
            <select
              value={patientId}
              onChange={(e) => handlePatientChange(e.target.value)}
              data-testid="patient-select"
            >
              {patients.map((p) => (
                <option key={p.patient_id} value={p.patient_id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            As of
            <input
              type="date"
              value={asOf}
              onChange={(e) => setAsOf(e.target.value)}
              data-testid="as-of-input"
            />
            <span className="field-hint">
              Only records on or before this date are included. Demo data is dated in 2026.
            </span>
          </label>
        </div>
        <label>
          Visit context
          <textarea
            value={visitContext}
            onChange={(e) => setVisitContext(e.target.value)}
            rows={3}
            data-testid="visit-context-input"
          />
        </label>
        <div className="button-row">
          <button
            type="button"
            onClick={() => void runGeneration(false)}
            disabled={busy}
            data-testid="generate-profile"
          >
            {busy ? "Working…" : "Generate profile"}
          </button>
          {interruptedRunId ? (
            <button
              type="button"
              className="secondary"
              onClick={() => void runGeneration(true)}
              disabled={busy}
              data-testid="restart-run"
            >
              Restart with new request ID
            </button>
          ) : null}
          {busy ? (
            <button
              type="button"
              className="secondary"
              onClick={cancelInFlight}
              data-testid="cancel-request"
            >
              Cancel
            </button>
          ) : null}
        </div>
        {runState?.run_status === "running" ? (
          <p className="status-line" data-testid="run-status">
            Run in progress — ID {runState.run_id}. Polling; work is not restarted
            automatically.
          </p>
        ) : null}
      </section>

      <section className="panel" aria-labelledby="reload-heading">
        <h2 id="reload-heading">Reload saved profile</h2>
        <form className="inline-form" onSubmit={handleReload}>
          <label>
            Profile ID
            <input
              value={reloadId}
              onChange={(e) => setReloadId(e.target.value)}
              placeholder="prof_…"
              data-testid="reload-profile-id"
            />
            <span className="field-hint">
              Profile ID from the heading (prof_…), not Run ID. Last generated ID is remembered
              for this browser tab session after refresh.
            </span>
          </label>
          <button type="submit" disabled={busy} data-testid="reload-profile">
            Reload
          </button>
        </form>
      </section>

      {profile ? (
        <section className="panel profile-panel" data-testid="profile-panel">
          <header className="profile-meta">
            <div>
              <h2>Profile {profile.profile_id}</h2>
              <p data-testid="profile-run-id">Run ID: {profile.run_id}</p>
              {retrievalLabel ? (
                <p className="status-line" data-testid="retrieval-status">
                  {retrievalLabel}
                </p>
              ) : null}
            </div>
            <div className="badges">
              <span className="badge" data-testid="review-status">
                Review: {profile.review_status}
              </span>
              <span className="badge muted">
                v{profile.profile_version} / rev {profile.review_revision}
              </span>
            </div>
          </header>

          <FactsPanel facts={profile.profile.facts} sources={profile.profile.sources} />
          <GapsConflictsPanel
            gaps={profile.profile.gaps}
            conflicts={profile.profile.conflicts}
          />
          <SourcesPanel sources={profile.profile.sources} />
          <FeedbackPanel
            disabled={busy}
            reviewStatus={profile.review_status}
            onSubmit={handleFeedback}
          />
        </section>
      ) : null}
    </div>
  );
}

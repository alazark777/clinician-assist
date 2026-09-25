import type {
  CreateProfileResult,
  DemoLogin,
  FeedbackRequest,
  FeedbackResponse,
  PatientSummary,
  ProfileRequest,
  ProfileResponse,
  RunResponse,
} from "./types";
import { AgentApiError } from "../utils/errors";
import { logLifecycle } from "../utils/safeLog";

function baseUrl(): string {
  const url = import.meta.env.VITE_AGENT_API_BASE_URL;
  if (!url) {
    throw new Error("VITE_AGENT_API_BASE_URL is not configured");
  }
  return url.replace(/\/$/, "");
}

async function parseError(response: Response): Promise<AgentApiError> {
  let body: { code: string; message: string } | null = null;
  try {
    body = (await response.json()) as { code: string; message: string };
  } catch {
    body = null;
  }
  const runHeader = response.headers.get("X-Run-Id") ?? undefined;
  return new AgentApiError(
    response.status,
    body?.message ?? response.statusText,
    body,
    runHeader,
  );
}

async function fetchJson<T>(
  path: string,
  init: RequestInit & { signal?: AbortSignal },
): Promise<{ data: T; response: Response }> {
  const response = await fetch(`${baseUrl()}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  const data = (await response.json()) as T;
  return { data, response };
}

async function fetchVoid(
  path: string,
  init: RequestInit & { signal?: AbortSignal },
): Promise<void> {
  const response = await fetch(`${baseUrl()}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!response.ok) {
    throw await parseError(response);
  }
}

export async function createDemoSession(
  login: DemoLogin,
  signal?: AbortSignal,
): Promise<void> {
  await fetchVoid("/v1/demo/session", {
    method: "POST",
    body: JSON.stringify(login),
    signal,
  });
  logLifecycle("demo_session_created");
}

export async function deleteDemoSession(signal?: AbortSignal): Promise<void> {
  await fetchVoid("/v1/demo/session", {
    method: "DELETE",
    signal,
  });
  logLifecycle("demo_session_deleted");
}

export async function listPatients(
  signal?: AbortSignal,
): Promise<PatientSummary[]> {
  const { data } = await fetchJson<PatientSummary[]>("/v1/patients", {
    method: "GET",
    signal,
  });
  return data;
}

function pollPathFromLocation(location: string | null, runId: string): string {
  if (location) {
    try {
      const parsed = new URL(location, baseUrl());
      return parsed.pathname;
    } catch {
      /* fall through */
    }
  }
  return `/v1/runs/${runId}`;
}

export async function createProfile(
  request: ProfileRequest,
  signal?: AbortSignal,
): Promise<CreateProfileResult> {
  const response = await fetch(`${baseUrl()}/v1/profiles`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
    signal,
  });

  if (response.status === 200) {
    const profile = (await response.json()) as ProfileResponse;
    logLifecycle("profile_ready", { run_id: profile.run_id });
    return { kind: "profile", profile };
  }

  if (response.status === 202) {
    const running = (await response.json()) as {
      run_id: string;
      run_status: "running";
      profile_id: null;
    };
    const pollPath = pollPathFromLocation(
      response.headers.get("Location"),
      running.run_id,
    );
    logLifecycle("profile_running", { run_id: running.run_id });
    return { kind: "running", runId: running.run_id, pollPath };
  }

  if (response.status === 409) {
    const body = (await response.json()) as { code: string; message: string };
    const runId = response.headers.get("X-Run-Id") ?? undefined;
    if (body.code === "run_interrupted") {
      return {
        kind: "interrupted",
        runId: runId ?? "unknown",
        code: body.code,
        message: body.message,
      };
    }
    throw new AgentApiError(409, body.message, body, runId);
  }

  throw await parseError(response);
}

export async function getRun(
  runId: string,
  signal?: AbortSignal,
): Promise<RunResponse> {
  const { data } = await fetchJson<RunResponse>(`/v1/runs/${runId}`, {
    method: "GET",
    signal,
  });
  return data;
}

export async function getProfile(
  profileId: string,
  signal?: AbortSignal,
): Promise<ProfileResponse> {
  const { data } = await fetchJson<ProfileResponse>(`/v1/profiles/${profileId}`, {
    method: "GET",
    signal,
  });
  return data;
}

export async function submitFeedback(
  profileId: string,
  body: FeedbackRequest,
  signal?: AbortSignal,
): Promise<FeedbackResponse> {
  const { data } = await fetchJson<FeedbackResponse>(
    `/v1/profiles/${profileId}/feedback`,
    {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    },
  );
  logLifecycle("feedback_submitted", { profile_id: profileId });
  return data;
}

export const POLL_INTERVAL_MS = 800;

export async function pollUntilProfile(
  runId: string,
  pollPath: string,
  signal: AbortSignal,
  onTick?: (run: RunResponse) => void,
): Promise<ProfileResponse> {
  const normalizedPath = pollPath.startsWith("/") ? pollPath : `/v1/runs/${runId}`;

  while (!signal.aborted) {
    const response = await fetch(`${baseUrl()}${normalizedPath}`, {
      method: "GET",
      credentials: "include",
      signal,
    });
    if (!response.ok) {
      throw await parseError(response);
    }
    const run = (await response.json()) as RunResponse;
    onTick?.(run);

    if (run.run_status === "completed" && run.profile_id) {
      return getProfile(run.profile_id, signal);
    }
    if (run.run_status === "failed") {
      throw new AgentApiError(
        502,
        "Profile generation failed",
        { code: run.error_code ?? "run_failed", message: "Run failed" },
        runId,
      );
    }
    if (run.run_status === "interrupted") {
      throw new AgentApiError(
        409,
        "Run interrupted",
        { code: "run_interrupted", message: "Run interrupted" },
        runId,
      );
    }

    await new Promise((resolve, reject) => {
      const timer = window.setTimeout(resolve, POLL_INTERVAL_MS);
      signal.addEventListener(
        "abort",
        () => {
          window.clearTimeout(timer);
          reject(new DOMException("Aborted", "AbortError"));
        },
        { once: true },
      );
    });
  }

  throw new DOMException("Aborted", "AbortError");
}

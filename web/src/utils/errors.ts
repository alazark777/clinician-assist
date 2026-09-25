import type { ApiErrorBody } from "../api/types";

/** Safe, non-clinical error shown in the UI. */
export interface SafeUserError {
  title: string;
  detail: string;
  runId?: string;
  code?: string;
}

export class AgentApiError extends Error {
  readonly status: number;
  readonly body: ApiErrorBody | null;
  readonly runId?: string;

  constructor(
    status: number,
    message: string,
    body: ApiErrorBody | null = null,
    runId?: string,
  ) {
    super(message);
    this.name = "AgentApiError";
    this.status = status;
    this.body = body;
    this.runId = runId;
  }
}

export function toSafeUserError(error: unknown, runId?: string): SafeUserError {
  if (error instanceof DOMException && error.name === "AbortError") {
    return {
      title: "Request cancelled",
      detail: "The request was cancelled because you changed context or started a new action.",
      runId,
    };
  }

  if (error instanceof AgentApiError) {
    const code = error.body?.code;
    const resolvedRunId = error.runId ?? runId;
    switch (error.status) {
      case 403:
        return {
          title: "Not authorized",
          detail:
            "You do not have access to this patient or profile. Check your demo session.",
          runId: resolvedRunId,
          code,
        };
      case 422:
        return {
          title: "Invalid request",
          detail: "The server rejected the input. Adjust the form and try again.",
          runId: resolvedRunId,
          code,
        };
      case 409:
        if (code === "run_interrupted") {
          return {
            title: "Run interrupted",
            detail:
              "This run was interrupted. Use restart with a new request ID to generate again.",
            runId: resolvedRunId,
            code,
          };
        }
        if (code === "stale_review" || code === "version_conflict") {
          return {
            title: "Review out of date",
            detail:
              "Feedback versions no longer match the saved profile. Reload the profile and try again.",
            runId: resolvedRunId,
            code,
          };
        }
        return {
          title: "Conflict",
          detail:
            error.body?.message ??
            "The request conflicted with server state. Reload or change inputs.",
          runId: resolvedRunId,
          code,
        };
      case 429:
        return {
          title: "Server busy",
          detail: "Too many active runs. Wait and retry with the same request ID if needed.",
          runId: resolvedRunId,
          code,
        };
      case 502:
        return {
          title: "Dependency error",
          detail:
            "A downstream service returned invalid data. Share the run ID with support diagnostics.",
          runId: resolvedRunId,
          code,
        };
      case 503:
        return {
          title: "Service unavailable",
          detail:
            "The agent could not reach required dependencies. Saved profiles may still be readable.",
          runId: resolvedRunId,
          code,
        };
      default:
        return {
          title: "Request failed",
          detail: error.body?.message ?? "An unexpected error occurred.",
          runId: resolvedRunId,
          code,
        };
    }
  }

  if (error instanceof TypeError) {
    return {
      title: "Network error",
      detail:
        "Could not reach the agent API. Confirm the service is running and the base URL is correct.",
      runId,
    };
  }

  return {
    title: "Unexpected error",
    detail: "Something went wrong. Try again or reload the page.",
    runId,
  };
}

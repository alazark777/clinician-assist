import type { SafeUserError } from "../utils/errors";

interface ErrorBannerProps {
  error: SafeUserError | null;
  onDismiss?: () => void;
}

export function ErrorBanner({ error, onDismiss }: ErrorBannerProps) {
  if (!error) {
    return null;
  }
  return (
    <div className="banner banner-error" role="alert" data-testid="error-banner">
      <strong>{error.title}</strong>
      <p>{error.detail}</p>
      {error.runId ? (
        <p className="run-id" data-testid="error-run-id">
          Run ID: {error.runId}
        </p>
      ) : null}
      {onDismiss ? (
        <button type="button" className="secondary" onClick={onDismiss}>
          Dismiss
        </button>
      ) : null}
    </div>
  );
}

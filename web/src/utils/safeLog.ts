/** Logs only safe lifecycle events — never clinical payloads or patient identifiers. */

export function logLifecycle(event: string, details?: Record<string, string>): void {
  if (import.meta.env.DEV) {
    const payload = details ? ` ${JSON.stringify(details)}` : "";
    // eslint-disable-next-line no-console
    console.info(`[clinician-web] ${event}${payload}`);
  }
}

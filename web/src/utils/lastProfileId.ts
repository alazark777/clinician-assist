const STORAGE_KEY = "clinician_demo_last_profile_id";

/** Normalize pasted profile id (strip labels / whitespace). */
export function normalizeProfileId(raw: string): string {
  let id = raw.trim();
  if (/^profile\s+/i.test(id)) {
    id = id.replace(/^profile\s+/i, "").trim();
  }
  return id;
}

export function readLastProfileId(): string {
  try {
    return sessionStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function rememberLastProfileId(profileId: string): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, profileId);
  } catch {
    /* ignore quota / private mode */
  }
}

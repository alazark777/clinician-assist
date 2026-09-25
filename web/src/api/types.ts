export type FactSection =
  | "condition"
  | "medication"
  | "allergy"
  | "lab"
  | "vital";

export type ProfileCompleteness = "complete" | "incomplete";

export type ReviewStatus = "draft" | "accepted" | "needs_correction";

export type RunLifecycle = "running" | "completed" | "failed" | "interrupted";

export interface PatientSummary {
  patient_id: string;
  label: string;
}

export interface Fact {
  section: FactSection;
  key: string;
  value: string;
  date: string | null;
  qualifier: string;
  source_ids: string[];
}

export interface Gap {
  code: string;
  text: string;
}

export interface Conflict {
  code: string;
  text: string;
  source_ids: string[];
}

export interface Source {
  record_id: string;
  version: number;
  excerpt: string;
}

export interface Profile {
  patient_id: string;
  status: ProfileCompleteness;
  facts: Fact[];
  gaps: Gap[];
  conflicts: Conflict[];
  sources: Source[];
}

export interface Usage {
  model_calls: number;
  tool_attempts: number;
  additional_record_ids: number;
  input_tokens: number | null;
  output_tokens: number | null;
}

export interface ProfileResponse {
  profile_id: string;
  run_id: string;
  trace_id: string;
  profile_version: number;
  review_status: ReviewStatus;
  review_revision: number;
  profile: Profile;
  usage: Usage;
}

export interface ProfileRequest {
  patient_id: string;
  visit_context: string;
  as_of: string;
  request_id: string;
}

export interface RunningResponse {
  run_id: string;
  run_status: "running";
  profile_id: null;
}

export interface RunResponse {
  run_id: string;
  run_status: RunLifecycle;
  profile_id: string | null;
  error_code: string | null;
}

export type FeedbackDecision = "accept" | "needs_correction";

export interface FeedbackRequest {
  profile_version: number;
  review_revision: number;
  decision: FeedbackDecision;
  comment?: string | null;
}

export interface FeedbackResponse {
  profile_id: string;
  profile_version: number;
  review_status: "accepted" | "needs_correction";
  review_revision: number;
}

export interface ApiErrorBody {
  code: string;
  message: string;
}

export interface DemoLogin {
  username: string;
  passphrase: string;
}

export type CreateProfileResult =
  | { kind: "profile"; profile: ProfileResponse }
  | { kind: "running"; runId: string; pollPath: string }
  | { kind: "interrupted"; runId: string; code: string; message: string };

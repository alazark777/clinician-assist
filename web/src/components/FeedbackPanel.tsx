import { FormEvent, useState } from "react";
import type { ReviewStatus } from "../api/types";

interface FeedbackPanelProps {
  reviewStatus: ReviewStatus;
  disabled: boolean;
  onSubmit: (decision: "accept" | "needs_correction", comment: string) => void;
}

export function FeedbackPanel({ reviewStatus, disabled, onSubmit }: FeedbackPanelProps) {
  const [comment, setComment] = useState("");

  function handle(decision: "accept" | "needs_correction") {
    onSubmit(decision, comment);
  }

  function handleForm(event: FormEvent) {
    event.preventDefault();
    handle("accept");
  }

  return (
    <section aria-labelledby="feedback-heading" data-testid="feedback-panel">
      <h3 id="feedback-heading">Clinician review (demo)</h3>
      <p className="muted">
        Accept or mark needs correction. This records demo review only — no orders,
        diagnoses, or record writes.
      </p>
      <form onSubmit={handleForm}>
        <label>
          Comment (optional)
          <textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={2}
            data-testid="feedback-comment"
          />
        </label>
        <div className="button-row">
          <button
            type="button"
            disabled={disabled}
            onClick={() => handle("accept")}
            data-testid="feedback-accept"
          >
            Accept draft
          </button>
          <button
            type="button"
            className="secondary"
            disabled={disabled}
            onClick={() => handle("needs_correction")}
            data-testid="feedback-needs-correction"
          >
            Needs correction
          </button>
        </div>
      </form>
      <p className="status-line" data-testid="feedback-current-status">
        Current review status: {reviewStatus}
      </p>
    </section>
  );
}

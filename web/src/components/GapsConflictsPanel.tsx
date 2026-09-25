import type { Conflict, Gap } from "../api/types";
import { SafeText } from "./SafeText";

interface GapsConflictsPanelProps {
  gaps: Gap[];
  conflicts: Conflict[];
}

export function GapsConflictsPanel({ gaps, conflicts }: GapsConflictsPanelProps) {
  return (
    <section aria-labelledby="uncertainty-heading">
      <h3 id="uncertainty-heading">Gaps and conflicts</h3>
      {gaps.length === 0 && conflicts.length === 0 ? (
        <p className="muted">No explicit gaps or conflicts reported.</p>
      ) : null}
      {gaps.length > 0 ? (
        <div data-testid="gaps-list">
          <h4>Evidence gaps</h4>
          <ul>
            {gaps.map((gap) => (
              <li key={gap.code}>
                <code>{gap.code}</code>: <SafeText text={gap.text} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {conflicts.length > 0 ? (
        <div data-testid="conflicts-list">
          <h4>Conflicts (both retained)</h4>
          <ul>
            {conflicts.map((conflict) => (
              <li key={conflict.code}>
                <code>{conflict.code}</code>: <SafeText text={conflict.text} /> (
                {conflict.source_ids.join(", ")})
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

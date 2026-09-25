import type { Source } from "../api/types";
import { SafeText } from "./SafeText";

interface SourcesPanelProps {
  sources: Source[];
}

export function SourcesPanel({ sources }: SourcesPanelProps) {
  return (
    <section aria-labelledby="sources-heading">
      <h3 id="sources-heading">Source excerpts</h3>
      {sources.length === 0 ? (
        <p className="muted" data-testid="sources-empty">
          No source excerpts returned.
        </p>
      ) : (
        <ul className="sources-list" data-testid="sources-list">
          {sources.map((source) => (
            <li key={source.record_id}>
              <strong>
                {source.record_id} v{source.version}
              </strong>
              <blockquote data-testid={`source-excerpt-${source.record_id}`}>
                <SafeText text={source.excerpt} />
              </blockquote>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

import type { Fact, Source } from "../api/types";
import { SafeText } from "./SafeText";

interface FactsPanelProps {
  facts: Fact[];
  sources: Source[];
}

const SECTION_ORDER: Fact["section"][] = [
  "condition",
  "medication",
  "allergy",
  "lab",
  "vital",
];

export function FactsPanel({ facts, sources }: FactsPanelProps) {
  const sourceMap = new Map(sources.map((s) => [s.record_id, s]));

  if (facts.length === 0) {
    return (
      <section aria-labelledby="facts-heading">
        <h3 id="facts-heading">Clinical facts</h3>
        <p className="muted" data-testid="facts-empty">
          No structured facts returned. Check gaps — absence of facts is not a
          negative finding.
        </p>
      </section>
    );
  }

  const grouped = SECTION_ORDER.map((section) => ({
    section,
    items: facts.filter((f) => f.section === section),
  })).filter((g) => g.items.length > 0);

  return (
    <section aria-labelledby="facts-heading">
      <h3 id="facts-heading">Clinical facts</h3>
      {grouped.map(({ section, items }) => (
        <div key={section} className="fact-group" data-testid={`facts-${section}`}>
          <h4>{section}</h4>
          <table>
            <thead>
              <tr>
                <th>Key</th>
                <th>Value</th>
                <th>Date</th>
                <th>Qualifier</th>
                <th>Sources</th>
              </tr>
            </thead>
            <tbody>
              {items.map((fact) => (
                <tr key={`${section}-${fact.key}-${fact.value}`}>
                  <td>
                    <SafeText text={fact.key} />
                  </td>
                  <td>
                    <SafeText text={fact.value} />
                  </td>
                  <td>{fact.date ?? "—"}</td>
                  <td>
                    <SafeText text={fact.qualifier} />
                  </td>
                  <td>
                    <ul className="source-refs">
                      {fact.source_ids.map((id) => {
                        const src = sourceMap.get(id);
                        return (
                          <li key={id}>
                            <code>{id}</code>
                            {src ? (
                              <>
                                {" "}
                                v{src.version}: <SafeText text={src.excerpt} />
                              </>
                            ) : null}
                          </li>
                        );
                      })}
                    </ul>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  );
}

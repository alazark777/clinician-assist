/** Renders untrusted text as plain React children (HTML escaped by React). */

interface SafeTextProps {
  text: string;
  className?: string;
  "data-testid"?: string;
}

export function SafeText({ text, className, "data-testid": testId }: SafeTextProps) {
  return (
    <span className={className} data-testid={testId}>
      {text}
    </span>
  );
}

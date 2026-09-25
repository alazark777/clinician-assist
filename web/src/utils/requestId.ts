export interface GenerationInput {
  patientId: string;
  visitContext: string;
  asOf: string;
}

export function inputFingerprint(input: GenerationInput): string {
  return `${input.patientId}\u0000${input.visitContext}\u0000${input.asOf}`;
}

export function newRequestId(): string {
  return crypto.randomUUID();
}

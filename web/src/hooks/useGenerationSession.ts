import { useCallback, useRef } from "react";
import type { GenerationInput } from "../utils/requestId";
import { inputFingerprint, newRequestId } from "../utils/requestId";

/** Tracks request IDs per canonical input and supports explicit restarts. */
export function useGenerationSession() {
  const mapRef = useRef<Map<string, string>>(new Map());

  const resolveRequestId = useCallback(
    (input: GenerationInput, forceNew: boolean): string => {
      const key = inputFingerprint(input);
      if (forceNew) {
        const id = newRequestId();
        mapRef.current.set(key, id);
        return id;
      }
      const existing = mapRef.current.get(key);
      if (existing) {
        return existing;
      }
      const id = newRequestId();
      mapRef.current.set(key, id);
      return id;
    },
    [],
  );

  return { resolveRequestId };
}

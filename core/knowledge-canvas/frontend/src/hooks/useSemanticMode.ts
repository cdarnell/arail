import { useState, useCallback, useEffect } from "react";

const KEY = "knowledge-canvas.semantic-mode";

export function useSemanticMode() {
  const [semanticMode, setMode] = useState<boolean>(() => {
    try { return localStorage.getItem(KEY) === "true"; } catch { return false; }
  });
  useEffect(() => {
    try { localStorage.setItem(KEY, String(semanticMode)); } catch { /* ignore */ }
  }, [semanticMode]);
  const toggle = useCallback(() => setMode((m) => !m), []);
  return { semanticMode, toggle };
}

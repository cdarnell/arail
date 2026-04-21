import { useEffect, useRef } from "react";

export function useCanvasSocket(onEvent: (evt: any) => void) {
  const retryRef = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let ws: WebSocket | null = null;

    const connect = () => {
      const fallback = (() => {
        const proto = window.location.protocol === "https:" ? "wss" : "ws";
        return `${proto}://${window.location.host}/knowledge-canvas/ws/canvas`;
      })();
      const url = (import.meta.env.VITE_WS_URL as string) ?? fallback;
      ws = new WebSocket(url);
      ws.onopen = () => { retryRef.current = 0; };
      ws.onmessage = (e) => {
        try { onEvent(JSON.parse(e.data)); }
        catch (err) { console.warn("bad event", err); }
      };
      ws.onclose = () => {
        if (cancelled) return;
        const delay = Math.min(1000 * 2 ** retryRef.current++, 15000);
        setTimeout(connect, delay);
      };
    };
    connect();
    return () => { cancelled = true; ws?.close(); };
  }, [onEvent]);
}

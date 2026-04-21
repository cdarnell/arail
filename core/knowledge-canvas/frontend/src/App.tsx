import { useEffect, useMemo, useState, useCallback } from "react";
import SourceCanvas, { SourceNode } from "./components/SourceCanvas";
import LegendPanel from "./components/LegendPanel";
import SourceDropZone from "./components/SourceDropZone";
import SourceSidebar from "./components/SourceSidebar";
import NLQBar from "./components/NLQBar";
import { useFlyTo } from "./hooks/useFlyTo";
import { useSemanticMode } from "./hooks/useSemanticMode";
import { api } from "./lib/api";

export default function App() {
  const isEmbed = new URLSearchParams(window.location.search).get("embed") === "1";
  const [data, setData] = useState<{ nodes: SourceNode[]; links: any[] } | null>(null);
  const [selected, setSelected] = useState<SourceNode | null>(null);
  const [hovered, setHovered] = useState<SourceNode | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [status, setStatus] = useState<any>(null);
  const [filters, setFilters] = useState<any>({});
  const { flyToIds, registerCanvas } = useFlyTo();
  const { semanticMode, toggle } = useSemanticMode();

  useEffect(() => {
    api.snapshot().then(setData);
    api.graphStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    if (semanticMode && data && !data.links.some((l: any) => l.kind === "semantic")) {
      api.semanticEdges().then((r) => {
        setData((prev) => prev && { ...prev, links: [...prev.links, ...r.links] });
      });
    }
  }, [semanticMode, data]);

  const onNodeSelect = useCallback(async (n: SourceNode) => {
    setSelected(n);
    setSummary(null);
    api.clusterSummary(n.id)
      .then((r) => setSummary(r.summary))
      .catch(() => setSummary("Cluster summary is temporarily unavailable."));
  }, []);

  const linkCountByNode = useMemo(() => {
    const counts: Record<string, number> = {};
    if (!data) return counts;
    for (const l of data.links) {
      const s = String(l.source);
      const t = String(l.target);
      counts[s] = (counts[s] ?? 0) + 1;
      counts[t] = (counts[t] ?? 0) + 1;
    }
    return counts;
  }, [data]);

  const activeNode = selected ?? hovered;

  const onNLQ = useCallback(async (text: string) => {
    const r = await api.nlq(text);
    flyToIds(r.node_ids);
  }, [flyToIds]);

  const { counts, domains } = useMemo(() => {
    if (!data) return { counts: {}, domains: [] };
    const c: Record<string, number> = {};
    const d = new Set<string>();
    for (const n of data.nodes) {
      c[n.kind] = (c[n.kind] ?? 0) + 1;
      if (n.domain) d.add(n.domain);
    }
    return { counts: c, domains: [...d].sort() };
  }, [data]);

  if (!data) {
    return (
      <div className="w-screen h-screen bg-[#0a0a0f] text-white/60
                      flex items-center justify-center">
        Loading canvas…
      </div>
    );
  }

  return (
    <div className="w-screen h-screen bg-[#0a0a0f] overflow-hidden relative">
      <SourceCanvas
        initialData={data}
        filters={filters}
        onNodeSelect={onNodeSelect}
        onNodeHover={setHovered}
        onReady={registerCanvas}
      />

      {!isEmbed && <SourceDropZone />}
      {!isEmbed && <NLQBar onSubmit={onNLQ} />}

      <div className="fixed top-4 left-4 z-20 flex gap-2">
        <div className="px-3 py-1.5 text-xs rounded-full backdrop-blur-md
                        bg-white/5 border border-white/10 text-white/70">
          {data.nodes.length} sources
        </div>
        {status && (
          <div className="px-3 py-1.5 text-xs rounded-full backdrop-blur-md
                          border text-white/80"
               style={{
                 background: status.store_ready ? "rgba(40,120,80,.25)" : "rgba(120,100,40,.22)",
                 borderColor: status.store_ready ? "rgba(120,255,180,.35)" : "rgba(255,220,120,.3)",
               }}>
            {status.store_ready ? "Store ready" : "Fallback mode"}
            {status.lance?.package_installed ? " · Lance OK" : " · Lance missing"}
          </div>
        )}
        {!isEmbed && (
          <button
            onClick={toggle}
            className="px-3 py-1.5 text-xs rounded-full backdrop-blur-md
                     bg-white/10 border border-white/15 text-white/80 hover:bg-white/20"
          >
            {semanticMode ? "Semantic" : "Explicit"} links
          </button>
        )}
      </div>

      {!isEmbed && (
        <LegendPanel
          counts={counts}
          filters={filters}
          onFiltersChange={setFilters}
          availableDomains={domains}
        />
      )}

      {!isEmbed && (
        <SourceSidebar
          node={selected}
          summary={summary}
          onClose={() => setSelected(null)}
        />
      )}

      {isEmbed && (
        <aside className="fixed right-3 bottom-3 z-20 w-[min(380px,92vw)]
                          backdrop-blur-md bg-black/45 border border-white/15
                          rounded-xl p-3 text-white/85 shadow-xl">
          {activeNode ? (
            <>
              <div className="text-[10px] uppercase tracking-wider text-white/50 mb-1">
                Node details
              </div>
              <div className="text-sm font-medium leading-snug">{activeNode.title}</div>
              <div className="mt-1 text-xs text-white/60">
                {activeNode.kind}
                {activeNode.domain ? ` · ${activeNode.domain}` : ""}
                {activeNode.year ? ` · ${activeNode.year}` : ""}
                {` · ${linkCountByNode[activeNode.id] ?? 0} link(s)`}
              </div>
              {activeNode.tags?.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {activeNode.tags.slice(0, 6).map((t) => (
                    <span key={t} className="text-[11px] px-1.5 py-0.5 rounded-full bg-white/10 text-white/75">
                      #{t}
                    </span>
                  ))}
                </div>
              )}
              {selected && summary && (
                <div className="mt-2 text-xs text-blue-100/85 leading-relaxed border-t border-white/10 pt-2">
                  {summary}
                </div>
              )}
            </>
          ) : (
            <>
              <div className="text-sm text-white/80">Hover a node to inspect details.</div>
              <div className="text-xs text-white/55 mt-1">Click a node to pin it and fetch a cluster summary.</div>
            </>
          )}
        </aside>
      )}
    </div>
  );
}

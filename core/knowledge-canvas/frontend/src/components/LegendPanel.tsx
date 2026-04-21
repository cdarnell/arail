import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { KIND_COLOR } from "./SourceCanvas";

const KIND_LABELS: Record<string, string> = {
  markdown:       "Notes",
  paper:          "Papers",
  web_page:       "Web",
  api_snapshot:   "API pulls",
  dataset:        "Datasets",
  experiment_log: "Experiments",
  image:          "Images",
};

const INGESTED_BY_LABELS: Record<string, string> = {
  user:       "You",
  curator:    "Curator",
  agent:      "Agents",
  experiment: "Experiments",
};

interface Props {
  counts: Record<string, number>;      // kind -> count, for badges
  filters: {
    kinds?: string[];
    ingestedBy?: string[];
    domain?: string;
  };
  onFiltersChange: (f: Props["filters"]) => void;
  availableDomains: string[];
}

export default function LegendPanel({
  counts, filters, onFiltersChange, availableDomains,
}: Props) {
  const [expanded, setExpanded] = useState(true);

  const toggleKind = (k: string) => {
    const current = new Set(filters.kinds ?? Object.keys(KIND_COLOR));
    if (current.has(k)) current.delete(k); else current.add(k);
    // If all are selected, clear the filter (empty = show all)
    const all = new Set(Object.keys(KIND_COLOR));
    const selected = [...current];
    onFiltersChange({
      ...filters,
      kinds: selected.length === all.size ? undefined : selected,
    });
  };

  const toggleIngested = (src: string) => {
    const all = Object.keys(INGESTED_BY_LABELS);
    const current = new Set(filters.ingestedBy ?? all);
    if (current.has(src)) current.delete(src); else current.add(src);
    const selected = [...current];
    onFiltersChange({
      ...filters,
      ingestedBy: selected.length === all.length ? undefined : selected,
    });
  };

  const isKindActive = (k: string) =>
    !filters.kinds || filters.kinds.includes(k);
  const isIngestedActive = (s: string) =>
    !filters.ingestedBy || filters.ingestedBy.includes(s);

  return (
    <div className="fixed bottom-4 left-4 z-20 max-w-xs">
      <div className="backdrop-blur-xl bg-white/5 border border-white/10 rounded-xl shadow-xl overflow-hidden">
        <button
          onClick={() => setExpanded((e) => !e)}
          className="w-full px-4 py-3 flex items-center justify-between text-white/90 hover:bg-white/5"
        >
          <span className="text-xs uppercase tracking-widest text-white/60">Sources</span>
          <span className="text-white/50 text-xs">{expanded ? "−" : "+"}</span>
        </button>

        <AnimatePresence initial={false}>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden"
            >
              <div className="px-4 pb-4 space-y-4">
                {/* Kind filters */}
                <div className="space-y-1.5">
                  {Object.entries(KIND_COLOR).map(([kind, color]) => {
                    const count = counts[kind] ?? 0;
                    const active = isKindActive(kind);
                    return (
                      <button
                        key={kind}
                        onClick={() => toggleKind(kind)}
                        className={`w-full flex items-center gap-2 text-sm py-1 px-2 rounded
                          ${active ? "text-white/90" : "text-white/30"}
                          hover:bg-white/5 transition-colors`}
                      >
                        <span
                          className="w-3 h-3 rounded-full shrink-0"
                          style={{
                            background: color,
                            opacity: active ? 1 : 0.3,
                          }}
                        />
                        <span className="flex-1 text-left">{KIND_LABELS[kind] ?? kind}</span>
                        <span className="text-xs text-white/40">{count}</span>
                      </button>
                    );
                  })}
                </div>

                {/* Ingested-by filters */}
                <div className="pt-3 border-t border-white/10 space-y-1">
                  <div className="text-[10px] uppercase tracking-widest text-white/40 mb-1.5">
                    Added by
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {Object.entries(INGESTED_BY_LABELS).map(([k, label]) => (
                      <button
                        key={k}
                        onClick={() => toggleIngested(k)}
                        className={`text-xs px-2 py-1 rounded-full border transition-colors
                          ${isIngestedActive(k)
                            ? "bg-white/15 border-white/25 text-white/90"
                            : "bg-transparent border-white/10 text-white/30"}`}
                      >
                        {label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Domain selector */}
                {availableDomains.length > 1 && (
                  <div className="pt-3 border-t border-white/10">
                    <div className="text-[10px] uppercase tracking-widest text-white/40 mb-1.5">
                      Domain
                    </div>
                    <select
                      value={filters.domain ?? ""}
                      onChange={(e) => onFiltersChange({
                        ...filters,
                        domain: e.target.value || undefined,
                      })}
                      className="w-full text-xs bg-white/5 border border-white/10 rounded px-2 py-1 text-white/85"
                    >
                      <option value="">All domains</option>
                      {availableDomains.map((d) => (
                        <option key={d} value={d}>{d}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

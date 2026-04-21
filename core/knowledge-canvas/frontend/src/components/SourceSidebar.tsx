import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { SourceNode, KIND_COLOR } from "./SourceCanvas";
import { api } from "../lib/api";

interface Props {
  node: SourceNode | null;
  summary: string | null;
  onClose: () => void;
}

export default function SourceSidebar({ node, summary, onClose }: Props) {
  const [detail, setDetail] = useState<any>(null);

  useEffect(() => {
    if (!node) { setDetail(null); return; }
    api.getSource(node.id).then(setDetail);
  }, [node]);

  return (
    <AnimatePresence>
      {node && (
        <motion.aside
          initial={{ x: 480, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 480, opacity: 0 }}
          transition={{ type: "spring", stiffness: 260, damping: 30 }}
          className="fixed top-0 right-0 h-full w-[480px] z-10
                     backdrop-blur-xl bg-white/5 border-l border-white/10
                     shadow-2xl overflow-hidden flex flex-col"
        >
          <header className="p-4 border-b border-white/10">
            <div className="flex items-center justify-between mb-2">
              <span
                className="text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full"
                style={{
                  background: `${KIND_COLOR[node.kind]}30`,
                  color: KIND_COLOR[node.kind],
                  border: `1px solid ${KIND_COLOR[node.kind]}50`,
                }}
              >
                {node.kind.replace("_", " ")}
              </span>
              <button onClick={onClose} className="text-white/60 hover:text-white">✕</button>
            </div>
            <h2 className="text-white font-medium leading-snug">{node.title}</h2>
            <div className="mt-2 flex flex-wrap gap-1">
              {node.domain && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-white/10 text-white/70">
                  {node.domain}
                </span>
              )}
              {node.year && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-white/10 text-white/70">
                  {node.year}
                </span>
              )}
              {node.ingested_by && node.ingested_by !== "user" && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-white/10 text-white/70">
                  added by {node.ingested_by}
                </span>
              )}
              {node.tags.slice(0, 4).map((t) => (
                <span key={t} className="text-xs px-2 py-0.5 rounded-full bg-white/5 text-white/55">
                  #{t}
                </span>
              ))}
            </div>
          </header>

          {summary ? (
            <section className="p-4 border-b border-white/10 bg-blue-400/5">
              <div className="text-[10px] uppercase tracking-widest text-blue-300/80 mb-2">
                Cluster Synthesis
              </div>
              <p className="text-sm text-white/85 leading-relaxed">{summary}</p>
            </section>
          ) : (
            <section className="p-4 border-b border-white/10 text-xs text-white/40">
              Synthesizing cluster…
            </section>
          )}

          <div className="flex-1 overflow-auto p-4 text-sm text-white/80 leading-relaxed whitespace-pre-wrap">
            {detail?.body_excerpt || (
              <span className="text-white/40">Loading source content…</span>
            )}
          </div>

          {detail?.uri && (
            <footer className="p-3 border-t border-white/10 text-xs text-white/50 truncate">
              <span className="text-white/40">uri: </span>
              <span className="font-mono">{detail.uri}</span>
            </footer>
          )}
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

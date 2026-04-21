import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

interface Props {
  onSubmit: (utterance: string) => Promise<void>;
}

const HINTS = [
  "papers on nitrogen timing from 2023",
  "experiments that contradict early planting",
  "USDA pulls for peanut yield 2020-2024",
  "agent-discovered sources this week",
];

export default function NLQBar({ onSubmit }: Props) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [hintIdx] = useState(() => Math.floor(Math.random() * HINTS.length));
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") { e.preventDefault(); setOpen((o) => !o); }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, []);

  useEffect(() => { if (open) inputRef.current?.focus(); }, [open]);

  const submit = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    try { await onSubmit(text.trim()); setOpen(false); setText(""); }
    finally { setBusy(false); }
  };

  return (
    <>
      <div className="fixed top-4 right-4 z-20">
        <button
          onClick={() => setOpen(true)}
          className="px-3 py-1.5 text-xs rounded-full backdrop-blur-md
                     bg-white/10 border border-white/15 text-white/70 hover:bg-white/20"
        >
          Fly to…  <kbd className="ml-1 px-1 text-[10px] bg-white/10 rounded">⌘K</kbd>
        </button>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            className="fixed inset-0 z-30 flex items-start justify-center pt-32
                       bg-black/40 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          >
            <motion.div
              initial={{ y: -20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -20, opacity: 0 }}
              onClick={(e) => e.stopPropagation()}
              className="w-full max-w-2xl backdrop-blur-xl bg-white/10
                         border border-white/20 rounded-2xl shadow-2xl overflow-hidden"
            >
              <input
                ref={inputRef}
                value={text}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
                placeholder={`Try: "${HINTS[hintIdx]}"`}
                className="w-full bg-transparent text-white/95 text-lg px-6 py-5
                           focus:outline-none placeholder:text-white/30"
                disabled={busy}
              />
              {busy && <div className="px-6 pb-3 text-xs text-white/50">Planning flight…</div>}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

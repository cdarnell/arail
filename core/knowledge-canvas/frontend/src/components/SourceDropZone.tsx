import { useState, useCallback, DragEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "../lib/api";

/**
 * Drop zone for users to add sources. Accepts:
 *   - Dragged URLs (text/uri-list) → ingests as web_page
 *   - Dragged text → ingests as markdown
 *   - Files: .md → markdown, others → best-effort by extension
 *
 * Shows a glassmorphic overlay on drag-enter so the target is obvious.
 */
export default function SourceDropZone() {
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [lastAdded, setLastAdded] = useState<string | null>(null);

  const handleDrop = useCallback(async (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    setBusy(true);

    try {
      // Prefer URL if dragged from browser
      const url = e.dataTransfer.getData("text/uri-list") ||
                  e.dataTransfer.getData("text/x-moz-url")?.split("\n")[0];
      if (url && /^https?:\/\//.test(url)) {
        await ingestUrl(url);
        setLastAdded(url);
        return;
      }

      // Files
      const files = Array.from(e.dataTransfer.files);
      for (const file of files) {
        await ingestFile(file);
        setLastAdded(file.name);
      }

      // Plain text fallback
      if (!files.length && !url) {
        const text = e.dataTransfer.getData("text/plain");
        if (text) {
          await ingestText(text);
          setLastAdded("Text snippet");
        }
      }
    } finally {
      setBusy(false);
      setTimeout(() => setLastAdded(null), 3000);
    }
  }, []);

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setDragging(true);
  };

  const handleDragLeave = (e: DragEvent) => {
    if (e.currentTarget === e.target) setDragging(false);
  };

  return (
    <>
      {/* Full-window drop catcher; only visible when dragging */}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className="fixed inset-0 z-40 pointer-events-none"
        style={{ pointerEvents: dragging ? "auto" : "none" }}
      >
        <AnimatePresence>
          {dragging && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-blue-500/10 backdrop-blur-sm
                         flex items-center justify-center"
            >
              <div className="px-8 py-6 backdrop-blur-xl bg-white/10 border-2
                              border-dashed border-blue-300/60 rounded-2xl text-center">
                <div className="text-blue-200 text-lg font-medium">Drop to add source</div>
                <div className="text-white/60 text-sm mt-1">URLs, files, or text</div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Toast for last-added */}
      <AnimatePresence>
        {(busy || lastAdded) && (
          <motion.div
            initial={{ y: 20, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 20, opacity: 0 }}
            className="fixed bottom-4 right-4 z-30
                       backdrop-blur-xl bg-white/10 border border-white/15 rounded-lg
                       px-4 py-2 text-sm text-white/90 shadow-xl"
          >
            {busy ? "Adding source…" : `Added: ${lastAdded}`}
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

async function ingestUrl(url: string) {
  await api.ingest({
    kind: "web_page",
    title: url,
    uri: url,
    body_excerpt: "",
    tags: ["user-added"],
    ingested_by: "user",
  });
}

async function ingestFile(file: File) {
  const text = await file.text();
  const kind = file.name.endsWith(".md") ? "markdown"
             : file.name.endsWith(".json") ? "dataset"
             : "markdown";
  await api.ingest({
    kind,
    title: file.name,
    uri: `upload::${file.name}`,
    body_excerpt: text.slice(0, 4000),
    tags: ["user-added"],
    ingested_by: "user",
  });
}

async function ingestText(text: string) {
  const title = text.slice(0, 60).replace(/\n/g, " ");
  await api.ingest({
    kind: "markdown",
    title: title || "Untitled snippet",
    uri: `snippet::${Date.now()}`,
    body_excerpt: text.slice(0, 4000),
    tags: ["user-added", "snippet"],
    ingested_by: "user",
  });
}

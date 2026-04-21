import { useEffect, useMemo, useRef, useCallback, useState } from "react";
import ForceGraph3D, { ForceGraphMethods } from "react-force-graph-3d";
import * as THREE from "three";
import { useCanvasSocket } from "../hooks/useCanvasSocket";
import { useSemanticMode } from "../hooks/useSemanticMode";

// Source kinds drive color. Chosen for visual distinction + semantic meaning:
// warm colors = human-authored, cool = data-sourced, neutral = derived.
export const KIND_COLOR: Record<string, string> = {
  focus:          "#5fd2ff",   // cyan-blue — system focus hubs
  markdown:       "#e8b84c",   // amber — user notes, human voice
  paper:          "#b07be8",   // purple — peer-reviewed knowledge
  web_page:       "#6fb8ff",   // sky — agent-scraped
  api_snapshot:   "#4fd9b8",   // teal — live data pulls
  dataset:        "#58d060",   // green — structured data
  experiment_log: "#ff8a5c",   // orange — lab-derived
  image:          "#f06ec3",   // pink — visual sources
};

export const EDGE_STYLE: Record<string, { color: string; width: number }> = {
  focus:      { color: "rgba(95,210,255,0.45)",  width: 1.0 },
  wikilink:   { color: "rgba(200,200,200,0.35)", width: 0.4 },
  discovered: { color: "rgba(120,180,255,0.5)",  width: 0.6 },
  motivates:  { color: "rgba(255,140,80,0.55)",  width: 0.8 },
  cites:      { color: "rgba(176,123,232,0.5)",  width: 0.5 },
  derived:    { color: "rgba(255,138,92,0.5)",   width: 0.5 },
  suggested:  { color: "rgba(255,180,80,0.7)",   width: 0.8 },
  semantic:   { color: "rgba(120,180,255,0.45)", width: 0.35 },
};

export interface SourceNode {
  id: string;
  title: string;
  kind: string;
  tags: string[];
  domain?: string;
  ingested_by?: string;
  year?: number;
  orphan?: boolean;
  x?: number; y?: number; z?: number;
}

export interface SourceLink {
  source: string;
  target: string;
  kind: string;              // wikilink | discovered | motivates | cites | derived | suggested | semantic
  confidence?: number;
  weight?: number;
}

interface Props {
  initialData: { nodes: SourceNode[]; links: SourceLink[] };
  filters: {
    kinds?: string[];          // if set, only these kinds render
    ingestedBy?: string[];     // if set, only these sources render
    domain?: string;
  };
  onNodeSelect: (node: SourceNode) => void;
  onNodeHover?: (node: SourceNode | null) => void;
  onReady?: (fg: ForceGraphMethods) => void;
}

function applyPatch(
  prev: { nodes: SourceNode[]; links: SourceLink[] },
  evt: any
): { nodes: SourceNode[]; links: SourceLink[] } {
  switch (evt.event) {
    case "source_added": {
      const s = evt.source;
      const node: SourceNode = {
        id: s.id, title: s.title, kind: s.kind,
        tags: s.tags || [], domain: s.domain,
        ingested_by: s.ingested_by, year: s.year, orphan: true,
      };
      const nodes = [...prev.nodes.filter((n) => n.id !== s.id), node];
      return { nodes, links: prev.links };
    }
    case "source_removed": {
      const nodes = prev.nodes.filter((n) => n.id !== evt.id);
      const links = prev.links.filter(
        (l) => l.source !== evt.id && l.target !== evt.id
      );
      return { nodes, links };
    }
    case "link_added": {
      const l = evt.link;
      const exists = prev.links.some(
        (x) => x.source === l.source && x.target === l.target && x.kind === l.kind
      );
      if (exists) return prev;
      return { nodes: prev.nodes, links: [...prev.links, l] };
    }
    default:
      return prev;
  }
}

export default function SourceCanvas({
  initialData, filters, onNodeSelect, onNodeHover, onReady,
}: Props) {
  const fgRef = useRef<ForceGraphMethods>();
  const [data, setData] = useState(initialData);
  const { semanticMode } = useSemanticMode();

  useCanvasSocket((evt) => setData((prev) => applyPatch(prev, evt)));

  // Apply user filters + semantic/wikilink mode to the rendered set
  const displayData = useMemo(() => {
    const nodesVisible = data.nodes.filter((n) => {
      if (filters.kinds?.length && !filters.kinds.includes(n.kind)) return false;
      if (filters.ingestedBy?.length && !filters.ingestedBy.includes(n.ingested_by || "")) return false;
      if (filters.domain && n.domain !== filters.domain) return false;
      return true;
    });
    const visibleIds = new Set(nodesVisible.map((n) => n.id));
    const links = data.links.filter((l) => {
      if (!visibleIds.has(l.source as string) || !visibleIds.has(l.target as string)) return false;
      if (semanticMode) return l.kind === "semantic" || l.kind === "suggested";
      return l.kind !== "semantic";
    });
    return { nodes: nodesVisible, links };
  }, [data, filters, semanticMode]);

  // Shared geometry + material cache — pragmatic InstancedMesh stand-in
  const geoCache = useRef(new Map<string, THREE.SphereGeometry>());
  const matCache = useRef(new Map<string, THREE.MeshLambertMaterial>());

  const degreeById = useMemo(() => {
    const deg: Record<string, number> = {};
    for (const l of displayData.links) {
      const s = String(l.source);
      const t = String(l.target);
      deg[s] = (deg[s] ?? 0) + 1;
      deg[t] = (deg[t] ?? 0) + 1;
    }
    return deg;
  }, [displayData.links]);

  const labeledIds = useMemo(() => {
    const ranked = [...displayData.nodes]
      .sort((a, b) => (degreeById[b.id] ?? 0) - (degreeById[a.id] ?? 0))
      .slice(0, 12)
      .map((n) => n.id);
    const set = new Set(ranked);
    for (const n of displayData.nodes) {
      if (n.kind === "focus") set.add(n.id);
    }
    return set;
  }, [displayData.nodes, degreeById]);

  const labelTextureCache = useRef(new Map<string, THREE.Texture>());

  const makeLabelSprite = useCallback((text: string) => {
    const label = text.length > 32 ? `${text.slice(0, 29)}...` : text;
    let tex = labelTextureCache.current.get(label);
    if (!tex) {
      const canvas = document.createElement("canvas");
      canvas.width = 512;
      canvas.height = 96;
      const ctx = canvas.getContext("2d");
      if (!ctx) return null;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "rgba(10,10,15,0.7)";
      ctx.fillRect(0, 20, canvas.width, 56);
      ctx.strokeStyle = "rgba(255,255,255,0.2)";
      ctx.strokeRect(0.5, 20.5, canvas.width - 1, 55);
      ctx.font = "500 30px system-ui, -apple-system, Segoe UI, sans-serif";
      ctx.fillStyle = "rgba(240,245,255,0.95)";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(label, canvas.width / 2, 48);
      tex = new THREE.CanvasTexture(canvas);
      labelTextureCache.current.set(label, tex);
    }
    const material = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false });
    const sprite = new THREE.Sprite(material);
    sprite.scale.set(24, 4.5, 1);
    return sprite;
  }, []);

  const nodeThreeObject = useCallback((n: SourceNode) => {
    const size = n.orphan ? 3 : 5;
    const color = KIND_COLOR[n.kind] ?? "#9aa0a6";
    const geoKey = `s-${size}`;
    if (!geoCache.current.has(geoKey)) {
      geoCache.current.set(geoKey, new THREE.SphereGeometry(size, 12, 12));
    }
    if (!matCache.current.has(color)) {
      matCache.current.set(color, new THREE.MeshLambertMaterial({ color }));
    }
    const sphere = new THREE.Mesh(geoCache.current.get(geoKey)!, matCache.current.get(color)!);
    if (!labeledIds.has(n.id)) return sphere;
    const group = new THREE.Group();
    group.add(sphere);
    const sprite = makeLabelSprite(n.title);
    if (sprite) {
      sprite.position.set(0, size + 4.5, 0);
      group.add(sprite);
    }
    return group;
  }, [labeledIds, makeLabelSprite]);

  // Called once after the force simulation settles — safe to hand off the ref.
  const handleEngineStop = useCallback(() => {
    if (fgRef.current) onReady?.(fgRef.current);
  }, [onReady]);

  // Keep the camera in a gentle orbit so the scene is always moving.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    const controls: any = fg.controls?.();
    if (!controls) return;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.08;
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
  }, [displayData]);

  const linkColor = (l: SourceLink) => {
    const base = EDGE_STYLE[l.kind] ?? EDGE_STYLE.wikilink;
    if (l.kind === "suggested" && typeof l.confidence === "number") {
      return base.color.replace(/[\d.]+\)$/, `${l.confidence.toFixed(2)})`);
    }
    if (l.kind === "semantic" && typeof l.weight === "number") {
      return base.color.replace(/[\d.]+\)$/, `${l.weight.toFixed(2)})`);
    }
    return base.color;
  };

  const linkWidth = (l: SourceLink) => (EDGE_STYLE[l.kind] ?? EDGE_STYLE.wikilink).width;

  return (
    <ForceGraph3D
      ref={fgRef}
      graphData={displayData}
      nodeLabel={(n) => {
        const s = n as SourceNode;
        return `<div class="fg-tip">
          <div class="fg-tip-kind" style="color:${KIND_COLOR[s.kind] ?? "#999"}">${s.kind}</div>
          <div class="fg-tip-title">${s.title}</div>
          ${s.domain ? `<div class="fg-tip-meta">${s.domain}${s.year ? ` · ${s.year}` : ""}</div>` : ""}
        </div>`;
      }}
      nodeThreeObject={nodeThreeObject}
      linkColor={linkColor}
      linkWidth={linkWidth}
      onNodeClick={(n) => onNodeSelect(n as SourceNode)}
      onNodeHover={(n) => onNodeHover?.((n as SourceNode) || null)}
      onEngineStop={handleEngineStop}
      cooldownTicks={100}
      warmupTicks={20}
      rendererConfig={{ antialias: false, powerPreference: "high-performance" }}
      backgroundColor="#0a0a0f"
    />
  );
}

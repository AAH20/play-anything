"use client";

import Graph from "graphology";
import Sigma from "sigma";
import ForceAtlas2Layout from "graphology-layout-forceatlas2/worker";
import { useEffect, useMemo, useRef, useState } from "react";
import type { GraphEdge, GraphNode } from "../lib/graph";
import { bindRendererContextEvents } from "../lib/renderer-lifecycle";

type Layout = "grouped" | "force";
type Props = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selected: string | null;
  onSelect: (id: string) => void;
  layout: Layout;
  onStatus?: (status: {
    renderer: string;
    layoutRunning: boolean;
    visible: number;
    error?: string;
  }) => void;
};

const COLORS: Record<GraphNode["kind"], string> = {
  module: "#8493ff",
  file: "#53c5ad",
  function: "#70a8ff",
  class: "#f2bf68",
  external: "#9ba6b8",
};

function groupedPositions(nodes: GraphNode[]) {
  const groups = new Map<string, GraphNode[]>();
  for (const node of [...nodes].sort((a, b) => a.id.localeCompare(b.id))) {
    const group = node.kind;
    const members = groups.get(group) ?? [];
    members.push(node);
    groups.set(group, members);
  }

  const names = [...groups.keys()].sort();
  const positions = new Map<string, { x: number; y: number }>();
  names.forEach((name, groupIndex) => {
    const members = groups.get(name)!;
    const angle = (2 * Math.PI * groupIndex) / Math.max(names.length, 1) - Math.PI / 2;
    const centerX = names.length === 1 ? 0 : Math.cos(angle) * 2.1;
    const centerY = names.length === 1 ? 0 : Math.sin(angle) * 2.1;
    const radius = Math.max(0.45, Math.min(1.7, 0.22 * Math.sqrt(members.length)));
    members.forEach((node, index) => {
      const nodeAngle = (2 * Math.PI * index) / Math.max(members.length, 1);
      positions.set(node.id, {
        x: centerX + Math.cos(nodeAngle) * radius,
        y: centerY + Math.sin(nodeAngle) * radius,
      });
    });
  });
  return positions;
}

export default function GraphCanvas({ nodes, edges, selected, onSelect, layout, onStatus }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const workerRef = useRef<ForceAtlas2Layout | null>(null);
  const selectedRef = useRef(selected);
  const onSelectRef = useRef(onSelect);
  const onStatusRef = useRef(onStatus);
  const workerTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [activeLayout, setActiveLayout] = useState<Layout>(layout);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [contextError, setContextError] = useState<string | null>(null);
  const [renderAttempt, setRenderAttempt] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);

  const fallback = useMemo(() => {
    const fallbackNodes = nodes.slice(0, 200);
    const ids = new Set(fallbackNodes.map((node) => node.id));
    const fallbackEdges: GraphEdge[] = [];
    let moreEdges = false;
    for (const edge of edges) {
      if (!ids.has(edge.source) || !ids.has(edge.target)) continue;
      if (fallbackEdges.length === 600) {
        moreEdges = true;
        break;
      }
      fallbackEdges.push(edge);
    }
    const positions = groupedPositions(fallbackNodes);
    const points = [...positions.values()];
    const minX = Math.min(0, ...points.map(p => p.x));
    const maxX = Math.max(0, ...points.map(p => p.x));
    const minY = Math.min(0, ...points.map(p => p.y));
    const maxY = Math.max(0, ...points.map(p => p.y));
    for (const [id, point] of positions) positions.set(id, {
      x: maxX === minX ? 500 : 90 + (point.x - minX) / (maxX - minX) * 740,
      y: maxY === minY ? 440 : 220 + (point.y - minY) / (maxY - minY) * 420,
    });
    return {
      nodes: fallbackNodes,
      edges: fallbackEdges,
      positions,
      truncated: nodes.length > fallbackNodes.length || moreEdges,
    };
  }, [nodes, edges]);

  selectedRef.current = selected;
  onSelectRef.current = onSelect;
  onStatusRef.current = onStatus;

  useEffect(() => setActiveLayout(layout), [layout]);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    let renderer: Sigma | null = null;
    let graph: Graph | null = null;
    let unbindContextEvents = () => {};
    try {
      graph = new Graph({ multi: true, type: "directed" });
      const positions = groupedPositions(nodes);
      const nodeById = new Map(nodes.map((node) => [node.id, node]));

      for (const node of nodes) {
        const point = positions.get(node.id) ?? { x: 0, y: 0 };
        graph.addNode(node.id, {
          x: point.x,
          y: point.y,
          label: node.name,
          color: COLORS[node.kind],
          size: node.kind === "module" ? 6 : Math.min(10, 4 + Math.log2((node.connections ?? 0) + 1)),
          kind: node.kind,
        });
      }

      edges.forEach((edge, index) => {
        if (!nodeById.has(edge.source) || !nodeById.has(edge.target)) return;
        graph!.addDirectedEdgeWithKey(`relationship-${index}`, edge.source, edge.target, {
          color: "rgba(151, 167, 194, 0.22)",
          size: Math.min(2, 0.6 + Math.log2((edge.count ?? 1) + 1) * 0.25),
          relation: edge.relation,
        });
      });

      renderer = new Sigma(graph, host, {
        defaultNodeColor: COLORS.file,
        defaultEdgeColor: "rgba(151, 167, 194, 0.22)",
        defaultEdgeType: "arrow",
        labelFont: "Inter, ui-sans-serif, system-ui, sans-serif",
        labelSize: nodes.length <= 60 ? 13 : 11,
        labelWeight: "500",
        labelColor: { color: "#e5ebf6" },
        labelRenderedSizeThreshold: nodes.length <= 60 ? 0 : 7,
        labelDensity: nodes.length <= 60 ? 1 : 0.08,
        stagePadding: 28,
        minCameraRatio: 0.08,
        maxCameraRatio: 8,
        hideEdgesOnMove: true,
        nodeReducer: (key, data) => {
          if (!selectedRef.current || !graph!.hasNode(selectedRef.current)) return data;
          if (key === selectedRef.current) {
            return { ...data, color: "#ffffff", size: Math.max(data.size ?? 4, 9), zIndex: 2 };
          }
          return { ...data, color: "#445067", zIndex: 0 };
        },
        edgeReducer: (key, data) => {
          if (!selectedRef.current || !graph!.hasNode(selectedRef.current)) return data;
          const source = graph!.source(key);
          const target = graph!.target(key);
          return source === selectedRef.current || target === selectedRef.current
            ? { ...data, color: "rgba(180, 197, 255, 0.75)", size: Math.max(data.size ?? 1, 1.5) }
            : { ...data, color: "rgba(75, 87, 110, 0.12)" };
        },
      });
      renderer.on("clickNode", ({ node }) => onSelectRef.current(node));
      const onContextLost = (event: Event) => {
        event.preventDefault();
        const message = "WebGL context was lost.";
        if (workerTimerRef.current) clearTimeout(workerTimerRef.current);
        workerTimerRef.current = null;
        workerRef.current?.stop();
        workerRef.current?.kill();
        workerRef.current = null;
        setContextError(message);
        onStatusRef.current?.({ renderer: "unavailable", layoutRunning: false, visible: nodes.length, error: message });
      };
      const onContextRestored = () => {
        setContextError(null);
        setRenderAttempt((attempt) => attempt + 1);
      };
      unbindContextEvents = bindRendererContextEvents(
        host.querySelectorAll("canvas"), onContextLost, onContextRestored,
      );

      graphRef.current = graph;
      sigmaRef.current = renderer;
      setRenderError(null);
      setContextError(null);
      onStatusRef.current?.({ renderer: "sigma-webgl", layoutRunning: false, visible: nodes.length });
    } catch (error) {
      unbindContextEvents();
      renderer?.kill();
      host.replaceChildren();
      graphRef.current = null;
      sigmaRef.current = null;
      const message = error instanceof Error ? error.message : "The graph renderer could not be initialized.";
      setRenderError(message);
      onStatusRef.current?.({ renderer: "unavailable", layoutRunning: false, visible: nodes.length, error: message });
    }

    const observer = new ResizeObserver(() => renderer?.resize(true));
    observer.observe(host);
    return () => {
      // Sigma.kill() intentionally fires context-loss events. Old layers must
      // never change the state of the next renderer during StrictMode/rebuilds.
      unbindContextEvents();
      observer.disconnect();
      if (workerTimerRef.current) clearTimeout(workerTimerRef.current);
      workerTimerRef.current = null;
      workerRef.current?.stop();
      workerRef.current?.kill();
      workerRef.current = null;
      renderer?.kill();
      if (sigmaRef.current === renderer) sigmaRef.current = null;
      if (graphRef.current === graph) graphRef.current = null;
    };
  }, [nodes, edges, renderAttempt]);

  useEffect(() => {
    sigmaRef.current?.refresh();
  }, [selected]);

  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;

    if (activeLayout !== "force" || reducedMotion || graph.order < 2) {
      if (activeLayout !== "force" || reducedMotion) {
        const positions = groupedPositions(nodes);
        positions.forEach((point, id) => {
          if (graph.hasNode(id)) {
            graph.setNodeAttribute(id, "x", point.x);
            graph.setNodeAttribute(id, "y", point.y);
          }
        });
        sigmaRef.current?.refresh();
      }
      onStatusRef.current?.({ renderer: "sigma-webgl", layoutRunning: false, visible: nodes.length });
      return;
    }

    let worker: ForceAtlas2Layout | null = null;
    try {
      worker = new ForceAtlas2Layout(graph, {
        settings: {
          gravity: 0.12,
          scalingRatio: 6,
          slowDown: 2,
          barnesHutOptimize: graph.order > 200,
          outboundAttractionDistribution: true,
        },
      });
      workerRef.current = worker;
      worker.start();
      onStatusRef.current?.({ renderer: "sigma-webgl", layoutRunning: true, visible: nodes.length });
      workerTimerRef.current = setTimeout(() => {
        worker?.stop();
        worker?.kill();
        if (workerRef.current === worker) workerRef.current = null;
        workerTimerRef.current = null;
        sigmaRef.current?.refresh();
        onStatusRef.current?.({ renderer: "sigma-webgl", layoutRunning: false, visible: nodes.length });
      }, 3000);
    } catch (error) {
      worker?.kill();
      const message = error instanceof Error ? error.message : "The force layout could not be started.";
      onStatusRef.current?.({ renderer: "sigma-webgl", layoutRunning: false, visible: nodes.length, error: message });
    }

    return () => {
      if (workerTimerRef.current) clearTimeout(workerTimerRef.current);
      workerTimerRef.current = null;
      worker?.stop();
      worker?.kill();
      if (workerRef.current === worker) workerRef.current = null;
    };
  }, [activeLayout, nodes, edges, reducedMotion, renderAttempt]);

  const chooseLayout = (next: Layout) => setActiveLayout(next);
  const camera = () => sigmaRef.current?.getCamera();
  const motionDuration = reducedMotion ? 0 : 180;

  return (
    <div className="graph-canvas-surface" style={{ position: "relative", width: "100%", height: "100%", minHeight: 320 }}>
      <div
        ref={hostRef}
        className="graph-canvas-renderer"
        aria-label="Interactive repository graph"
        style={{ position: "absolute", inset: 0, visibility: renderError || contextError ? "hidden" : undefined }}
      />
      {(renderError || contextError) && (
        <svg
          className="graph-canvas-svg-fallback"
          viewBox="0 0 1000 700"
          preserveAspectRatio="xMidYMid meet"
          role="group"
          aria-label="Repository graph SVG fallback"
          style={{ position: "absolute", inset: 0, width: "100%", height: "100%", background: "#101b2b" }}
        >
          <defs>
            <marker id="graph-fallback-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#8291aa" />
            </marker>
          </defs>
          {fallback.edges.map((edge, index) => {
            const source = fallback.positions.get(edge.source);
            const target = fallback.positions.get(edge.target);
            if (!source || !target) return null;
            const sx = source.x;
            const sy = source.y;
            const tx = target.x;
            const ty = target.y;
            if (edge.source === edge.target) {
              return (
                <path
                  key={`fallback-edge-${index}`}
                  d={`M ${sx - 4} ${sy - 4} C ${sx - 32} ${sy - 46}, ${sx + 32} ${sy - 46}, ${sx + 4} ${sy - 4}`}
                  fill="none"
                  stroke="#71829d"
                  strokeOpacity="0.55"
                  strokeWidth="1.2"
                  markerEnd="url(#graph-fallback-arrow)"
                >
                  <title>{edge.relation}</title>
                </path>
              );
            }
            const dx = tx - sx;
            const dy = ty - sy;
            const distance = Math.max(Math.hypot(dx, dy), 1);
            const ux = dx / distance;
            const uy = dy / distance;
            return (
              <line
                key={`fallback-edge-${index}`}
                x1={sx + ux * 6}
                y1={sy + uy * 6}
                x2={tx - ux * 8}
                y2={ty - uy * 8}
                stroke="#8291aa"
                strokeOpacity="0.42"
                strokeWidth="1.1"
                markerEnd="url(#graph-fallback-arrow)"
              >
                <title>{edge.relation}</title>
              </line>
            );
          })}
          {fallback.nodes.map((node) => {
            const point = fallback.positions.get(node.id) ?? { x: 0, y: 0 };
            const x = point.x;
            const y = point.y;
            const isSelected = selected === node.id;
            const radius = Math.min(9, 4 + Math.log2((node.connections ?? 0) + 1) * 0.65);
            return (
              <g
                key={node.id}
                role="button"
                tabIndex={0}
                aria-label={`Select ${node.kind}: ${node.name}`}
                aria-pressed={isSelected}
                onClick={() => onSelect(node.id)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    onSelect(node.id);
                  }
                }}
                style={{ cursor: "pointer", outline: "none" }}
              >
                <title>{`${node.name} · ${node.path || node.kind}`}</title>
                <circle
                  cx={x}
                  cy={y}
                  r={radius}
                  fill={COLORS[node.kind]}
                  stroke={isSelected ? "#ffffff" : "#101b2b"}
                  strokeWidth={isSelected ? 3 : 1.5}
                />
                <text
                  x={x + radius + 4}
                  y={y + 3}
                  fill={isSelected ? "#ffffff" : "#c3cede"}
                  fontSize={isSelected ? 12 : 10}
                  fontFamily="Inter, ui-sans-serif, system-ui, sans-serif"
                  pointerEvents="none"
                >
                  {node.name.length > 26 ? `${node.name.slice(0, 25)}…` : node.name}
                </text>
              </g>
            );
          })}
        </svg>
      )}
      {!renderError && !contextError && (
      <div className="canvas-controls" role="toolbar" aria-label="Graph view controls">
        <div className="canvas-layout-controls" aria-label="Layout">
          <button type="button" aria-pressed={activeLayout === "grouped"} onClick={() => chooseLayout("grouped")}>
            Grouped
          </button>
          <button
            type="button"
            aria-pressed={activeLayout === "force"}
            title={reducedMotion ? "Force layout is paused because reduced motion is enabled" : undefined}
            onClick={() => chooseLayout("force")}
          >
            Force
          </button>
        </div>
        <button type="button" aria-label="Zoom in" onClick={() => void camera()?.animatedZoom({ duration: motionDuration })}>
          +
        </button>
        <button type="button" aria-label="Zoom out" onClick={() => void camera()?.animatedUnzoom({ duration: motionDuration })}>
          −
        </button>
      <button type="button" onClick={() => void camera()?.animatedReset({ duration: motionDuration })}>
        Fit
      </button>
      </div>
      )}
      {reducedMotion && activeLayout === "force" && (
        <p className="graph-canvas-motion-note" role="status">Force layout is paused while reduced motion is enabled.</p>
      )}
      {(renderError || contextError) && (
        <div
          className="graph-canvas-fallback"
          role="status"
          aria-live="polite"
          style={{
            position: "absolute",
            zIndex: 8,
            left: "50%",
            top: 12,
            transform: "translateX(-50%)",
            display: "grid",
            gap: 6,
            width: "min(540px, calc(100% - 32px))",
            padding: 10,
            border: "1px solid rgba(184, 199, 222, 0.24)",
            borderRadius: 10,
            background: "rgba(13, 25, 40, 0.97)",
            color: "#e7edf6",
            boxShadow: "0 12px 36px rgba(0, 0, 0, 0.3)",
            textAlign: "center",
          }}
        >
          <strong>Reduced graphics mode</strong>
          <span style={{ color: "#aebbd0", fontSize: 12, lineHeight: 1.6 }}>
            WebGL is unavailable. Select nodes in the SVG overview below, use the node list, or retry GPU rendering.
          </span>
          <button
            type="button"
            onClick={() => setRenderAttempt((attempt) => attempt + 1)}
            style={{ justifySelf: "center", padding: "7px 11px", border: "1px solid #596c87", borderRadius: 6, background: "#24364e", color: "#f1f5fb" }}
          >
            Retry graph renderer
          </button>
          {fallback.truncated && (
            <span role="note" style={{ color: "#e4c27b", fontSize: 11 }}>
              Showing up to 200 nodes and 600 relationships in this fallback view.
            </span>
          )}
        </div>
      )}
    </div>
  );
}

"use client";

import { useEffect, useRef, useState } from "react";
import type { KGVisualizationElement, KGGraphStats } from "~/lib/types";

const NODE_COLORS: Record<string, string> = {
  Alarm: "#ef4444",
  Fault: "#3b82f6",
  Device: "#22c55e",
  Topology: "#f59e0b",
  Rule: "#a855f7",
  Community: "#06b6d4",
  unknown: "#6b7280",
};

interface GraphCanvasProps {
  elements: KGVisualizationElement[];
  stats?: KGGraphStats;
  height?: number;
  onNodeClick?: (nodeId: string) => void;
}

interface NodeMap {
  [id: string]: {
    x: number;
    y: number;
    vx: number;
    vy: number;
    fx?: number;
    fy?: number;
  };
}

interface LinkMap {
  [id: string]: { source: string; target: string };
}

export function GraphCanvas({ elements, stats, height = 300, onNodeClick }: GraphCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animRef = useRef<number>(0);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // Split elements into nodes and edges
  const nodeEls = elements.filter((e) => !e.data.source && !e.data.target);
  const edgeEls = elements.filter((e) => e.data.source && e.data.target);

  // Build node positions map
  const nodePositions: NodeMap = {};
  const links: LinkMap = {};

  for (const el of nodeEls) {
    const id = el.data.id;
    if (!(id in nodePositions)) {
      nodePositions[id] = {
        x: Math.random() * 400 + 50,
        y: Math.random() * (height - 100) + 50,
        vx: 0,
        vy: 0,
      };
    }
  }

  for (let i = 0; i < edgeEls.length; i++) {
    const e = edgeEls[i].data;
    if (e.source && e.target) {
      links[`e_${i}`] = { source: e.source, target: e.target };
    }
  }

  const nodeIds = Object.keys(nodePositions);
  const linkIds = Object.keys(links);

  // Simple force simulation
  const simulate = () => {
    const reps = 120;
    const centerX = 250;
    const centerY = height / 2;
    const alpha = 0.08;

    for (let i = 0; i < nodeIds.length; i++) {
      for (let j = i + 1; j < nodeIds.length; j++) {
        const a = nodePositions[nodeIds[i]];
        const b = nodePositions[nodeIds[j]];
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = reps / (dist * dist);
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        a.vx -= fx * alpha;
        a.vy -= fy * alpha;
        b.vx += fx * alpha;
        b.vy += fy * alpha;
      }
    }

    const linkStrength = 0.06;
    for (const lid of linkIds) {
      const l = links[lid];
      const src = nodePositions[l.source];
      const tgt = nodePositions[l.target];
      if (!src || !tgt) continue;
      const dx = tgt.x - src.x;
      const dy = tgt.y - src.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const force = (dist - 100) * linkStrength;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      src.vx += fx * alpha;
      src.vy += fy * alpha;
      tgt.vx -= fx * alpha;
      tgt.vy -= fy * alpha;
    }

    for (const id of nodeIds) {
      const n = nodePositions[id];
      n.vx += (centerX - n.x) * 0.005;
      n.vy += (centerY - n.y) * 0.005;
    }

    const damping = 0.88;
    for (const id of nodeIds) {
      const n = nodePositions[id];
      if (n.fx !== undefined) { n.x = n.fx; n.vx = 0; }
      if (n.fy !== undefined) { n.y = n.fy; n.vy = 0; }
      n.x += n.vx * damping;
      n.y += n.vy * damping;
      n.vx *= damping;
      n.vy *= damping;
    }
  };

  const getNodeColor = (id: string) => {
    const el = nodeEls.find((e) => e.data.id === id);
    if (!el) return "#888";
    return NODE_COLORS[el.data.nodeType ?? "unknown"] ?? "#888";
  };

  const draw = () => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.strokeStyle = "rgba(255,255,255,0.12)";
    ctx.lineWidth = 1;
    for (const lid of linkIds) {
      const l = links[lid];
      const src = nodePositions[l.source];
      const tgt = nodePositions[l.target];
      if (!src || !tgt) continue;
      ctx.beginPath();
      ctx.moveTo(src.x, src.y);
      ctx.lineTo(tgt.x, tgt.y);
      ctx.stroke();
    }

    for (const id of nodeIds) {
      const n = nodePositions[id];
      const color = getNodeColor(id);
      const isHovered = hoveredNode === id;
      const r = isHovered ? 9 : 6;

      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
      ctx.fillStyle = isHovered ? color : color + "cc";
      ctx.fill();

      if (isHovered) {
        ctx.strokeStyle = "#fff";
        ctx.lineWidth = 1.5;
        ctx.stroke();
      }

      if (isHovered || nodeIds.length < 30) {
        const el = nodeEls.find((e) => e.data.id === id);
        if (el?.data.label) {
          ctx.fillStyle = "#e4e4e7";
          ctx.font = "10px monospace";
          ctx.fillText(el.data.label, n.x + 10, n.y + 4);
        }
      }
    }
  };

  useEffect(() => {
    let running = true;
    const loop = () => {
      if (!running) return;
      simulate();
      draw();
      animRef.current = requestAnimationFrame(loop);
    };
    animRef.current = requestAnimationFrame(loop);
    return () => {
      running = false;
      cancelAnimationFrame(animRef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [elements, height]);

  const getNodeAt = (mx: number, my: number): string | null => {
    const scaleX = 500 / (canvasRef.current?.offsetWidth ?? 500);
    const scaleY = height / (canvasRef.current?.offsetHeight ?? height);
    for (const id of nodeIds) {
      const n = nodePositions[id];
      const dx = mx * scaleX - n.x;
      const dy = my * scaleY - n.y;
      if (Math.sqrt(dx * dx + dy * dy) < 14) return id;
    }
    return null;
  };

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        width={500}
        height={height}
        className="w-full rounded border border-zinc-800 bg-zinc-950 cursor-crosshair"
        onMouseMove={(e) => {
          const rect = canvasRef.current!.getBoundingClientRect();
          setHoveredNode(getNodeAt(e.clientX - rect.left, e.clientY - rect.top));
        }}
        onMouseLeave={() => setHoveredNode(null)}
        onClick={() => {
          if (hoveredNode && onNodeClick) onNodeClick(hoveredNode);
        }}
      />
      {stats && (
        <div className="mt-2 flex flex-wrap gap-3 text-xs text-zinc-500">
          <span>节点 {stats.node_count}</span>
          <span>·</span>
          <span>边 {stats.edge_count}</span>
          <span>·</span>
          <span>社区 {stats.community_count}</span>
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-3">
        {Object.entries(NODE_COLORS).map(([type, color]) => (
          <div key={type} className="flex items-center gap-1.5 text-xs text-zinc-500">
            <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ backgroundColor: color }} />
            {type}
          </div>
        ))}
      </div>
    </div>
  );
}

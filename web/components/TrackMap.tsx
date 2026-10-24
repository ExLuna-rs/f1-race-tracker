"use client";

import { useEffect, useRef } from "react";
import { TRACK_STATUS } from "@/lib/format";
import { positionAt, sampleMotion, type Stream } from "@/lib/useStream";
import type { DriverInfo, Meta } from "@/lib/types";

interface Props {
  meta: Meta;
  motion: Stream["motion"];
  selected: string | null;
  // null when the click lands away from every car
  onSelect: (code: string | null) => void;
}

interface Transform {
  scale: number;
  ox: number;
  oy: number;
  cos: number;
  sin: number;
}

// Same rotation as FastF1's circuit_info example, then y flipped for canvas
function project(t: Transform, x: number, y: number): [number, number] {
  const rx = x * t.cos - y * t.sin;
  const ry = x * t.sin + y * t.cos;
  return [t.ox + rx * t.scale, t.oy - ry * t.scale];
}

function fit(points: [number, number][], rotation: number, width: number, height: number): Transform | null {
  if (points.length < 2) return null;
  const angle = (rotation / 180) * Math.PI;
  const cos = Math.cos(angle);
  const sin = Math.sin(angle);
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
  for (const [x, y] of points) {
    const rx = x * cos - y * sin;
    const ry = x * sin + y * cos;
    minX = Math.min(minX, rx); maxX = Math.max(maxX, rx);
    minY = Math.min(minY, ry); maxY = Math.max(maxY, ry);
  }
  const pad = 36;
  const scale = Math.min((width - 2 * pad) / (maxX - minX || 1), (height - 2 * pad) / (maxY - minY || 1));
  const ox = width / 2 - ((minX + maxX) / 2) * scale;
  const oy = height / 2 + ((minY + maxY) / 2) * scale;
  return { scale, ox, oy, cos, sin };
}

export default function TrackMap({ meta, motion, selected, onSelect }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const props = useRef({ meta, selected });
  props.current = { meta, selected };
  // Screen positions from the last draw, for clicks
  const hits = useRef<{ code: string; x: number; y: number }[]>([]);
  // Without an outline yet (live, first lap), fit the map to where cars have been
  const seen = useRef<[number, number][]>([]);

  useEffect(() => {
    const canvas = canvasRef.current!;
    const ctx = canvas.getContext("2d")!;
    let raf = 0;
    let size = { w: 0, h: 0, dpr: 1 };

    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      size = { w: rect.width, h: rect.height, dpr };
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(rect.height * dpr);
    };
    const observer = new ResizeObserver(resize);
    observer.observe(canvas);
    resize();

    const draw = () => {
      raf = requestAnimationFrame(draw);
      const { meta, selected } = props.current;
      // Frames on either side of the moment drawn, for smooth car movement
      const sample = sampleMotion(motion.current, performance.now());
      const cur = sample ? sample.frames[sample.i] : null;
      const { w, h, dpr } = size;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      hits.current = [];

      const outline = meta.track ?? null;
      if (!outline && cur) {
        for (const d of Object.values(cur.drivers)) {
          if (d.x != null && d.y != null && (d.x !== 0 || d.y !== 0)) seen.current.push([d.x, d.y]);
        }
        if (seen.current.length > 4000) seen.current = seen.current.filter((_, i) => i % 2 === 0);
      }
      const transform = fit(outline ?? seen.current, meta.rotation ?? 0, w, h);
      if (!transform) {
        ctx.fillStyle = "#8a8f98";
        ctx.font = "14px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("En attente des positions des voitures…", w / 2, h / 2);
        return;
      }

      if (outline) {
        const status = TRACK_STATUS[cur?.track_status ?? "1"];
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.beginPath();
        outline.forEach(([x, y], i) => {
          const [px, py] = project(transform, x, y);
          if (i === 0) ctx.moveTo(px, py); else ctx.lineTo(px, py);
        });
        ctx.closePath();
        ctx.strokeStyle = "#2a2f3a";
        ctx.lineWidth = 14;
        ctx.stroke();
        ctx.strokeStyle = cur?.track_status && cur.track_status !== "1" && status ? status.color : "#4a5160";
        ctx.lineWidth = 2;
        ctx.stroke();

        ctx.fillStyle = "#6b7280";
        ctx.font = "10px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        for (const c of meta.corners ?? []) {
          const [px, py] = project(transform, c.x, c.y);
          const a = (c.angle / 180) * Math.PI;
          // Push the label off the track, along the corner's angle
          const [dx, dy] = project({ ...transform, ox: 0, oy: 0 }, Math.cos(a), Math.sin(a));
          const len = Math.hypot(dx, dy) || 1;
          ctx.fillText(`${c.number}${c.letter}`, px + (dx / len) * 18, py + (dy / len) * 18);
        }
      }

      if (!sample || !cur) return;
      const info = new Map<string, DriverInfo>((meta.drivers ?? []).map((d) => [d.code, d]));
      const entries = Object.entries(cur.drivers)
        .filter(([, d]) => d.x != null && d.y != null && !d.retired)
        // Leader drawn last so it stays on top
        .sort(([, a], [, b]) => (b.position || 99) - (a.position || 99));

      ctx.font = "600 11px system-ui, sans-serif";
      ctx.textBaseline = "middle";
      ctx.textAlign = "left";
      for (const [code, d] of entries) {
        const position = positionAt(sample, (f) => f.drivers[code]);
        if (!position) continue;
        const [px, py] = project(transform, position[0], position[1]);
        hits.current.push({ code, x: px, y: py });
        const color = info.get(code)?.color ?? "#ffffff";
        const isSelected = code === selected;
        const dim = selected && !isSelected ? 0.55 : 1;
        ctx.globalAlpha = (d.in_pit ? 0.45 : 1) * dim;
        ctx.beginPath();
        ctx.arc(px, py, isSelected ? 8 : 6, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.lineWidth = isSelected ? 2.5 : 1.5;
        ctx.strokeStyle = isSelected ? "#ffffff" : "#0d0f14";
        ctx.stroke();
        // Cars in the pit lane bunch up, so only label them when selected
        if (!d.in_pit || isSelected) {
          ctx.fillStyle = isSelected ? "#ffffff" : "#d6d9df";
          ctx.fillText(code, px + 10, py - 1);
        }
        ctx.globalAlpha = 1;
      }

      const sc = cur.safety_car;
      const scPosition = sc ? positionAt(sample, (f) => f.safety_car) : null;
      if (sc && scPosition) {
        const [px, py] = project(transform, scPosition[0], scPosition[1]);
        ctx.globalAlpha = sc.alpha ?? 1;
        ctx.fillStyle = "#ff9f1c";
        ctx.fillRect(px - 7, py - 5, 14, 10);
        ctx.fillStyle = "#0d0f14";
        ctx.font = "700 8px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText("SC", px, py);
        ctx.globalAlpha = 1;
      }
    };
    raf = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
    };
  }, [motion]);

  // A new session starts a new outline
  useEffect(() => {
    seen.current = [];
  }, [meta.session?.name, meta.session?.meeting]);

  const onClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    let best: { code: string; d: number } | null = null;
    for (const hit of hits.current) {
      const d = Math.hypot(hit.x - x, hit.y - y);
      if (d < 18 && (!best || d < best.d)) best = { code: hit.code, d };
    }
    onSelect(best?.code ?? null);
  };

  return <canvas ref={canvasRef} className="track-map" onClick={onClick} aria-label="Carte du circuit" />;
}


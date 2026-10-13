'use client';

// Small hand-built SVG charts for shapes lightweight-charts doesn't draw:
// stacked bars, a scatter and a horizontal contribution bar list. Each has a
// per-mark hover read-out and a legend; colours come from theme tokens.

import { useMemo, useState } from 'react';

type Tip = { x: number; y: number; lines: string[] } | null;

function TipBox({ tip }: { tip: Tip }) {
  if (!tip) return null;
  return (
    <div className="chart-tip" style={{ left: tip.x, top: tip.y, transform: 'translate(-50%, calc(-100% - 10px))' }}>
      {tip.lines.map((l, i) => (
        <div key={i} className={i === 0 ? 'mb-1 font-mono text-[color:var(--fg)]' : 'font-mono tnum'}>{l}</div>
      ))}
    </div>
  );
}

// ── Stacked bars ───────────────────────────────────────────────────────────

export type StackSegment = { key: string; label: string; color: string };
export type StackRow = { label: string; values: Record<string, number | null> };

export function StackedBars({
  rows,
  segments,
  mode,
  height = 200,
  ariaLabel,
  format = v => String(Math.round(v)),
}: {
  rows: StackRow[];
  segments: StackSegment[];
  mode: 'share' | 'count';
  height?: number;
  ariaLabel: string;
  format?: (v: number) => string;
}) {
  const [tip, setTip] = useState<Tip>(null);
  const W = 800;
  const padL = 34, padB = 18, padT = 6;
  const plotH = height - padB - padT;
  const totals = rows.map(r => segments.reduce((s, seg) => s + (r.values[seg.key] ?? 0), 0));
  const max = mode === 'share' ? 1 : Math.max(1, ...totals);
  const n = Math.max(rows.length, 1);
  const slot = (W - padL) / n;
  const barW = Math.max(1, slot - (n > 120 ? 0.5 : 2));
  const ticks = mode === 'share' ? [0, 0.5, 1] : [0, max / 2, max];
  const labelEvery = Math.ceil(n / 6);

  return (
    <figure aria-label={ariaLabel} className="m-0">
      <figcaption className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-[color:var(--ink-3)]">
        {segments.map(s => (
          <span key={s.key} className="inline-flex items-center gap-1.5">
            <span className="legend-dot" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </figcaption>
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${height}`} className="block h-auto w-full" role="img" aria-label={ariaLabel} onMouseLeave={() => setTip(null)}>
          {ticks.map((t, i) => {
            const y = padT + plotH - (t / max) * plotH;
            return (
              <g key={i}>
                <line x1={padL} x2={W} y1={y} y2={y} stroke="rgb(var(--fg-rgb)/0.07)" />
                <text x={padL - 6} y={y + 3} textAnchor="end" fontSize="10" fill="var(--ink-3)">
                  {mode === 'share' ? `${Math.round(t * 100)}%` : format(t)}
                </text>
              </g>
            );
          })}
          {rows.map((r, i) => {
            const total = totals[i];
            const x = padL + i * slot;
            let acc = 0;
            const denom = mode === 'share' ? (total > 0 ? total : 1) : 1;
            return (
              <g key={r.label}
                onMouseMove={e => {
                  const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                  setTip({
                    x: ((x + barW / 2) / W) * box.width,
                    y: (padT / height) * box.height + 8,
                    lines: [r.label, ...segments.map(s => `${s.label}: ${r.values[s.key] == null ? '–' : mode === 'share' ? `${Math.round(((r.values[s.key] as number) / (total || 1)) * 100)}%` : format(r.values[s.key] as number)}`)],
                  });
                }}>
                <rect x={x} y={padT} width={slot} height={plotH} fill="transparent" />
                {total === 0 ? (
                  <rect x={x} y={padT + plotH - 2} width={barW} height={2} fill="var(--line)" />
                ) : (
                  segments.map(s => {
                    const v = (r.values[s.key] ?? 0) / denom;
                    const h = (v / max) * plotH;
                    const y = padT + plotH - ((acc + v) / max) * plotH;
                    acc += v;
                    return h > 0 ? <rect key={s.key} x={x} y={y + (h > 3 ? 1 : 0)} width={barW} height={Math.max(h - (h > 3 ? 1 : 0), 0.5)} fill={s.color} /> : null;
                  })
                )}
                {i % labelEvery === 0 && (
                  <text x={x} y={height - 4} fontSize="10" fill="var(--ink-3)">{r.label}</text>
                )}
              </g>
            );
          })}
        </svg>
        <TipBox tip={tip} />
      </div>
    </figure>
  );
}

// ── Scatter ────────────────────────────────────────────────────────────────

export type ScatterPoint = { x: number; y: number; label: string };

export function Scatter({
  points,
  xLabel,
  yLabel,
  ariaLabel,
  formatX = v => v.toFixed(2),
  formatY = v => `${(v * 100).toFixed(1)}%`,
  height = 260,
}: {
  points: ScatterPoint[];
  xLabel: string;
  yLabel: string;
  ariaLabel: string;
  formatX?: (v: number) => string;
  formatY?: (v: number) => string;
  height?: number;
}) {
  const [tip, setTip] = useState<Tip>(null);
  const W = 520, padL = 48, padB = 34, padT = 8, padR = 8;
  const { xmin, xmax, ymin, ymax, fit } = useMemo(() => {
    const xs = points.map(p => p.x), ys = points.map(p => p.y);
    const q = (arr: number[], p: number) => {
      const s = [...arr].sort((a, b) => a - b);
      return s[Math.min(s.length - 1, Math.max(0, Math.floor(p * (s.length - 1))))] ?? 0;
    };
    // Clip the axis to the 1st–99th percentile so a few extreme days don't flatten the cloud.
    const ylo = Math.min(q(ys, 0.01), 0), yhi = Math.max(q(ys, 0.99), 0);
    const xlo = Math.min(...xs, 0), xhi = Math.max(...xs, 0);
    const n = points.length;
    const mx = xs.reduce((a, b) => a + b, 0) / (n || 1), my = ys.reduce((a, b) => a + b, 0) / (n || 1);
    const sxx = xs.reduce((a, x) => a + (x - mx) ** 2, 0), sxy = xs.reduce((a, x, i) => a + (x - mx) * (ys[i] - my), 0);
    const b = sxx > 0 ? sxy / sxx : 0;
    return { xmin: xlo, xmax: xhi === xlo ? xlo + 1 : xhi, ymin: ylo, ymax: yhi === ylo ? ylo + 0.01 : yhi, fit: { a: my - b * mx, b } };
  }, [points]);
  const px = (x: number) => padL + ((x - xmin) / (xmax - xmin)) * (W - padL - padR);
  const py = (y: number) => padT + (1 - (Math.max(ymin, Math.min(ymax, y)) - ymin) / (ymax - ymin)) * (height - padT - padB);

  return (
    <figure aria-label={ariaLabel} className="m-0">
      <div className="relative">
        <svg viewBox={`0 0 ${W} ${height}`} className="block h-auto w-full" role="img" aria-label={ariaLabel} onMouseLeave={() => setTip(null)}>
          <line x1={px(0)} x2={px(0)} y1={padT} y2={height - padB} stroke="rgb(var(--fg-rgb)/0.18)" />
          <line x1={padL} x2={W - padR} y1={py(0)} y2={py(0)} stroke="rgb(var(--fg-rgb)/0.18)" />
          {[ymin, 0, ymax].map((t, i) => (
            <text key={i} x={padL - 6} y={py(t) + 3} textAnchor="end" fontSize="10" fill="var(--ink-3)">{formatY(t)}</text>
          ))}
          {[xmin, 0, xmax].map((t, i) => (
            <text key={i} x={px(t)} y={height - padB + 14} textAnchor="middle" fontSize="10" fill="var(--ink-3)">{formatX(t)}</text>
          ))}
          <text x={(padL + W) / 2} y={height - 4} textAnchor="middle" fontSize="11" fill="var(--ink-3)">{xLabel}</text>
          <text x={12} y={height / 2} textAnchor="middle" fontSize="11" fill="var(--ink-3)" transform={`rotate(-90 12 ${height / 2})`}>{yLabel}</text>
          {points.map((p, i) => (
            <circle key={i} cx={px(p.x)} cy={py(p.y)} r={3.2} fill="rgb(var(--series-1-rgb)/0.45)" stroke="var(--surface)" strokeWidth={0.8}
              onMouseEnter={e => {
                const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect();
                setTip({ x: (px(p.x) / W) * box.width, y: (py(p.y) / height) * box.height, lines: [p.label, `${xLabel}: ${formatX(p.x)}`, `${yLabel}: ${formatY(p.y)}`] });
              }} />
          ))}
          {points.length > 2 && (
            <line x1={px(xmin)} x2={px(xmax)} y1={py(fit.a + fit.b * xmin)} y2={py(fit.a + fit.b * xmax)} stroke="var(--series-2)" strokeWidth={2} strokeDasharray="5 4" />
          )}
        </svg>
        <TipBox tip={tip} />
      </div>
      <figcaption className="mt-1 flex flex-wrap gap-x-4 text-[12px] text-[color:var(--ink-3)]">
        <span className="inline-flex items-center gap-1.5"><span className="legend-dot" style={{ background: 'var(--series-1)' }} />One day</span>
        <span className="inline-flex items-center gap-1.5"><span className="legend-swatch" style={{ background: 'var(--series-2)' }} />Least-squares line</span>
      </figcaption>
    </figure>
  );
}

// ── Horizontal bars (feature contributions) ────────────────────────────────

export function HBars({ items, format, signed = true }: { items: { label: string; value: number }[]; format: (v: number) => string; signed?: boolean }) {
  const max = Math.max(1e-12, ...items.map(i => Math.abs(i.value)));
  return (
    <ul className="space-y-1.5">
      {items.map(item => {
        const pct = (Math.abs(item.value) / max) * 50;
        const pos = item.value >= 0;
        return (
          <li key={item.label} className="grid grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_auto] items-center gap-3 text-[12.5px]">
            <span className="truncate text-[color:var(--ink-2)]" title={item.label}>{item.label}</span>
            <span className="relative h-2.5 rounded-full bg-[rgb(var(--fg-rgb)/0.05)]">
              {signed && <span className="absolute left-1/2 top-[-3px] h-[16px] w-px bg-[rgb(var(--fg-rgb)/0.25)]" />}
              <span
                className="absolute top-0 h-2.5 rounded-full"
                style={{
                  background: signed ? (pos ? 'var(--up)' : 'var(--down)') : 'var(--series-1)',
                  width: `${signed ? pct : pct * 2}%`,
                  left: signed ? (pos ? '50%' : `${50 - pct}%`) : 0,
                }}
              />
            </span>
            <span className="w-[76px] text-right font-mono tnum text-[color:var(--ink-2)]">{format(item.value)}</span>
          </li>
        );
      })}
    </ul>
  );
}

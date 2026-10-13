'use client';

// Thin wrapper around lightweight-charts for daily series. One y-axis per
// chart (never dual-axis). Missing values become whitespace points, so a gap
// in the data is drawn as a gap, not interpolated. The legend above the plot
// doubles as the crosshair read-out.

import { useEffect, useMemo, useRef, useState } from 'react';
import { canvasColors, useTheme } from '@/lib/theme';

export type Point = { time: string; value: number | null | undefined };
export type SeriesSpec = {
  id: string;
  label: string;
  kind: 'line' | 'area' | 'histogram';
  color: string; // CSS colour, may use var(--x)
  data: Point[];
  lineWidth?: 1 | 2 | 3;
  dashed?: boolean;
  /** per-point colours for histograms, e.g. green/red returns */
  colorFor?: (v: number) => string;
};
export type Marker = { seriesId: string; time: string; text: string };

export function TimeSeriesChart({
  series,
  height = 280,
  format = v => v.toFixed(2),
  markers,
  zeroLine = false,
  onClickTime,
  ariaLabel,
}: {
  series: SeriesSpec[];
  height?: number;
  format?: (v: number) => string;
  markers?: Marker[];
  zeroLine?: boolean;
  onClickTime?: (time: string) => void;
  ariaLabel: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const theme = useTheme();
  const [hover, setHover] = useState<{ time: string; values: Record<string, number | null> } | null>(null);
  const clickRef = useRef(onClickTime);
  useEffect(() => {
    clickRef.current = onClickTime;
  }, [onClickTime]);

  const last = useMemo(() => {
    const out: Record<string, number | null> = {};
    for (const s of series) {
      const p = [...s.data].reverse().find(d => typeof d.value === 'number' && Number.isFinite(d.value));
      out[s.id] = p ? (p.value as number) : null;
    }
    return out;
  }, [series]);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    let disposed = false;
    let cleanup = () => {};
    import('lightweight-charts').then(({ createChart, LineSeries, AreaSeries, HistogramSeries, LineStyle, createSeriesMarkers }) => {
      if (disposed || !el) return;
      el.innerHTML = '';
      const chart = createChart(el, canvasColors({
        width: el.clientWidth || 600,
        height,
        layout: { background: { color: 'transparent' }, textColor: 'var(--ink-3)', fontSize: 11, attributionLogo: false },
        grid: { vertLines: { visible: false }, horzLines: { color: 'rgb(var(--fg-rgb)/0.06)' } },
        rightPriceScale: { borderVisible: false },
        timeScale: { borderVisible: false, fixLeftEdge: true, fixRightEdge: true },
        crosshair: {
          vertLine: { color: 'rgb(var(--fg-rgb)/0.35)', labelBackgroundColor: 'var(--surface-2)' },
          horzLine: { color: 'rgb(var(--fg-rgb)/0.25)', labelBackgroundColor: 'var(--surface-2)' },
        },
        localization: { locale: 'en-US', priceFormatter: format },
      }));
      const handles: { id: string; api: ReturnType<typeof chart.addSeries> }[] = [];
      for (const s of series) {
        const color = canvasColors(s.color);
        const data = s.data.map(p =>
          typeof p.value === 'number' && Number.isFinite(p.value)
            ? s.kind === 'histogram' && s.colorFor
              ? { time: p.time, value: p.value, color: canvasColors(s.colorFor(p.value)) }
              : { time: p.time, value: p.value }
            : { time: p.time },
        );
        let api;
        if (s.kind === 'area') {
          api = chart.addSeries(AreaSeries, {
            lineColor: color, lineWidth: s.lineWidth ?? 2, topColor: canvasColors(`rgb(var(--series-1-rgb)/0.22)`),
            bottomColor: 'rgba(0,0,0,0)', priceLineVisible: false, lastValueVisible: true,
          });
        } else if (s.kind === 'histogram') {
          api = chart.addSeries(HistogramSeries, { color, priceLineVisible: false, lastValueVisible: false });
        } else {
          api = chart.addSeries(LineSeries, {
            color, lineWidth: s.lineWidth ?? 2, priceLineVisible: false, lastValueVisible: false,
            lineStyle: s.dashed ? LineStyle.Dashed : LineStyle.Solid, crosshairMarkerRadius: 4,
          });
        }
        api.setData(data as never);
        handles.push({ id: s.id, api });
      }
      if (zeroLine && handles[0]) {
        handles[0].api.createPriceLine(canvasColors({ price: 0, color: 'rgb(var(--fg-rgb)/0.35)', lineWidth: 1, lineStyle: LineStyle.Dotted, axisLabelVisible: false, title: '' }));
      }
      if (markers?.length) {
        for (const h of handles) {
          const own = markers.filter(m => m.seriesId === h.id).map(m => ({
            time: m.time, position: 'aboveBar' as const, shape: 'arrowDown' as const, color: canvasColors('var(--ink-3)'), text: m.text,
          }));
          if (own.length) createSeriesMarkers(h.api, own as never);
        }
      }
      chart.timeScale().fitContent();
      chart.subscribeCrosshairMove(param => {
        if (!param.time || !param.seriesData) {
          setHover(null);
          return;
        }
        const values: Record<string, number | null> = {};
        for (const h of handles) {
          const d = param.seriesData.get(h.api) as { value?: number } | undefined;
          values[h.id] = d && typeof d.value === 'number' ? d.value : null;
        }
        setHover({ time: String(param.time), values });
      });
      chart.subscribeClick(param => {
        if (param.time && clickRef.current) clickRef.current(String(param.time));
      });
      const ro = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }));
      ro.observe(el);
      cleanup = () => {
        ro.disconnect();
        chart.remove();
      };
    });
    return () => {
      disposed = true;
      cleanup();
    };
  }, [series, height, format, markers, zeroLine, theme]);

  const values = hover?.values ?? last;
  return (
    <figure aria-label={ariaLabel} className="m-0">
      <figcaption className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-[color:var(--ink-3)]">
        <span className="font-mono tnum text-[color:var(--ink-2)]">{hover ? hover.time : 'latest'}</span>
        {series.map(s => (
          <span key={s.id} className="inline-flex items-center gap-1.5">
            <span className={s.kind === 'histogram' ? 'legend-dot' : 'legend-swatch'} style={{ background: s.color, opacity: s.dashed ? 0.7 : 1 }} />
            <span>{s.label}</span>
            <span className="font-mono tnum text-[color:var(--fg)]">{typeof values[s.id] === 'number' ? format(values[s.id] as number) : '–'}</span>
          </span>
        ))}
      </figcaption>
      <div ref={ref} style={{ height }} className="w-full" />
    </figure>
  );
}

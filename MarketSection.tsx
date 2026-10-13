'use client';

import { useMemo, useState } from 'react';
import { TimeSeriesChart, type SeriesSpec } from '@/components/charts/TimeSeriesChart';
import type { Range } from '@/components/dashboard/Dashboard';
import { Empty, ErrorBox, Loading, Panel, SectionTitle, Tag } from '@/components/dashboard/Panel';
import { qs, useApi, type AssetSummary, type MarketResponse } from '@/lib/api';
import { fmtDate, fmtPct, fmtUsd, toneClass } from '@/lib/format';

const usd = (v: number) => fmtUsd(v);
const usdCompact = (v: number) => fmtUsd(v, { compact: true });
const pct = (v: number) => fmtPct(v, 2);
const upDown = (v: number) => (v >= 0 ? 'var(--up)' : 'var(--down)');

export function MarketSection({ symbol, range, assets, onSelect }: { symbol: string; range: Range; assets: AssetSummary[]; onSelect: (s: string) => void }) {
  const asset = assets.find(a => a.symbol === symbol);
  const market = useApi<MarketResponse>(asset?.has_data ? `/market/${symbol}${qs({ start: range.start, end: range.end })}` : null);
  const [showTable, setShowTable] = useState(false);
  const rows = market.data?.rows;

  const priceSeries = useMemo<SeriesSpec[]>(() => [
    { id: 'close', label: `${symbol} daily close (USD)`, kind: 'area', color: 'var(--series-1)', data: (rows ?? []).map(r => ({ time: r.date, value: r.close })) },
  ], [rows, symbol]);
  const returnSeries = useMemo<SeriesSpec[]>(() => [
    { id: 'ret', label: 'Daily return', kind: 'histogram', color: 'var(--ink-3)', colorFor: upDown, data: (rows ?? []).map(r => ({ time: r.date, value: r.return_1d })) },
  ], [rows]);
  const volumeSeries = useMemo<SeriesSpec[]>(() => [
    { id: 'vol', label: 'Reported spot volume (USD)', kind: 'histogram', color: 'rgb(var(--series-1-rgb)/0.55)', data: (rows ?? []).map(r => ({ time: r.date, value: r.volume_usd })) },
  ], [rows]);
  const hasVolume = rows?.some(r => r.volume_usd != null);
  const sources = useMemo(() => Array.from(new Set((rows ?? []).map(r => r.source).filter(Boolean))), [rows]);

  return (
    <div className="space-y-4">
      <SectionTitle id="market" kicker="B · Market" title="Cryptocurrency market overview"
        sub="Daily closes on UTC days (close = end of the UTC day). Days without a price are left as gaps, never filled." />

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        {assets.map(a => (
          <button key={a.symbol} type="button" onClick={() => onSelect(a.symbol)} aria-pressed={a.symbol === symbol}
            className={`panel p-4 text-left transition hover:border-[rgb(var(--accent-rgb)/0.5)] ${a.symbol === symbol ? 'border-[rgb(var(--accent-rgb)/0.7)]' : ''}`}>
            <div className="flex items-center justify-between">
              <span className="font-semibold">{a.name} <span className="font-mono text-[12px] text-[color:var(--ink-3)]">{a.symbol}</span></span>
              {a.has_data ? <Tag tone="observed">{fmtDate(a.last_date)}</Tag> : <Tag tone="warn">No data</Tag>}
            </div>
            {a.has_data ? (
              <div className="mt-2 flex items-baseline gap-3">
                <span className="font-mono text-[18px] font-semibold tnum">{fmtUsd(a.last_close)}</span>
                <span className={`font-mono text-[12.5px] tnum ${toneClass(a.change_1d)}`}>{fmtPct(a.change_1d)}</span>
              </div>
            ) : (
              <p className="mt-2 text-[12.5px] text-[color:var(--ink-3)]">Not in the bundled sample. Needs live mode.</p>
            )}
            {a.has_data && <div className="mt-1 text-[11.5px] text-[color:var(--ink-3)]">Market cap {fmtUsd(a.market_cap_usd, { compact: true })} · volume {fmtUsd(a.volume_usd, { compact: true })}</div>}
          </button>
        ))}
      </div>

      {!asset?.has_data ? (
        <Panel title="Price history"><Empty title={`No price data for ${symbol}`} description="Run a live refresh (Data & model status page) once DATA_MODE=live, or import a CSV." /></Panel>
      ) : market.error ? (
        <ErrorBox error={market.error} onRetry={() => market.mutate()} />
      ) : !rows ? (
        <Loading height={360} />
      ) : rows.length === 0 ? (
        <Panel title="Price history"><Empty title="No prices in this date range" /></Panel>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
          <Panel className="xl:col-span-2" title={`${asset.name} price`}
            sub={<>Source: {sources.join(', ')}. {market.data && market.data.missing_days > 0 ? `${market.data.missing_days} missing day(s) in range.` : 'No missing days in range.'}</>}
            actions={<button type="button" className="text-[12px] text-[color:var(--accent-text)] hover:underline" onClick={() => setShowTable(v => !v)}>{showTable ? 'Show chart' : 'Show table'}</button>}>
            {showTable ? (
              <div className="max-h-[320px] overflow-auto">
                <table className="data-table">
                  <thead><tr><th>Date (UTC)</th><th className="num">Close</th><th className="num">Return</th><th className="num">Volume</th><th>Source</th></tr></thead>
                  <tbody>
                    {[...rows].reverse().map(r => (
                      <tr key={r.date}><td className="font-mono">{r.date}</td><td className="num">{fmtUsd(r.close)}</td>
                        <td className={`num ${toneClass(r.return_1d)}`}>{fmtPct(r.return_1d)}</td><td className="num">{fmtUsd(r.volume_usd, { compact: true })}</td><td>{r.source}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <TimeSeriesChart ariaLabel={`${symbol} daily closing price`} series={priceSeries} format={usd} height={300} />
            )}
          </Panel>
          <div className="grid gap-4">
            <Panel title="Daily returns" sub="Close-to-close simple return.">
              <TimeSeriesChart ariaLabel={`${symbol} daily returns`} series={returnSeries} format={pct} height={120} />
            </Panel>
            <Panel title="Trading volume" sub={hasVolume ? 'Reported spot volume across exchanges.' : 'Not available from this source.'}>
              {hasVolume ? <TimeSeriesChart ariaLabel={`${symbol} trading volume`} series={volumeSeries} format={usdCompact} height={120} /> : <Empty title="No volume data" />}
            </Panel>
          </div>
        </div>
      )}
    </div>
  );
}

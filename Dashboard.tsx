'use client';

import Link from 'next/link';
import { useState } from 'react';
import { MarketSection } from '@/components/dashboard/MarketSection';
import { ErrorBox, Loading, Tag } from '@/components/dashboard/Panel';
import { PredictionSection } from '@/components/dashboard/PredictionSection';
import { SentimentSection } from '@/components/dashboard/SentimentSection';
import { Button } from '@/components/ui';
import {
  ENGINE_LABELS,
  useApi,
  type AssetSummary,
  type AssetsResponse,
  type ForecastResponse,
  type SentimentDailyResponse,
  type StatusResponse,
} from '@/lib/api';
import { fmtDate, fmtDateTime, fmtInt, fmtPct, fmtSigned, fmtUsd, toneClass } from '@/lib/format';

const PRESETS = [
  { id: '3M', days: 91 },
  { id: '6M', days: 182 },
  { id: '1Y', days: 365 },
  { id: '2Y', days: 730 },
  { id: 'All', days: null },
] as const;
type PresetId = (typeof PRESETS)[number]['id'] | 'custom';

function shiftDate(iso: string, days: number) {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

export type Range = { start: string | null; end: string | null };

export function Dashboard() {
  const assets = useApi<AssetsResponse>('/assets');
  const status = useApi<StatusResponse>('/status', { refreshInterval: 30000 });
  const [symbol, setSymbol] = useState('BTC');
  const [preset, setPreset] = useState<PresetId>('1Y');
  const [custom, setCustom] = useState<Range>({ start: null, end: null });

  const asset: AssetSummary | undefined = assets.data?.assets.find(a => a.symbol === symbol);
  const lastDate = asset?.last_date;
  const presetDays = PRESETS.find(x => x.id === preset)?.days ?? null;
  const range: Range =
    preset === 'custom' ? custom : !lastDate || presetDays === null ? { start: null, end: null } : { start: shiftDate(lastDate, presetDays), end: lastDate };
  const customInvalid = preset === 'custom' && !!custom.start && !!custom.end && custom.start > custom.end;

  const dataMode = status.data?.data_mode ?? assets.data?.data_mode;

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-[80ch]">
          <div className="kicker">Research dashboard</div>
          <h1 className="mt-1.5 text-[26px] font-semibold leading-tight tracking-[-0.02em] sm:text-[30px]">
            Does aggregated daily sentiment predict 1–3 day crypto returns?
          </h1>
          <p className="mt-2 text-[14px] leading-6 text-[color:var(--ink-3)]">
            Daily news and social-media sentiment is scored, aggregated per asset and UTC day, and tested against momentum and
            volatility in walk-forward forecasts. <Link href="/methodology" className="text-[color:var(--accent-text)] hover:underline">How it works →</Link>
          </p>
        </div>
        <div className="flex items-center gap-2">
          {dataMode === 'sample' && <Tag tone="sample">Historical sample data</Tag>}
          {dataMode === 'live' && <Tag tone="live">Live mode</Tag>}
        </div>
      </header>

      {dataMode === 'sample' && asset?.last_date && (
        <p className="rounded-xl border border-[rgb(var(--warn-rgb)/0.35)] bg-[rgb(var(--warn-rgb)/0.06)] px-4 py-2.5 text-[13px] leading-6 text-[color:var(--ink-2)]">
          You are viewing the bundled <strong>historical</strong> dataset (prices and headlines up to {fmtDate(asset.last_date)}). Nothing on this page is a live
          market observation. Forecasts are made as of the last day in the data. Set <code className="font-mono">DATA_MODE=live</code> in the backend to extend it with live data.
        </p>
      )}

      {/* Controls: asset + date range, in one row above everything they filter */}
      <div className="panel flex flex-wrap items-center gap-x-5 gap-y-3 p-3 sm:px-4">
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-semibold text-[color:var(--ink-3)]">Asset</span>
          <div className="seg" role="group" aria-label="Asset">
            {(assets.data?.assets ?? [{ symbol: 'BTC' }, { symbol: 'ETH' }, { symbol: 'SOL' }]).map(a => (
              <button key={a.symbol} type="button" aria-pressed={symbol === a.symbol} onClick={() => setSymbol(a.symbol)}>
                {a.symbol}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[12px] font-semibold text-[color:var(--ink-3)]">Range</span>
          <div className="seg" role="group" aria-label="Date range">
            {PRESETS.map(p => (
              <button key={p.id} type="button" aria-pressed={preset === p.id} onClick={() => setPreset(p.id)}>
                {p.id}
              </button>
            ))}
            <button type="button" aria-pressed={preset === 'custom'} onClick={() => { setCustom(range); setPreset('custom'); }}>
              Custom
            </button>
          </div>
          {preset === 'custom' && (
            <span className="flex flex-wrap items-center gap-2">
              <input type="date" aria-label="Start date" className="field" value={custom.start ?? ''} min={asset?.first_date} max={asset?.last_date}
                onChange={e => setCustom(c => ({ ...c, start: e.target.value || null }))} />
              <span className="text-[color:var(--ink-3)]">to</span>
              <input type="date" aria-label="End date" className="field" value={custom.end ?? ''} min={asset?.first_date} max={asset?.last_date}
                onChange={e => setCustom(c => ({ ...c, end: e.target.value || null }))} />
            </span>
          )}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button size="sm" variant="secondary" onClick={() => { assets.mutate(); status.mutate(); }}>
            Reload data
          </Button>
        </div>
      </div>
      {customInvalid && <ErrorBox error={new Error('Start date must be on or before the end date.')} />}

      {assets.error ? (
        <ErrorBox error={assets.error} onRetry={() => assets.mutate()} />
      ) : !assets.data ? (
        <Loading height={130} />
      ) : (
        <Overview asset={asset} status={status.data} />
      )}

      {!customInvalid && (
        <>
          <MarketSection symbol={symbol} range={range} assets={assets.data?.assets ?? []} onSelect={setSymbol} />
          <SentimentSection symbol={symbol} range={range} />
          <PredictionSection symbol={symbol} />
        </>
      )}
    </div>
  );
}

function Card({ label, tag, children, foot }: { label: string; tag?: React.ReactNode; children: React.ReactNode; foot?: React.ReactNode }) {
  return (
    <div className="panel flex min-w-0 flex-col gap-1.5 p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11.5px] font-semibold text-[color:var(--ink-3)]">{label}</span>
        {tag}
      </div>
      <div className="min-w-0">{children}</div>
      {foot != null && <div className="mt-auto text-[11.5px] leading-5 text-[color:var(--ink-3)]">{foot}</div>}
    </div>
  );
}

function Overview({ asset, status }: { asset: AssetSummary | undefined; status: StatusResponse | undefined }) {
  const symbol = asset?.symbol ?? 'BTC';
  const forecast = useApi<ForecastResponse>(asset?.has_data ? `/forecasts/${symbol}/latest` : null);
  const lastDay = asset?.last_date;
  const sent = useApi<SentimentDailyResponse>(lastDay ? `/sentiment/${symbol}/daily?start=${shiftDate(lastDay, 6)}&end=${lastDay}` : null);
  const latestSent = sent.data?.rows.filter(r => r.n_records > 0).at(-1);
  const h1 = forecast.data?.horizons['1']?.primary;
  const h3 = forecast.data?.horizons['3']?.primary;
  const run = status?.latest_model_run;

  if (asset && !asset.has_data) {
    return (
      <div className="panel p-5 text-[14px] text-[color:var(--ink-2)]">
        <strong>{asset.name} ({asset.symbol})</strong> has no stored price data yet. The bundled sample covers BTC and ETH; {asset.symbol} becomes
        available once live mode fetches its prices (see <Link className="text-[color:var(--accent-text)] hover:underline" href="/status">Data & model status</Link>).
      </div>
    );
  }

  const fc = (f: typeof h1, h: number) =>
    f ? (
      <Card label={`Predicted ${h}-day return`} tag={<Tag tone="model">Model forecast</Tag>}
        foot={<>{f.label} · for close of {fmtDate(f.target_date)}{f.is_primary && (f.model_name === 'zero' || f.model_name === 'hist_mean') ? ' · no model beat this baseline in validation' : ''}</>}>
        <div className={`font-mono text-[22px] font-semibold tnum ${toneClass(f.predicted_return)}`}>{fmtPct(f.predicted_return, 2)}</div>
        <div className="text-[12px] text-[color:var(--ink-3)]">
          Scenario {fmtUsd(f.predicted_price)}
          {f.lower_return != null && f.upper_return != null && <> · 80% range {fmtPct(f.lower_return, 1)} to {fmtPct(f.upper_return, 1)}</>}
        </div>
      </Card>
    ) : (
      <Card label={`Predicted ${h}-day return`} tag={<Tag tone="model">Model forecast</Tag>}>
        <div className="text-[13px] text-[color:var(--ink-3)]">{forecast.error ? forecast.error.message : forecast.isLoading ? 'Loading…' : 'No forecast yet'}</div>
      </Card>
    );

  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
      <Card label="Selected asset" foot={<>Daily close data {fmtDate(asset?.first_date)} – {fmtDate(asset?.last_date)} ({fmtInt(asset?.n_days)} days)</>}>
        <div className="text-[20px] font-semibold">{asset?.name}</div>
        <div className="font-mono text-[12px] text-[color:var(--ink-3)]">{symbol} / USD</div>
      </Card>
      <Card label="Latest daily close" tag={<Tag tone="observed">Observed</Tag>}
        foot={<>UTC close of {fmtDate(asset?.last_date)} · source {asset?.source}</>}>
        <div className="font-mono text-[22px] font-semibold tnum">{fmtUsd(asset?.last_close)}</div>
        <div className={`font-mono text-[12.5px] tnum ${toneClass(asset?.change_1d)}`}>{fmtPct(asset?.change_1d)} vs previous close</div>
      </Card>
      <Card label="Latest daily sentiment" tag={<Tag tone="observed">Observed</Tag>}
        foot={latestSent ? <>{fmtDate(latestSent.date)} · {fmtInt(latestSent.n_records)} texts · {ENGINE_LABELS[sent.data?.engine ?? ''] ?? sent.data?.engine}</> : 'No scored texts in the last 7 days of data'}>
        <div className={`font-mono text-[22px] font-semibold tnum ${toneClass(latestSent?.sent_mean)}`}>{fmtSigned(latestSent?.sent_mean)}</div>
        <div className="text-[12px] text-[color:var(--ink-3)]">scale −1 (negative) to +1 (positive)</div>
      </Card>
      {fc(h1, 1)}
      {fc(h3, 3)}
      <Card label="Model status" tag={status?.training_in_progress || status?.pipeline.running ? <Tag tone="warn">Running</Tag> : run?.status === 'completed' ? <Tag tone="live">Trained</Tag> : <Tag tone="warn">Not trained</Tag>}
        foot={<>Data cutoff {fmtDate(h1?.feature_date)} · <Link href="/status" className="hover:underline">details</Link></>}>
        <div className="text-[13px] leading-5 text-[color:var(--ink-2)]">Last run {fmtDateTime(run?.created_at)}</div>
        <div className="text-[12px] text-[color:var(--ink-3)]">Last data update {fmtDateTime(status?.last_success?.market)}</div>
      </Card>
    </div>
  );
}

'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { HBars } from '@/components/charts/SvgCharts';
import { TimeSeriesChart, type Marker, type SeriesSpec } from '@/components/charts/TimeSeriesChart';
import { Empty, ErrorBox, Loading, Panel, SectionTitle, Tag } from '@/components/dashboard/Panel';
import {
  MODEL_LABELS,
  useApi,
  type BacktestResponse,
  type Forecast,
  type ForecastResponse,
  type PerformanceResponse,
} from '@/lib/api';
import { featureLabel, fmtDate, fmtNum, fmtP, fmtPct, fmtSigned, fmtUsd, toneClass } from '@/lib/format';

const pct2 = (v: number) => fmtPct(v, 2);
const sse = (v: number) => v.toFixed(4);
const BASELINES = new Set(['zero', 'hist_mean']);

export function PredictionSection({ symbol }: { symbol: string }) {
  const [h, setH] = useState<1 | 3>(1);
  const forecast = useApi<ForecastResponse>(`/forecasts/${symbol}/latest`);
  const perf = useApi<PerformanceResponse>(`/models/performance?symbol=${symbol}&horizon=${h}`);
  const fh = forecast.data?.horizons[String(h)];
  const primary = fh?.primary ?? null;
  const selected = perf.data?.evaluation.selected_model;
  // The comparison line on charts: the best sentiment model by validation RMSE.
  const sentimentModel = useMemo(() => {
    const m = perf.data?.evaluation.models;
    if (!m) return 'ridge_sentiment';
    return ['ridge_sentiment', 'gbr_sentiment'].sort((a, b) => (m[a]?.validation?.rmse ?? 9) - (m[b]?.validation?.rmse ?? 9))[0];
  }, [perf.data]);
  const marketTwin = sentimentModel.replace('_sentiment', '_market');
  const chartModels = Array.from(new Set([selected ?? 'zero', sentimentModel, marketTwin]));
  const backtest = useApi<BacktestResponse>(perf.data ? `/backtest/${symbol}?horizon=${h}&models=${chartModels.join(',')}` : null);

  return (
    <div className="space-y-4">
      <SectionTitle id="prediction" kicker="D · Prediction" title="Prediction dashboard"
        sub="Forecasts of the simple return from the latest close to the close h days later. The primary model is whichever candidate had the lowest out-of-sample error in the validation period, baselines included." />

      <div className="flex flex-wrap items-center gap-3">
        <div className="seg" role="group" aria-label="Forecast horizon">
          {[1, 3].map(x => (
            <button key={x} type="button" aria-pressed={h === x} onClick={() => setH(x as 1 | 3)}>{x}-day horizon</button>
          ))}
        </div>
        <span className="text-[12px] text-[color:var(--ink-3)]">Applies to everything in this section.</span>
      </div>

      {forecast.error ? (
        <ErrorBox error={forecast.error} onRetry={() => forecast.mutate()} />
      ) : !forecast.data ? (
        <Loading height={220} />
      ) : !fh ? (
        <Panel title="Forecast"><Empty title={`No ${h}-day forecast for ${symbol}`} /></Panel>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
          <PrimaryCard f={primary} h={h} />
          <Panel className="lg:col-span-3" title="All candidate forecasts" sub="Same data cutoff for every model. Validation and test RMSE come from the walk-forward evaluation (lower is better).">
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead><tr><th>Model</th><th className="num">Forecast</th><th className="num">Scenario price</th><th className="num">Val. RMSE</th><th className="num">Test RMSE</th></tr></thead>
                <tbody>
                  {fh.models.map(m => (
                    <tr key={m.model_name} className={m.is_primary ? 'is-primary' : ''}>
                      <td>{m.label}{m.is_primary ? <span className="ml-2"><Tag tone="model">Primary</Tag></span> : null}</td>
                      <td className={`num ${toneClass(m.predicted_return)}`}>{fmtPct(m.predicted_return, 3)}</td>
                      <td className="num">{fmtUsd(m.predicted_price)}</td>
                      <td className="num">{fmtNum(m.validation_rmse, 4)}</td>
                      <td className="num">{fmtNum(m.test_rmse, 4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>
      )}

      {fh && <Contributions models={fh.models} primary={primary} />}

      {perf.error ? <ErrorBox error={perf.error} onRetry={() => perf.mutate()} /> : !perf.data ? <Loading height={300} /> : (
        <>
          <BacktestPanels perf={perf.data} backtest={backtest.data} error={backtest.error} retry={() => backtest.mutate()} selected={selected ?? 'zero'} sentimentModel={sentimentModel} marketTwin={marketTwin} />
          <MetricsTable perf={perf.data} />
        </>
      )}
    </div>
  );
}

function PrimaryCard({ f, h }: { f: Forecast | null; h: number }) {
  if (!f) return <Panel className="lg:col-span-2" title="Primary forecast"><Empty title="No primary forecast" /></Panel>;
  const isBaseline = BASELINES.has(f.model_name);
  return (
    <Panel className="lg:col-span-2" title={`Primary ${h}-day forecast`} actions={<Tag tone="model">Model forecast</Tag>}
      sub={<>Made at the close of {fmtDate(f.feature_date)} (UTC) for the close of {fmtDate(f.target_date)}.</>}>
      <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
        <div>
          <div className="text-[12px] text-[color:var(--ink-3)]">Predicted return</div>
          <div className={`font-mono text-[30px] font-semibold tnum ${toneClass(f.predicted_return)}`}>{fmtPct(f.predicted_return, 2)}</div>
        </div>
        <div>
          <div className="text-[12px] text-[color:var(--ink-3)]">Price scenario</div>
          <div className="font-mono text-[20px] tnum">{fmtUsd(f.predicted_price)}</div>
          <div className="text-[11.5px] text-[color:var(--ink-3)]">from {fmtUsd(f.reference_price)} observed close</div>
        </div>
      </div>
      {f.lower_return != null && f.upper_return != null && (
        <div className="mt-4 rounded-xl border border-[color:var(--line)] p-3 text-[12.5px] leading-5 text-[color:var(--ink-2)]">
          80% empirical range: <span className="font-mono">{fmtPct(f.lower_return, 2)}</span> to <span className="font-mono">{fmtPct(f.upper_return, 2)}</span>
          {' '}({fmtUsd(f.reference_price * (1 + f.lower_return))} – {fmtUsd(f.reference_price * (1 + f.upper_return))}).
          <div className="mt-1 text-[11.5px] text-[color:var(--ink-3)]">{f.interval_note}</div>
        </div>
      )}
      <p className="mt-3 text-[12.5px] leading-5 text-[color:var(--ink-3)]">
        Model: <span className="text-[color:var(--ink-2)]">{f.label}</span>.{' '}
        {isBaseline
          ? 'No trained model (with or without sentiment) beat this baseline on validation error, so the honest forecast is the baseline.'
          : 'Selected for the lowest validation error.'}{' '}
        {f.sentiment_available ? '' : 'Sentiment was missing on the cutoff day; it was imputed with the training median plus a missing flag.'}
      </p>
    </Panel>
  );
}

function Contributions({ models, primary }: { models: Forecast[]; primary: Forecast | null }) {
  // Explain the primary model if it has features; otherwise the Ridge market+sentiment model.
  const target = primary?.contributions ? primary : models.find(m => m.model_name === 'ridge_sentiment');
  if (!target?.contributions) return null;
  const c = target.contributions;
  const linear = c.kind === 'linear';
  return (
    <Panel title={`What drives the ${target.label} forecast`}
      sub={<>{c.note}.{linear && c.intercept != null ? <> Intercept {fmtPct(c.intercept, 3)}, ridge penalty α = {fmtNum(c.alpha, 1)}.</> : null}{primary && target.model_name !== primary.model_name ? ' Shown because the primary model is a baseline with no features.' : ''}</>}>
      <HBars signed={linear} format={v => (linear ? fmtPct(v, 3) : fmtNum(v, 3))} items={c.items.map(i => ({ label: featureLabel(i.feature), value: i.value }))} />
    </Panel>
  );
}

function BacktestPanels({ perf, backtest, error, retry, selected, sentimentModel, marketTwin }: {
  perf: PerformanceResponse; backtest: BacktestResponse | undefined; error?: Error; retry: () => void;
  selected: string; sentimentModel: string; marketTwin: string;
}) {
  const rows = backtest?.rows;
  const series = useMemo<SeriesSpec[]>(() => {
    if (!rows) return [];
    const out: SeriesSpec[] = [
      { id: 'actual', label: 'Actual return', kind: 'line', color: 'rgb(var(--fg-rgb)/0.35)', lineWidth: 1, data: rows.map(r => ({ time: r.date, value: r.actual })) },
      { id: sentimentModel, label: MODEL_LABELS[sentimentModel], kind: 'line', color: 'var(--series-1)', lineWidth: 2, data: rows.map(r => ({ time: r.date, value: r[sentimentModel] as number })) },
    ];
    if (selected !== sentimentModel) {
      out.push({ id: selected, label: `${MODEL_LABELS[selected]} (primary)`, kind: 'line', color: 'var(--series-2)', lineWidth: 2, dashed: true, data: rows.map(r => ({ time: r.date, value: r[selected] as number })) });
    }
    return out;
  }, [rows, selected, sentimentModel]);

  const testStart = rows?.find(r => r.segment === 'test')?.date;
  const markers = useMemo<Marker[]>(() => (testStart ? [{ seriesId: 'actual', time: testStart, text: 'test period starts' }] : []), [testStart]);

  // Cumulative squared-error difference: (sentiment model)² − (market-only twin)². Falling = sentiment helping.
  const cum = useMemo<SeriesSpec[]>(() => {
    if (!rows) return [];
    let acc = 0;
    const data = rows.map(r => {
      const a = r[sentimentModel] as number | null, b = r[marketTwin] as number | null;
      if (a != null && b != null) acc += (r.actual - a) ** 2 - (r.actual - b) ** 2;
      return { time: r.date, value: acc };
    });
    return [{ id: 'cum', label: `Cumulative SE: ${MODEL_LABELS[sentimentModel]} − ${MODEL_LABELS[marketTwin]}`, kind: 'line', color: 'var(--series-1)', data }];
  }, [rows, sentimentModel, marketTwin]);

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Panel title="Actual vs out-of-sample predicted returns" sub={<>Walk-forward predictions: each point was produced by a model trained only on earlier data (refit every {perf.config.refit_every} days, with an embargo of h days). Validation ends {fmtDate(perf.config.validation_end)}.</>}>
        {error ? <ErrorBox error={error} onRetry={retry} /> : !rows ? <Loading height={280} /> : rows.length === 0 ? <Empty title="No backtest rows" /> : (
          <TimeSeriesChart ariaLabel="Actual and predicted returns" series={series} format={pct2} height={280} markers={markers} zeroLine />
        )}
      </Panel>
      <Panel title="Does adding sentiment reduce error?" sub="Running total of squared-error differences between the sentiment model and its market-only twin. A falling line means sentiment is helping; a rising line means it adds noise.">
        {!rows ? <Loading height={280} /> : <TimeSeriesChart ariaLabel="Cumulative squared error difference" series={cum} format={sse} height={280} markers={markers.map(m => ({ ...m, seriesId: 'cum' }))} zeroLine />}
      </Panel>
    </div>
  );
}

function MetricsTable({ perf }: { perf: PerformanceResponse }) {
  const ev = perf.evaluation;
  const order = ['zero', 'hist_mean', 'ridge_market', 'ridge_sentiment', 'gbr_market', 'gbr_sentiment'];
  const ablation = ev.ablation;
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
      <Panel className="xl:col-span-3" title="Model performance (out-of-sample)"
        sub={<>R²<sub>OOS</sub> compares with the historical-mean forecast available at the time (positive = better). Direction accuracy counts days where the sign was right; it is undefined for the zero forecast. Up-day share in the test period: {fmtPct(ev.models.zero?.test?.up_share, 1, false)}.</>}>
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr><th>Model</th><th className="num">Val RMSE</th><th className="num">Test RMSE</th><th className="num">Test MAE</th><th className="num">Test R²<sub>OOS</sub></th><th className="num">Test dir. acc.</th><th className="num">n test</th></tr>
            </thead>
            <tbody>
              {order.filter(k => ev.models[k]).map(k => {
                const m = ev.models[k];
                return (
                  <tr key={k} className={k === ev.selected_model ? 'is-primary' : ''}>
                    <td>{m.label}{k === ev.selected_model ? <span className="ml-2"><Tag tone="model">Selected</Tag></span> : null}</td>
                    <td className="num">{fmtNum(m.validation?.rmse, 4)}</td>
                    <td className="num">{fmtNum(m.test?.rmse, 4)}</td>
                    <td className="num">{fmtNum(m.test?.mae, 4)}</td>
                    <td className={`num ${toneClass(m.test?.r2_oos_vs_mean)}`}>{fmtPct(m.test?.r2_oos_vs_mean, 2)}</td>
                    <td className="num">{fmtPct(m.test?.direction_acc, 1, false)}</td>
                    <td className="num">{m.test?.n ?? '–'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-[12px] text-[color:var(--ink-3)]">Selection rule: {ev.selection_rule}. Sample {fmtDate(perf.data_start)} – {fmtDate(perf.data_end)}; sentiment present on {fmtPct(perf.coverage.sentiment_coverage, 0, false)} of days.</p>
      </Panel>
      <Panel className="xl:col-span-2" title="Ablation: market-only vs market + sentiment"
        sub={<>Diebold–Mariano test on squared errors. Negative statistic = sentiment model more accurate. <Link href="/methodology#ablation" className="text-[color:var(--accent-text)] hover:underline">Regime detail →</Link></>}>
        <table className="data-table">
          <thead><tr><th>Pair</th><th>Period</th><th className="num">DM stat</th><th className="num">p-value</th></tr></thead>
          <tbody>
            {(['validation', 'test'] as const).flatMap(seg =>
              ['ridge_sentiment_vs_ridge_market', 'gbr_sentiment_vs_gbr_market'].map(key => {
                const r = ablation[seg]?.[key];
                return (
                  <tr key={seg + key}>
                    <td>{key.startsWith('ridge') ? 'Ridge' : 'Gradient boosting'}</td>
                    <td className="capitalize">{seg}</td>
                    <td className="num">{fmtSigned(r?.stat, 2)}</td>
                    <td className={`num ${r?.p_value != null && r.p_value < 0.05 ? 'text-[color:var(--warn)]' : ''}`}>{fmtP(r?.p_value)}</td>
                  </tr>
                );
              }),
            )}
          </tbody>
        </table>
      </Panel>
    </div>
  );
}

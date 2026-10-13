'use client';

import { useMemo, useState } from 'react';
import { HBars, Scatter, StackedBars, type StackRow } from '@/components/charts/SvgCharts';
import { TimeSeriesChart, type SeriesSpec } from '@/components/charts/TimeSeriesChart';
import type { Range } from '@/components/dashboard/Dashboard';
import { Empty, ErrorBox, Loading, Panel, SectionTitle } from '@/components/dashboard/Panel';
import { Button } from '@/components/ui';
import {
  ApiError,
  ENGINE_LABELS,
  apiFetch,
  qs,
  useApi,
  type RecordsResponse,
  type SentimentDailyResponse,
  type SentimentRow,
  type SourcesResponse,
} from '@/lib/api';
import { fmtDate, fmtInt, fmtNum, fmtSigned, toneClass } from '@/lib/format';

const signed3 = (v: number) => fmtSigned(v, 3);

/** Rolling mean over the previous `w` calendar days, using only days that have a value. */
function rollingMean(rows: SentimentRow[], w: number) {
  return rows.map((_, i) => {
    const vals = rows.slice(Math.max(0, i - w + 1), i + 1).map(r => r.sent_mean).filter((v): v is number => v != null);
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  });
}

/** Weekly buckets (Monday start) when the range is long, so bars stay legible. */
function bucket(rows: SentimentRow[]) {
  const weekly = rows.length > 120;
  const groups = new Map<string, SentimentRow[]>();
  for (const r of rows) {
    let key = r.date;
    if (weekly) {
      const d = new Date(`${r.date}T00:00:00Z`);
      d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
      key = d.toISOString().slice(0, 10);
    }
    groups.set(key, [...(groups.get(key) ?? []), r]);
  }
  return { weekly, groups: Array.from(groups.entries()) };
}

export function SentimentSection({ symbol, range }: { symbol: string; range: Range }) {
  const daily = useApi<SentimentDailyResponse>(`/sentiment/${symbol}/daily${qs({ start: range.start, end: range.end })}`);
  const sources = useApi<SourcesResponse>(`/sentiment/${symbol}/sources${qs({ start: range.start, end: range.end })}`);
  const rows = daily.data?.rows;
  // The picked day belongs to one asset; switching asset falls back to its latest day.
  const [picked, setPicked] = useState<{ symbol: string; day: string } | null>(null);
  const setDay = (d: string) => setPicked({ symbol, day: d });

  // Default the headline drill-down to the latest day that has texts; reset when the asset changes.
  const latestWithText = useMemo(() => rows?.filter(r => r.n_records > 0).at(-1)?.date ?? null, [rows]);
  const selectedDay = (picked?.symbol === symbol ? picked.day : null) ?? latestWithText;

  const trend = useMemo<SeriesSpec[]>(() => {
    if (!rows) return [];
    const ma = rollingMean(rows, 7);
    return [
      { id: 'daily', label: 'Daily sentiment S(d)', kind: 'line', color: 'rgb(var(--series-1-rgb)/0.75)', lineWidth: 1, data: rows.map(r => ({ time: r.date, value: r.sent_mean })) },
      { id: 'ma7', label: '7-day mean', kind: 'line', color: 'var(--series-2)', lineWidth: 2, data: rows.map((r, i) => ({ time: r.date, value: ma[i] })) },
    ];
  }, [rows]);

  const { shareRows, countRows, weekly } = useMemo(() => {
    if (!rows) return { shareRows: [] as StackRow[], countRows: [] as StackRow[], weekly: false };
    const b = bucket(rows);
    const share: StackRow[] = [], count: StackRow[] = [];
    for (const [key, g] of b.groups) {
      const n = g.reduce((a, r) => a + r.n_records, 0);
      const w = (f: keyof SentimentRow) => (n ? g.reduce((a, r) => a + ((r[f] as number | null) ?? 0) * r.n_records, 0) : 0);
      const label = fmtDate(key, false);
      share.push({ label, values: { pos: w('pos_prop'), neu: w('neu_prop'), neg: w('neg_prop') } });
      count.push({ label, values: { news: g.reduce((a, r) => a + r.n_news, 0), social: g.reduce((a, r) => a + r.n_social, 0) } });
    }
    return { shareRows: share, countRows: count, weekly: b.weekly };
  }, [rows]);

  const scatter = useMemo(
    () => (rows ?? []).filter(r => r.sent_mean != null && r.return_next_1d != null).map(r => ({ x: r.sent_mean as number, y: r.return_next_1d as number, label: r.date })),
    [rows],
  );
  const missingDays = rows?.filter(r => r.n_records === 0).length ?? 0;
  const corr = daily.data?.correlation;

  return (
    <div className="space-y-4">
      <SectionTitle id="sentiment" kicker="C · Sentiment" title="Sentiment analysis dashboard"
        sub={<>Each headline or post is scored from −1 to +1 by the {ENGINE_LABELS[daily.data?.engine ?? ''] ?? 'selected'} engine, then averaged with equal weights per asset and UTC day. Days with no eligible text are shown as gaps (missing, not neutral).</>} />

      {daily.error ? (
        <ErrorBox error={daily.error} onRetry={() => daily.mutate()} />
      ) : !rows ? (
        <Loading height={300} />
      ) : rows.length === 0 ? (
        <Panel title="Sentiment"><Empty title={`No sentiment for ${symbol} in this range`} description="No eligible texts were collected for this asset and period." /></Panel>
      ) : (
        <>
          <Panel title="Sentiment trend" sub={<>Click a day to read its headlines below. {missingDays > 0 ? `${missingDays} day(s) in range had no eligible text.` : ''}</>}>
            <TimeSeriesChart ariaLabel={`${symbol} daily sentiment`} series={trend} format={signed3} height={260} zeroLine onClickTime={setDay} />
          </Panel>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Panel title="Positive, neutral and negative share" sub={weekly ? 'Weekly buckets (text-weighted) because the range is long.' : 'Per day.'}>
              <StackedBars ariaLabel="Share of positive, neutral and negative texts" mode="share" rows={shareRows}
                segments={[
                  { key: 'pos', label: 'Positive', color: 'var(--up)' },
                  { key: 'neu', label: 'Neutral', color: 'var(--neutral-mark)' },
                  { key: 'neg', label: 'Negative', color: 'var(--down)' },
                ]} />
            </Panel>
            <Panel title="Daily volume of analysed texts" sub={weekly ? 'Texts per week, split by source type.' : 'Texts per day, split by source type.'}>
              <StackedBars ariaLabel="Number of analysed texts" mode="count" rows={countRows} format={v => fmtInt(v)}
                segments={[
                  { key: 'news', label: 'News headlines', color: 'var(--series-1)' },
                  { key: 'social', label: 'Social posts', color: 'var(--series-2)' },
                ]} />
            </Panel>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Panel title="Sentiment vs next-day return"
              sub={corr ? <>Correlation with next-day return <span className="font-mono">{fmtSigned(corr.next_day, 3)}</span>, with same-day return <span className="font-mono">{fmtSigned(corr.same_day, 3)}</span> (n = {corr.n}). Descriptive only; the forecasting section tests predictive value properly.</> : 'Too few days for a correlation.'}>
              {scatter.length > 2 ? <Scatter ariaLabel="Daily sentiment against next-day return" points={scatter} xLabel="Sentiment on day d" yLabel="Return on day d+1" /> : <Empty title="Not enough days" />}
            </Panel>
            <Panel title="Sentiment source breakdown" sub="Texts and mean score by source type and top domains in this range.">
              {sources.error ? <ErrorBox error={sources.error} onRetry={() => sources.mutate()} /> : !sources.data ? <Loading height={200} /> : (
                <div className="space-y-4">
                  <HBars signed={false} format={v => fmtInt(v)} items={sources.data.by_type.map(t => ({ label: `${t.source_type === 'news' ? 'News' : 'Social'} · mean ${fmtSigned(t.mean_score, 3)}`, value: t.n }))} />
                  <div className="max-h-[220px] overflow-auto">
                    <table className="data-table">
                      <thead><tr><th>Source</th><th>Type</th><th className="num">Texts</th><th className="num">Mean score</th></tr></thead>
                      <tbody>
                        {sources.data.by_domain.map(d => (
                          <tr key={d.domain + d.source_type}><td>{d.domain}</td><td>{d.source_type}</td><td className="num">{fmtInt(d.n)}</td><td className={`num ${toneClass(d.mean_score)}`}>{fmtSigned(d.mean_score, 3)}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </Panel>
          </div>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
            <div className="lg:col-span-3"><Headlines symbol={symbol} day={selectedDay} onDay={setDay} /></div>
            <div className="lg:col-span-2"><TryIt /></div>
          </div>
        </>
      )}
    </div>
  );
}

function Headlines({ symbol, day, onDay }: { symbol: string; day: string | null; onDay: (d: string) => void }) {
  const recs = useApi<RecordsResponse>(day ? `/sentiment/${symbol}/records?day=${day}&limit=60` : null);
  const records = recs.data?.records ?? [];
  const mean = records.length ? records.reduce((a, r) => a + r.score, 0) / records.length : null;
  return (
    <Panel title={`Scored texts for ${day ? fmtDate(day) : '–'}`}
      sub={<>Individual records behind one day&apos;s aggregate{mean != null ? <> (mean <span className={`font-mono ${toneClass(mean)}`}>{fmtSigned(mean, 3)}</span>, first {records.length})</> : null}.</>}
      actions={<input type="date" aria-label="Pick a day" className="field" value={day ?? ''} onChange={e => e.target.value && onDay(e.target.value)} />}>
      {recs.error ? <ErrorBox error={recs.error} onRetry={() => recs.mutate()} /> : !recs.data ? <Loading height={200} /> : records.length === 0 ? (
        <Empty title="No eligible texts on this day" description="This day counts as missing sentiment." />
      ) : (
        <ul className="max-h-[360px] divide-y divide-[color:var(--line)] overflow-auto pr-1">
          {records.map((r, i) => (
            <li key={i} className="grid grid-cols-[64px_minmax(0,1fr)] gap-3 py-2.5">
              <span className={`font-mono text-[13px] tnum ${toneClass(r.score)}`}>{fmtSigned(r.score, 2)}</span>
              <div className="min-w-0">
                <p className="text-[13.5px] leading-5 text-[color:var(--fg)]">
                  {r.url ? <a href={r.url} target="_blank" rel="noreferrer" className="hover:underline">{r.title}</a> : r.title}
                </p>
                <p className="mt-0.5 text-[11.5px] text-[color:var(--ink-3)]">
                  {r.published_at.slice(11, 16)} UTC · {r.domain} · {r.source_type} · linked by {r.asset_link === 'tag' ? 'source tag' : 'keyword'}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

type Analysis = { engine: string; score: number; label: string; assets: string[]; p_pos: number | null; p_neg: number | null; p_neu: number | null };

function TryIt() {
  const [text, setText] = useState('Bitcoin rallies as ETF inflows hit a record, but analysts warn of liquidations');
  const [result, setResult] = useState<Analysis | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await apiFetch<Analysis>('/sentiment/analyze', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ text }) }));
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Panel title="Score a headline" sub="Runs the active sentiment engine on your own text. Nothing is stored.">
      <label htmlFor="try-text" className="sr-only">Headline text</label>
      <textarea id="try-text" value={text} maxLength={1000} onChange={e => setText(e.target.value)} rows={4}
        className="w-full resize-y rounded-xl border border-[color:var(--line)] bg-[rgb(var(--fg-rgb)/0.03)] p-3 text-[13.5px] leading-6 text-[color:var(--fg)] outline-none focus:border-[color:var(--accent)]" />
      <div className="mt-2 flex items-center gap-3">
        <Button size="sm" onClick={run} disabled={busy || text.trim().length < 3}>{busy ? 'Scoring…' : 'Score text'}</Button>
        <span className="text-[11.5px] text-[color:var(--ink-3)]">{text.length}/1000</span>
      </div>
      {error && <div className="mt-3"><ErrorBox error={error} /></div>}
      {result && (
        <div className="mt-4 grid grid-cols-3 gap-3 text-[12.5px]">
          <div><div className="text-[color:var(--ink-3)]">Score</div><div className={`font-mono text-[18px] font-semibold ${toneClass(result.score)}`}>{fmtSigned(result.score, 3)}</div></div>
          <div><div className="text-[color:var(--ink-3)]">Label</div><div className="mt-1 capitalize">{result.label}</div></div>
          <div><div className="text-[color:var(--ink-3)]">Assets found</div><div className="mt-1 font-mono">{result.assets.join(', ') || 'none'}</div></div>
          <div className="col-span-3 text-[11.5px] text-[color:var(--ink-3)]">
            Engine: {ENGINE_LABELS[result.engine] ?? result.engine}{result.p_pos != null && <> · p(pos) {fmtNum(result.p_pos, 2)} · p(neg) {fmtNum(result.p_neg, 2)}</>}
          </div>
        </div>
      )}
    </Panel>
  );
}

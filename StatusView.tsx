'use client';

import { useState } from 'react';
import { ErrorBox, Loading, Panel, Tag } from '@/components/dashboard/Panel';
import { Button } from '@/components/ui';
import { ApiError, ENGINE_LABELS, apiFetch, useApi, type StatusResponse } from '@/lib/api';
import { fmtDate, fmtDateTime, fmtInt } from '@/lib/format';

export function StatusView() {
  const status = useApi<StatusResponse>('/status', { refreshInterval: (d) => (d?.pipeline.running ? 4000 : 30000) });
  const [jobError, setJobError] = useState<ApiError | null>(null);
  const [jobMsg, setJobMsg] = useState<string | null>(null);
  const s = status.data;

  const start = async (kind: 'refresh' | 'train') => {
    setJobError(null);
    setJobMsg(null);
    try {
      await apiFetch(`/jobs/${kind}`, { method: 'POST' });
      setJobMsg(kind === 'refresh' ? 'Live refresh started.' : 'Retraining started. This takes a few minutes.');
      status.mutate();
    } catch (e) {
      setJobError(e as ApiError);
    }
  };

  return (
    <div className="mx-auto max-w-[1100px] space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="kicker">F · Data and model status</div>
          <h1 className="mt-1.5 text-[28px] font-semibold tracking-[-0.02em]">What the system knows, and how fresh it is</h1>
        </div>
        <Button size="sm" variant="secondary" onClick={() => status.mutate()}>Reload</Button>
      </header>

      {status.error ? <ErrorBox error={status.error} onRetry={() => status.mutate()} /> : !s ? <Loading height={400} /> : (
        <>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <Panel title="Data mode" actions={s.data_mode === 'live' ? <Tag tone="live">Live</Tag> : <Tag tone="sample">Sample</Tag>}>
              <p className="text-[13px] leading-6 text-[color:var(--ink-2)]">{s.data_mode_note}</p>
            </Panel>
            <Panel title="Latest model run" actions={s.latest_model_run?.status === 'completed' ? <Tag tone="live">Completed</Tag> : <Tag tone="warn">{s.latest_model_run?.status ?? 'None'}</Tag>}>
              <p className="text-[13px] leading-6 text-[color:var(--ink-2)]">
                {s.latest_model_run ? <>{fmtDateTime(s.latest_model_run.created_at)}<br /><span className="font-mono text-[11.5px] text-[color:var(--ink-3)]">{s.latest_model_run.run_id}</span></> : 'No model trained yet. Run: python scripts/pipeline.py all'}
              </p>
              {s.latest_model_run?.message && <p className="mt-2 text-[12px] text-[color:var(--down)]">{s.latest_model_run.message}</p>}
            </Panel>
            <Panel title="Sentiment engine">
              <p className="text-[13px] leading-6 text-[color:var(--ink-2)]">{ENGINE_LABELS[s.sentiment_engine] ?? s.sentiment_engine}</p>
              <p className="text-[12px] text-[color:var(--ink-3)]">Last text update {fmtDateTime(s.last_success.text)}<br />Last price update {fmtDateTime(s.last_success.market)}</p>
            </Panel>
          </div>

          <Panel title="Jobs" sub="Slow work runs in the background on the backend; the dashboard only reads stored results. One job at a time."
            actions={s.pipeline.running ? <span className="inline-flex items-center gap-2 text-[12.5px] text-[color:var(--ink-2)]"><span className="spinner" aria-hidden /> Running…</span> : null}>
            <div className="flex flex-wrap items-center gap-3">
              <Button size="sm" onClick={() => start('refresh')} disabled={s.pipeline.running || s.data_mode !== 'live'}>Fetch latest prices & news</Button>
              <Button size="sm" variant="secondary" onClick={() => start('train')} disabled={s.pipeline.running}>Retrain & re-evaluate</Button>
              {s.data_mode !== 'live' && <span className="text-[12px] text-[color:var(--ink-3)]">Live fetching is off in sample mode.</span>}
            </div>
            {jobMsg && <p className="mt-3 text-[13px] text-[color:var(--up)]">{jobMsg}</p>}
            {jobError && <div className="mt-3"><ErrorBox error={jobError} /></div>}
            {s.pipeline.last && (
              <p className="mt-3 text-[12.5px] text-[color:var(--ink-3)]">
                Last job: {s.pipeline.last.status} · {s.pipeline.last.steps.join(' → ')} · finished {fmtDateTime(s.pipeline.last.finished_at)} ({s.pipeline.last.seconds}s)
                {s.pipeline.last.error && <span className="text-[color:var(--down)]"> · {s.pipeline.last.error}</span>}
              </p>
            )}
          </Panel>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Panel title="Price coverage" sub="Per asset and source. Days are UTC; the running day is never stored.">
              <table className="data-table">
                <thead><tr><th>Asset</th><th>Source</th><th>From</th><th>To</th><th className="num">Days</th></tr></thead>
                <tbody>
                  {s.price_coverage.map(r => <tr key={r.symbol + r.source}><td>{r.symbol}</td><td>{r.source}</td><td>{fmtDate(r.first)}</td><td>{fmtDate(r.last)}</td><td className="num">{fmtInt(r.n)}</td></tr>)}
                  {s.assets_configured.filter(a => !s.price_coverage.some(r => r.symbol === a)).map(a => (
                    <tr key={a}><td>{a}</td><td colSpan={4} className="text-[color:var(--warn)]">No price data stored</td></tr>
                  ))}
                </tbody>
              </table>
            </Panel>
            <Panel title="Text coverage and quality" sub="Eligible texts linked to each asset, and why others were excluded.">
              <table className="data-table">
                <thead><tr><th>Asset</th><th>From</th><th>To</th><th className="num">Texts</th></tr></thead>
                <tbody>{s.text_coverage.map(r => <tr key={r.symbol}><td>{r.symbol}</td><td>{fmtDate(r.first)}</td><td>{fmtDate(r.last)}</td><td className="num">{fmtInt(r.n)}</td></tr>)}</tbody>
              </table>
              <div className="mt-3 flex flex-wrap gap-2">
                {s.text_quality.map(q => <span key={q.reason} className="rounded-lg border border-[color:var(--line)] px-2 py-1 text-[12px] text-[color:var(--ink-2)]">{q.reason.replace(/_/g, ' ')}: <span className="font-mono">{fmtInt(q.n)}</span></span>)}
              </div>
            </Panel>
          </div>

          <Panel title="Sources and pipeline steps" sub="Most recent attempt for each source or step. Errors here are recorded, not hidden; a failing source never blocks the others.">
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead><tr><th>Kind</th><th>Source / step</th><th>Status</th><th>Finished</th><th className="num">Fetched</th><th className="num">Stored</th><th>Message</th></tr></thead>
                <tbody>
                  {s.sources.map(r => (
                    <tr key={r.kind + r.source}>
                      <td>{r.kind}</td><td className="font-mono text-[12px]">{r.source}</td>
                      <td>{r.status === 'ok' ? <Tag tone="live">ok</Tag> : r.status === 'error' ? <Tag tone="warn">error</Tag> : <Tag tone="observed">{r.status}</Tag>}</td>
                      <td>{fmtDateTime(r.finished_at)}</td><td className="num">{fmtInt(r.n_fetched)}</td><td className="num">{fmtInt(r.n_inserted)}</td>
                      <td className="max-w-[360px] text-[12px] text-[color:var(--ink-3)]">{r.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <p className="text-[12px] text-[color:var(--ink-3)]">{s.disclaimer}</p>
        </>
      )}
    </div>
  );
}

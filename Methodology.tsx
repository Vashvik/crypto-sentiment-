'use client';

import { useState } from 'react';
import { Empty, ErrorBox, Loading, Panel, SectionTitle } from '@/components/dashboard/Panel';
import { ENGINE_LABELS, MODEL_LABELS, useApi, type EnginesResponse, type PerformanceResponse, type StatusResponse } from '@/lib/api';
import { featureLabel, fmtDate, fmtInt, fmtNum, fmtP, fmtPct, fmtSigned } from '@/lib/format';

export function Methodology() {
  const engines = useApi<EnginesResponse>('/sentiment/engines');
  const status = useApi<StatusResponse>('/status');
  const [symbol, setSymbol] = useState('BTC');
  const p1 = useApi<PerformanceResponse>(`/models/performance?symbol=${symbol}&horizon=1`);
  const p3 = useApi<PerformanceResponse>(`/models/performance?symbol=${symbol}&horizon=3`);
  const cfg = p1.data?.config;

  return (
    <div className="mx-auto max-w-[1100px] space-y-5">
      <header>
        <div className="kicker">E · Research & methodology</div>
        <h1 className="mt-1.5 text-[28px] font-semibold tracking-[-0.02em]">How the study works, and what it found</h1>
        <p className="mt-2 max-w-[80ch] text-[14px] leading-6 text-[color:var(--ink-3)]">
          Every number on this page is read from the latest model run in the backend, so it always matches the dashboard.
        </p>
      </header>

      <Panel title="Research question">
        <div className="prose-research">
          <p className="!mt-0">
            Does aggregated daily sentiment from news headlines and social media help predict cryptocurrency returns over the next
            1–3 days <strong>after accounting for volatility and momentum</strong>, and is its predictive value stable across market regimes?
          </p>
          <p>
            The test is an ablation: identical models are trained with market features only and with market + sentiment features. If
            sentiment carries information, the second version should have lower out-of-sample error, and the difference should survive a
            formal test (Diebold–Mariano). Granger-causality tests ask the same question in a regression framework, in both directions.
          </p>
        </div>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="1 · Data and the daily convention">
          <div className="prose-research">
            <ul className="!mt-0">
              <li><strong>Prices:</strong> Coin Metrics community data (daily reference close, reported spot volume, market cap) for BTC and ETH, 2020 – 2 Dec 2025. Live mode extends this with CoinGecko (no key needed) or Binance public klines (OHLCV).</li>
              <li><strong>Text:</strong> the CryptoPanic news dataset (CC0): headlines from about 200 crypto news sites plus some X/Twitter and Reddit posts, each tagged with the coins it concerns. Live mode adds RSS feeds and, with keys, the CryptoPanic API and Reddit.</li>
              <li><strong>Day boundary:</strong> all timestamps are UTC. Day <em>d</em> runs from 00:00 to 24:00 UTC; the close of <em>d</em> is the price at the end of that window, and texts published inside it belong to day <em>d</em>. A forecast for days d+1…d+h is made at the close of <em>d</em>, so every text it uses was already published.</li>
            </ul>
          </div>
        </Panel>
        <Panel title="2 · Cleaning the text">
          <div className="prose-research">
            <ul className="!mt-0">
              <li>HTML, URLs and odd whitespace removed; Unicode normalised.</li>
              <li>Exact duplicates (same headline after lower-casing and stripping punctuation) are kept once.</li>
              <li>Bot templates: posts that differ only in numbers (&ldquo;1,200 BTC transferred…&rdquo;) are excluded after their third appearance. The rule only looks backwards in time.</li>
              <li>Texts under 4 words, non-English text and obvious promotions are excluded but kept on record.</li>
              <li>Asset link: the source&apos;s own coin tags when present, otherwise whole-word keyword matching (e.g. &ldquo;Solana&rdquo; or &ldquo;$SOL&rdquo;, never the bare word &ldquo;sol&rdquo;).</li>
            </ul>
            {status.data && (
              <p className="text-[13px]">
                Current database: {status.data.text_quality.map(q => `${q.reason.replace('_', ' ')} ${fmtInt(q.n)}`).join(' · ')}.
              </p>
            )}
          </div>
        </Panel>
      </div>

      <SectionTitle kicker="Sentiment" title="3 · Choosing a sentiment engine on evidence" />
      <Panel title="Agreement with held-out community votes"
        sub={engines.data?.label_definition}>
        {engines.error ? <ErrorBox error={engines.error} onRetry={() => engines.mutate()} /> : !engines.data ? <Loading height={180} /> : (
          <>
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead><tr><th>Engine</th><th className="num">Val ROC-AUC</th><th className="num">Val macro-F1</th><th className="num">Val coverage</th><th className="num">Test ROC-AUC</th><th className="num">Test macro-F1</th><th className="num">n (val / test)</th></tr></thead>
                <tbody>
                  {['vader', 'vader_crypto', 'crypto_lr', 'finbert'].map(e => {
                    const r = engines.data!.engines[e];
                    const active = engines.data!.active === e;
                    return (
                      <tr key={e} className={active ? 'is-primary' : ''}>
                        <td>{ENGINE_LABELS[e]}{active ? ' · active' : ''}</td>
                        {r ? (
                          <>
                            <td className="num">{fmtNum(r.validation?.roc_auc, 3)}</td>
                            <td className="num">{fmtNum(r.validation?.macro_f1_sign, 3)}</td>
                            <td className="num">{fmtPct(r.validation?.coverage_non_neutral, 0, false)}</td>
                            <td className="num">{fmtNum(r.test?.roc_auc, 3)}</td>
                            <td className="num">{fmtNum(r.test?.macro_f1_sign, 3)}</td>
                            <td className="num">{fmtInt(r.validation?.n)} / {fmtInt(r.test?.n)}</td>
                          </>
                        ) : (
                          <td colSpan={6} className="text-[color:var(--ink-3)]">Not available in this installation (optional dependency not installed).</td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="prose-research">
              <p>
                Engines are compared on headlines whose CryptoPanic readers voted clearly positive or negative. The choice uses <strong>validation-period
                ROC-AUC only</strong> (how well the continuous score ranks positive above negative headlines); test-period agreement is shown but never used.
                {engines.data.crypto_lr_training && <> The vote-trained classifier learned from {fmtInt(engines.data.crypto_lr_training.n_train)} headlines dated on or before {fmtDate(engines.data.crypto_lr_training.label_cutoff)}, before the forecasting study starts, so its labels never overlap the period it scores.</>}
                {' '}Coverage is the share of headlines given a non-neutral score.
              </p>
              <p>Daily index for asset <em>a</em> on day <em>d</em>, over its eligible texts <em>i</em>:</p>
              <span className="formula">S(a, d) = Σ wᵢ·sᵢ / Σ wᵢ,   wᵢ = 1 (equal weights, the baseline)</span>
              <p>Alongside S the pipeline keeps the text count, positive / neutral / negative shares, the standard deviation of scores, and separate news and social means. A day with no eligible text has S missing and count 0. It is never set to neutral.</p>
            </div>
          </>
        )}
      </Panel>

      <SectionTitle kicker="Forecasting" title="4 · Features, targets and evaluation" />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Targets and features">
          <div className="prose-research">
            <span className="formula !mt-0">R(t, h) = P(t+h) / P(t) − 1,   h ∈ {'{'}1, 3{'}'}</span>
            <p>Rows whose forward window is incomplete or touches a missing price are dropped, never filled.</p>
            {cfg && (
              <>
                <h3>Market features ({cfg.market_features.length})</h3>
                <p className="text-[13px]">{cfg.market_features.map(featureLabel).join(' · ')}</p>
                <h3>Sentiment features ({cfg.sentiment_features.length})</h3>
                <p className="text-[13px]">{cfg.sentiment_features.map(featureLabel).join(' · ')}</p>
              </>
            )}
            <p>Every feature in row <em>t</em> uses data up to the close of <em>t</em> only; a unit test changes all data after <em>t</em> and checks that features at <em>t</em> stay identical.</p>
          </div>
        </Panel>
        <Panel title="Walk-forward evaluation">
          <div className="prose-research">
            {cfg && (
              <ul className="!mt-0">
                <li>Study window starts {fmtDate(cfg.study_start)}; the first {cfg.min_train_days} days are training-only.</li>
                <li>Expanding window, refit every {cfg.refit_every} days. For a block starting at day s, training rows satisfy t + h ≤ s (an embargo so overlapping 3-day targets cannot leak).</li>
                <li>Missing-value imputation (training medians plus missing flags) and scaling are fitted inside each refit on its training rows only.</li>
                <li>Predictions up to {fmtDate(cfg.validation_end)} form the <strong>validation</strong> period, used once to pick the primary model (lowest RMSE). Later predictions form the <strong>test</strong> period and are only reported.</li>
                <li>Candidates: {cfg.candidates.map(c => MODEL_LABELS[c]).join(' · ')}. Seed {cfg.seed}.</li>
                <li>Regimes: a day is high-volatility when its 30-day volatility is above the median of all earlier days (no look-ahead).</li>
              </ul>
            )}
          </div>
        </Panel>
      </div>

      <SectionTitle id="ablation" kicker="Results" title="5 · What the data says" />
      <div className="seg" role="group" aria-label="Asset">
        {['BTC', 'ETH'].map(s => <button key={s} type="button" aria-pressed={symbol === s} onClick={() => setSymbol(s)}>{s}</button>)}
      </div>
      {(p1.error || p3.error) ? <ErrorBox error={(p1.error || p3.error)!} onRetry={() => { p1.mutate(); p3.mutate(); }} /> : !p1.data || !p3.data ? <Loading height={300} /> : (
        <Results p1={p1.data} p3={p3.data} />
      )}

      <Panel title="6 · Limitations">
        <div className="prose-research">
          <ul className="!mt-0">
            <li><strong>Text coverage:</strong> the sample is mostly English news headlines; social posts tagged to BTC/ETH are few, so &ldquo;social&rdquo; sentiment is thin. Headlines are not full articles.</li>
            <li><strong>Engine quality:</strong> lexicon and small supervised models only reach moderate agreement with human votes (ROC-AUC around 0.6–0.7). Votes themselves are noisy and skew positive.</li>
            <li><strong>Sample size:</strong> about three years of daily out-of-sample predictions per asset. Small real effects can be invisible, and p-values across many comparisons should be read with care.</li>
            <li><strong>Selection bias in sources:</strong> CryptoPanic&apos;s source list and tagging decide which texts exist here. Live RSS history only starts when you start collecting.</li>
            <li><strong>Granger ≠ causation:</strong> the tests show incremental predictive information, not that mood moves prices (or the other way round).</li>
            <li><strong>Not a trading system:</strong> there are no transaction costs, slippage, position sizing or risk controls. A small statistical edge, if any, would not imply a profitable strategy.</li>
          </ul>
        </div>
      </Panel>
    </div>
  );
}

function Results({ p1, p3 }: { p1: PerformanceResponse; p3: PerformanceResponse }) {
  const pairs = [['ridge_sentiment_vs_ridge_market', 'Ridge'], ['gbr_sentiment_vs_gbr_market', 'Gradient boosting']] as const;
  const g = p1.granger;
  const mainGranger = g.filter(x => !x.regime);
  const regimeGranger = g.filter(x => x.regime);
  return (
    <div className="space-y-4">
      <Panel title={`Ablation by horizon, period and volatility regime · ${p1.symbol}`}
        sub="Diebold–Mariano statistic (negative = adding sentiment lowered squared error) and p-value; RMSE of each model on the same days.">
        <div className="overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Horizon</th><th>Model pair</th><th>Period</th><th>Regime</th><th className="num">RMSE with sent.</th><th className="num">RMSE market only</th><th className="num">DM stat</th><th className="num">p-value</th></tr></thead>
            <tbody>
              {[p1, p3].flatMap(p =>
                (['validation', 'test'] as const).flatMap(seg =>
                  pairs.flatMap(([key, label]) =>
                    ['all', 'high_vol', 'low_vol'].map(reg => {
                      const r = p.evaluation.ablation[seg]?.[reg === 'all' ? key : `${key}:${reg}`];
                      if (!r) return null;
                      return (
                        <tr key={`${p.horizon}${seg}${key}${reg}`}>
                          <td>{p.horizon}-day</td><td>{label}</td><td className="capitalize">{seg}</td><td>{reg === 'all' ? 'All days' : reg === 'high_vol' ? 'High volatility' : 'Low volatility'}</td>
                          <td className="num">{fmtNum(r.rmse_with_sentiment, 4)}</td><td className="num">{fmtNum(r.rmse_market_only, 4)}</td>
                          <td className="num">{fmtSigned(r.stat, 2)}</td>
                          <td className={`num ${r.p_value != null && r.p_value < 0.05 ? 'text-[color:var(--warn)]' : ''}`}>{fmtP(r.p_value)}</td>
                        </tr>
                      );
                    }),
                  ),
                ),
              )}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-[12px] text-[color:var(--ink-3)]">RMSE columns are blank for regime rows (the test is run on the regime&apos;s days only). Selected primary model: 1-day {MODEL_LABELS[p1.evaluation.selected_model]}, 3-day {MODEL_LABELS[p3.evaluation.selected_model]}.</p>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title="Granger tests (HAC-robust)" sub={p1.notes.granger}>
          <table className="data-table">
            <thead><tr><th>Direction</th><th className="num">Lags</th><th className="num">n</th><th className="num">F</th><th className="num">p-value</th></tr></thead>
            <tbody>
              {mainGranger.map((x, i) => (
                <tr key={i}>
                  <td>{x.direction === 'sentiment_to_returns' ? 'Sentiment → next-day return' : 'Return → next-day sentiment'}</td>
                  <td className="num">{x.lags}</td><td className="num">{fmtInt(x.n)}</td><td className="num">{fmtNum(x.f_stat, 2)}</td>
                  <td className={`num ${x.p_value != null && x.p_value < 0.05 ? 'text-[color:var(--warn)]' : ''}`}>{fmtP(x.p_value)}</td>
                </tr>
              ))}
              {regimeGranger.map((x, i) => (
                <tr key={`r${i}`}>
                  <td>Sentiment → return, {x.regime === 'high_vol' ? 'high-vol days' : 'low-vol days'}</td>
                  <td className="num">{x.lags}</td><td className="num">{fmtInt(x.n)}</td><td className="num">{fmtNum(x.f_stat, 2)}</td>
                  <td className={`num ${x.p_value != null && x.p_value < 0.05 ? 'text-[color:var(--warn)]' : ''}`}>{fmtP(x.p_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-[12px] leading-5 text-[color:var(--ink-3)]">Each regression controls for the asset&apos;s own lags and 7-day volatility; standard errors are Newey–West (5 lags). Highlighted p-values are below 0.05.</p>
        </Panel>
        <Panel title="Accuracy by volatility regime (test period)" sub="RMSE of each model on high- and low-volatility days.">
          {p1.evaluation.regimes.test ? (
            <table className="data-table">
              <thead><tr><th>Model</th><th className="num">1d high-vol</th><th className="num">1d low-vol</th><th className="num">3d high-vol</th><th className="num">3d low-vol</th></tr></thead>
              <tbody>
                {Object.keys(MODEL_LABELS).map(m => (
                  <tr key={m}>
                    <td>{MODEL_LABELS[m]}</td>
                    <td className="num">{fmtNum(p1.evaluation.regimes.test?.high_vol?.[m]?.rmse, 4)}</td>
                    <td className="num">{fmtNum(p1.evaluation.regimes.test?.low_vol?.[m]?.rmse, 4)}</td>
                    <td className="num">{fmtNum(p3.evaluation.regimes.test?.high_vol?.[m]?.rmse, 4)}</td>
                    <td className="num">{fmtNum(p3.evaluation.regimes.test?.low_vol?.[m]?.rmse, 4)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <Empty title="No test-period regime data" />}
        </Panel>
      </div>
      <Interpretation p1={p1} p3={p3} />
    </div>
  );
}

/** Plain-language reading generated from the numbers, so it can never contradict them. */
function Interpretation({ p1, p3 }: { p1: PerformanceResponse; p3: PerformanceResponse }) {
  const lines: string[] = [];
  for (const p of [p1, p3]) {
    const sel = p.evaluation.selected_model;
    const baseline = sel === 'zero' || sel === 'hist_mean';
    lines.push(`${p.horizon}-day horizon: the lowest validation error came from the ${MODEL_LABELS[sel].toLowerCase()}${baseline ? ', so no model, with or without sentiment, beat a naive forecast' : ''}.`);
    const sig = (['validation', 'test'] as const).flatMap(seg => ['ridge_sentiment_vs_ridge_market', 'gbr_sentiment_vs_gbr_market'].map(k => ({ seg, k, r: p.evaluation.ablation[seg]?.[k] })))
      .filter(x => x.r?.p_value != null && x.r.p_value < 0.05);
    lines.push(sig.length === 0
      ? `Adding sentiment did not change forecast accuracy significantly in either period (all Diebold–Mariano p ≥ 0.05).`
      : `Significant differences: ${sig.map(x => `${x.k.startsWith('ridge') ? 'Ridge' : 'Boosting'} in ${x.seg} (DM ${fmtSigned(x.r!.stat, 2)}, ${x.r!.stat! < 0 ? 'sentiment helped' : 'sentiment hurt'})`).join('; ')}.`);
  }
  const fwd = p1.granger.filter(g => !g.regime && g.direction === 'sentiment_to_returns' && g.p_value != null);
  const rev = p1.granger.filter(g => !g.regime && g.direction === 'returns_to_sentiment' && g.p_value != null);
  if (fwd.length && rev.length) {
    const fwdSig = fwd.some(g => (g.p_value as number) < 0.05);
    const revSig = rev.some(g => (g.p_value as number) < 0.05);
    lines.push(`Granger: sentiment ${fwdSig ? 'does' : 'does not'} add significant information about next-day returns at the lags tested, while past returns ${revSig ? 'do' : 'do not'} predict next-day sentiment${revSig && !fwdSig ? '. Mood mostly follows the market rather than leading it' : ''}.`);
  }
  return (
    <Panel title={`Reading the results for ${p1.symbol}`} sub="Generated from the figures above.">
      <ul className="list-disc space-y-1.5 pl-5 text-[14px] leading-6 text-[color:var(--ink-2)]">
        {lines.map((l, i) => <li key={i}>{l}</li>)}
      </ul>
    </Panel>
  );
}

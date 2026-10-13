'use client';

// Typed access to the FastAPI backend through the same-origin proxy at
// /api/backend (app/api/backend/[...path]/route.ts). SWR keys each request by
// its full URL, so a newer asset/date selection can never be overwritten by a
// slower response for an older one, and identical requests are de-duplicated.

import useSWR, { type SWRConfiguration } from 'swr';

export const BACKEND = '/api/backend/api/v1';

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BACKEND}${path}`, { cache: 'no-store', ...init });
  } catch {
    throw new ApiError('Cannot reach the backend. Is it running on port 8000?', 0);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status})`;
    throw new ApiError(detail, response.status);
  }
  return data as T;
}

export function useApi<T>(path: string | null, config?: SWRConfiguration<T, ApiError>) {
  return useSWR<T, ApiError>(path, (p: string) => apiFetch<T>(p), {
    revalidateOnFocus: false,
    shouldRetryOnError: (err: ApiError) => err.status === 0 || err.status >= 500,
    errorRetryCount: 2,
    keepPreviousData: true,
    ...config,
  });
}

export function qs(params: Record<string, string | number | null | undefined>) {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== '') q.set(k, String(v));
  const s = q.toString();
  return s ? `?${s}` : '';
}

// ── Response types ─────────────────────────────────────────────────────────

export type AssetSummary = {
  symbol: string;
  name: string;
  has_data: boolean;
  last_date?: string;
  last_close?: number;
  change_1d?: number | null;
  first_date?: string;
  n_days?: number;
  source?: string;
  volume_usd?: number | null;
  market_cap_usd?: number | null;
};
export type AssetsResponse = { assets: AssetSummary[]; data_mode: string };

export type MarketRow = {
  date: string; open: number | null; high: number | null; low: number | null; close: number | null;
  volume_usd: number | null; market_cap_usd: number | null; return_1d: number | null; source: string | null;
};
export type MarketResponse = { symbol: string; rows: MarketRow[]; missing_days: number; timezone: string; data_mode: string };

export type SentimentRow = {
  date: string; n_records: number; n_news: number; n_social: number; sent_mean: number | null; sent_std: number | null;
  pos_prop: number | null; neu_prop: number | null; neg_prop: number | null; sent_news: number | null; sent_social: number | null;
  close?: number | null; return_1d?: number | null; return_next_1d?: number | null;
};
export type SentimentDailyResponse = {
  symbol: string; engine: string; rows: SentimentRow[];
  correlation: { same_day: number; next_day: number; n: number; note: string } | null;
  missing_note: string;
};
export type SourcesResponse = {
  symbol: string; engine: string;
  by_type: { source_type: string; n: number; mean_score: number | null }[];
  by_domain: { source_type: string; domain: string; n: number; mean_score: number }[];
};
export type TextRecord = {
  published_at: string; title: string; source_type: string; domain: string; url: string | null;
  score: number; label: string; asset_link: string;
};
export type RecordsResponse = { symbol: string; day: string; engine: string; records: TextRecord[] };

export type Contributions = {
  kind: 'linear' | 'global_importance'; note: string; intercept?: number; alpha?: number;
  items: { feature: string; value: number }[];
};
export type Forecast = {
  id: number; run_id: string; symbol: string; horizon: number; model_name: string; label: string; is_primary: number;
  created_at: string; feature_date: string; target_date: string; reference_price: number; predicted_return: number;
  predicted_price: number; lower_return: number | null; upper_return: number | null; interval_note: string | null;
  contributions: Contributions | null; sentiment_available: number; realized_return: number | null;
  validation_rmse: number | null; test_rmse: number | null;
};
export type ForecastResponse = {
  symbol: string; run_id: string; disclaimer: string; selection_rule: string;
  horizons: Record<string, { horizon: number; primary: Forecast | null; models: Forecast[] }>;
};

export type Metrics = {
  n: number; mae: number; rmse: number; r2_oos_vs_zero: number | null; r2_oos_vs_mean?: number | null;
  direction_acc: number | null; up_share: number | null;
};
export type DMResult = {
  n: number; stat: number | null; p_value: number | null; mean_loss_diff?: number;
  rmse_with_sentiment?: number; rmse_market_only?: number; note?: string;
};
export type GrangerResult = {
  lags: number; direction: string; n: number; f_stat?: number; p_value?: number; r2?: number; regime?: string; note?: string;
};
export type PerformanceResponse = {
  symbol: string; horizon: number; run_id: string; created_at: string; engine: string;
  config: { study_start: string; validation_end: string; min_train_days: number; refit_every: number; seed: number;
    market_features: string[]; sentiment_features: string[]; candidates: string[]; data_mode: string; code_version: string };
  evaluation: {
    models: Record<string, { label: string; validation?: Metrics; test?: Metrics }>;
    ablation: Record<string, Record<string, DMResult>>;
    regimes: Record<string, Record<string, Record<string, Metrics>>>;
    selected_model: string; selection_rule: string;
  };
  data_start: string; data_end: string;
  coverage: { price_days: number; sentiment_days: number; sentiment_coverage: number; price_sources: Record<string, number> };
  granger: GrangerResult[];
  notes: Record<string, string>;
};

export type BacktestRow = { date: string; segment: string; regime: string | null; actual: number } & Record<string, number | string | null>;
export type BacktestResponse = { symbol: string; horizon: number; run_id: string; models: string[]; rows: BacktestRow[]; note?: string };

export type EngineMetrics = {
  n: number; positive_share: number; roc_auc: number; macro_f1_sign: number; accuracy_sign: number;
  coverage_non_neutral: number; accuracy_when_decided: number | null; note?: string;
};
export type EnginesResponse = {
  active: string; configured: string;
  selection: { selected: string; criterion: string; scores: Record<string, number>; at: string } | null;
  engines: Record<string, { validation?: EngineMetrics; test?: EngineMetrics }>;
  crypto_lr_training: { n_train: number; label_cutoff: string; first_date: string; last_date: string; positive_share: number } | null;
  label_definition: string;
};

export type JobStatus = {
  running: boolean;
  last: { started_at: string; finished_at: string; seconds: number; status: string; error: string | null; engine: string; live: boolean; steps: string[] } | null;
};
export type StatusResponse = {
  data_mode: string; data_mode_note: string; assets_configured: string[];
  price_coverage: { symbol: string; source: string; first: string; last: string; n: number; fetched_at: string }[];
  text_coverage: { symbol: string; first: string; last: string; n: number }[];
  text_quality: { reason: string; n: number }[];
  sources: { kind: string; source: string; status: string; started_at: string; finished_at: string | null; n_fetched: number; n_inserted: number; message: string | null }[];
  last_success: Record<string, string>;
  sentiment_engine: string;
  latest_model_run: { run_id: string; created_at: string; status: string; engine: string; data_mode: string; message: string | null } | null;
  pipeline: JobStatus;
  training_in_progress: boolean;
  disclaimer: string;
};

export const ENGINE_LABELS: Record<string, string> = {
  vader: 'VADER (baseline lexicon)',
  vader_crypto: 'VADER + crypto lexicon',
  crypto_lr: 'Vote-trained TF-IDF classifier',
  finbert: 'FinBERT (transformer)',
};

export const MODEL_LABELS: Record<string, string> = {
  zero: 'Zero-return baseline',
  hist_mean: 'Historical-mean baseline',
  ridge_market: 'Ridge · market only',
  ridge_sentiment: 'Ridge · market + sentiment',
  gbr_market: 'Gradient boosting · market only',
  gbr_sentiment: 'Gradient boosting · market + sentiment',
};

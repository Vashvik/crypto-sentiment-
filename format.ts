// Number and date formatters. Everything returns '–' for missing values so a
// gap is visible rather than shown as zero.

const DASH = '–';

export function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

export function fmtUsd(v: unknown, opts: { compact?: boolean } = {}) {
  if (!isNum(v)) return DASH;
  if (opts.compact && Math.abs(v) >= 1e6) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', notation: 'compact', maximumFractionDigits: 2 }).format(v);
  }
  const digits = Math.abs(v) >= 1000 ? 0 : Math.abs(v) >= 1 ? 2 : 4;
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: digits, minimumFractionDigits: digits }).format(v);
}

export function fmtPct(v: unknown, digits = 2, signed = true) {
  if (!isNum(v)) return DASH;
  const s = (v * 100).toFixed(digits);
  return `${signed && v > 0 ? '+' : ''}${s}%`;
}

export function fmtNum(v: unknown, digits = 3) {
  if (!isNum(v)) return DASH;
  return v.toFixed(digits);
}

export function fmtSigned(v: unknown, digits = 3) {
  if (!isNum(v)) return DASH;
  return `${v > 0 ? '+' : ''}${v.toFixed(digits)}`;
}

export function fmtInt(v: unknown) {
  if (!isNum(v)) return DASH;
  return new Intl.NumberFormat('en-US').format(Math.round(v));
}

export function fmtP(v: unknown) {
  if (!isNum(v)) return DASH;
  if (v < 0.001) return '< 0.001';
  return v.toFixed(3);
}

export function fmtDate(iso: string | null | undefined, withYear = true) {
  if (!iso) return DASH;
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00Z` : iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', ...(withYear ? { year: 'numeric' } : {}), timeZone: 'UTC' });
}

export function fmtDateTime(iso: string | null | undefined) {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return `${d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })} UTC`;
}

export function toneOf(v: unknown): 'up' | 'down' | 'flat' {
  if (!isNum(v) || v === 0) return 'flat';
  return v > 0 ? 'up' : 'down';
}

export function toneClass(v: unknown) {
  const t = toneOf(v);
  return t === 'up' ? 'text-[color:var(--up)]' : t === 'down' ? 'text-[color:var(--down)]' : 'text-[color:var(--ink-2)]';
}

export const FEATURE_LABELS: Record<string, string> = {
  ret_1: 'Return today',
  ret_lag1: 'Return 1 day ago',
  ret_lag2: 'Return 2 days ago',
  mom_5: '5-day momentum',
  mom_20: '20-day momentum',
  vol_7: '7-day volatility',
  vol_30: '30-day volatility',
  vol_ratio: 'Volatility ratio (7d / 30d)',
  volume_chg: 'Volume vs 7-day average',
  ma_gap_20: 'Gap to 20-day average',
  sent_mean: 'Sentiment today',
  sent_lag1: 'Sentiment yesterday',
  sent_ma3: 'Sentiment, 3-day mean',
  sent_ma7: 'Sentiment, 7-day mean',
  sent_shock: 'Sentiment vs 30-day mean',
  pos_prop: 'Share positive',
  neg_prop: 'Share negative',
  log_count: 'Text volume (log)',
  count_shock: 'Text volume spike',
};

export function featureLabel(name: string) {
  if (name.startsWith('missing:')) return `Missing: ${FEATURE_LABELS[name.slice(8)] ?? name.slice(8)}`;
  return FEATURE_LABELS[name] ?? name;
}

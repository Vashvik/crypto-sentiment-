// CryptoSentinel mark: a rounded frame (the watch post) with a sentiment
// waveform running through it, the last point lifted in the accent colour
// (the forecast). Original artwork; ring and wordmark use currentColor.

export function SentinelMark({ size = 26, className = '' }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden className={className}>
      <rect x="2.5" y="2.5" width="27" height="27" rx="8" stroke="currentColor" strokeWidth="2.6" />
      <path d="M7.5 19.5 11.5 15l3.5 4 4-7.5 3 3.5" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="24" cy="11" r="2.6" style={{ fill: 'var(--accent)' }} />
    </svg>
  );
}

export function Logo({ size = 26, className = '' }: { size?: number; className?: string }) {
  return (
    <span className={`inline-flex items-center gap-2 text-[color:var(--fg)] ${className}`}>
      <SentinelMark size={size} />
      <span className="text-[17px] font-semibold leading-none tracking-[-0.02em]">
        Crypto<span className="text-[color:var(--accent-text)]">Sentinel</span>
      </span>
    </span>
  );
}

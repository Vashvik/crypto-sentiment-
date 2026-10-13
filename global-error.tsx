'use client';

import './globals.css';

// Replaces the root layout when it fails, so it brings its own <html>.
// Plain system fonts: the layout's font loaders are part of what failed.
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, minHeight: '100dvh', background: 'var(--bg)', color: 'var(--fg)', fontFamily: 'system-ui, sans-serif' }}>
        <main style={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', padding: 24, textAlign: 'center' }}>
          <div style={{ maxWidth: 440 }}>

            <h1 style={{ margin: '20px 0 8px', fontSize: 28, fontWeight: 600 }}>CryptoSentinel hit a problem</h1>
            <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: 'var(--ink-2)' }}>
              The page couldn&apos;t load. Please try again in a moment.
            </p>
            <button
              type="button"
              onClick={reset}
              style={{ marginTop: 28, height: 44, padding: '0 24px', border: 0, borderRadius: 999, background: 'var(--fg)', color: 'var(--bg)', fontSize: 14, fontWeight: 600, cursor: 'pointer' }}
            >
              Try again
            </button>
          </div>
        </main>
      </body>
    </html>
  );
}

'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import { Logo } from '@/components/brand/Logo';
import { NAV } from '@/components/layout/nav';
import { SiteMenu } from '@/components/SiteMenu';
import { ThemeToggle } from '@/components/ThemeToggle';

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return (
    <>
      <header className="site-header print:hidden">
        <div className="mx-auto flex h-16 w-full max-w-[1280px] items-center gap-3 px-4 sm:px-6">
          <Link href="/" aria-label="CryptoSentinel home" className="shrink-0">
            <Logo />
          </Link>
          <nav aria-label="Main" className="ml-6 hidden items-center gap-1 md:flex">
            {NAV.map(item => {
              const active = item.href === '/' ? pathname === '/' : pathname?.startsWith(item.href);
              return (
                <Link key={item.href} href={item.href} className="nav-link" aria-current={active ? 'page' : undefined}>
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle className="hdr-icon hidden md:grid" />
            <SiteMenu />
          </div>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-[1280px] flex-1 px-4 pb-16 pt-6 outline-none sm:px-6">
        {children}
      </main>
      <SiteFooter />
    </>
  );
}

function SiteFooter() {
  return (
    <footer className="border-t border-[color:var(--line)] print:hidden">
      <div className="mx-auto flex w-full max-w-[1280px] flex-wrap items-start justify-between gap-6 px-4 py-8 text-[12.5px] text-[color:var(--ink-3)] sm:px-6">
        <div className="max-w-[60ch] space-y-2">
          <Logo size={22} />
          <p>
            Academic research project: <em>Aggregated Daily Sentiment Analysis for Predicting Short-Term Crypto Returns</em>.
            Forecasts are statistical estimates with large errors. Not investment advice.
          </p>
          <p>
            Data: price history by <a className="underline hover:text-[color:var(--fg)]" href="https://coinmetrics.io/community-network-data/" target="_blank" rel="noreferrer">Coin Metrics</a> (CC BY-NC 4.0);
            headlines from the <a className="underline hover:text-[color:var(--fg)]" href="https://github.com/soheilrahsaz/cryptoNewsDataset" target="_blank" rel="noreferrer">CryptoPanic news dataset</a> (CC0);
            live prices by CoinGecko / Binance when enabled.
          </p>
        </div>
        <nav aria-label="Footer" className="flex gap-5">
          <Link href="/methodology" className="hover:text-[color:var(--fg)]">Methodology</Link>
          <Link href="/status" className="hover:text-[color:var(--fg)]">Status</Link>
          <Link href="/privacy" className="hover:text-[color:var(--fg)]">Privacy</Link>
          <Link href="/terms" className="hover:text-[color:var(--fg)]">Terms</Link>
        </nav>
      </div>
    </footer>
  );
}

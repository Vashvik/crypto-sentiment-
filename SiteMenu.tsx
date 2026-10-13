'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { usePresence } from '@/components/motion/usePresence';
import { NAV } from '@/components/layout/nav';
import { setTheme, useTheme, type Theme } from '@/lib/theme';

/** Phone menu: every page, the theme switch and the legal links in one sheet. */
export function SiteMenu({ className = 'md:hidden' }: { className?: string }) {
  const [open, setOpen] = useState(false);
  const presence = usePresence(open, 160);
  const wrapRef = useRef<HTMLDivElement>(null);
  const pathname = usePathname();
  const theme = useTheme();

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('pointerdown', onPointer);
    window.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      window.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const themes: { value: Theme; label: string }[] = [
    { value: 'light', label: 'Light' },
    { value: 'dark', label: 'Dark' },
  ];

  return (
    <div ref={wrapRef} className={`relative ${className}`}>
      <button type="button" onClick={() => setOpen(v => !v)} className="hdr-icon" aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open}>
        <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden>
          <path d={open ? 'M6 6l12 12M18 6 6 18' : 'M4 6.5h16M4 12h16M4 17.5h16'} />
        </svg>
      </button>
      {presence.mounted && (
        <div data-state={presence.state} className="anim-pop menu-sheet absolute right-0 top-full z-50 mt-2 w-[min(290px,calc(100vw-32px))] rounded-2xl p-1.5">
          <nav aria-label="Site">
            {NAV.map(item => {
              const active = item.href === '/' ? pathname === '/' : pathname?.startsWith(item.href);
              return (
                <Link key={item.href} href={item.href} onClick={() => setOpen(false)} aria-current={active ? 'page' : undefined}
                  className={`block rounded-xl px-3 py-2.5 text-[14.5px] transition hover:bg-white/[0.06] ${active ? 'bg-white/[0.06] text-[color:var(--fg)]' : 'text-[color:var(--ink-2)]'}`}>
                  {item.label}
                </Link>
              );
            })}
          </nav>
          <div className="mx-1.5 my-1.5 h-px bg-[color:var(--line)]" />
          <div className="flex items-center justify-between gap-3 px-3 py-2">
            <span id="menu-theme" className="text-[13.5px] text-[color:var(--ink-2)]">Theme</span>
            <div role="radiogroup" aria-labelledby="menu-theme" className="seg">
              {themes.map(t => (
                <button key={t.value} type="button" role="radio" aria-checked={theme === t.value} onClick={() => setTheme(t.value)}>
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex gap-4 px-3 pb-2 pt-1 text-[12.5px] text-[color:var(--ink-3)]">
            <Link href="/privacy" onClick={() => setOpen(false)} className="hover:text-[color:var(--fg)]">Privacy</Link>
            <Link href="/terms" onClick={() => setOpen(false)} className="hover:text-[color:var(--fg)]">Terms</Link>
          </div>
        </div>
      )}
    </div>
  );
}

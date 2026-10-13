'use client';

import type { ReactNode } from 'react';
import { Button, EmptyState, Skeleton, cn } from '@/components/ui';
import type { ApiError } from '@/lib/api';

export function Panel({
  title,
  sub,
  actions,
  children,
  className,
  id,
}: {
  title: ReactNode;
  sub?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section id={id} className={cn('panel min-w-0 p-4 sm:p-5', className)}>
      <div className="panel-head">
        <div className="min-w-0">
          <h3 className="panel-title">{title}</h3>
          {sub != null && <p className="panel-sub max-w-[72ch]">{sub}</p>}
        </div>
        {actions != null && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

export function SectionTitle({ kicker, title, sub, id }: { kicker: string; title: string; sub?: ReactNode; id?: string }) {
  return (
    <div id={id} className="scroll-mt-24 pt-6">
      <div className="kicker">{kicker}</div>
      <h2 className="mt-1.5 text-[22px] font-semibold tracking-[-0.02em]">{title}</h2>
      {sub != null && <p className="mt-1.5 max-w-[80ch] text-[13.5px] leading-6 text-[color:var(--ink-3)]">{sub}</p>}
    </div>
  );
}

export function Loading({ height = 240 }: { height?: number }) {
  return <Skeleton className="w-full" style={{ height }} />;
}

export function ErrorBox({ error, onRetry }: { error: ApiError | Error; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[rgb(var(--down-rgb)/0.35)] bg-[rgb(var(--down-rgb)/0.07)] px-4 py-3 text-[13px] text-[color:var(--ink-2)]">
      <span>{error.message}</span>
      {onRetry && (
        <Button size="sm" variant="secondary" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function Empty({ title, description }: { title: string; description?: ReactNode }) {
  return <EmptyState title={title} description={description} className="py-8" />;
}

export function Tag({ tone, children }: { tone: 'observed' | 'model' | 'sample' | 'live' | 'warn'; children: ReactNode }) {
  const styles: Record<string, string> = {
    observed: 'border-[color:var(--line)] text-[color:var(--ink-2)] bg-[rgb(var(--fg-rgb)/0.04)]',
    model: 'border-[rgb(var(--accent-rgb)/0.4)] text-[color:var(--accent-text)] bg-[rgb(var(--accent-rgb)/0.1)]',
    sample: 'border-[rgb(var(--warn-rgb)/0.4)] text-[color:var(--warn)] bg-[rgb(var(--warn-rgb)/0.08)]',
    live: 'border-[rgb(var(--up-rgb)/0.4)] text-[color:var(--up)] bg-[rgb(var(--up-rgb)/0.08)]',
    warn: 'border-[rgb(var(--warn-rgb)/0.4)] text-[color:var(--warn)] bg-[rgb(var(--warn-rgb)/0.08)]',
  };
  return (
    <span className={cn('inline-flex items-center rounded-md border px-1.5 py-[1px] text-[10px] font-bold uppercase tracking-[0.1em]', styles[tone])}>
      {children}
    </span>
  );
}

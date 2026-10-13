import type { ReactNode } from 'react';

/** Shared frame for the 404 and error screens. */
export function StatusPage({ code, title, body, children }: { code: string; title: string; body: string; children: ReactNode }) {
  return (
    <section className="mx-auto flex min-h-[60vh] max-w-[560px] flex-col items-center justify-center text-center">
      <span className="font-mono text-[12px] tracking-[0.3em] text-[color:var(--ink-3)]">{code}</span>
      <h1 className="mt-4 text-[32px] font-semibold tracking-[-0.02em]">{title}</h1>
      <p className="mt-3 text-[15px] leading-7 text-[color:var(--ink-2)]">{body}</p>
      <div className="mt-8 flex flex-wrap justify-center gap-3">{children}</div>
    </section>
  );
}

import type { ReactNode } from 'react';
import { LEGAL_LAST_UPDATED } from '@/lib/site';

export type LegalSection = { id: string; title: string; body: ReactNode };

export function LegalPage({ title, summary, sections }: { title: string; summary: ReactNode; sections: LegalSection[] }) {
  return (
    <article className="prose-research mx-auto max-w-[72ch]">
      <h1 className="text-[30px] font-semibold tracking-[-0.02em] text-[color:var(--fg)]">{title}</h1>
      <p className="text-[13px] !text-[color:var(--ink-3)]">Last updated {LEGAL_LAST_UPDATED}</p>
      <div className="panel mt-6 p-5">{summary}</div>
      {sections.map((s, i) => (
        <section key={s.id} id={s.id} className="mt-8">
          <h3>{i + 1}. {s.title}</h3>
          {s.body}
        </section>
      ))}
    </article>
  );
}

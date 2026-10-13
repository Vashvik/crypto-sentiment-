/** Site-wide facts used by metadata and the legal pages. */
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || 'http://localhost:3000').replace(/\/$/, '');
export const SITE_NAME = 'CryptoSentinel';
export const SITE_TAGLINE = 'Aggregated daily sentiment and short-term crypto returns';
export const SITE_DESCRIPTION =
  'A research dashboard testing whether aggregated daily news and social-media sentiment helps predict 1–3 day Bitcoin and Ethereum returns beyond momentum and volatility. Academic project, not investment advice.';
export const LEGAL_LAST_UPDATED = '13 October 2026';

export function pageMetadata({ title, description, path }: { title: string; description: string; path: string }) {
  return {
    title,
    description,
    alternates: { canonical: path },
    openGraph: { type: 'website' as const, siteName: SITE_NAME, url: path, title: `${title} · ${SITE_NAME}`, description },
  };
}

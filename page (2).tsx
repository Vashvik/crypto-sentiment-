import { LegalPage } from '@/components/legal/LegalPage';
import { pageMetadata } from '@/lib/site';

export const metadata = pageMetadata({ title: 'Terms of use', description: 'Research use only. Not investment advice.', path: '/terms' });

export default function TermsPage() {
  return (
    <LegalPage
      title="Terms of use"
      summary={<p className="!mt-0"><strong>Research and teaching use only. Nothing here is investment advice.</strong> Forecasts are statistical estimates with large errors, made by models that, in this study, mostly did not beat naive baselines.</p>}
      sections={[
        { id: 'purpose', title: 'Purpose', body: <p>CryptoSentinel is a university data-science project that studies whether aggregated news and social-media sentiment helps predict 1–3 day cryptocurrency returns. It is not a trading system: it ignores transaction costs, liquidity and risk management.</p> },
        { id: 'data', title: 'Data and attribution', body: <p>Historical prices: Coin Metrics Community Data, licensed CC BY-NC 4.0 (non-commercial use with attribution). Headlines: the CryptoPanic news dataset by Soheil Rahsaz (CC0). Live prices, when enabled: CoinGecko and Binance public APIs, subject to their own terms and rate limits. Original article rights stay with their publishers; only headlines and links are shown.</p> },
        { id: 'warranty', title: 'No warranty', body: <p>The software and data are provided as they are, without any warranty of accuracy, completeness or fitness for a purpose. Data can be delayed, missing or wrong.</p> },
      ]}
    />
  );
}

import { LegalPage } from '@/components/legal/LegalPage';
import { pageMetadata } from '@/lib/site';

export const metadata = pageMetadata({ title: 'Privacy', description: 'What CryptoSentinel stores.', path: '/privacy' });

export default function PrivacyPage() {
  return (
    <LegalPage
      title="Privacy"
      summary={<p className="!mt-0">CryptoSentinel has no accounts, no analytics and no advertising. It does not collect personal data.</p>}
      sections={[
        { id: 'browser', title: 'In your browser', body: <p>Your light/dark theme choice is saved in your browser&apos;s local storage. Nothing else is stored on your device.</p> },
        { id: 'server', title: 'On the server', body: <p>The backend stores market prices, public headlines and posts, sentiment scores and model results. Text you type into &ldquo;Score a headline&rdquo; is scored and discarded, not saved. Standard web-server logs (IP address, time, path) may be kept by whoever hosts the backend.</p> },
        { id: 'third', title: 'Third parties', body: <p>In live mode the backend, not your browser, calls CoinGecko, Binance&apos;s public market-data API, RSS feeds and optionally CryptoPanic and Reddit. Your browser only talks to this site.</p> },
      ]}
    />
  );
}

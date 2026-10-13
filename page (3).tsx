import { StatusView } from '@/components/research/StatusView';
import { pageMetadata } from '@/lib/site';

export const metadata = pageMetadata({
  title: 'Data & model status',
  description: 'Data coverage, source health, model runs and background jobs.',
  path: '/status',
});

export default function StatusPage() {
  return <StatusView />;
}

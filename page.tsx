import { Methodology } from '@/components/research/Methodology';
import { pageMetadata } from '@/lib/site';

export const metadata = pageMetadata({
  title: 'Research & methodology',
  description: 'Research question, data, sentiment construction, forecasting design, evaluation results and limitations.',
  path: '/methodology',
});

export default function MethodologyPage() {
  return <Methodology />;
}

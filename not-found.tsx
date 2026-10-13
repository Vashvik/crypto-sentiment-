import Link from 'next/link';
import { StatusPage } from '@/components/StatusPage';
import { Button } from '@/components/ui';

export const metadata = { title: 'Page not found', robots: { index: false } };

export default function NotFound() {
  return (
    <StatusPage code="404" title="This page doesn’t exist" body="The link may be old or the address may have a typo.">
      <Link href="/"><Button size="md">Back to the dashboard</Button></Link>
    </StatusPage>
  );
}

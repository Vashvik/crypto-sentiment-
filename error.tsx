'use client';

import Link from 'next/link';
import { useEffect } from 'react';
import { StatusPage } from '@/components/StatusPage';
import { Button } from '@/components/ui';

export default function ErrorPage({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <StatusPage code={error.digest ? `ERROR · ${error.digest}` : 'ERROR'} title="Something went wrong"
      body="This page hit an unexpected problem. Trying again usually fixes it; if the backend was restarting it may need a few seconds.">
      <Button onClick={reset}>Try again</Button>
      <Link href="/"><Button variant="secondary">Back to the dashboard</Button></Link>
    </StatusPage>
  );
}

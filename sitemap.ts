import type { MetadataRoute } from 'next';
import { SITE_URL } from '@/lib/site';

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return ['/', '/methodology', '/status', '/privacy', '/terms'].map((path, i) => ({
    url: `${SITE_URL}${path}`,
    lastModified: now,
    changeFrequency: i === 0 ? 'daily' : 'monthly',
    priority: i === 0 ? 1 : 0.5,
  }));
}

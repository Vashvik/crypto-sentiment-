import { NextRequest, NextResponse } from 'next/server';

import { getBackendBaseUrl } from '../../backend-url';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

type BackendRouteContext = {
  params: Promise<{
    path: string[];
  }>;
};

const HOP_BY_HOP_HEADERS = new Set([
  'connection',
  'content-length',
  'content-encoding',
  'host',
  'keep-alive',
  'proxy-authenticate',
  'proxy-authorization',
  'te',
  'trailer',
  'transfer-encoding',
  'upgrade',
]);

function getForwardHeaders(request: NextRequest) {
  const headers = new Headers();

  request.headers.forEach((value, key) => {
    const lowerKey = key.toLowerCase();
    if (HOP_BY_HOP_HEADERS.has(lowerKey) || lowerKey.startsWith('x-forwarded-')) {
      return;
    }
    headers.set(key, value);
  });

  headers.set('accept', request.headers.get('accept') || 'application/json');
  headers.set('x-cryptosentinel-proxy', 'nextjs');
  return headers;
}

function getResponseHeaders(response: Response) {
  const headers = new Headers();

  response.headers.forEach((value, key) => {
    const lowerKey = key.toLowerCase();
    if (HOP_BY_HOP_HEADERS.has(lowerKey)) {
      return;
    }
    headers.set(key, value);
  });

  headers.set('cache-control', 'no-store');
  return headers;
}

async function proxyToBackend(request: NextRequest, context: BackendRouteContext) {
  const { path } = await context.params;
  const backendPath = path[0] === 'api' && path[1] === 'v1' ? path.slice(2) : path;
  const targetUrl = new URL(`/api/v1/${backendPath.map(encodeURIComponent).join('/')}`, getBackendBaseUrl());
  targetUrl.search = request.nextUrl.search;

  try {
    const method = request.method.toUpperCase();
    const hasRequestBody = method !== 'GET' && method !== 'HEAD';
    const response = await fetch(targetUrl, {
      method,
      headers: getForwardHeaders(request),
      body: hasRequestBody ? await request.arrayBuffer() : undefined,
      cache: 'no-store',
    });

    return new NextResponse(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: getResponseHeaders(response),
    });
  } catch {
    return NextResponse.json(
      {
        detail: 'Cannot reach the CryptoSentinel backend. Start it with: cd backend && uvicorn main:app --port 8000',
      },
      { status: 502 }
    );
  }
}

export async function GET(request: NextRequest, context: BackendRouteContext) {
  return proxyToBackend(request, context);
}

export async function HEAD(request: NextRequest, context: BackendRouteContext) {
  return proxyToBackend(request, context);
}

export async function POST(request: NextRequest, context: BackendRouteContext) {
  return proxyToBackend(request, context);
}

export async function PUT(request: NextRequest, context: BackendRouteContext) {
  return proxyToBackend(request, context);
}

export async function PATCH(request: NextRequest, context: BackendRouteContext) {
  return proxyToBackend(request, context);
}

export async function DELETE(request: NextRequest, context: BackendRouteContext) {
  return proxyToBackend(request, context);
}

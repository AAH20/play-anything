import { NextResponse } from 'next/server';
import {
  createNeo4jStore,
  getNeo4jConfig,
  GRAPH_STORE_MAX_BYTES,
  GRAPH_STORE_TIMEOUT_MS,
  hasGraphStoreSafeOrigin,
  isGraphStoreAuthorized,
} from '../../../lib/neo4j-store';

export const runtime = 'nodejs';
export const maxDuration = 25;

function json(body: unknown, status = 200) {
  return NextResponse.json(body, { status, headers: { 'Cache-Control': 'no-store' } });
}

export async function GET() {
  return json({ enabled: Boolean(getNeo4jConfig() && process.env.GRAPH_STORE_ACCESS_TOKEN), mode: 'neo4j' });
}

export async function POST(request: Request) {
  if (!hasGraphStoreSafeOrigin(request)) return json({ error: 'Request origin is not allowed.' }, 403);
  if (!isGraphStoreAuthorized(request, process.env.GRAPH_STORE_ACCESS_TOKEN)) return json({ error: 'Graph store access token is missing or invalid.' }, 401);
  const config = getNeo4jConfig();
  if (!config) return json({ error: 'Neo4j graph storage is not configured.' }, 503);
  if (!(request.headers.get('content-type') || '').toLowerCase().startsWith('application/json')) return json({ error: 'Send a JSON request body.' }, 415);
  const declaredLength = Number(request.headers.get('content-length') || 0);
  if (declaredLength > GRAPH_STORE_MAX_BYTES) return json({ error: `Request body exceeds ${GRAPH_STORE_MAX_BYTES} bytes.` }, 413);

  let body: unknown;
  try {
    const reader = request.body?.getReader();
    if (!reader) return json({ error: 'Request body is empty.' }, 400);
    const chunks: Uint8Array[] = [];
    let total = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > GRAPH_STORE_MAX_BYTES) {
        await reader.cancel();
        return json({ error: `Request body exceeds ${GRAPH_STORE_MAX_BYTES} bytes.` }, 413);
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    body = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes));
  } catch (error) {
    return json({ error: error instanceof SyntaxError ? 'Request body is not valid JSON.' : 'Could not read request body.' }, 400);
  }

  if (!body || typeof body !== 'object' || !['load', 'save'].includes(String((body as Record<string, unknown>).action))) {
    return json({ error: 'action must be "load" or "save".' }, 400);
  }
  const input = body as Record<string, unknown>;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), GRAPH_STORE_TIMEOUT_MS);
  try {
    const store = createNeo4jStore(config);
    if (input.action === 'load') {
      const loaded = await store.load(controller.signal);
      return loaded ? json(loaded) : json({ error: 'No saved graph is available.' }, 404);
    }
    if (!Object.hasOwn(input, 'graph')) return json({ error: 'graph is required for save.' }, 400);
    const saved = await store.save(input.graph, controller.signal);
    return json(saved);
  } catch {
    if (controller.signal.aborted) return json({ error: 'Graph storage request timed out.' }, 504);
    // Keep Neo4j URIs, credentials, query text, and server error payloads private.
    return json({ error: 'Graph storage failed. Check server configuration and Neo4j status.' }, 502);
  } finally {
    clearTimeout(timer);
  }
}

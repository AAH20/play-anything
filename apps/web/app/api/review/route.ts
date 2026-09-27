import { NextResponse } from 'next/server';
import {
  hasSafeOrigin,
  isAuthorized,
  isReviewEnabled,
  parseReviewInput,
  REVIEW_DEADLINE_MS,
  REVIEW_MAX_BYTES,
  runModelReview,
} from '../../../lib/model-review';

export const runtime = 'nodejs';
export const maxDuration = 35;

function json(body: unknown, status = 200) {
  return NextResponse.json(body, { status, headers: { 'Cache-Control': 'no-store' } });
}

export async function GET() {
  return json({ enabled: isReviewEnabled() });
}

export async function POST(request: Request) {
  if (!hasSafeOrigin(request)) return json({ error: 'Request origin is not allowed.' }, 403);
  if (!isAuthorized(request)) return json({ error: 'Model review access token is missing or invalid.' }, 401);
  const contentType = request.headers.get('content-type') || '';
  if (!contentType.toLowerCase().startsWith('application/json')) return json({ error: 'Send a JSON request body.' }, 415);
  const declaredLength = Number(request.headers.get('content-length') || 0);
  if (declaredLength > REVIEW_MAX_BYTES) return json({ error: `Request body exceeds ${REVIEW_MAX_BYTES} bytes.` }, 413);

  let input;
  try {
    const reader = request.body?.getReader();
    if (!reader) return json({ error: 'Request body is empty.' }, 400);
    const chunks: Uint8Array[] = [];
    let total = 0;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.byteLength;
      if (total > REVIEW_MAX_BYTES) {
        await reader.cancel();
        return json({ error: `Request body exceeds ${REVIEW_MAX_BYTES} bytes.` }, 413);
      }
      chunks.push(value);
    }
    const bytes = new Uint8Array(total);
    let offset = 0;
    for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
    const raw = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    input = parseReviewInput(JSON.parse(raw));
  } catch (error) {
    const message = error instanceof SyntaxError ? 'Request body is not valid JSON.' : error instanceof Error ? error.message : 'Invalid review request.';
    return json({ error: message }, 400);
  }
  if (!isReviewEnabled()) return json({ error: 'Model review is disabled. Configure the server model, gateway key, and access token.' }, 503);

  const controller = new AbortController();
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => {
        controller.abort();
        reject(new Error('deadline'));
      }, REVIEW_DEADLINE_MS);
    });
    const result = await Promise.race([runModelReview(input, controller.signal), timeout]);
    return json(result);
  } catch (error) {
    if (error instanceof Error && error.message === 'deadline') return json({ error: 'Model review timed out after 30 seconds.' }, 504);
    // Provider errors can contain credentials, request bodies, and account details. Never return them to callers.
    return json({ error: 'Model review failed. Check server configuration and provider status.' }, 502);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

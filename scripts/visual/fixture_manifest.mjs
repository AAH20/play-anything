import fs from 'node:fs/promises';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { constants } from 'node:fs';

export const INDEXED_GRAPH_FIXTURE_NAMES = Object.freeze([
  'page-0.json', 'page-1.json', 'invalid-coverage.json', 'hostile-label.json'
]);
const MAX_FIXTURE_BYTES = 15_000_000;

async function readBounded(filename, limit) {
  const info = await fs.lstat(filename, { bigint: true });
  if (!info.isFile() || info.isSymbolicLink()) throw new Error('Fixture inputs must be regular files, not symlinks.');
  if (info.size > BigInt(limit)) throw new Error(`Fixture exceeds its ${limit}-byte limit.`);
  const handle = await fs.open(filename, constants.O_RDONLY |
    (constants.O_NOFOLLOW || 0) | (constants.O_NONBLOCK || 0));
  try {
    const opened = await handle.stat({ bigint: true });
    if (!opened.isFile() || opened.dev !== info.dev || opened.ino !== info.ino) {
      throw new Error('Fixture changed while opening; regular file identity is required.');
    }
    const parts = [], buffer = Buffer.alloc(65_536);
    let bytes = 0;
    while (bytes <= limit) {
      const { bytesRead } = await handle.read(buffer, 0, Math.min(buffer.length, limit - bytes + 1), null);
      if (!bytesRead) break;
      bytes += bytesRead;
      if (bytes > limit) throw new Error(`Fixture exceeds its ${limit}-byte limit.`);
      parts.push(Buffer.from(buffer.subarray(0, bytesRead)));
    }
    return Buffer.concat(parts, bytes);
  } finally {
    await handle.close();
  }
}

export async function loadIndexedGraphFixtures(directory) {
  // Hash integrity identifies input bytes; it does not authenticate an author.
  const files = [], payloads = new Map();
  for (const name of INDEXED_GRAPH_FIXTURE_NAMES) {
    const bytes = await readBounded(path.join(directory, name), MAX_FIXTURE_BYTES);
    payloads.set(name, bytes);
    files.push({ name, bytes: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex') });
  }
  let encoded;
  try { encoded = await readBounded(path.join(directory, 'manifest.json'), 65_536); }
  catch (error) {
    if (error.code === 'ENOENT') return { payloads, integrity: { manifest_integrity_verified: false,
      status: 'manifest_not_provided', scope: 'hash_integrity_only', files } };
    throw error;
  }
  const manifest = JSON.parse(encoded.toString('utf8'));
  if (manifest?.schema_version !== 1 || manifest.evidence_type !== 'synthetic_index_cli_fixture' ||
      !Array.isArray(manifest.files) || manifest.files.length !== INDEXED_GRAPH_FIXTURE_NAMES.length) {
    throw new Error('Invalid indexed fixture manifest.');
  }
  const declared = new Map();
  for (const row of manifest.files) {
    if (!row || !INDEXED_GRAPH_FIXTURE_NAMES.includes(row.name) || declared.has(row.name) ||
        !Number.isSafeInteger(row.bytes) || row.bytes < 0 || row.bytes > MAX_FIXTURE_BYTES ||
        typeof row.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(row.sha256)) {
      throw new Error('Invalid or duplicate fixture manifest record.');
    }
    declared.set(row.name, row);
  }
  for (const actual of files) {
    const expected = declared.get(actual.name);
    if (actual.bytes !== expected.bytes || actual.sha256 !== expected.sha256) {
      throw new Error(`Fixture integrity mismatch: ${actual.name}`);
    }
  }
  return { payloads, integrity: { manifest_integrity_verified: true, status: 'manifest_matches_inputs',
    scope: 'hash_integrity_only', manifest_sha256: createHash('sha256').update(encoded).digest('hex'), files } };
}

export async function verifyFixtureManifest(directory) {
  return (await loadIndexedGraphFixtures(directory)).integrity;
}

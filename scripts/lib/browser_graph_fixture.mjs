import { createHash } from 'node:crypto';
import { constants } from 'node:fs';
import fs from 'node:fs/promises';
import path from 'node:path';

export const MAX_GRAPH_FIXTURE_BYTES = 15_000_000;
export const DASHBOARD_BROWSER_USAGE = 'Usage: node scripts/verify_dashboard_browser.mjs http://127.0.0.1:PORT OUTPUT_DIRECTORY [--fixture-graph GRAPH_JSON]';

export function parseDashboardBrowserArgs(args) {
  if (!Array.isArray(args)) throw new TypeError('Arguments must be an array.');
  if (args.length === 2 && args.every(value => typeof value === 'string' && value.length > 0)) {
    return { url: args[0], output: args[1], fixturePath: null };
  }
  if (args.length === 4 && args[2] === '--fixture-graph' &&
      args.every(value => typeof value === 'string') && args[3].trim().length > 0) {
    return { url: args[0], output: args[1], fixturePath: args[3] };
  }
  throw new Error(DASHBOARD_BROWSER_USAGE);
}

async function readBounded(file, limit) {
  const info = await fs.lstat(file, { bigint: true });
  if (!info.isFile() || info.isSymbolicLink()) throw new Error('Graph fixture must be a regular file, not a symlink.');
  if (info.size > BigInt(limit)) throw new Error(`Graph fixture exceeds the ${limit}-byte browser import limit.`);
  const handle = await fs.open(file, constants.O_RDONLY | (constants.O_NOFOLLOW || 0) | (constants.O_NONBLOCK || 0));
  try {
    const opened = await handle.stat({ bigint: true });
    if (!opened.isFile() || opened.dev !== info.dev || opened.ino !== info.ino) {
      throw new Error('Graph fixture changed while opening; regular file identity is required.');
    }
    const chunks = [], buffer = Buffer.alloc(65_536);
    let bytes = 0;
    while (bytes <= limit) {
      const { bytesRead } = await handle.read(buffer, 0, Math.min(buffer.length, limit - bytes + 1), null);
      if (!bytesRead) break;
      bytes += bytesRead;
      if (bytes > limit) throw new Error(`Graph fixture exceeds the ${limit}-byte browser import limit.`);
      chunks.push(Buffer.from(buffer.subarray(0, bytesRead)));
    }
    return Buffer.concat(chunks, bytes);
  } finally {
    await handle.close();
  }
}

export async function loadBrowserGraphFixture(filePath) {
  const file = path.resolve(filePath);
  const bytes = await readBounded(file, MAX_GRAPH_FIXTURE_BYTES);
  const graph = JSON.parse(bytes.toString('utf8'));
  if (!graph || graph.version !== 1 || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) {
    throw new TypeError('Graph fixture must be a version 1 snapshot with node and edge arrays.');
  }
  const sha256 = createHash('sha256').update(bytes).digest('hex');
  const identity = `sha256:${sha256}`;
  const evidenceMessage = `Fixed browser graph fixture (${path.basename(file)}; ${identity}). The displayed graph is static test data, not evidence about the selected repository.`;
  const annotatedGraph = JSON.parse(JSON.stringify(graph));
  annotatedGraph.fixture_evidence = { type: 'fixed_browser_fixture', file: path.basename(file), sha256 };
  const fileNodes = annotatedGraph.nodes.filter(node => node?.kind === 'file' && typeof node.path === 'string');
  annotatedGraph.analysis = {
    status: 'partial', complete: false, sample_fallback: false, source_kind: 'browser_fixed_fixture',
    message: evidenceMessage, file_count: fileNodes.length, analyzed_files: 0,
    unparsed_files: fileNodes.length, parse_errors: 0, unreadable_files: 0, too_large_files: 0,
  };
  const fileById = new Map(fileNodes.map(node => [node.id, node]));
  const groups = new Map();
  for (const node of fileNodes) {
    const parts = node.path.split('/');
    const group = parts.length > 1 ? parts[0] : 'root files';
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(node.path);
  }
  const edges = annotatedGraph.edges.flatMap(edge => {
    const importer = fileById.get(edge.source);
    const dependency = fileById.get(edge.target);
    return importer && dependency
      ? [[dependency.path, importer.path]] : [];
  });
  const analysis = {
    status: 'partial', complete: false, sample_fallback: false, source_kind: 'browser_fixed_fixture',
    message: evidenceMessage, file_count: fileNodes.length, analyzed_files: 0,
    unparsed_files: fileNodes.length, parse_errors: 0, unreadable_files: 0, too_large_files: 0,
    file_limit: fileNodes.length, file_limit_reached: false,
  };
  const report = {
    id: `browser-fixture-${sha256.slice(0, 20)}`,
    name: `Fixed fixture · ${annotatedGraph.name || 'graph'}`,
    url: `fixture:${identity}`,
    files: fileNodes.map(node => ({ path: node.path, analysis: 'unparsed_language', lines_of_code: 0, complexity: 0, imports: [] })),
    edges,
    graph: annotatedGraph,
    groups: [...groups].sort(([a], [b]) => a.localeCompare(b)).map(([name, files]) => ({ name, files: files.sort() })),
    licenses: [],
    truncated: Boolean(annotatedGraph.truncated || annotatedGraph.coverage?.has_next || annotatedGraph.coverage?.source_partial),
    python_files: 0,
    analysis,
  };
  return { graph: annotatedGraph, report, identity, sha256, file: path.basename(file), bytes: bytes.byteLength, message: evidenceMessage };
}

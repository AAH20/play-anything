import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import { createHash } from 'node:crypto';
import { verifyFixtureManifest, loadIndexedGraphFixtures, INDEXED_GRAPH_FIXTURE_NAMES } from '../../scripts/visual/fixture_manifest.mjs';

async function withFixtures(action) {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), 'indexed-fixture-integrity-'));
  const files = [];
  try {
    for (const name of INDEXED_GRAPH_FIXTURE_NAMES) {
      const data = Buffer.from(JSON.stringify({ fixture: name }));
      await fs.writeFile(path.join(directory, name), data);
      files.push({ name, bytes: data.length, sha256: createHash('sha256').update(data).digest('hex') });
    }
    const manifest = { schema_version: 1, evidence_type: 'synthetic_index_cli_fixture', files };
    await fs.writeFile(path.join(directory, 'manifest.json'), JSON.stringify(manifest));
    await action(directory, manifest);
  } finally { await fs.rm(directory, { recursive: true, force: true }); }
}

test('all four input hashes are checked and absent manifests remain explicitly unverified', async () => {
  await withFixtures(async directory => {
    const verified = await verifyFixtureManifest(directory);
    assert.equal(verified.manifest_integrity_verified, true);
    assert.equal(verified.files.length, 4);
    assert.equal(verified.scope, 'hash_integrity_only');
    await fs.unlink(path.join(directory, 'manifest.json'));
    const legacy = await verifyFixtureManifest(directory);
    assert.equal(legacy.manifest_integrity_verified, false);
    assert.equal(legacy.status, 'manifest_not_provided');
    assert.equal(legacy.files.length, 4);
  });
});

test('changed fixture bytes and dishonest manifest sizes fail before browser execution', async () => {
  await withFixtures(async directory => {
    await fs.writeFile(path.join(directory, 'page-1.json'), '{}');
    await assert.rejects(verifyFixtureManifest(directory), /integrity mismatch/);
  });
  await withFixtures(async (directory, manifest) => {
    manifest.files[0].bytes++;
    await fs.writeFile(path.join(directory, 'manifest.json'), JSON.stringify(manifest));
    await assert.rejects(verifyFixtureManifest(directory), /integrity mismatch/);
  });
});

test('duplicate, escaping and malformed manifest records are rejected', async () => {
  for (const mutate of [m => { m.files[1] = m.files[0]; },
                        m => { m.files[0].name = '../private.json'; },
                        m => { m.files[0].sha256 = 'not-a-hash'; }]) {
    await withFixtures(async (directory, manifest) => {
      mutate(manifest);
      await fs.writeFile(path.join(directory, 'manifest.json'), JSON.stringify(manifest));
      await assert.rejects(verifyFixtureManifest(directory), /Invalid or duplicate/);
    });
  }
});

test('symlinked fixtures and over-limit files cannot be accepted', async () => {
  await withFixtures(async directory => {
    await fs.unlink(path.join(directory, 'page-0.json'));
    await fs.symlink(path.join(directory, 'page-1.json'), path.join(directory, 'page-0.json'));
    await assert.rejects(verifyFixtureManifest(directory), /regular files/);
  });
  await withFixtures(async directory => {
    const handle = await fs.open(path.join(directory, 'page-0.json'), 'w');
    try { await handle.truncate(15_000_001); } finally { await handle.close(); }
    await assert.rejects(verifyFixtureManifest(directory), /byte limit/);
  });
});

test('loaded payloads retain the exact hashed input bytes if files later change', async () => {
  await withFixtures(async directory => {
    const loaded = await loadIndexedGraphFixtures(directory);
    const original = Buffer.from(loaded.payloads.get('page-0.json'));
    await fs.writeFile(path.join(directory, 'page-0.json'), '{"changed":true}');
    assert.deepEqual(loaded.payloads.get('page-0.json'), original);
    assert.equal(createHash('sha256').update(original).digest('hex'),
      loaded.integrity.files.find(file => file.name === 'page-0.json').sha256);
  });
});

test('a symlink replacement between path checking and opening cannot be followed', async () => {
  await withFixtures(async directory => {
    const originalOpen = fs.open;
    let replaced = false;
    fs.open = async (filename, ...arguments_) => {
      if (!replaced && filename === path.join(directory, 'page-0.json')) {
        replaced = true;
        await fs.rename(filename, path.join(directory, 'old-page-0.json'));
        await fs.symlink(path.join(directory, 'page-1.json'), filename);
      }
      return originalOpen(filename, ...arguments_);
    };
    try {
      await assert.rejects(loadIndexedGraphFixtures(directory), error =>
        error.code === 'ELOOP' || /regular file identity/.test(error.message));
      assert.equal(replaced, true);
    } finally { fs.open = originalOpen; }
  });
});

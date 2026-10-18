import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { resolve } from 'node:path';
import { once } from 'node:events';

test('CLI fails clearly when Python cannot launch, never synthesizes evidence', async () => {
  const child = spawn(process.execPath, [resolve('dist/cli.js')], {
    env: {...process.env, LITERATURE_EVIDENCE_PYTHON: '/missing-python-command-literature-mcp'},
    stdio: ['ignore','pipe','pipe'],
  });
  const stderr = [];
  child.stderr.on('data', chunk => stderr.push(chunk.toString()));
  const [exitCode] = await once(child,'exit');
  assert.notEqual(exitCode, 0);
  assert.match(stderr.join(''), /Literature Evidence MCP startup failed:/);
});

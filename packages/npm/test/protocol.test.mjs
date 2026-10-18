import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { resolve } from 'node:path';

const cli = resolve('dist/cli.js');

test('TypeScript MCP stdio forwards real Python tools without changing scientific verdict', async () => {
  const client = new Client({ name: 'npm-protocol-regression', version: '0.1.0' });
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [cli],
    env: { ...process.env, LITERATURE_EVIDENCE_PYTHON: process.env.LITERATURE_EVIDENCE_PYTHON },
  });
  try {
    await client.connect(transport);
    const { tools } = await client.listTools();
    assert.equal(tools.length, 33);
    const names = new Set(tools.map(tool => tool.name));
    assert(names.has('verify_claim'));
    assert(names.has('bm25_rank_evidence'));
    assert(names.has('nli_assess_challenger_evidence'));
    assert(names.has('export_bibliography'));
    assert(names.has('audit_methodology'));
    const response = await client.callTool({name: 'verify_claim', arguments: {
      quote: 'null effect', source_text: 'A null effect was measured.', source_id: 'test:article',
    }});
    assert.equal(response.isError, false);
    const info = response.structuredContent ?? JSON.parse(response.content[0].text);
    assert.equal(info.scientific_claim_verified, false);
    assert.equal(info.status, 'TEXTUAL_MATCH_ONLY');
  } finally {
    await client.close();
  }
});

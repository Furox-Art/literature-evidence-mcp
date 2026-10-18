import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Client } from '@modelcontextprotocol/client';
import { InMemoryTransport, McpServer } from '@modelcontextprotocol/server';
import { connectPython, listAllTools, registerBackendTools } from '../dist/adapter.js';
import { selectPython } from '../dist/cli.js';

const schema = { type: 'object', properties: { value: { type: 'number' } }, required: ['value'], additionalProperties: false };

test('retains pagination and discovers each tool page', async () => {
  const seen = [];
  const tools = await listAllTools(async cursor => {
    seen.push(cursor);
    return cursor ? { tools: [{ name: 'b', inputSchema: schema }] } : {
      tools: [{ name: 'a', inputSchema: schema }], nextCursor: 'page:2',
    };
  });
  assert.deepEqual(seen, [undefined, 'page:2']);
  assert.deepEqual(tools.map(t => t.name), ['a', 'b']);
});

test('retains full MCP schema and backend success/error responses', async () => {
  const server = new McpServer({ name: 'adapter-test', version: '0.1.0' });
  const forwarded = [];
  registerBackendTools(server, [
    { name: 'echo_success', description: 'Test tool', title: 'Echo', inputSchema: schema },
    { name: 'echo_error', description: 'A failure', inputSchema: schema },
  ], async (name, args) => {
    forwarded.push({name, args});
    return {content: [{ type: 'text', text: JSON.stringify(args) }], isError: name === 'echo_error'};
  });
  const [a,b] = InMemoryTransport.createLinkedPair();
  const client = new Client({ name: 'test-host', version: '1.0.0' });
  try {
    await Promise.all([server.connect(a), client.connect(b)]);
    const result = await client.listTools();
    assert.equal(result.tools.find(t => t.name === 'echo_success').description, 'Test tool');
    assert.equal(result.tools.find(t => t.name === 'echo_success').inputSchema.required[0], 'value');
    const success = await client.callTool({name: 'echo_success', arguments: {value: 5}});
    const failure = await client.callTool({name: 'echo_error', arguments: {value: 2}});
    assert.equal(success.isError ?? false, false);
    assert.equal(failure.isError, true);
    assert.deepEqual(forwarded, [
      {name:'echo_success',args:{value:5}},
      {name:'echo_error',args:{value:2}},
    ]);
  } finally {
    await client.close();
    await server.close();
  }
});

test('unavailable backend fails rather than returning empty results', async () => {
  await assert.rejects(connectPython('/does-not-exist-literature-python'));
});

test('Python executable selection supports Windows, Unix and explicit override', () => {
  assert.equal(selectPython(undefined, 'win32'), 'python');
  assert.equal(selectPython(undefined, 'linux'), 'python3');
  assert.equal(selectPython('/path/to/python', 'win32'), '/path/to/python');
});

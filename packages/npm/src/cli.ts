#!/usr/bin/env node
import { serveStdio } from '@modelcontextprotocol/server/stdio';
import { connectPython } from './adapter.js';

export function selectPython(explicit: string | undefined, platform: string): string {
  return explicit || (platform === 'win32' ? 'python' : 'python3');
}

export async function main(): Promise<void> {
  const executable = selectPython(process.env.LITERATURE_EVIDENCE_PYTHON, process.platform);
  const { server, python } = await connectPython(executable);
  const handle = serveStdio(() => server);
  const shutdown = async () => {
    await handle.close();
    await python.close();
  };
  process.once('SIGINT', shutdown);
  process.once('SIGTERM', shutdown);
}

if (import.meta.main) {
  main().catch((error: unknown) => {
    process.stderr.write(`Literature Evidence MCP startup failed: ${String(error)}\n`);
    process.exitCode = 1;
  });
}

import { Client } from '@modelcontextprotocol/client';
import { StdioClientTransport } from '@modelcontextprotocol/client/stdio';
import { McpServer, fromJsonSchema } from '@modelcontextprotocol/server';
import type { Tool, JsonSchemaType } from '@modelcontextprotocol/server';

/** Forwards MCP tool calls without interpreting bibliographic or scientific evidence. */
export function registerBackendTools(
  server: McpServer,
  tools: Tool[],
  forward: (name: string, args: Record<string, unknown>) => Promise<Awaited<ReturnType<Client['callTool']>>>,
): void {
  for (const tool of tools) {
    server.registerTool(tool.name, {
      title: tool.title,
      description: tool.description,
      inputSchema: fromJsonSchema<Record<string, unknown>>(tool.inputSchema as unknown as JsonSchemaType),
      // The Python server retains the authoritative input and result contracts.
    }, async (args) => forward(tool.name, args));
  }
}

/** List every tool page, preserving advertised JSON Schemas. */
export async function listAllTools(
  fetchPage: (cursor?: string) => Promise<{ tools: Tool[]; nextCursor?: string }>,
): Promise<Tool[]> {
  const tools: Tool[] = [];
  let cursor: string | undefined;
  do {
    const page = await fetchPage(cursor);
    tools.push(...page.tools);
    cursor = page.nextCursor;
  } while (cursor);
  return tools;
}

export async function connectPython(
  executable: string,
  args: string[] = ['-m', 'literature_evidence_mcp.server'],
): Promise<{ server: McpServer; python: Client }> {
  const python = new Client({ name: 'literature-evidence-typescript-bridge', version: '0.5.1' });
  // Always force stdio inside the child; ignore an inherited HTTP setting.
  const env = { ...process.env, MCP_TRANSPORT: 'stdio' } as Record<string, string>;
  try {
    await python.connect(new StdioClientTransport({ command: executable, args, env }));
    const server = new McpServer({ name: 'literature-evidence-mcp-ts', version: '0.5.1' });
    const tools = await listAllTools(async (cursor) => {
      return await python.listTools({ cursor });
    });
    registerBackendTools(server, tools, (name, input) => python.callTool({ name, arguments: input }));
    return { server, python };
  } catch (error) {
    await python.close();
    throw error;
  }
}

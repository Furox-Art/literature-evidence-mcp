# Security policy

Do not expose unauthenticated Streamable HTTP to a public interface. Keep API keys in environment variables. The server uses an explicit allowlist of provider hosts and routes; report any SSRF, key leakage, metadata injection or rights-related issue privately to the repository maintainers via GitHub security reporting if enabled. Do not paste secrets into public issues.

Version 0.1 has no authentication layer and is supported only as a localhost MCP server. Default network calls are outbound HTTPS to known providers.

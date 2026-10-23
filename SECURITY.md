# Security policy

## Supported versions

The latest release published on PyPI (`literature-evidence-mcp` 0.5.x at the time of writing) receives security fixes. Fixes ship as patch releases; older minor versions are not maintained. If you are unsure whether a version is supported, check the latest release on [PyPI](https://pypi.org/project/literature-evidence-mcp/).

## Reporting a vulnerability

Do **not** open a public issue for a suspected vulnerability. Report it privately through GitHub's private vulnerability reporting:

<https://github.com/Furox-Art/literature-evidence-mcp/security/advisories/new>

Please include:

- the affected version and how it was installed (wheel, source, container);
- a minimal reproduction, including configuration and the MCP client used;
- the impact you observed or expect;
- any suggested fix or mitigation.

Do not include real API keys, credentials, or third-party personal data in the report. Use placeholders.

## What to expect

- **Acknowledgement:** within 3 business days.
- **Initial assessment:** within 7 calendar days, including a severity estimate and whether the report is in scope.
- **Fix or mitigation plan:** within 30 days of a confirmed high or critical vulnerability; lower-severity issues are scheduled with their fix release.
- **Disclosure:** we practise coordinated disclosure. We ask reporters to allow up to 90 days before public disclosure, and we publish a GitHub Security Advisory when a fix is available. You will be credited unless you ask to remain anonymous.

This project is maintained by a single maintainer; if you do not receive an acknowledgement within the window above, re-open the advisory thread rather than disclosing publicly.

## Scope

`literature-evidence-mcp` is supported only as a localhost MCP server. In-scope vulnerability classes include:

- SSRF or DNS-rebinding that bypasses the explicit provider host/route allowlist;
- API-key or credential exposure in logs, error messages, tool output, or generated files;
- prompt or metadata injection that causes requests to leave the allowlisted providers;
- path traversal or unsafe file handling in downloaded or cached content;
- vulnerabilities in the shipped package or its pinned runtime dependencies.

Out of scope: issues that require an already-compromised host, provider outages or third-party content, and missing authentication on a server deliberately exposed to a public interface (unsupported configuration).

## Hardening guidance

- Run the server on localhost and never expose unauthenticated Streamable HTTP to a public interface.
- Keep provider API keys in environment variables, never in checked-in files or MCP client configuration committed to source control.
- Keep the package up to date and review the allowlisted provider hosts before deployment.
- Treat tool output from external providers as untrusted data, not as instructions.

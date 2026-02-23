# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | Yes       |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, please report security issues by emailing:

**security@mnemox.ai**

Include the following in your report:

1. **Description** of the vulnerability
2. **Steps to reproduce** (or proof-of-concept)
3. **Impact assessment** — what could an attacker do?
4. **Affected versions** — which version(s) are impacted?

## Response Timeline

- **Acknowledgment:** Within 72 hours of receiving your report
- **Initial assessment:** Within 1 week
- **Fix timeline:** Depends on severity
  - Critical: Patch within 48 hours
  - High: Patch within 1 week
  - Medium/Low: Next scheduled release

## What Qualifies

- SQL injection or database access issues
- API key / credential exposure
- Authentication or authorization bypass
- Remote code execution
- Path traversal or file access
- Sensitive data in logs or error messages

## What Does NOT Qualify

- Denial of service (the MCP server is designed for local use)
- Issues requiring physical access to the machine
- Social engineering
- Bugs in third-party dependencies (report upstream, but let us know)

## Disclosure

We follow responsible disclosure. Once a fix is released, we will:

1. Credit the reporter (unless they prefer anonymity)
2. Publish a security advisory on GitHub
3. Update CHANGELOG.md with the fix

## Scope

This policy covers the TradeMemory Protocol codebase at:
https://github.com/mnemox-ai/tradememory-protocol

Thank you for helping keep TradeMemory secure.

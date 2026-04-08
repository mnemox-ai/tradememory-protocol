# ADR 003: MCP Protocol Choice

**Status:** Accepted  
**Date:** 2025-10-30  
**Authors:** Sean Peng  
**Supersedes:** None

## Context

TradeMemory needs an interface for AI agents to store trade decisions, recall similar past trades, query strategy performance, and manage trading plans. The interface must support both programmatic AI agent access and human-driven tooling (dashboards, debugging, MT5 synchronization).

We evaluated five options:

| Interface | AI Agent Integration | Human Tooling | Ecosystem | Schema Enforcement |
|-----------|---------------------|---------------|-----------|-------------------|
| REST API only | Manual (HTTP client) | Native (curl, browser) | Mature | OpenAPI/Pydantic |
| **MCP primary + REST secondary** | **Native (tool discovery)** | **REST for non-AI** | **Growing (11K+ servers)** | **FastMCP validation** |
| MCP only | Native | Poor (no curl/browser) | Growing | FastMCP |
| gRPC | Requires codegen | Poor | Mature but heavy | Protobuf |
| Custom protocol | None | None | None | Custom |

## Decision

MCP (Model Context Protocol) as the primary interface for AI agent interactions. REST API as the secondary interface for MT5 synchronization, dashboard frontend, and debugging.

### Why MCP as Primary

**Native AI agent integration.** MCP is the standard protocol for tool use in Claude, Cursor, Windsurf, and a growing list of AI coding environments. When an agent connects to TradeMemory's MCP server, it automatically discovers all 19 tools -- `remember_trade`, `recall_similar_trades`, `get_strategy_performance`, etc. No SDK installation, no API key management, no endpoint discovery.

**Tool discovery eliminates documentation friction.** Each MCP tool carries its own description, parameter schema, and return type. The agent reads these at connection time. Compare this with REST, where the agent needs to know the base URL, read API docs, construct headers, and parse responses. MCP makes the tool self-describing.

**Schema enforcement via FastMCP.** Input validation happens at the protocol layer. If an agent calls `remember_trade` with a missing `symbol` field, FastMCP rejects it before our code runs. This prevents garbage-in problems that plague REST APIs consumed by LLMs (which frequently hallucinate optional fields or malform JSON).

**Ecosystem momentum.** The MCP registry (Smithery) lists 11,000+ servers as of early 2026. Anthropic, OpenAI (via Agents SDK), Google (via ADK), and Microsoft have adopted or announced MCP support. Building on MCP positions TradeMemory in a growing ecosystem rather than a proprietary silo.

### Why REST as Secondary

**MT5 synchronization.** MetaTrader 5 Expert Advisors are written in MQL5, which supports HTTP requests (`WebRequest`) but cannot speak the MCP stdio protocol. The MT5 sync bridge sends closed trade data via REST endpoints.

**Dashboard frontend.** The web dashboard (Next.js) fetches strategy performance, trade history, and agent state via REST. Browsers cannot connect to stdio-based MCP servers.

**Debugging and testing.** `curl` and Postman remain the fastest way to inspect and test individual endpoints during development.

**Non-AI integrations.** Webhook receivers, monitoring scripts, and third-party tools expect HTTP. REST provides a universal fallback.

## Implementation Architecture

```
AI Agents (Claude, Cursor, etc.)
    |
    | MCP (stdio transport)
    v
+-------------------+
| FastMCP Server    |  <-- 19 tools, schema-validated
|   server.py       |
+-------------------+
    |
    | Internal function calls
    v
+-------------------+
| Core Logic        |  <-- owm.py, evolution.py, etc.
|   (shared)        |
+-------------------+
    |
    | Internal function calls
    v
+-------------------+
| Storage Layer     |  <-- db.py (SQLite), database.py (PostgreSQL)
+-------------------+
    ^
    | REST (HTTP)
    |
+-------------------+
| REST Endpoints    |  <-- sync_server.py, dashboard API
+-------------------+
    ^
    |
MT5 EA / Dashboard / curl
```

Both MCP tools and REST endpoints call the same core logic layer. There is no feature divergence -- a trade stored via MCP is queryable via REST and vice versa.

## Consequences

### Positive

- AI agents discover and use tools with zero configuration
- Schema validation prevents malformed inputs at the protocol layer
- Aligned with industry direction (multi-vendor MCP adoption)
- REST fallback ensures non-AI access paths remain functional
- Single core logic layer prevents MCP/REST feature drift

### Negative

- **MCP spec instability.** The protocol is pre-1.0. Breaking changes in transport, auth, or tool schema could require migration work. Mitigated by pinning the `fastmcp` dependency version and abstracting transport details.
- **Single-client stdio limitation.** MCP's stdio transport supports one connected client at a time. If two agents need simultaneous access, they need separate server processes (each with its own SQLite connection). The SSE transport option partially addresses this but is less widely supported.
- **Duplicated surface area.** Some functionality (e.g., `recall_similar_trades`) exists as both an MCP tool and a REST endpoint. This is intentional but increases maintenance burden. Mitigated by sharing the core logic layer.
- **Testing complexity.** MCP tools require an MCP client harness to test end-to-end, whereas REST endpoints can be tested with simple HTTP assertions. Unit tests bypass the MCP layer and test core logic directly; integration tests use FastMCP's test client.

### Future Considerations

- **SSE/WebSocket transport.** When MCP stabilizes a network transport, the single-client limitation disappears and the REST secondary interface may become unnecessary for dashboards.
- **MCP auth.** The protocol's authentication story is still evolving. Currently TradeMemory runs locally (no auth needed). A hosted version would need MCP-level auth or a reverse proxy.
- **Tool count management.** At 19 tools, we are approaching the practical limit of what an AI agent can effectively reason about in a single tool-use turn. Future tools may need to be grouped into sub-servers or gated behind capability flags.

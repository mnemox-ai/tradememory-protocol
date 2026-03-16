# Smithery 上架步驟

> 最後更新：2026-03-16

## 方法 1：Web UI（最簡單）

1. 開瀏覽器到 https://smithery.ai/new
2. 用 GitHub 登入
3. 選擇 repo：`mnemox-ai/tradememory-protocol`
4. Smithery 會自動讀取 `smithery.yaml`，偵測 stdio transport
5. 填寫 server metadata（名稱、描述、icon）
6. 按 Publish

## 方法 2：Smithery CLI

### 安裝 CLI

```bash
npm install -g @anthropic/smithery-cli
# 或
npx @anthropic/smithery-cli
```

### 登入

```bash
smithery login
# 用 GitHub OAuth 或 API key 登入
# API Key: 9e8fbb37-1374-444a-a771-0b6b20084da3
```

### 發布（stdio transport）

```bash
cd C:/Users/johns/projects/tradememory-protocol

# 方法 A：從本地 repo 發布
smithery mcp publish --name @mnemox-ai/tradememory-protocol --transport stdio

# 方法 B：如果 CLI 支援 --api-key
smithery mcp publish --name @mnemox-ai/tradememory-protocol --transport stdio --api-key 9e8fbb37-1374-444a-a771-0b6b20084da3
```

### 驗證上架

```bash
smithery mcp search tradememory
```

## 方法 3：API 直接呼叫

```bash
# 如果 CLI 有問題，可以用 REST API
# 參考 https://smithery.ai/docs/api-reference/servers/publish-a-server
curl -X POST https://registry.smithery.ai/servers \
  -H "Authorization: Bearer 9e8fbb37-1374-444a-a771-0b6b20084da3" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "@mnemox-ai/tradememory-protocol",
    "description": "MCP memory for AI trading agents. Store trades, recall similar setups, track strategy performance.",
    "repository": "https://github.com/mnemox-ai/tradememory-protocol",
    "transport": "stdio"
  }'
```

## 已完成的準備

- [x] `smithery.yaml` — 已建立（stdio transport, 可選 dbUrl 配置）
- [x] `server.json` — MCP metadata（已存在）
- [x] `Dockerfile` — 已存在（container fallback）
- [x] `pyproject.toml` — 包含 `tradememory-protocol` 入口點
- [x] GitHub repo public — `mnemox-ai/tradememory-protocol`

## 配置說明

`smithery.yaml` 定義了：
- **Transport**: stdio（標準 MCP transport）
- **Command**: `tradememory-protocol`（pip install 後的 CLI 指令）
- **可選配置**: `dbUrl` — 使用者可以設定 PostgreSQL 連線，預設用 SQLite

## 注意事項

1. Smithery 有兩種 runtime：`typescript` 和 `container`。我們用的是 `stdio` startCommand，Smithery 會用 mcpb 打包
2. 使用者安裝時需要先 `pip install tradememory-protocol`，Smithery 會在頁面顯示安裝指令
3. 如果 Smithery CLI 指令格式有變，查最新文檔：https://smithery.ai/docs/build/publish
4. 上架後可在 https://smithery.ai/server/@mnemox-ai/tradememory-protocol 查看頁面

---

# mcp.so 上架步驟

> 最後更新：2026-03-16

## 提交方式

### 方法 1：Web UI（推薦）

1. 開瀏覽器到 https://mcp.so/submit
2. 填寫表單：
   - **MCP Name**: TradeMemory Protocol
   - **Type**: Server
   - **GitHub URL**: https://github.com/mnemox-ai/tradememory-protocol
   - **Description**: MCP memory layer for AI trading agents. 5-type outcome-weighted memory, evolution engine, MT5/Binance integration.
3. 提交

### 方法 2：GitHub Issue

1. 到 https://github.com/chatmcp/mcpso/issues
2. 建立新 Issue，附上 server 資訊（name, GitHub URL, description）

### 方法 3：Email

- 寄到 support@mcp.so

## 狀態

- [ ] 待提交（Sean 手動操作）

---

# awesome-mcp-servers PR

> 最後更新：2026-03-16

## 狀態

- [x] Fork: `zychenpeng/awesome-mcp-servers`（parent: `punkpeye/awesome-mcp-servers`）
- [x] TradeMemory 已在 Finance & Fintech section（之前的 PR 已 merge）
- [x] 更新描述到 v0.5.0：5-type OWM + evolution engine
- [x] PR: https://github.com/punkpeye/awesome-mcp-servers/pull/3302

## 描述更新

- **舊**: Structured 3-layer memory system (trades → patterns → strategy) for AI trading agents. Supports MT5, Binance, and Alpaca.
- **新**: MCP memory layer for AI trading agents. 5-type outcome-weighted memory, evolution engine, MT5/Binance integration.

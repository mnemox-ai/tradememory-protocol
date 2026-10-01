# Put a brake in front of Alpaca in 30 minutes

Your agent already trades through Alpaca's official MCP server. This recipe
puts TradeMemory between the two: every order is evaluated against a policy
you own before it reaches Alpaca, every decision is recorded and chained, and
the memory fills itself from the orders that pass. Nothing about your agent
changes except one line of its MCP config.

Everything below was run against a real Alpaca paper account on 2026-10-01;
the outputs are from that run, shortened.

## 0. What you need

- Python 3.12 or newer, and `uv` (for `uvx`, which starts Alpaca's server).
- An Alpaca account. Paper trading needs only an email: sign up at
  <https://app.alpaca.markets/signup>, switch to the **Paper** account (top
  left), and generate an API key pair on the paper overview page. The secret
  is shown once.
- Put the pair in a file the proxy will hand to Alpaca's process and never
  store itself:

```text
# ~/.secrets/alpaca-paper.env
ALPACA_API_KEY=PK...
ALPACA_SECRET_KEY=...
```

## 1. Install

```bash
# until the next release ships the extra:
pip install "tradememory-protocol[proxy] @ git+https://github.com/mnemox-ai/tradememory-protocol@feat/broker-proxy"
```

## 2. Find your account id and write a policy

The policy binds to the account's `id` (a UUID), not the `PA...` account
number. `doctor` prints both the live id and whatever the policy says:

```bash
tradememory proxy init --account-id placeholder --symbols AAPL,MSFT
tradememory proxy doctor --env-file ~/.secrets/alpaca-paper.env
# upstream tools: 72; missing required: none
# upstream account id: e3a0b99f-...; policy account id: placeholder; MISMATCH (every order would be refused)
tradememory proxy init --account-id e3a0b99f-... --symbols AAPL,MSFT
tradememory proxy doctor --env-file ~/.secrets/alpaca-paper.env
# ... MATCH
```

The default policy is deliberately tight. Open `~/.tradememory/policy.json`
if you want to change it, then `tradememory proxy seal ~/.tradememory/policy.json`
so the hash matches again. Defaults:

| Field | Default | Meaning |
|---|---|---|
| `allowed_symbols` | what you passed | anything else is refused |
| `max_order_notional` | 1000 | per order, in account currency |
| `max_position_notional` | 5000 | per symbol, counting what you already hold and what is still resting |
| `max_daily_loss` | 200 | once equity is down this much since the last close, no new entries |
| `max_drawdown` | 1000 | same, from the running equity peak |
| `approval_notional` | 1000 | orders at or above this wait for `tradememory proxy approve` |
| `require_protective_stop` | true | entries must be bracket orders with `stop_loss_stop_price`, 10 to 500 bps away |
| `allowed_weekly_windows` | all week | tighten to your session if you like |
| `expires_at` | 30 days | a policy that never expires is a policy nobody re-reads |

## 3. Point the agent at the brake

`tradememory proxy config` prints the entry. For Claude Desktop replace the
direct `alpaca` server with it:

```json
{
  "mcpServers": {
    "alpaca-with-brake": {
      "command": "tradememory",
      "args": ["proxy", "run", "--policy", "/home/you/.tradememory/policy.json",
               "--env-file", "/home/you/.secrets/alpaca-paper.env"]
    }
  }
}
```

Claude Code: `claude mcp add alpaca-with-brake -- tradememory proxy run --policy ... --env-file ...`.
OpenClaw: install the `tradememory` skill and use the same command as the server.

The agent sees Alpaca's 72 tools exactly as before, plus `recall_memories`,
`get_behavioral_analysis`, `get_agent_state` and `brake_status`.

## 4. What the first orders look like

Ask the agent for an order outside the list:

```text
place_stock_order(symbol="TSLA", side="buy", qty="1", type="market", order_class="bracket",
                  take_profit_limit_price="300", stop_loss_stop_price="240", client_order_id="t-1")
→ {"decision": "DENY", "order_placed": false,
   "denied_rules": [{"code": "SYMBOL_NOT_ALLOWED", "actual": "TSLA", ...}],
   "decision_event": "de-58e8...", "policy_hash": "2830d1bb...", "evaluation_hash": "..."}
```

An entry without a stop:

```text
place_stock_order(symbol="AAPL", side="buy", qty="1", type="market", client_order_id="t-2")
→ {"decision": "DENY", "denied_rules": [{"code": "PROTECTIVE_STOP_REQUIRED", ...}], ...}
```

Too big:

```text
place_stock_order(symbol="AAPL", side="buy", qty="5", ... stop_loss_stop_price="325", client_order_id="t-3")
→ {"decision": "DENY", "denied_rules": [{"code": "ORDER_NOTIONAL_EXCEEDED", "actual": "1665.25", "limit": "1000"}, ...]}
```

Inside the policy:

```text
place_stock_order(symbol="AAPL", side="buy", qty="1", type="market", order_class="bracket",
                  take_profit_limit_price="350", stop_loss_stop_price="325", client_order_id="t-4")
→ {"decision": "ALLOW", "order_placed": true, "intent_id": "...", "decision_event": "de-bfd5...",
   "prior_outcomes": [], "upstream": {"_alpaca_mcp_security": {...}, "data": {"id": "1f501cc3-...", "status": "pending_new", ...}}}
```

The same call again, for example after a timeout, is answered from the record
and places nothing:

```text
→ {"decision": "ALLOW", "replayed": true, "order_placed": true, "upstream": {... "id": "1f501cc3-..." ...}}
```

Always pass a `client_order_id`. Without one, every call is a new order and an
ESCALATE cannot be approved and retried.

## 5. Approvals, halts, exits

- An order at or above `approval_notional` returns `ESCALATE` with the
  intent id. Run `tradememory proxy approve <intent_id>`; the agent retries
  with the same `client_order_id` and the same terms, and the brake forwards
  it once. An approval is bound to the terms that escalated: change the
  symbol, side, size or price and it does not apply. Approvals expire after
  15 minutes.
- `tradememory proxy halt FULL_HALT` refuses every new order until you run
  `tradememory proxy halt NORMAL`. `REDUCE_ONLY` lets through only orders that
  shrink a position. The running proxy reads the state file on every order,
  so the halt takes effect immediately.
- `close_position` and `close_all_positions` are never blocked, in any state.
  They are recorded.
- `cancel_order_by_id` and `cancel_all_orders` are forwarded and recorded,
  except that while the policy requires stops, cancelling the stop leg of an
  open position is refused, and `cancel_all_orders` is refused while any
  position is open.
- If the broker call fails after the brake said ALLOW, the response says
  `order_placed: "unknown"`. Retry with the same `client_order_id`: the brake
  asks the broker whether it has that order before placing anything.

## 6. Where the evidence lives

Every decision is a row in `decision_events` in the TradeMemory database and
a link in its hash chain. The agent (or you) can verify it:

```text
verify_audit_chain()
→ {"verified": true, "checked_count": 6, "first_break_at": null}
```

Set `TRADEMEMORY_DB=~/.tradememory/alpaca-paper.db` before `proxy run` if you
want these records in their own file.

## 7. What it refuses rather than evaluates

Options, order replacement, stop-limit and trailing orders, any symbol the
broker does not know, any order while a quote cannot be obtained. While the
US market is closed the brake prices from the last trade, because the
after-hours book is stale and wide (AAPL showed 320.91 / 354.20 against a last
trade of 333.05 the night this was written).

## Something did not work?

Open a [brake-integration issue](https://github.com/mnemox-ai/tradememory-protocol/issues/new?template=brake_integration.yml)
with your broker, runtime and what the brake should refuse. The first ten
setups get hands-on help.

"""
TradeMemory Hosted API Server (MVP).

Multi-tenant FastAPI server with API key authentication and SQLite storage.
Implements core endpoints from docs/hosted-api-spec.md:
  - POST /api/v1/trades       (store_trade)
  - GET  /api/v1/trades       (recall_trades)
  - GET  /api/v1/performance  (get_performance)
  - GET  /api/v1/health       (no auth)

API keys: Bearer tm_live_* / tm_test_*
Storage: SQLite (PostgreSQL migration planned)
"""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Header, Query
from pydantic import BaseModel, Field


# ========== Configuration ==========

DB_PATH = os.environ.get("TM_HOSTED_DB", "hosted/hosted.db")

app = FastAPI(
    title="TradeMemory Hosted API",
    description="Multi-tenant AI Trading Memory API",
    version="0.3.0",
)


# ========== Database ==========


class HostedDB:
    """SQLite storage for hosted API. Scoped by account_id."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        conn = self._conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    key TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    plan TEXT NOT NULL DEFAULT 'free',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_keys_account
                ON api_keys(account_id)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    strategy TEXT NOT NULL,
                    market_context TEXT NOT NULL,
                    exit_price REAL,
                    pnl REAL,
                    reflection TEXT,
                    PRIMARY KEY (id, account_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_account
                ON trades(account_id, timestamp DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trades_strategy
                ON trades(account_id, strategy)
            """)

            # Seed API keys from env if provided (comma-separated key:account:plan)
            seed = os.environ.get("TM_API_KEYS", "")
            if seed:
                for entry in seed.split(","):
                    entry = entry.strip()
                    if not entry:
                        continue
                    parts = entry.split(":")
                    key = parts[0]
                    account_id = parts[1] if len(parts) > 1 else "default"
                    plan = parts[2] if len(parts) > 2 else "free"
                    conn.execute(
                        "INSERT OR IGNORE INTO api_keys VALUES (?, ?, ?, ?)",
                        (key, account_id, plan, datetime.now(timezone.utc).isoformat()),
                    )
                conn.commit()

            conn.commit()
        finally:
            conn.close()

    def validate_key(self, api_key: str) -> Optional[Dict[str, str]]:
        """Validate API key, return account info or None."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM api_keys WHERE key = ?", (api_key,)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def insert_trade(self, account_id: str, trade: Dict[str, Any]) -> bool:
        conn = self._conn()
        try:
            conn.execute(
                """INSERT INTO trades
                   (id, account_id, timestamp, symbol, direction, entry_price,
                    strategy, market_context, exit_price, pnl, reflection)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade["id"],
                    account_id,
                    trade["timestamp"],
                    trade["symbol"],
                    trade["direction"],
                    trade["entry_price"],
                    trade["strategy"],
                    trade["market_context"],
                    trade.get("exit_price"),
                    trade.get("pnl"),
                    trade.get("reflection"),
                ),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            raise HTTPException(
                status_code=409,
                detail={"error": "conflict", "message": f"Trade '{trade['id']}' already exists"},
            )
        finally:
            conn.close()

    def query_trades(
        self,
        account_id: str,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Query trades for an account. Returns (trades, total_count)."""
        conn = self._conn()
        try:
            where = "WHERE account_id = ?"
            params: list[Any] = [account_id]

            if symbol:
                where += " AND symbol = ?"
                params.append(symbol.upper())
            if strategy:
                where += " AND strategy = ?"
                params.append(strategy)

            total = conn.execute(
                f"SELECT COUNT(*) FROM trades {where}", params
            ).fetchone()[0]

            rows = conn.execute(
                f"SELECT * FROM trades {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()

            trades = []
            for row in rows:
                t = dict(row)
                del t["account_id"]
                trades.append(t)

            return trades, total
        finally:
            conn.close()

    def get_performance(
        self,
        account_id: str,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate performance stats for closed trades (pnl IS NOT NULL)."""
        conn = self._conn()
        try:
            where = "WHERE account_id = ? AND pnl IS NOT NULL"
            params: list[Any] = [account_id]

            if symbol:
                where += " AND symbol = ?"
                params.append(symbol.upper())
            if strategy:
                where += " AND strategy = ?"
                params.append(strategy)

            rows = conn.execute(
                f"SELECT * FROM trades {where} ORDER BY timestamp DESC",
                params,
            ).fetchall()

            closed = [dict(r) for r in rows]
            if not closed:
                return {
                    "symbol": symbol or "all",
                    "total_closed_trades": 0,
                    "strategies": {},
                }

            by_strat: Dict[str, list] = {}
            for t in closed:
                by_strat.setdefault(t["strategy"], []).append(t)

            strategies = {}
            for strat, trades in by_strat.items():
                pnls = [t["pnl"] for t in trades]
                winners = [p for p in pnls if p > 0]
                losers = [p for p in pnls if p <= 0]
                total_pnl = sum(pnls)

                best = max(trades, key=lambda t: t["pnl"])
                worst = min(trades, key=lambda t: t["pnl"])

                strategies[strat] = {
                    "trade_count": len(trades),
                    "win_rate": round(len(winners) / len(trades) * 100, 1),
                    "total_pnl": round(total_pnl, 2),
                    "avg_pnl": round(total_pnl / len(trades), 2),
                    "avg_winner": round(sum(winners) / len(winners), 2) if winners else 0,
                    "avg_loser": round(sum(losers) / len(losers), 2) if losers else 0,
                    "profit_factor": (
                        round(sum(winners) / abs(sum(losers)), 2)
                        if losers and sum(losers) != 0
                        else float("inf")
                    ),
                    "best_trade": {"id": best["id"], "pnl": best["pnl"]},
                    "worst_trade": {"id": worst["id"], "pnl": worst["pnl"]},
                }

            return {
                "symbol": symbol or "all",
                "total_closed_trades": len(closed),
                "strategies": strategies,
            }
        finally:
            conn.close()

    def create_api_key(self, account_id: str, plan: str = "free") -> str:
        """Create a new API key for an account."""
        key = f"tm_live_{uuid.uuid4().hex}"
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO api_keys VALUES (?, ?, ?, ?)",
                (key, account_id, plan, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            return key
        finally:
            conn.close()


# Singleton DB — initialized on first use
_db: Optional[HostedDB] = None


def get_db() -> HostedDB:
    global _db
    if _db is None:
        _db = HostedDB(DB_PATH)
    return _db


# ========== Auth Dependency ==========


def require_auth(
    authorization: Optional[str] = Header(None),
    db: HostedDB = Depends(get_db),
) -> Dict[str, str]:
    """Validate Bearer token and return account info."""
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "Missing Authorization header"},
        )

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "Invalid Authorization format. Use: Bearer <api_key>"},
        )

    api_key = parts[1].strip()
    if not api_key.startswith(("tm_live_", "tm_test_")):
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "Invalid API key format"},
        )

    account = db.validate_key(api_key)
    if not account:
        raise HTTPException(
            status_code=401,
            detail={"error": "unauthorized", "message": "Invalid API key"},
        )

    return account


# ========== Request/Response Models ==========


class StoreTradeRequest(BaseModel):
    symbol: str
    direction: str
    entry_price: float
    strategy_name: str
    market_context: str
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    reflection: Optional[str] = None
    trade_id: Optional[str] = None
    timestamp: Optional[str] = None


class StoreTradeResponse(BaseModel):
    memory_id: str
    symbol: str
    direction: str
    strategy: str
    stored_at: str
    has_outcome: bool
    status: str = "stored"
    credits_used: int = 1


class RecallTradesResponse(BaseModel):
    trades: List[Dict[str, Any]]
    count: int
    total: int
    limit: int
    offset: int


# ========== Endpoints ==========


@app.get("/api/v1/health")
async def health():
    """Health check — no auth required."""
    return {"status": "healthy", "version": "0.3.0"}


@app.post("/api/v1/trades", status_code=201, response_model=StoreTradeResponse)
async def store_trade(
    req: StoreTradeRequest,
    account: Dict = Depends(require_auth),
    db: HostedDB = Depends(get_db),
):
    """Store a trade decision with full context."""
    direction = req.direction.lower()
    if direction not in ("long", "short"):
        raise HTTPException(
            status_code=422,
            detail={"error": "validation_error", "message": "direction must be 'long' or 'short'"},
        )

    trade_id = req.trade_id or f"tm-{uuid.uuid4().hex[:12]}"
    ts = req.timestamp or datetime.now(timezone.utc).isoformat()

    trade_data = {
        "id": trade_id,
        "timestamp": ts,
        "symbol": req.symbol.upper(),
        "direction": direction,
        "entry_price": req.entry_price,
        "strategy": req.strategy_name,
        "market_context": req.market_context,
        "exit_price": req.exit_price,
        "pnl": req.pnl,
        "reflection": req.reflection,
    }

    db.insert_trade(account["account_id"], trade_data)

    return StoreTradeResponse(
        memory_id=trade_id,
        symbol=req.symbol.upper(),
        direction=direction,
        strategy=req.strategy_name,
        stored_at=ts,
        has_outcome=req.exit_price is not None,
    )


@app.get("/api/v1/trades")
async def recall_trades(
    symbol: Optional[str] = Query(None),
    strategy: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    account: Dict = Depends(require_auth),
    db: HostedDB = Depends(get_db),
):
    """Query past trades with filters."""
    trades, total = db.query_trades(
        account_id=account["account_id"],
        symbol=symbol,
        strategy=strategy,
        limit=limit,
        offset=offset,
    )
    return {
        "trades": trades,
        "count": len(trades),
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/v1/performance")
async def get_performance(
    symbol: Optional[str] = Query(None),
    strategy: Optional[str] = Query(None),
    account: Dict = Depends(require_auth),
    db: HostedDB = Depends(get_db),
):
    """Aggregate performance stats per strategy."""
    return db.get_performance(
        account_id=account["account_id"],
        symbol=symbol,
        strategy=strategy,
    )


# ========== Entry Point ==========


def main():
    """Run hosted API server."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()

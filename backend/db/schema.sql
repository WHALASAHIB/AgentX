-- AGENTX Platform — PostgreSQL Schema
-- Migration V1: core tables

-- ── MT5 Accounts ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accounts (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL DEFAULT 'Default Account',
    login           BIGINT NOT NULL,
    password_encrypted TEXT NOT NULL DEFAULT '',
    server          TEXT NOT NULL DEFAULT '',
    terminal_path   TEXT NOT NULL DEFAULT 'C:\Program Files\MetaTrader 5\terminal64.exe',
    symbols         TEXT[] NOT NULL DEFAULT ARRAY['XAUUSD', 'EURUSD'],
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Trades (synced from MT5 deal history) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS trades (
    id              SERIAL PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    position_id     BIGINT NOT NULL,
    symbol          TEXT NOT NULL,
    type            TEXT NOT NULL CHECK (type IN ('BUY', 'SELL')),
    volume          NUMERIC(10,2) NOT NULL,
    entry_price     NUMERIC(12,5) NOT NULL,
    exit_price      NUMERIC(12,5),
    open_time       TIMESTAMPTZ NOT NULL,
    close_time      TIMESTAMPTZ,
    profit          NUMERIC(12,2) NOT NULL DEFAULT 0,
    swap            NUMERIC(12,2) NOT NULL DEFAULT 0,
    commission      NUMERIC(12,2) NOT NULL DEFAULT 0,
    net_profit      NUMERIC(12,2) NOT NULL DEFAULT 0,
    duration        TEXT NOT NULL DEFAULT '',
    magic           BIGINT NOT NULL DEFAULT 0,
    comment         TEXT NOT NULL DEFAULT '',
    tags            TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    notes           TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(account_id, position_id)
);

CREATE INDEX IF NOT EXISTS idx_trades_account_id ON trades(account_id);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_open_time ON trades(open_time DESC);

-- ── Positions Snapshot (last-known state per account) ────────────────────────
CREATE TABLE IF NOT EXISTS positions (
    id              SERIAL PRIMARY KEY,
    account_id      TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    ticket          BIGINT NOT NULL,
    symbol          TEXT NOT NULL,
    type            TEXT NOT NULL CHECK (type IN ('BUY', 'SELL')),
    volume          NUMERIC(10,2) NOT NULL,
    open_price      NUMERIC(12,5) NOT NULL,
    current_price   NUMERIC(12,5) NOT NULL,
    sl              NUMERIC(12,5) NOT NULL DEFAULT 0,
    tp              NUMERIC(12,5) NOT NULL DEFAULT 0,
    swap            NUMERIC(12,2) NOT NULL DEFAULT 0,
    profit          NUMERIC(12,2) NOT NULL DEFAULT 0,
    open_time       TIMESTAMPTZ NOT NULL,
    duration        TEXT NOT NULL DEFAULT '',
    magic           BIGINT NOT NULL DEFAULT 0,
    comment         TEXT NOT NULL DEFAULT '',
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(account_id, ticket)
);

CREATE INDEX IF NOT EXISTS idx_positions_account_id ON positions(account_id);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);

-- ── Bots ─────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bots (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    display_name    TEXT NOT NULL,
    script_path     TEXT NOT NULL,
    strategy        TEXT NOT NULL DEFAULT '',
    symbol          TEXT NOT NULL DEFAULT 'XAUUSD',
    account_id      TEXT REFERENCES accounts(id),
    status          TEXT NOT NULL DEFAULT 'stopped'
                        CHECK (status IN ('running', 'stopped', 'error', 'restarting')),
    config          JSONB NOT NULL DEFAULT '{}',
    pid             INTEGER,
    uptime_seconds  BIGINT NOT NULL DEFAULT 0,
    last_started    TIMESTAMPTZ,
    last_stopped    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Bot Logs ─────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bot_logs (
    id              BIGSERIAL PRIMARY KEY,
    bot_id          INTEGER NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
    level           TEXT NOT NULL DEFAULT 'INFO',
    message         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bot_logs_bot_id ON bot_logs(bot_id);
CREATE INDEX IF NOT EXISTS idx_bot_logs_created_at ON bot_logs(created_at DESC);

-- ── Agent Decisions ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_logs (
    id              BIGSERIAL PRIMARY KEY,
    agent_name      TEXT NOT NULL,
    task            TEXT NOT NULL DEFAULT '',
    decision        TEXT NOT NULL DEFAULT '',
    outcome         TEXT NOT NULL DEFAULT '',
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_logs_agent_name ON agent_logs(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_logs_created_at ON agent_logs(created_at DESC);

-- ── System Events ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS system_events (
    id              BIGSERIAL PRIMARY KEY,
    event_type      TEXT NOT NULL,
    severity        TEXT NOT NULL DEFAULT 'info'
                        CHECK (severity IN ('info', 'warning', 'error', 'critical')),
    message         TEXT NOT NULL,
    metadata        JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_system_events_type ON system_events(event_type);
CREATE INDEX IF NOT EXISTS idx_system_events_created_at ON system_events(created_at DESC);

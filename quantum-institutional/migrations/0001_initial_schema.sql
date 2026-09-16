-- Quantum Institutional -- initial schema. Master prompt sections 43 and 44.
--
-- DESIGN RULES ENCODED HERE
--
-- 1. Every analytical row carries the versions that produced it
--    (engine/formula/model/data + git commit), so any number on the dashboard
--    can be re-derived. Section 44.
-- 2. Every record that can be revised stores event_time, publication_time and
--    received_time separately. Point-in-time queries filter on
--    publication_time and nothing else. Sections 70-72.
-- 3. Volume carries its TYPE. Broker tick counts and exchange contracts are
--    never summed into one column. Section 7.
-- 4. Source is part of the identity of a price row, not metadata. Two feeds
--    for XAUUSD are two rows to reconcile, not a last-write-wins collision.
--    Section 69.
--
-- Timestamps are timestamptz throughout. A naive timestamp column is how a
-- session boundary ends up off by the server's local offset.

BEGIN;

CREATE TABLE schema_version (
    version      TEXT PRIMARY KEY,
    applied_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- reference
CREATE TABLE data_sources (
    source_id    TEXT PRIMARY KEY,
    kind         TEXT NOT NULL CHECK (kind IN ('market','macro','news','calendar','futures','sentiment')),
    description  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE instruments (
    symbol          TEXT PRIMARY KEY,
    asset_class     TEXT NOT NULL,
    quote_currency  TEXT NOT NULL DEFAULT 'USD',
    exchange        TEXT,
    description     TEXT
);

-- Section 14: the mathematical source of truth. One row per formula version.
CREATE TABLE formula_registry (
    formula_id       TEXT NOT NULL,
    version          TEXT NOT NULL,
    name             TEXT NOT NULL,
    description      TEXT NOT NULL,
    expression       TEXT NOT NULL,
    source_variables TEXT[] NOT NULL,
    output_variable  TEXT NOT NULL,
    units            TEXT,
    timeframe        TEXT,
    lookback         INTEGER,
    assumptions      TEXT,
    implementation   TEXT NOT NULL,
    pine_reference   TEXT,
    test_status      TEXT NOT NULL DEFAULT 'NOT RUN'
                     CHECK (test_status IN ('NOT RUN','PASS','FAIL','PARITY_PENDING')),
    PRIMARY KEY (formula_id, version)
);

CREATE TABLE engine_versions (
    engine_version           TEXT PRIMARY KEY,
    formula_registry_version TEXT NOT NULL,
    git_commit               TEXT,
    released_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes                    TEXT
);

-- -------------------------------------------------------------- market data
CREATE TABLE market_bars (
    symbol       TEXT NOT NULL REFERENCES instruments(symbol),
    timeframe    TEXT NOT NULL,
    event_time   TIMESTAMPTZ NOT NULL,          -- bar OPEN, left-aligned, UTC
    source_id    TEXT NOT NULL REFERENCES data_sources(source_id),
    open         DOUBLE PRECISION NOT NULL,
    high         DOUBLE PRECISION NOT NULL,
    low          DOUBLE PRECISION NOT NULL,
    close        DOUBLE PRECISION NOT NULL,
    volume       DOUBLE PRECISION,              -- NULL means absent, not zero
    volume_type  TEXT NOT NULL CHECK (volume_type IN ('TICK','EXCHANGE','FUTURES','OTC_ESTIMATE','NONE')),
    quality      TEXT NOT NULL DEFAULT 'OK' CHECK (quality IN ('OK','DEGRADED','STALE','INVALID','OFFLINE')),
    received_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    data_version TEXT NOT NULL,
    -- source is in the key: two feeds are two rows to reconcile (section 69).
    PRIMARY KEY (symbol, timeframe, event_time, source_id),
    CONSTRAINT ohlc_consistent CHECK (
        high >= GREATEST(open, close) AND low <= LEAST(open, close) AND high >= low
    ),
    CONSTRAINT volume_non_negative CHECK (volume IS NULL OR volume >= 0)
);
CREATE INDEX market_bars_lookup ON market_bars (symbol, timeframe, event_time DESC);

CREATE TABLE market_quotes (
    symbol        TEXT NOT NULL REFERENCES instruments(symbol),
    event_time    TIMESTAMPTZ NOT NULL,
    source_id     TEXT NOT NULL REFERENCES data_sources(source_id),
    bid           DOUBLE PRECISION NOT NULL,
    ask           DOUBLE PRECISION NOT NULL,
    received_time TIMESTAMPTZ NOT NULL,
    quality       TEXT NOT NULL DEFAULT 'OK',
    PRIMARY KEY (symbol, event_time, source_id),
    CONSTRAINT spread_non_negative CHECK (ask >= bid)
);

CREATE TABLE data_quality (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    checked_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    symbol       TEXT,
    timeframe    TEXT,
    source_id    TEXT,
    check_name   TEXT NOT NULL,
    issue_count  INTEGER NOT NULL,
    detail       TEXT,
    quality      TEXT NOT NULL
);

-- ---------------------------------------------------------- macro and news
-- publication_time is the ONLY column a point-in-time query may filter on.
CREATE TABLE macro_values (
    series_id        TEXT NOT NULL,
    event_time       TIMESTAMPTZ NOT NULL,      -- reference period
    publication_time TIMESTAMPTZ NOT NULL,      -- when it became public
    received_time    TIMESTAMPTZ NOT NULL,
    source_id        TEXT NOT NULL REFERENCES data_sources(source_id),
    value            DOUBLE PRECISION NOT NULL,
    revision_of      TEXT,                      -- NULL for a first release
    quality          TEXT NOT NULL DEFAULT 'OK',
    -- publication_time in the key: a revision is a NEW row, never an update.
    -- Overwriting in place silently improves every historical backtest.
    PRIMARY KEY (series_id, event_time, publication_time, source_id)
);
CREATE INDEX macro_values_pit ON macro_values (series_id, publication_time DESC);

CREATE TABLE macro_events (
    event_id         TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    scheduled_time   TIMESTAMPTZ NOT NULL,
    publication_time TIMESTAMPTZ,
    importance       TEXT,
    category         TEXT,
    source_id        TEXT REFERENCES data_sources(source_id)
);

CREATE TABLE news (
    news_id          TEXT PRIMARY KEY,
    headline         TEXT NOT NULL,
    publication_time TIMESTAMPTZ NOT NULL,
    received_time    TIMESTAMPTZ NOT NULL,
    source_id        TEXT NOT NULL REFERENCES data_sources(source_id),
    event_category   TEXT,
    importance       TEXT,
    sentiment        DOUBLE PRECISION,          -- NULL = unscored, not neutral
    entities         TEXT[],
    reference_url    TEXT,
    quality          TEXT NOT NULL DEFAULT 'OK'
);
CREATE INDEX news_pit ON news (publication_time DESC);

-- -------------------------------------------------------- derived analytics
CREATE TABLE features (
    feature_id       TEXT NOT NULL,
    symbol           TEXT NOT NULL REFERENCES instruments(symbol),
    timeframe        TEXT NOT NULL,
    event_time       TIMESTAMPTZ NOT NULL,
    -- When the inputs to this feature became available. Never earlier than the
    -- publication_time of any input. Section 30.
    availability_time TIMESTAMPTZ NOT NULL,
    value            DOUBLE PRECISION,
    quality          TEXT NOT NULL DEFAULT 'OK',
    formula_version  TEXT NOT NULL,
    engine_version   TEXT NOT NULL,
    data_version     TEXT NOT NULL,
    git_commit       TEXT,
    PRIMARY KEY (feature_id, symbol, timeframe, event_time, formula_version),
    CONSTRAINT availability_not_before_event CHECK (availability_time >= event_time)
);

CREATE TABLE smc_events (
    id             TEXT PRIMARY KEY,
    symbol         TEXT NOT NULL REFERENCES instruments(symbol),
    timeframe      TEXT NOT NULL,
    event_time     TIMESTAMPTZ NOT NULL,
    event_type     TEXT NOT NULL,   -- BOS | CHOCH | MSS | SWEEP | FVG | OB | ...
    direction      TEXT,
    price_level    DOUBLE PRECISION,
    detail         JSONB,
    formula_version TEXT NOT NULL,
    engine_version TEXT NOT NULL
);

CREATE TABLE regimes (
    symbol         TEXT NOT NULL REFERENCES instruments(symbol),
    timeframe      TEXT NOT NULL,
    event_time     TIMESTAMPTZ NOT NULL,
    regime         TEXT NOT NULL,
    composite_raw  DOUBLE PRECISION,  -- UNROUNDED. See F-021 / F-A17.
    detail         JSONB,
    engine_version TEXT NOT NULL,
    PRIMARY KEY (symbol, timeframe, event_time, engine_version)
);

CREATE TABLE models (
    model_version  TEXT PRIMARY KEY,
    family         TEXT NOT NULL,
    target         TEXT NOT NULL,
    horizon        TEXT NOT NULL,
    feature_set    TEXT[] NOT NULL,
    hyperparameters JSONB,
    train_start    TIMESTAMPTZ,
    train_end      TIMESTAMPTZ,
    validate_start TIMESTAMPTZ,
    validate_end   TIMESTAMPTZ,
    test_start     TIMESTAMPTZ,
    test_end       TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    git_commit     TEXT
);

CREATE TABLE model_runs (
    run_id         TEXT PRIMARY KEY,
    model_version  TEXT NOT NULL REFERENCES models(model_version),
    run_kind       TEXT NOT NULL CHECK (run_kind IN ('TRAIN','VALIDATE','CALIBRATE','TEST','WALKFORWARD')),
    started_at     TIMESTAMPTZ NOT NULL,
    finished_at    TIMESTAMPTZ,
    metrics        JSONB,
    data_version   TEXT NOT NULL,
    git_commit     TEXT
);

CREATE TABLE probabilities (
    signal_id            TEXT NOT NULL,
    event_time           TIMESTAMPTZ NOT NULL,
    p_win                DOUBLE PRECISION,
    p_win_lower          DOUBLE PRECISION,
    p_win_upper          DOUBLE PRECISION,
    horizon              TEXT NOT NULL,
    model_version        TEXT REFERENCES models(model_version),
    calibration_version  TEXT,
    sample_n             INTEGER,
    effective_n          DOUBLE PRECISION,
    unavailable_reason   TEXT,   -- set when p_win IS NULL; section 78
    PRIMARY KEY (signal_id, horizon),
    CONSTRAINT probability_or_reason CHECK (p_win IS NOT NULL OR unavailable_reason IS NOT NULL),
    CONSTRAINT probability_in_range CHECK (p_win IS NULL OR (p_win >= 0 AND p_win <= 1))
);

CREATE TABLE signals (
    signal_id        TEXT PRIMARY KEY,
    event_time       TIMESTAMPTZ NOT NULL,
    symbol           TEXT NOT NULL REFERENCES instruments(symbol),
    timeframe        TEXT NOT NULL,
    direction        TEXT NOT NULL CHECK (direction IN ('LONG','SHORT','FLAT')),
    entry            DOUBLE PRECISION,
    stop             DOUBLE PRECISION,
    target           DOUBLE PRECISION,
    expected_value   DOUBLE PRECISION,
    risk_fraction    DOUBLE PRECISION,
    regime           TEXT,
    session          TEXT,
    strategy         TEXT NOT NULL,
    reason_codes     TEXT[],
    data_quality     TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('VALID','DEGRADED','INVALID','STALE','OFFLINE')),
    model_version    TEXT,
    formula_version  TEXT NOT NULL,
    engine_version   TEXT NOT NULL,
    data_version     TEXT NOT NULL,
    git_commit       TEXT
);
CREATE INDEX signals_lookup ON signals (symbol, timeframe, event_time DESC);

CREATE TABLE backtests (
    backtest_id    TEXT PRIMARY KEY,
    strategy       TEXT NOT NULL,
    period_start   TIMESTAMPTZ NOT NULL,
    period_end     TIMESTAMPTZ NOT NULL,
    is_out_of_sample BOOLEAN NOT NULL,
    cost_model     JSONB NOT NULL,   -- section 34: assumptions are never hidden
    metrics        JSONB,
    engine_version TEXT NOT NULL,
    data_version   TEXT NOT NULL,
    git_commit     TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE trades (
    trade_id       TEXT PRIMARY KEY,
    backtest_id    TEXT REFERENCES backtests(backtest_id),
    signal_id      TEXT REFERENCES signals(signal_id),
    mode           TEXT NOT NULL CHECK (mode IN ('PAPER','LIVE','BACKTEST')),
    opened_at      TIMESTAMPTZ NOT NULL,
    closed_at      TIMESTAMPTZ,
    direction      TEXT NOT NULL,
    entry_price    DOUBLE PRECISION NOT NULL,
    exit_price     DOUBLE PRECISION,
    size           DOUBLE PRECISION NOT NULL,
    outcome_code   SMALLINT CHECK (outcome_code IN (-1, 0, 1)),  -- loss/timeout/win
    r_multiple     DOUBLE PRECISION,
    costs          JSONB
);

CREATE TABLE risk_metrics (
    as_of          TIMESTAMPTZ NOT NULL,
    scope          TEXT NOT NULL,
    metric         TEXT NOT NULL,
    value          DOUBLE PRECISION,
    engine_version TEXT NOT NULL,
    PRIMARY KEY (as_of, scope, metric)
);

CREATE TABLE dashboard_snapshots (
    snapshot_id    TEXT PRIMARY KEY,
    captured_at    TIMESTAMPTZ NOT NULL,
    payload        JSONB NOT NULL,
    engine_version TEXT NOT NULL,
    git_commit     TEXT
);

CREATE TABLE system_health (
    checked_at     TIMESTAMPTZ NOT NULL,
    component      TEXT NOT NULL,
    quality        TEXT NOT NULL,
    detail         TEXT,
    latency_ms     DOUBLE PRECISION,
    PRIMARY KEY (checked_at, component)
);

-- Append-only. Section 84: every production result must answer what/why/when.
CREATE TABLE audit_logs (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    logged_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    component      TEXT NOT NULL,
    severity       TEXT NOT NULL,
    signal_id      TEXT,
    request_id     TEXT,
    message        TEXT NOT NULL,
    context        JSONB,
    engine_version TEXT NOT NULL,
    git_commit     TEXT
);
CREATE INDEX audit_logs_signal ON audit_logs (signal_id, logged_at DESC);

INSERT INTO schema_version (version) VALUES ('0001');

COMMIT;

-- A (fixture, bookmaker, market, selection, captured_at) combination is one
-- fact — the same price, from the same book, for the same outcome, captured
-- at the same instant. Nothing before odds_sync.py needed this to be unique
-- because nothing wrote more than one row per statement; batching the whole
-- run into a single insert (see jobs/odds_sync.py) made a duplicate-write
-- retry after a dropped connection a real possibility, and this constraint
-- plus `on conflict do nothing` is what makes that retry safe rather than a
-- silent double-write.
create unique index if not exists odds_snapshots_dedupe_idx
    on odds_snapshots (fixture_id, bookmaker, market, selection, captured_at);

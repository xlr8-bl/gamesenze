-- 0001_core.sql — canonical entities.
-- Plain Postgres only: no vendor-specific extensions (§9.3, portability).

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Teams and competitions
-- ---------------------------------------------------------------------------
create table if not exists competitions (
    id            uuid primary key default gen_random_uuid(),
    sport         text not null check (sport in ('football', 'basketball')),
    name          text not null,
    country       text,
    tier          int,
    created_at    timestamptz not null default now(),
    unique (sport, name, country)
);

create table if not exists teams (
    id            uuid primary key default gen_random_uuid(),
    sport         text not null check (sport in ('football', 'basketball')),
    canonical_name text not null,
    short_name    text,
    country       text,
    created_at    timestamptz not null default now(),
    unique (sport, canonical_name)
);

-- §4.3 — every ingested record resolves to a canonical team ID before storage.
-- Unresolved names raise a QA flag and block publication (REQ-DATA-NORM-1).
create table if not exists team_aliases (
    id                bigserial primary key,
    canonical_team_id uuid not null references teams (id) on delete cascade,
    source            text not null,
    source_name       text not null,
    source_id         text,
    created_at        timestamptz not null default now(),
    unique (source, source_name)
);

create index if not exists team_aliases_canonical_idx
    on team_aliases (canonical_team_id);

-- Names seen in the wild that we could not resolve. Populated by the ingestion
-- path so the backlog is visible rather than silently dropped.
create table if not exists unresolved_team_names (
    id           bigserial primary key,
    source       text not null,
    source_name  text not null,
    sport        text,
    first_seen   timestamptz not null default now(),
    last_seen    timestamptz not null default now(),
    sightings    int not null default 1,
    resolved_at  timestamptz,
    unique (source, source_name)
);

-- ---------------------------------------------------------------------------
-- Fixtures
-- ---------------------------------------------------------------------------
create table if not exists fixtures (
    id              uuid primary key default gen_random_uuid(),
    sport           text not null check (sport in ('football', 'basketball')),
    competition_id  uuid references competitions (id),
    home_team_id    uuid references teams (id),
    away_team_id    uuid references teams (id),
    kickoff_at      timestamptz not null,
    status          text not null default 'scheduled'
                    check (status in ('scheduled', 'live', 'finished',
                                      'postponed', 'cancelled')),
    home_goals      int,
    away_goals      int,
    venue           text,
    -- REQ-BUDGET-1: only covered fixtures get snapshotted.
    covered         boolean not null default false,
    covered_at      timestamptz,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists fixtures_kickoff_idx on fixtures (kickoff_at);
create index if not exists fixtures_covered_idx on fixtures (covered, kickoff_at)
    where covered;
create index if not exists fixtures_status_idx on fixtures (status, kickoff_at);

-- Vendor fixture ids, kept out of `fixtures` so one fixture can carry several.
create table if not exists fixture_source_ids (
    fixture_id  uuid not null references fixtures (id) on delete cascade,
    source      text not null,
    source_id   text not null,
    primary key (source, source_id)
);

-- ---------------------------------------------------------------------------
-- Odds
-- ---------------------------------------------------------------------------
create table if not exists odds_snapshots (
    id             bigserial primary key,
    fixture_id     uuid not null references fixtures (id) on delete cascade,
    captured_at    timestamptz not null default now(),
    bookmaker      text not null,
    market         text not null,          -- e.g. '1x2', 'ou_2.5', 'btts'
    selection      text not null,          -- e.g. 'home', 'over', 'yes'
    decimal_odds   numeric(10, 3) not null
                   check (decimal_odds >= 1.01 and decimal_odds <= 1000.0),
    -- Which cadence window (§3.4) produced this capture.
    window_label   text,
    -- REQ-QA-5: the closing line is the honest benchmark.
    is_closing     boolean not null default false
);

create index if not exists odds_snapshots_fixture_idx
    on odds_snapshots (fixture_id, market, selection, captured_at desc);
create index if not exists odds_snapshots_closing_idx
    on odds_snapshots (fixture_id) where is_closing;

-- ---------------------------------------------------------------------------
-- Analysis inputs
-- ---------------------------------------------------------------------------
-- Per-team, per-match observations. All feature computation reads this table
-- through get_features_as_of() and filters on kickoff_at (REQ-QA-4).
create table if not exists team_match_stats (
    id            bigserial primary key,
    fixture_id    uuid not null references fixtures (id) on delete cascade,
    team_id       uuid not null references teams (id) on delete cascade,
    kickoff_at    timestamptz not null,
    status        text not null,
    is_home       boolean not null,
    goals_for     int,
    goals_against int,
    xg            numeric(6, 3),
    xga           numeric(6, 3),
    ppda          numeric(6, 2),
    corners       int,
    source        text not null,
    unique (fixture_id, team_id, source)
);

create index if not exists team_match_stats_asof_idx
    on team_match_stats (team_id, kickoff_at desc)
    where status = 'finished';

create table if not exists player_match_stats (
    id             bigserial primary key,
    fixture_id     uuid not null references fixtures (id) on delete cascade,
    player_id      text not null,
    player_name    text not null,
    team_id        uuid references teams (id),
    kickoff_at     timestamptz not null,
    minutes        int check (minutes between 0 and 120),
    started        boolean,
    goals          int,
    assists        int,
    shots          int,
    source         text not null,
    unique (fixture_id, player_id, source)
);

create index if not exists player_match_stats_asof_idx
    on player_match_stats (player_id, kickoff_at desc);

create table if not exists lineups (
    id          bigserial primary key,
    fixture_id  uuid not null references fixtures (id) on delete cascade,
    team_id     uuid references teams (id),
    source      text not null,
    confirmed   boolean not null default false,
    player_ids  text[] not null,
    fetched_at  timestamptz not null default now(),
    unique (fixture_id, team_id, source)
);

create table if not exists referees (
    id           uuid primary key default gen_random_uuid(),
    name         text not null unique,
    matches_seen int not null default 0
);

create table if not exists weather_snapshots (
    fixture_id     uuid primary key references fixtures (id) on delete cascade,
    fetched_at     timestamptz not null default now(),
    temperature_c  numeric(5, 2),
    wind_kph       numeric(5, 2),
    precip_mm      numeric(5, 2),
    conditions     text
);

-- ---------------------------------------------------------------------------
-- Picks
-- ---------------------------------------------------------------------------
create table if not exists picks (
    id                uuid primary key default gen_random_uuid(),
    fixture_id        uuid not null references fixtures (id) on delete cascade,
    market            text not null,
    selection         text not null,
    -- Our number, before any comparison with the market.
    internal_prob     numeric(6, 5)
                      check (internal_prob > 0 and internal_prob < 1),
    -- The price we saw when the pick was written.
    capture_odds      numeric(10, 3),
    capture_bookmaker text,
    captured_at       timestamptz,
    -- REQ-QA-5: filled at lock; backtests measure against this, not capture.
    closing_odds      numeric(10, 3),
    closing_bookmaker text,
    confidence_tag    text check (confidence_tag in
                          ('lean', 'strong_lean', 'best_bet')),
    stakes_tags       text[],
    reasoning_full    text,
    valid_factors     text[] not null default '{}',
    excluded_factors  jsonb not null default '[]'::jsonb,  -- REQ-QA-2
    status            text not null default 'draft'
                      check (status in ('draft', 'blocked', 'published',
                                        'settled', 'void')),
    reviewed_by       text,                                 -- REQ-QA-3
    reviewed_at       timestamptz,
    published_at      timestamptz,
    result            text check (result in ('won', 'lost', 'push', 'void')),
    settled_at        timestamptz,
    settled_sources   text[],
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);

create index if not exists picks_status_idx on picks (status, published_at desc);
create index if not exists picks_fixture_idx on picks (fixture_id);

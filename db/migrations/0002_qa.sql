-- 0002_qa.sql — the supervision layer (§7).
-- Deployed before any ingestion runs: analysis built on unvalidated data has
-- to be rebuilt, validation built first never does (§11).

-- ---------------------------------------------------------------------------
-- qa_flags — every layer in §5 writes here.
-- ---------------------------------------------------------------------------
create table if not exists qa_flags (
    id              bigserial primary key,
    entity_type     text not null
                    check (entity_type in ('fixture', 'pick', 'odds',
                                           'player', 'team', 'scrape',
                                           'budget')),
    entity_id       uuid,
    entity_ref      text,          -- for entities without a uuid (e.g. source keys)
    issue           text not null,
    detail          text,
    severity        text not null check (severity in ('block', 'review', 'info')),
    raised_at       timestamptz not null default now(),
    resolved_at     timestamptz,
    resolved_by     text,
    resolution_note text
);

-- The hot path is "does this fixture have an unresolved blocking flag?".
create index if not exists qa_flags_open_idx
    on qa_flags (entity_type, entity_id, severity)
    where resolved_at is null;
create index if not exists qa_flags_raised_idx on qa_flags (raised_at desc);

-- One open flag per (entity, issue): re-raising an existing problem should not
-- multiply rows, or the daily audit's unresolved count becomes noise.
create unique index if not exists qa_flags_dedupe_idx
    on qa_flags (entity_type, coalesce(entity_id::text, entity_ref), issue)
    where resolved_at is null;

-- ---------------------------------------------------------------------------
-- data_provenance — REQ-SCRAPE-5. Raw first, parse second.
-- ---------------------------------------------------------------------------
create table if not exists data_provenance (
    id             bigserial primary key,
    entity_type    text not null,
    entity_id      uuid,
    entity_ref     text,
    source         text not null,
    fetched_at     timestamptz not null default now(),
    request_url    text,
    raw_response   jsonb,
    parser_version text not null default 'v1',
    content_hash   text
);

create index if not exists data_provenance_entity_idx
    on data_provenance (entity_type, entity_id, fetched_at desc);
create index if not exists data_provenance_fetched_idx
    on data_provenance (fetched_at);
-- Prune raw_response after 60 days to protect the 500MB ceiling (§7).
create index if not exists data_provenance_prune_idx
    on data_provenance (fetched_at) where raw_response is not null;

-- ---------------------------------------------------------------------------
-- api_budget — REQ-BUDGET-3. Every vendor call increments a row here.
-- ---------------------------------------------------------------------------
create table if not exists api_budget (
    provider    text not null,
    period      text not null,      -- 'YYYY-MM' or 'YYYY-MM-DD'
    calls_used  int not null default 0,
    calls_limit int not null,
    updated_at  timestamptz not null default now(),
    primary key (provider, period)
);

-- Per-call ledger. Cheap to keep at our volume and it is the only way to
-- answer "what burned the budget on the 14th?" after the fact.
create table if not exists api_calls (
    id          bigserial primary key,
    provider    text not null,
    endpoint    text not null,
    called_at   timestamptz not null default now(),
    status_code int,
    cost        int not null default 1,
    job         text
);

create index if not exists api_calls_called_idx on api_calls (called_at desc);

-- ---------------------------------------------------------------------------
-- publication_blocks — §5.5. Silence is the safe state, but never a silent one.
-- ---------------------------------------------------------------------------
create table if not exists publication_blocks (
    id            bigserial primary key,
    fixture_id    uuid references fixtures (id) on delete cascade,
    pick_id       uuid references picks (id) on delete cascade,
    failed_checks text[] not null,
    blocked_at    timestamptz not null default now()
);

create index if not exists publication_blocks_at_idx
    on publication_blocks (blocked_at desc);

-- ---------------------------------------------------------------------------
-- backtest_runs — §5.7.
-- ---------------------------------------------------------------------------
create table if not exists backtest_runs (
    id                bigserial primary key,
    run_at            timestamptz not null default now(),
    label             text,
    pick_count        int not null,
    as_of_correct     boolean not null,
    vs_closing_line   boolean not null,
    brier_score       numeric(8, 5),
    calibration_error numeric(8, 5),
    roi               numeric(8, 5),
    hit_rate          numeric(6, 5),
    ci_low            numeric(6, 5),
    ci_high           numeric(6, 5),
    notes             text
);

-- Per-bucket calibration detail for the run (REQ-QA-8).
create table if not exists backtest_calibration_bins (
    id            bigserial primary key,
    run_id        bigint not null references backtest_runs (id) on delete cascade,
    bin_low       numeric(6, 5) not null,
    bin_high      numeric(6, 5) not null,
    predicted_avg numeric(6, 5) not null,
    observed_rate numeric(6, 5) not null,
    n             int not null
);

-- ---------------------------------------------------------------------------
-- scrape_runs — so a silent scraper failure shows up in the daily audit.
-- ---------------------------------------------------------------------------
create table if not exists scrape_runs (
    id           bigserial primary key,
    source       text not null,
    job          text not null,
    started_at   timestamptz not null default now(),
    finished_at  timestamptz,
    status       text not null default 'running'
                 check (status in ('running', 'ok', 'failed', 'skipped')),
    rows_written int not null default 0,
    error        text
);

create index if not exists scrape_runs_started_idx on scrape_runs (started_at desc);

-- ---------------------------------------------------------------------------
-- daily_audit_reports — §5.6, one row per audited day.
-- ---------------------------------------------------------------------------
create table if not exists daily_audit_reports (
    audit_date  date primary key,
    generated_at timestamptz not null default now(),
    report      jsonb not null,
    alerted     boolean not null default false
);

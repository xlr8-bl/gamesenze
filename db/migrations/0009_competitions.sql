-- 0009_competitions.sql — vendor IDs for competitions, resolved not guessed.
--
-- Mirrors fixture_source_ids exactly. A competition's numeric API-Football ID
-- is not something to hardcode from memory or a scraped blog post: two
-- independent lookups during this build produced conflicting numbers for the
-- same competition, which is precisely the class of error REQ-DATA-NORM-1
-- exists to catch for team names. The same discipline applies here — an
-- unresolved competition has no source id, and fixture_sync refuses to run
-- for it rather than guess.

create table if not exists competition_source_ids (
    competition_id uuid not null references competitions (id) on delete cascade,
    source         text not null,
    source_id      text not null,
    -- The name/country the source returned at resolution time, kept as
    -- evidence for why this ID was accepted — the same audit trail
    -- data_provenance gives every other resolved fact.
    resolved_name    text,
    resolved_country text,
    -- The vendor's "current" season year at resolution time. Seasons roll
    -- over annually; re-running resolve_competitions each pre-season keeps
    -- this current rather than fixture_sync silently pulling last year's
    -- fixtures against a stale year.
    resolved_season  int,
    resolved_at      timestamptz not null default now(),
    resolved_by      text not null,
    primary key (source, source_id)
);

create unique index if not exists competition_source_ids_comp_idx
    on competition_source_ids (competition_id, source);

-- Whether a competition's table (standings) makes sense to fetch. Knockout
-- cups have no table, so standings_refresh should never be called for them —
-- calling it anyway wastes a call and gets an error back, not data.
alter table competitions add column if not exists needs_standings boolean not null default true;

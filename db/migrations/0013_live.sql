-- 0013_live.sql — in-play match state and the events on the clock.
--
-- The board is about fixtures you can still act on; this is about fixtures in
-- progress. They are disjoint by kickoff time, so a match moves from the board
-- to the live view the moment it starts, and to the record when it finishes.
--
-- The score and the clock live in one row per fixture that a live poller
-- upserts; the goals and cards live as an append-only log, because a timeline
-- is a sequence of events and reconstructing it from a running total loses the
-- minute each one happened.

create table if not exists match_state (
    fixture_id  uuid primary key references fixtures (id) on delete cascade,
    phase       text not null default 'pre'
                check (phase in ('pre', 'live', 'ht', 'ft')),
    minute      int check (minute >= 0 and minute <= 130),
    home_score  int not null default 0 check (home_score >= 0),
    away_score  int not null default 0 check (away_score >= 0),
    updated_at  timestamptz not null default now()
);

create table if not exists match_events (
    id          uuid primary key default gen_random_uuid(),
    fixture_id  uuid not null references fixtures (id) on delete cascade,
    minute      int not null check (minute >= 0 and minute <= 130),
    side        text not null check (side in ('home', 'away')),
    kind        text not null
                check (kind in ('goal', 'own_goal', 'pen_goal', 'yellow', 'red')),
    player      text,
    created_at  timestamptz not null default now()
);
create index if not exists match_events_fixture_idx
    on match_events (fixture_id, minute);

-- The live hub: every in-play fixture, its score and clock, the published pick
-- riding on it, and its goals as an ordered array so the page makes one read.
create or replace view v_live_board as
select f.id                    as fixture_id,
       f.sport,
       f.kickoff_at,
       c.name                  as competition,
       ht.canonical_name       as home_team,
       at.canonical_name       as away_team,
       ms.phase,
       ms.minute,
       ms.home_score,
       ms.away_score,
       ms.updated_at,
       p.market,
       p.selection,
       p.confidence_tag,
       -- The goal timeline, oldest first, only the events a fan watches for.
       coalesce(
         (select jsonb_agg(jsonb_build_object(
                   'minute', e.minute, 'side', e.side,
                   'kind', e.kind, 'player', e.player) order by e.minute)
            from match_events e
           where e.fixture_id = f.id
             and e.kind in ('goal', 'own_goal', 'pen_goal')),
         '[]'::jsonb)          as goals
  from fixtures f
  join match_state ms on ms.fixture_id = f.id
  left join competitions c on c.id = f.competition_id
  left join teams ht on ht.id = f.home_team_id
  left join teams at on at.id = f.away_team_id
  left join lateral (
      select market, selection, confidence_tag
        from picks
       where fixture_id = f.id and status in ('published', 'settled')
       order by published_at desc
       limit 1
  ) p on true
 where ms.phase in ('live', 'ht')
 order by ms.minute desc nulls last;

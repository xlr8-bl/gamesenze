-- 0007_analysis.sql — derived tables the analysis layer reads.
--
-- These are caches of things computable from team_match_stats and
-- player_match_stats. They exist because recomputing them per pick would be
-- slow, not because they are a second source of truth — anything here can be
-- dropped and rebuilt by the weekly jobs.

-- Gated at 10 appearances of 45+ minutes (§5.4). A player below the gate has
-- no row rather than a row with a wide error bar: a factor that exists is a
-- factor someone will eventually use.
create table if not exists player_variance (
    player_id   text primary key,
    appearances int not null,
    mean_ga     numeric(8, 4),
    sd_ga       numeric(8, 4),
    mean_shots  numeric(8, 4),
    computed_at timestamptz not null default now()
);

-- Referee tendencies, gated at 20 matches at level.
create table if not exists referee_tendencies (
    referee_id     uuid primary key references referees (id) on delete cascade,
    matches        int not null,
    cards_per_game numeric(6, 3),
    pens_per_game  numeric(6, 3),
    computed_at    timestamptz not null default now()
);

-- Closing lines, denormalised for the backtest. Populated at lock from the
-- snapshot marked is_closing; REQ-QA-5 makes this the number that matters, so
-- it gets its own row rather than being rediscovered by query each time.
create or replace function capture_closing_lines()
returns int
language sql
as $$
    with closing as (
        select distinct on (o.fixture_id, o.market, o.selection)
               o.fixture_id, o.market, o.selection, o.decimal_odds, o.bookmaker
          from odds_snapshots o
         where o.is_closing
         order by o.fixture_id, o.market, o.selection, o.captured_at desc
    ),
    updated as (
        update picks p
           set closing_odds = c.decimal_odds,
               closing_bookmaker = c.bookmaker,
               updated_at = now()
          from closing c
         where c.fixture_id = p.fixture_id
           and c.market = p.market
           and c.selection = p.selection
           and p.closing_odds is null
        returning 1
    )
    select count(*)::int from updated;
$$;

-- Picks published without a closing line captured. §10 requires the closing
-- line for every pick, so this should always be empty once a fixture is done.
create or replace view v_missing_closing_lines as
select p.id as pick_id, p.fixture_id, p.market, p.selection, f.kickoff_at
  from picks p
  join fixtures f on f.id = p.fixture_id
 where p.status in ('published', 'settled')
   and p.closing_odds is null
   and f.kickoff_at < now();

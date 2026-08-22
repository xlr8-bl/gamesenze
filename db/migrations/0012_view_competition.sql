-- 0012_view_competition.sql — carry the competition through to the frontend.
--
-- The board renders each fixture under its competition's own colours, so the
-- competition has to reach the browser. It was the one join the read models
-- were missing: fixtures knew it, the views dropped it.
--
-- Both views are recreated rather than altered, because Postgres will not add
-- a column to an existing view in place.

drop view if exists v_published_picks;
create view v_published_picks as
select p.id,
       p.fixture_id,
       p.market,
       p.selection,
       p.confidence_tag,
       p.stakes_tags,
       p.internal_prob,
       p.capture_odds,
       p.capture_bookmaker,
       p.closing_odds,
       p.reasoning_full,
       p.valid_factors,
       p.excluded_factors,
       p.published_at,
       p.result,
       f.sport,
       f.kickoff_at,
       f.status                as fixture_status,
       c.name                  as competition,
       c.country               as competition_country,
       ht.canonical_name       as home_team,
       at.canonical_name       as away_team,
       latest.decimal_odds     as latest_odds,
       latest.bookmaker        as latest_bookmaker,
       latest.captured_at      as latest_odds_at
  from picks p
  join fixtures f on f.id = p.fixture_id
  left join competitions c on c.id = f.competition_id
  left join teams ht on ht.id = f.home_team_id
  left join teams at on at.id = f.away_team_id
  left join lateral (
      select o.decimal_odds, o.bookmaker, o.captured_at
        from odds_snapshots o
       where o.fixture_id = p.fixture_id
         and o.market = p.market
         and o.selection = p.selection
       order by o.captured_at desc
       limit 1
  ) latest on true
 where p.status in ('published', 'settled');

drop view if exists v_record_summary;
drop view if exists v_pick_record;
create view v_pick_record as
select p.id,
       p.fixture_id,
       p.market,
       p.selection,
       p.confidence_tag,
       p.internal_prob,
       p.capture_odds,
       p.capture_bookmaker,
       p.closing_odds,
       p.published_at,
       p.settled_at,
       p.result,
       f.sport,
       f.kickoff_at,
       c.name            as competition,
       ht.canonical_name as home_team,
       at.canonical_name as away_team,
       case
           when p.closing_odds is null or p.capture_odds is null then null
           else round(100.0 * (p.capture_odds / p.closing_odds - 1), 2)
       end as clv_pct,
       case p.result
           when 'won'  then round(p.capture_odds - 1, 3)
           when 'lost' then -1.0
           else 0.0
       end as unit_return
  from picks p
  join fixtures f on f.id = p.fixture_id
  left join competitions c on c.id = f.competition_id
  left join teams ht on ht.id = f.home_team_id
  left join teams at on at.id = f.away_team_id
 where p.status = 'settled'
   and p.result is not null;

-- Unchanged from 0011, recreated because it depends on v_pick_record.
create view v_record_summary as
with base as (
    select sport, result, unit_return, clv_pct from v_pick_record
    union all
    select 'all', result, unit_return, clv_pct from v_pick_record
),
agg as (
    select sport,
           count(*)                                           as settled,
           count(*) filter (where result = 'won')              as won,
           count(*) filter (where result = 'lost')             as lost,
           count(*) filter (where result in ('push', 'void'))  as pushed,
           count(clv_pct)                                      as clv_sample,
           sum(unit_return)                                    as units,
           avg(clv_pct)                                        as avg_clv
      from base
     group by sport
)
select sport,
       settled,
       won,
       lost,
       pushed,
       clv_sample,
       settled >= record_sample_floor() as rates_published,
       record_sample_floor()            as sample_floor,
       case when settled >= record_sample_floor() and (won + lost) > 0
            then round(100.0 * won / (won + lost), 1) end as hit_rate_pct,
       case when settled >= record_sample_floor()
            then round(100.0 * units / settled, 1) end     as roi_pct,
       case when clv_sample >= record_sample_floor()
            then round(avg_clv, 2) end                     as avg_clv_pct,
       round(units, 2)                                     as units
  from agg;

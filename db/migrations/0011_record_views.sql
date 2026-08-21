-- 0011_record_views.sql — the public track record.
--
-- The site's whole claim is that we show what we do not know, so the record
-- page cannot be a marketing number. Two rules are enforced here rather than
-- in the browser, because a rule enforced in the browser is a rule someone
-- can turn off:
--
--   1. Only settled picks count. A pick still in flight is not a result.
--   2. Below the §5.4 sample floor we return the counts but no rate. The gate
--      lives in the view so every reader of it inherits it.
--
-- CLV (closing line value) is the honest measure: it compares the price we
-- published against the price the market settled on, and it is meaningful long
-- before the win rate is.

-- One row per settled pick. The record page's table reads this directly.
create or replace view v_pick_record as
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
       ht.canonical_name as home_team,
       at.canonical_name as away_team,
       -- Positive CLV means we published a longer price than the close: the
       -- market moved toward us. Null when no closing line was captured, and
       -- null is shown as null, never as zero.
       case
           when p.closing_odds is null or p.capture_odds is null then null
           else round(100.0 * (p.capture_odds / p.closing_odds - 1), 2)
       end as clv_pct,
       -- Level-stake return on one unit, so the page never has to guess a
       -- staking plan it was not given.
       case p.result
           when 'won'  then round(p.capture_odds - 1, 3)
           when 'lost' then -1.0
           else 0.0
       end as unit_return
  from picks p
  join fixtures f on f.id = p.fixture_id
  left join teams ht on ht.id = f.home_team_id
  left join teams at on at.id = f.away_team_id
 where p.status = 'settled'
   and p.result is not null;

-- §5.4 sample floor. Below this the aggregate reports counts and withholds
-- every rate, because a hit rate over 11 bets is noise wearing a percentage
-- sign.
create or replace function record_sample_floor()
returns int
language sql
immutable
as $$ select 30 $$;

-- The headline aggregate, per sport plus an 'all' row.
create or replace view v_record_summary as
with base as (
    select sport, result, unit_return, clv_pct from v_pick_record
    union all
    select 'all', result, unit_return, clv_pct from v_pick_record
),
agg as (
    select sport,
           count(*)                                        as settled,
           count(*) filter (where result = 'won')          as won,
           count(*) filter (where result = 'lost')         as lost,
           count(*) filter (where result in ('push', 'void')) as pushed,
           count(clv_pct)                                  as clv_sample,
           sum(unit_return)                                as units,
           avg(clv_pct)                                    as avg_clv
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
       -- Withheld, not zeroed. A null here means "we will not say yet".
       case when settled >= record_sample_floor() and (won + lost) > 0
            then round(100.0 * won / (won + lost), 1) end as hit_rate_pct,
       case when settled >= record_sample_floor()
            then round(100.0 * units / settled, 1) end     as roi_pct,
       -- CLV has its own sample: a pick can settle without a closing line.
       case when clv_sample >= record_sample_floor()
            then round(avg_clv, 2) end                     as avg_clv_pct,
       round(units, 2)                                     as units
  from agg;

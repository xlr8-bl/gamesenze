-- 0004_views.sql — read models. The frontend reads these, never a vendor API
-- (REQ-BUDGET-2), and never joins across raw tables in the browser.

-- Blocking flags that are still open, per fixture. The publication gate and the
-- daily audit both read this.
create or replace view v_open_blocking_flags as
select entity_id as fixture_id,
       count(*)  as flag_count,
       array_agg(issue order by raised_at) as issues
from qa_flags
where entity_type = 'fixture'
  and severity = 'block'
  and resolved_at is null
  and entity_id is not null
group by entity_id;

-- Current budget position per provider/period, with the §8 ladder rung.
create or replace view v_budget_status as
select provider,
       period,
       calls_used,
       calls_limit,
       case when calls_limit = 0 then 0
            else round(100.0 * calls_used / calls_limit, 1)
       end as pct_used,
       case
           when calls_limit = 0 then 'normal'
           when calls_used >= calls_limit then 'exhausted'
           when calls_used >= 0.9 * calls_limit then 'closing_only'
           when calls_used >= 0.8 * calls_limit then 'reduced'
           else 'normal'
       end as ladder_rung
from api_budget;

-- The public board: published picks with their latest price.
create or replace view v_published_picks as
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
       ht.canonical_name as home_team,
       at.canonical_name as away_team,
       latest.decimal_odds as latest_odds,
       latest.bookmaker    as latest_bookmaker,
       latest.captured_at  as latest_odds_at
from picks p
join fixtures f on f.id = p.fixture_id
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

-- Combo analytics (§12). Aggregated, no per-user detail.
create or replace view v_combo_performance as
select jsonb_array_length(cs.pick_ids) as leg_count,
       count(*) filter (where cb.result is not null)      as settled_bets,
       count(*) filter (where cb.result = 'won')          as won,
       avg(cs.total_odds)                                 as avg_expected_odds,
       avg(cb.odds_received)                              as avg_odds_received,
       sum(cb.stake_amount) filter (where cb.result is not null) as staked,
       sum(case when cb.result = 'won'
                then cb.stake_amount * cb.odds_received
                when cb.result = 'lost' then 0
                else cb.stake_amount end)                 as returned
from combo_sessions cs
left join combo_bets cb on cb.combo_id = cs.id
group by 1;

-- Combo popularity: which published picks get stacked together most (§12).
create or replace view v_combo_pick_popularity as
select l.pick_id,
       count(distinct l.combo_id) as combo_count,
       avg(l.odds)                as avg_leg_odds
from combo_legs l
group by l.pick_id;

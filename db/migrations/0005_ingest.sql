-- 0005_ingest.sql — the Worker's write path.
--
-- §2.3 caveat: Cloudflare Workers allow 10ms CPU per invocation on the free
-- tier. I/O wait does not count, so a fetch-and-write job should pass — but
-- only if it is genuinely fetch-and-write. Parsing a full event object (forty
-- books x several markets x several outcomes) in the Worker is CPU, and it is
-- exactly the kind of work that blows the limit.
--
-- So the Worker relays bytes: it POSTs the vendor payload verbatim into
-- odds_ingest_queue and returns. Postgres does the flattening in a trigger,
-- where CPU is free and the §5.1/§5.3 rules already live.

create table if not exists odds_ingest_queue (
    id           bigserial primary key,
    fixture_id   uuid not null references fixtures (id) on delete cascade,
    window_label text not null,
    captured_at  timestamptz not null default now(),
    source       text not null default 'sportsgameodds',
    payload      jsonb not null,
    processed_at timestamptz,
    rows_written int,
    rejections   text[]
);

create index if not exists odds_ingest_queue_unprocessed_idx
    on odds_ingest_queue (captured_at) where processed_at is null;

-- ---------------------------------------------------------------------------
-- Flatten one queued payload into odds_snapshots.
--
-- Mirrors gamesenze.providers.sgo.parse_odds. The two must agree, and
-- tests/test_ingest_parity.py pins them to the same fixtures so a change to
-- one that is not made to the other fails the build.
-- ---------------------------------------------------------------------------
create or replace function process_odds_ingest(queue_id bigint)
returns int
language plpgsql
as $$
declare
    q            odds_ingest_queue%rowtype;
    book         jsonb;
    market       jsonb;
    outcome      jsonb;
    book_name    text;
    market_key   text;
    selection    text;
    price        numeric;
    implied      numeric;
    written      int := 0;
    rejects      text[] := '{}';
begin
    select * into q from odds_ingest_queue where id = queue_id
        and processed_at is null
        for update skip locked;
    if not found then
        return 0;
    end if;

    for book in select * from jsonb_array_elements(
                    coalesce(q.payload -> 'bookmakers', '[]'::jsonb))
    loop
        book_name := coalesce(book ->> 'key', book ->> 'name', 'unknown');

        for market in select * from jsonb_array_elements(
                          coalesce(book -> 'markets', '[]'::jsonb))
        loop
            market_key := coalesce(market ->> 'key', market ->> 'name', 'unknown');

            for outcome in select * from jsonb_array_elements(
                               coalesce(market -> 'outcomes', '[]'::jsonb))
            loop
                selection := coalesce(outcome ->> 'name', outcome ->> 'key');
                begin
                    price := coalesce((outcome ->> 'price')::numeric,
                                      (outcome ->> 'decimal')::numeric);
                exception when others then
                    price := null;
                end;

                -- §5.1 range rule.
                if price is null then
                    rejects := rejects ||
                        format('%s/%s/%s: decimal_odds missing',
                               book_name, market_key, selection);
                    continue;
                end if;
                if price < 1.01 or price > 1000.0 then
                    rejects := rejects ||
                        format('%s/%s/%s: decimal_odds=%s outside [1.01, 1000.0]',
                               book_name, market_key, selection, price);
                    continue;
                end if;

                -- §5.3 impossible line: implies <1% or >99%.
                implied := 1.0 / price;
                if implied < 0.01 or implied > 0.99 then
                    rejects := rejects ||
                        format('%s/%s/%s: decimal_odds=%s implies %s',
                               book_name, market_key, selection, price,
                               to_char(implied * 100, 'FM990.9999%'));
                    continue;
                end if;

                insert into odds_snapshots (fixture_id, captured_at, bookmaker,
                                            market, selection, decimal_odds,
                                            window_label, is_closing)
                values (q.fixture_id, q.captured_at, book_name, market_key,
                        selection, price, q.window_label,
                        q.window_label = 'lock');
                written := written + 1;
            end loop;
        end loop;
    end loop;

    update odds_ingest_queue
       set processed_at = now(), rows_written = written, rejections = rejects
     where id = q.id;

    -- A payload that produced nothing usable is a coverage problem, not a
    -- quiet no-op: flag it so the daily audit sees it (§5.6).
    if written = 0 then
        insert into qa_flags (entity_type, entity_id, issue, detail, severity)
        values ('fixture', q.fixture_id, 'empty_odds_payload',
                format('queue row %s produced no usable prices (%s rejections)',
                       q.id, coalesce(array_length(rejects, 1), 0)),
                'review')
        on conflict do nothing;
    end if;

    return written;
end;
$$;

create or replace function odds_ingest_queue_after_insert()
returns trigger
language plpgsql
as $$
begin
    perform process_odds_ingest(new.id);
    return null;
end;
$$;

drop trigger if exists odds_ingest_queue_process on odds_ingest_queue;
create trigger odds_ingest_queue_process
    after insert on odds_ingest_queue
    for each row execute function odds_ingest_queue_after_insert();

-- ---------------------------------------------------------------------------
-- The §3.4 cadence, in SQL. Defined before `due_odds_snapshots`, which calls
-- it. This must agree with gamesenze/odds/schedule.py; tests/test_sql_parity.py
-- pins both to the same expected capture times.
-- ---------------------------------------------------------------------------
create or replace function snapshot_plan(
    kickoff timestamptz,
    thinning_factor int default 1,
    closing_only boolean default false
)
returns table (at timestamptz, label text)
language sql
immutable
as $$
    select kickoff - make_interval(mins => offs), label
      from (
        select generate_series(48 * 60, 12 * 60 + 1, -(360 * thinning_factor)) as offs,
               't48_t12' as label
        where not closing_only
        union all
        select generate_series(12 * 60, 3 * 60 + 1, -(180 * thinning_factor)),
               't12_t3'
        where not closing_only
        union all
        select generate_series(3 * 60, 60 + 1, -60), 't3_t1'
        where not closing_only
        union all
        select generate_series(60, 1, -15), 't1_kickoff'
        where not closing_only
        union all
        select 0, 'lock'
      ) points
     order by offs desc;
$$;

-- ---------------------------------------------------------------------------
-- What the Worker asks for on each tick.
--
-- All the cadence arithmetic from §3.4 happens here so the Worker does not
-- have to: it receives a short list of fixture ids and window labels and makes
-- one vendor call each.
-- ---------------------------------------------------------------------------
create or replace function due_odds_snapshots(
    at_time timestamptz default now(),
    grace_minutes int default 10,
    max_fixtures int default 20
)
returns table (
    fixture_id   uuid,
    vendor_event_id text,
    window_label text,
    kickoff_at   timestamptz
)
language sql
stable
as $$
    with rung as (
        select ladder_rung
          from v_budget_status
         where provider = 'sportsgameodds'
           and period = to_char(at_time, 'YYYY-MM')
         limit 1
    ),
    plan as (
        select f.id,
               s.source_id as vendor_event_id,
               f.kickoff_at,
               p.at,
               p.label
          from fixtures f
          join fixture_source_ids s
            on s.fixture_id = f.id and s.source = 'sportsgameodds'
          -- REQ-BUDGET-1: covered fixtures only. Never poll the board.
         cross join lateral snapshot_plan(
               f.kickoff_at,
               case when coalesce((select ladder_rung from rung), 'normal')
                         in ('reduced', 'closing_only') then 2 else 1 end,
               coalesce((select ladder_rung from rung), 'normal')
                    in ('closing_only', 'exhausted')
         ) as p(at, label)
         where f.covered
           and f.status = 'scheduled'
           and coalesce((select ladder_rung from rung), 'normal') <> 'exhausted'
    )
    select plan.id, plan.vendor_event_id, plan.label, plan.kickoff_at
      from plan
     where plan.at <= at_time
       and plan.at > at_time - make_interval(mins => grace_minutes)
       and not exists (
           select 1 from odds_snapshots o
            where o.fixture_id = plan.id
              and o.window_label = plan.label
              and o.captured_at > plan.at - interval '1 minute'
       )
     order by plan.kickoff_at
     limit max_fixtures;
$$;

-- 0006_lineups.sql — the T-1h lineup watch.
--
-- §2.1 is the whole reason this path is separate: a confirmed XI fetched 30
-- minutes late is a confirmed XI fetched after the market already moved on it.
-- GitHub Actions cannot promise the timing, so the Worker owns this and the
-- database owns the arithmetic.

create table if not exists lineup_ingest_queue (
    id           bigserial primary key,
    fixture_id   uuid not null references fixtures (id) on delete cascade,
    source       text not null default 'api_football',
    captured_at  timestamptz not null default now(),
    payload      jsonb not null,
    processed_at timestamptz,
    rows_written int
);

create index if not exists lineup_ingest_queue_unprocessed_idx
    on lineup_ingest_queue (captured_at) where processed_at is null;

-- Which covered fixtures are inside their T-1h window and still have no
-- confirmed XI. Bounded on both sides so a fixture is asked about once, not
-- once a minute for an hour: the T-1h budget line is 12 calls a day (§3.2).
create or replace function due_lineup_checks(
    at_time timestamptz default now(),
    max_fixtures int default 20
)
returns table (fixture_id uuid, vendor_fixture_id text, kickoff_at timestamptz)
language sql
stable
as $$
    select f.id, s.source_id, f.kickoff_at
      from fixtures f
      join fixture_source_ids s
        on s.fixture_id = f.id and s.source = 'api_football'
     where f.covered
       and f.status = 'scheduled'
       and f.kickoff_at between at_time + interval '45 minutes'
                            and at_time + interval '75 minutes'
       and not exists (
           select 1 from lineups l
            where l.fixture_id = f.id
              and l.source = 'api_football'
              and l.confirmed
       )
       and not exists (
           -- one attempt per fixture per window, successful or not
           select 1 from lineup_ingest_queue q
            where q.fixture_id = f.id
              and q.captured_at > at_time - interval '40 minutes'
       )
     order by f.kickoff_at
     limit max_fixtures;
$$;

create or replace function process_lineup_ingest(queue_id bigint)
returns int
language plpgsql
as $$
declare
    q       lineup_ingest_queue%rowtype;
    v_entry   jsonb;
    v_team_nm text;
    v_team_id uuid;
    v_players text[];
    v_written int := 0;
begin
    select * into q from lineup_ingest_queue
     where id = queue_id and processed_at is null
       for update skip locked;
    if not found then
        return 0;
    end if;

    for v_entry in select * from jsonb_array_elements(
                     coalesce(q.payload -> 'response', '[]'::jsonb))
    loop
        v_team_nm := v_entry #>> '{team,name}';

        -- REQ-DATA-NORM-1: resolve through team_aliases or do not store.
        -- An unresolved name raises a blocking flag; it does not get a guess.
        select ta.canonical_team_id into v_team_id
          from team_aliases ta
         where ta.source = q.source and ta.source_name = v_team_nm;

        if v_team_id is null then
            insert into qa_flags (entity_type, entity_id, issue, detail, severity)
            values ('fixture', q.fixture_id, 'unresolved_team_name',
                    format('%s sent %L in a lineup payload; not in team_aliases',
                           q.source, v_team_nm),
                    'block')
            on conflict do nothing;

            insert into unresolved_team_names (source, source_name, first_seen,
                                               last_seen, sightings)
            values (q.source, v_team_nm, now(), now(), 1)
            on conflict (source, source_name) do update
                set last_seen = now(),
                    sightings = unresolved_team_names.sightings + 1;
            continue;
        end if;

        select array_agg(p #>> '{player,id}')
          into v_players
          from jsonb_array_elements(
                   coalesce(v_entry -> 'startXI', '[]'::jsonb)) as p;

        if v_players is null or array_length(v_players, 1) is null then
            continue;
        end if;

        insert into lineups (fixture_id, team_id, source, confirmed, player_ids,
                             fetched_at)
        values (q.fixture_id, v_team_id, q.source, true, v_players, q.captured_at)
        on conflict (fixture_id, team_id, source) do update
            set confirmed = true,
                player_ids = excluded.player_ids,
                fetched_at = excluded.fetched_at;
        v_written := v_written + 1;
    end loop;

    update lineup_ingest_queue
       set processed_at = now(), rows_written = v_written
     where id = q.id;
    return v_written;
end;
$$;

create or replace function lineup_ingest_queue_after_insert()
returns trigger
language plpgsql
as $$
begin
    perform process_lineup_ingest(new.id);
    return null;
end;
$$;

drop trigger if exists lineup_ingest_queue_process on lineup_ingest_queue;
create trigger lineup_ingest_queue_process
    after insert on lineup_ingest_queue
    for each row execute function lineup_ingest_queue_after_insert();
